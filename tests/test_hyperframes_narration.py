"""Offline tests for hyperframes-narration (dry run needs only ffmpeg)."""
import importlib.util, json, re, shutil, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "hyperframes-narration" / "scripts" / "hf_narrate.py"


def load():
    sys.path.insert(0, str(P.parent))
    spec = importlib.util.spec_from_file_location("hf_narrate", P)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_parse_script_titles_and_ids():
    m = load()
    sc = m.parse_script((ROOT / "hyperframes-narration/examples/script.md").read_text())
    assert [s["id"] for s in sc] == ["scene-01", "scene-02", "scene-03"]
    assert sc[0]["title"] == "Write HTML" and sc[1]["text"].startswith("Miragea speaks")


def test_caption_lines_no_orphans():
    m = load()
    ws = [{"text": t, "start": i * .3, "end": i * .3 + .25} for i, t in enumerate("Your agent already knows how to write it.".split())]
    lines = m.caption_lines(ws)
    assert [x["text"] for ln in lines for x in ln] == [w["text"] for w in ws]
    assert all(len(" ".join(x["text"] for x in ln)) >= 14 for ln in lines)


def test_missing_voice_gives_clear_error(tmp_path, monkeypatch):
    m = load()
    monkeypatch.delenv("MIRAGEA_ACTOR_ID", raising=False)
    monkeypatch.setenv("MIRAGEA_API_KEY", "x")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    with pytest.raises(SystemExit) as e:
        m.main([str(ROOT / "hyperframes-narration/examples/script.md"), "--project", str(tmp_path)])
    assert "no voice" in str(e.value) and "miragea.ai" in str(e.value)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")
def test_dry_run_composition_is_timed_and_never_overwrites(tmp_path):
    m = load()
    s = str(ROOT / "hyperframes-narration/examples/script.md")
    assert m.main([s, "--project", str(tmp_path), "--dry-run"]) == 0
    man = json.loads((tmp_path / "narration.json").read_text())
    sc = man["scenes"]
    assert man["dryRun"] and len(sc) == 3
    for a, b in zip(sc, sc[1:]):  # scenes are back to back
        assert abs(a["start"] + a["span"] - b["start"]) < 1e-3
    page = (tmp_path / "index.html").read_text()
    assert 'data-composition-id="main"' in page and page.count("<audio") == 3
    assert f'data-duration="{man["totalSec"]}"' in page and 'window.__timelines["main"]' in page
    assert re.search(r'id="scene-01"[^>]*data-start="0(\.0)?"[^>]*data-track-index="1"', page)
    assert (tmp_path / "narration.srt").read_text().startswith("1\n")
    (tmp_path / "index.html").write_text("<html>my edits</html>")
    assert m.main([s, "--project", str(tmp_path), "--dry-run"]) == 0
    assert (tmp_path / "index.html").read_text() == "<html>my edits</html>"
    assert (tmp_path / "narration.snippet.html").exists()
