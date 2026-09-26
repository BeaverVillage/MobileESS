"""Causal event-triggered Q repair with frozen physical P and SOC execution."""
from dataclasses import dataclass

import numpy as np

REVISION = "Q_ONLY_EVENT_TRIGGERED_MINIMAL_REPAIR_V3_20260920"
TOL = 1e-9
IMPROVEMENT_TOL = 1e-6
DEVIATION_TOL = 1e-9
EVENT_RHO_PU = 0.02
EVENT_VMIN_PU = 0.005
EVENT_VMAX_PU = 0.005


@dataclass(frozen=True)
class Limits:
    pmax: float
    smax: float
    emin: float
    emax: float
    eta_c: float
    eta_d: float
    dt: float
    faces: int = 16


def energy_next(e, p, a):
    return e + a.eta_c * np.maximum(-p, 0) * a.dt - np.maximum(p, 0) * a.dt / a.eta_d


def q_bounds(p, connected, a):
    assert np.all(np.abs(p) <= a.pmax + 1e-8)
    assert np.all(np.abs(p) <= a.smax + 1e-8)
    headroom = np.sqrt(np.maximum(0.0, a.smax * a.smax - p * p))
    return np.where(connected, -headroom, 0.0), np.where(connected, headroom, 0.0)


def ac_feasible(r):
    if not r["converged"] or not r.get("settled", True):
        return False
    v = np.asarray(r["v"])
    current = np.asarray(r["ipu"] if "ipu" in r else r["line"])
    tx = np.asarray(r.get("tx", []))
    kva = np.asarray(r["kva"])
    return bool(
        np.all(np.isfinite(v))
        and np.min(v) >= 0.95 - TOL
        and np.max(v) <= 1.05 + TOL
        and np.max(current) <= 1 + TOL
        and (tx.size == 0 or np.max(tx) <= 1 + TOL)
        and np.max(kva[np.isfinite(kva)], initial=0) <= 1 + TOL
    )


def line_rho(r):
    if "line_rho" in r:
        return float(r["line_rho"])
    return float(np.max(r["line"] if "line" in r else r["ipu"]))


def state_values(r):
    return dict(rho=line_rho(r), vmin=float(np.min(r["v"])), vmax=float(np.max(r["v"])))


def deviation(state, da):
    # Fixed, dimensionless L1 distance, normalized by the event thresholds.
    return (abs(state["rho"] - da["rho"]) / EVENT_RHO_PU
            + abs(state["vmin"] - da["vmin"]) / EVENT_VMIN_PU
            + abs(state["vmax"] - da["vmax"]) / EVENT_VMAX_PU)


class Controller:
    def __init__(self, limits, initial_energy, q_corrector=None):
        self.a = limits
        self.energy = np.asarray(initial_energy, dtype=float)
        self.slot = 0
        self.q_corrector = q_corrector

    def step(self, *, slot, p_da, q_da, connected, travel_energy, evaluate,
             da_exact, allow_correct=True):
        assert slot == self.slot, "NONCAUSAL_OR_OUT_OF_ORDER_SLOT"
        a = self.a
        p = np.asarray(p_da, dtype=float).copy()
        q_da = np.asarray(q_da, dtype=float)
        connected = np.asarray(connected, dtype=bool)
        travel = np.asarray(travel_energy, dtype=float)
        assert p.shape == q_da.shape == connected.shape == travel.shape == self.energy.shape
        if np.any((~connected) & (np.abs(p) > 1e-9)):
            raise RuntimeError("FROZEN_P_DISCONNECTED")
        if np.any((~connected) & (np.abs(q_da) > 1e-9)):
            raise RuntimeError("FROZEN_Q_DISCONNECTED")
        lo, hi = q_bounds(p, connected, a)
        capable = bool(np.all(q_da >= lo - 1e-8) and np.all(q_da <= hi + 1e-8))
        before = self.energy.copy()
        available = before - travel
        after = energy_next(available, p, a)
        if (np.any(available < a.emin - 1e-7) or np.any(after < a.emin - 1e-7)
                or np.any(after > a.emax + 1e-7)):
            raise RuntimeError("FROZEN_P_ENERGY_BOUND_FAILURE")

        da = {key: float(da_exact[key]) for key in ("rho", "vmin", "vmax")}
        baseline = evaluate(p, q_da)
        base = state_values(baseline)
        base_pass = ac_feasible(baseline) and capable
        base_dev = deviation(base, da)
        material = (abs(base["rho"] - da["rho"]) >= EVENT_RHO_PU
                    or abs(base["vmin"] - da["vmin"]) >= EVENT_VMIN_PU
                    or abs(base["vmax"] - da["vmax"]) >= EVENT_VMAX_PU)
        trigger = "AC_FAIL" if not base_pass else "MATERIAL_DA_DEVIATION" if material else "NONE"
        trials = 1
        chosen = None
        candidates = []
        seen = {q_da.tobytes()}

        def try_q(value):
            nonlocal trials
            value = np.clip(np.asarray(value, dtype=float), lo, hi)
            key = value.tobytes()
            if key in seen:
                return
            seen.add(key)
            result = evaluate(p, value)
            trials += 1
            if not ac_feasible(result):
                return
            state = state_values(result)
            dev = deviation(state, da)
            delta = float(np.abs(value - q_da).sum())
            item = (delta, dev, state["rho"], value.copy(), result)
            candidates.append(item)
            return item

        if allow_correct and trigger != "NONE":
            # Screen small Q steps first. Stop at the first magnitude with an
            # acceptable repair; no current-slot rho minimization.
            scale = a.smax / 800.0
            radii = ((1, 2, 4, 8, 16) if trigger == "MATERIAL_DA_DEVIATION"
                     else (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 800))
            promising_directions = None
            for radius in radii:
                count_before = len(candidates)
                first_radius_directions = set()
                for j in np.flatnonzero(connected):
                    for sign in (-1., 1.):
                        if (trigger == "MATERIAL_DA_DEVIATION" and promising_directions is not None
                                and (j, sign) not in promising_directions):
                            continue
                        trial = q_da.copy()
                        trial[j] += sign * radius * scale
                        item = try_q(trial)
                        if (trigger == "MATERIAL_DA_DEVIATION" and radius == 1 and item is not None
                                and item[2] < base["rho"] - IMPROVEMENT_TOL):
                            first_radius_directions.add((j, sign))
                new = candidates[count_before:]
                if trigger == "MATERIAL_DA_DEVIATION":
                    preferred = [c for c in new if c[2] < base["rho"] - IMPROVEMENT_TOL
                                 and c[1] < base_dev - DEVIATION_TOL]
                else:
                    preferred = [c for c in new if c[1] < base_dev - DEVIATION_TOL]
                if preferred:
                    chosen = min(preferred, key=lambda c: (c[0], c[1], c[2]))
                    break
                if trigger == "MATERIAL_DA_DEVIATION" and radius == 1:
                    promising_directions = first_radius_directions
                    if not promising_directions:
                        break

            if trigger == "AC_FAIL" and chosen is None and self.q_corrector is not None:
                # Inherited IEEE123 Q safety search is a fallback for difficult
                # AC failures. Stop after 16 feasible exact trials.
                class SufficientFeasibleSamples(Exception):
                    pass

                def safety_evaluate(value):
                    nonlocal trials
                    value = np.asarray(value, dtype=float).copy()
                    result = evaluate(p, value)
                    trials += 1
                    if ac_feasible(result):
                        state = state_values(result)
                        candidates.append((float(np.abs(value - q_da).sum()), deviation(state, da),
                                           state["rho"], value.copy(), result))
                        if len(candidates) >= 16:
                            raise SufficientFeasibleSamples
                    return result

                try:
                    self.q_corrector(safety_evaluate, np.clip(q_da, lo, hi), lo, hi, q_da=q_da)
                except SufficientFeasibleSamples:
                    pass

            if trigger == "AC_FAIL" and chosen is None and candidates:
                preferred = [c for c in candidates if c[1] < base_dev - DEVIATION_TOL]
                chosen = (min(preferred, key=lambda c: (c[0], c[1], c[2])) if preferred
                          else min(candidates, key=lambda c: (c[1], c[0], c[2])))

        if chosen is not None:
            _, expected_dev, expected_rho, q, _ = chosen
            result = evaluate(p, q)
            trials += 1
            if (not ac_feasible(result) or abs(line_rho(result) - expected_rho) > 1e-9
                    or abs(deviation(state_values(result), da) - expected_dev) > 1e-9):
                raise RuntimeError("SELECTED_Q_EXACT_REVALIDATION_MISMATCH")
            status = "Q_RESTORED" if trigger == "AC_FAIL" else "Q_MATERIAL_REPAIRED"
        else:
            q, result = q_da.copy(), baseline
            status = "UNCHANGED" if base_pass else "Q_ONLY_UNRESOLVED"
        assert np.array_equal(p, p_da), "P_DA_DRIFT"
        if chosen is not None:
            assert np.all(np.hypot(p, q) <= a.smax + 1e-7)
        self.energy = after
        self.slot += 1
        accepted = state_values(result)
        event = dict(
            slot=slot, status=status, trigger=trigger, event_triggered=bool(allow_correct and trigger != "NONE"),
            exact_trials=trials, baseline_AC_PASS=base_pass, AC_PASS=ac_feasible(result),
            DA_exact=da, baseline_rho=base["rho"], accepted_rho=accepted["rho"],
            baseline_Vmin=base["vmin"], baseline_Vmax=base["vmax"],
            accepted_Vmin=accepted["vmin"], accepted_Vmax=accepted["vmax"],
            baseline_deviation=base_dev, accepted_deviation=deviation(accepted, da),
            P_EXEC=p.tolist(), Q_DA=q_da.tolist(), Q_EXEC=q.tolist(),
            corrective_delta_P=np.zeros_like(p).tolist(), recovery_P=np.zeros_like(p).tolist(),
            energy_before_kwh=before.tolist(), travel_energy_kwh=travel.tolist(),
            energy_after_kwh=after.tolist(), energy_deviation_kwh=np.zeros_like(p).tolist(),
            P_intervention=False, Q_intervention=bool(np.max(np.abs(q - q_da)) > 1e-6),
            max_abs_delta_Q=float(np.max(np.abs(q - q_da))),
            current_actual_slot_exposed=slot, future_actual_rows_exposed=0,
            global_optimality_claimed=False,
        )
        return p, q, result, event
