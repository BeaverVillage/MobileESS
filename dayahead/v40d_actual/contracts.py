"""User-authorized Actual rules, deliberately separate from sealed DA science."""
from pathlib import Path
from dayahead.paper_analysis.storage import read, reference, write_json, STAGES

SCHEMA = "V40D_ACTUAL_SAVED_DATA_SCHEMA_V1"
SLOT_SECONDS = 900
BEGIN = 24
H = 120
ZERO_COUNTERS = (
    "Actual_temporal_optimization_calls", "Actual_time_optimization_calls",
    "Actual_AIDC_reoptimization_calls", "Actual_migration_reoptimization_calls",
    "Actual_WAN_rerouting_calls", "Actual_MESS_route_search_calls",
    "Actual_MESS_reoptimization_calls", "Actual_result_based_policy_changes",
    "Actual_AC_restoration_calls", "Actual_alternate_AIDC_attempts",
    "Actual_Rack_grid_objective_calls", "Actual_gang_split_count",
    "ACTUAL_ALTERNATE_AIDC_ATTEMPTS", "ACTUAL_SITE_REOPTIMIZATION_CALLS",
    "ACTUAL_CAPACITY_DRIVEN_SITE_CHANGE_COUNT", "ACTUAL_GANG_SPLIT_COUNT",
)


def artifacts(repo):
    repo = Path(repo)
    priority = reference(repo / "dayahead/v37/aidc_materializer.py")
    rack = reference(repo / "dayahead/v39d/actual.py")
    common = {"schema_id": SCHEMA, "status": "IMPLEMENTED_PENDING_VALIDATION",
              "stage_aliases": [{"internal_stage": k, "paper_stage": v} for k, v in STAGES.items()],
              "source_of_authorization": "User individual-job Actual replay instructions",
              "science_changes_in_DA": False, "cross_day_carry": False,
              "physical_slots_issue_relative": [BEGIN, H], "slot_seconds": SLOT_SECONDS}
    return {
        "V40D_INDIVIDUAL_JOB_ACTUAL_REPLAY_CONTRACT.json": {**common,
            "PENDING_duration": "historical_end - historical_start; no requested-walltime cap",
            "PENDING_start": "first 15-minute opportunity >= frozen planned start with whole-gang site/Rack capacity",
            "RUNNING_duration": "max(0, observed_end - issue_time); no restart",
            "site": "frozen site only", "within_H_UNASSIGNED": "HARD_FAIL_UNLESS_ALL_PRE_DAY_COMPLETE_CONDITIONS_PASS",
            "PRE_DAY_COMPLETE_authority": "Explicit user amendment: both planned and observed completion <= D00; half-open interval semantics",
            "PRE_DAY_COMPLETE_conditions": ["planned start/end ordered and planned end <= D00",
                "unambiguous ordered observed timestamps and observed end <= D00", "actual overlap with [D00,D+1_00) equals zero",
                "not RUNNING at D00", "operating-day GPU contribution zero", "operating-day IT/PCC contribution zero",
                "no migration/WAN/Rack state crosses D00", "site remains UNASSIGNED; no inferred site or Rack"],
            "PRE_DAY_COMPLETE_output": {"status": "PRE_DAY_COMPLETE", "AIDC_site": "UNASSIGNED", "actual_Rack": None,
                "actual_execution_on_D_day": False, "operating_day_GPU_slots": 0, "operating_day_GPU_hours": 0,
                "operating_day_power_contribution": 0, "backlog_GPU_hours": 0, "unfinished_at_operating_day_start": False},
            "post_H_UNASSIGNED": "unallocated terminal backlog; no site invention",
            "priority_source": priority,
            "priority_key": ["frozen_planned_start", "protected(high,urgent)/normal/standby/other", "submit_time", "job_uid"],
            "completion": "exact elapsed seconds retained; resource released at first slot boundary at/after completion",
            "power_occupancy": "integer whole-gang occupancy at slot start; no fractional GPU model",
            "execution_horizon": "continue assigned jobs to completion; electrical horizon remains 96 slots",
            "migration": "existing frozen evidence required; no inferred WAN readiness"},
        "V40D_ACTUAL_RACK_ASSIGNMENT_CONTRACT.json": {**common,
            "source": rack, "assignment": "compatible stable Rack-ID first-fit within frozen site",
            "lifetime": "admission to realized completion; no preemption",
            "caps": "C_s is the sole cumulative hard cap; each Rack envelope tests individual gang admissibility only",
            "failure": "queue until next release; do not split gang or change site"},
        "V40D_ACTUAL_MESS_FIXED_COMMAND_CONTRACT.json": {**common,
            "mobility": "frozen departure, destination and ordered links; link-entry 5-minute realized traffic",
            "energy": "frozen longitudinal physics evaluated at actual traversal time",
            "projection": ["unconnected: P=Q=0", "connected: saturate P only at current battery-energy bounds",
                           "then clip Q to sqrt(PCS_kVA^2-P_EXEC^2)"],
            "missed_commands": "discard at original slot; no catch-up",
            "travel_energy_bound_failure": "FAIL_CLOSED; no reroute or command optimization",
            "zero_counters": list(ZERO_COUNTERS)},
        "V40D_ACTUAL_MESS_D00_STATE_CONTRACT.json": {**common,
            "connected":"preserve frozen D00 slot location; future route origin cannot overwrite it",
            "departure_at_D00":"use frozen origin only if exact slot-zero departure and route endpoints match authority",
            "departure_after_D00":"preserve D00 location until exact frozen departure slot",
            "transit_before_D00":"FAIL_CLOSED unless authoritative current edge, progress, residual route, edge-entry time and residual execution/energy binding exist; never reset origin",
            "current_pre_D00_transit_support":"No such May01 cases; residual replay remains fail-closed until a complete authority is bound",
            "arrived_before_D00":"preserve frozen destination and ready state, never reset origin",
            "exact_initial_energy_source":reference(repo/"dayahead/mess_physics.py"),
            "rounded_9_decimal_SoC_source_match_tolerance_kWh":6.1e-7,
            "independent_energy_balance_tolerance_kWh":1e-9,
            "travel_energy_accounting":"once per committed departure; current authority uses unit charge/discharge efficiency",
            "command_nonexecution_count_unit":"vehicle-slot with any nonzero P/Q command partly or wholly unexecuted"},
        "V40D_ACTUAL_INFORMATION_FIREWALL.json": {**common,
            "read_order": "verify accepted DA certificate and SHA before opening realized inputs",
            "actual_field_role": "ACTUAL_EXECUTION_ONLY",
            "write_scope": "separate Actual artifacts only", "DA_feedback_allowed": False,
            "optimizer_runtime_guard": "all gurobipy Model.optimize calls raise during preflight/replay"},
        "V40D_ACTUAL_SAVED_DATA_SCHEMA.json": {**common,
            "raw_tables": ["job_ledger.parquet", "rack_ledger.parquet", "rack_waits.parquet",
                           "aidc_site_timeseries.parquet", "mess_executed_trajectory.parquet"],
            "dense_arrays": ["actual_grid_arrays.npz"],
            "summaries": ["provenance.json", "result_summary.json", "PERSISTENCE_STATUS.json"],
            "separate_quantities": ["Planning_J", "Fresh_AC_rho", "Actual_AC_rho"],
            "missing_value": "MISSING_NOT_RECORDED", "incomplete_result_may_pass": False,
            "atomic_write": "same-directory tempfile, flush, fsync, close, os.replace"},
    }


def write_contracts(repo, output):
    for name, value in artifacts(repo).items():
        write_json(Path(output) / name, value)


class ReplayError(RuntimeError):
    pass
