"""Build V23M prior-benchmark, novelty, and training-only recurrence audits."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dayahead.ml.c_mass_tpp.data import (
    AEST,
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    conflict_ids,
    expanding_blocked_folds,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"
V19 = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prior_benchmark_reproduction() -> dict[str, object]:
    comparison_path = V19 / "V19_MODEL_COMPARISON.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    authority = comparison["SCALE_INDEPENDENT_ML_AUTHORITY"]
    expected = {
        "B2_LIGHTGBM_TWEEDIE": {
            "daily_WAPE": 0.976108062962391,
            "burst_WAPE": 0.868229869598140,
            "aggregate_mass_ratio": 0.650508278376442,
        },
        "B3_LIGHTGBM_QUANTILE": {
            "daily_WAPE": 0.890250058481854,
            "burst_WAPE": 0.920623006401315,
            "aggregate_mass_ratio": 0.363702963012490,
        },
        "V19-A": {
            "daily_WAPE": 1.007605567971126,
            "burst_WAPE": 0.847146966830785,
            "aggregate_mass_ratio": 0.756275027307800,
        },
    }
    rows: list[dict[str, object]] = []
    passed = True
    for model, metrics in expected.items():
        seed_metrics = authority[model]["seed_metrics"]
        record = seed_metrics["deterministic"] if "deterministic" in seed_metrics else next(iter(seed_metrics.values()))
        for metric, target in metrics.items():
            # B2/B3 are deterministic serialized baselines.  V19-A's task
            # authority is the frozen three-seed mean, not seed 20260901.
            actual = float(
                authority[model][f"{metric}_mean"]
                if model == "V19-A"
                else record[metric]
            )
            error = abs(actual - target)
            ok = error <= 1e-9
            passed &= ok
            rows.append(
                {
                    "model": model,
                    "metric": metric,
                    "expected": target,
                    "serialized_actual": actual,
                    "absolute_error": error,
                    "tolerance": 1e-9,
                    "status": "PASS" if ok else "FAIL",
                }
            )
    payload = {
        "artifact_id": "V23M_PRIOR_BENCHMARK_REPRODUCTION_V1",
        "method": "READ_FROZEN_SERIALIZED_V19_AUTHORITY_WITHOUT_RETRAINING",
        "source": str(comparison_path.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha256(comparison_path),
        "results": rows,
        "status": "PASS" if passed else "FAIL_PRIOR_BENCHMARK_REPRODUCTION",
        "RACQ_training_authorized": passed,
    }
    write_json("V23M_PRIOR_BENCHMARK_REPRODUCTION.json", payload)
    if not passed:
        raise RuntimeError("FAIL_PRIOR_BENCHMARK_REPRODUCTION")
    return payload


QUERIES = [
    "recurrence aware workload forecasting GPU cluster",
    "recurrent job motif forecasting data center",
    "recurring innovation workload decomposition",
    "compound count payload workload forecasting",
    "queue consistent workload forecasting",
    "queue aware probabilistic workload prediction",
    "GPU workload extreme value forecasting",
    "temporal point process recurring innovation events",
    "hierarchical GPU workload power tier forecasting",
    "deadline aware probabilistic workload forecasting",
    "forecasting submitted and executed GPU workload",
    "mass coherent queue workload power forecasting",
    "AI data center job arrival forecasting",
    "data center workload recurrence motif",
    "compound hurdle extreme value time series forecasting",
]


PRIOR_WORK = [
    {
        "paper_model": "Deep Renewal Processes",
        "year": 2019,
        "url": "https://arxiv.org/abs/1911.10416",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": True,
        "payload_size_model": True,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Intermittent arrival/size renewal model; no identity motif memory, queue layer, or workload-to-power bridge.",
    },
    {
        "paper_model": "DualTPP",
        "year": 2021,
        "url": "https://arxiv.org/abs/2101.02815",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": True,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": True,
        "power_mapping": False,
        "hard_coherent_mass_relation": True,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Long-horizon event/count consensus, but not recurring-vs-innovation compound GPU-h payload forecasting.",
    },
    {
        "paper_model": "EventFlow",
        "year": 2024,
        "url": "https://arxiv.org/abs/2410.07430",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": True,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Flow-matched joint event-time forecasts; no motif memory, payload tail, EDF queue, or power semantics.",
    },
    {
        "paper_model": "ADD-THIN",
        "year": 2023,
        "url": "https://openreview.net/forum?id=tn9Dldam9L",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": True,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Diffusion over whole point patterns; does not implement RACQ's workload semantics or queue/power layers.",
    },
    {
        "paper_model": "RMTPP",
        "year": 2016,
        "url": "https://doi.org/10.1145/2939672.2939875",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Next marked-event intensity model rather than coherent day-ahead GPU-h cohort distribution.",
    },
    {
        "paper_model": "SAHP",
        "year": 2020,
        "url": "https://proceedings.mlr.press/v119/zhang20q.html",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Self-attentive event intensity; no account motif recurrence split or physical queue/power outputs.",
    },
    {
        "paper_model": "Transformer Hawkes Process",
        "year": 2020,
        "url": "https://proceedings.mlr.press/v119/zuo20a.html",
        "irregular_event_history": True,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": False,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Transformer event intensity with long dependencies; no compound mass/tail/cohort/queue contract.",
    },
    {
        "paper_model": "Dirichlet Proportions Model",
        "year": 2023,
        "url": "https://proceedings.mlr.press/v216/das23b.html",
        "irregular_event_history": False,
        "recurring_event_memory": False,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": True,
        "extreme_tail_model": False,
        "queue_consistency": False,
        "power_mapping": False,
        "hard_coherent_mass_relation": True,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Top-down coherent proportions overlap with cohort allocation only; not a job-event/queue/power model.",
    },
    {
        "paper_model": "Prediction-Assisted GPU Scheduling (A-SRPT)",
        "year": 2025,
        "url": "https://arxiv.org/abs/2501.05563",
        "irregular_event_history": True,
        "recurring_event_memory": True,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": True,
        "extreme_tail_model": False,
        "queue_consistency": True,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Uses recurring DDL jobs to predict iterations for scheduling, not probabilistic future-arrival GPU-h mass and tail forecasts.",
    },
    {
        "paper_model": "Characterization and Prediction of DL Workloads",
        "year": 2021,
        "url": "https://arxiv.org/abs/2109.01313",
        "irregular_event_history": True,
        "recurring_event_memory": True,
        "recurring_innovation_decomposition": False,
        "count_model": False,
        "payload_size_model": True,
        "extreme_tail_model": False,
        "queue_consistency": True,
        "power_mapping": False,
        "hard_coherent_mass_relation": False,
        "grid_objective_used": False,
        "exact_overlap": False,
        "difference": "Per-job workload characterization/prediction for services; not a coherent probabilistic day-ahead workload-to-power forecaster.",
    },
]


def novelty_audit() -> dict[str, object]:
    fields = list(PRIOR_WORK[0].keys())
    with (OUT / "V23M_NEAREST_PRIOR_WORK_MATRIX.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(PRIOR_WORK)
    payload = {
        "artifact_id": "V23M_SYSTEMATIC_NOVELTY_AUDIT_V1",
        "search_date": "2026-09-01",
        "queries": QUERIES,
        "source_access": {
            "IEEE_Xplore": "SEARCH_RESULTS_ACCESSED",
            "ACM_Digital_Library": "SEARCH_RESULTS_AND_OPEN_PAPER_METADATA_ACCESSED",
            "ScienceDirect": "SEARCH_RESULTS_AND_ABSTRACTS_ACCESSED",
            "SpringerLink": "SEARCH_RESULTS_AND_ABSTRACTS_ACCESSED",
            "arXiv": "ACCESSED",
            "OpenReview": "ACCESSED",
            "NeurIPS": "ACCESSED",
            "ICML_PMLR": "ACCESSED",
            "ICLR": "SEARCH_RESULTS_ACCESSED",
            "KDD": "ACCESSED",
            "AAAI": "SEARCH_RESULTS_ACCESSED",
            "AISTATS_PMLR": "ACCESSED",
            "Web_of_Science": "NOT_ACCESSED_NO_AUTHENTICATED_CONNECTOR",
            "Scopus": "NOT_ACCESSED_NO_AUTHENTICATED_CONNECTOR",
        },
        "nearest_prior_works": PRIOR_WORK,
        "finding": (
            "Every major component has prior art, and A-SRPT/DL-workload studies explicitly exploit recurring GPU jobs. "
            "No accessed work combines causal account-level motif memory, recurring/innovation decomposition, hurdle count, "
            "lognormal-plus-GPD service payload, exactly coherent tier/latency mass, queue feasibility, and workload-to-power diagnostics."
        ),
        "novelty_gate": "PARTIAL_OVERLAP_BUT_DISTINCT_COMBINATION",
        "near_duplicate_found": False,
        "WORLD_FIRST": "NOT_YET",
        "MODEL_DEVELOPMENT_READY": True,
        "claim_limit": "DISTINCT_COMBINATION_SUBJECT_TO_EMPIRICAL_ABLATION; NO_WORLD_FIRST_CLAIM",
    }
    write_json("V23M_SYSTEMATIC_NOVELTY_AUDIT.json", payload)
    lines = [
        "# V23M RACQ-Flex systematic novelty audit",
        "",
        f"- Gate: `{payload['novelty_gate']}`",
        "- WORLD_FIRST: `NOT_YET`",
        "- Near-identical architecture found: `false`",
        "",
        "RACQ-Flex의 각 구성요소에는 명확한 선행연구가 있다. 특히 Deep Renewal은 발생/크기 분해, "
        "DualTPP는 장기 event/count 일관성, Dirichlet Proportions는 계층 질량 일관성, A-SRPT는 반복 GPU job 활용과 "
        "예측-스케줄 결합을 제공한다. 그러나 조사한 원문 범위에서는 이 요소들을 Kestrel의 인과적 motif 기억, "
        "recurring/innovation 분해, 극단 꼬리, EDF queue, IT-power 의미론과 한 모델 계약으로 결합한 사례는 찾지 못했다.",
        "",
        "따라서 허용되는 주장은 '부분 중복이 있으나 결합이 구별된다'까지이며, world-first 주장은 보류한다.",
    ]
    (OUT / "V23M_SYSTEMATIC_NOVELTY_AUDIT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload


def gini(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values >= 0)]
    if len(values) == 0 or values.sum() == 0:
        return 0.0
    ordered = np.sort(values)
    n = len(ordered)
    return float((2 * np.dot(np.arange(1, n + 1), ordered) / (n * ordered.sum())) - (n + 1) / n)


def account_stability(events: pd.DataFrame, targets: pd.DataFrame) -> dict[str, object]:
    data = events.loc[
        events["submit_AEST"].ge(pd.Timestamp(TRAIN_START, tz=AEST))
        & events["submit_AEST"].lt(pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST))
    ].copy()
    data["month"] = data["submit_AEST"].dt.strftime("%Y-%m")
    month_accounts = {
        month: set(frame["account_hash"].dropna().astype(str))
        for month, frame in data.groupby("month", sort=True)
    }
    months = sorted(month_accounts)
    overlap = []
    for left, right in zip(months, months[1:]):
        a, b = month_accounts[left], month_accounts[right]
        overlap.append(
            {
                "left_month": left,
                "right_month": right,
                "intersection": len(a & b),
                "jaccard": len(a & b) / max(1, len(a | b)),
                "right_survival_from_left": len(a & b) / max(1, len(a)),
            }
        )
    survival = data.groupby("account_hash")["month"].nunique()
    target_by_account = targets.groupby("account_hash")["service_GPU_h"].agg(["count", "sum"])
    median_jaccard = float(np.median([row["jaccard"] for row in overlap]))
    stable = median_jaccard >= 0.25 and float((survival >= 2).mean()) >= 0.25
    payload = {
        "artifact_id": "V23M_ACCOUNT_HASH_STABILITY_AUDIT_V1",
        "monthly_unique_accounts": {month: len(accounts) for month, accounts in month_accounts.items()},
        "adjacent_month_overlap": overlap,
        "median_adjacent_month_jaccard": median_jaccard,
        "multi_month_account_survival": {
            "accounts": int(len(survival)),
            "fraction_seen_2plus_months": float((survival >= 2).mean()),
            "fraction_seen_4plus_months": float((survival >= 4).mean()),
            "max_months": int(survival.max()),
        },
        "target_account_event_count_distribution": target_by_account["count"].describe().to_dict(),
        "target_account_GPU_h_distribution": target_by_account["sum"].describe().to_dict(),
        "hash_reset_change_evidence": (
            "NO_MONTH_BOUNDARY_COLLAPSE_DETECTED" if stable else "POSSIBLE_MONTHLY_REANONYMIZATION"
        ),
        "status": "PASS" if stable else "FAIL",
    }
    write_json("V23M_ACCOUNT_HASH_STABILITY_AUDIT.json", payload)
    return payload


def add_recurrence_labels(targets: pd.DataFrame) -> pd.DataFrame:
    jobs = targets.copy().sort_values(["submit_AEST", "id"]).reset_index(drop=True)
    jobs["strict_motif"] = list(
        zip(jobs.account_hash.astype(str), jobs.partition.astype(str), jobs.qos.astype(str), jobs.tier, jobs.latency)
    )
    jobs["family_motif"] = list(
        zip(jobs.account_hash.astype(str), jobs.partition.astype(str), jobs.tier, jobs.latency)
    )
    labels: list[str] = []
    strict_last: dict[tuple[object, ...], list[pd.Timestamp]] = defaultdict(list)
    family_last: dict[tuple[object, ...], list[pd.Timestamp]] = defaultdict(list)
    for row in jobs.itertuples(index=False):
        cutoff = pd.Timestamp(row.target_day, tz=AEST) - pd.Timedelta(hours=6)
        lower = cutoff - pd.Timedelta(days=28)
        strict_seen = any(lower <= time < cutoff for time in strict_last[row.strict_motif])
        family_seen = any(lower <= time < cutoff for time in family_last[row.family_motif])
        if strict_seen:
            labels.append("STRICT_RECURRENT")
        elif family_seen:
            labels.append("FAMILY_RECURRENT")
        else:
            labels.append("INNOVATION")
        strict_last[row.strict_motif].append(row.submit_AEST)
        family_last[row.family_motif].append(row.submit_AEST)
    jobs["recurrence_class"] = labels
    return jobs


def occurrence_rows(jobs: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(TRAIN_START)
    end = pd.Timestamp(TRAIN_END_EXCLUSIVE)
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    grouped = {(day, int(hour)): frame for (day, hour), frame in jobs.groupby(["target_day", jobs.submit_AEST.dt.hour])}
    history_daily = jobs.groupby("target_day").agg(events=("id", "count"), mass=("service_GPU_h", "sum"))
    records = []
    for day in days:
        day_key = day.date().isoformat()
        cutoff = pd.Timestamp(day_key, tz=AEST) - pd.Timedelta(hours=6)
        past = jobs.loc[jobs.submit_AEST.lt(cutoff) & jobs.submit_AEST.ge(cutoff - pd.Timedelta(days=28))]
        prior_days = [
            (day - pd.Timedelta(days=k)).date().isoformat() for k in range(1, 29)
        ]
        prior = history_daily.reindex(prior_days).fillna(0.0)
        for hour in range(24):
            current = grouped.get((day_key, hour), jobs.iloc[0:0])
            recurring = current.loc[current.recurrence_class.ne("INNOVATION")]
            past_hour = past.loc[past.submit_AEST.dt.hour.eq(hour)]
            past_same_dow_hour = past_hour.loc[past_hour.submit_AEST.dt.dayofweek.eq(day.dayofweek)]
            ages_h = (cutoff - past_hour.submit_AEST).dt.total_seconds().to_numpy(float) / 3600.0
            decay = np.exp(-np.maximum(ages_h, 0.0) / 168.0)
            records.append(
                {
                    "date": day_key,
                    "hour": hour,
                    "dow": day.dayofweek,
                    "target": int(len(recurring) > 0),
                    "target_GPU_h": float(recurring.service_GPU_h.sum()),
                    "target_total_GPU_h": float(current.service_GPU_h.sum()),
                    "hist_events_1d": float(prior.events.iloc[0]),
                    "hist_events_7d": float(prior.events.iloc[:7].sum()),
                    "hist_mass_7d": float(prior.mass.iloc[:7].sum()),
                    "hist_mass_28d": float(prior.mass.sum()),
                    "motif_hour_events_28d": float(len(past_hour)),
                    "motif_hour_recurring_28d": float(past_hour.recurrence_class.ne("INNOVATION").sum()),
                    "motif_hour_mass_28d": float(past_hour.service_GPU_h.sum()),
                    "motif_same_dow_hour_events_28d": float(len(past_same_dow_hour)),
                    "motif_same_dow_hour_mass_28d": float(past_same_dow_hour.service_GPU_h.sum()),
                    "motif_hour_unique_strict_28d": float(past_hour.strict_motif.nunique()),
                    "motif_hour_unique_family_28d": float(past_hour.family_motif.nunique()),
                    "motif_hour_decay_score_28d": float(decay.sum()),
                    "motif_hour_decay_mass_28d": float(np.dot(decay, past_hour.service_GPU_h.to_numpy(float))) if len(past_hour) else 0.0,
                    "active_strict_motifs_28d": float(past.strict_motif.nunique()),
                    "active_family_motifs_28d": float(past.family_motif.nunique()),
                }
            )
    frame = pd.DataFrame(records)
    frame["hour_sin"] = np.sin(2 * np.pi * frame.hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame.hour / 24)
    frame["dow_sin"] = np.sin(2 * np.pi * frame.dow / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * frame.dow / 7)
    return frame


FEATURES = {
    "R0_CALENDAR": ["hour_sin", "hour_cos", "dow_sin", "dow_cos"],
    "R1_CALENDAR_AGGREGATE": [
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "hist_events_1d", "hist_events_7d", "hist_mass_7d", "hist_mass_28d"
    ],
    "R2_CALENDAR_AGGREGATE_MOTIF": [
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "hist_events_1d", "hist_events_7d", "hist_mass_7d", "hist_mass_28d",
        "motif_hour_events_28d", "motif_hour_recurring_28d", "motif_hour_mass_28d",
        "motif_same_dow_hour_events_28d", "motif_same_dow_hour_mass_28d",
        "motif_hour_unique_strict_28d", "motif_hour_unique_family_28d",
        "motif_hour_decay_score_28d", "motif_hour_decay_mass_28d",
        "active_strict_motifs_28d", "active_family_motifs_28d"
    ],
}


def fitted_probabilities(train: pd.DataFrame, valid: pd.DataFrame, features: list[str]) -> np.ndarray:
    if train.target.nunique() < 2:
        return np.full(len(valid), float(train.target.mean()))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, random_state=20260901),
    )
    model.fit(
        train[features],
        train.target,
        logisticregression__sample_weight=np.maximum(train.target_GPU_h.to_numpy(float), 1.0),
    )
    return np.clip(model.predict_proba(valid[features])[:, 1], 1e-6, 1 - 1e-6)


def recurrence_predictive_audit(jobs: pd.DataFrame) -> tuple[list[dict[str, object]], dict[str, object]]:
    hourly = occurrence_rows(jobs)
    rows: list[dict[str, object]] = []
    bootstrap_parts = []
    for fold in expanding_blocked_folds():
        train = hourly.loc[(hourly.date >= fold.train_start) & (hourly.date <= fold.train_end)]
        valid = hourly.loc[(hourly.date >= fold.validation_start) & (hourly.date <= fold.validation_end)].copy()
        predictions = {}
        for name, features in FEATURES.items():
            probs = fitted_probabilities(train, valid, features)
            predictions[name] = probs
            weight = np.maximum(valid.target_GPU_h.to_numpy(float), 1.0)
            weighted_brier = float(np.average((probs - valid.target.to_numpy(float)) ** 2, weights=weight))
            y = valid.target.to_numpy(int)
            rows.append(
                {
                    "fold_id": fold.fold_id,
                    "model": name,
                    "log_loss": float(log_loss(y, probs, labels=[0, 1])),
                    "brier_score": float(brier_score_loss(y, probs)),
                    "AUROC": float(roc_auc_score(y, probs)) if len(np.unique(y)) > 1 else None,
                    "average_precision": float(average_precision_score(y, probs)) if y.sum() else None,
                    "GPU_h_weighted_brier": weighted_brier,
                    "mean_predicted_probability": float(probs.mean()),
                    "observed_frequency": float(y.mean()),
                }
            )
        valid["r1_sq"] = (predictions["R1_CALENDAR_AGGREGATE"] - valid.target.to_numpy(float)) ** 2
        valid["r2_sq"] = (predictions["R2_CALENDAR_AGGREGATE_MOTIF"] - valid.target.to_numpy(float)) ** 2
        valid["weight"] = np.maximum(valid.target_GPU_h.to_numpy(float), 1.0)
        bootstrap_parts.append(valid[["date", "r1_sq", "r2_sq", "weight"]])
    all_valid = pd.concat(bootstrap_parts, ignore_index=True)
    daily = all_valid.groupby("date").apply(
        lambda g: pd.Series(
            {
                "r1": np.average(g.r1_sq, weights=g.weight),
                "r2": np.average(g.r2_sq, weights=g.weight),
                "weight": g.weight.sum(),
            }
        ), include_groups=False
    ).reset_index()
    rng = np.random.default_rng(20260901)
    dates = daily.date.to_numpy()
    improvements = []
    block = 7
    for _ in range(2000):
        sampled = []
        while len(sampled) < len(dates):
            start = int(rng.integers(0, max(1, len(dates) - block + 1)))
            sampled.extend(range(start, min(start + block, len(dates))))
        sample = daily.iloc[np.asarray(sampled[: len(dates)])]
        r1 = float(np.average(sample.r1, weights=sample.weight))
        r2 = float(np.average(sample.r2, weights=sample.weight))
        improvements.append((r1 - r2) / max(r1, 1e-12))
    by_model = {(int(row["fold_id"]), str(row["model"])): row for row in rows}
    fold_lifts = []
    for fold in expanding_blocked_folds():
        r1 = float(by_model[(fold.fold_id, "R1_CALENDAR_AGGREGATE")]["GPU_h_weighted_brier"])
        r2 = float(by_model[(fold.fold_id, "R2_CALENDAR_AGGREGATE_MOTIF")]["GPU_h_weighted_brier"])
        fold_lifts.append((r1 - r2) / max(r1, 1e-12))
    payload = {
        "artifact_id": "V23M_RECURRENCE_PREDICTIVE_LIFT_V1",
        "models": FEATURES,
        "fold_metrics": rows,
        "R2_vs_R1_GPU_h_weighted_brier_relative_improvement_by_fold": fold_lifts,
        "median_fold_relative_improvement": float(np.median(fold_lifts)),
        "seven_day_block_bootstrap": {
            "replicates": 2000,
            "seed": 20260901,
            "relative_improvement_mean": float(np.mean(improvements)),
            "CI95": [float(np.quantile(improvements, 0.025)), float(np.quantile(improvements, 0.975))],
            "supports_improvement_direction": bool(np.quantile(improvements, 0.025) > 0),
        },
    }
    write_json("V23M_RECURRENCE_PREDICTIVE_LIFT.json", payload)
    return rows, payload


def recurrence_audit(events: pd.DataFrame, targets: pd.DataFrame) -> dict[str, object]:
    stability = account_stability(events, targets)
    jobs = add_recurrence_labels(targets)
    fold_rows = []
    for fold in expanding_blocked_folds():
        part = jobs.loc[(jobs.target_day >= fold.validation_start) & (jobs.target_day <= fold.validation_end)]
        total_mass = float(part.service_GPU_h.sum())
        row: dict[str, object] = {"fold_id": fold.fold_id, "validation_start": fold.validation_start, "validation_end": fold.validation_end, "events": len(part), "GPU_h": total_mass}
        for label, prefix in (("STRICT_RECURRENT", "strict"), ("FAMILY_RECURRENT", "family"), ("INNOVATION", "innovation")):
            selected = part.loc[part.recurrence_class.eq(label)]
            row[f"{prefix}_event_fraction"] = len(selected) / max(1, len(part))
            row[f"{prefix}_GPU_h_fraction"] = float(selected.service_GPU_h.sum()) / max(total_mass, 1e-12)
        row["recurring_GPU_h_fraction"] = row["strict_GPU_h_fraction"] + row["family_GPU_h_fraction"]
        fold_rows.append(row)
    with (OUT / "V23M_RECURRENCE_BY_FOLD.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fold_rows[0]))
        writer.writeheader()
        writer.writerows(fold_rows)
    _, lift = recurrence_predictive_audit(jobs)
    recurring = jobs.loc[jobs.recurrence_class.ne("INNOVATION")]
    interarrival = recurring.groupby("strict_motif").submit_AEST.diff().dt.total_seconds().dropna() / 3600.0
    class_mass = jobs.groupby("recurrence_class").service_GPU_h.agg(["count", "sum", "median", "max"])
    median_share = float(np.median([float(row["recurring_GPU_h_fraction"]) for row in fold_rows]))
    gate = (
        median_share >= 0.20
        and float(lift["median_fold_relative_improvement"]) >= 0.02
        and bool(lift["seven_day_block_bootstrap"]["supports_improvement_direction"])
        and stability["status"] == "PASS"
    )
    audit = {
        "artifact_id": "V23M_RECURRENCE_SIGNAL_AUDIT_V1",
        "training_period": {"start": TRAIN_START, "end_inclusive": "2025-03-31"},
        "timezone": str(AEST),
        "global_conflict_jobs_excluded": len(conflict_ids()),
        "target_jobs": len(jobs),
        "strict_definition": ["account_hash", "partition", "qos", "power_tier", "latency_class"],
        "family_definition": ["account_hash", "partition", "power_tier", "latency_class"],
        "lookback_days": 28,
        "overall_class_statistics": class_mass.reset_index().to_dict(orient="records"),
        "interarrival_hours": interarrival.describe().to_dict(),
        "recurrence_by_weekday": jobs.assign(weekday=jobs.submit_AEST.dt.dayofweek).groupby(["weekday", "recurrence_class"]).service_GPU_h.sum().unstack(fill_value=0).to_dict(),
        "recurrence_by_hour": jobs.assign(hour=jobs.submit_AEST.dt.hour).groupby(["hour", "recurrence_class"]).service_GPU_h.sum().unstack(fill_value=0).to_dict(),
        "recurrence_by_power_tier": jobs.groupby(["tier", "recurrence_class"]).service_GPU_h.sum().unstack(fill_value=0).to_dict(),
        "recurrence_by_latency_class": jobs.groupby(["latency", "recurrence_class"]).service_GPU_h.sum().unstack(fill_value=0).to_dict(),
        "recurrence_concentration_gini_by_account_GPU_h": gini(recurring.groupby("account_hash").service_GPU_h.sum().to_numpy()),
        "recurring_tail_GPU_h": recurring.service_GPU_h.quantile([0.5, 0.9, 0.95, 0.99, 1.0]).to_dict(),
        "innovation_tail_GPU_h": jobs.loc[jobs.recurrence_class.eq("INNOVATION"), "service_GPU_h"].quantile([0.5, 0.9, 0.95, 0.99, 1.0]).to_dict(),
        "median_fold_recurring_GPU_h_share": median_share,
        "gate_components": {
            "median_share_ge_20pct": median_share >= 0.20,
            "R2_weighted_brier_improvement_ge_2pct": float(lift["median_fold_relative_improvement"]) >= 0.02,
            "bootstrap_supports_improvement": bool(lift["seven_day_block_bootstrap"]["supports_improvement_direction"]),
            "account_hash_stability_PASS": stability["status"] == "PASS",
        },
        "RACQ_RECURRENCE_GATE_PASS": gate,
        "fallback_if_fail": "ACQ_FLEX_WITHOUT_RECURRENCE_BRANCH",
    }
    write_json("V23M_RECURRENCE_SIGNAL_AUDIT.json", audit)
    freeze = {
        "artifact_id": "V23M_RECURRENCE_RULE_FREEZE_V1",
        "frozen_before_RACQ_training": True,
        "strict_motif": audit["strict_definition"],
        "family_motif": audit["family_definition"],
        "lookback_days": 28,
        "classification_order": ["STRICT_RECURRENT", "FAMILY_RECURRENT", "INNOVATION"],
        "cutoff": "D-1 18:00 AEST",
        "future_target_fields_used_for_feature_construction": 0,
        "RACQ_RECURRENCE_GATE_PASS": gate,
    }
    write_json("V23M_RECURRENCE_RULE_FREEZE.json", freeze)
    return audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prior_benchmark_reproduction()
    novelty_audit()
    frame, source = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(frame)
    targets = semantic_flexible_targets(frame, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids())
    recurrence = recurrence_audit(events, targets)
    write_json(
        "V23M_AUDIT_EXECUTION_SUMMARY.json",
        {
            "artifact_id": "V23M_AUDIT_EXECUTION_SUMMARY_V1",
            "source": source,
            "source_valid_H100_input_events": len(events),
            "semantic_flexible_targets": len(targets),
            "novelty_gate": "PARTIAL_OVERLAP_BUT_DISTINCT_COMBINATION",
            "recurrence_gate": recurrence["RACQ_RECURRENCE_GATE_PASS"],
            "April_target_reads": 0,
            "RACQ_training_calls": 0,
        },
    )
    print(json.dumps({"targets": len(targets), "recurrence_gate": recurrence["RACQ_RECURRENCE_GATE_PASS"]}))


if __name__ == "__main__":
    main()
