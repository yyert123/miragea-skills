"""Offline tests for the skills' pure-Python parts (no API key needed)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(skill, mod):
    path = ROOT / skill / "scripts" / f"{mod}.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"{skill}_{mod}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SAMPLE = json.loads((ROOT / "video-captions" / "examples" / "transcript.json").read_text())


def test_words_are_whole_even_when_segments_split_mid_word():
    cues = load("video-captions", "cues")
    ws = cues.words(SAMPLE)
    assert all(" " not in w["text"] for w in ws)
    assert [w["text"] for w in ws][:3] == SAMPLE["text"].split()[:3]
    assert all(b["start"] >= a["start"] for a, b in zip(ws, ws[1:]))


def test_standard_cues_respect_line_limits():
    cues = load("video-captions", "cues")
    out = cues.build_cues(cues.words(SAMPLE), "standard")
    for c in out:
        lines = c["text"].split("\n")
        assert len(lines) <= 2 and all(len(l) <= 42 for l in lines)
        assert c["end"] > c["start"]
    assert all(b["start"] >= a["end"] - 1e-6 for a, b in zip(out, out[1:]))


def test_shorts_cues_are_short_and_upper():
    cues = load("video-captions", "cues")
    out = cues.build_cues(cues.words(SAMPLE), "shorts", upper=True)
    assert all(len(c["text"].split()) <= 3 and c["text"] == c["text"].upper() for c in out)


def test_srt_and_vtt_format():
    cues = load("video-captions", "cues")
    c = [{"start": 1.5, "end": 3.25, "text": "Hello"}]
    assert "00:00:01,500 --> 00:00:03,250" in cues.to_srt(c)
    assert cues.to_vtt(c).startswith("WEBVTT") and "00:00:01.500" in cues.to_vtt(c)


def test_script_parsing_markdown_and_json(tmp_path):
    nar = load("remotion-narration", "narrate")
    md = tmp_path / "s.md"
    md.write_text("## Intro\nHello **world**.\nSecond line.\n\n## Intro\nAgain.\n")
    sc = nar.parse_script(md)
    assert [s["id"] for s in sc] == ["intro", "intro-2"]
    assert sc[0]["text"] == "Hello world. Second line."
    js = tmp_path / "s.json"
    js.write_text(json.dumps({"scenes": [{"id": "a", "text": "One."}, {"text": "Two."}]}))
    assert [s["id"] for s in nar.parse_script(js)] == ["a", "scene-02"]


def test_long_scene_is_chunked_under_api_limit():
    nar = load("remotion-narration", "narrate")
    text = " ".join(["This is a fairly ordinary sentence for testing."] * 120)
    parts = nar.chunks(text)
    assert len(parts) > 1 and all(len(p) <= 1900 for p in parts)
    assert " ".join(parts) == text


# --- screen-recording-voiceover -------------------------------------------------------------

def test_voiceover_script_parsing_and_errors():
    vo = load("screen-recording-voiceover", "voiceover")
    lines = vo.parse_script("# c\n[00:00] Hello there.\n00:04.5 - Click Save.\n[1:02:03] Late.\n[00:09] # step 3: 5s, ~11 words\n".replace("[00:09]", "[1:02:09]"))
    assert [l["t"] for l in lines] == [0.0, 4.5, 3723.0]
    assert lines[1]["text"] == "Click Save."
    import pytest
    with pytest.raises(vo.ScriptError, match="line 2"):
        vo.parse_script("[00:05] A.\n[00:03] B.\n")
    with pytest.raises(vo.ScriptError, match="no timestamp"):
        vo.parse_script("Hello without time\n")


def test_voiceover_plan_speeds_up_then_freezes_and_shifts_later_lines():
    vo = load("screen-recording-voiceover", "voiceover")
    lines = [{"t": 0.0, "text": "a"}, {"t": 4.0, "text": "b"}, {"t": 9.0, "text": "c"}]
    p = vo.plan(lines, 14.0, [3.0, 4.5, 2.0], max_speed=1.15)
    assert p[0]["speed"] == 1.0 and p[0]["freeze"] == 0
    assert p[1]["speed"] == 1.0 and p[1]["freeze"] == 0          # 4.5 fits in 5.0 - 0.25
    p = vo.plan(lines, 14.0, [5.5, 2.0, 2.0], max_speed=1.15)
    assert p[0]["speed"] == 1.15 and p[0]["freeze"] > 0
    assert abs(p[1]["start"] - (4.0 + p[0]["freeze"])) < 1e-3     # later lines shift, never overlap
    assert p[0]["start"] + p[0]["duration"] <= p[1]["start"] - 0.2


def test_voiceover_caption_words_cover_spoken_time():
    vo = load("screen-recording-voiceover", "voiceover")
    ws = vo.caption_words([{"text": "Click the big button", "start": 2.0, "duration": 2.0}])
    assert ws[0]["start"] == 2.0 and abs(ws[-1]["end"] - 4.0) < 1e-6
    assert all(b["start"] >= a["start"] for a, b in zip(ws, ws[1:]))


def test_scene_merge_starts_at_zero_and_respects_gap_and_cap():
    sc = load("screen-recording-voiceover", "scenes")
    assert sc.merge([0.5, 1.0, 5.0, 6.0, 12.0, 29.5], 30.0, 3.0, 40) == [0.0, 5.0, 12.0]
    many = sc.merge([float(i) for i in range(3, 300, 3)], 300.0, 3.0, 10)
    assert len(many) == 10 and many[0] == 0.0


# --- shorts-voiceover -----------------------------------------------------------------------

def test_shorts_script_parsing_with_media_and_comments():
    sh = load("shorts-voiceover", "short")
    sc = sh.parse_script("Hook line.\n\n@broll/a.mp4\nFirst tip,\nwrapped.\n\n# note only\n\nLast.")
    assert sc == [{"text": "Hook line.", "media": None}, {"text": "First tip, wrapped.", "media": "broll/a.mp4"},
                  {"text": "Last.", "media": None}]
    import pytest
    with pytest.raises(ValueError):
        sh.parse_script("   \n\n ")


def test_shorts_media_assignment_skips_named_files(tmp_path):
    sh = load("shorts-voiceover", "short")
    d = tmp_path / "m"
    d.mkdir()
    for n in ("01.png", "02.jpg", "03.mp4", "notes.txt"):
        (d / n).write_bytes(b"x")
    scenes = [{"text": "a", "media": None}, {"text": "b", "media": "02.jpg"}, {"text": "c", "media": None},
              {"text": "d", "media": None}]
    got = [p.name for p in sh.assign_media(scenes, tmp_path, d)]
    assert got == ["01.png", "02.jpg", "03.mp4", "01.png"]
    assert sh.assign_media([{"text": "a", "media": None}], tmp_path, None) == [None]
