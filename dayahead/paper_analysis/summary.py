"""Read-only paper statistics from daily saved numerical data; no solver imports."""
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from .storage import MISSING, read, write_json, write_parquet, verify_seal


def daily(root):
    rows, runtime_rows, ml = [], [], []
    for p in sorted((Path(root) / "days").glob("*/B*/provenance.json")):
        case_root = p.parent
        certificate = verify_seal(case_root)
        provenance = read(p)
        planning = read(case_root / "planning/planning_summary.json")
        fresh = read(case_root / "fresh_ac/fresh_summary.json")
        day, case = provenance["operating_date"], provenance["case_id"]
        # Extrema independently recomputed from authoritative arrays.
        with np.load(case_root / "fresh_ac/bus_phase_voltage.npz") as z:
            v = z["Vmag_pu"]
            vmin, vmax, deviation = float(v.min()), float(v.max()), float(np.abs(v-1).max())
        with np.load(case_root / "fresh_ac/line_phase_current.npz") as z:
            rho = float(z["loading_pu"].max())
        if (rho, vmin, vmax) != (fresh["rho_max_AC"], fresh["Vmin_pu"], fresh["Vmax_pu"]):
            raise RuntimeError("PAPER_MONTHLY_RAW_EXTREMA_MISMATCH")
        row = {"date": day, "case": case, "Planning_J": planning["planning_objective_J"],
            "planning_rho_max": planning["planning_rho_max"], "Fresh_AC_rho": rho,
            "Vmin_pu": vmin, "Vmax_pu": vmax, "voltage_deviation": deviation,
            "persistence_status": certificate["status"]}
        for field in ("line_current_violation_count", "voltage_violation_count", "transformer_current_violation_count",
                      "transformer_kva_violation_count", "transformer_phase_current_loading_max", "transformer_total_kva_loading_max", "losses_kwh"):
            row[field] = fresh[field]
        runtime = read(case_root / "solver_runtime.json")
        for k, v in runtime.items():
            if k.startswith("runtime_") and isinstance(v, (int, float)):
                runtime_rows.append({"date": day, "case": case, "metric": k, "seconds": v})
        if case == "B3":
            row.update({k: v for k, v in read(case_root / "stage_objectives.json").items() if isinstance(v, (int, float))})
            feedback = read(case_root / "A2_feedback_summary.json")
            row.update({k: feedback[k] for k in ("A2_accepted", "A2_accepted_no_change", "A2_strict_improvement", "A2_fallback_to_A1")})
            m2 = read(case_root / "M2_summary.json")
            row.update({k: m2[k] for k in ("M2_accepted", "M2_strict_improvement", "M2_fallback")})
            frame = pd.read_parquet(case_root / "ml/runtime_predictions.parquet")
            frame["date"] = day
            ml.append(frame)
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(runtime_rows), pd.concat(ml, ignore_index=True) if ml else pd.DataFrame()


def stats(values):
    a = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(float)
    if not len(a):
        return {"n": 0, "status": MISSING}
    return {"n": len(a), "mean": float(a.mean()), "median": float(np.median(a)),
        "std_sample": float(a.std(ddof=1)) if len(a)>1 else None,
        "IQR": float(np.percentile(a, 75)-np.percentile(a, 25)), "p95": float(np.percentile(a, 95))}


def build(root, output):
    frame, runtime, ml = daily(root)
    output = Path(output)
    write_parquet(output / "DAILY_METRICS.parquet", frame)
    write_parquet(output / "DAILY_RUNTIME.parquet", runtime)
    summaries = []
    metrics = [k for k in frame.select_dtypes(include="number").columns if k not in ("date", "case")]
    for case, group in frame.groupby("case"):
        for metric in metrics:
            s = stats(group[metric])
            if s["n"]:
                summaries.append({"case": case, "metric": metric, **s})
    write_parquet(output / "CASE_STATISTICS.parquet", pd.DataFrame(summaries))
    paired = []
    for metric in ("Planning_J", "planning_rho_max", "Fresh_AC_rho"):
        pivot = frame.pivot(index="date", columns="case", values=metric)
        for left, right in combinations(pivot.columns, 2):
            common = pivot[[left, right]].dropna()
            for date, r in common.iterrows():
                paired.append({"date": date, "metric": metric, "left_case": left, "right_case": right,
                    "left_minus_right": float(r[left]-r[right]), "pair_common_date_count": len(common)})
    pairs = pd.DataFrame(paired)
    write_parquet(output / "PAIRED_DAILY_DIFFERENCES.parquet", pairs)
    stages = frame[frame.case.eq("B3")]
    counts = {k: int(stages[k].fillna(False).sum()) for k in
        ("A2_accepted", "A2_accepted_no_change", "A2_strict_improvement", "A2_fallback_to_A1", "M2_accepted", "M2_strict_improvement", "M2_fallback") if k in stages}
    write_json(output / "STAGE_ATTRIBUTION.json", {"days": len(stages), "counts": counts,
        "objective_statistics": {k: stats(stages[k]) for k in ("J_A1", "J_M1", "J_A2", "J_M2", "DELTA_J_M1", "DELTA_J_A2", "DELTA_J_M2") if k in stages}})
    write_json(output / "RUNTIME_STATISTICS.json", {case + ":" + metric: stats(g.seconds)
        for (case, metric), g in runtime.groupby(["case", "metric"])})
    ml_stats = {}
    if len(ml):
        used = ml[ml.point_model_evaluation_eligible]
        # Daily issue-job population; repeated UID across issue dates is intentional and disclosed.
        ml_stats = {"population": "eligible issue-time job predictions, not unique jobs", "rows": len(used),
            "unique_job_UIDs": used.job_uid.nunique(), "point_MAE": float(used.absolute_error_point.mean()),
            "point_median_AE": float(used.absolute_error_point.median()),
            "WAPE": float(used.absolute_error_point.sum()/used.actual_runtime_sec.sum()) if used.actual_runtime_sec.sum() else None,
            "safe_runtime_coverage": float(used.covered_by_safe_runtime.mean()),
            "mean_safety_margin_seconds": float((used.safe_runtime_sec-used.runtime_point_prediction_sec).mean()),
            "actual_fields_role": "EVALUATION_ONLY", "RUNNING_requested_remaining_not_a_ML_prediction": True}
    write_json(output / "RUNTIME_ML_STATISTICS.json", ml_stats)
    write_json(output / "SUMMARY_MANIFEST.json", {"case_rows": len(frame), "dates": sorted(frame.date.unique()),
        "common_dates_all_four_cases": int(frame.pivot(index="date", columns="case", values="Planning_J").dropna().shape[0]),
        "Actual_AC_rho": "NOT_EXECUTED", "optimizer_imports": 0, "optimizer_calls": 0,
        "source_artifacts_modified": False, "rounding_applied": False, "statistical_test_selected": False,
        "historical_missing_fields_are_not_complete_PASS": True})
    return frame
