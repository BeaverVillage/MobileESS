"""Freeze and independently verify all four operational Day-Ahead schedules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from .backend_contract import canonical_sha256, sha256_file
from .day_state import atomic_json
from .solver_payload import SolverPayload


OPERATIONAL_SOLVER = {
    "B0": "MONOLITHIC", "B1": "MONOLITHIC", "B2": "MONOLITHIC", "B3": "CL_MC_BD",
}


def _schedule(payload: SolverPayload, reference_sha256: str) -> dict[str, object]:
    source = payload.canonical_payload()
    fields = (
        "case", "controls", "workload_service_tensor", "aidc_rack_cohort_allocation",
        "site_it_power_kw", "rack_it_power_kw", "rack_gpu", "site_gpu",
        "planning_pcc_power_kw",
        "planning_pcc_reactive_kvar", "mess_p_kw", "mess_q_kvar", "mess_soc_kwh",
        "mess_route_location", "backlog_nodeh", "formulation_fingerprint", "input_sha256",
    )
    result = {field: source[field] for field in fields}
    result["solver"] = payload.solver
    result["reference_schedule_sha256"] = reference_sha256
    result["schedule_sha256"] = canonical_sha256(result)
    return result


def freeze_dayahead_schedules(
    output: Path, payloads: Mapping[str, SolverPayload], reference_bytes: bytes,
) -> dict[str, object]:
    if set(payloads) != set(OPERATIONAL_SOLVER):
        raise ValueError("V28R2_ALL_OPERATIONAL_CASES_REQUIRED")
    fingerprints = {payload.formulation_fingerprint for payload in payloads.values()}
    inputs = {payload.input_sha256 for payload in payloads.values()}
    if len(fingerprints) != 1 or len(inputs) != 1:
        raise RuntimeError("V28R2_OPERATIONAL_FORMULATION_OR_INPUT_MISMATCH")
    b0_compute_sha = canonical_sha256(payloads["B0"].workload_service_tensor)
    b2_compute_sha = canonical_sha256(payloads["B2"].workload_service_tensor)
    if b0_compute_sha != b2_compute_sha:
        raise RuntimeError("V28R2_B0_B2_REFERENCE_COMPUTE_MISMATCH")
    reference_sha = hashlib.sha256(reference_bytes).hexdigest()
    files = {}
    for case in ("B0", "B1", "B2", "B3"):
        payload = payloads[case]
        payload.validate()
        if payload.solver != OPERATIONAL_SOLVER[case] or not payload.hard_feasible:
            raise RuntimeError(f"V28R2_OPERATIONAL_SOLVER_BINDING:{case}")
        path = output / f"DAYAHEAD_{case}_SCHEDULE.json"
        atomic_json(path, _schedule(payload, reference_sha))
        files[case] = {
            "path": str(path.resolve()), "file_sha256": sha256_file(path),
            "schedule_sha256": json.loads(path.read_text(encoding="utf-8"))["schedule_sha256"],
            "solver": payload.solver,
        }
    root_sha = canonical_sha256({case: files[case]["file_sha256"] for case in sorted(files)})
    manifest = {
        "artifact_id": "DAYAHEAD_SCHEDULE_MANIFEST_V28R2_V1",
        "status": "FROZEN",
        "cases": files,
        "reference_schedule_sha256": reference_sha,
        "B0_B2_reference_schedule_bytes_identical": True,
        "B0_B2_workload_service_sha256": b0_compute_sha,
        "formulation_fingerprint": payloads["B0"].formulation_fingerprint,
        "input_sha256": payloads["B0"].input_sha256,
        "schedule_root_sha256": root_sha,
        "actual_namespace_open_before_DA_freeze": 0,
        "future_actual_reads_before_DA_freeze": 0,
    }
    atomic_json(output / "DAYAHEAD_SCHEDULE_MANIFEST.json", manifest)
    return manifest


def verify_schedule_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cases = manifest.get("cases", {})
    if set(cases) != set(OPERATIONAL_SOLVER):
        raise RuntimeError("V28R2_SCHEDULE_MANIFEST_CASE_AXIS")
    recomputed = {}
    workload_sha = {}
    for case, record in cases.items():
        schedule_path = Path(record["path"])
        if not schedule_path.is_file() or sha256_file(schedule_path) != record["file_sha256"]:
            raise RuntimeError(f"V28R2_SCHEDULE_FILE_SHA:{case}")
        payload = json.loads(schedule_path.read_text(encoding="utf-8"))
        stored = payload.pop("schedule_sha256", None)
        if stored != canonical_sha256(payload) or stored != record["schedule_sha256"]:
            raise RuntimeError(f"V28R2_SCHEDULE_PAYLOAD_SHA:{case}")
        recomputed[case] = record["file_sha256"]
        workload_sha[case] = canonical_sha256(payload["workload_service_tensor"])
    if manifest.get("schedule_root_sha256") != canonical_sha256({case: recomputed[case] for case in sorted(recomputed)}):
        raise RuntimeError("V28R2_SCHEDULE_ROOT_SHA")
    if workload_sha["B0"] != workload_sha["B2"] or workload_sha["B0"] != manifest.get("B0_B2_workload_service_sha256"):
        raise RuntimeError("V28R2_B0_B2_REFERENCE_COMPUTE_SHA")
    return manifest
