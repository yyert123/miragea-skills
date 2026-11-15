import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jump-cut-editor" / "scripts"))
import jumpcut  # noqa: E402

W = lambda t, s, e: {"text": t, "start": s, "end": e}
WS = [W("So", 0.2, 0.4), W("um", 0.5, 0.8), W("the", 1.0, 1.2), W("the", 1.3, 1.5), W("plan.", 1.6, 2.0), W("Next", 4.0, 4.3)]


def test_cuts():
    c = jumpcut.find_cuts(WS, total=5.5)
    r = [x[2] for x in c]
    assert "filler" in r or "mixed" in r
    assert any(s < 1.3 < e for s, e, _ in c)  # repeated "the"
    assert any(2.0 < s and e < 4.0 for s, e, _ in c)  # long pause


def test_keep_flags():
    assert not jumpcut.find_cuts([W("um", 0, .2)], fillers=False)


def test_keeps_cover_rest():
    c = jumpcut.find_cuts(WS, total=5.5)
    k = jumpcut.keeps(c, 5.5)
    assert abs(sum(e - s for s, e in k) - (5.5 - sum(e - s for s, e, _ in c))) < 0.01


def test_plan_and_graph():
    c = jumpcut.find_cuts(WS, total=5.5)
    assert jumpcut.plan(c, 5.5)["saved_s"] > 1
    g = jumpcut.filter_graph(jumpcut.keeps(c, 5.5), True)
    assert "concat=n=" in g and "afade" in g


def test_dry_run(tmp_path, capsys):
    m = tmp_path / "a.wav"; m.write_bytes(b"x")
    t = tmp_path / "t.json"
    t.write_text(json.dumps({"text": "So um the the plan. Next", "segments": [{"text": "So um the the plan. Next", "start": 0.2, "end": 4.3}]}))
    assert jumpcut.main([str(m), "--transcript", str(t), "--dry-run"]) == 0
    assert "saved_s" in capsys.readouterr().out
