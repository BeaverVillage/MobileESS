import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v29_grid_responsive_aidc"


def test_current_head_smoke_passes_every_gate():
    result = json.loads((ROOT / "V29_CURRENT_HEAD_SMOKE_RESULT.json").read_text(encoding="utf-8"))
    verify = json.loads((ROOT / "V29_CURRENT_HEAD_SMOKE_VERIFICATION.json").read_text(encoding="utf-8"))
    freeze = json.loads((ROOT / "V29_DEV_FREEZE.json").read_text(encoding="utf-8"))
    assert result["status"] == verify["status"] == "PASS"
    assert verify["check_count"] == verify["pass_count"]
    assert all(verify["checks"].values())
    assert result["result"]["B3_equivalence"]["relative_objective_range"] <= 1e-4
    assert result["result"]["OpenDSS_solve_count"] == 960
    assert result["result"]["actual_optimizer_calls"] == 0
    assert freeze["V29_DEV_FREEZE_HEAD"] == "1de680e158b04c4bc1b97f7e7cf3bc85d2b69f6d"
    assert freeze["status"] == "FROZEN"
