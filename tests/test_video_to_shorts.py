import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "video-to-shorts"
sys.path.insert(0, str(SKILL / "scripts"))
import clips  # noqa: E402
from cues import words  # noqa: E402

TRANSCRIPT = SKILL / "examples" / "podcast.transcript.json"
CLIPS = SKILL / "examples" / "podcast.clips.json"


def _sents():
    return clips.sentences(words(json.loads(TRANSCRIPT.read_text())))


def test_sentences_split_on_punctuation():
    s = _sents()
    assert len(s) == 10
    assert s[1]["text"].startswith("Why do most") and s[1]["text"].endswith("?")
    assert all(a["end"] <= b["start"] + 0.01 for a, b in zip(s, s[1:]))


def test_snap_never_cuts_mid_sentence():
    s = _sents()
    a, b = clips.snap(6.0, 12.0, s)  # starts and ends mid-sentence
    assert a == pytest.approx(4.45) and b == pytest.approx(16.85)


def test_suggest_skips_weak_openers_and_respects_bounds():
    picks = clips.suggest(_sents(), n=3, min_s=20, max_s=60)
    assert picks and picks[0]["title"].startswith("Why do most")
    for p in picks:
        assert 20 <= p["end"] - p["start"] <= 60
    for x, y in zip(picks, picks[1:]):
        assert x["end"] <= y["start"]


def test_clip_cues_are_shifted_and_hook_first():
    ws = words(json.loads(TRANSCRIPT.read_text()))
    cues = clips.clip_cues(ws, 4.45, 16.85, offset=2.0, hook="Stop scrolling.", hook_s=2.0)
    assert cues[0]["text"] == "STOP SCROLLING." and cues[0]["end"] == 2.0
    assert cues[1]["start"] >= 2.0 and cues[1]["text"].startswith("WHY")
    assert all(len(c["text"].split()) <= 3 for c in cues[1:])


def test_frame_modes():
    assert "crop=1080:1920" in clips.frame_filter("crop")
    assert "boxblur" in clips.frame_filter("fit")
    with pytest.raises(ValueError):
        clips.frame_filter("stretch")


def test_bad_clips_file(tmp_path):
    bad = tmp_path / "c.json"
    bad.write_text('[{"start": 5, "end": 2}]')
    with pytest.raises(SystemExit):
        clips.read_clips(bad)


def test_dry_run_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"not decoded in dry run")
    rc = clips.main(["render", str(video), str(CLIPS), "--transcript", str(TRANSCRIPT), "--dry-run"])
    assert rc == 0 and "clip_02" in capsys.readouterr().out


def test_moments_writes_markdown_and_draft(tmp_path):
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"x")
    clips.main(["moments", str(video), "--transcript", str(TRANSCRIPT), "--suggest", "2", "--out-dir", str(tmp_path)])
    assert "[4.6-9.8]" in (tmp_path / "talk.moments.md").read_text()
    assert json.loads((tmp_path / "talk.clips.json").read_text())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_render_offline_with_fake_voice(tmp_path, monkeypatch):
    video = tmp_path / "talk.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=20",
                    "-f", "lavfi", "-i", "sine=f=220:d=20", "-shortest", "-c:v", "libx264", "-preset",
                    "ultrafast", "-c:a", "aac", str(video)], check=True)
    plan = tmp_path / "c.json"
    plan.write_text(json.dumps([{"start": 4.6, "end": 16.5, "title": "t", "hook": "Watch this."}]))

    def fake_speak(self, text, out_path, **kw):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=1.2", str(out_path)],
                       check=True)
        return Path(out_path)

    monkeypatch.setenv("MIRAGEA_API_KEY", "test")
    monkeypatch.setattr(clips.Client, "speak", fake_speak)
    out = tmp_path / "out"
    rc = clips.main(["render", str(video), str(plan), "--transcript", str(TRANSCRIPT), "-o", str(out),
                     "--voice", "v1", "--frame", "fit"])
    assert rc == 0
    m = json.loads((out / "manifest.json").read_text())["clips"][0]
    assert m["hook_seconds"] and m["seconds"] == pytest.approx(16.85 - 4.45 + m["hook_seconds"], abs=0.4)
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(out / "clip_01.mp4")], capture_output=True, text=True).stdout
    assert dims.strip() == "1080,1920"
