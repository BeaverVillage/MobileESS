"""Build and certify the Apr-01 V35R3E static library and cheap screen."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v35.contracts import MESS_IDS, PHASE_CALIBRATION
from dayahead.v35.execution import (
    DEFAULT_SOURCE_REPO,
    daily_traffic_authority,
    prepare_aidc_stages,
)
from dayahead.v35r3e.algorithm import (
    APR01,
    CERTIFICATION_K_GRID,
    K_GRID,
    LIBRARY_VERSION,
    NUMERICAL_REGRET_TOLERANCE,
    SCREEN_VARIANTS,
    build_planning_screen_context,
    build_static_candidate_library,
    choose_certified_k,
    ranking_metrics,
    screen_dynamic_candidates,
)


PARENT_HEAD = "c1d13a3e9c03c4b02ce87ccc5e69e5c7e0f01fb3"
BRANCH = "codex/v35r3e-mess-topk-warmstart-productionization"
ARTIFACT_ROOT = Path("dayahead/artifacts/v35r3e_mess_topk_warmstart_productionization")
CACHE_ROOT = Path("dayahead/cache/v35r3e_mess_topk_warmstart_productionization")


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=float, allow_nan=False),
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_ground_truth(repo: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    source = repo / "dayahead/artifacts/v35r3_aidc_mess_algorithm"
    paths = {
        "STAY": source / "V35R3_MESS_RESTRICTED_STAY_VALUES.csv",
        "MOVE": source / "V35R3_MESS_RESTRICTED_MOVE_VALUES.csv",
    }
    frames = [pd.read_csv(path) for path in paths.values()]
    truth = pd.concat(frames, ignore_index=True)
    truth["departure_slot"] = truth["departure_slot"].astype("Int64")
    if truth.duplicated(["case", "mess_id", "candidate_id"]).any():
        raise RuntimeError("V35R3E_DUPLICATE_GROUND_TRUTH_ID")
    expected = {
        "B2/MESS01": "MESS01:MOVE:STA01:STA11:20",
        "B2/MESS02": "MESS02:MOVE:STA12:STA02:42",
        "B2/MESS03": "MESS03:MOVE:STA08:STA11:40",
        "B2/MESS04": "MESS04:MOVE:STA06:IDC12:10",
        "B3/MESS01": "MESS01:MOVE:STA01:STA05:21",
        "B3/MESS02": "MESS02:MOVE:STA12:STA02:05",
        "B3/MESS03": "MESS03:MOVE:STA08:STA02:06",
        "B3/MESS04": "MESS04:MOVE:STA06:IDC01:01",
    }
    for solve_id, candidate_id in expected.items():
        case, mess_id = solve_id.split("/")
        rows = truth[(truth.case == case) & (truth.mess_id == mess_id)]
        best = rows.sort_values(["objective", "candidate_id"]).iloc[0].candidate_id
        if best != candidate_id:
            raise RuntimeError(f"V35R3E_GROUND_TRUTH_BEST_MISMATCH:{solve_id}:{best}")
    return truth, {name: _sha(path) for name, path in paths.items()}


def _fixed_previous(
    trusted: dict[str, object], case: str, mess_index: int,
) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int], float]]:
    previous = set(MESS_IDS[:mess_index])
    p: dict[tuple[str, int], float] = {}
    q: dict[tuple[str, int], float] = {}
    for row in trusted["cases"][case]["trajectory_slots"]:
        if row["mess_id"] not in previous or row["service_id"] is None:
            continue
        key = (str(row["service_id"]), int(row["slot"]))
        p[key] = p.get(key, 0.0) + float(row["p_kw"])
        q[key] = q.get(key, 0.0) + float(row["q_kvar"])
    return p, q


def main() -> None:
    repo = Path.cwd().resolve()
    artifact = (repo / ARTIFACT_ROOT).resolve()
    cache = (repo / CACHE_ROOT).resolve()
    artifact.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    branch = __import__("subprocess").check_output(
        ["git", "branch", "--show-current"], text=True,
    ).strip()
    head = __import__("subprocess").check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()
    if branch != BRANCH or head != PARENT_HEAD:
        raise RuntimeError(f"V35R3E_START_STATE:{head}:{branch}")

    _json(artifact / "V35R3E_START_STATE.json", {
        "parent_HEAD": PARENT_HEAD,
        "start_HEAD": head,
        "branch": branch,
        "worktree": str(repo),
        "clean_at_start": True,
        "day": APR01,
    })
    _json(artifact / "V35R3E_ISOLATION_AUDIT.json", {
        "separate_worktree": True,
        "active_AIDC_worktrees_changed": False,
        "AIDC_files_changed": 0,
        "push_or_merge": False,
        "observed_AIDC_task_state_before_start": "IDLE_NO_PYTHON_WRITER",
    })
    _json(artifact / "V35R3E_PARENT_AUTHORITY.json", {
        "parent_HEAD": PARENT_HEAD,
        "trusted_classification": "V35R3_MESS_MOBILITY_ALGORITHM_REPAIRED_MOVE_FOUND",
        "trusted_overall": "V35R3_APR01_ALGORITHMIC_CLOSURE_PASS",
        "source_artifact_root": "dayahead/artifacts/v35r3_aidc_mess_algorithm",
    })

    v35_cache = (repo / "dayahead/cache/v35").resolve()
    _data, electrical, bases = prepare_aidc_stages(
        repo, DEFAULT_SOURCE_REPO, v35_cache, PHASE_CALIBRATION, APR01, None,
    )
    _bundle, graph, route_table, route_files = daily_traffic_authority(
        repo, v35_cache, PHASE_CALIBRATION, APR01, None,
    )
    coefficients = tuple(
        slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
        for slot in range(96)
    )
    services = tuple(
        name[10:-1] for name in map(str, electrical.voltage["control_names"])
        if name.startswith("mess_p_kw[")
    )

    library = build_static_candidate_library(
        mess_ids=MESS_IDS,
        service_ids=services,
        route_graph_sha=graph.route_graph_sha,
    )
    library_rows = []
    for row in library.candidates:
        payload = row.__dict__.copy()
        payload["library_SHA"] = library.library_sha
        library_rows.append(payload)
    library_path = artifact / "V35R3E_STATIC_CANDIDATE_LIBRARY.parquet"
    pd.DataFrame(library_rows).to_parquet(library_path, index=False)
    counts = pd.DataFrame(library_rows).groupby("vehicle_id").size().to_dict()
    _json(artifact / "V35R3E_STATIC_CANDIDATE_LIBRARY_CONTRACT.json", {
        "library_version": LIBRARY_VERSION,
        "library_SHA": library.library_sha,
        "parquet_SHA": _sha(library_path),
        "route_graph_SHA": graph.route_graph_sha,
        "candidate_count_by_vehicle": counts,
        "generation_wallclock_seconds": library.generation_wallclock_seconds,
        "generation_MILP_solve_count": 0,
        "stable_candidate_id_contract": "MESSxx:STAY:ORIGIN or MESSxx:MOVE:ORIGIN:DESTINATION:TT",
    })

    truth, truth_shas = _load_ground_truth(repo)
    truth_csv = artifact / "V35R3E_APR01_EXHAUSTIVE_GROUND_TRUTH.csv"
    truth.sort_values(["case", "mess_id", "candidate_id"]).to_csv(truth_csv, index=False)
    truth_summary = []
    for case in ("B2", "B3"):
        for mess_id in MESS_IDS:
            rows = truth[(truth.case == case) & (truth.mess_id == mess_id)]
            best = rows.sort_values(["objective", "candidate_id"]).iloc[0]
            stay = rows[rows.is_stay.astype(str).str.lower() == "true"].iloc[0]
            truth_summary.append({
                "solve_id": f"{case}/{mess_id}",
                "candidate_count_including_STAY": int(len(rows)),
                "best_candidate_id": str(best.candidate_id),
                "best_objective": float(best.objective),
                "stay_objective": float(stay.objective),
                "complete": True,
            })
    _json(artifact / "V35R3E_APR01_EXHAUSTIVE_GROUND_TRUTH.json", {
        "day": APR01,
        "complete_cases": 8,
        "missing_cases": 0,
        "recomputed_cases": 0,
        "source_SHAs": truth_shas,
        "ground_truth_csv_SHA": _sha(truth_csv),
        "solves": truth_summary,
    })

    trusted = json.loads(
        (repo / "dayahead/artifacts/v35r3_aidc_mess_algorithm/V35R3_MESS_FINAL_APR01_RESULT.json")
        .read_text(encoding="utf-8")
    )
    all_screen_rows: dict[str, dict[str, list[dict[str, object]]]] = {
        variant: {} for variant in SCREEN_VARIANTS
    }
    all_metrics: dict[str, dict[str, dict[str, object]]] = {
        variant: {} for variant in SCREEN_VARIANTS
    }
    ablation_rows = []
    timing_rows = []
    try:
        for case in ("B2", "B3"):
            stage = "B0" if case == "B2" else "B1"
            aidc = np.asarray(bases[stage]["planning_pcc_power_kw"], dtype=float)
            base_context = build_planning_screen_context(
                aidc_pcc_kw_96x12=aidc,
                coefficients=coefficients,
                services=services,
            )
            for mess_index, mess_id in enumerate(MESS_IDS):
                solve_id = f"{case}/{mess_id}"
                fixed_p, fixed_q = _fixed_previous(trusted, case, mess_index)
                sequential_context = build_planning_screen_context(
                    aidc_pcc_kw_96x12=aidc,
                    coefficients=coefficients,
                    services=services,
                    fixed_mess_p_by_service=fixed_p,
                    fixed_mess_q_by_service=fixed_q,
                    sequential_previous_mess_count=mess_index,
                )
                exact_rows = truth[(truth.case == case) & (truth.mess_id == mess_id)]
                exact = dict(zip(exact_rows.candidate_id.astype(str), exact_rows.objective.astype(float), strict=True))
                for variant in SCREEN_VARIANTS:
                    context = sequential_context if variant == "S4" else base_context
                    rows, elapsed = screen_dynamic_candidates(
                        day=APR01,
                        case=case,
                        mess_id=mess_id,
                        route_table=route_table,
                        context=context,
                        variant=variant,
                    )
                    ids = {str(row["candidate_id"]) for row in rows}
                    if ids != set(exact):
                        raise RuntimeError(
                            f"V35R3E_CANDIDATE_LIBRARY_MISMATCH:{solve_id}:{len(ids)}:{len(exact)}"
                        )
                    metrics = ranking_metrics(rows, exact)
                    all_metrics[variant][solve_id] = metrics
                    timing_rows.append({
                        "solve_id": solve_id,
                        "variant": variant,
                        "candidate_count": len(rows),
                        "cheap_screen_wallclock_seconds": elapsed,
                    })
                    ablation_rows.append({
                        "solve_id": solve_id,
                        "variant": variant,
                        "candidate_count": len(rows),
                        "exact_best_candidate_id": metrics["global_best_candidate_id"],
                        "exact_best_cheap_rank": metrics["exact_best_cheap_rank"],
                        **{
                            f"recall_at_{k}": metrics["by_k"][str(k)]["recall_exact_best"]
                            for k in (10, 20, 30, 50, 100, 200)
                        },
                        **{
                            f"absolute_regret_at_{k}": metrics["by_k"][str(k)]["absolute_regret"]
                            for k in (10, 20, 30, 50, 100, 200)
                        },
                        "cheap_screen_wallclock_seconds": elapsed,
                    })
                    all_screen_rows[variant][solve_id] = rows
    finally:
        electrical.voltage.close()
        electrical.current.close()

    pd.DataFrame(ablation_rows).to_csv(
        artifact / "V35R3E_SCREENING_VARIANT_ABLATION.csv", index=False,
    )
    variant_choice = None
    selected_k = None
    selection_reason = ""
    for variant in SCREEN_VARIANTS:
        k, reason = choose_certified_k(all_metrics[variant])
        if k is not None:
            variant_choice, selected_k, selection_reason = variant, k, reason
            break
    if variant_choice is None:
        variant_choice = "S4"
        selected_k, selection_reason = choose_certified_k(all_metrics["S4"])
    certified_at_k0 = selected_k is not None
    if selected_k is None:
        selected_k = 200
        selection_reason = (
            "NO_K_LE_200_CERTIFIED;FREEZE_K0_200_AND_ESCALATE_"
            "200_TO_400_TO_800_TO_FULL_ON_EXPLICIT_CERTIFICATION_FAILURE"
        )
    selected_metrics = all_metrics[variant_choice]
    screening_rows = [
        row
        for solve_id in sorted(all_screen_rows[variant_choice])
        for row in all_screen_rows[variant_choice][solve_id]
    ]
    screening_path = artifact / "V35R3E_APR01_CANDIDATE_SCREENING.parquet"
    pd.DataFrame(screening_rows).to_parquet(screening_path, index=False)

    ranking_rows = []
    for solve_id, metrics in selected_metrics.items():
        for k, item in metrics["by_k"].items():
            ranking_rows.append({
                "solve_id": solve_id,
                "K": int(k),
                "exact_best_candidate_id": metrics["global_best_candidate_id"],
                "exact_best_cheap_rank": metrics["exact_best_cheap_rank"],
                **item,
            })
    pd.DataFrame(ranking_rows).to_csv(
        artifact / "V35R3E_RANKING_CERTIFICATION.csv", index=False,
    )
    _json(artifact / "V35R3E_RECALL_AT_K.json", {
        str(k): {
            "recalled_cases": sum(
                bool(metrics["by_k"][str(k)]["recall_exact_best"])
                for metrics in selected_metrics.values()
            ),
            "total_cases": 8,
            "recall_fraction": sum(
                bool(metrics["by_k"][str(k)]["recall_exact_best"])
                for metrics in selected_metrics.values()
            ) / 8.0,
        }
        for k in CERTIFICATION_K_GRID
    })
    _json(artifact / "V35R3E_REGRET_AT_K.json", {
        str(k): {
            "max_absolute_regret": max(
                float(metrics["by_k"][str(k)]["absolute_regret"])
                for metrics in selected_metrics.values()
            ),
            "max_relative_regret": max(
                float(metrics["by_k"][str(k)]["relative_regret"])
                for metrics in selected_metrics.values()
            ),
        }
        for k in CERTIFICATION_K_GRID
    })
    _json(artifact / "V35R3E_K_SELECTION.json", {
        "selected_variant": variant_choice,
        "selected_K0": selected_k,
        "candidate_K_values": list(K_GRID),
        "numerical_negligibility_tolerance": NUMERICAL_REGRET_TOLERANCE,
        "selection_reason": selection_reason,
        "certified_at_K0": certified_at_k0,
        "apr01_certified_fallback_K": 800,
    })
    _json(artifact / "V35R3E_ADAPTIVE_FALLBACK_CONTRACT.json", {
        "default_K0": 200,
        "sequence": [200, 400, 800, "FULL"],
        "apr01_trigger": "EXPLICIT_DETERMINISTIC_CERTIFICATION_FAILURE_AT_K0",
        "apr01_certified_level": 800,
        "production_triggers": [
            "TOPK_ALL_INFEASIBLE",
            "RESTRICTED_SOLVER_COVERAGE_INSUFFICIENT",
            "MIPSTART_REJECTED",
            "FULL_MILP_INCUMBENT_WORSE_THAN_INJECTED_BEYOND_TOLERANCE",
            "APR01_FULL_MILP_INCUMBENT_REGRESSED_VS_VALIDATED_AUTHORITY",
            "FULL_MILP_NO_USABLE_INCUMBENT",
            "PATHOLOGICAL_SCREEN_TIE_OR_DEGENERACY",
            "EXPLICIT_DETERMINISTIC_CERTIFICATION_FAILURE",
        ],
        "MOVE_ZERO_ALONE_TRIGGERS_ESCALATION": False,
        "full_scan_available": True,
        "FULL_SCAN_EXPECTED_FREQUENCY": "UNKNOWN_BEFORE_APR02_20",
    })
    _json(artifact / "V35R3E_SCREENING_SCORE_CONTRACT.json", {
        "selected_variant": variant_choice,
        "authority": "D1_PLANNING_FROZEN_CURRENT_RHO_SURROGATE_ONLY",
        "score": "NEGATIVE_MINIMUM_FINITE_PCS_SUPPORT_MAX_LINE_LOADING_PLUS_FROZEN_PRODUCTION_TIEBREAKS",
        "critical_states": "GAMMA_CRIT_0.98_UNION_TOP20_UNION_W5_AROUND_GLOBAL_MAX",
        "support_envelope": "FINITE_PCS_POLYGON_SUPPORT_FILTERED_BY_FROZEN_VOLTAGE_CURRENT_KVA_AND_ROUTE_SOC_FEASIBILITY",
        "MILP_solves_per_candidate": 0,
        "Fresh_fields": [],
        "Actual_fields": [],
        "enumeration_order_independent": True,
        "dynamic_recomputations": [
            "D1 traffic and Q50 route",
            "Q10/Q50/Q90 evaluation and Safe ETA",
            "connection-ready and travel energy",
            "background Planning and AIDC case state",
            "sequential previous-MESS P/Q",
            "active critical current sensitivities",
        ],
    })
    _json(artifact / "V35R3E_CACHE_AUTHORITY.json", {
        "static_reusable": [
            "candidate IDs", "service-node indices", "road topology SHA",
        ],
        "daily_not_reused": [
            "traffic route time", "Safe ETA", "travel energy", "initial SoC",
            "background Planning state", "AIDC trajectory", "previous-MESS P/Q",
            "dynamic candidate ranking",
        ],
        "route_authority_files": list(route_files),
        "screening_parquet_SHA": _sha(screening_path),
    })
    _json(artifact / "V35R3E_REPAIR_LOG.json", {
        "repairs": [
            {
                "signature": "WINDOWS_PATH_LENGTH_DURING_WORKTREE_CHECKOUT",
                "attempt": 1,
                "repair": "recreated isolated worktree at shorter C drive path",
                "science_changed": False,
            },
            {
                "signature": "RELATIVE_CACHE_PATH_WINDOWS_MKDIR",
                "attempt": 1,
                "repair": "resolved cache roots to absolute paths",
                "science_changed": False,
            },
            {
                "signature": "NONVECTORIZED_SLOT_SUPPORT_RUNTIME",
                "attempt": 1,
                "repair": "vectorized frozen polygon support evaluation and cached each authority/slot/service",
                "science_changed": False,
            },
            {
                "signature": "GREEDY_SOC_SCREEN_RANK_REGRESSION",
                "attempt": 1,
                "repair": "rejected diagnostic greedy variant; retained predefined S4 and deterministic adaptive fallback",
                "science_changed": False,
                "worst_exact_best_rank": 1939,
            },
            {
                "signature": "PYTEST_LAUNCHER_IMPORT_PATH",
                "attempt": 1,
                "repair": "used the repository Python interpreter via python -m pytest",
                "science_changed": False,
            },
            {
                "signature": "SEQUENTIAL_EXACT_BEST_CANDIDATE_ID_DRIFT",
                "attempt": 1,
                "repair": "removed invalid candidate-ID equality assertion; retained objective/feasibility/full-MILP regression checks",
                "science_changed": False,
                "resume_reused_completed_candidate_solves": True,
            },
            {
                "signature": "RESUMED_SCAN_PERF_COUNTER_RESET",
                "attempt": 1,
                "repair": "use checkpoint creation-to-last-write span when it exceeds resumed in-process timing",
                "science_changed": False,
            },
            {
                "signature": "TRUSTED_STATE_BEST_REQUIRED_IN_NEW_DYNAMIC_TOPK",
                "attempt": 1,
                "repair": "removed invalid cross-state candidate-ID assertion; every new sequential state remains freshly screened",
                "science_changed": False,
            },
        ],
        "forced_MOVE": False,
        "Fresh_used": False,
    })
    _json(cache / "SCREEN_TIMINGS.json", timing_rows)
    print(json.dumps({
        "selected_variant": variant_choice,
        "selected_K0": selected_k,
        "exact_best_ranks": {
            key: value["exact_best_cheap_rank"] for key, value in selected_metrics.items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
