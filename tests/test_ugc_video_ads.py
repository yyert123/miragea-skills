import json
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "ugc-video-ads"
sys.path.insert(0, str(SKILL / "scripts"))
import ads  # noqa: E402

EXAMPLE = SKILL / "examples" / "brewly.ad.json"
RAW = json.loads(EXAMPLE.read_text())
HAS_FF = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def spec(**over):
    d = json.loads(json.dumps(RAW))
    d.update(over)
    return ads.load_spec(d)


def test_example_checks_clean():
    problems, advice = ads.check(spec(), EXAMPLE.parent)
    assert problems == [] and advice == []


def test_variant_matrix_is_hooks_times_bodies_with_cta_last():
    d = json.loads(json.dumps(RAW))
    d["bodies"].append({"id": "review", "lines": ["Honestly the smoothest cold brew I've had."]})
    s = ads.load_spec(d)
    vs = ads.variants(s)
    assert [v["id"] for v in vs] == ["price-demo", "price-review", "pov-demo", "pov-review", "stop-demo", "stop-review"]
    assert vs[0]["lines"][0]["role"] == "hook" and vs[0]["lines"][-1]["role"] == "cta"
    assert [v["id"] for v in ads.variants(s, only=["review"])] == ["price-review", "pov-review", "stop-review"]
    assert len(ads.variants(s, limit=2)) == 2


def test_single_body_shortcut_and_default_ids():
    s = ads.load_spec({"brand": "X", "hooks": ["One.", "Two."], "body": ["Line."]})
    assert [h["id"] for h in s["hooks"]] == ["a", "b"]
    assert ads.variants(s)[0]["id"] == "a-body"


@pytest.mark.parametrize("bad, msg", [
    ({"hooks": [], "body": ["x"]}, "hooks"),
    ({"hooks": ["x"]}, "body"),
    ({"hooks": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}], "body": ["x"]}, "duplicate"),
    ({"hooks": ["x"], "body": [""]}, "non-empty"),
    ({"hooks": ["x"], "body": ["y"], "platform": "myspace"}, "platform"),
])
def test_bad_specs_explain_the_fix(bad, msg):
    with pytest.raises(ValueError, match=msg):
        ads.load_spec(bad)


def test_estimates_count_numbers_and_symbols():
    assert ads.spoken_words("Only $29") == 4
    assert ads.spoken_words("Save 1999 today") == 5
    assert ads.est_seconds("one two three four five six seven eight nine ten") == pytest.approx(10 / ads.WPS + 0.15, abs=0.01)


def test_long_hook_and_long_ad_are_flagged():
    d = json.loads(json.dumps(RAW))
    d["hooks"][0]["text"] = "This is a very long opening line that nobody will ever hear because they already scrolled away"
    d["bodies"][0]["lines"] *= 12
    problems, advice = ads.check(ads.load_spec(d), EXAMPLE.parent)
    assert any("hook 'price'" in x for x in advice)
    assert any("over 60s" in p for p in problems)


@pytest.mark.parametrize("text, hit", [
    ("Guaranteed results in a week.", "guarantee"),
    ("It cures headaches.", "health"),
    ("I lost 20 pounds in a month.", "weight-loss"),
    ("I made $5,000 last month with this.", "income"),
    ("Are you overweight and tired?", "personal attribute"),
    ("Get a free sample.", "free"),
    ("100% natural.", "absolute"),
])
def test_claim_lint(text, hit):
    assert any(hit in why for why in ads.lint_claims(text))


def test_clean_copy_has_no_claim_flags():
    assert ads.lint_claims("Coffee in, water in, fridge overnight. That's it.") == []


def test_first_person_without_label_gets_disclosure_note():
    _, advice = ads.check(spec(label=None), EXAMPLE.parent)
    assert any("FTC" in x for x in advice)


def test_missing_media_is_a_problem():
    d = json.loads(json.dumps(RAW))
    d["hooks"][0]["media"] = "media/nope.jpg"
    problems, _ = ads.check(ads.load_spec(d), EXAMPLE.parent)
    assert problems == ["media not found: media/nope.jpg"]


def test_timed_words_keep_script_spelling_on_asr_timing():
    tr = {"segments": [{"start": 0.0, "end": 0.8, "text": "this is the bru"}, {"start": 0.8, "end": 1.6, "text": "lee cold brew kit"}]}
    ws = ads.timed_words("This is the Brewly cold brew kit.", tr, 1.6)
    assert [w["text"] for w in ws] == "This is the Brewly cold brew kit.".split()
    assert ws[0]["start"] == 0.0 and ws[-1]["end"] <= 1.6 + 1e-6
    assert [w["start"] for w in ws] == sorted(w["start"] for w in ws)


def test_timed_words_fallback_spreads_evenly():
    ws = ads.timed_words("aa bb cc dd", None, 2.0)
    assert len(ws) == 4 and ws[0]["start"] == 0 and ws[-1]["end"] == pytest.approx(2.0)


def test_pop_captions_break_on_commas_and_stay_short():
    ws = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, t in
          enumerate("Coffee in, water in, fridge overnight. That's it.".split())]
    cues = ads.ad_cues(ws)
    assert [c["text"] for c in cues] == ["COFFEE IN", "WATER IN", "FRIDGE OVERNIGHT.", "THAT'S IT."]
    for a, b in zip(cues, cues[1:]):
        assert a["end"] <= b["start"]


def test_frame_splits_do_not_drift():
    starts = [0, 1.013, 2.517, 4.0333]
    fr = ads.frame_splits(starts, 7.25)
    assert sum(fr) == round(7.25 * ads.FPS)


def test_ass_keeps_text_in_safe_zone():
    caps = [{"start": 0, "end": 1, "text": "HELLO"}]
    doc = ads.ass_doc("9:16", caps, [{"start": 0, "end": 1, "text": "$29"}],
                      {"title": "Brewly", "lines": ["20% off"], "button": "Shop Now"}, 5.0, 7.0, "AI voice")
    assert "PlayResX: 1080" in doc and "PlayResY: 1920" in doc
    ys = [int(y) for y in __import__("re").findall(r"\\pos\(\d+,(\d+)\)", doc)]
    assert all(0.10 * 1920 <= y <= 0.70 * 1920 for y in ys)  # clear of top bar and bottom caption/CTA UI
    xs = [int(x) for x in __import__("re").findall(r"\\pos\((\d+),", doc)]
    assert max(xs) < 1080 * 0.86  # clear of the right-hand action rail
    assert "Shop Now" in doc and "AI voice" in doc


def test_voice_track_starts_and_gaps(tmp_path):
    clips = []
    for i, secs in enumerate([0.5, 1.0]):
        p = tmp_path / f"c{i}.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(ads.SR)
            w.writeframes(b"\x01\x00" * int(secs * ads.SR))
        clips.append(p)
    out = tmp_path / "vo.wav"
    starts = ads.build_voice_track(clips, 0.1, 0.3, out)
    assert starts == pytest.approx([0.0, 0.6])
    assert ads.wav_seconds(out) == pytest.approx(1.9, abs=1e-3)


def test_dry_run_needs_no_key(monkeypatch, capsys):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    assert ads.main(["render", str(EXAMPLE), "--dry-run", "--ratios", "9:16,1:1"]) == 0
    out = capsys.readouterr().out
    assert "6 video(s)" in out and "7 unique lines" in out


@pytest.mark.skipif(not HAS_FF, reason="ffmpeg not installed")
def test_end_to_end_render_with_fake_voice(tmp_path, monkeypatch):
    class Fake:
        calls = 0

        def speak(self, text, out, **kw):
            Fake.calls += 1
            n = int(ads.SR * (0.3 + 0.05 * len(text.split())))
            with wave.open(str(out), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(ads.SR)
                w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n)))

        def transcribe(self, path):
            d = ads.wav_seconds(Path(path))
            return {"text": "x", "segments": [{"start": 0, "end": d, "text": "x"}]}

    monkeypatch.setattr(ads, "Client", Fake)
    ad = tmp_path / "ad.json"
    d = json.loads(json.dumps(RAW))
    for ln in d["hooks"] + d["bodies"][0]["lines"] + [d["cta"], d["end_card"]]:
        ln["media"] = str(SKILL / "examples" / ln["media"])
    d["hooks"] = d["hooks"][:2]
    ad.write_text(json.dumps(d))
    out = tmp_path / "out"
    assert ads.main(["render", str(ad), "-o", str(out), "--ref-url", "https://x/r.wav", "--ratios", "1:1"]) == 0
    rows = json.loads((out / "manifest.json").read_text())["videos"]
    assert [r["file"] for r in rows] == ["brewly_price-demo_1x1.mp4", "brewly_pov-demo_1x1.mp4"]
    assert Fake.calls == 6  # body + CTA lines voiced once, shared by both hooks
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(out / rows[0]["file"])], capture_output=True, text=True).stdout
    assert "1080,1080" in probe
    assert abs(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(out / rows[0]["file"])], capture_output=True, text=True).stdout)
               - rows[0]["seconds"]) < 0.15
