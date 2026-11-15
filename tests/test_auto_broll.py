import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "auto-broll"
sys.path.insert(0, str(SKILL / "scripts"))
import broll  # noqa: E402
import cues  # noqa: E402

TRANSCRIPT = json.loads((SKILL / "examples" / "talk.transcript.json").read_text())
PLAN = json.loads((SKILL / "examples" / "talk.broll.json").read_text())
HAS_FF = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def plan(**over):
    p = json.loads(json.dumps(PLAN))
    p["_dir"] = str(SKILL / "examples")
    p.update(over)
    return p


def test_lines_are_sentences_with_word_times():
    lines = broll.group_lines(cues.words(TRANSCRIPT))
    assert [ln["text"] for ln in lines][0] == "Want to grow your channel in another language?"
    assert len(lines) == 3
    for ln in lines:
        starts = [s for _, s in ln["words"]]
        assert starts == sorted(starts)
        assert ln["start"] == starts[0]


def test_number_words_match_digits_both_ways():
    assert broll.norm("ninety-three degrees") == ["93", "degrees"]
    assert broll.norm("a hundred videos") == ["100", "videos"]
    assert broll.norm("1,000 subscribers") == ["1000", "subscribers"]
    assert broll.norm("one hundred and five") == ["105"]
    lines = [{"i": 0, "start": 0, "end": 3, "words": [["Aim", 0.0], ["for", 0.3], ["93", 0.6], ["degrees,", 1.0]]}]
    assert broll.find_word(lines, "ninety three degrees")["start"] == 0.6


def test_find_word_respects_line_and_order():
    lines = broll.group_lines(cues.words(TRANSCRIPT))
    hit = broll.find_word(lines, "Your", line=2)
    assert hit["line"] == 2
    first = broll.find_word(lines, "your")
    second = broll.find_word(lines, "your", after=first["start"])
    assert second["start"] > first["start"]
    assert broll.find_word(lines, "subscribers") is None


def test_cut_lands_just_before_the_word():
    ev = broll.resolve(plan())
    lines = plan()["lines"]
    w = broll.find_word(lines, "another language", 0)
    assert ev[0]["start"] == pytest.approx(w["start"] - broll.DEFAULT_RULES["lead"], abs=1e-6)
    assert ev[0]["problems"] == ["clip not found: broll/globe.mp4"]  # example ships without media


def test_overlaps_are_trimmed_and_flagged():
    ev = broll.resolve(plan())
    up = ev[3]
    assert up["start"] + up["dur"] <= ev[4]["start"] + 1e-6
    p = plan(cutaways=[{"line": 2, "on": "upload", "clip": "x.mp4", "dur": 5},
                       {"line": 2, "on": "retention", "clip": "y.mp4"}])
    ev = broll.resolve(p)
    assert any("trimmed" in w for w in ev[0]["warnings"])


def test_problems_and_warnings():
    p = plan(cutaways=[{"line": 0, "on": "grow", "clip": "nope.mp4"},
                       {"line": 1, "on": "payoff", "clip": "pexels:stopwatch"},
                       {"line": 2, "on": "watch", "clip": "a.txt"},
                       {"line": 1, "on": "zebra", "clip": "a.mp4"}])
    ev = broll.resolve(p)
    assert any("not found" in x for x in ev[0]["problems"])
    assert any("the hook" in x for x in ev[0]["warnings"])
    assert any("fetch" in x for x in ev[1]["problems"])
    assert any("not a video or image" in x or "not found" in x for x in ev[2]["problems"])
    assert any("'zebra' not found" in x for x in ev[3]["problems"])


def test_flash_cut_warning_and_duration_clamped_to_video():
    p = plan(cutaways=[{"line": 2, "on": "climb", "clip": "c.mp4", "dur": 9}])
    ev = broll.resolve(p)[0]
    assert ev["start"] + ev["dur"] <= p["duration"] + 1e-6
    p = plan(cutaways=[{"line": 1, "on": "rule", "clip": "c.mp4", "dur": 0.6}])
    assert any("flash" in w for w in broll.resolve(p)[0]["warnings"])


def test_narration_mode_fills_the_whole_runtime():
    nar = json.loads((SKILL / "examples" / "coffee.narration.broll.json").read_text())
    nar["_dir"] = str(SKILL / "examples")
    ev = [e for e in broll.resolve(nar) if "start" in e]
    assert ev[0]["start"] == 0
    for a, b in zip(ev, ev[1:]):
        assert a["start"] + a["dur"] == pytest.approx(b["start"], abs=1e-3)
    assert ev[-1]["start"] + ev[-1]["dur"] == pytest.approx(nar["duration"], abs=1e-3)
    assert not any("the hook" in w for e in ev for w in e["warnings"])


def test_script_paragraphs_skip_headings_and_notes():
    text = "# Title\n\nFirst line\nwraps here. [show logo]\n\n<!-- note -->\nSecond."
    assert broll.script_paragraphs(text) == ["First line wraps here.", "Second."]


def test_edl_is_cmx3600():
    ev = [{"clip": "broll/espresso shot.mp4", "start": 2.5, "dur": 2.0, "clip_start": 1.0, "on": "espresso"}]
    edl = broll.to_edl("demo", ev)
    assert "TITLE: demo" in edl and "FCM: NON-DROP FRAME" in edl
    assert "001  ESPRESSO V     C        00:00:01:00 00:00:03:00 00:00:02:15 00:00:04:15" in edl
    assert "* FROM CLIP NAME: espresso shot.mp4" in edl


def test_pexels_rendition_choice():
    video = {"video_files": [
        {"file_type": "video/mp4", "width": 640, "height": 360, "link": "s"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "m"},
        {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "l"}]}
    assert broll.pick_pexels_file(video, 1920, 1080)["link"] == "m"
    assert broll.pick_pexels_file(video, 1080, 1920)["link"] == "m"
    assert broll.pick_pexels_file({"video_files": [video["video_files"][0]]}, 1920, 1080)["link"] == "s"


def test_fetch_without_key_explains(tmp_path, monkeypatch, capsys):
    p = tmp_path / "x.broll.json"
    d = plan(cutaways=[{"line": 0, "on": "grow", "clip": "pexels:plant"}])
    d.pop("_dir")
    p.write_text(json.dumps(d))
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        broll.main(["fetch", str(p)])
    assert "pexels.com/api" in capsys.readouterr().err


def test_check_exit_codes(tmp_path):
    p = tmp_path / "x.broll.json"
    d = plan(cutaways=[{"line": 1, "on": "zebra", "clip": "a.mp4"}])
    d.pop("_dir")
    p.write_text(json.dumps(d))
    assert broll.main(["check", str(p)]) == 1


@pytest.mark.skipif(not HAS_FF, reason="ffmpeg not installed")
def test_render_end_to_end_offline(tmp_path):
    def ff(*args):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)
    talk = tmp_path / "talk.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=6", "-f", "lavfi", "-i", "sine=f=220:d=6",
       "-shortest", "-pix_fmt", "yuv420p", str(talk))
    (tmp_path / "b").mkdir()
    ff("-f", "lavfi", "-i", "color=c=red:s=640x480:r=25:d=1", "-pix_fmt", "yuv420p", str(tmp_path / "b" / "red.mp4"))
    ff("-f", "lavfi", "-i", "color=c=blue:s=400x400", "-frames:v", "1", str(tmp_path / "b" / "blue.png"))
    lines = [{"i": 0, "start": 0.2, "end": 5.5, "text": "We go red then blue.",
              "words": [["We", 0.2], ["go", 0.6], ["red", 2.1], ["then", 3.0], ["blue.", 4.0]]}]
    d = {"source": "talk.mp4", "mode": "talking-head", "duration": 6.0, "size": [320, 180], "lines": lines,
         "rules": {"protect_start": 0}, "cutaways": [{"on": "red", "clip": "b/red.mp4", "dur": 1.5},
                                                    {"on": "blue", "clip": "b/blue.png", "dur": 1.5}]}
    plan_path = tmp_path / "talk.broll.json"
    plan_path.write_text(json.dumps(d))
    out = tmp_path / "out"
    assert broll.main(["render", str(talk), str(plan_path), "-o", str(out)]) == 0
    mp4 = out / "talk.broll.mp4"
    info = broll.probe(mp4)
    assert (info["width"], info["height"]) == (320, 180) and info["has_audio"]
    assert info["seconds"] == pytest.approx(6.0, abs=0.15)

    def rgb(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4), "-frames:v", "1",
                              "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        return tuple(raw[:3])
    r, g, b = rgb(1.0)
    assert abs(r - g) < 20  # speaker (gray) before the cut
    r, g, b = rgb(2.8)
    assert r > 150 and b < 100  # red B-roll on "red", held past the 1 s clip
    r, g, b = rgb(4.6)
    assert b > 150 and r < 100  # blue still on "blue"
    man = json.loads((out / "talk.broll.manifest.json").read_text())
    assert len(man["cutaways"]) == 2
    assert (out / "talk.broll.edl").read_text().count(" V     C ") == 2
