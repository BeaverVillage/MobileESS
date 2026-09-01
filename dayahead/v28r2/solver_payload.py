"""Canonical complete primal payload returned by every V28R2 solver."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .backend_contract import canonical_sha256
from .formulation import DT_HOURS
from .variable_registry import VariableRegistry


@dataclass(frozen=True)
class SolverPayload:
    case: str
    solver: str
    objective: float | None
    status: str
    hard_feasible: bool
    incumbent: float | None
    lower_bound: float | None
    upper_bound: float | None
    gap: float | None
    iterations: int
    optimality_cuts: int
    feasibility_cuts: int
    termination_reason: str
    runtime_seconds: float
    controls: list[list[float]]
    workload_service_tensor: list[list[list[float]]]
    aidc_rack_cohort_allocation: Mapping[str, object]
    site_it_power_kw: list[list[float]]
    rack_it_power_kw: list[list[float]]
    rack_gpu: list[list[float]]
    site_gpu: list[list[float]]
    planning_pcc_power_kw: list[list[float]]
    planning_pcc_reactive_kvar: list[list[float]]
    mess_p_kw: list[list[float]]
    mess_q_kvar: list[list[float]]
    mess_soc_kwh: list[list[float]]
    mess_route_location: Mapping[str, object]
    backlog_nodeh: list[list[float]]
    feasibility_residuals: Mapping[str, float]
    formulation_fingerprint: str
    input_sha256: str

    def validate(self) -> None:
        if self.case not in {"B0", "B1", "B2", "B3"}:
            raise ValueError("V28R2_PAYLOAD_CASE")
        if self.solver not in {"MONOLITHIC", "STANDARD_BD", "CL_MC_BD"}:
            raise ValueError("V28R2_PAYLOAD_SOLVER")
        arrays = {
            "controls": np.asarray(self.controls),
            "workload": np.asarray(self.workload_service_tensor),
            "site_it": np.asarray(self.site_it_power_kw),
            "rack_it": np.asarray(self.rack_it_power_kw),
            "rack_gpu": np.asarray(self.rack_gpu),
            "site_gpu": np.asarray(self.site_gpu),
            "pcc": np.asarray(self.planning_pcc_power_kw),
            "q": np.asarray(self.planning_pcc_reactive_kvar),
            "mess_p": np.asarray(self.mess_p_kw),
            "mess_q": np.asarray(self.mess_q_kvar),
            "soc": np.asarray(self.mess_soc_kwh),
            "backlog": np.asarray(self.backlog_nodeh),
        }
        expected = {
            "controls": (96, 60), "workload": (15, 48, 96),
            "site_it": (96, 12), "rack_it": (96, 48),
            "rack_gpu": (96, 48), "site_gpu": (96, 12), "pcc": (96, 12),
            "q": (96, 12), "mess_p": (96, 4), "mess_q": (96, 4),
            "soc": (97, 4), "backlog": (97, 15),
        }
        if any(arrays[name].shape != shape or not np.isfinite(arrays[name]).all() for name, shape in expected.items()):
            raise ValueError("V28R2_PAYLOAD_ARRAY_SHAPE_OR_FINITE")
        if self.hard_feasible and (self.objective is None or max(self.feasibility_residuals.values(), default=0.0) > 1e-5):
            raise ValueError("V28R2_PAYLOAD_FALSE_FEASIBILITY")
        if len(self.formulation_fingerprint) != 64 or len(self.input_sha256) != 64:
            raise ValueError("V28R2_PAYLOAD_FINGERPRINT")

    def canonical_payload(self) -> dict[str, object]:
        self.validate()
        payload = asdict(self)
        payload["LB"] = self.lower_bound
        payload["UB"] = self.upper_bound
        return payload

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256({
            key: value for key, value in self.canonical_payload().items()
            if key in {
                "case", "controls", "workload_service_tensor", "aidc_rack_cohort_allocation",
                "site_it_power_kw", "rack_it_power_kw", "rack_gpu", "site_gpu",
                "planning_pcc_power_kw",
                "planning_pcc_reactive_kvar", "mess_p_kw", "mess_q_kvar",
                "mess_soc_kwh", "mess_route_location", "backlog_nodeh",
                "formulation_fingerprint", "input_sha256",
            }
        })

    def write(self, path: Path) -> None:
        payload = self.canonical_payload()
        payload["schedule_sha256"] = self.schedule_sha256
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8", newline="\n",
        )
        os.replace(temporary, path)


def payload_from_registry(
    registry: VariableRegistry, *, solver: str, status: str, hard_feasible: bool,
    objective: float | None, lower_bound: float | None, upper_bound: float | None,
    gap: float | None, iterations: int, optimality_cuts: int,
    feasibility_cuts: int, termination_reason: str, runtime_seconds: float,
) -> SolverPayload:
    arrays = registry.primal_arrays()
    data = registry.data
    x = arrays["workload_service_nodeh"]
    backlog = arrays["backlog_nodeh"]
    served = x.sum(axis=1).T
    balance = backlog[1:] - backlog[:-1] - data.arrivals_nodeh + served
    terminal = backlog[-1] - data.reference.backlog_nodeh[-1]
    gpu_violation = arrays["rack_gpu"] - data.rack_gpu_capacity[None, :]
    coefficients = data.c1_by_site_slot
    c1_error = max(
        abs(
            arrays["site_pcc_power_kw"][slot, aidc_index]
            - coefficients[(aidc, slot)].slope * arrays["site_it_power_kw"][slot, aidc_index]
            - coefficients[(aidc, slot)].intercept_kw
        )
        for aidc_index, aidc in enumerate(data.aidc_ids) for slot in range(96)
    )
    mess_terminal = arrays["mess_soc_kwh"][-1] - 760.0
    residuals = {
        "workload_balance_max_abs_nodeh": float(np.max(np.abs(balance))),
        "terminal_backlog_parity_max_abs_nodeh": float(np.max(np.abs(terminal))),
        "negative_service_max_nodeh": float(max(0.0, -float(x.min()))),
        "rack_gpu_capacity_violation_max": float(max(0.0, float(gpu_violation.max()))),
        "c1_affine_equality_max_abs_kw": float(c1_error),
        "mess_terminal_soc_max_abs_kwh": float(np.max(np.abs(mess_terminal))),
        "model_constraint_violation": float(getattr(registry.model, "ConstrVio", 0.0)),
    }
    route = {
        mess_id: {
            "service_site": str(record["service_site"]),
            "mode_96": list(record["mode_96"]),
            "location_96": list(record["location_96"]),
            "available_96": list(record["available_96"]),
        }
        for mess_id, record in sorted(data.mess_records.items())
    }
    payload = SolverPayload(
        case=registry.case, solver=solver, objective=objective, status=status,
        hard_feasible=hard_feasible, incumbent=objective,
        lower_bound=lower_bound, upper_bound=upper_bound, gap=gap,
        iterations=iterations, optimality_cuts=optimality_cuts,
        feasibility_cuts=feasibility_cuts, termination_reason=termination_reason,
        runtime_seconds=runtime_seconds, controls=arrays["controls_96x60"].tolist(),
        workload_service_tensor=x.tolist(),
        aidc_rack_cohort_allocation={
            "cohort_ids": list(data.cohort_ids), "rack_ids": list(data.rack_ids),
            "rack_aidc": list(data.rack_aidc), "tensor_order": "cohort,rack,slot",
        },
        site_it_power_kw=arrays["site_it_power_kw"].tolist(),
        rack_it_power_kw=arrays["rack_it_power_kw"].tolist(),
        rack_gpu=arrays["rack_gpu"].tolist(), site_gpu=arrays["site_gpu"].tolist(),
        planning_pcc_power_kw=arrays["site_pcc_power_kw"].tolist(),
        planning_pcc_reactive_kvar=arrays["site_pcc_reactive_kvar"].tolist(),
        mess_p_kw=arrays["mess_p_kw"].tolist(),
        mess_q_kvar=arrays["mess_q_kvar"].tolist(),
        mess_soc_kwh=arrays["mess_soc_kwh"].tolist(),
        mess_route_location=route, backlog_nodeh=backlog.tolist(),
        feasibility_residuals=residuals,
        formulation_fingerprint=data.formulation_fingerprint,
        input_sha256=data.input_sha256,
    )
    payload.validate()
    return payload
