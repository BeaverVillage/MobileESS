from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


@dataclass
class CalibrationResult:
    probabilities: pd.DataFrame
    hazard_wide: pd.DataFrame
    maps: dict
    audit: pd.DataFrame
    summary: dict


def _horizon(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"_h(\d+)$")[0].astype(int)


def _ece(y, p, bins=10):
    y = np.asarray(y, int)
    p = np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges, right=True) - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)


def _safe_metrics(y, p, score, bins):
    eps = 1e-8
    y = np.asarray(y, int)
    p = np.asarray(p, float)
    score = np.asarray(score, float)
    pc = np.clip(p, eps, 1 - eps)
    out = {
        "n": len(y),
        "positive_rate": float(np.mean(y)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, pc, labels=[0, 1])),
        "ece": _ece(y, p, bins),
    }
    out["pr_auc"] = float(average_precision_score(y, score)) if len(np.unique(y)) > 1 else np.nan
    out["roc_auc"] = float(roc_auc_score(y, score)) if len(np.unique(y)) > 1 else np.nan
    return out


def _transform(score, cfg):
    s = np.asarray(score, float)
    if cfg.get("score_transform", "log1p") == "log1p":
        s = np.log1p(np.maximum(s, 0))
    return s


def _hour_bin(hours, bins):
    h = np.asarray(hours, int)
    out = np.empty(len(h), dtype=object)
    for i in range(len(bins) - 1):
        m = (h >= bins[i]) & (h < bins[i + 1])
        out[m] = f"{bins[i]:02d}-{bins[i+1]:02d}"
    return out


def _calendar_keys(timestamps, cfg):
    ts = pd.to_datetime(pd.Series(timestamps), utc=True)
    local = ts.dt.tz_convert(cfg["analysis"]["local_timezone"])
    bins = list(map(int, cfg["scenarios"]["representative_hour_bins"]))
    hb = _hour_bin(local.dt.hour.to_numpy(), bins)
    weekend = (local.dt.dayofweek.to_numpy() >= 5).astype(int)
    return np.array([f"{w}|{b}" for w, b in zip(weekend, hb)], dtype=object)


def _constant_map(y, score_t):
    return {
        "kind": "constant",
        "prevalence": float(np.mean(y)),
        "x_min": float(np.min(score_t)),
        "x_max": float(np.max(score_t)),
    }


def _fit_candidate(kind, score, y, timestamps, cfg):
    y = np.asarray(y, int)
    st = _transform(score, cfg)
    prevalence = float(np.mean(y))
    pos = int(y.sum())
    uniq = np.unique(st).size
    if kind == "constant":
        return _constant_map(y, st)
    # Calendar calibration is independent of the ML score values.  In the
    # final pre-2025 refit we intentionally pass a zero score vector, so the
    # generic unique-score guard must not collapse a calendar winner to a
    # constant map.  It only needs enough positive events to estimate the
    # smoothed calendar strata.
    if kind == "calendar":
        if pos < int(cfg["minimum_positive_samples"]):
            m = _constant_map(y, st)
            m["fallback_reason"] = "insufficient_positive_samples_for_calendar"
            return m
        keys = _calendar_keys(timestamps, cfg)
        alpha = float(cfg.get("calendar_prior_strength", 100.0))
        rates = {}
        for key in sorted(np.unique(keys)):
            mask = keys == key
            rates[str(key)] = float((y[mask].sum() + alpha * prevalence) / (mask.sum() + alpha))
        return {
            "kind": "calendar",
            "global_prevalence": prevalence,
            "rates": rates,
            "x_min": float(st.min()),
            "x_max": float(st.max()),
        }
    if pos < int(cfg["minimum_positive_samples"]) or uniq < int(cfg["minimum_unique_scores"]):
        m = _constant_map(y, st)
        m["fallback_reason"] = "insufficient_positive_or_unique_samples"
        return m
    if kind == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1, increasing=True)
        iso.fit(st, y)
        return {
            "kind": "isotonic",
            "x": iso.X_thresholds_.astype(float).tolist(),
            "y": iso.y_thresholds_.astype(float).tolist(),
            "x_min": float(st.min()),
            "x_max": float(st.max()),
        }
    if kind == "platt":
        model = LogisticRegression(C=float(cfg.get("platt_c", 1.0)), solver="lbfgs", max_iter=1000)
        model.fit(st.reshape(-1, 1), y)
        return {
            "kind": "platt",
            "coef": float(model.coef_[0, 0]),
            "intercept": float(model.intercept_[0]),
            "x_min": float(st.min()),
            "x_max": float(st.max()),
        }
    if kind == "binned_isotonic":
        q = int(cfg.get("binned_quantiles", 8))
        edges = np.unique(np.quantile(st, np.linspace(0, 1, q + 1)))
        if len(edges) < 3:
            return _constant_map(y, st)
        idx = np.clip(np.digitize(st, edges[1:-1], right=True), 0, len(edges) - 2)
        centers, rates, counts = [], [], []
        alpha = float(cfg.get("binned_prior_strength", 50.0))
        for b in range(len(edges) - 1):
            m = idx == b
            if not m.any():
                continue
            centers.append(float(np.mean(st[m])))
            counts.append(int(m.sum()))
            rates.append(float((y[m].sum() + alpha * prevalence) / (m.sum() + alpha)))
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1, increasing=True)
        fitted = iso.fit_transform(np.asarray(centers), np.asarray(rates), sample_weight=np.asarray(counts))
        return {
            "kind": "binned_isotonic",
            "x": np.asarray(centers, float).tolist(),
            "y": np.asarray(fitted, float).tolist(),
            "x_min": float(st.min()),
            "x_max": float(st.max()),
            "bin_count": len(centers),
        }
    raise ValueError(f"Unknown calibration candidate: {kind}")


def _apply_map(score, timestamps, m, cfg):
    st = _transform(score, cfg)
    kind = m["kind"]
    if kind == "constant":
        p = np.full(len(st), float(m["prevalence"]))
    elif kind in {"isotonic", "binned_isotonic"}:
        p = np.interp(
            st,
            np.asarray(m["x"], float),
            np.asarray(m["y"], float),
            left=float(m["y"][0]),
            right=float(m["y"][-1]),
        )
    elif kind == "platt":
        z = float(m["coef"]) * st + float(m["intercept"])
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))
    elif kind == "calendar":
        keys = _calendar_keys(timestamps, cfg)
        p = np.array([float(m["rates"].get(str(k), m["global_prevalence"])) for k in keys])
    else:
        raise ValueError(f"Unsupported map kind: {kind}")
    lo, hi = map(float, cfg["probability_clip"])
    return np.clip(p, lo, hi), st


def _build_hazard(prob: pd.DataFrame, horizons: list[int], max_steps: int):
    wide = (
        prob.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability_calibrated")
        .reindex(columns=horizons)
        .sort_index()
    )
    p = wide.to_numpy(float)
    lam_knots = -np.log1p(-np.clip(p, 0, 1 - 1e-12))
    knots = [0] + horizons
    full = np.zeros((len(wide), max_steps + 1), dtype=np.float64)
    for seg in range(len(horizons)):
        a, b = knots[seg], knots[seg + 1]
        va = np.zeros(len(wide)) if seg == 0 else lam_knots[:, seg - 1]
        vb = lam_knots[:, seg]
        for k in range(a + 1, b + 1):
            full[:, k] = va + (vb - va) * (k - a) / (b - a)
    hazard = np.maximum(np.diff(full, axis=1), 0)
    out = pd.DataFrame({"timestamp_utc": wide.index})
    for k in range(1, max_steps + 1):
        out[f"lambda_step_{k:02d}"] = hazard[:, k - 1].astype(np.float32)
    return out


def _load_development_calendar_frame(k5a, target_columns):
    path = k5a / "outputs/kestrel_ml_development_2024.parquet"
    if not path.exists():
        return None
    try:
        dev = pd.read_parquet(path, columns=["timestamp_utc", *target_columns])
    except Exception:
        return None
    dev["timestamp_utc"] = pd.to_datetime(dev.timestamp_utc, utc=True)
    return dev


def calibrate(k5b3, k5a, cfg):
    oof = pd.read_parquet(k5b3 / "predictions/validation_oof_dl.parquet")
    test = pd.read_parquet(k5b3 / "predictions/test_2025_frozen_dl.parquet")
    for x in [oof, test]:
        x["timestamp_utc"] = pd.to_datetime(x.timestamp_utc, utc=True)
    oof = oof[oof.task.astype(str).eq("flexible")].copy()
    test = test[test.task.astype(str).eq("flexible")].copy()
    oof["horizon_steps"] = _horizon(oof.target_column)
    test["horizon_steps"] = _horizon(test.target_column)
    horizons = list(map(int, cfg["analysis"]["horizons_steps"]))
    calcfg = cfg["calibration"]
    candidates = list(calcfg.get("candidates", ["constant", "platt", "binned_isotonic", "isotonic", "calendar"]))
    maps, audit, frames, cross_frames = {}, [], [], []
    target_by_h = {h: oof.loc[oof.horizon_steps.eq(h), "target_column"].iloc[0] for h in horizons}
    dev_calendar = _load_development_calendar_frame(k5a, [target_by_h[h] for h in horizons])

    for h in horizons:
        g = oof[oof.horizon_steps.eq(h)].copy().sort_values("timestamp_utc").reset_index(drop=True)
        y = (g.actual.to_numpy(float) > 0).astype(int)
        score = g.dl_prediction.to_numpy(float)
        if "fold_id" not in g:
            g["fold_id"] = g.timestamp_utc.dt.strftime("%Y-%m")
        pred_by_candidate = {c: np.full(len(g), np.nan, dtype=float) for c in candidates}
        for fold in sorted(g.fold_id.astype(str).unique()):
            va = g.fold_id.astype(str).eq(fold).to_numpy()
            tr = ~va
            for c in candidates:
                m = _fit_candidate(c, score[tr], y[tr], g.loc[tr, "timestamp_utc"], {**calcfg, **{"analysis": cfg["analysis"], "scenarios": cfg["scenarios"]}})
                pred_by_candidate[c][va] = _apply_map(score[va], g.loc[va, "timestamp_utc"], m, {**calcfg, **{"analysis": cfg["analysis"], "scenarios": cfg["scenarios"]}})[0]
        candidate_metrics = []
        for c in candidates:
            met = _safe_metrics(y, pred_by_candidate[c], score, int(calcfg["ece_bins"]))
            candidate_metrics.append((c, met))
        constant_brier = next(m["brier"] for c, m in candidate_metrics if c == "constant")
        best_name, best_met = min(candidate_metrics, key=lambda cm: (cm[1]["brier"], cm[1]["log_loss"]))
        min_gain = float(calcfg.get("minimum_brier_improvement_vs_prevalence", 0.0))
        if constant_brier - best_met["brier"] < min_gain - 1e-12:
            best_name = "constant"
            best_met = next(m for c, m in candidate_metrics if c == "constant")
        for c, met in candidate_metrics:
            audit.append({
                "horizon_steps": h,
                "evaluation": "leave_one_fold_out",
                "candidate": c,
                "selected_final_mapping": best_name,
                **met,
                "constant_baseline_brier": constant_brier,
                "brier_improvement_vs_constant": constant_brier - met["brier"],
            })
            cross_frames.append(pd.DataFrame({
                "timestamp_utc": g.timestamp_utc,
                "fold_id": g.fold_id,
                "horizon_steps": h,
                "candidate": c,
                "actual_event": y,
                "expected_score": score,
                "cross_calibrated_probability": pred_by_candidate[c],
                "selected_candidate": best_name,
            }))

        if best_name == "calendar" and dev_calendar is not None:
            target = target_by_h[h]
            final_y = (dev_calendar[target].to_numpy(float) > 0).astype(int)
            final_map = _fit_candidate(
                "calendar",
                np.zeros(len(dev_calendar), dtype=float),
                final_y,
                dev_calendar.timestamp_utc,
                {**calcfg, **{"analysis": cfg["analysis"], "scenarios": cfg["scenarios"]}},
            )
            oof_st = _transform(score, calcfg)
            final_map["x_min"] = float(oof_st.min())
            final_map["x_max"] = float(oof_st.max())
            final_map["final_fit_source"] = "K5-A full pre-2025 development targets"
        else:
            final_map = _fit_candidate(
                best_name,
                score,
                y,
                g.timestamp_utc,
                {**calcfg, **{"analysis": cfg["analysis"], "scenarios": cfg["scenarios"]}},
            )
            final_map["final_fit_source"] = "K5-B3 rolling OOF rows"
        final_map["selected_by_temporal_cross_validation"] = best_name
        final_map["effective_final_mapping"] = final_map["kind"]
        final_map["cross_validated_brier"] = float(best_met["brier"])
        final_map["constant_baseline_brier"] = float(constant_brier)
        maps[str(h)] = final_map

        t = test[test.horizon_steps.eq(h)].copy().sort_values("timestamp_utc")
        tscores = t.dl_ensemble_prediction.to_numpy(float)
        p, st = _apply_map(
            tscores,
            t.timestamp_utc,
            final_map,
            {**calcfg, **{"analysis": cfg["analysis"], "scenarios": cfg["scenarios"]}},
        )
        frames.append(pd.DataFrame({
            "timestamp_utc": t.timestamp_utc,
            "horizon_steps": h,
            "target_column": t.target_column,
            "expected_gpu_hours_score": tscores,
            "selected_calibration_candidate_cv": best_name,
            "effective_calibration_mapping": final_map["kind"],
            "event_probability_calibrated_pre_monotone": p,
            "score_transformed": st,
            "score_below_oof_range": st < float(final_map["x_min"]),
            "score_above_oof_range": st > float(final_map["x_max"]),
        }))

    prob = pd.concat(frames, ignore_index=True).sort_values(["timestamp_utc", "horizon_steps"])
    pwide = prob.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability_calibrated_pre_monotone").reindex(columns=horizons)
    pwide.columns.name = "horizon_steps"
    raw = pwide.to_numpy(float)
    previol = float((np.diff(raw, axis=1) < -1e-12).mean())
    post = np.maximum.accumulate(raw, axis=1)
    postmat = pd.DataFrame(post, index=pwide.index, columns=horizons)
    postmat.columns.name = "horizon_steps"
    postdf = postmat.stack().rename("event_probability_calibrated").reset_index()
    prob = prob.merge(postdf, on=["timestamp_utc", "horizon_steps"], how="left")
    hazard = _build_hazard(prob, horizons, int(cfg["analysis"]["trajectory_steps"]))
    hz = hazard.filter(like="lambda_step_").to_numpy(float)
    cum = np.cumsum(hz, axis=1)
    pp = prob.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability_calibrated").reindex(columns=horizons)
    rec = [np.max(np.abs((1 - np.exp(-cum[:, h - 1])) - pp[h].to_numpy(float))) for h in horizons]
    selected_cv = {str(h): maps[str(h)]["selected_by_temporal_cross_validation"] for h in horizons}
    effective = {str(h): maps[str(h)]["kind"] for h in horizons}
    variability = {str(h): float(pp[h].std()) for h in horizons}
    dynamic_horizons = sum(
        effective[str(h)] != "constant" and variability[str(h)] > 1e-10
        for h in horizons
    )
    summary = {
        "source": "K5-B3 leakage-free rolling OOF expected-demand score plus pre-2025 calendar fallback candidate",
        "calibration_method": "per-horizon temporal-CV selection among constant, Platt, binned isotonic, isotonic, and calendar calibration",
        "temporal_evaluation": "leave-one-validation-fold-out",
        "final_mapping_fit": "all 2024 rolling OOF rows; calendar winner refit on K5-A full pre-2025 development targets",
        "analysis_year_application": "2025 frozen ensemble score/calendar covariates",
        "cross_validated_selection_by_horizon": selected_cv,
        "selected_mapping_by_horizon": effective,
        "dynamic_horizon_count": int(dynamic_horizons),
        "probability_std_by_horizon": variability,
        "pre_monotonicity_violation_fraction": previol,
        "postprocess": "cumulative_max across horizons",
        "hazard_max_knot_recovery_error": float(max(rec)),
        "test_score_outside_oof_range_fraction": float((prob.score_below_oof_range | prob.score_above_oof_range).mean()),
        "strict_constant_fallback_horizons": [int(h) for h in horizons if effective[str(h)] == "constant"],
        "calendar_rate_count_by_horizon": {
            str(h): len(maps[str(h)].get("rates", {})) for h in horizons
        },
    }
    return CalibrationResult(prob.reset_index(drop=True), hazard, maps, pd.DataFrame(audit), summary), pd.concat(cross_frames, ignore_index=True)
