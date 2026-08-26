"""Run the PFR B0-B7 matrix or an isolated B8 timing baseline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from functools import lru_cache
import hashlib
import importlib
import itertools
import json
import os
from pathlib import Path
import pickle
import shutil
import statistics
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from pfr.daily import DailyInitializationError, certify_daily_pre_identity
from pfr.electrical_stress import OBJECTIVE_AUTHORITY
from pfr.git_identity import run_git
from pfr.methods import (
    ComparisonMethod,
    ElectricalStressMethod,
    FACTORIAL_ELECTRICAL_STRESS_CELLS,
    ExperimentAuthority,
    MethodFactory,
)
from pfr.migration import MigrationAuthority, load_migration_authority
from pfr.mobility_execution import Stage25fSumoExecutionAuthority
from pfr.mobility_physics import MobilityPhysics
from pfr.native_predictive import (
    PREDICTIVE_NATIVE_HORIZON_STEPS,
    PredictivePathScore,
    capacitor_switch_count,
    intermediate_capacitor_states,
)
from pfr.optimization import GurobiFastControlOptimizer, gurobi_thread_limit
from pfr.power import H100UtilizationPowerCurve
from pfr.provenance import scientific_implementation_fingerprint
from pfr.risk_calibration import (
    ELECTRICAL_STRESS_AUTHORITY_ID,
    load_frozen_risk_calibration,
)
from pfr.persistent_bounded_milp import (
    ADAPTER_ID as ONLINE_MILP_ADAPTER_ID,
    SOLVER_CONTRACT as ONLINE_MILP_SOLVER_CONTRACT,
    PersistentBoundedMilpPlanner,
)
from pfr.retained_h54 import ADAPTER_ID, RetainedH54JointPlanner
from pfr.runtime import (
    CausalExperimentFrame,
    MobilityRouteForecast,
    OperationalTrainingJob,
    PLANNING_HORIZON_STEPS,
    PhysicalCommit,
    PfrRuntimeRunner,
    RuntimeInitialState,
    MutableMethodState,
    NativeGridControlDecision,
)
from pfr.safety import ExactAcResult


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_source_identity(repo: Path) -> Mapping[str, Any]:
    def git(*args: str) -> str:
        return run_git(repo, args)

    full_commit = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    dirty = bool(git("status", "--porcelain"))
    if len(full_commit) != 40:
        raise RuntimeError("scientific source commit is not a full Git SHA")
    return {
        "git_full_commit_sha": full_commit,
        "git_branch": branch,
        "git_worktree_dirty": dirty,
    }


def sha256_files(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        resolved = path.resolve()
        encoded_name = resolved.name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(bytes.fromhex(sha256(resolved)))
    return digest.hexdigest()


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_exact_module(repo: Path, exact_package_root: Path):
    science = repo / "science"
    support = exact_package_root.resolve()
    if not (support / "opendss_metrics_common.py").is_file():
        raise RuntimeError("exact package lacks opendss_metrics_common.py")
    sys.path.insert(0, str(support))
    sys.path.insert(0, str(science))
    return importlib.import_module("EXACT_GRID_RUNNER_24SERVICE")


class ExactOpenDssBackend:
    def __init__(self, exact: Any, paths: Mapping[str, str]) -> None:
        self.exact = exact
        self.paths = dict(paths)

    @staticmethod
    def _state(
        *,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
    ) -> dict[str, Any]:
        return {
            "facility_p_kw": list(facility_p_kw),
            "facility_q_kvar": list(facility_q_kvar),
            "mess_location_service_id": list(mess_location),
            "mess_p_kw": list(mess_p_kw),
            "mess_q_kvar": list(mess_q_kvar),
            "mess_parked": [not value for value in mess_in_transit],
            "mess_plugged": [not value for value in mess_in_transit],
            "mess_grid_connected": [not value for value in mess_in_transit],
            "mess_in_transit": list(mess_in_transit),
        }

    def select_native_control(
        self,
        *,
        issue: int,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
        previous_capacitor_states: Mapping[str, Sequence[int]],
        previous_regulator_taps: Mapping[str, int],
        locked_capacitors: Sequence[str],
        native_forecast_background_p_kw: Sequence[
            Sequence[Sequence[float]]
        ] = (),
        native_forecast_background_q_kvar: Sequence[
            Sequence[Sequence[float]]
        ] = (),
        native_forecast_pv_available_kw: Sequence[
            Sequence[Sequence[float]]
        ] = (),
        deep_search: bool = False,
    ) -> NativeGridControlDecision:
        state = self._state(
            facility_p_kw=facility_p_kw,
            facility_q_kvar=facility_q_kvar,
            mess_location=mess_location,
            mess_p_kw=mess_p_kw,
            mess_q_kvar=mess_q_kvar,
            mess_in_transit=mess_in_transit,
        )
        state.update(
            {
                "native_grid_control_mode": "EVALUATE_TRANSITION",
                "native_capacitor_initial_states": {
                    str(name).lower(): list(values)
                    for name, values in previous_capacitor_states.items()
                },
                "native_capacitor_locked": [
                    str(name).lower() for name in locked_capacitors
                ],
                "native_regulator_initial_tap_numbers": {
                    str(name).lower(): int(value)
                    for name, value in previous_regulator_taps.items()
                },
            }
        )
        raw = self.exact.solve_step(self.paths, issue, state)
        transition_states = {
            str(name).lower(): tuple(int(value) for value in values)
            for name, values in raw.get("native_capacitor_states", {}).items()
        }
        previous_states = {
            str(name).lower(): tuple(int(value) for value in values)
            for name, values in previous_capacitor_states.items()
        }
        transition_taps = {
            str(name).lower(): int(round(float(value)))
            for name, value in raw.get("native_regulator_tap_numbers", {}).items()
        }
        previous_taps = {
            str(name).lower(): int(value)
            for name, value in previous_regulator_taps.items()
        }
        locked = {str(name).lower() for name in locked_capacitors}

        # OpenDSS CapControl objects use local measurements.  The January failure
        # evidence showed that their local decisions can leave a different
        # bus/phase just above the feeder-wide hard limit.  When that happens,
        # coordinate the *existing* one-step capacitor assets against the exact
        # feeder envelope.  This is a common feeder controller, not a B-method
        # optimization variable: every arm runs the same deterministic law and
        # method-disabled MESS/compute controls remain untouched.
        candidate_evidence: list[dict[str, Any]] = []

        def metrics(candidate_raw: Mapping[str, Any]) -> dict[str, float | bool]:
            transformer = max(
                float(candidate_raw["transformer_max_kva_loading_pu"]),
                float(candidate_raw["transformer_max_current_loading_pu"]),
            )
            return {
                "hard_constraint_pass": bool(candidate_raw["hard_constraint_pass"]),
                "voltage_min_pu": float(candidate_raw["voltage_min_pu"]),
                "voltage_max_pu": float(candidate_raw["voltage_max_pu"]),
                "line_max_loading_pu": float(candidate_raw["line_max_loading_pu"]),
                "transformer_max_loading_pu": transformer,
            }

        def violation_score(candidate_metrics: Mapping[str, float | bool]) -> float:
            # Normalize voltage residuals by the 0.05-pu admissible span so the
            # selector compares voltage and thermal violations dimensionlessly.
            residuals = (
                max(0.0, (0.95 - float(candidate_metrics["voltage_min_pu"])) / 0.05),
                max(0.0, (float(candidate_metrics["voltage_max_pu"]) - 1.05) / 0.05),
                max(0.0, float(candidate_metrics["line_max_loading_pu"]) - 1.0),
                max(0.0, float(candidate_metrics["transformer_max_loading_pu"]) - 1.0),
            )
            return sum(value * value for value in residuals)

        def guard_score(candidate_metrics: Mapping[str, float | bool]) -> float:
            residuals = (
                max(0.0, (0.955 - float(candidate_metrics["voltage_min_pu"])) / 0.005),
                max(0.0, (float(candidate_metrics["voltage_max_pu"]) - 1.045) / 0.005),
                max(0.0, (float(candidate_metrics["line_max_loading_pu"]) - 0.995) / 0.005),
                max(0.0, (float(candidate_metrics["transformer_max_loading_pu"]) - 0.995) / 0.005),
            )
            return sum(value * value for value in residuals)

        transition_metrics = metrics(raw)
        predictive_guard_evidence: dict[str, Any] = {
            "status": "NOT_TRIGGERED_NO_LOCAL_CAPACITOR_TRANSITION",
            "authority": "PREDICTIVE_NATIVE_DWELL_GUARD_V1",
            "future_actual_used": False,
            "horizon_steps": PREDICTIVE_NATIVE_HORIZON_STEPS,
            "candidate_count": 0,
        }
        native_forecasts = (
            native_forecast_background_p_kw,
            native_forecast_background_q_kvar,
            native_forecast_pv_available_kw,
        )
        if any(native_forecasts) and not all(native_forecasts):
            raise RuntimeError(
                "predictive native forecast requires background P/Q and PV"
            )
        if any(native_forecasts) and any(
            len(values) != PREDICTIVE_NATIVE_HORIZON_STEPS
            for values in native_forecasts
        ):
            raise RuntimeError("predictive native forecast horizon must be 12 steps")
        if (
            not deep_search
            and bool(transition_metrics["hard_constraint_pass"])
            and transition_states != previous_states
            and all(native_forecasts)
        ):
            candidate_rows = []
            capacitor_candidates = intermediate_capacitor_states(
                previous_states,
                transition_states,
                tuple(locked),
            )
            all_capacitor_names = tuple(sorted(previous_states))
            for candidate_states in capacitor_candidates:
                is_local_transition = candidate_states == transition_states
                if is_local_transition:
                    current_raw = raw
                    current_metrics = transition_metrics
                    current_taps = dict(transition_taps)
                else:
                    current_state = dict(state)
                    current_state.update(
                        {
                            "native_grid_control_mode": "EVALUATE_TRANSITION",
                            "native_capacitor_initial_states": {
                                name: list(values)
                                for name, values in candidate_states.items()
                            },
                            "native_capacitor_locked": list(all_capacitor_names),
                            "native_regulator_initial_tap_numbers": previous_taps,
                        }
                    )
                    current_raw = self.exact.solve_step(
                        self.paths, issue, current_state
                    )
                    current_metrics = metrics(current_raw)
                    current_taps = {
                        str(name).lower(): int(round(float(value)))
                        for name, value in current_raw.get(
                            "native_regulator_tap_numbers", previous_taps
                        ).items()
                    }
                if not bool(current_metrics["hard_constraint_pass"]):
                    candidate_rows.append(
                        {
                            "states": {
                                name: list(values)
                                for name, values in sorted(candidate_states.items())
                            },
                            "current_h0_hard_pass": False,
                            "is_local_transition": is_local_transition,
                        }
                    )
                    continue

                forecast_metrics = []
                forecast_taps = dict(current_taps)
                for lead, (background_p, background_q, pv_available) in enumerate(
                    zip(*native_forecasts), start=1
                ):
                    forecast_state = dict(state)
                    forecast_state.update(
                        {
                            "background_p_kw": background_p,
                            "background_q_kvar": background_q,
                            "pv_available_kw": pv_available,
                            "native_grid_control_mode": "EVALUATE_TRANSITION",
                            "native_capacitor_initial_states": {
                                name: list(values)
                                for name, values in candidate_states.items()
                            },
                            "native_capacitor_locked": list(all_capacitor_names),
                            "native_regulator_initial_tap_numbers": forecast_taps,
                        }
                    )
                    forecast_raw = self.exact.solve_step(
                        self.paths, issue, forecast_state
                    )
                    observed_states = {
                        str(name).lower(): tuple(int(value) for value in values)
                        for name, values in forecast_raw.get(
                            "native_capacitor_states", {}
                        ).items()
                    }
                    if observed_states and observed_states != candidate_states:
                        raise RuntimeError(
                            "predictive forecast changed a locked capacitor state"
                        )
                    forecast_taps = {
                        str(name).lower(): int(round(float(value)))
                        for name, value in forecast_raw.get(
                            "native_regulator_tap_numbers", forecast_taps
                        ).items()
                    }
                    row_metrics = metrics(forecast_raw)
                    forecast_metrics.append(row_metrics)
                score = PredictivePathScore.from_metrics(forecast_metrics)
                tap_movement = sum(
                    abs(int(value) - int(previous_taps.get(name, value)))
                    for name, value in current_taps.items()
                )
                candidate_rows.append(
                    {
                        "states": {
                            name: list(values)
                            for name, values in sorted(candidate_states.items())
                        },
                        "current_h0_hard_pass": True,
                        "is_local_transition": is_local_transition,
                        "current_taps": dict(sorted(current_taps.items())),
                        "forecast_violation_steps": score.violation_steps,
                        "forecast_maximum_violation_score": score.maximum_violation,
                        "forecast_cumulative_violation_score": (
                            score.cumulative_violation
                        ),
                        "forecast_minimum_voltage_pu": min(
                            float(row["voltage_min_pu"])
                            for row in forecast_metrics
                        ),
                        "forecast_maximum_voltage_pu": max(
                            float(row["voltage_max_pu"])
                            for row in forecast_metrics
                        ),
                        "forecast_maximum_line_loading_pu": max(
                            float(row["line_max_loading_pu"])
                            for row in forecast_metrics
                        ),
                        "forecast_maximum_transformer_loading_pu": max(
                            float(row["transformer_max_loading_pu"])
                            for row in forecast_metrics
                        ),
                        "capacitor_switch_count": capacitor_switch_count(
                            previous_states, candidate_states
                        ),
                        "regulator_tap_movement": tap_movement,
                        "_selection": (
                            score.rank(),
                            0 if is_local_transition else 1,
                            capacitor_switch_count(
                                previous_states, candidate_states
                            ),
                            tap_movement,
                            tuple(
                                candidate_states[name]
                                for name in sorted(candidate_states)
                            ),
                            tuple(
                                current_taps[name] for name in sorted(current_taps)
                            ),
                        ),
                        "_current_raw": current_raw,
                        "_current_metrics": current_metrics,
                        "_current_taps": current_taps,
                        "_states": candidate_states,
                    }
                )
            selectable = [
                row for row in candidate_rows if row.get("current_h0_hard_pass")
            ]
            if not selectable:
                raise RuntimeError(
                    "local transition passed but no predictive h0 candidate passed"
                )
            selected_predictive = min(
                selectable, key=lambda row: row["_selection"]
            )
            transition_states = dict(selected_predictive["_states"])
            transition_taps = dict(selected_predictive["_current_taps"])
            raw = selected_predictive["_current_raw"]
            transition_metrics = selected_predictive["_current_metrics"]
            predictive_guard_evidence = {
                "status": (
                    "LOCAL_TRANSITION_RETAINED"
                    if selected_predictive["is_local_transition"]
                    else "PREDICTIVE_DWELL_GUARD_OVERRIDE"
                ),
                "authority": "PREDICTIVE_NATIVE_DWELL_GUARD_V1",
                "future_actual_used": False,
                "forecast_quantiles": {
                    "background_p": "q90_gross",
                    "background_q": "q90",
                    "pv_available": "q10",
                },
                "horizon_steps": PREDICTIVE_NATIVE_HORIZON_STEPS,
                "candidate_count": len(candidate_rows),
                "selected_states": {
                    name: list(values)
                    for name, values in sorted(transition_states.items())
                },
                "candidates": [
                    {
                        key: value
                        for key, value in row.items()
                        if not key.startswith("_")
                    }
                    for row in candidate_rows
                ],
            }
        elif transition_states == previous_states:
            predictive_guard_evidence["status"] = (
                "NOT_TRIGGERED_NO_LOCAL_CAPACITOR_TRANSITION"
            )
        elif not all(native_forecasts):
            predictive_guard_evidence["status"] = (
                "NOT_TRIGGERED_NO_CAUSAL_HORIZON_FORECAST"
            )
        elif deep_search:
            predictive_guard_evidence["status"] = (
                "NOT_TRIGGERED_DEEP_CURRENT_STATE_FALLBACK"
            )
        else:
            predictive_guard_evidence["status"] = (
                "NOT_TRIGGERED_LOCAL_TRANSITION_H0_UNSAFE"
            )
        beam_width = int(os.environ.get("PFR_NATIVE_GUARD_BEAM_WIDTH", "2"))
        maximum_tap_depth = int(
            os.environ.get("PFR_NATIVE_GUARD_MAX_TAP_DEPTH", "2")
        )
        if beam_width < 1 or maximum_tap_depth < 1:
            raise RuntimeError(
                "native guard beam width and tap depth must both be positive"
            )
        deep_trust_region_radius = 8
        deep_maximum_relinearizations = 4
        candidates: list[
            tuple[
                Mapping[str, tuple[int, ...]],
                Mapping[str, int],
                Mapping[str, Any],
                Mapping[str, float | bool],
            ]
        ] = [
            (transition_states, transition_taps, raw, transition_metrics)
        ]
        if not bool(transition_metrics["hard_constraint_pass"]):
            names = tuple(sorted(transition_states))
            mutable_names = tuple(name for name in names if name not in locked)
            fixed = {
                name: previous_states.get(name, transition_states[name])
                for name in names
                if name in locked
            }
            capacitor_hypotheses = []
            for bits in itertools.product((0, 1), repeat=len(mutable_names)):
                candidate_states = dict(fixed)
                candidate_states.update(
                    {name: (int(bit),) for name, bit in zip(mutable_names, bits)}
                )
                capacitor_hypotheses.append(candidate_states)

            # RegControl may move several independent taps in one OpenDSS
            # transition.  Searching only around that resulting tap vector can
            # exclude the chronological pre-transition state even though it is
            # the closest safe restoration anchor.  Evaluate every admissible
            # capacitor hypothesis at both physical anchors before expanding
            # one-tap neighbors.
            tap_anchors = [transition_taps]
            if previous_taps and previous_taps != transition_taps:
                tap_anchors.append(previous_taps)
            for candidate_states in capacitor_hypotheses:
                for tap_anchor in tap_anchors:
                    if (
                        candidate_states == transition_states
                        and tap_anchor == transition_taps
                    ):
                        continue
                    candidate_state = dict(state)
                    candidate_state.update(
                        {
                            "native_grid_control_mode": "FIXED_STATE_VERIFICATION",
                            "native_capacitor_initial_states": {
                                name: list(values)
                                for name, values in candidate_states.items()
                            },
                            "native_capacitor_locked": [],
                            "native_regulator_initial_tap_numbers": tap_anchor,
                        }
                    )
                    candidate_raw = self.exact.solve_step(
                        self.paths, issue, candidate_state
                    )
                    candidates.append(
                        (
                            candidate_states,
                            tap_anchor,
                            candidate_raw,
                            metrics(candidate_raw),
                        )
                    )

            # The capacitor and regulator decisions are coupled: a capacitor
            # state that initially looks poor because of overvoltage can become
            # the only feasible state after several regulator moves, while the
            # locally best capacitor state can remain thermally infeasible.
            # Preserve several capacitor/tap hypotheses in a bounded global
            # beam and search their regulator neighbors jointly.  The two
            # anchors prevent a multi-tap local transition from excluding the
            # chronological restoration basin.  A deeper per-capacitor-state
            # reachability search belongs to the background-native scaling gate,
            # not this online controller: method-scoped continuous projection
            # must not wait for thousands of native-only states when active or
            # reactive recourse is the required actuator.
            # Every candidate is still solved Fresh with all discrete controls
            # disabled, and each edge changes one existing tap by one step.
            seen = {
                (
                    tuple(sorted(candidate_states.items())),
                    tuple(sorted(candidate_taps.items())),
                )
                for candidate_states, candidate_taps, _, _ in candidates
            }
            ranking = lambda item: (
                violation_score(item[3]),
                guard_score(item[3]),
                tuple(item[0][name] for name in sorted(item[0])),
                tuple(item[1][name] for name in sorted(item[1])),
            )

            def ranked_frontier(items):
                return sorted(items, key=ranking)[:beam_width]

            candidate_index = {
                (
                    tuple(sorted(candidate_states.items())),
                    tuple(sorted(candidate_taps.items())),
                ): item
                for item in candidates
                for candidate_states, candidate_taps, _, _ in (item,)
            }

            def evaluate_fixed(candidate_states, candidate_taps):
                identity = (
                    tuple(sorted(candidate_states.items())),
                    tuple(sorted(candidate_taps.items())),
                )
                if identity in candidate_index:
                    return candidate_index[identity]
                candidate_state = dict(state)
                candidate_state.update(
                    {
                        "native_grid_control_mode": "FIXED_STATE_VERIFICATION",
                        "native_capacitor_initial_states": {
                            name: list(values)
                            for name, values in candidate_states.items()
                        },
                        "native_capacitor_locked": [],
                        "native_regulator_initial_tap_numbers": candidate_taps,
                    }
                )
                candidate_raw = self.exact.solve_step(
                    self.paths, issue, candidate_state
                )
                item = (
                    candidate_states,
                    dict(candidate_taps),
                    candidate_raw,
                    metrics(candidate_raw),
                )
                seen.add(identity)
                candidate_index[identity] = item
                candidates.append(item)
                return item

            if not deep_search:
                frontier = ranked_frontier(candidates)
                for _ in range(maximum_tap_depth):
                    if any(item[3]["hard_constraint_pass"] for item in candidates):
                        break
                    neighbors = []
                    for base_states, base_taps, _, _ in frontier:
                        for regulator_name in sorted(base_taps):
                            for direction in (-1, 1):
                                next_value = int(base_taps[regulator_name]) + direction
                                if not -16 <= next_value <= 16:
                                    continue
                                candidate_taps = dict(base_taps)
                                candidate_taps[regulator_name] = next_value
                                identity = (
                                    tuple(sorted(base_states.items())),
                                    tuple(sorted(candidate_taps.items())),
                                )
                                if identity in seen:
                                    continue
                                neighbors.append(
                                    evaluate_fixed(base_states, candidate_taps)
                                )
                    if not neighbors:
                        break
                    frontier = ranked_frontier(neighbors)
            else:
                # Deep restoration is a bounded sequential linearization over
                # the seven existing integer regulator taps.  Each seed is the
                # better of the two physical anchors for one admissible
                # capacitor state.  Fresh exact +/- one-tap probes form a local
                # Jacobian; a small elastic integer QP proposes a coordinated
                # upstream/downstream tap vector.  Exact backtracking and
                # relinearization handle the nonsmooth min/max envelope.  This
                # preserves cascaded-regulator tradeoffs without enumerating
                # tens of thousands of one-tap paths.
                grouped = {}
                for item in candidates:
                    grouped.setdefault(tuple(sorted(item[0].items())), []).append(item)
                active = [
                    min(grouped[identity], key=ranking)
                    for identity in sorted(grouped)
                ]
                metric_names = (
                    "voltage_min_pu",
                    "voltage_max_pu",
                    "line_max_loading_pu",
                    "transformer_max_loading_pu",
                )
                for _ in range(deep_maximum_relinearizations):
                    if any(
                        item[3]["hard_constraint_pass"] for item in candidates
                    ):
                        break
                    next_active = []
                    for base_states, base_taps, _, base_metrics in active:
                        regulator_names = tuple(sorted(base_taps))
                        probes = {}
                        for regulator_name in regulator_names:
                            for direction in (-1, 1):
                                next_value = int(base_taps[regulator_name]) + direction
                                if not -16 <= next_value <= 16:
                                    continue
                                probe_taps = dict(base_taps)
                                probe_taps[regulator_name] = next_value
                                probes[(regulator_name, direction)] = evaluate_fixed(
                                    base_states, probe_taps
                                )
                        if not probes:
                            continue
                        try:
                            import gurobipy as gp
                            from gurobipy import GRB
                        except ImportError as exc:
                            raise RuntimeError(
                                "gurobipy is required by deep native restoration"
                            ) from exc
                        model = gp.Model("pfr_native_tap_restoration")
                        model.Params.OutputFlag = 0
                        model.Params.Threads = gurobi_thread_limit()
                        model.Params.Seed = 0
                        delta = {}
                        for regulator_name in regulator_names:
                            current = int(base_taps[regulator_name])
                            delta[regulator_name] = model.addVar(
                                lb=max(-deep_trust_region_radius, -16 - current),
                                ub=min(deep_trust_region_radius, 16 - current),
                                vtype=GRB.INTEGER,
                                name=f"delta[{regulator_name}]",
                            )
                        predicted = {}
                        for metric_name in metric_names:
                            expression = float(base_metrics[metric_name])
                            for regulator_name in regulator_names:
                                minus = probes.get((regulator_name, -1))
                                plus = probes.get((regulator_name, 1))
                                if minus is not None and plus is not None:
                                    slope = 0.5 * (
                                        float(plus[3][metric_name])
                                        - float(minus[3][metric_name])
                                    )
                                elif plus is not None:
                                    slope = (
                                        float(plus[3][metric_name])
                                        - float(base_metrics[metric_name])
                                    )
                                else:
                                    slope = (
                                        float(base_metrics[metric_name])
                                        - float(minus[3][metric_name])
                                    )
                                expression += slope * delta[regulator_name]
                            predicted[metric_name] = expression
                        residual = {
                            name: model.addVar(lb=0.0, name=f"residual[{name}]")
                            for name in metric_names
                        }
                        model.addConstr(
                            predicted["voltage_min_pu"]
                            + residual["voltage_min_pu"]
                            >= 0.95002
                        )
                        model.addConstr(
                            predicted["voltage_max_pu"]
                            - residual["voltage_max_pu"]
                            <= 1.04998
                        )
                        model.addConstr(
                            predicted["line_max_loading_pu"]
                            - residual["line_max_loading_pu"]
                            <= 0.99998
                        )
                        model.addConstr(
                            predicted["transformer_max_loading_pu"]
                            - residual["transformer_max_loading_pu"]
                            <= 0.99998
                        )
                        feasibility = (
                            (residual["voltage_min_pu"] / 0.05) ** 2
                            + (residual["voltage_max_pu"] / 0.05) ** 2
                            + residual["line_max_loading_pu"] ** 2
                            + residual["transformer_max_loading_pu"] ** 2
                        )
                        movement = gp.quicksum(
                            value * value for value in delta.values()
                        )
                        # Numerical feasibility has strict practical priority
                        # over tap movement.  A 0.001-pu transformer residual
                        # must never be cheaper than a coordinated two-tap
                        # correction merely because the residual is squared.
                        model.setObjective(
                            1.0e9 * feasibility + 1.0e-3 * movement,
                            GRB.MINIMIZE,
                        )
                        model.optimize()
                        if model.SolCount < 1:
                            model.dispose()
                            continue
                        proposed_delta = {
                            name: int(round(float(value.X)))
                            for name, value in delta.items()
                        }
                        model.dispose()
                        proposals = []
                        for numerator, denominator in ((1, 1), (1, 2), (1, 4), (1, 8)):
                            proposed_taps = {
                                name: int(
                                    max(
                                        -16,
                                        min(
                                            16,
                                            int(base_taps[name])
                                            + round(
                                                proposed_delta[name]
                                                * numerator
                                                / denominator
                                            ),
                                        ),
                                    )
                                )
                                for name in regulator_names
                            }
                            if proposed_taps == dict(base_taps):
                                continue
                            proposal = evaluate_fixed(base_states, proposed_taps)
                            if proposal not in proposals:
                                proposals.append(proposal)
                        if not proposals:
                            proposals = list(probes.values())
                        best = min(proposals, key=ranking)
                        if bool(best[3]["hard_constraint_pass"]):
                            next_active.append(best)
                            break
                        if violation_score(best[3]) < violation_score(base_metrics) - 1e-10:
                            next_active.append(best)
                    active = next_active
                    if not active:
                        break

        def switching_count(candidate_states: Mapping[str, tuple[int, ...]]) -> int:
            return sum(
                tuple(candidate_states[name])
                != tuple(previous_states.get(name, candidate_states[name]))
                for name in candidate_states
            )

        def tap_movement(candidate_taps: Mapping[str, int]) -> int:
            baseline = previous_taps or transition_taps
            return sum(
                abs(int(value) - int(baseline.get(name, value)))
                for name, value in candidate_taps.items()
            )

        combined_candidates = [(*item, (0.0, 0.0, 0.0)) for item in candidates]
        passing = [
            item for item in combined_candidates if item[3]["hard_constraint_pass"]
        ]
        pool = passing or combined_candidates
        selected_states, selected_taps, selected_raw, _, selected_pv_q = min(
            pool,
            key=lambda item: (
                guard_score(item[3]) if passing else violation_score(item[3]),
                sum(abs(value) for value in item[4]),
                switching_count(item[0]),
                tap_movement(item[1]),
                tuple(item[0][name] for name in sorted(item[0])),
                tuple(item[1][name] for name in sorted(item[1])),
            ),
        )
        for candidate_states, candidate_taps, _, candidate_metrics in candidates:
            candidate_evidence.append(
                {
                    "states": {
                        name: list(values)
                        for name, values in sorted(candidate_states.items())
                    },
                    "regulator_taps": dict(sorted(candidate_taps.items())),
                    **candidate_metrics,
                    "hard_violation_score": violation_score(candidate_metrics),
                    "guard_violation_score": guard_score(candidate_metrics),
                    "switching_count_from_previous": switching_count(candidate_states),
                    "regulator_tap_movement_from_previous": tap_movement(
                        candidate_taps
                    ),
                }
            )
        states = {
            name: tuple(values) for name, values in selected_states.items()
        }
        return NativeGridControlDecision(
            states=states,
            raw_metrics={
                "status": (
                    "COMMON_NATIVE_GRID_PREDICTIVE_DWELL_GUARD_SELECTED_FRESH"
                    if predictive_guard_evidence.get("status")
                    == "PREDICTIVE_DWELL_GUARD_OVERRIDE"
                    else (
                        "COMMON_NATIVE_GRID_GLOBAL_GUARD_SELECTED_FRESH"
                        if len(candidates) > 1
                        else "COMMON_NATIVE_GRID_TRANSITION_EVALUATED_FRESH"
                    )
                ),
                "issue": issue,
                "native_grid_control_authority": selected_raw.get(
                    "native_grid_control_authority"
                ),
                "previous_states": {
                    str(name).lower(): list(values)
                    for name, values in previous_capacitor_states.items()
                },
                "selected_states": {
                    name: list(values) for name, values in states.items()
                },
                "previous_regulator_taps": dict(sorted(previous_taps.items())),
                "selected_regulator_taps": dict(sorted(selected_taps.items())),
                "locked_capacitors": sorted(
                    str(name).lower() for name in locked_capacitors
                ),
                "selection_hard_constraint_pass": bool(
                    selected_raw.get("hard_constraint_pass", False)
                ),
                "selection_voltage_min_pu": float(selected_raw["voltage_min_pu"]),
                "selection_voltage_max_pu": float(selected_raw["voltage_max_pu"]),
                "selection_line_max_loading_pu": float(
                    selected_raw["line_max_loading_pu"]
                ),
                "selection_transformer_max_loading_pu": max(
                    float(selected_raw["transformer_max_kva_loading_pu"]),
                    float(selected_raw["transformer_max_current_loading_pu"]),
                ),
                "selection_voltage_min_bus_node": selected_raw.get(
                    "voltage_min_bus_node"
                ),
                "selection_transformer_max_current_loading_name": selected_raw.get(
                    "transformer_max_current_loading_name"
                ),
                "global_guard_search_triggered": len(candidates) > 1,
                "global_guard_candidates_evaluated": (
                    len(candidates)
                ),
                "global_guard_joint_discrete_search": {
                    "algorithm": (
                        (
                            "FRESH_EXACT_DUAL_ANCHOR_SENSITIVITY_GUIDED_"
                            "CAPACITOR_REGULATOR_RESTORATION"
                        )
                        if deep_search
                        else (
                            "FRESH_EXACT_DUAL_ANCHOR_GLOBAL_ONLINE_"
                            "CAPACITOR_REGULATOR_BEAM_SEARCH"
                        )
                    ),
                    "search_profile": "DEEP_RESTORATION" if deep_search else "ONLINE",
                    "tap_anchors": [
                        "LOCAL_TRANSITION",
                        "CHRONOLOGICAL_PRE_TRANSITION",
                    ],
                    "beam_width": beam_width,
                    "beam_width_per_capacitor_state": None,
                    "frontier_policy": (
                        "FINITE_DIFFERENCE_INTEGER_TRUST_REGION"
                        if deep_search
                        else "SCALAR_FEASIBILITY_BEAM"
                    ),
                    "frontier_width_per_capacitor_state": (
                        1 if deep_search else None
                    ),
                    "voltage_tradeoff_bin_pu": None,
                    "maximum_tap_depth": None if deep_search else maximum_tap_depth,
                    "single_tap_change_per_search_edge": not deep_search,
                    "integer_trust_region_radius": (
                        deep_trust_region_radius if deep_search else None
                    ),
                    "maximum_relinearizations": (
                        deep_maximum_relinearizations if deep_search else None
                    ),
                },
                "global_guard_candidate_evidence": candidate_evidence,
                "predictive_native_dwell_guard": predictive_guard_evidence,
            },
            fresh_instance=True,
            common_to_all_methods=True,
            regulator_taps=dict(selected_taps),
            pv_q_fraction_by_phase=(0.0, 0.0, 0.0),
        )

    def select_native_control_deep(self, **kwargs: Any) -> NativeGridControlDecision:
        return self.select_native_control(deep_search=True, **kwargs)

    def verify_fresh(
        self,
        *,
        issue: int,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
        robust_background_p_kw: Sequence[Sequence[float]],
        robust_background_q_kvar: Sequence[Sequence[float]],
        robust_pv_available_kw: Sequence[Sequence[float]],
        native_capacitor_states: Optional[Mapping[str, Sequence[int]]] = None,
        native_regulator_taps: Optional[Mapping[str, int]] = None,
        pv_q_fraction_by_phase: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> PhysicalCommit:
        state = self._state(
            facility_p_kw=facility_p_kw,
            facility_q_kvar=facility_q_kvar,
            mess_location=mess_location,
            mess_p_kw=mess_p_kw,
            mess_q_kvar=mess_q_kvar,
            mess_in_transit=mess_in_transit,
        )
        state.update(
            {
                "native_grid_control_mode": "FIXED_STATE_VERIFICATION",
                "native_capacitor_initial_states": {
                    str(name).lower(): list(values)
                    for name, values in (native_capacitor_states or {}).items()
                },
                "native_regulator_initial_tap_numbers": {
                    str(name).lower(): int(value)
                    for name, value in (native_regulator_taps or {}).items()
                },
            }
        )
        raw = self.exact.solve_step(self.paths, issue, state)
        robust = raw
        if robust_background_p_kw:
            robust_state = dict(state)
            robust_state.update({
                "background_p_kw": robust_background_p_kw,
                "background_q_kvar": robust_background_q_kvar,
                "pv_available_kw": robust_pv_available_kw,
            })
            robust = self.exact.solve_step(self.paths, issue, robust_state)
        actual_violation_count = sum(
            int(raw[key])
            for key in (
                "voltage_violation_count",
                "line_violation_count",
                "transformer_kva_violation_count",
                "transformer_current_violation_count",
            )
        ) + (0 if raw["root_sign_pass"] else 1)
        robust_violation_count = sum(
            int(robust[key])
            for key in (
                "voltage_violation_count",
                "line_violation_count",
                "transformer_kva_violation_count",
                "transformer_current_violation_count",
            )
        ) + (0 if robust["root_sign_pass"] else 1)
        passed = bool(raw["hard_constraint_pass"])
        if passed:
            exact_status = "PASS_FRESH_EXACT_OPENDSS_REALIZED_H0"
        elif not raw["root_sign_pass"]:
            exact_status = "FAIL_FRESH_EXACT_OPENDSS_ACTUAL_ROOT_SIGN"
        else:
            exact_status = "FAIL_FRESH_EXACT_OPENDSS_REALIZED_H0"
        exact_result = ExactAcResult(
            passed=passed,
            status=exact_status,
            fresh_instance=True,
            exact_three_phase_authority=True,
            minimum_voltage_pu=float(raw["voltage_min_pu"]),
            maximum_voltage_pu=float(raw["voltage_max_pu"]),
            maximum_line_loading_fraction=float(raw["line_max_loading_pu"]),
            maximum_transformer_loading_fraction=max(
                float(raw["transformer_max_kva_loading_pu"]),
                float(raw["transformer_max_current_loading_pu"]),
            ),
            final_ac_violation_count=actual_violation_count,
        )
        combined = dict(raw)
        combined.update({
            "facility_p_kw": [float(value) for value in facility_p_kw],
            "facility_q_kvar": [float(value) for value in facility_q_kvar],
            "facility_power_factor_assumption": 0.95,
            "facility_pue_assumption": 1.30,
            "robust_grid_fresh_opendss": bool(robust_background_p_kw),
            "robust_grid_role": "CAUSAL_PLAN_VALIDITY_DIAGNOSTIC_NOT_H0_COMMIT_GATE",
            "robust_grid_hard_constraint_pass": bool(robust["hard_constraint_pass"]),
            "robust_grid_violation_count": robust_violation_count,
            "robust_grid_voltage_min_pu": float(robust["voltage_min_pu"]),
            "robust_grid_voltage_max_pu": float(robust["voltage_max_pu"]),
            "robust_grid_line_max_loading_pu": float(robust["line_max_loading_pu"]),
            "robust_grid_transformer_max_loading_pu": max(
                float(robust["transformer_max_kva_loading_pu"]),
                float(robust["transformer_max_current_loading_pu"]),
            ),
            "robust_grid_native_capacitor_states": dict(
                robust.get("native_capacitor_states", {})
            ),
            "robust_grid_native_capcontrol_count": int(
                robust.get("native_capcontrol_count", 0)
            ),
        })
        return PhysicalCommit(exact_result, combined, False, True)


def _load_curve(path: Path) -> H100UtilizationPowerCurve:
    data = json_load(path)
    curve = H100UtilizationPowerCurve(
        tuple(map(float, data["utilization_fraction"])),
        tuple(map(float, data["per_gpu_power_kw_p95_envelope"])),
        str(data["source_sha256"]),
        tuple(item["sha256"] for item in data["source_members"] if item["included_in_statistics"]),
        str(data["work_fraction_semantics"]),
    )
    curve.validate()
    return curve


def _runtime_initial_state(
    pre: Mapping[str, Any],
    start_issue: int,
    *,
    require_population_identity: bool = False,
) -> RuntimeInitialState:
    """Accept legacy runtime PRE or the v13.2 independent-daily manifest."""
    if "canonical_pre" in pre:
        if start_issue % 288 != 0:
            raise RuntimeError("independent daily PRE must start on a 288-issue boundary")
        if require_population_identity:
            try:
                certificate = certify_daily_pre_identity(dict(pre))
            except DailyInitializationError as exc:
                raise RuntimeError("daily PRE population identity is invalid") from exc
            if certificate.get("status") != "PASS":
                raise RuntimeError("daily PRE identity certificate did not pass")
        canonical = pre["canonical_pre"]
        energy = canonical["mess_energy_kwh"]
        locations = canonical["mess_locations"]
        if len(energy) != 4 or len(locations) != 4:
            raise RuntimeError("v13.2 canonical PRE must contain exactly four MESS")
        if canonical.get("ai_queue_empty") is not True or canonical.get("ai_running_empty") is not True:
            raise RuntimeError("v13.2 daily PRE must start with empty controllable AI state")
        if canonical.get("wan_inventory_empty") is not True or canonical.get("wan_pipeline_empty") is not True:
            raise RuntimeError("v13.2 daily PRE must start with empty WAN state")
        if canonical.get("active_slow_plan") is not None:
            raise RuntimeError("v13.2 daily PRE must not carry an active slow plan")
        if tuple(map(float, energy)) != (760.0, 760.0, 760.0, 760.0):
            raise RuntimeError("v13.2 daily PRE must reset every MESS to 760 kWh")
        if tuple(map(str, locations)) != ("STA09", "IDC12", "STA07", "STA11"):
            raise RuntimeError("v13.2 daily PRE MESS staging locations changed")
        zero_fields = ("compute_debt_gpu_hours", "energy_debt_kwh", "rebound_state")
        if require_population_identity and any(
            float(canonical.get(field, float("nan"))) != 0.0
            for field in zero_fields
        ):
            raise RuntimeError("v13.2 daily PRE debt/rebound state must reset to zero")
        if require_population_identity:
            encoded = json.dumps(
                canonical, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != str(pre["canonical_pre_sha256"]):
                raise RuntimeError("v13.2 canonical PRE content hash mismatch")
        return RuntimeInitialState(
            issue=start_issue,
            state_sha256=str(pre["canonical_pre_sha256"]),
            mess_energy_kwh={f"MESS{i + 1:02d}": float(value) for i, value in enumerate(energy)},
            mess_location={f"MESS{i + 1:02d}": str(value) for i, value in enumerate(locations)},
        )

    if int(pre["state"]["issue_step"]) > start_issue:
        raise RuntimeError("canonical PRE starts after requested issue")
    return RuntimeInitialState(
        issue=start_issue,
        state_sha256=str(pre["state_sha256"]),
        mess_energy_kwh={key: float(value) for key, value in pre["state"]["mess_E_kWh"].items()},
        mess_location={key: str(value["service_id"]) for key, value in pre["state"]["mess_state"].items()},
    )


@lru_cache(maxsize=16)
def _indexed_power_blocks(shared: Path) -> tuple[tuple[int, int, Path], ...]:
    rows = []
    for path in sorted((shared / "power_price").glob("block_*_*_*")):
        if not path.is_dir():
            continue
        try:
            first, last = map(int, path.name.rsplit("_", 2)[-2:])
        except ValueError:
            continue
        if first > last:
            raise RuntimeError(
                f"power/price source block has reversed range: {path.name}"
            )
        rows.append((first, last, path))
    if not rows:
        raise RuntimeError(f"no power/price source blocks found under {shared}")
    # A full-month source view joins several independently generated chunks.
    # Each chunk legitimately restarts its local block ordinal at block_00, so
    # directory-name order is not chronological.  Validate overlap only after
    # ordering by the authoritative global issue interval encoded in the name.
    rows.sort(key=lambda row: (row[0], row[1], row[2].name))
    for (_, prior_last, _), (current_first, _, _) in zip(rows, rows[1:]):
        if current_first <= prior_last:
            raise RuntimeError("power/price source block ranges overlap")
    return tuple(rows)


def _block(shared: Path, issue: int) -> Path:
    if issue < 0:
        raise RuntimeError("issue must be non-negative")
    block = issue // 576
    start = block * 576
    aligned = shared / "power_price" / f"block_{block:02d}_{start}_{start + 575}"
    if aligned.is_dir():
        return aligned
    matches = [
        path
        for first, last, path in _indexed_power_blocks(shared.resolve())
        if first <= issue <= last
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"issue {issue} is covered by {len(matches)} power/price source blocks"
        )
    return matches[0]


def _frames(
    *,
    shared: Path,
    start_issue: int,
    count: int,
    independent_jobs: Path,
    canonical_jobs: Path,
    mobility_paths: Mapping[int, Path],
    route_rows: Sequence[Mapping[str, Any]],
    mobility_physics: MobilityPhysics,
    mobility_physics_sha256: str,
    workload_reserve_gpu: Mapping[str, float],
    feeder_scale: float,
    migration_authority: MigrationAuthority,
) -> list[CausalExperimentFrame]:
    if not 0.0 < feeder_scale <= 1.0:
        raise RuntimeError("feeder scale must be in (0, 1]")
    independent = pd.read_parquet(independent_jobs)
    canonical_fields = [
        "job_uid", "source_record_id", "runtime_seconds_source", "CPU_request_share_upper_component_kW",
        "input_bytes", "job_power_prefreeze_authorized",
    ]
    canonical = pd.read_parquet(canonical_jobs, columns=canonical_fields)
    if canonical["job_uid"].astype(str).duplicated().any():
        raise RuntimeError("canonical job_uid is not unique")
    canonical["job_uid"] = canonical["job_uid"].astype(str)
    independent["job_uid"] = independent["job_uid"].astype(str)
    selected = independent[
        (independent["arrival_step"].astype(int) >= start_issue)
        & (independent["arrival_step"].astype(int) < start_issue + count)
    ].merge(canonical, on="job_uid", how="left", validate="many_to_one", suffixes=("", "_canonical"))
    if selected["runtime_seconds_source"].isna().any() or not selected["job_power_prefreeze_authorized"].fillna(False).all():
        raise RuntimeError("runtime job cohort lacks source-matched authorized power/work records")
    arrivals: dict[int, list[OperationalTrainingJob]] = {}
    for record in selected.to_dict(orient="records"):
        input_value = record.get("input_bytes_canonical", record.get("input_bytes"))
        input_bytes = None if pd.isna(input_value) else int(input_value)
        job = OperationalTrainingJob(
            job_uid=str(record["job_uid"]),
            origin_idc=str(record["origin_IDC_id"]),
            arrival_step=int(record["arrival_step"]),
            latest_start_step=int(record["latest_start_step"]),
            deadline_step=int(record["latest_completion_step"]),
            requested_gpu=int(record["requested_gpu"]),
            runtime_seconds_source=float(record["runtime_seconds_source"]),
            cpu_request_share_kw=float(record["CPU_request_share_upper_component_kW"]),
            input_bytes=input_bytes,
            source_record_id=str(record["source_record_id"]),
            migration_payload_bytes=migration_authority.checkpoint_payload_bytes(
                int(record["requested_gpu"])
            ),
            migration_authority_sha256=migration_authority.fingerprint,
        )
        job.validate()
        arrivals.setdefault(job.arrival_step, []).append(job)
    frames = []
    cache: dict[Path, dict[str, np.ndarray]] = {}
    for issue in range(start_issue, start_issue + count):
        root = _block(shared, issue)
        if root not in cache:
            cache[root] = {
                "issues": np.load(root / "power__issues.npy", mmap_mode="r"),
                "p": np.load(root / "power__q50_net_background_p_kw.npy", mmap_mode="r"),
                "q": np.load(root / "power__q50_background_q_kvar.npy", mmap_mode="r"),
                "upper_p": np.load(root / "power__q90_gross_background_p_kw.npy", mmap_mode="r"),
                "upper_q": np.load(root / "power__q90_background_q_kvar.npy", mmap_mode="r"),
                "lower_pv": np.load(root / "power__q10_pv_available_kw.npy", mmap_mode="r"),
                "price_issues": np.load(root / "price__issues.npy", mmap_mode="r"),
                "price": np.load(root / "price__q50.npy", mmap_mode="r"),
            }
        block = cache[root]
        hits = np.flatnonzero(np.asarray(block["issues"], dtype=np.int64) == issue)
        price_hits = np.flatnonzero(np.asarray(block["price_issues"], dtype=np.int64) == issue)
        if len(hits) != 1 or len(price_hits) != 1:
            raise RuntimeError(f"causal source cardinality failure issue={issue}")
        row, price_row = int(hits[0]), int(price_hits[0])
        price_horizon = np.asarray(block["price"][price_row], dtype=float)
        mobility_path = mobility_paths.get(issue)
        if mobility_path is None:
            raise RuntimeError(f"missing causal mobility source issue={issue}")
        with np.load(mobility_path, allow_pickle=False) as mobility:
            eta_horizon = np.asarray(mobility["path_quantiles_sec"], dtype=float)
        if eta_horizon.shape != (PLANNING_HORIZON_STEPS, 1656, 3):
            raise RuntimeError(
                f"causal H54 mobility ETA shape is invalid issue={issue} "
                f"shape={eta_horizon.shape}"
            )
        eta = eta_horizon[0]
        if eta.shape != (1656, 3):
            raise RuntimeError(
                f"causal mobility ETA shape is invalid issue={issue} shape={eta.shape}"
            )
        routes = []
        for static in route_rows:
            slot = int(static["slot"])
            q50_energy, safe_energy = mobility_physics.forecast_energy_kwh(
                static, eta[slot]
            )
            routes.append(MobilityRouteForecast(
                source_service_id=str(static["source_service_id"]),
                destination_service_id=str(static["destination_service_id"]),
                od_index=int(static["od_index"]),
                rank=int(static["rank"]),
                q50_eta_seconds=float(eta[slot, 1]),
                safe_eta_seconds=float(eta[slot, 2]),
                q50_energy_kwh=q50_energy,
                safe_energy_kwh=safe_energy,
            ))
        robust_p = feeder_scale * np.asarray(block["upper_p"][row, 0], dtype=float)
        robust_q = feeder_scale * np.asarray(block["upper_q"][row, 0], dtype=float)
        robust_pv = feeder_scale * np.asarray(block["lower_pv"][row, 0], dtype=float)
        native_forecast_p = feeder_scale * np.asarray(
            block["upper_p"][row, 1 : PREDICTIVE_NATIVE_HORIZON_STEPS + 1],
            dtype=float,
        )
        native_forecast_q = feeder_scale * np.asarray(
            block["upper_q"][row, 1 : PREDICTIVE_NATIVE_HORIZON_STEPS + 1],
            dtype=float,
        )
        native_forecast_pv = feeder_scale * np.asarray(
            block["lower_pv"][row, 1 : PREDICTIVE_NATIVE_HORIZON_STEPS + 1],
            dtype=float,
        )
        planning_forecast_p = feeder_scale * np.asarray(
            block["upper_p"][row, :PLANNING_HORIZON_STEPS],
            dtype=float,
        )
        planning_forecast_q = feeder_scale * np.asarray(
            block["upper_q"][row, :PLANNING_HORIZON_STEPS],
            dtype=float,
        )
        planning_forecast_pv = feeder_scale * np.asarray(
            block["lower_pv"][row, :PLANNING_HORIZON_STEPS],
            dtype=float,
        )
        if any(
            values.shape[0] != PREDICTIVE_NATIVE_HORIZON_STEPS
            for values in (
                native_forecast_p,
                native_forecast_q,
                native_forecast_pv,
            )
        ):
            raise RuntimeError(
                f"causal native-control forecast is shorter than "
                f"{PREDICTIVE_NATIVE_HORIZON_STEPS} steps at issue={issue}"
            )
        if any(
            values.shape[0] != PLANNING_HORIZON_STEPS
            for values in (
                planning_forecast_p,
                planning_forecast_q,
                planning_forecast_pv,
            )
        ):
            raise RuntimeError(
                f"causal planning forecast is shorter than "
                f"{PLANNING_HORIZON_STEPS} steps at issue={issue}"
            )
        payload = {
            "issue": issue,
            "power_block_authority_sha256": sha256(root / "BLOCK_AUTHORITY.json"),
            "arriving_job_uids": sorted(job.job_uid for job in arrivals.get(issue, ())),
            "mobility_issue_sha256": sha256(mobility_path),
            "mobility_physics_sha256": mobility_physics_sha256,
            "mobility_energy_source": "DETERMINISTIC_PHYSICS_FROM_GEOMETRY_AND_ETA",
            "legacy_mobility_energy_arrays_read": False,
            "factorized_uncertainty_bound": True,
            "predictive_native_forecast_lead_steps": [
                1,
                PREDICTIVE_NATIVE_HORIZON_STEPS,
            ],
            "predictive_native_future_actual_used": False,
            "joint_planning_forecast_horizon_indices": [
                0,
                PLANNING_HORIZON_STEPS - 1,
            ],
            "joint_planning_future_actual_used": False,
            "feeder_absolute_scale_alpha": feeder_scale,
            "migration_authority_sha256": migration_authority.fingerprint,
        }
        frames.append(CausalExperimentFrame(
            issue=issue,
            current_price_aud_per_mwh=float(price_horizon[0]),
            horizon_price_median_aud_per_mwh=float(statistics.median(price_horizon.tolist())),
            q50_background_p_kw=feeder_scale * float(np.asarray(block["p"][row, 0], dtype=float).sum()),
            q50_background_q_kvar=feeder_scale * float(np.asarray(block["q"][row, 0], dtype=float).sum()),
            arrivals=tuple(sorted(arrivals.get(issue, ()), key=lambda job: job.job_uid)),
            exogenous_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            grid_upper_background_p_kw=float((robust_p - robust_pv).sum()),
            grid_upper_background_q_kvar=float(robust_q.sum()),
            robust_background_p_kw=tuple(tuple(map(float, values)) for values in robust_p),
            robust_background_q_kvar=tuple(tuple(map(float, values)) for values in robust_q),
            robust_pv_available_kw=tuple(tuple(map(float, values)) for values in robust_pv),
            native_forecast_background_p_kw=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in native_forecast_p
            ),
            native_forecast_background_q_kvar=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in native_forecast_q
            ),
            native_forecast_pv_available_kw=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in native_forecast_pv
            ),
            planning_forecast_background_p_kw=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in planning_forecast_p
            ),
            planning_forecast_background_q_kvar=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in planning_forecast_q
            ),
            planning_forecast_pv_available_kw=tuple(
                tuple(tuple(map(float, phase_values)) for phase_values in profile)
                for profile in planning_forecast_pv
            ),
            workload_reserve_gpu=dict(workload_reserve_gpu),
            mobility_routes=tuple(routes),
            planning_mobility_npz_path=str(mobility_path.resolve()),
            planning_mobility_npz_sha256=sha256(mobility_path),
        ))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--candidate-id", default="JAN2025_DAY01")
    parser.add_argument(
        "--evaluation-period-id",
        help="Frozen V14 evaluation period identity bound into every result.",
    )
    parser.add_argument(
        "--final-evaluation-authority",
        type=Path,
        help="Frozen final-evaluation authority; required by the March launcher.",
    )
    parser.add_argument(
        "--calendar-date",
        help="Simulation-local AEST calendar date (YYYY-MM-DD) for daily output grouping.",
    )
    parser.add_argument(
        "--h0-fidelity-audit-every-steps",
        type=int,
        default=0,
        help="Sample aligned same-action surrogate/Fresh-AC candidates; 0 disables.",
    )
    parser.add_argument(
        "--diagnostic-method",
        choices=(
            tuple(method.value for method in ComparisonMethod)
            + tuple(method.value for method in ElectricalStressMethod)
        ),
        help="Run one full state-chain method for technical diagnosis only.",
    )
    parser.add_argument(
        "--electrical-stress-campaign",
        action="store_true",
        help=(
            "Run the authoritative B00-B09 electrical-stress registry. "
            "Historical B0-B8 identifiers remain read-compatible only."
        ),
    )
    parser.add_argument(
        "--supplementary-b8-periodic-5min",
        action="store_true",
        help=(
            "Run only the post-hoc B8 five-minute periodic full-replan "
            "timing baseline; the frozen B0-B7 main matrix remains unchanged."
        ),
    )
    parser.add_argument(
        "--allow-pending-native-grid-control-diagnostic",
        action="store_true",
        help=(
            "Permit the explicitly non-frozen capacitor-control candidate only "
            "with --diagnostic-method; never authorizes a B0-B7 campaign."
        ),
    )
    parser.add_argument("--start-issue", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--exact-package-root", type=Path, required=True)
    parser.add_argument("--authority-package-root", type=Path, required=True)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument(
        "--retained-h54-base",
        type=Path,
        default=Path("/home/jaewon/mobile_ess_work"),
        help="Existing BUILD4/BUILD7 authority base used by the retained H54 solver.",
    )
    parser.add_argument(
        "--h54-planner-backend",
        choices=("online-bounded", "full-miqcp-oracle"),
        default="online-bounded",
        help=(
            "Use the bounded online controller in the live loop (default), or "
            "the retained Full H54 MIQCP only for offline paired-oracle diagnostics."
        ),
    )
    parser.add_argument("--initial-state", type=Path, required=True)
    parser.add_argument("--independent-jobs", type=Path, required=True)
    parser.add_argument("--canonical-jobs", type=Path, required=True)
    parser.add_argument("--power-curve", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, action="append", required=True)
    parser.add_argument("--route-catalog", type=Path, required=True)
    parser.add_argument(
        "--mobility-template-bank",
        type=Path,
        help="Legacy compatibility argument; E4 energy profiles are never loaded.",
    )
    parser.add_argument("--workload-uncertainty", type=Path, required=True)
    parser.add_argument("--factorized-uncertainty", type=Path, required=True)
    parser.add_argument(
        "--risk-calibration",
        type=Path,
        help=(
            "Frozen January-2025 B07 electrical-stress event-risk calibration. "
            "Required before calibrated B08/B09 execution and prohibited from "
            "B07 fitting."
        ),
    )
    parser.add_argument(
        "--migration-authority",
        type=Path,
        help=(
            "Frozen IDC migration/WAN authority; defaults to the repository "
            "IDC_MIGRATION_AUTHORITY_V1 contract."
        ),
    )
    parser.add_argument(
        "--checkpoint-payload-occupancy-factor",
        type=float,
        choices=(0.25, 0.5, 1.0),
        help=(
            "January development sensitivity only. Defaults to the frozen "
            "primary factor in the migration authority."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--diagnostic-checkpoint-after-issue",
        type=int,
        help="Save a non-scientific cold-planner resume checkpoint after this issue.",
    )
    parser.add_argument(
        "--diagnostic-resume-checkpoint",
        type=Path,
        help="Resume a diagnostic method from a locally generated runtime checkpoint.",
    )
    parser.add_argument(
        "--diagnostic-resume-prefix-output",
        type=Path,
        help=(
            "Reuse the contiguous committed issue prefix in this output while "
            "resuming from --diagnostic-resume-checkpoint."
        ),
    )
    parser.add_argument(
        "--diagnostic-stop-after-issue",
        type=int,
        help=(
            "Stop cleanly after committing this issue while retaining the "
            "original --count episode horizon; diagnostic methods only."
        ),
    )
    parser.add_argument(
        "--restart-checkpoint-interval",
        type=int,
        help=(
            "Atomically refresh LATEST_RUNTIME_CHECKPOINT every N committed "
            "issues so an interrupted day can resume from a verified prefix."
        ),
    )
    parser.add_argument(
        "--reuse-passed-methods",
        action="store_true",
        help=(
            "Reuse only fully validated PASS method directories and execute "
            "the remaining methods in the frozen matrix order."
        ),
    )
    args = parser.parse_args()
    if args.reuse_passed_methods and args.diagnostic_method:
        parser.error("--reuse-passed-methods is only valid for a full matrix")
    if (
        args.diagnostic_checkpoint_after_issue is not None
        or args.diagnostic_resume_checkpoint is not None
        or args.diagnostic_resume_prefix_output is not None
        or args.diagnostic_stop_after_issue is not None
    ) and not args.diagnostic_method:
        parser.error(
            "diagnostic checkpoint/resume/stop requires --diagnostic-method"
        )
    if (
        args.diagnostic_resume_prefix_output is not None
        and args.diagnostic_resume_checkpoint is None
    ):
        parser.error(
            "--diagnostic-resume-prefix-output requires "
            "--diagnostic-resume-checkpoint"
        )
    if args.diagnostic_method and args.supplementary_b8_periodic_5min:
        parser.error(
            "--diagnostic-method and --supplementary-b8-periodic-5min are mutually exclusive"
        )
    if args.electrical_stress_campaign and args.supplementary_b8_periodic_5min:
        parser.error(
            "--electrical-stress-campaign already includes B08; legacy B8 supplementary mode is incompatible"
        )
    if args.electrical_stress_campaign and args.h54_planner_backend == "full-miqcp-oracle":
        parser.error(
            "Full H54 MIQCP is an offline sampled-state oracle and cannot be attached "
            "to the online B00-B09 campaign loop"
        )
    calibrated_method_selected = bool(
        args.supplementary_b8_periodic_5min
        or args.diagnostic_method in {"B7", "B8", "B08", "B09"}
        or args.diagnostic_method is None
    )
    if calibrated_method_selected and args.risk_calibration is None:
        parser.error(
            "--risk-calibration is required before a calibrated method or full campaign execution"
        )
    if args.diagnostic_method in {"B6", "B07"} and args.risk_calibration is not None:
        parser.error(
            "January B6 calibration fitting must not load a calibrated-risk artifact"
        )
    risk_calibration = (
        load_frozen_risk_calibration(args.risk_calibration)
        if args.risk_calibration is not None
        else None
    )
    stress_method_selected = bool(
        args.electrical_stress_campaign
        or args.diagnostic_method
        in {method.value for method in ElectricalStressMethod}
    )
    if (
        stress_method_selected
        and risk_calibration is not None
        and (
            risk_calibration.source_method != "B07"
            or risk_calibration.authority_id != ELECTRICAL_STRESS_AUTHORITY_ID
        )
    ):
        parser.error(
            "B00-B09 requires a frozen January B07 electrical-stress calibration; "
            "historical B6 calibration is read-compatible only"
        )
    if args.count <= 0:
        parser.error("--count must be positive")
    repo = args.repo.resolve()
    final_evaluation_authority = None
    final_evaluation_authority_path = None
    if args.final_evaluation_authority is not None:
        final_evaluation_authority_path = args.final_evaluation_authority.resolve()
        final_evaluation_authority = json_load(final_evaluation_authority_path)
        if (
            final_evaluation_authority.get("identity")
            != "MARCH_2025_FINAL_EVALUATION_AUTHORITY_V2"
            or final_evaluation_authority.get("scientific_framework_id")
            != "V14_AI_ICPS"
            or final_evaluation_authority.get("status")
            != "FROZEN_FINAL_EVALUATION_AUTHORIZED"
            or final_evaluation_authority.get(
                "main_scientific_campaign_authorized"
            )
            is not True
            or final_evaluation_authority.get("independent_holdout_claim")
            is not False
            or args.evaluation_period_id
            != final_evaluation_authority.get("evaluation_period_id")
        ):
            raise RuntimeError("March final-evaluation authority is invalid")
        if args.calendar_date is None or not (
            str(final_evaluation_authority["calendar_date_first"])
            <= args.calendar_date
            <= str(final_evaluation_authority["calendar_date_last"])
        ):
            raise RuntimeError("calendar date is outside final-evaluation authority")
        if not args.electrical_stress_campaign:
            raise RuntimeError(
                "final-evaluation authority requires the full B00-B09 campaign"
            )
    elif args.evaluation_period_id is not None:
        raise RuntimeError(
            "--evaluation-period-id requires --final-evaluation-authority"
        )
    migration_authority_path = (
        args.migration_authority.resolve()
        if args.migration_authority is not None
        else (repo / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json").resolve()
    )
    migration_authority = load_migration_authority(
        migration_authority_path,
        checkpoint_payload_occupancy_factor=(
            args.checkpoint_payload_occupancy_factor
        ),
    )
    source_identity = git_source_identity(repo)
    native_control_dss = (
        repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.dss"
    ).resolve()
    native_control_authority = (
        repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json"
    ).resolve()
    native_asset_audit = (
        repo / "pfr/contracts/IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1.json"
    ).resolve()
    predictive_native_authority = (
        repo / "pfr/contracts/PREDICTIVE_NATIVE_DWELL_GUARD_V1.json"
    ).resolve()
    runtime_contract_path = (
        repo / "pfr/contracts/PFR_RUNTIME_CONTRACT.json"
    ).resolve()
    if not all(
        path.is_file()
        for path in (
            native_control_dss,
            native_control_authority,
            native_asset_audit,
            predictive_native_authority,
            runtime_contract_path,
        )
    ):
        raise RuntimeError("common native grid-control authority is incomplete")
    native_control_contract = json_load(native_control_authority)
    native_asset_contract = json_load(native_asset_audit)
    predictive_native_contract = json_load(predictive_native_authority)
    runtime_contract = json_load(runtime_contract_path)
    if (
        predictive_native_contract.get("identity")
        != "PREDICTIVE_NATIVE_DWELL_GUARD_V1"
        or int(predictive_native_contract.get("horizon_steps", -1))
        != PREDICTIVE_NATIVE_HORIZON_STEPS
        or predictive_native_contract.get("forecast_authority", {}).get(
            "future_actual_used"
        )
        is not False
        or predictive_native_contract.get("common_to_methods")
        != [f"B{index}" for index in range(9)]
    ):
        raise RuntimeError("predictive native dwell-guard authority is invalid")
    if (
        runtime_contract.get("schema_version")
        != "K9H7_RESULT_V2.runtime_contract.v2"
        or "admitted on its causal arrival issue"
        not in runtime_contract.get("workload_admission_authority", "")
        or "work-conserving"
        not in runtime_contract.get("common_gpu_gang_scheduler", "")
        or "fails closed"
        not in runtime_contract.get("non_temporal_compute_authority", "")
        or "Every started MESS route"
        not in runtime_contract.get("mobility_prediction_actual_audit", "")
        or "Every completed checkpoint migration"
        not in runtime_contract.get("migration_prediction_actual_audit", "")
    ):
        raise RuntimeError("workload admission runtime authority is invalid")
    frozen_control_authorized = bool(
        native_control_contract.get("status") == "FROZEN_APPROVED"
        and native_control_contract.get("main_scientific_campaign_authorized")
        is True
    )
    post_hoc_control_authorized = bool(
        native_control_contract.get("status")
        == "FROZEN_APPROVED_POST_HOC_VALIDATION_ONLY"
        and native_control_contract.get(
            "january_2025_post_hoc_validation_authorized"
        )
        is True
        and native_control_contract.get("main_scientific_campaign_authorized")
        is False
    )
    pending_diagnostic_authorized = bool(
        args.diagnostic_method
        and args.allow_pending_native_grid_control_diagnostic
        and native_control_contract.get("status")
        == "ARCHITECTURE_IMPLEMENTED_PARAMETER_AUTHORITY_PENDING"
    )
    if args.allow_pending_native_grid_control_diagnostic and not args.diagnostic_method:
        parser.error(
            "--allow-pending-native-grid-control-diagnostic requires --diagnostic-method"
        )
    if not (
        frozen_control_authorized
        or post_hoc_control_authorized
        or pending_diagnostic_authorized
    ):
        raise SystemExit(
            "BLOCKED: native capacitor parameters lack a frozen prospective "
            "authority. The pending-control flag is restricted to an explicit "
            "single-method engineering diagnostic."
        )
    final_evaluation_authorized = final_evaluation_authority is not None
    campaign_authorized = bool(
        frozen_control_authorized or final_evaluation_authorized
    )
    evaluation_classification = (
        str(final_evaluation_authority["evaluation_classification"])
        if final_evaluation_authority is not None
        else str(native_control_contract["evaluation_classification"])
    )
    evaluation_period_id = (
        str(args.evaluation_period_id)
        if args.evaluation_period_id is not None
        else str(args.candidate_id)
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    exact = _load_exact_module(repo, args.exact_package_root)
    source_work = output / "_exact_source_work"
    if source_work.exists():
        shutil.rmtree(source_work)
    source_work.mkdir(parents=True)
    paths = exact.prepare_sources(
        args.authority_package_root.resolve(), source_work,
        v2038_root=str(args.exact_package_root.resolve()),
        primary_root=str(args.primary_root.resolve()),
    )
    if (
        native_control_contract.get("common_to_B0_B7") is not True
        or native_control_contract.get("optimized_by_B_method") is not False
        or native_asset_contract.get("status")
        != "PASS_ASSET_AUDIT_PARAMETER_GAP_FOUND"
    ):
        raise RuntimeError("common native grid-control authority is invalid")
    original_master = Path(paths["assets"]) / "IEEE123Master.dss"
    if sha256(original_master) != native_control_contract.get(
        "original_ieee123_master_sha256"
    ):
        raise RuntimeError(
            "original IEEE123 master does not match native-control authority"
        )
    paths["native_grid_control"] = str(native_control_dss)
    feeder_scale_path = (
        repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"
    ).resolve()
    feeder_scale_contract = json_load(feeder_scale_path)
    feeder_scale = float(feeder_scale_contract.get("alpha_grid", float("nan")))
    if (
        feeder_scale_contract.get("status") != "FROZEN_POST_HOC_P100_FEEDER_SCALE"
        or not 0.0 < feeder_scale <= 1.0
    ):
        raise RuntimeError("feeder absolute-scale contract is invalid")
    paths["feeder_scale_contract"] = str(feeder_scale_path)
    diagnostic_resume_state = None
    diagnostic_resume_cumulative_grid_cost_aud = 0.0
    diagnostic_prefix_records: list[Mapping[str, Any]] = []
    pre: Optional[Mapping[str, Any]] = None
    if args.diagnostic_resume_checkpoint is not None:
        with args.diagnostic_resume_checkpoint.resolve().open("rb") as handle:
            checkpoint = pickle.load(handle)
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("schema_version")
            != "PFR_DIAGNOSTIC_RUNTIME_CHECKPOINT_V1"
            or checkpoint.get("comparison_method_id") != args.diagnostic_method
            or checkpoint.get("representative_week_id") != args.candidate_id
            or int(checkpoint.get("completed_issue", -2)) + 1
            != int(checkpoint.get("resume_issue", -1))
            or int(checkpoint.get("resume_issue", -1)) != args.start_issue
            or not isinstance(checkpoint.get("state"), MutableMethodState)
            or checkpoint.get("post_state_sha256")
            != checkpoint.get("state").pre_state_sha256
        ):
            raise RuntimeError("diagnostic resume checkpoint contract mismatch")
        diagnostic_resume_state = checkpoint["state"]
        diagnostic_resume_cumulative_grid_cost_aud = float(
            checkpoint["cumulative_grid_cost_aud"]
        )
        initial = RuntimeInitialState(
            issue=args.start_issue,
            state_sha256=str(checkpoint["post_state_sha256"]),
            mess_energy_kwh=dict(diagnostic_resume_state.mess_energy_kwh),
            mess_location=dict(diagnostic_resume_state.mess_location),
        )
        if args.diagnostic_resume_prefix_output is not None:
            prefix_method_root = (
                args.diagnostic_resume_prefix_output.resolve()
                / str(args.diagnostic_method)
            )
            prefix_paths = sorted(
                prefix_method_root.glob("issue_*/COMMIT_MARKER.json")
            )
            diagnostic_prefix_records = [
                json_load(path)
                for path in prefix_paths
                if int(path.parent.name.removeprefix("issue_"))
                < args.start_issue
            ]
            if not diagnostic_prefix_records:
                raise RuntimeError("diagnostic resume prefix contains no markers")
    else:
        pre = json_load(args.initial_state)
        if not args.diagnostic_method and "canonical_pre" not in pre:
            raise RuntimeError("main January B0-B7 execution requires canonical daily PRE")
        initial = _runtime_initial_state(
            pre,
            args.start_issue,
            require_population_identity=not bool(args.diagnostic_method),
        )
    factorized = json_load(args.factorized_uncertainty)
    workload_uncertainty = json_load(args.workload_uncertainty)
    if factorized.get("status") != "PASS" or workload_uncertainty.get("status") != "PASS":
        raise RuntimeError("PFR3 factorized/workload authority is not PASS")
    mobility_paths = {}
    for root in args.mobility_root:
        for path in (root / "mobility_runtime").glob("issue_*.npz"):
            issue = int(path.name.split("_")[1])
            if issue in mobility_paths:
                raise RuntimeError(f"duplicate mobility issue {issue}")
            mobility_paths[issue] = path
    route_catalog = json_load(args.route_catalog)
    route_rows = route_catalog.get("routes", ())
    required_route_physics = {
        "route_distance_km",
        "cumulative_ascent_m",
        "cumulative_descent_m",
    }
    if (
        route_catalog.get("status") != "PASS"
        or route_catalog.get("mobility_energy_ml_loaded") is not False
        or route_catalog.get("runtime_energy_authority")
        != "DETERMINISTIC_PHYSICS_E_RECOMPUTED_FROM_GEOMETRY_AND_CAUSAL_ETA"
        or len(route_rows) != 1656
        or any(not required_route_physics.issubset(route) for route in route_rows)
    ):
        raise RuntimeError("frozen K=3 route catalog is incomplete")
    mobility_physics_path = args.repo / "pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json"
    mobility_physics = MobilityPhysics.from_contract(mobility_physics_path)
    mobility_physics_fingerprint = sha256(mobility_physics_path)
    mobility_execution_path = (
        args.repo / "pfr/contracts/MESS_MOBILITY_EXECUTION_SUMO_V1.json"
    )
    mobility_execution = Stage25fSumoExecutionAuthority(
        contract_path=mobility_execution_path,
        mobility_physics=mobility_physics,
        route_rows=route_rows,
    )
    frames = _frames(
        shared=args.shared_root.resolve(), start_issue=args.start_issue, count=args.count,
        independent_jobs=args.independent_jobs.resolve(), canonical_jobs=args.canonical_jobs.resolve(),
        mobility_paths=mobility_paths,
        route_rows=route_rows,
        mobility_physics=mobility_physics,
        mobility_physics_sha256=mobility_physics_fingerprint,
        workload_reserve_gpu={
            key: float(value) for key, value in workload_uncertainty["idc_gpu_reserve"].items()
        },
        feeder_scale=feeder_scale,
        migration_authority=migration_authority,
    )
    evaluation_contract = {
        "scientific_framework_id": "V14_AI_ICPS",
        "evaluation_period_id": evaluation_period_id,
        "final_evaluation_authority_sha256": (
            sha256(final_evaluation_authority_path)
            if final_evaluation_authority_path is not None
            else None
        ),
        "gpu_capacity_per_idc_modeled": 256,
        "facility_power_factor_assumption": 0.95,
        "facility_pue_assumption": 1.30,
        "mess_discharge_kw_when_enabled": 20.0,
        "maximum_refresh_steps": 6,
        "future_actual_used": False,
        "factorized_uncertainty_sha256": sha256(args.factorized_uncertainty),
        "workload_uncertainty_sha256": sha256(args.workload_uncertainty),
        "migration_authority_sha256": migration_authority.fingerprint,
        "migration_contract_sha256": migration_authority.contract_fingerprint,
        "migration_authority_id": migration_authority.authority_id,
        "checkpoint_payload_occupancy_factor": (
            migration_authority.checkpoint_payload_occupancy_factor
        ),
        "checkpoint_payload_parameterization": (
            "ENGINEERING_SCENARIO_NOT_MEASURED_CHECKPOINT_SIZE"
        ),
        "route_catalog_sha256": sha256(args.route_catalog),
        "mobility_physics_sha256": mobility_physics_fingerprint,
        "mobility_execution_authority_sha256": mobility_execution.fingerprint,
        "mobility_energy_authority": (
            "PLANNING_PHYSICS_AT_CAUSAL_ML_ETA_EXECUTION_PHYSICS_AT_SUMO_REALIZED_ETA"
        ),
        "mobility_planning_time_authority": "CAUSAL_ML_ETA_Q10_Q50_Q90",
        "mobility_execution_time_authority": mobility_execution.AUTHORITY_ID,
        "mobility_execution_post_decision_only": True,
        "mobility_execution_actual_used_by_optimizer": False,
        "mobility_prediction_actual_error_materialized": True,
        "migration_prediction_actual_error_materialized": True,
        "risk_calibration_authority_id": (
            risk_calibration.authority_id
            if risk_calibration is not None
            else None
        ),
        "risk_calibration_artifact_sha256": (
            risk_calibration.artifact_sha256
            if risk_calibration is not None
            else None
        ),
        "risk_calibration_fit_period": (
            risk_calibration.source_period
            if risk_calibration is not None
            else None
        ),
        "march_outcomes_used_for_risk_calibration": False,
        "migration_realization_classification": (
            "DETERMINISTIC_FROZEN_ABILENE_SCENARIO_NOT_EXTERNAL_WAN_TELEMETRY"
        ),
        "legacy_mobility_energy_fields_ignored": [
            "energy_quantiles_kWh",
            "safe_energy_kWh",
            "e4b_template_id",
            "profile_safe_horizon_steps",
        ],
        "legacy_mobility_template_bank_loaded": False,
        "physical_execution_authority_version": (
            "V13_13_POST_HOC_P100_FEEDER_SCALE_NATIVE_ELASTIC_AC_FREEZE_20260823"
        ),
        "feeder_absolute_scale_contract_sha256": sha256(feeder_scale_path),
        "feeder_absolute_scale_alpha": feeder_scale,
        "common_native_grid_control_id": native_control_contract["identity"],
        "common_native_grid_control_dss_sha256": sha256(native_control_dss),
        "common_native_grid_control_authority_sha256": sha256(
            native_control_authority
        ),
        "native_grid_asset_audit_sha256": sha256(native_asset_audit),
        "predictive_native_dwell_guard_id": predictive_native_contract[
            "identity"
        ],
        "predictive_native_dwell_guard_authority_sha256": sha256(
            predictive_native_authority
        ),
        "predictive_native_forecast_horizon_steps": (
            PREDICTIVE_NATIVE_HORIZON_STEPS
        ),
        "predictive_native_future_actual_used": False,
        "runtime_contract_sha256": sha256(runtime_contract_path),
        "workload_admission_authority": (
            "CAUSAL_ARRIVAL_ORIGIN_PLACEMENT_ADMISSION_ONLY_PLAN_REVISION"
        ),
        "common_gpu_gang_scheduler": (
            "WORK_CONSERVING_LEAST_START_SLACK_EDF_CAPACITY_QUEUE_WHOLE_GANG"
        ),
        "non_temporal_compute_modulation_allowed": False,
        "native_grid_control_release_status": native_control_contract["status"],
        "main_scientific_campaign_authorized": campaign_authorized,
        "january_2025_post_hoc_validation_authorized": post_hoc_control_authorized,
        "evaluation_classification": evaluation_classification,
        "common_native_grid_control_applied_to": (
            [f"B{index:02d}" for index in range(10)]
            if args.electrical_stress_campaign
            else [f"B{index}" for index in range(8)]
        ),
        "original_ieee123_master_modified": False,
    }
    contract_sha = hashlib.sha256(json.dumps(evaluation_contract, sort_keys=True).encode()).hexdigest()
    authority = ExperimentAuthority(
        exogenous_inputs_sha256=sha256(args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"),
        initial_state_sha256=sha256(args.initial_state),
        grid_model_sha256=sha256_files(
            (
                Path(paths["assets"]) / "IEEE123Master.dss",
                native_control_dss,
            )
        ),
        jobs_sha256=sha256(args.canonical_jobs),
        wan_sha256=migration_authority.fingerprint,
        evaluation_coefficients_sha256=contract_sha,
        physical_ratings_sha256=sha256(Path(paths["assets"]) / "Generated_Planning_Line_Ratings_u080.dss"),
    )
    electrical_stress_selected = bool(
        args.electrical_stress_campaign
        or args.diagnostic_method
        in {method.value for method in ElectricalStressMethod}
    )
    power_curve = _load_curve(args.power_curve)
    h54_planner_class = (
        RetainedH54JointPlanner
        if args.h54_planner_backend == "full-miqcp-oracle"
        else PersistentBoundedMilpPlanner
    )
    retained_h54 = (
        h54_planner_class(
            repo=repo,
            base=args.retained_h54_base,
            output_root=output,
            power_curve=power_curve,
            gurobi_threads=int(os.environ.get("PFR_GUROBI_THREADS", "4")),
            legacy_causal_screening=(
                args.h54_planner_backend == "full-miqcp-oracle"
                and
                os.environ.get(
                    "PFR_EXPERIMENTAL_LEGACY_CAUSAL_SCREENING", "0"
                )
                == "1"
            ),
        )
        if electrical_stress_selected
        else None
    )
    runner = PfrRuntimeRunner(
        power_curve=power_curve,
        physical_backend=ExactOpenDssBackend(exact, paths),
        fast_optimizer=GurobiFastControlOptimizer(),
        native_control_initial_states={
            str(row["name"]).lower(): tuple(row["initial_state"])
            for row in native_asset_contract["capacitors"]
        },
        native_control_minimum_dwell_steps=int(
            float(
                native_control_contract[
                    "frozen_post_hoc_control_basis"
                ]["dead_time_seconds"]
            )
            // 300.0
        ),
        migration_authority=migration_authority,
        mobility_execution_authority=mobility_execution,
        risk_calibration_authority=risk_calibration,
        joint_planner=retained_h54,
        h0_fidelity_audit_every_steps=args.h0_fidelity_audit_every_steps,
        evaluation_period_id=evaluation_period_id,
        source_commit_sha=source_identity["git_full_commit_sha"],
        objective_contract_sha256=contract_sha,
    )
    factory = MethodFactory(authority)
    configs = (
        factory.electrical_stress_campaign()
        if args.electrical_stress_campaign
        else factory.all()
    )
    single_method_id = (
        ComparisonMethod.B8.value
        if args.supplementary_b8_periodic_5min
        else args.diagnostic_method
    )
    if single_method_id:
        config = (
            factory.create_electrical_stress(ElectricalStressMethod(single_method_id))
            if single_method_id in {method.value for method in ElectricalStressMethod}
            else factory.create(ComparisonMethod(single_method_id))
        )
        method = runner.run_method(
            config=config,
            frames=frames,
            initial=initial,
            representative_week_id=args.candidate_id,
            output=output,
            simulation_calendar_date=args.calendar_date,
            diagnostic_resume_state=diagnostic_resume_state,
            diagnostic_resume_cumulative_grid_cost_aud=(
                diagnostic_resume_cumulative_grid_cost_aud
            ),
            diagnostic_prefix_records=diagnostic_prefix_records,
            diagnostic_checkpoint_after_issue=(
                args.diagnostic_checkpoint_after_issue
            ),
            diagnostic_stop_after_issue=args.diagnostic_stop_after_issue,
            restart_checkpoint_interval=args.restart_checkpoint_interval,
        )
        matrix = {
            "schema_version": (
                "K9H7_RESULT_V2.supplementary_b8_periodic_5min.v1"
                if args.supplementary_b8_periodic_5min
                else "K9H7_RESULT_V2.diagnostic_single_method.v1"
            ),
            "status": method["status"],
            "representative_week_id": args.candidate_id,
            "method_count": 1,
            "diagnostic_method": args.diagnostic_method,
            "supplementary_method": (
                ComparisonMethod.B8.value
                if args.supplementary_b8_periodic_5min
                else None
            ),
            "comparison_scope": (
                "POST_HOC_SUPPLEMENTARY_TIMING_BASELINE"
                if args.supplementary_b8_periodic_5min
                else "TECHNICAL_DIAGNOSTIC_ONLY"
            ),
            "issues_per_method": int(method["requested_issues"]),
            "expected_commit_markers": int(method["requested_issues"]),
            "valid_commit_markers": method["committed_issues"],
            "all_fresh_exact_opendss": (
                method["fresh_exact_opendss_count"]
                == int(method["requested_issues"])
            ),
            "all_actual_gurobi": (
                method["actual_gurobi_count"]
                == int(method["requested_issues"])
            ),
            "all_state_chains_complete": method["state_chain_complete"],
            "all_binary_states_unchanged_in_fast_layer": method["binary_state_unchanged"],
            "future_actual_used": False,
            "failed_methods": (
                []
                if method["status"] in {"PASS", "DIAGNOSTIC_STOP"}
                else [single_method_id]
            ),
            "method_failures_isolated": True,
            "continue_to_next_method_after_failure": True,
            "method_execution_order": [single_method_id],
            "methods": [method],
        }
        temporary_summary = output / "MATRIX_SUMMARY.json.tmp"
        temporary_summary.write_text(
            json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_summary.replace(output / "MATRIX_SUMMARY.json")
    else:
        matrix = runner.run_matrix(
            configs=configs,
            frames=frames,
            initial=initial,
            representative_week_id=args.candidate_id,
            output=output,
            simulation_calendar_date=args.calendar_date,
            reuse_passed_methods=args.reuse_passed_methods,
        )
    manifest = {
        "status": matrix["status"],
        "candidate_id": args.candidate_id,
        "start_issue": args.start_issue,
        "count": args.count,
        "exact_prefix_resume": {
            "used": bool(diagnostic_prefix_records),
            "checkpoint_path": (
                str(args.diagnostic_resume_checkpoint.resolve())
                if args.diagnostic_resume_checkpoint is not None
                else None
            ),
            "checkpoint_sha256": (
                sha256(args.diagnostic_resume_checkpoint.resolve())
                if args.diagnostic_resume_checkpoint is not None
                else None
            ),
            "prefix_output": (
                str(args.diagnostic_resume_prefix_output.resolve())
                if args.diagnostic_resume_prefix_output is not None
                else None
            ),
            "prefix_issue_count": len(diagnostic_prefix_records),
            "prefix_first_issue": (
                int(diagnostic_prefix_records[0]["issue"])
                if diagnostic_prefix_records
                else None
            ),
            "prefix_last_issue": (
                int(diagnostic_prefix_records[-1]["issue"])
                if diagnostic_prefix_records
                else None
            ),
            "prefix_checkpoint_state_chain_match": bool(
                diagnostic_prefix_records
                and diagnostic_resume_state is not None
                and diagnostic_prefix_records[-1]["post_state_sha256"]
                == diagnostic_resume_state.pre_state_sha256
            ),
        },
        "shared_authority_fingerprint": authority.fingerprint,
        "method_ids": [config.comparison_method_id.value for config in configs]
        if not single_method_id
        else [single_method_id],
        "method_id": single_method_id,
        "method_reuse": {
            "enabled": bool(args.reuse_passed_methods),
            "reused_passed_methods": list(
                matrix.get("reused_passed_methods", [])
            ),
            "executed_methods": list(matrix.get("executed_methods", [])),
        },
        "methods": [
            {
                **asdict(config),
                "comparison_method_id": config.comparison_method_id.value,
                "method_id": config.comparison_method_id.value,
                "method_name": config.label,
                "method_order": int(config.comparison_method_id.value[1:]),
                "h54_capability_mask": dict(config.h54_capability_mask),
                "controller_type": config.control_mode,
                "risk_calibration": config.risk_interface == "CALIBRATED",
                "full_replan_interval": (
                    f"EVERY_{config.periodic_replan_steps}_STEPS"
                    if config.periodic_replan_steps is not None
                    else "EVENT_WITH_MAX_REFRESH"
                ),
                "factorial_energy": (
                    int(config.energy_flexibility == "MESS")
                    if config.comparison_method_id.value
                    in {method.value for method in FACTORIAL_ELECTRICAL_STRESS_CELLS.values()}
                    else None
                ),
                "factorial_compute": (
                    int(config.temporal_workload_shift and config.spatial_workload_migration)
                    if config.comparison_method_id.value
                    in {method.value for method in FACTORIAL_ELECTRICAL_STRESS_CELLS.values()}
                    else None
                ),
            }
            for config in (
                configs
                if not single_method_id
                else (config,)
            )
        ],
        "objective_id": OBJECTIVE_AUTHORITY,
        "objective_version": "V1",
        "objective_primary": "MIN_MAX_PREDICTED_AC_STRESS",
        "objective_secondary": "MIN_STRESS_EXPOSURE",
        "objective_tertiary": "MIN_ACTUATION",
        "stress_definition_version": "ELECTRICAL_STRESS_OBJECTIVE_V1",
        "objective_contract_sha256": sha256(
            repo / "pfr/contracts/ELECTRICAL_STRESS_OBJECTIVE_V1.json"
        ),
        "method_registry_contract_sha256": sha256(
            repo / "pfr/contracts/ELECTRICAL_STRESS_METHOD_REGISTRY_V1.json"
        ),
        "result_schema_version": "ELECTRICAL_STRESS_RESULT_SCHEMA_V1",
        "result_schema_contract_sha256": sha256(
            repo / "pfr/contracts/ELECTRICAL_STRESS_RESULT_SCHEMA_V1.json"
        ),
        "retained_h54_adapter": {
            "connected": retained_h54 is not None,
            "backend_role": args.h54_planner_backend,
            "adapter_id": (
                ADAPTER_ID
                if retained_h54 is not None
                and args.h54_planner_backend == "full-miqcp-oracle"
                else (
                    ONLINE_MILP_ADAPTER_ID if retained_h54 is not None else None
                )
            ),
            "retained_entrypoint": (
                "science/main.py::build_full"
                if args.h54_planner_backend == "full-miqcp-oracle"
                else "pfr/persistent_bounded_milp.py::PersistentBoundedMilpPlanner"
            ),
            "adapter_source_sha256": (
                sha256(
                    repo
                    / (
                        "pfr/retained_h54.py"
                        if args.h54_planner_backend == "full-miqcp-oracle"
                        else "pfr/persistent_bounded_milp.py"
                    )
                )
                if retained_h54 is not None
                else None
            ),
            "online_solver_contract": (
                ONLINE_MILP_SOLVER_CONTRACT
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "online_solver_contract_sha256": (
                sha256(
                    repo
                    / "pfr/contracts/HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_MPC_V1.json"
                )
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "paper_facing_online_backend": (
                "Hierarchical Move-Blocked Mixed-Integer MPC with Causal Domain Reduction"
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "slow_master_grid_minutes": (
                30
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "slow_master_stage_count": (
                9
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "fixed_slow_decision_exact_h54_qcp_recourse": (
                args.h54_planner_backend == "online-bounded"
                and os.environ.get(
                    "PFR_NORM_CONSTRAINT_MODE", "INNER_POLYGON"
                ).upper()
                == "EXACT_QCP"
                if retained_h54 is not None
                else None
            ),
            "fixed_slow_decision_h54_recourse_norm_model": (
                os.environ.get(
                    "PFR_NORM_CONSTRAINT_MODE", "INNER_POLYGON"
                ).upper()
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "gurobi_slow_master_numeric_focus": (
                0
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "gurobi_exact_recourse_numeric_focus": (
                2
                if retained_h54 is not None
                and args.h54_planner_backend == "online-bounded"
                else None
            ),
            "gurobi_crossover": "AUTO",
            "gurobi_multi_objective_presolve": "AUTO",
            "retained_solver_source_sha256": (
                sha256(repo / "science/main.py")
                if retained_h54 is not None
                else None
            ),
            "retained_base": (
                str(args.retained_h54_base.resolve())
                if retained_h54 is not None
                else None
            ),
            "planning_horizon_steps": 54,
            "forecast_semantics": "ISSUE_CAUSAL_RUNTIME_H54_OVERRIDE",
            "price_role": "EX_POST_KPI_ONLY_NOT_OPTIMIZER_OBJECTIVE",
            "full_miqcp_in_online_loop": False,
            "restricted_online_decision_domain": (
                args.h54_planner_backend == "online-bounded"
            ),
        },
        "config_sha256": hashlib.sha256(
            json.dumps(
                [
                    {
                        **asdict(item),
                        "comparison_method_id": item.comparison_method_id.value,
                    }
                    for item in (
                        configs if not single_method_id else (config,)
                    )
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "shared_exogenous_authority_sha256": sha256(
            args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
        ),
        "exogenous_input_sha256": sha256(
            args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
        ),
        "forecast_model_sha256": hashlib.sha256(
            json.dumps(
                {
                    "shared_exogenous_authority": sha256(
                        args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
                    ),
                    "factorized_uncertainty": sha256(args.factorized_uncertainty),
                    "workload_uncertainty": sha256(args.workload_uncertainty),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "network_model_sha256": authority.grid_model_sha256,
        "rating_contract_sha256": authority.physical_ratings_sha256,
        "initial_state_sha256": authority.initial_state_sha256,
        "shared_exogenous_authority_path": str(
            (args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json").resolve()
        ),
        "evaluation_contract": evaluation_contract,
        "mobility_execution_authority_path": str(
            mobility_execution_path.resolve()
        ),
        "mobility_execution_authority_sha256": mobility_execution.fingerprint,
        "mobility_execution_time_authority": mobility_execution.AUTHORITY_ID,
        "mobility_execution_post_decision_only": True,
        "mobility_execution_actual_used_by_optimizer": False,
        "mobility_prediction_actual_error_materialized": True,
        "migration_prediction_actual_error_materialized": True,
        "risk_calibration_authority_path": (
            str(args.risk_calibration.resolve())
            if args.risk_calibration is not None
            else None
        ),
        "risk_calibration_authority_id": (
            risk_calibration.authority_id
            if risk_calibration is not None
            else None
        ),
        "risk_calibration_artifact_sha256": (
            risk_calibration.artifact_sha256
            if risk_calibration is not None
            else None
        ),
        "risk_calibration_sha256": (
            risk_calibration.artifact_sha256
            if risk_calibration is not None
            else None
        ),
        "risk_calibration_march_outcomes_read": False,
        "migration_realization_classification": (
            "DETERMINISTIC_FROZEN_ABILENE_SCENARIO_NOT_EXTERNAL_WAN_TELEMETRY"
        ),
        "migration_authority_path": str(migration_authority_path),
        "migration_authority_sha256": migration_authority.fingerprint,
        "migration_contract_sha256": migration_authority.contract_fingerprint,
        "migration_authority_id": migration_authority.authority_id,
        "checkpoint_payload_occupancy_factor": (
            migration_authority.checkpoint_payload_occupancy_factor
        ),
        **source_identity,
        "git_commit_sha": source_identity["git_full_commit_sha"],
        "actual_gurobi_used": matrix["all_actual_gurobi"],
        "actual_fresh_opendss_used": matrix["all_fresh_exact_opendss"],
        "opendss_metrics_common_sha256": sha256(args.exact_package_root / "opendss_metrics_common.py"),
        "full_scientific_daily_episode_issues": 288,
        "bounded_regression_not_full_scientific_episode": args.count != 288,
        "diagnostic_single_method": args.diagnostic_method,
        "supplementary_b8_periodic_5min": args.supplementary_b8_periodic_5min,
        "comparison_scope": (
            "POST_HOC_SUPPLEMENTARY_TIMING_BASELINE"
            if args.supplementary_b8_periodic_5min
                else (
                    "FROZEN_B00_B09_ELECTRICAL_STRESS_CAMPAIGN"
                    if args.electrical_stress_campaign
                    else "FROZEN_B0_B7_MAIN_OR_TECHNICAL_DIAGNOSTIC"
                )
            ),
        "independent_daily_cold_start": (
            pre is not None and "canonical_pre" in pre
        ),
        "cross_day_endogenous_state_carryover": False,
        "controller_burn_in_steps": 0,
        "factorized_uncertainty_decision_use": {
            "U_mob": "CAUSAL_ETA_Q10_Q50_Q90_TO_DETERMINISTIC_PHYSICS",
            "U_work": "SITE_GPU_CAPACITY_AND_PLAN_VALIDITY_RISK",
            "U_grid": "CAUSAL_ADAPTIVE_ENVELOPE_PLAN_VALIDITY_DIAGNOSTIC",
        },
        "fresh_opendss_commit_gate": "REALIZED_H0_ONLY",
        "robust_grid_forecast_is_commit_gate": False,
        "future_actual_used": False,
        "scientific_implementation_fingerprint": scientific_implementation_fingerprint(
            repo
        ),
        "physical_execution_authority_version": (
            "V13_13_POST_HOC_P100_FEEDER_SCALE_NATIVE_ELASTIC_AC_FREEZE_20260823"
        ),
        "scientific_framework_id": "V14_AI_ICPS",
        "evaluation_period_id": evaluation_period_id,
        "final_evaluation_authority_path": (
            str(final_evaluation_authority_path)
            if final_evaluation_authority_path is not None
            else None
        ),
        "final_evaluation_authority_sha256": (
            sha256(final_evaluation_authority_path)
            if final_evaluation_authority_path is not None
            else None
        ),
        "main_scientific_campaign_authorized": campaign_authorized,
        "evaluation_classification": evaluation_classification,
        "independent_holdout_claim": False,
        "common_native_grid_control": {
            "identity": native_control_contract["identity"],
            "common_to_B0_B7": True,
            "also_applied_to_supplementary_B8": (
                args.supplementary_b8_periodic_5min
            ),
            "original_ieee123_master_modified": False,
            "dss_sha256": sha256(native_control_dss),
            "authority_sha256": sha256(native_control_authority),
            "asset_audit_sha256": sha256(native_asset_audit),
            "release_status": native_control_contract["status"],
            "main_scientific_campaign_authorized": frozen_control_authorized,
            "authorized_via_final_evaluation_authority": (
                final_evaluation_authorized
            ),
            "january_2025_post_hoc_validation_authorized": post_hoc_control_authorized,
            "diagnostic_candidate_override": pending_diagnostic_authorized,
        },
        "predictive_native_dwell_guard": {
            "identity": predictive_native_contract["identity"],
            "authority_sha256": sha256(predictive_native_authority),
            "horizon_steps": PREDICTIVE_NATIVE_HORIZON_STEPS,
            "lead_steps": [1, PREDICTIVE_NATIVE_HORIZON_STEPS],
            "future_actual_used": False,
            "common_to_methods": predictive_native_contract[
                "common_to_methods"
            ],
        },
    }
    temporary_manifest = output / "RUN_MANIFEST.json.tmp"
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_manifest.replace(output / "RUN_MANIFEST.json")
    print(json.dumps({"status": matrix["status"], "markers": matrix["valid_commit_markers"], "output": str(output)}))
    if matrix["status"] not in {"PASS", "DIAGNOSTIC_STOP"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
