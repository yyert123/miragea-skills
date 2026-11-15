import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hook-variants" / "scripts"))
import hooks  # noqa: E402

def test_read_and_dry_run(tmp_path):
    f = tmp_path / "h.txt"
    f.write_text("# c\nShort one.\n\nThis hook is definitely going to be far too long for three seconds.\n")
    assert hooks.read_hooks(f) == ["Short one.", "This hook is definitely going to be far too long for three seconds."]
    assert hooks.main([str(f), "-o", str(tmp_path / "o"), "--dry-run"]) == 0
    m = json.loads((tmp_path / "o" / "manifest.json").read_text())
    assert m["hooks"][0]["text"] == "Short one." and not m["hooks"][0]["over_budget"]
    assert m["hooks"][1]["over_budget"]
