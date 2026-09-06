"""Behavioral regression tests for authorized fixed-decision execution."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import sys
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
import pytest
from dayahead.paper_analysis.storage import STAGES, canonical, digest, seal, sha, write_json, write_npz, verify_seal
from dayahead.v40d_actual.contracts import ReplayError
from dayahead.v40d_actual.job_replay import replay_jobs, validate_jobs, priority_key
from dayahead.v40d_actual.mess_replay import project_command, traverse, replay_commands
from dayahead.v40d_actual.rack_dispatch import Rack

ISSUE = datetime(2025, 4, 30, 18, tzinfo=timezone(timedelta(hours=10)))


def job(uid="j1", start=24, gpu=4, site="S", **kw):
    return {"job_uid": uid, "state_at_issue": "PENDING", "requested_GPU": gpu,
        "AIDC_site": site, "start_slot": start, "end_slot": start + 1,
        "qos": "normal", "submit_time": ISSUE.isoformat(), "requested_walltime_seconds": 900,
        "migration_selected": False, "Rack_label": None, "accepted_A0_assignment_and_WAN": {}, **kw}


def observation(seconds=1800, gpu=4, *, start=None):
    start = start or ISSUE + timedelta(days=10)
    return {"start_time": start, "end_time": start + timedelta(seconds=seconds), "gpus_requested": gpu}


def run(jobs, obs, racks=None, cap=4):
    return replay_jobs(jobs, obs, issue_time=ISSUE, site_capacity={"S": cap},
        racks=racks or [Rack("S", "R02", cap), Rack("S", "R01", cap)])


def test_pending_historical_start_never_overwrites_frozen_start():
    x = run([job()], {"j1": observation()})["job_ledger"][0]
    assert x["actual_execution_start"] == 24
    assert x["actual_execution_end"] == 26
    assert x["actual_runtime_gt_requested_walltime"] is True


def test_overrun_delays_whole_gang_instead_of_overbooking():
    x = run([job(), job("j2", 25)], {"j1": observation(2700), "j2": observation(900)})
    rows = {r["job_uid"]: r for r in x["job_ledger"]}
    assert rows["j2"]["actual_execution_start"] == 27
    assert rows["j2"]["start_delay_slots"] == 2
    assert rows["j2"]["delayed_by_GPU_capacity"]
    assert max(r["occupied_GPU_slots"] for r in x["site_occupancy"]) == 4


def test_running_residual_not_restarted():
    x = run([job(state_at_issue="RUNNING", start=0)],
            {"j1": observation(4 * 900, start=ISSUE - timedelta(seconds=900))})["job_ledger"][0]
    assert x["actual_runtime_seconds"] == 3600
    assert x["actual_service_seconds"] == 2700
    assert x["actual_execution_start"] is None
    assert x["actual_execution_end"] == 3


def test_same_site_and_no_alternate_site_calls():
    x = run([job()], {"j1": observation()})
    assert x["job_ledger"][0]["frozen_AIDC_site"] == "S"
    assert x["counters"]["Actual_alternate_AIDC_attempts"] == 0
    assert all(v == 0 for k, v in x["counters"].items() if k != "Actual_Rack_assignment_calls")


def test_stable_rack_first_fit_and_release():
    x = run([job("j2", 25), job()], {"j1": observation(900), "j2": observation(900)})
    assert [r["rack_pool_id"] for r in x["rack_ledger"]] == ["R01", "R01"]


def test_logical_rack_is_single_gang_admissibility_not_cumulative_bin():
    x = run([job(), job("j2", 24)], {"j1": observation(), "j2": observation()},
            racks=[Rack("S", "R", 4)], cap=8)
    assert x["job_ledger"][1]["actual_execution_start"] == 24
    assert not x["job_ledger"][1]["delayed_by_Rack_capacity"]
    assert len(x["rack_ledger"]) == 2


def test_post_H_accounting_not_truncated_or_carried():
    x = run([job(start=119)], {"j1": observation(2701)})
    r = x["job_ledger"][0]
    assert r["unfinished_at_H"]
    assert r["remaining_runtime_at_H"] == pytest.approx(1801)
    assert r["actual_execution_end"] > 122
    assert r["post_H_site"] == "S"
    assert x["cross_day_state_carried"] is False
    assert len(x["site_occupancy"]) == 96


def test_job_input_not_mutated_and_repeat_is_identical():
    jobs, obs = [job(), job("j2", 25)], {"j1": observation(2700), "j2": observation()}
    before = canonical(jobs)
    first, second = run(jobs, obs), run(jobs, obs)
    assert canonical(jobs) == before
    assert canonical(first) == canonical(second)


@pytest.mark.parametrize("g", [0, -1, 1.5, float("nan")])
def test_invalid_gpu_is_fail_closed(g):
    with pytest.raises(ReplayError, match="INVALID_GPU"):
        run([job(gpu=g)], {"j1": observation()})


def test_initial_running_capacity_cannot_be_delayed():
    obs = observation(3600, start=ISSUE - timedelta(seconds=900))
    with pytest.raises(ReplayError, match="RUNNING_INITIAL_CAPACITY_CONFLICT"):
        run([job("j1", 0, state_at_issue="RUNNING"), job("j2", 0, state_at_issue="RUNNING")], {"j1": obs, "j2": obs})


def test_unassigned_pre_H_fails_even_when_completed_pre_day():
    with pytest.raises(ReplayError, match="UNASSIGNED_PRE_DAY_COMPLETE_CONDITIONS_FAILED"):
        run([job(start=0, site="UNASSIGNED")], {"j1": observation()})


def test_unassigned_post_H_is_backlog_without_site_invention():
    r = run([job(start=120, site="UNASSIGNED")], {"j1": observation()})["job_ledger"][0]
    assert r["status"] == "UNASSIGNED_POST_H_BACKLOG"
    assert r["actual_execution_start"] is None
    assert r["backlog_GPU_hours"] == 2


def test_priority_matches_authoritative_service_tiers():
    jobs = [job(uid=q, qos=q) for q in ("standby", "normal", "urgent", "unknown", "high")]
    assert [j["job_uid"] for j in sorted(jobs, key=priority_key)] == ["high", "urgent", "normal", "standby", "unknown"]


def test_missing_runtime_and_uid_are_not_silently_dropped():
    with pytest.raises(ReplayError, match="MISSING_ACTUAL_RUNTIME"):
        run([job()], {})
    with pytest.raises(ReplayError, match="DUPLICATE_UID"):
        run([job(), job()], {"j1": observation()})


def test_unconnected_discards_commands_without_shift():
    r = project_command(400, -500, 760, connected=False)
    assert r["P_EXEC"] == r["Q_EXEC"] == 0
    assert r["energy_after_kWh"] == 760


def test_soc_saturation_then_exact_PCS_Q_clipping():
    r = project_command(550, 700, 450, connected=True)
    assert r["P_EXEC"] == 40
    assert r["energy_after_kWh"] == 440
    assert r["Q_EXEC"] == pytest.approx(np.sqrt(700**2 - 40**2))
    r = project_command(-550, -700, 1070, connected=True)
    assert r["P_EXEC"] == -40
    assert r["energy_after_kWh"] == 1080


def test_travel_energy_is_never_clipped_or_reoptimized():
    with pytest.raises(ReplayError, match="TRAVEL_ENERGY_BOUND"):
        project_command(0, 0, 450, connected=False, travel_energy=11)


def test_link_entry_timing_route_identity_and_physics_energy():
    x = np.full((288, 2), 301.0)
    x[1, 1] = 500
    r = traverse(["a", "b"], 0, ["a", "b"], x, lambda links, seconds: seconds / 100, connection_delay_seconds=300)
    assert r["route_link_ids"] == ["a", "b"]
    assert r["actual_eta_seconds"] == 801
    assert r["actual_travel_energy_kWh"] == 8.01
    assert r["actual_connection_ready_slot"] == 2
    assert r["link_entries"][1]["entry_step5"] == 1


def test_incomplete_actual_link_path_fails():
    with pytest.raises(ReplayError, match="LINK_ENTRY_UNAVAILABLE"):
        traverse(["missing"], 0, ["a"], np.ones((288, 1)), lambda *_: 0, connection_delay_seconds=300)


def test_repeated_fixed_commands_preserve_identity():
    commands = [{"mess_id": "m", "slot": t, "service_id": "S", "p_kw": 0., "q_kvar": 10.} for t in range(96)]
    a = replay_commands(commands, [], {"m": 760.})
    b = replay_commands(commands, [], {"m": 760.})
    assert canonical(a) == canonical(b)
    assert a["counters"]["Actual_MESS_reoptimization_calls"] == 0
    assert a["counters"]["Actual_AC_restoration_calls"] == 0


def test_slot_zero_departure_uses_frozen_initial_origin():
    commands=[{"mess_id":"m","slot":t,"service_id":None if t==0 else "T","p_kw":0.,"q_kvar":0.} for t in range(96)]
    moves=[{"mess_id":"m","departure_slot":0,"actual_connection_ready_slot":1,
        "origin_service_id":"S","destination_service_id":"T","actual_travel_energy_kWh":1.}]
    x=replay_commands(commands,moves,{"m":760.},initial_locations={"m":"S"})
    assert x["trajectory"][0]["actual_service_id"] is None
    assert x["trajectory"][0]["travel_energy_kWh"]==1
    assert x["trajectory"][1]["actual_service_id"]=="T"


def test_paper_aliases_exact():
    assert STAGES == {"A0": "A1", "M1": "M1", "A1": "A2", "MF": "M2"}


def test_atomic_serialization_no_mutation_and_no_false_PASS(tmp_path):
    x = np.arange(96, dtype=float)
    before = x.copy()
    write_npz(tmp_path / "raw.npz", x=x)
    np.testing.assert_array_equal(x, before)
    with pytest.raises(RuntimeError, match="RESULT_PERSISTENCE_FAIL"):
        seal(tmp_path, ["missing.json"])
    with pytest.raises(RuntimeError):
        verify_seal(tmp_path)
    seal(tmp_path, ["raw.npz"], missing=["branch.P"])
    assert verify_seal(tmp_path)["status"] == "PARTIAL_HISTORICAL"


def test_execution_modules_have_no_optimizer_imports_in_clean_process():
    code = "import sys; import dayahead.v40d_actual.job_replay, dayahead.v40d_actual.mess_replay; assert 'gurobipy' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_actual_code_is_not_imported_by_day_ahead_sources():
    root = Path(__file__).resolve().parents[1] / "dayahead"
    for name in ("v40a", "v40b", "v39e"):
        for p in (root / name).glob("*.py"):
            assert "v40d_actual" not in p.read_text(encoding="utf-8-sig")


def pred_inputs(*, plan_end=23, observed_end=23):
    r = job(start=1, site="UNASSIGNED", end_slot=plan_end)
    o = observation((observed_end-1)*900, start=ISSUE+timedelta(seconds=900))
    return r, o


@pytest.mark.parametrize("plan_end,observed_end", [(23, 23), (24, 24)])
def test_pre_day_complete_before_and_exact_half_open_boundary(plan_end, observed_end):
    r, o = pred_inputs(plan_end=plan_end, observed_end=observed_end)
    x = run([r], {"j1": o})
    row = x["job_ledger"][0]
    assert row["status"] == "PRE_DAY_COMPLETE"
    assert row["AIDC_site"] == "UNASSIGNED" and row["actual_Rack"] is None
    assert row["actual_execution_on_D_day"] is False
    assert row["operating_day_GPU_slots"] == row["operating_day_GPU_hours"] == 0
    assert row["operating_day_power_contribution"] == row["backlog_GPU_hours"] == 0
    assert row["unfinished_at_operating_day_start"] is False
    assert not x["rack_ledger"]
    assert all(r["occupied_GPU_slots"] == 0 for r in x["site_occupancy"])


@pytest.mark.parametrize("plan_end,observed_end", [(23, 25), (25, 23)])
def test_pre_day_exception_never_truncates_plan_or_observed_overrun(plan_end, observed_end):
    r, o = pred_inputs(plan_end=plan_end, observed_end=observed_end)
    with pytest.raises(ReplayError, match="UNASSIGNED_PRE_DAY_COMPLETE"):
        run([r], {"j1": o})


def test_pre_day_missing_observed_completion_fails():
    r, o = pred_inputs()
    o["end_time"] = None
    with pytest.raises(ReplayError, match="INVALID_OBSERVATION"):
        run([r], {"j1": o})


def test_pre_day_running_at_boundary_fails():
    from dayahead.v40d_actual.pre_day_complete import classify
    r, o = pred_inputs()
    r["running_at_operating_day_start"] = True
    assert classify(r, o, ISSUE)["status"] == "FAIL_CLOSED"


@pytest.mark.parametrize("state", ["migration_state_crosses_D00", "WAN_state_crosses_D00", "Rack_state_crosses_D00"])
def test_pre_day_no_carried_execution_state(state):
    from dayahead.v40d_actual.pre_day_complete import classify
    r, o = pred_inputs()
    r[state] = True
    assert classify(r, o, ISSUE)["status"] == "FAIL_CLOSED"


def test_pre_day_gpu_power_and_rack_downstream_guards():
    from dayahead.v40d_actual.pre_day_complete import audit_exclusion, classify
    r, o = pred_inputs()
    c = [classify(r, o, ISSUE)]
    with pytest.raises(ReplayError, match="GPU_CONTRIBUTION"):
        audit_exclusion(c, gpu_contributions=[{"job_uid": "j1", "occupied_GPU": 1}])
    with pytest.raises(ReplayError, match="POWER_CONTRIBUTION"):
        audit_exclusion(c, power_contributions=[{"job_uid": "j1", "P_PCC_kW": .001}])
    with pytest.raises(ReplayError, match="RACK_ASSIGNMENT"):
        audit_exclusion(c, rack_assignments=[{"job_uid": "j1", "rack_pool_id": "R"}])


def test_pre_day_classification_cannot_change_protected_inputs(tmp_path):
    r, o = pred_inputs()
    p = tmp_path / "protected_planning.json"
    f = tmp_path / "protected_fresh.npz"
    write_json(p, r)
    write_npz(f, voltage=np.ones((96, 3)))
    before = (sha(p), sha(f), canonical(r))
    run([r], {"j1": o})
    assert (sha(p), sha(f), canonical(r)) == before


def test_pre_day_reversed_timestamp_order_fails():
    from dayahead.v40d_actual.pre_day_complete import classify
    r, o = pred_inputs()
    o["end_time"] = o["start_time"] - timedelta(seconds=1)
    assert classify(r, o, ISSUE)["status"] == "FAIL_CLOSED"
