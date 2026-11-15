import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audiogram-clips" / "scripts"))
import audiogram  # noqa: E402


def test_layout_and_graph():
    for f, (w, h) in audiogram.SIZES.items():
        g = audiogram.filter_graph(f, "dark", "Hi: there, you", "clip.srt", True)
        assert f"{w}x{h}" in g and "subtitles=clip.srt" in g and "overlay" in g
    assert "subtitles" not in audiogram.filter_graph("1:1", "light", None, None, False)


def test_esc():
    assert audiogram.esc("a:b,c'd") == "a\\:b\\,c\u2019d"


def test_dry_run(tmp_path, capsys):
    a = tmp_path / "a.wav"; a.write_bytes(b"x")
    assert audiogram.main([str(a), "--dry-run", "--duration", "30"]) == 0
    assert json.loads(capsys.readouterr().out)["format"] == "9:16"


def test_duration_cap(tmp_path):
    a = tmp_path / "a.wav"; a.write_bytes(b"x")
    try:
        audiogram.main([str(a), "--duration", "999", "--dry-run"])
    except SystemExit as e:
        assert "180" in str(e)
    else:
        raise AssertionError
