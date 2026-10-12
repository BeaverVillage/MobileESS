"""JSON-only post-run timing receipt; never imports or invokes a solver."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/v42_b2_u4_primal_alns_600x3"
ANCHOR = datetime(2026, 10, 12, 3, 11, 44, tzinfo=timezone.utc)


def main():
    comparison_path = DOCS / "COMPARISON.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    methods = comparison["methods"]
    assert set(methods) == {"N1", "N2", "N3"}
    assert all(m["stopped_reason"] and 0 <= m["actual_Native_sum"] <= 600 for m in methods.values())
    now = datetime.now(timezone.utc)
    total_method_wall = sum(m["overall_wall_seconds"] for m in methods.values())
    method_times = {}
    for name, method in methods.items():
        method_times[name] = {
            "algorithm_wall_seconds": method["overall_wall_seconds"],
            "actual_Native_seconds": method["actual_Native_sum"],
            "pre_Optimize_build_wall_seconds": sum(c["model_build_wall_seconds"] for c in method["calls"]),
            "external_Optimize_return_wall_seconds": sum(c["Optimize_return_wall_seconds"] for c in method["calls"]),
            "external_return_minus_Runtime_seconds": sum(c["Solver_return_overhead_seconds"] for c in method["calls"]),
            "candidate_FULL_replay_wall_seconds": sum(
                v["validation_wall_seconds"]
                for iteration in method["iterations"]
                for v in iteration.get("validated_candidates", [])
            ),
            "neighborhood_preparation_wall_seconds": sum(i.get("preparation_wall_seconds", 0) for i in method["iterations"]),
        }
    assert sum(m["actual_Native_seconds"] for m in method_times.values()) == comparison["total_actual_Native_seconds"]
    observed = (now - ANCHOR).total_seconds()
    assert observed >= comparison["total_wall_seconds"] >= total_method_wall
    receipt = {
        "schema": "V42_U4_PRIMAL_ALNS_POST_RUN_WALL_TIMING_V1",
        "PASS": True,
        "anchor_UTC": ANCHOR.isoformat(),
        "anchor_provenance": "Observed research worktree CreationTimeUtc, rounded to seconds; human message receipt and pre-worktree activity were not measured.",
        "recorded_UTC": now.isoformat(),
        "observed_worktree_to_timing_receipt_seconds": observed,
        "execution_epochs_wall_seconds": comparison["total_wall_seconds"],
        "algorithm_wall_sum_seconds": total_method_wall,
        "execution_epochs_outside_method_wall_seconds": comparison["total_wall_seconds"] - total_method_wall,
        "actual_Native_sum_seconds": comparison["total_actual_Native_seconds"],
        "methods": method_times,
        "scope": {
            "observed_span": "Includes setup, historical/source/resource review, failed preparation, Native0 regressions, both execution epochs, pause/recovery and post-run independent validation up to recorded_UTC. Report rendering and Git delivery occur later and are separately timestamped.",
            "execution_epochs": comparison["wall_scope"],
            "method_wall": "Measured algorithm entry through all restricted calls and independent candidate FULL Replay; each method starts its own original U4 point.",
            "pre_Optimize_build": "Worker entry through model load/construction/readback/Native0/admission; not a pure model assembly benchmark.",
            "component_accounting": "Component times are measured subscopes, not quantities to add to algorithm or execution wall. Overlapping or concurrent independent preparation is not assigned invented exclusive durations.",
            "unmeasured": "No exact human receipt timestamp, no exclusive initial setup/history phase durations; no zero-time claim for these activities.",
            "report_end": "REPORT_RENDER_RECEIPT.json separately records observed worktree-to-report time including report construction.",
        },
        "comparison_sha256": sha256(comparison_path.read_bytes()).hexdigest(),
        "Native_optimize_calls_by_timer": 0,
        "Gurobi_imports_by_timer": 0,
    }
    output = DOCS / "RESEARCH_WALL_CLOCK.json"
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"PASS": True, "output": str(output), "observed_seconds": observed,
                      "actual_Native_seconds": comparison["total_actual_Native_seconds"]}))


if __name__ == "__main__":
    main()
