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
