"""Offline tests for the skills' pure-Python parts (no API key needed)."""
import importlib.util
import json
import sys
import pytest
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


def test_article_to_video_parse_and_srt():
    m = load("article-to-video", "article2video")
    sc = m.parse((ROOT / "article-to-video" / "examples" / "post.md").read_text())
    assert [s["title"] for s in sc] == ["Why short videos win", "Cut the dead air", "Say it once"]
    assert all(len(l) <= 170 for s in sc for l in s["lines"])
    cues = m.caption_cues(["one two three four five six seven eight nine"], [4.0])
    assert len(cues) == 2 and abs(cues[-1][1] - 4.0) < 1e-6
    assert "00:00:00,000 -->" in m.to_srt(cues)


def test_article_to_video_renders_with_stub_voice(tmp_path, monkeypatch):
    import shutil, subprocess
    if not shutil.which("ffmpeg"):
        return
    m = load("article-to-video", "article2video")
    import miragea_client
    monkeypatch.setenv("MIRAGEA_API_KEY", "x")
    def fake(self, text, out, **kw):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=0.6", str(out)], check=True)
        return out
    monkeypatch.setattr(miragea_client.Client, "speak", fake)
    out = tmp_path / "a.mp4"
    assert m.main([str(ROOT / "article-to-video/examples/post.md"), "-o", str(out), "--voice", "A1"]) == 0
    assert out.stat().st_size > 1000 and out.with_suffix(".srt").exists()


def test_voice_patch_plan_and_cmd():
    m = load("voice-patch", "voicepatch")
    ws = [{"text": "Our", "start": 0.0, "end": 0.3}, {"text": "price", "start": 0.35, "end": 0.7},
          {"text": "ten", "start": 0.8, "end": 1.0}, {"text": "dollars.", "start": 1.05, "end": 1.5},
          {"text": "Thanks", "start": 1.52, "end": 2.0}]
    p = m.plan(ws, "Ten dollars", total=2.0)
    assert 0.7 <= p["start"] <= 0.8 and 1.5 <= p["end"] <= 1.52
    import pytest
    with pytest.raises(ValueError):
        m.plan(ws, "twenty")
    assert "concat=n=3" in " ".join(m.splice_cmd("a.mp4", "p.wav", 0.8, 1.5, "o.mp4", True))


def test_client_rejects_ref_url_with_clear_hint(tmp_path, monkeypatch):
    import importlib.util, pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "voice-patch/scripts/miragea_client.py"
    spec = importlib.util.spec_from_file_location("mc", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.delenv("MIRAGEA_ACTOR_ID", raising=False)
    c = m.Client(api_key="x")
    import pytest
    with pytest.raises(m.MirageaError) as e:
        c.speak("hi", tmp_path / "a.wav", reference_audio_url="https://x/y.wav")
    assert "actor_id" in str(e.value) and "/v1/actors" in str(e.value)


def test_slides_to_video_notes_and_order(tmp_path):
    m = load("slides-to-video", "slides2video")
    notes = m.parse_notes((ROOT / "slides-to-video/examples/notes.md").read_text())
    assert len(notes) == 3 and notes[2].startswith("Thanks")
    for n in ("slide-10.png", "slide-2.png", "slide-1.jpg"):
        (tmp_path / n).write_bytes(b"x")
    assert [p.name for p in m.find_slides(tmp_path)] == ["slide-1.jpg", "slide-2.png", "slide-10.png"]
    assert m.main([str(tmp_path), "--notes", str(ROOT / "slides-to-video/examples/notes.md"), "--dry-run"]) == 0


def test_dub_batch_langs_and_status(tmp_path):
    m = load("dub-batch", "dub_batch")
    assert m.parse_langs("es, pt,es") == ["es", "pt"]
    with pytest.raises(SystemExit):
        m.parse_langs("xx")
    v = tmp_path / "a.mp4"
    (tmp_path / "a.es.dub.json").write_text('{"lines":[{"text":"hola"},{"text":""}]}')
    assert m.status(v, ["es", "pt"]) == [("es", "needs translation", 1, 2), ("pt", "missing", 0, 0)]


def test_animated_captions_ass_events_and_colours(tmp_path):
    m = load("animated-captions", "animated_captions")
    assert m.ass_colour("FFE000") == "&H0000E0FF&"
    with pytest.raises(ValueError):
        m.ass_colour("yellow")
    cues = load("video-captions", "cues")
    ws = cues.words(SAMPLE)
    ass = m.build_ass(ws, "hormozi", 1080, 1920)
    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == len(ws) and "PlayResX: 1080" in ass
    spans = []
    for l in events:
        f = l.split(",", 9)
        spans.append((f[1], f[2]))
    assert all(a <= b for a, b in spans)
    # every chunk fits the width budget (max_chars) and breaks after sentence ends
    for ch in m.chunk(ws, 3, 14):
        assert 1 <= len(ch) <= 3
        assert sum(len(w["text"]) for w in ch) + len(ch) - 1 <= 14 or len(ch) == 1
    for name in ("karaoke", "highlighter", "minimal"):
        assert "Dialogue:" in m.build_ass(ws, name, 1920, 1080)


def test_animated_captions_cli_offline(tmp_path):
    m = load("animated-captions", "animated_captions")
    src = tmp_path / "a.wav"
    src.write_bytes(b"x")
    tr = ROOT / "video-captions" / "examples" / "transcript.json"
    assert m.main([str(src), "--transcript", str(tr), "--preset", "karaoke", "--size", "1080x1920"]) == 0
    assert (tmp_path / "a.ass").exists() and (tmp_path / "a.words.json").exists()
    with pytest.raises(SystemExit):
        m.main([str(src), "--transcript", str(tr), "--active", "nope", "--size", "1080x1920"])


def test_manim_narration_spoken_math_and_parse():
    m = load("manim-narration", "manim_narrate")
    assert m.spoken("The derivative of x^2 is 2x.") == "The derivative of x squared is 2x."
    assert m.spoken("f(x) = x^2 + 3/4") == "f(x) equals x squared plus 3 over 4"
    assert "square root of 2 times pi" in m.spoken("√2 · π")
    sc = m.parse_script("## Intro Part\nHello x^2.\n\n## Intro Part\nAgain.\n")
    assert [s["key"] for s in sc] == ["intro-part", "intro-part-2"] and sc[0]["say"] == "Hello x squared."


def test_manim_narration_word_time_and_beat(tmp_path):
    h = load("manim-narration", "narration_manim")
    ws = [{"text": "The", "start": 0.0, "end": 0.2}, {"text": "derivative,", "start": 0.3, "end": 1.0},
          {"text": "the", "start": 1.2, "end": 1.3}]
    assert h.word_time(ws, "Derivative") == 0.3 and h.word_time(ws, "the", 2) == 1.2
    with pytest.raises(KeyError):
        h.word_time(ws, "nope")

    class Fake:
        narration_dir = str(tmp_path)
        narration_gap = 0.0
        time = 0.0
        sounds, waits = [], []

        def add_sound(self, p):
            self.sounds.append(p)

        def play(self, rt):
            self.time += rt

        def wait(self, t):
            self.waits.append(t)
            self.time += t

    class S(h.Narrated, Fake):
        narration_dir = str(tmp_path)

    (tmp_path / "narration.json").write_text(json.dumps({"scenes": [{"key": "a", "file": "a.mp3", "durationSec": 2.0, "words": ws}]}))
    s = S()
    with s.narrate("a") as n:
        rt = n.until("derivative")
        s.play(rt)
        assert abs(rt - 0.3) < 1e-9
    assert abs(s.time - 2.0) < 1e-6 and s.sounds and (tmp_path / "narration.timeline.json").exists()


def test_manim_narration_plan_dry_run_and_mux_cmd(tmp_path):
    m = load("manim-narration", "manim_narrate")
    out = tmp_path / "n"
    assert m.main(["plan", str(ROOT / "manim-narration" / "examples" / "script.md"), "--out", str(out), "--dry-run"]) == 0
    man = json.loads((out / "narration.json").read_text())
    assert [s["key"] for s in man["scenes"]] == ["intro", "secant", "result"]
    assert man["scenes"][1]["start"] > man["scenes"][0]["start"] and (out / "narration.srt").exists()
    cmd = m.mux_cmd(tmp_path / "v.mp4", [(out / "intro.mp3", 0.0), (out / "secant.mp3", 3.5)], tmp_path / "o.mp4")
    assert "adelay=3500:all=1" in " ".join(cmd) and "copy" in cmd


def test_subtitle_translator_build_and_lint(tmp_path):
    m = load("subtitle-translator", "subtitle_translate")
    src = ROOT / "subtitle-translator" / "examples" / "talk.translate.json"
    job = tmp_path / "talk.translate.json"
    data = json.loads(src.read_text())
    data["translations"]["ja"] = {"1": "印刷とは、可動活字で本を作る技術と考えられます。" * 2}
    job.write_text(json.dumps(data, ensure_ascii=False))
    assert m.main(["build", str(job)]) == 0
    assert (tmp_path / "talk.es.srt").read_text().startswith("1\n00:00:00,320")
    assert (tmp_path / "talk.ja.vtt").exists()
    assert m.wrap("a" * 40 + " " + "b" * 40, 42) == "a" * 40 + "\n" + "b" * 40
    assert any("missing" in w or "too" in w or "cps" in w for w in m.lint([{"id": 1, "start": 0, "end": 1, "text": "x" * 60}], "es"))


def test_thumbnail_title_ab_lint_and_cmd():
    m = load("thumbnail-title-ab", "thumb_ab")
    assert m.lint({"title": "x" * 61, "thumb_text": "a b c d e"}) and not m.lint({"title": "Short", "thumb_text": "Go now"})
    assert m.frame_times(100, 4) == [20.0, 40.0, 60.0, 80.0]
    cmd = m.render_cmd("f.jpg", "it's 50%", "o.jpg")
    assert "1280:720" in cmd[cmd.index("-vf") + 1] and "IT\u2019S 50\\%" in cmd[cmd.index("-vf") + 1]
