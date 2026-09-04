"""Verify the successful current-head V29 smoke and freeze its code HEAD."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"
SMOKE = REPO / "frozen_artifacts/v29_non_authority_smoke_retry1/2025-04-02/V29_DAY_RESULT.json"
FREEZE_HEAD = "1de680e158b04c4bc1b97f7e7cf3bc85d2b69f6d"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if head != FREEZE_HEAD:
        raise RuntimeError(f"V29_SMOKE_HEAD_MISMATCH:{head}")
    value = json.loads(SMOKE.read_text(encoding="utf-8"))
    checks = {
        "full_pipeline": value["status"] == "PASS",
        "B0_B1_B2_B3_dominance": all(value["dominance"].values()),
        "B3_solver_equivalence_le_1e_4": value["B3_equivalence"]["relative_objective_range"] <= 1e-4,
        "schedule_freeze": len(value["schedule_root_sha256"]) == 64,
        "Actual_optimizer_calls_zero": value["actual_optimizer_calls"] == 0,
        "PI_firewall": value["PI"]["DA_namespace_reads"] == 0,
        "Fresh_OpenDSS_10x96": value["OpenDSS_trajectory_count"] == 10 and value["OpenDSS_solve_count"] == 960,
        "workload_conservation": all(abs(row["workload_mass_error_nodeh"]) <= 1e-9 for row in value["actual"].values()),
        "carryin_conservation": value["carryin_nodeh"] == 0.0,
        "no_hidden_shedding": all(row["hidden_shedding_nodeh"] == 0.0 for row in value["actual"].values()),
        "source_namespace_firewall": value["actual_namespace_open_before_freeze"] == 0,
        "connection_delay_semantics": value["connection_delay_slots"] == 1,
        "rho_main_contract": value["rho_AIDC"] == 0.1,
        "increment_resolution": value["increment_resolution"]["status"] in {"INCREMENT_RESOLVED", "STRONGLY_RESOLVED"},
    }
    if not all(checks.values()):
        raise RuntimeError(f"V29_SMOKE_VERIFICATION_FAIL:{checks}")
    write("V29_CURRENT_HEAD_SMOKE_RESULT.json", {
        "artifact_id": "V29_CURRENT_HEAD_SMOKE_RESULT_V1", "status": "PASS",
        "classification": "NON_AUTHORITY_V29_SMOKE", "day": "2025-04-02",
        "V29_DEV_FREEZE_HEAD": FREEZE_HEAD, "source_result_path": str(SMOKE),
        "source_result_sha256": sha256(SMOKE), "result": value,
        "failed_attempt_preserved": str(REPO / "frozen_artifacts/v29_non_authority_smoke/2025-04-02"),
    })
    write("V29_CURRENT_HEAD_SMOKE_VERIFICATION.json", {
        "artifact_id": "V29_CURRENT_HEAD_SMOKE_VERIFICATION_V1", "status": "PASS",
        "checks": checks, "check_count": len(checks), "pass_count": sum(checks.values()),
        "scientific_code_changed_after_smoke": False,
    })
    write("V29_DEV_FREEZE.json", {
        "artifact_id": "V29_DEV_FREEZE_V1", "status": "FROZEN",
        "V29_DEV_FREEZE_HEAD": FREEZE_HEAD,
        "smoke_result_sha256": sha256(SMOKE),
        "scientific_change_invalidates_smoke": True,
        "evaluation_name": "V29_DEVELOPMENT_REGRESSION_APR01_04",
    })


if __name__ == "__main__":
    main()
