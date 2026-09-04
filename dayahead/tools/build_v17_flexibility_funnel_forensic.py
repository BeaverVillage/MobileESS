from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CAND = ROOT / "dayahead" / "artifacts" / "v17_candidate"
OUT = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
REF_DIR = CAND / "reference_v6_v4r1"
PUE = 1.30
BETA = 0.25
DT_H = 0.25
KAPPA = {"Q10": 0.3941881609951147, "Q50": 0.48563611660901085, "Q90": 0.5391969931144363}
DATES = ["2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"]
AIDCS = [f"AIDC{i:02d}" for i in range(1, 13)]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def div(a, b):
    return None if b in (None, 0) or a is None else float(a / b)


def sum_metric(rows, key):
    return float(sum(float(r[key]) for r in rows))


def schedule_map(results: dict) -> dict[tuple[str, str], Path]:
    out = {}
    for row in results["rows"]:
        raw = Path(row["final_schedule_path"])
        p = raw if raw.exists() else ROOT / "dayahead" / "artifacts" / "v17_candidate" / "schedules_v4r1" / raw.name
        out[(row["operating_day"], row["case"])] = p
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results_path = CAND / "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json"
    comparison_path = CAND / "V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON.json"
    results = load_json(results_path)
    comparison = load_json(comparison_path)
    schedules = schedule_map(results)
    coverage = results["coverage"]
    s0_jobs = int(coverage["semantic_flexible"]["jobs"])
    s0_gpuh = float(coverage["semantic_flexible"]["GPU_hours"])
    s1_jobs = int(coverage["V1_plus_V4R1_U2_CLEAN"]["jobs"])
    s1_gpuh = float(coverage["V1_plus_V4R1_U2_CLEAN"]["GPU_hours"])

    daily = {}
    site_rows = []
    all_ref_inputs = []
    aggregate_vectors = {k: [] for k in ["total_it", "total_pcc", "flex_it", "flex_pcc"]}
    shift_aggregate = defaultdict(lambda: defaultdict(float))
    shift_peak = defaultdict(float)
    shift_system_peak = defaultdict(float)
    mess_peak_kw = 0.0
    mess_per_unit_peak_kw = 0.0

    for date in DATES:
        ref_path = REF_DIR / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{date}.npz"
        all_ref_inputs.append(ref_path)
        with np.load(ref_path, allow_pickle=False) as z:
            allocation = np.asarray(z["allocation"], dtype=float)
            arrivals = np.asarray(z["arrivals"], dtype=float)
            plan_pcc = np.asarray(z["plan_kw_96x12"], dtype=float)
            p_res = np.asarray(z["p_res_aidc"], dtype=float)
        rack_flex_gpuh = allocation.sum(axis=0)  # 48 x 96 GPU-hour per slot
        rack_flex_kw = rack_flex_gpuh.T / DT_H * KAPPA["Q50"]
        flex_it_kw = rack_flex_kw.reshape(96, 12, 4).sum(axis=2)
        total_it_kw = plan_pcc / PUE
        flex_pcc_kw = flex_it_kw * PUE
        residual_it_kw = total_it_kw - flex_it_kw
        assert np.max(np.abs(plan_pcc - PUE * (p_res + flex_it_kw))) < 1e-9
        assert np.min(residual_it_kw) >= -1e-9
        assert abs(allocation.sum() - arrivals.sum()) < 1e-7

        aggregate_vectors["total_it"].append(total_it_kw)
        aggregate_vectors["total_pcc"].append(plan_pcc)
        aggregate_vectors["flex_it"].append(flex_it_kw)
        aggregate_vectors["flex_pcc"].append(flex_pcc_kw)

        pair_arrays = {}
        for pair, base_case, opt_case in [("B1-B0", "B0", "B1"), ("B3-B2", "B2", "B3")]:
            with np.load(schedules[(date, base_case)], allow_pickle=False) as z:
                base = np.asarray(z["controls_96x60"], dtype=float)[:, :12]
            with np.load(schedules[(date, opt_case)], allow_pickle=False) as z:
                opt = np.asarray(z["controls_96x60"], dtype=float)[:, :12]
                if opt_case == "B3":
                    mess = np.asarray(z["mess_p_96x4"], dtype=float)
                    mess_peak_kw = max(mess_peak_kw, float(np.max(np.abs(mess.sum(axis=1)))))
                    mess_per_unit_peak_kw = max(mess_per_unit_peak_kw, float(np.max(np.abs(mess))))
            delta = opt - base
            pair_arrays[pair] = delta
            for i, aidc in enumerate(AIDCS):
                d = delta[:, i]
                pos = float(np.maximum(d, 0).sum() * DT_H)
                neg = float(np.maximum(-d, 0).sum() * DT_H)
                absolute = float(np.abs(d).sum() * DT_H)
                net = float(d.sum() * DT_H)
                peak = float(np.max(np.abs(d)))
                vals = {
                    "date": date, "aidc_id": aidc, "optimized_case": pair,
                    "total_it_kwh": float(total_it_kw[:, i].sum() * DT_H),
                    "total_pcc_kwh": float(plan_pcc[:, i].sum() * DT_H),
                    "flex_it_kwh": float(flex_it_kw[:, i].sum() * DT_H),
                    "flex_pcc_kwh": float(flex_pcc_kw[:, i].sum() * DT_H),
                    "eta_flex_it": div(float(flex_it_kw[:, i].sum()), float(total_it_kw[:, i].sum())),
                    "eta_flex_pcc": div(float(flex_pcc_kw[:, i].sum()), float(plan_pcc[:, i].sum())),
                    "shifted_pcc_kwh": 0.5 * absolute,
                    "positive_shifted_pcc_kwh": pos,
                    "negative_shifted_pcc_kwh_magnitude": neg,
                    "absolute_shifted_pcc_kwh": absolute,
                    "net_shifted_pcc_kwh": net,
                    "peak_abs_delta_it_kw": peak / PUE,
                    "peak_abs_delta_pcc_kw": peak,
                }
                site_rows.append(vals)
                for key in ["shifted_pcc_kwh", "positive_shifted_pcc_kwh", "negative_shifted_pcc_kwh_magnitude", "absolute_shifted_pcc_kwh", "net_shifted_pcc_kwh"]:
                    shift_aggregate[pair][key] += vals[key]
                shift_peak[pair] = max(shift_peak[pair], peak)
            shift_system_peak[pair] = max(shift_system_peak[pair], float(np.max(np.abs(delta.sum(axis=1)))))

        daily[date] = {
            "forecast_arrival_GPU_hours": float(arrivals.sum()),
            "admitted_GPU_hours": float(allocation.sum()),
            "rejected_GPU_hours_within_forecast_cohort": float(arrivals.sum() - allocation.sum()),
            "flexible_IT_kWh": float(flex_it_kw.sum() * DT_H),
            "flexible_PCC_kWh": float(flex_pcc_kw.sum() * DT_H),
            "total_IT_kWh": float(total_it_kw.sum() * DT_H),
            "total_PCC_kWh": float(plan_pcc.sum() * DT_H),
            "mean_total_IT_kW": float(total_it_kw.sum(axis=1).mean()),
            "peak_total_IT_kW": float(total_it_kw.sum(axis=1).max()),
            "mean_total_PCC_kW": float(plan_pcc.sum(axis=1).mean()),
            "peak_total_PCC_kW": float(plan_pcc.sum(axis=1).max()),
            "mean_flexible_IT_kW": float(flex_it_kw.sum(axis=1).mean()),
            "peak_flexible_IT_kW": float(flex_it_kw.sum(axis=1).max()),
            "mean_flexible_PCC_kW": float(flex_pcc_kw.sum(axis=1).mean()),
            "peak_flexible_PCC_kW": float(flex_pcc_kw.sum(axis=1).max()),
            "eta_flex_energy_IT": div(float(flex_it_kw.sum()), float(total_it_kw.sum())),
            "eta_flex_energy_PCC": div(float(flex_pcc_kw.sum()), float(plan_pcc.sum())),
            "eta_flex_peak_IT": div(float(flex_it_kw.sum(axis=1).max()), float(total_it_kw.sum(axis=1).max())),
            "eta_flex_peak_PCC": div(float(flex_pcc_kw.sum(axis=1).max()), float(plan_pcc.sum(axis=1).max())),
            "pairs": {},
        }
        for pair in ["B1-B0", "B3-B2"]:
            d = pair_arrays[pair]
            daily[date]["pairs"][pair] = {
                "positive_shifted_IT_kWh": float(np.maximum(d, 0).sum() * DT_H / PUE),
                "negative_shifted_IT_kWh_magnitude": float(np.maximum(-d, 0).sum() * DT_H / PUE),
                "absolute_shifted_IT_kWh": float(np.abs(d).sum() * DT_H / PUE),
                "shifted_IT_kWh_L1_half": float(np.abs(d).sum() * DT_H / (2 * PUE)),
                "net_shifted_IT_kWh": float(d.sum() * DT_H / PUE),
                "positive_shifted_PCC_kWh": float(np.maximum(d, 0).sum() * DT_H),
                "negative_shifted_PCC_kWh_magnitude": float(np.maximum(-d, 0).sum() * DT_H),
                "absolute_shifted_PCC_kWh": float(np.abs(d).sum() * DT_H),
                "shifted_PCC_kWh_L1_half": float(np.abs(d).sum() * DT_H / 2),
                "net_shifted_PCC_kWh": float(d.sum() * DT_H),
                "peak_individual_AIDC_abs_delta_PCC_kW": float(np.max(np.abs(d))),
                "peak_system_aggregate_abs_delta_PCC_kW": float(np.max(np.abs(d.sum(axis=1)))),
            }

    total_it = np.concatenate(aggregate_vectors["total_it"], axis=0)
    total_pcc = np.concatenate(aggregate_vectors["total_pcc"], axis=0)
    flex_it = np.concatenate(aggregate_vectors["flex_it"], axis=0)
    flex_pcc = np.concatenate(aggregate_vectors["flex_pcc"], axis=0)
    s2_gpuh = sum(v["forecast_arrival_GPU_hours"] for v in daily.values())
    s4_flex_it_kwh = float(flex_it.sum() * DT_H)
    s4_flex_pcc_kwh = float(flex_pcc.sum() * DT_H)
    total_it_kwh = float(total_it.sum() * DT_H)
    total_pcc_kwh = float(total_pcc.sum() * DT_H)
    residual_it_kwh = total_it_kwh - s4_flex_it_kwh

    for pair in ["B1-B0", "B3-B2"]:
        assert abs(shift_aggregate[pair]["positive_shifted_pcc_kwh"] - shift_aggregate[pair]["negative_shifted_pcc_kwh_magnitude"]) < 1e-7
        assert abs(shift_aggregate[pair]["net_shifted_pcc_kwh"]) < 1e-7

    # Add same-definition site aggregates and system rows to the facility table.
    detailed_rows = list(site_rows)
    for pair in ["B1-B0", "B3-B2"]:
        pair_rows = [r for r in detailed_rows if r["optimized_case"] == pair]
        for aidc in AIDCS + ["SYSTEM"]:
            rs = pair_rows if aidc == "SYSTEM" else [r for r in pair_rows if r["aidc_id"] == aidc]
            row = {"date": "ALL_7_DAYS", "aidc_id": aidc, "optimized_case": pair}
            for key in ["total_it_kwh", "total_pcc_kwh", "flex_it_kwh", "flex_pcc_kwh", "shifted_pcc_kwh", "positive_shifted_pcc_kwh", "negative_shifted_pcc_kwh_magnitude", "absolute_shifted_pcc_kwh", "net_shifted_pcc_kwh"]:
                row[key] = sum_metric(rs, key)
            row["eta_flex_it"] = div(row["flex_it_kwh"], row["total_it_kwh"])
            row["eta_flex_pcc"] = div(row["flex_pcc_kwh"], row["total_pcc_kwh"])
            row["peak_abs_delta_it_kw"] = max(r["peak_abs_delta_it_kw"] for r in rs)
            row["peak_abs_delta_pcc_kw"] = max(r["peak_abs_delta_pcc_kw"] for r in rs)
            site_rows.append(row)
        for date in DATES:
            rs = [r for r in pair_rows if r["date"] == date]
            row = {"date": date, "aidc_id": "SYSTEM", "optimized_case": pair}
            for key in ["total_it_kwh", "total_pcc_kwh", "flex_it_kwh", "flex_pcc_kwh", "shifted_pcc_kwh", "positive_shifted_pcc_kwh", "negative_shifted_pcc_kwh_magnitude", "absolute_shifted_pcc_kwh", "net_shifted_pcc_kwh"]:
                row[key] = sum_metric(rs, key)
            row["eta_flex_it"] = div(row["flex_it_kwh"], row["total_it_kwh"])
            row["eta_flex_pcc"] = div(row["flex_pcc_kwh"], row["total_pcc_kwh"])
            row["peak_abs_delta_it_kw"] = daily[date]["pairs"][pair]["peak_individual_AIDC_abs_delta_PCC_kW"] / PUE
            row["peak_abs_delta_pcc_kw"] = daily[date]["pairs"][pair]["peak_individual_AIDC_abs_delta_PCC_kW"]
            site_rows.append(row)

    comp_by_day = {r["operating_day"]: r for r in comparison["rows"]}
    objective = []
    for date in DATES:
        r = comp_by_day[date]
        actual = float(r["V4R1_B1_minus_B0"]["objective_relief_pu"])
        upper = float(r["V4R1_AIDC_only_upper_bound"]["best_possible_relief_pu"])
        objective.append({
            "date": date,
            "B1_minus_B0_relief_pu": actual,
            "B3_minus_B2_relief_pu": float(r["V4R1_B3_minus_B2"]["objective_relief_pu"]),
            "AIDC_only_best_possible_relief_pu": upper,
            "B1_fraction_of_AIDC_only_upper_bound": div(actual, upper),
        })

    s0 = {"jobs": s0_jobs, "GPU_hours": s0_gpuh, "scope": "2024-08-19 through 2025-03-31 semantic-flexible training authority"}
    s1 = {"jobs": s1_jobs, "GPU_hours": s1_gpuh, "retained_job_fraction": s1_jobs / s0_jobs, "retained_GPU_hour_fraction": s1_gpuh / s0_gpuh, "attrition_GPU_hours": s0_gpuh - s1_gpuh}
    s2 = {"jobs": None, "jobs_status": "NOT_IDENTIFIABLE_FROM_AGGREGATE_FORECAST_AUTHORITY", "GPU_hours": s2_gpuh, "ratio_to_S1": s2_gpuh / s1_gpuh, "ratio_semantics": "MAGNITUDE_RATIO_NOT_SET_RETENTION; different periods and forecast aggregate versus training support"}
    s3 = {"jobs": None, "admitted_GPU_hours": s2_gpuh, "rejected_GPU_hours_within_forecast_cohort": 0.0, "retained_fraction_within_forecast_cohort": 1.0, "already_running_GPU_hours": None, "queued_or_backlog_GPU_hours": None, "policy": "FORECAST_COHORT_ONLY; initial backlog=0; individual queued-job injection=0"}
    s4 = {"flexible_IT_kWh": s4_flex_it_kwh, "flexible_PCC_kWh": s4_flex_pcc_kwh, "average_flexible_IT_kW": s4_flex_it_kwh / (24 * 7), "peak_flexible_IT_kW": float(flex_it.sum(axis=1).max()), "average_flexible_PCC_kW": s4_flex_pcc_kwh / (24 * 7), "peak_flexible_PCC_kW": float(flex_pcc.sum(axis=1).max()), "boundary": "NVML GPU-board incremental above 72.5 W/GPU idle; Q50; whole GPU; PUE once at IT-to-PCC"}
    s5 = {"total_IT_kWh": total_it_kwh, "total_PCC_kWh": total_pcc_kwh, "mean_total_IT_kW": total_it_kwh / (24 * 7), "peak_total_IT_kW": float(total_it.sum(axis=1).max()), "mean_total_PCC_kW": total_pcc_kwh / (24 * 7), "peak_total_PCC_kW": float(total_pcc.sum(axis=1).max()), "eta_flex_energy_IT": s4_flex_it_kwh / total_it_kwh, "eta_flex_energy_PCC": s4_flex_pcc_kwh / total_pcc_kwh, "eta_flex_peak_IT": float(flex_it.sum(axis=1).max() / total_it.sum(axis=1).max()), "eta_flex_peak_PCC": float(flex_pcc.sum(axis=1).max() / total_pcc.sum(axis=1).max())}
    s6 = {}
    s7 = {}
    for pair in ["B1-B0", "B3-B2"]:
        s6[pair] = {
            "shifted_IT_kWh_L1_half": shift_aggregate[pair]["shifted_pcc_kwh"] / PUE,
            "positive_shifted_IT_kWh": shift_aggregate[pair]["positive_shifted_pcc_kwh"] / PUE,
            "negative_shifted_IT_kWh_magnitude": shift_aggregate[pair]["negative_shifted_pcc_kwh_magnitude"] / PUE,
            "absolute_shifted_IT_kWh": shift_aggregate[pair]["absolute_shifted_pcc_kwh"] / PUE,
            "net_shifted_IT_kWh": shift_aggregate[pair]["net_shifted_pcc_kwh"] / PUE,
            **shift_aggregate[pair],
            "peak_individual_AIDC_abs_delta_PCC_kW": shift_peak[pair],
            "peak_individual_AIDC_abs_delta_IT_kW": shift_peak[pair] / PUE,
            "peak_system_aggregate_abs_delta_PCC_kW": shift_system_peak[pair],
            "peak_system_aggregate_abs_delta_IT_kW": shift_system_peak[pair] / PUE,
        }
        s7[pair] = {"shift_utilization_energy": shift_aggregate[pair]["shifted_pcc_kwh"] / s4_flex_pcc_kwh, "shift_utilization_peak": shift_peak[pair] / s4["peak_flexible_PCC_kW"]}

    counterfactuals = {
        "diagnostic_class": "NON_AUTHORITY_DIAGNOSTIC",
        "C0_CURRENT": {"flexible_IT_kWh": s4_flex_it_kwh, "flexible_PCC_kWh": s4_flex_pcc_kwh, "facility_flexible_share": s5["eta_flex_energy_IT"], "theoretical_peak_actuation_upper_bound_PCC_kW": s4["peak_flexible_PCC_kW"]},
        "C1_BETA_1_EQUIVALENT_ARITHMETIC": {"assumption": "total and flexible power both divided by frozen beta=0.25", "flexible_IT_kWh": s4_flex_it_kwh / BETA, "flexible_PCC_kWh": s4_flex_pcc_kwh / BETA, "facility_flexible_share": s5["eta_flex_energy_IT"], "theoretical_peak_actuation_upper_bound_PCC_kW": s4["peak_flexible_PCC_kW"] / BETA},
        "C2_KAPPA_SENSITIVITY": {},
        "C3_BACKLOG_INCLUSION_UPPER_BOUND": {"flexible_IT_kWh": None, "flexible_PCC_kWh": None, "facility_flexible_share": None, "theoretical_peak_actuation_upper_bound_PCC_kW": None, "status": "NOT_IDENTIFIABLE_FROM_CURRENT_AUTHORITY"},
        "C4_HOST_POWER_INCLUSION": {"flexible_IT_kWh": None, "flexible_PCC_kWh": None, "facility_flexible_share": None, "theoretical_peak_actuation_upper_bound_PCC_kW": None, "status": "NOT_IDENTIFIABLE_FROM_CURRENT_AUTHORITY"},
        "C5_FULL_MODELABLE_AS_7DAY_AVAILABLE": {"assumption": "all S1 training-support GPU-hours available in the seven evaluation days; not policy or temporal authority", "flexible_IT_kWh": s1_gpuh * KAPPA["Q50"], "flexible_PCC_kWh": s1_gpuh * KAPPA["Q50"] * PUE, "facility_flexible_share": s1_gpuh * KAPPA["Q50"] / total_it_kwh, "theoretical_peak_actuation_upper_bound_PCC_kW": None, "peak_status": "NOT_IDENTIFIABLE_WITHOUT_SLOT_PROFILE_AND_DEADLINES"},
    }
    for q, k in KAPPA.items():
        counterfactuals["C2_KAPPA_SENSITIVITY"][q] = {"flexible_IT_kWh": s2_gpuh * k, "flexible_PCC_kWh": s2_gpuh * k * PUE, "facility_flexible_share": s2_gpuh * k / total_it_kwh, "theoretical_peak_actuation_upper_bound_PCC_kW": s4["peak_flexible_PCC_kW"] * k / KAPPA["Q50"]}

    funnel_rows = [
        {"stage": "S0", "quantity": "semantic-flexible training workload", "jobs": s0_jobs, "GPU_hours": s0_gpuh, "energy_kWh": "", "retained_fraction": 1.0, "attrition_fraction": 0.0, "reason": "training semantic universe"},
        {"stage": "S1", "quantity": "power-modelable training support", "jobs": s1_jobs, "GPU_hours": s1_gpuh, "energy_kWh": "", "retained_fraction": s1_gpuh / s0_gpuh, "attrition_fraction": 1 - s1_gpuh / s0_gpuh, "reason": "unsupported or quarantined power semantics"},
        {"stage": "S2", "quantity": "seven evaluation-day forecast magnitude", "jobs": "", "GPU_hours": s2_gpuh, "energy_kWh": "", "retained_fraction": s2_gpuh / s1_gpuh, "attrition_fraction": 1 - s2_gpuh / s1_gpuh, "reason": "MAGNITUDE_RATIO_NOT_SET_RETENTION; 7 days versus training window"},
        {"stage": "S3", "quantity": "D-1 admitted forecast cohort", "jobs": "", "GPU_hours": s2_gpuh, "energy_kWh": "", "retained_fraction": 1.0, "attrition_fraction": 0.0, "reason": "all forecast arrivals served; other backlog/running workload excluded by policy but unquantified"},
        {"stage": "S4_IT", "quantity": "source-backed flexible IT energy", "jobs": "", "GPU_hours": s2_gpuh, "energy_kWh": s4_flex_it_kwh, "retained_fraction": "", "attrition_fraction": "", "reason": "Q50 GPU-board incremental conversion"},
        {"stage": "S4_PCC", "quantity": "source-backed flexible PCC energy", "jobs": "", "GPU_hours": s2_gpuh, "energy_kWh": s4_flex_pcc_kwh, "retained_fraction": "", "attrition_fraction": "", "reason": "PUE=1.30 applied once"},
        {"stage": "S5", "quantity": "facility-wide total IT denominator", "jobs": "", "GPU_hours": "", "energy_kWh": total_it_kwh, "retained_fraction": s4_flex_it_kwh / total_it_kwh, "attrition_fraction": 1 - s4_flex_it_kwh / total_it_kwh, "reason": "denominator comparison, not workload loss"},
        {"stage": "S6_B1", "quantity": "actually shifted PCC energy L1/2", "jobs": "", "GPU_hours": "", "energy_kWh": shift_aggregate["B1-B0"]["shifted_pcc_kwh"], "retained_fraction": s7["B1-B0"]["shift_utilization_energy"], "attrition_fraction": 1 - s7["B1-B0"]["shift_utilization_energy"], "reason": "deadline/capacity/reference and grid-objective scheduling envelope"},
        {"stage": "S6_B3", "quantity": "actually shifted PCC energy L1/2", "jobs": "", "GPU_hours": "", "energy_kWh": shift_aggregate["B3-B2"]["shifted_pcc_kwh"], "retained_fraction": s7["B3-B2"]["shift_utilization_energy"], "attrition_fraction": 1 - s7["B3-B2"]["shift_utilization_energy"], "reason": "joint MESS/workload optimization envelope"},
        {"stage": "S7", "quantity": "peak individual-AIDC PCC actuation", "jobs": "", "GPU_hours": "", "energy_kWh": "", "retained_fraction": s7["B3-B2"]["shift_utilization_peak"], "attrition_fraction": 1 - s7["B3-B2"]["shift_utilization_peak"], "reason": "peak shift divided by peak available flexible PCC power"},
    ]
    attrition_rows = [
        {"rank": 1, "transition": "S1 training support to S2 seven-day magnitude", "absolute_before": s1_gpuh, "absolute_after": s2_gpuh, "unit": "GPU-hour", "retained_fraction": s2_gpuh / s1_gpuh, "attrition_fraction": 1 - s2_gpuh / s1_gpuh, "causal_status": "CONTEXTUAL_MAGNITUDE_NOT_SET_ATTRITION", "reason": "different temporal populations; explains why training coverage cannot imply seven-day facility share"},
        {"rank": 2, "transition": "S4 flexible IT to S5 facility total IT", "absolute_before": total_it_kwh, "absolute_after": s4_flex_it_kwh, "unit": "kWh", "retained_fraction": s4_flex_it_kwh / total_it_kwh, "attrition_fraction": 1 - s4_flex_it_kwh / total_it_kwh, "causal_status": "DENOMINATOR_COMPARISON_NOT_WORKLOAD_LOSS", "reason": "GPU-board incremental flex is compared with whole-facility modeled IT"},
        {"rank": 3, "transition": "S4 available flexible PCC to S6 B1 shifted PCC", "absolute_before": s4_flex_pcc_kwh, "absolute_after": shift_aggregate["B1-B0"]["shifted_pcc_kwh"], "unit": "kWh", "retained_fraction": s7["B1-B0"]["shift_utilization_energy"], "attrition_fraction": 1 - s7["B1-B0"]["shift_utilization_energy"], "causal_status": "ACTUATION_UTILIZATION", "reason": "only part of available energy is moved relative to reference"},
        {"rank": 4, "transition": "S0 semantic-flexible to S1 power-modelable", "absolute_before": s0_gpuh, "absolute_after": s1_gpuh, "unit": "GPU-hour", "retained_fraction": s1_gpuh / s0_gpuh, "attrition_fraction": 1 - s1_gpuh / s0_gpuh, "causal_status": "TRUE_TRAINING_SUPPORT_ATTRITION", "reason": "unsupported/quarantined power semantics"},
        {"rank": 5, "transition": "S2 forecast arrivals to S3 admitted", "absolute_before": s2_gpuh, "absolute_after": s2_gpuh, "unit": "GPU-hour", "retained_fraction": 1.0, "attrition_fraction": 0.0, "causal_status": "WITHIN_FORECAST_COHORT", "reason": "reference scheduler served all aggregate arrivals; excluded backlog/running amount is unknown"},
    ]

    required_names = [
        "V17_AIDC_POWER_V4R1_FINAL_REVIEW.json", "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json", "V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON.json",
        "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_FORENSIC.json", "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_TABLE.csv", "V17_AIDC_FLEXIBLE_SHARE_AUTHORITY_PRECHECK.json",
        "V17_FLEXIBLE_SHARE_AUTHORITY_GAP.json", "V17_FLEXIBLE_SHARE_AUTHORITY_GAP_RESOLUTION.json", "V17_TRAINING_SEMANTIC_FLEXIBILITY_MAGNITUDE.json",
        "V17_FIXED_PLUS_FLEX_RESOURCE_LABEL_AUDIT.json", "V17_FLEXIBLE_COHORT_SEMANTICS_V2.json", "V17_GPU_SUBSYSTEM_BOUNDARY_TRAINING_AUDIT.json",
        "V17_KESTREL_DEFERRABILITY_FIELD_AUDIT.json", "V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT.json", "V17_KESTREL_WHOLE_GPU_GRES_SEMANTICS_AUDIT.json",
        "V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json", "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json", "V17_AIDC_POWER_MODEL_V4R1_CAPACITY_CONSISTENT_SUPPORT_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V4_WHOLE_GPU_GRES_CONTRACT.json", "V17_DATASET312_PER_GPU_BOARD_POWER_AUTHORITY.json", "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_CONTRACT.json",
        "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_7DAY_VALIDATION.json", "V17_RCMQT_V4R1_TARGET_SEMANTICS_CONTRACT.json", "V17_RCMQT_V4R1_APRIL_7DAY_VALIDATION.json",
        "V17_APRIL_7DAY_AIDC_ACTUATION_FORENSIC.json", "V17_V4R1_7DAY_SURROGATE_VALIDATION.json",
    ]
    inputs = []
    for name in required_names:
        matches = list(CAND.rglob(name))
        if matches:
            p = matches[0]
            inputs.append({"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p), "role": "authority_or_lineage"})
    for p in all_ref_inputs + sorted(set(schedules.values())):
        inputs.append({"path": p.relative_to(ROOT).as_posix(), "sha256": sha256(p), "role": "frozen_numeric_input"})

    hypotheses = {
        "H1": {"verdict": "PASS", "evidence": {"semantic_modelable_GPU_hour_coverage": s1_gpuh / s0_gpuh, "facility_flexible_energy_share": s4_flex_it_kwh / total_it_kwh}, "reason": "the two ratios have different denominators"},
        "H2": {"verdict": "PARTIAL", "evidence": {"identified_flexible_IT_kWh": s4_flex_it_kwh, "unidentified_or_residual_IT_kWh": residual_it_kwh, "identified_share": s4_flex_it_kwh / total_it_kwh}, "reason": "GPU-board-only authority leaves host/CPU/memory/network and other load in residual, but their workload-dependent flexible part is not identifiable"},
        "H3": {"verdict": "PARTIAL", "evidence": {"forecast_cohort_admission_fraction": 1.0, "excluded_already_running_GPU_hours": None, "excluded_queue_backlog_GPU_hours": None}, "reason": "policy excludes non-forecast cohorts, but all forecast arrivals are served and excluded amounts are unavailable"},
        "H4": {"verdict": "PASS", "evidence": {"B1_shift_utilization_energy": s7["B1-B0"]["shift_utilization_energy"], "B1_upper_bound_realization_mean": float(np.mean([r["B1_fraction_of_AIDC_only_upper_bound"] for r in objective]))}, "reason": "available flexible energy exceeds the moved energy, while objective relief closely approaches the independent AIDC-only bound"},
    }
    root = {
        "artifact_id": "V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1",
        "status": "PASS_READ_ONLY_REPRODUCIBLE_FORENSIC",
        "classification": "D. MULTI_FACTOR_ATTRITION",
        "temporal_contract": {"training_cutoff_statement": "2025-03-31 IS ML TRAINING CUTOFF ONLY.", "scaling_reference_statement": "APRIL 2025 IS THE REAL-WORLD SCALING REFERENCE PERIOD.", "evaluation_dates": DATES},
        "frozen_parameters": {"PUE": PUE, "beta_AIDC": BETA, "kappa_kW_per_GPU": KAPPA, "slot_hours": DT_H},
        "funnel": {"S0": s0, "S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "S6": s6, "S7": s7},
        "daily": daily,
        "objective_comparison": objective,
        "objective_summary": {
            "B1_relief_pu_min": min(r["B1_minus_B0_relief_pu"] for r in objective),
            "B1_relief_pu_max": max(r["B1_minus_B0_relief_pu"] for r in objective),
            "B3_relief_pu_min": min(r["B3_minus_B2_relief_pu"] for r in objective),
            "B3_relief_pu_max": max(r["B3_minus_B2_relief_pu"] for r in objective),
            "AIDC_only_upper_bound_pu_min": min(r["AIDC_only_best_possible_relief_pu"] for r in objective),
            "AIDC_only_upper_bound_pu_max": max(r["AIDC_only_best_possible_relief_pu"] for r in objective),
            "B1_fraction_of_upper_bound_min": min(r["B1_fraction_of_AIDC_only_upper_bound"] for r in objective),
            "B1_fraction_of_upper_bound_mean": float(np.mean([r["B1_fraction_of_AIDC_only_upper_bound"] for r in objective])),
            "B1_fraction_of_upper_bound_max": max(r["B1_fraction_of_AIDC_only_upper_bound"] for r in objective),
        },
        "facility_residual_decomposition": {"P_flexible_GPU_kWh": s4_flex_it_kwh, "P_nonflex_GPU_kWh": None, "P_CPU_host_kWh": None, "P_idle_base_kWh": None, "P_memory_storage_network_kWh": None, "P_unidentified_residual_kWh": residual_it_kwh, "status": "ONLY_FLEXIBLE_GPU_AND_COMBINED_RESIDUAL_IDENTIFIABLE"},
        "measurement_boundaries": {
            "Dataset312": "NVML per-GPU board power; Q50 incremental after 72.5 W/GPU idle subtraction; CPU/host absent",
            "Kestrel": "Slurm job/resource/timestamp telemetry; native U2 energy is null/zero and has no usable positive observations",
            "Eagle": "node iLO total-power plus V100-era scheduler/Ganglia telemetry exists, but V100-to-H100 absolute transfer and shared marginal response are not authorized",
            "ESIF": "whole-facility IT magnitude/PUE telemetry; no direct schedulability attribution to workload",
            "workload_dependent_host_power_authorized": False,
        },
        "hypotheses": hypotheses,
        "MESS_comparison": {"actual_B3_peak_abs_aggregate_active_power_kW": mess_peak_kw, "actual_B3_peak_abs_per_unit_active_power_kW": mess_per_unit_peak_kw, "AIDC_peak_individual_PCC_shift_kW": max(shift_peak.values()), "same_active_power_boundary_ratio": div(mess_peak_kw, max(shift_peak.values())), "nameplate_context": "4 x 700 kVA is apparent power and is not divided by kW without a supported power factor"},
        "inputs": inputs,
        "firewall_counters": {"scientific_solver_calls": 0, "OpenDSS_calls": 0, "ML_retraining_calls": 0, "beta_mutations": 0, "PUE_mutations": 0, "PF_mutations": 0, "final_scale_selection_calls": 0, "existing_V17_files_modified": 0},
    }

    review = {
        "artifact_id": "V17_AIDC_FLEXIBILITY_ROOT_CAUSE_FINAL_REVIEW_V1",
        "result_classification": "D. MULTI_FACTOR_ATTRITION",
        "classification_basis": "coverage-denominator mismatch, GPU-board-only electrical boundary, forecast-cohort policy with unquantified excluded cohorts, and partial actuation utilization all contribute; no single supported factor fully explains the funnel",
        "core_findings": {
            "semantic_modelable_GPU_hour_coverage": s1_gpuh / s0_gpuh,
            "facility_flexible_energy_share": s5["eta_flex_energy_IT"],
            "facility_flexible_peak_share": s5["eta_flex_peak_PCC"],
            "actual_peak_AIDC_PCC_shift_kW": max(shift_peak.values()),
            "actual_peak_shift_as_fraction_of_peak_total_PCC": max(shift_peak.values()) / s5["peak_total_PCC_kW"],
            "B1_upper_bound_realization_mean": root["objective_summary"]["B1_fraction_of_upper_bound_mean"],
        },
        "hypotheses": hypotheses,
        "counterfactual_reference": "V17_AIDC_FLEXIBILITY_COUNTERFACTUAL_DIAGNOSTIC_V1.json",
        "reviewer_safe_claim": "92.0945% is coverage within the semantic-flexible training GPU-hour subset; under frozen V4R1, the source-backed seven-day flexible component is GPU-board incremental power and is a small modeled fraction of whole-facility IT, while the optimized PCC shift is smaller still.",
        "forbidden_overclaim": "Do not generalize the modeled facility share to real data centers or claim that 92% of facility load is flexible.",
        "missing_authority": ["D-1 snapshots of already-running and queued/backlog GPU-hours with causal deadlines", "co-timed per-job or per-node host/CPU/memory/network incremental power", "source-backed workload attribution within whole-facility ESIF IT telemetry", "slot/deadline profile for any full-S1 counterfactual"],
        "firewall_counters": root["firewall_counters"],
    }

    write_json(OUT / "V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1.json", root)
    write_json(OUT / "V17_AIDC_FLEXIBILITY_COUNTERFACTUAL_DIAGNOSTIC_V1.json", counterfactuals)
    write_json(OUT / "V17_AIDC_FLEXIBILITY_ROOT_CAUSE_FINAL_REVIEW_V1.json", review)
    write_csv(OUT / "V17_AIDC_FLEXIBILITY_FUNNEL_TABLE_V1.csv", funnel_rows, ["stage", "quantity", "jobs", "GPU_hours", "energy_kWh", "retained_fraction", "attrition_fraction", "reason"])
    write_csv(OUT / "V17_AIDC_FACILITY_FLEXIBLE_SHARE_V1.csv", site_rows, ["date", "aidc_id", "optimized_case", "total_it_kwh", "total_pcc_kwh", "flex_it_kwh", "flex_pcc_kwh", "eta_flex_it", "eta_flex_pcc", "shifted_pcc_kwh", "positive_shifted_pcc_kwh", "negative_shifted_pcc_kwh_magnitude", "absolute_shifted_pcc_kwh", "net_shifted_pcc_kwh", "peak_abs_delta_it_kw", "peak_abs_delta_pcc_kw"])
    write_csv(OUT / "V17_AIDC_FLEXIBILITY_ATTRITION_BY_STAGE_V1.csv", attrition_rows, ["rank", "transition", "absolute_before", "absolute_after", "unit", "retained_fraction", "attrition_fraction", "causal_status", "reason"])

    md = f"""# V17 AIDC Flexibility Funnel Root-Cause Final Review V1

RESULT CLASSIFICATION: D. MULTI_FACTOR_ATTRITION

## 핵심 결론

92.0945%는 학습기간 semantic-flexible GPU-hour 중 V1+V4R1 U2_CLEAN 전력 지원범위의 비율이며 시설 전체 IT 전력 비율이 아니다. 7개 평가일의 source-backed flexible IT는 {s4_flex_it_kwh:.6f} kWh로 전체 IT {total_it_kwh:.6f} kWh의 {100*s5['eta_flex_energy_IT']:.6f}%이다. 이 성분만 D-1 스케줄러의 전기적 가동범위가 되고, 실제 최대 개별 AIDC PCC 이동은 {max(shift_peak.values()):.6f} kW였다. B1 목적함수 개선은 AIDC-only 상한의 평균 {100*root['objective_summary']['B1_fraction_of_upper_bound_mean']:.6f}%에 도달하므로 주된 설명은 optimizer 결함이 아니라 작은 authority-backed actuator와 그리드 민감도/제약이다.

## Reviewer-safe 경계

- Dataset312: NVML GPU-board incremental power만 유연 전력으로 인정한다.
- Kestrel: workload/resource telemetry이며 usable positive U2 host-energy가 없다.
- Eagle: node total-power는 있으나 V100→H100 절대 전력 전이와 shared marginal response가 승인되지 않았다.
- ESIF: whole-facility IT magnitude를 제공하지만 workload schedulability attribution은 없다.
- CPU/host/memory/storage/network의 workload-dependent 유연 전력은 현재 authority에서 식별할 수 없다.

## 핵심 수치

- 전체 IT 평균/피크: {s5['mean_total_IT_kW']:.6f} / {s5['peak_total_IT_kW']:.6f} kW
- 전체 PCC 평균/피크: {s5['mean_total_PCC_kW']:.6f} / {s5['peak_total_PCC_kW']:.6f} kW
- 유연 IT 평균/피크: {s4['average_flexible_IT_kW']:.6f} / {s4['peak_flexible_IT_kW']:.6f} kW
- 유연 PCC 평균/피크: {s4['average_flexible_PCC_kW']:.6f} / {s4['peak_flexible_PCC_kW']:.6f} kW
- B1/B3 실제 이동 PCC 에너지(L1/2): {s6['B1-B0']['shifted_pcc_kwh']:.6f} / {s6['B3-B2']['shifted_pcc_kwh']:.6f} kWh
- 최대 개별 AIDC PCC 이동: {max(shift_peak.values()):.6f} kW
- B3 MESS 실제 aggregate active-power peak / AIDC peak shift: {mess_peak_kw:.6f} kW / {max(shift_peak.values()):.6f} kW = {mess_peak_kw/max(shift_peak.values()):.6f}배

Counterfactual C0~C5는 모두 `NON_AUTHORITY_DIAGNOSTIC`이며 새 과학 권위나 scale 선택이 아니다.
"""
    (OUT / "V17_AIDC_FLEXIBILITY_ROOT_CAUSE_FINAL_REVIEW_V1.md").write_text(md, encoding="utf-8")

    readme = """# Provenance — V17 AIDC Flexibility Funnel Forensic V1

이 디렉터리는 기존 V4R1 authority/reference/schedule/result를 읽기만 하여 생성한 forensic 산출물이다. 과학 solver, OpenDSS, ML 재학습을 호출하지 않았고 beta/PUE/PF/scale을 변경하거나 선택하지 않았다.

정의: 15분 slot 적분은 kW × 0.25 h, flexible IT는 whole-GPU service GPU-hour × Dataset312 Q50 kW/GPU, PCC는 IT × frozen PUE 1.30이다. shifted energy는 reference 대비 delta의 L1/2이며 positive/negative/absolute/net도 별도 기록한다. `92.0945%`와 facility flexible share는 분모가 다르다. 평가일은 2025-04-02, 03, 12, 13, 15, 22, 23이다.

`V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1.json`의 `inputs`에 사용·검토한 모든 입력 경로와 SHA256이 기록되어 있다. CSV는 UTF-8 BOM이며 숫자 단위는 열 이름에 표시했다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    main()
