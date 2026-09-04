"""Deterministic, globally capacity-feasible synthetic home-AIDC mapping."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd

from .authority import (
    atomic_json,
    canonical_sha256,
    load_capacity_authority,
    sha256_file,
)
from .contracts import (
    EXPECTED_DATES,
    HOME_MAPPING,
    HOME_MAPPING_AUDIT,
    SLOTS,
    V37_DAY_ROOT,
)


def _cell_descriptor(cell: int) -> dict[str, Any]:
    day_index, within_day = divmod(cell, 2 * SLOTS)
    mode_index, slot = divmod(within_day, SLOTS)
    return {
        "cell": cell,
        "operating_day": EXPECTED_DATES[day_index],
        "temporal_mode": ("RW", "RSP")[mode_index],
        "slot": slot,
    }


def _hash_rank(job_key: str, rack: str) -> int:
    return int(hashlib.sha256(f"V38_HOME:{job_key}:{rack}".encode()).hexdigest()[:12], 16)


def _load_activity(repo: Path) -> tuple[dict[str, dict[str, Any]], int]:
    cells = len(EXPECTED_DATES) * 2 * SLOTS
    jobs: dict[str, dict[str, Any]] = {}
    for day_index, day in enumerate(EXPECTED_DATES):
        root = repo / V37_DAY_ROOT / day
        for mode_index, mode in enumerate(("RW", "RSP")):
            schedule = pd.read_parquet(root / f"V37_R4A_{mode}_SCHEDULE.parquet")
            for row in schedule.itertuples(index=False):
                uid = str(row.job_id)
                gpu = int(round(float(row.requested_gpus)))
                if gpu <= 0:
                    raise RuntimeError("V38_HOME_NONPOSITIVE_GPU")
                item = jobs.setdefault(uid, {"requested_GPU": gpu, "activity": bytearray(cells)})
                if item["requested_GPU"] != gpu:
                    raise RuntimeError(f"V38_HOME_JOB_GPU_MUTATION:{uid}")
                start = max(0, int(row.scheduled_start_slot))
                end = min(SLOTS, int(row.scheduled_end_slot))
                base = (day_index * 2 + mode_index) * SLOTS
                for slot in range(start, max(start, end)):
                    item["activity"][base + slot] = 1
    return jobs, cells


def materialize_home_mapping(repo: Path, *, force: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Solve one D-1-input-only home-AIDC map across all May occupancy cells."""

    if HOME_MAPPING.is_absolute():
        mapping_path = HOME_MAPPING
        audit_path = HOME_MAPPING_AUDIT
    else:
        mapping_path = repo / HOME_MAPPING
        audit_path = repo / HOME_MAPPING_AUDIT
    source_paths = [
        repo / V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
        for day in EXPECTED_DATES for mode in ("RW", "RSP")
    ]
    source_sha = canonical_sha256([
        (str(path.relative_to(repo)).replace("\\", "/"), sha256_file(path))
        for path in source_paths
    ])
    capacity = load_capacity_authority(repo)
    identity = canonical_sha256({
        "source_schedule_set_sha256": source_sha,
        "rack_source_sha256": capacity.source_sha256,
        "site_capacity": dict(capacity.site_capacity),
        "implementation": sha256_file(Path(__file__)),
    })
    if mapping_path.is_file() and audit_path.is_file() and not force:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("mapping_input_sha256") == identity and audit.get("status") == "PASS":
            frame = pd.read_parquet(mapping_path)
            if sha256_file(mapping_path) == audit.get("mapping_file_sha256"):
                return frame, audit

    jobs, cell_count = _load_activity(repo)
    groups: dict[tuple[int, bytes], list[str]] = defaultdict(list)
    inactive: list[str] = []
    for uid, item in jobs.items():
        activity = bytes(item["activity"])
        if any(activity):
            groups[(int(item["requested_GPU"]), activity)].append(uid)
        else:
            inactive.append(uid)

    racks = capacity.rack_pools
    sites = capacity.aidc_ids
    model = gp.Model("V38_SYNTHETIC_REFERENCE_HOME_MAPPING")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260828
    model.Params.MIPGap = 0.0
    model.Params.FeasibilityTol = 1e-8
    model.Params.IntFeasTol = 1e-8
    model.Params.TimeLimit = 300.0
    model.Params.SolutionLimit = 1
    variables: dict[tuple[int, int], gp.Var] = {}
    group_rows = sorted(
        ((gpu, activity, sorted(uids)) for (gpu, activity), uids in groups.items()),
        key=lambda row: (-row[0], hashlib.sha256(row[1]).hexdigest(), row[2][0]),
    )
    eligible: dict[int, tuple[int, ...]] = {}
    for group_index, (gpu, _activity, uids) in enumerate(group_rows):
        candidates = tuple(
            index for index, site in enumerate(sites)
            if capacity.site_capacity[site] >= gpu
            and capacity.eligible_racks(site, gpu)
        )
        if not candidates:
            raise RuntimeError(f"V38_HOME_NO_RACK_FOR_GPU_GANG:{gpu}")
        eligible[group_index] = candidates
        for site_index in candidates:
            variables[group_index, site_index] = model.addVar(
                vtype=GRB.INTEGER,
                lb=0,
                ub=len(uids),
                name=f"home_count[{group_index},{site_index}]",
            )
        model.addConstr(
            gp.quicksum(variables[group_index, s] for s in candidates) == len(uids),
            name=f"group_conservation[{group_index}]",
        )

    active_by_cell: dict[int, list[int]] = defaultdict(list)
    for group_index, (_gpu, activity, _uids) in enumerate(group_rows):
        for cell, active in enumerate(activity):
            if active:
                active_by_cell[cell].append(group_index)
    for cell, group_indices in sorted(active_by_cell.items()):
        for site_index, site in enumerate(sites):
            expression = gp.quicksum(
                group_rows[g][0] * variables[g, site_index]
                for g in group_indices if (g, site_index) in variables
            )
            model.addConstr(
                expression <= capacity.site_capacity[site],
                name=f"site_capacity[{cell},{site}]",
            )

    # A deterministic hash preference is only a tie-break after exact capacity.
    objective = gp.quicksum(
        ((_hash_rank(group_rows[g][2][0], sites[s]) % 1_000_003) + 1)
        * variables[g, s]
        for g, s in variables
    )
    model.setObjective(objective, GRB.MINIMIZE)
    model.optimize()
    if model.SolCount < 1:
        if model.Status == GRB.INFEASIBLE:
            model.computeIIS()
            iis_path = repo / "dayahead/artifacts/v38_aidc_spatiotemporal_wan/V38_HOME_MAPPING_IIS.ilp"
            iis_path.parent.mkdir(parents=True, exist_ok=True)
            model.write(str(iis_path))
            # Gurobi emits a whitespace-only separator line.  Normalize it so
            # the persisted forensic artifact is stable under repository QA.
            iis_text = iis_path.read_text(encoding="utf-8")
            iis_path.write_text(
                "\n".join(line.rstrip() for line in iis_text.splitlines()) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            iis_names = sorted(
                constraint.ConstrName
                for constraint in model.getConstrs()
                if constraint.IISConstr
            )
            iis_cells = sorted({
                int(name.split("[", 1)[1].split(",", 1)[0])
                for name in iis_names if name.startswith("site_capacity[")
            })
            atomic_json(repo / HOME_MAPPING_AUDIT, {
                "artifact_id": "V38_HOME_IDC_MAPPING_AUDIT_V1",
                "status": "FAIL",
                "failure": "NO_SINGLE_JOB_UID_TO_HOME_AIDC_MAPPING_SATISFIES_ALL_V37_RW_RSP_SITE_CAPS",
                "scientific_blocker": (
                    "The mandated same-job_uid/same-home-AIDC invariant, accepted V37 "
                    "RW/RSP temporal schedules, gang indivisibility, and frozen 12-site "
                    "equivalent-GPU capacities have no joint feasible assignment."
                ),
                "forbidden_workarounds": [
                    "date-dependent home-AIDC remapping",
                    "splitting GPU gangs",
                    "increasing or rebalancing frozen site capacities",
                    "changing accepted V37 RW/RSP start schedules",
                    "using May outcomes or Fresh results to choose the mapping",
                ],
                "solver_status": int(model.Status),
                "solver_status_name": "INFEASIBLE",
                "solver_threads": 1,
                "solver_seed": 20260828,
                "job_count": len(jobs),
                "active_cohort_count": len(group_rows),
                "occupancy_cell_count": cell_count,
                "mapping_input_sha256": identity,
                "source_schedule_set_sha256": source_sha,
                "IIS_path": str(iis_path.relative_to(repo)).replace("\\", "/"),
                "IIS_sha256": sha256_file(iis_path),
                "IIS_constraint_count": len(iis_names),
                "IIS_site_capacity_cells": [
                    _cell_descriptor(cell) for cell in iis_cells
                ],
                "May_result_reads": 0,
                "grid_result_reads": 0,
            })
        raise RuntimeError(f"V38_HOME_MAPPING_NO_FEASIBLE_SOLUTION:{model.Status}")

    mapping: dict[str, tuple[str, str, int]] = {}
    for group_index, (_gpu, _activity, uids) in enumerate(group_rows):
        cursor = 0
        for site_index in sorted(
            eligible[group_index],
            key=lambda s: (_hash_rank(uids[0], sites[s]), sites[s]),
        ):
            count = int(round(variables[group_index, site_index].X))
            for uid in uids[cursor: cursor + count]:
                site = sites[site_index]
                mapping[uid] = (site, "D1_RACK_ASSIGNMENT_REQUIRED", int(_hash_rank(uid, site)))
            cursor += count
        if cursor != len(uids):
            raise RuntimeError("V38_HOME_GROUP_EXPANSION")

    for uid in sorted(inactive):
        gpu = int(jobs[uid]["requested_GPU"])
        candidates = [
            site for site in sites
            if capacity.site_capacity[site] >= gpu
            and capacity.eligible_racks(site, gpu)
        ]
        if not candidates:
            # The mapping covers all D-1 snapshot rows, including jobs whose
            # temporal start lies beyond the 96-slot evaluation horizon.  Such
            # a job is mapped deterministically but is not an executable V38
            # candidate until a later operating-day authority can host it.
            candidates = [max(sites, key=lambda site: (capacity.site_capacity[site], site))]
        site = min(candidates, key=lambda value: (_hash_rank(uid, value), value))
        mapping[uid] = (site, "D1_RACK_ASSIGNMENT_REQUIRED", _hash_rank(uid, site))

    frame = pd.DataFrame([
        {
            "job_uid": uid,
            "home_AIDC": mapping[uid][0],
            "home_rack_pool_id": mapping[uid][1],
            "requested_GPU": int(jobs[uid]["requested_GPU"]),
            "mapping_type": "SYNTHETIC_REFERENCE_HOME_AIDC_MAPPING",
            "outcome_blind": True,
            "deterministic_tie_break": mapping[uid][2],
        }
        for uid in sorted(mapping)
    ])
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = mapping_path.with_suffix(mapping_path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(mapping_path)

    max_site_over = 0.0
    for cell, group_indices in active_by_cell.items():
        site_load = {site: 0.0 for site in capacity.aidc_ids}
        for group_index in group_indices:
            gpu, _activity, uids = group_rows[group_index]
            for uid in uids:
                site, rack, _rank = mapping[uid]
                site_load[site] += gpu
        max_site_over = max(max_site_over, max(site_load[s] - capacity.site_capacity[s] for s in site_load))
    audit = {
        "artifact_id": "V38_HOME_IDC_MAPPING_AUDIT_V1",
        "status": "PASS" if max_site_over <= 1e-8 else "FAIL",
        "mapping_type": "SYNTHETIC_REFERENCE_HOME_AIDC_MAPPING",
        "job_count": len(frame), "active_job_count": len(frame) - len(inactive),
        "inactive_outside_96_job_count": len(inactive), "cohort_count": len(group_rows),
        "same_job_same_home_AIDC_across_cases_and_dates": True,
        "May_result_reads": 0, "grid_result_reads": 0,
        "mapping_input_sha256": identity,
        "source_schedule_set_sha256": source_sha,
        "mapping_file_sha256": sha256_file(mapping_path),
        "mapping_content_sha256": canonical_sha256(frame.drop(columns=["deterministic_tie_break"]).to_dict("records")),
        "maximum_site_capacity_violation_GPU": max(0.0, max_site_over),
        "maximum_rack_capacity_violation_GPU": "CHECKED_PER_DAY_BY_D1_RACK_ORACLE",
        "solver_status": int(model.Status), "solver_solution_count": int(model.SolCount),
        "solver_threads": 1, "solver_seed": 20260828,
    }
    atomic_json(audit_path, audit)
    if audit["status"] != "PASS":
        raise RuntimeError("V38_HOME_MAPPING_POSTCHECK")
    return frame, audit


__all__ = ["materialize_home_mapping"]
