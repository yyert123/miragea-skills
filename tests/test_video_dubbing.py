import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "video-dubbing"
sys.path.insert(0, str(SKILL / "scripts"))
import dub  # noqa: E402

TRANSCRIPT = json.loads((SKILL / "examples" / "tips.transcript.json").read_text())
DUB = SKILL / "examples" / "tips.es.dub.json"
HAS_FF = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def test_lang_code_normalises_names_and_regions():
    assert dub.lang_code("Spanish") == "es"
    assert dub.lang_code("pt-BR") == "pt"
    assert dub.lang_code("zh_CN") == "zh"
    assert dub.lang_code(None) == ""


def test_lines_follow_punctuation_not_audio_segments():
    # Miragea segments split mid-word ("ano" | "ther") and carry no punctuation.
    lines = dub.group_lines(TRANSCRIPT)
    assert [ln["source"] for ln in lines] == [
        "Want to grow your channel in another language?",
        "Here is the one rule I learned after posting a hundred videos: say the payoff in the first three "
        "seconds, then explain how you got there.",
        "Try it on your next upload and watch your retention climb."]
    assert lines[0]["start"] == pytest.approx(0.96, abs=0.01)
    assert all(a["end"] <= b["start"] + 0.01 for a, b in zip(lines, lines[1:]))


def test_long_sentence_splits_on_clauses():
    lines = dub.group_lines(TRANSCRIPT, max_dur=6.0)
    assert len(lines) == 4
    assert lines[1]["source"].endswith("videos:")
    assert lines[2]["source"].startswith("say the payoff")


def test_cjk_transcript_groups_by_sentence_marks():
    t = {"text": "大家好。今天教你剪辑视频，五分钟就够了。",
         "segments": [{"start": 0.0, "end": 1.0, "text": "大家好"}, {"start": 1.2, "end": 4.0, "text": "今天教你剪辑视频五分钟就够了"}]}
    lines = dub.group_lines(t)
    assert [ln["source"] for ln in lines] == ["大家好。", "今天教你剪辑视频，五分钟就够了。"]
    assert lines[0]["end"] == pytest.approx(1.0, abs=0.07) and lines[1]["start"] == pytest.approx(1.2)
    t2 = dict(t, segments=[{"start": 0.0, "end": 0.5, "text": "大家好"}, {"start": 0.6, "end": 4.0, "text": "今天教你剪辑视频五分钟就够了"}])
    assert [ln["source"] for ln in dub.group_lines(t2)] == ["大家好。今天教你剪辑视频，五分钟就够了。"]  # tiny line folded


def test_budgets_give_each_line_the_time_until_the_next():
    lines = dub.add_budgets(dub.group_lines(TRANSCRIPT), 18.9, "es")
    assert lines[0]["room"] == pytest.approx(lines[1]["start"] - lines[0]["start"], abs=0.01)
    assert lines[-1]["room"] == pytest.approx(18.9 - lines[-1]["start"], abs=0.01)
    assert lines[0]["max_chars"] == int(lines[0]["room"] * dub.RATES["es"])


def test_cjk_counts_characters_without_spaces():
    assert dub.spoken_len("你好 世界", "zh") == 4
    assert dub.spoken_len("hola   mundo", "es") == 10
    assert dub.estimate_seconds("你" * 48, "zh") == pytest.approx(10.0)


def test_assess_flags_ok_tight_long_missing():
    lines = [{"id": 1, "room": 2.0, "text": "a" * 20}, {"id": 2, "room": 2.0, "text": "a" * 32},
             {"id": 3, "room": 2.0, "text": "a" * 60}, {"id": 4, "room": 2.0, "text": " "}]
    st = [r["status"] for r in dub.assess(lines, "es", 1.2)]
    assert st == ["ok", "tight", "long", "missing"]


def test_example_dub_file_passes_check(capsys):
    assert dub.main(["check", str(DUB)]) == 0
    assert "0 too long" in capsys.readouterr().out


def test_check_exits_nonzero_on_untranslated(tmp_path):
    d = json.loads(DUB.read_text())
    d["lines"][1]["text"] = ""
    p = tmp_path / "x.dub.json"
    p.write_text(json.dumps(d))
    assert dub.main(["check", str(p)]) == 1


def test_place_starts_on_original_speeds_up_then_drifts():
    lines = [{"id": 1, "start": 0.0}, {"id": 2, "start": 2.0}, {"id": 3, "start": 6.0}]
    out = dub.place(lines, {1: 1.5, 2: 4.2, 3: 1.0}, 10.0, max_speed=1.2)
    assert out[0]["speed"] == 1.0 and out[0]["start"] == 0.0
    assert 1.0 < out[1]["speed"] <= 1.2           # 4.2 s into ~3.95 s: gentle speed-up
    assert out[1]["overflow"] == 0
    lines[2]["start"] = 4.5                        # now even 1.2x cannot fit
    out = dub.place(lines, {1: 1.5, 2: 4.2, 3: 1.0}, 10.0, max_speed=1.2)
    assert out[1]["speed"] == pytest.approx(1.2) and out[1]["overflow"] > 0
    assert out[2]["drift"] > 0 and out[2]["start"] >= out[1]["end"]


def test_duck_expression_is_escaped_for_ffmpeg():
    e = dub.duck_expr([(1.0, 2.0), (3.0, 4.0)], 0.08)
    assert e.startswith("if(gt(between(t\\,0.92\\,2.15)+between(t\\,2.92\\,4.15)")
    assert dub.duck_expr([], 0.1) == "1"


def test_captions_follow_placed_timing_and_wrap():
    lines = json.loads(DUB.read_text())["lines"]
    placed = [{"id": ln["id"], "start": ln["start"], "end": ln["start"] + ln["room"] - 0.1} for ln in lines]
    cues = dub.caption_cues(lines, placed, "es")
    assert cues[0]["start"] == lines[0]["start"]
    assert all(len(row) <= 42 for c in cues for row in c["text"].split("\n"))
    assert all(len(c["text"].split("\n")) <= 2 for c in cues)
    srt = dub.to_srt(cues)
    assert srt.startswith("1\n00:00:00,960 --> ")


def test_cjk_captions_wrap_by_characters():
    lines = [{"id": 1, "start": 0.0, "text": "这是一个很长的句子，用来测试中文字幕是否会按照字符数正确换行。"}]
    cues = dub.caption_cues(lines, [{"id": 1, "start": 0.0, "end": 5.0}], "zh")
    assert all(len(row) <= 16 for c in cues for row in c["text"].split("\n"))


def test_render_dry_run_makes_no_api_calls(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    video = tmp_path / "tips.mp4"
    video.write_bytes(b"x")
    assert dub.main(["render", str(video), str(DUB), "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out


def test_render_without_voice_explains_fix(monkeypatch, tmp_path):
    for k in ("MIRAGEA_VOICE_ID", "MIRAGEA_REF_URL"):
        monkeypatch.delenv(k, raising=False)
    video = tmp_path / "tips.mp4"
    video.write_bytes(b"x")
    with pytest.raises(SystemExit):
        dub.main(["render", str(video), str(DUB), "--voice", "", "--ref-url", ""])


@pytest.mark.skipif(not HAS_FF, reason="needs ffmpeg")
def test_full_render_with_fake_voice(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def speak(self, text, out, **kw):
            calls.append(text)
            secs = max(0.5, len(text) / 15)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            f"sine=f=330:sample_rate=24000:d={secs:.2f}", str(out)], check=True)
            return Path(out)

    monkeypatch.setattr(dub, "Client", FakeClient)
    video = tmp_path / "tips.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=19",
                    "-f", "lavfi", "-i", "sine=f=220:sample_rate=48000:d=19", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-c:a", "aac", "-shortest", str(video)], check=True)
    out = tmp_path / "out"
    dubfile = tmp_path / DUB.name
    shutil.copy(DUB, dubfile)
    args = ["render", str(video), str(dubfile), "-o", str(out), "--voice", "v1", "--keep-original"]
    assert dub.main(args) == 0
    assert len(calls) == 3
    for f in ("tips.es.mp4", "tips.es.dub.wav", "tips.es.voice.wav", "tips.es.srt", "tips.es.manifest.json"):
        assert (out / f).exists(), f
    with wave.open(str(out / "tips.es.voice.wav")) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(19.5, abs=0.6)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:stream_tags=language",
                            "-of", "csv=p=0", str(out / "tips.es.mp4")], capture_output=True, text=True).stdout
    assert "audio,spa" in probe and "audio,eng" in probe
    man = json.loads((out / "tips.es.manifest.json").read_text())
    assert man["lines_billed_this_run"] == 3
    assert dub.main(args) == 0 and len(calls) == 3       # second run: everything from cache, nothing billed
