#!/usr/bin/env python3
"""Write fixed-schedule Actual replay contracts."""

from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    gate = {
        "artifact_id": "V28_ACTUAL_EXECUTION_GATE_CONTRACT_V1",
        "input": ["FROZEN_DAY_AHEAD_SCHEDULE", "REALIZED_D_DAY_INPUTS", "PREDEFINED_EXECUTION_GATES"],
        "optimizer_imports": [], "actual_reoptimization_calls": 0,
        "event_trigger_calls": 0, "local_repair_calls": 0, "rolling_update_calls": 0,
        "schedule_hash_verified_before_actual_namespace": True,
        "command_time_shift_allowed": False, "replacement_optimization_allowed": False,
    }
    aidc = {
        "artifact_id": "V28_AIDC_ACTUAL_DECOMPOSITION_CONTRACT_V1",
        "residual_formula": "P_IT_RES_ACT=P_IT_ACT_NATURAL-P_FLEX_ACT_NATURAL",
        "replay_formula": "P_IT_REPLAY=P_IT_RES_ACT+P_FLEX_EXEC",
        "negative_residual_clipping": False,
        "negative_residual_failure": "FAIL_AIDC_ACTUAL_DECOMPOSITION",
        "x_EXEC_lower": 0, "x_EXEC_upper": "x_DA_and_actual_available",
        "extra_realized_workload": "EXPLICIT_BACKLOG_OR_FROZEN_NATURAL_RESIDUAL",
        "hidden_shedding_GPU_h": 0,
    }
    mess = {
        "artifact_id": "V28_MESS_ACTUAL_EXECUTION_CONTRACT_V1",
        "physically_unavailable": "P_EXEC=Q_EXEC=0_WITH_EXPLICIT_REASON",
        "travel_energy_or_SOC_infeasible": "COMMAND_NOT_EXECUTED",
        "execute_later": False, "substitute_vehicle": False,
        "optimizer_calls": 0,
    }
    opendss = {
        "artifact_id": "V28_ACTUAL_OPENDSS_BINDING_V1", "slots": 96,
        "inputs": ["realized_grid", "realized_PV", "C1_replayed_AIDC_PCC", "executed_MESS_commands"],
        "native_controls_same_as_dayahead": True, "local_repair": False,
    }
    model = {
        "artifact_id": "FINAL_ACTUAL_REPLAY_MODEL_V1", "status": "IMPLEMENTATION_READY",
        "execution_gate": gate, "AIDC_decomposition": aidc, "MESS_execution": mess,
        "natural_reference": "R0_NATURAL_REALIZED_REFERENCE_NOT_AN_OPTIMIZATION_POLICY",
        "opendss": opendss,
    }
    write("V28_ACTUAL_EXECUTION_GATE_CONTRACT.json", gate)
    write("V28_AIDC_ACTUAL_DECOMPOSITION_CONTRACT.json", aidc)
    write("V28_MESS_ACTUAL_EXECUTION_CONTRACT.json", mess)
    write("V28_ACTUAL_OPENDSS_BINDING.json", opendss)
    write("FINAL_ACTUAL_REPLAY_MODEL_V1.json", model)
    (OUT / "FINAL_ACTUAL_REPLAY_MODEL_V1.md").write_text("# Final Actual replay model V1\n\nActual opens only after the Day-Ahead schedule SHA is frozen. Every action is a gated execution of an existing command; no optimizer, time shift, local repair, or substitute vehicle is available.\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
