"""Exact background+PV+native-control feasibility scan with zero IDC/MESS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any

from pfr.runtime import IDCS, MESS_IDS
from pfr.tools.run_pfr_matrix import (
    ExactOpenDssBackend,
    _load_exact_module,
    json_load,
    sha256,
)


ZERO_FACILITY = tuple(0.0 for _ in IDCS)
ZERO_MESS = tuple(0.0 for _ in MESS_IDS)
MESS_LOCATIONS = ("STA09", "IDC12", "STA07", "STA11")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--start-issue", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--exact-package-root", type=Path, required=True)
    parser.add_argument("--authority-package-root", type=Path, required=True)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.start_issue < 0 or args.count <= 0:
        parser.error("--start-issue must be nonnegative and --count positive")

    repo = args.repo.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    gate_path = repo / "pfr/contracts/BACKGROUND_NATIVE_FEASIBILITY_GATE_V1.json"
    native_path = repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json"
    native_dss = repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.dss"
    asset_path = repo / "pfr/contracts/IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1.json"
    gate = json_load(gate_path)
    native = json_load(native_path)
    assets = json_load(asset_path)
    if gate.get("status") != "FROZEN_POST_HOC_GATE":
        raise RuntimeError("background-native gate is not frozen")

    exact = _load_exact_module(repo, args.exact_package_root)
    source_work = output / "_exact_source_work"
    if source_work.exists():
        shutil.rmtree(source_work)
    source_work.mkdir(parents=True)
    paths = exact.prepare_sources(
        args.authority_package_root.resolve(),
        source_work,
        v2038_root=str(args.exact_package_root.resolve()),
        primary_root=str(args.primary_root.resolve()),
    )
    paths["native_grid_control"] = str(native_dss.resolve())
    paths["feeder_scale_contract"] = str(
        (repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json").resolve()
    )
    backend = ExactOpenDssBackend(exact, paths)

    capacitor_states = {
        str(row["name"]).lower(): tuple(int(value) for value in row["initial_state"])
        for row in assets["capacitors"]
    }
    regulator_taps: dict[str, int] = {}
    dwell = {name: 0 for name in capacitor_states}
    minimum_dwell_steps = int(
        float(native["frozen_post_hoc_control_basis"]["dead_time_seconds"])
        // 300.0
    )
    rows: list[dict[str, Any]] = []
    failures = []
    for issue in range(args.start_issue, args.start_issue + args.count):
        locked = tuple(name for name, remaining in dwell.items() if remaining > 0)
        decision = backend.select_native_control(
            issue=issue,
            facility_p_kw=ZERO_FACILITY,
            facility_q_kvar=ZERO_FACILITY,
            mess_location=MESS_LOCATIONS,
            mess_p_kw=ZERO_MESS,
            mess_q_kvar=ZERO_MESS,
            mess_in_transit=tuple(False for _ in MESS_IDS),
            previous_capacitor_states=capacitor_states,
            previous_regulator_taps=regulator_taps,
            locked_capacitors=locked,
        )
        commit = backend.verify_fresh(
            issue=issue,
            facility_p_kw=ZERO_FACILITY,
            facility_q_kvar=ZERO_FACILITY,
            mess_location=MESS_LOCATIONS,
            mess_p_kw=ZERO_MESS,
            mess_q_kvar=ZERO_MESS,
            mess_in_transit=tuple(False for _ in MESS_IDS),
            robust_background_p_kw=(),
            robust_background_q_kvar=(),
            robust_pv_available_kw=(),
            native_capacitor_states=decision.states,
            native_regulator_taps=decision.regulator_taps,
        )
        exact_result = commit.exact
        row = {
            "issue": issue,
            "passed": exact_result.passed,
            "voltage_min_pu": exact_result.minimum_voltage_pu,
            "voltage_max_pu": exact_result.maximum_voltage_pu,
            "line_max_loading_pu": exact_result.maximum_line_loading_fraction,
            "transformer_max_loading_pu": exact_result.maximum_transformer_loading_fraction,
            "native_capacitor_states": {
                name: list(values) for name, values in decision.states.items()
            },
            "native_regulator_taps": dict(decision.regulator_taps),
            "native_candidates_evaluated": decision.raw_metrics[
                "global_guard_candidates_evaluated"
            ],
        }
        rows.append(row)
        if not exact_result.passed:
            failures.append(row)

        previous = capacitor_states
        capacitor_states = {
            name: tuple(values) for name, values in decision.states.items()
        }
        for name, values in capacitor_states.items():
            if tuple(previous.get(name, values)) != tuple(values):
                dwell[name] = minimum_dwell_steps
            else:
                dwell[name] = max(0, dwell.get(name, 0) - 1)
        regulator_taps = {
            name: int(value) for name, value in decision.regulator_taps.items()
        }

    passed = not failures
    payload = {
        "schema_version": "BACKGROUND_NATIVE_FEASIBILITY_GATE_V1.result.v1",
        "status": (
            "PASS_KEEP_CURRENT_PHYSICAL_SCALE"
            if passed
            else "FAIL_CONTROLLER_REACHABILITY_CERTIFICATE_REQUIRED_NOT_SCALE_TRIGGER"
        ),
        "start_issue": args.start_issue,
        "count": args.count,
        "passed_issues": args.count - len(failures),
        "failed_issues": len(failures),
        "scale_redesign_triggered": False,
        "complete_legal_state_infeasibility_certificates": 0,
        "zero_idc": True,
        "zero_mess": True,
        "hard_limits_relaxed": False,
        "gate_contract_sha256": sha256(gate_path),
        "native_control_authority_sha256": sha256(native_path),
        "issues": rows,
    }
    (output / "BACKGROUND_NATIVE_FEASIBILITY_GATE.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: payload[key] for key in ("status", "passed_issues", "failed_issues")}))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
