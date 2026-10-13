"""Small physical fixture execution; these are not real May action receipts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

import numpy as np
import pytest

from v42_capacity.actual import Environment
from v42_integration.actual import JobRequest, run_actual, FrozenPowerModel
from v42_integration.policy import (compile_policy, FrozenControlPolicy,
                                    ReservationLedger, migration_guard)
from v42_integration.qos import TrainingStatistics, QoSWindowProvider, ObservedJob
from v42_final.workload import ForecastBook


def qos(receipts=None):
    rows = [dict(uid=str(i), submit_seconds=100000., start_seconds=104500.,
                 end_seconds=105400., observed_at_seconds=110000.,
                 request_provenance="SUBMISSION_VERSION_VERIFIED", qos="normal", protected=False,
                 partition="gpu-h100", gpu=1, requested_walltime_seconds=3600) for i in range(100)]
    stats = TrainingStatistics.from_records(rows, source_sha="FIXTURE_ONLY_TRAIN")
    return QoSWindowProvider(stats, case_sha="case", provider_sha="provider", receipts=receipts)


def request(uid="job", submit=0, q50=900, gpu=1, compatible=("A", "B"), source_site="A", **metadata):
    return JobRequest(uid, submit, gpu, compatible, q50, source_site,
        {"origin_unknown": True, "batch_eligible": True, "partition": "gpu-h100",
             "representation_starts_seconds": tuple(range(0, 14401, 900)), **metadata})


def policy(*, horizon=14400, grammar=None, delayed=False, capacities=None):
    capacities = capacities or {"A": 1, "B": 1}
    envelope = [dict(site=s, slot_start=t, slot_end=t+900, gpu_capacity=cap,
                     source_variable="CC4_site_GPU["+s+","+str(t//900)+"]", carryout_end=horizon)
                for t in range(0, horizon, 900) for s, cap in capacities.items()]
    coefficients = {(s, t): [(-10 if delayed and t >= 900 else 0) if s == "A" else -20]
                    for t in range(0, horizon, 900) for s in capacities}
    return compile_policy(envelope, dict(science_sha="science", qos_sha="qos", case_sha="case",
        aidc_anchor="aidc", mess_anchor="mess"), coefficients, grammar=grammar)


def meta_and_receipt(job=None):
    job = request() if job is None else job
    metadata = dict(job.metadata, uid=job.uid, submit_seconds=job.submit, event_seconds=job.submit,
        reference_start_seconds=0, t50_seconds=job.q50, gpu=job.gpu,
        compatible_sites=list(job.compatible), source_site=job.source_site,
        qos="normal", protected=False, state="PENDING", is_observed=True)
    observed = ObservedJob(**{k: v for k, v in metadata.items() if k in ObservedJob.__dataclass_fields__})
    return metadata, qos().issue(observed)


def capability(**updates):
    return dict(source_sha="FIXTURE_INHERITED_PHYSICAL_CONTRACT", checkpoint_authorized=True,
        allowed_destinations=["B"], gpu_type_confirmed=True, rack_gang_confirmed=True,
        data_residency_confirmed=True, wan_path="AB", bandwidth_bytes_per_second=100,
        payload_bytes=90000, restart_seconds=900, source_wait_seconds=0,
        source_hold_until="transfer_start", destination_hold_from="transfer_end", assumption=True,
        **updates)


def test_nonempty_serialized_rule_reload_determinism_and_anchor_guard(tmp_path):
    p = policy(delayed=True)
    p.save(tmp_path/"UNKNOWN_CONTROL_POLICY.json")
    loaded = FrozenControlPolicy.load(tmp_path/"UNKNOWN_CONTROL_POLICY.json", bindings=p.bindings)
    m, r = meta_and_receipt(request(can_prestart_place=True))
    first = p.select(m, r, 0, ReservationLedger({"A": 1, "B": 1}))
    second = loaded.select(m, r, 0, ReservationLedger({"A": 1, "B": 1}))
    assert first == second and first["action"] == "PREPLACE" and first["site"] == "B"
    assert loaded.document["rules"] and loaded.document["online_global_optimizer_calls"] == 0
    with pytest.raises(ValueError, match="ANCHOR_MISMATCH"):
        loaded.require_bindings(dict(loaded.bindings, mess_anchor="stale-M1"))
    doc = loaded.document
    doc["envelope"][0]["gpu_capacity"] += 1
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        FrozenControlPolicy(doc)


def test_observed_unknown_delay_execution_and_pre_submit_guard():
    p = policy(delayed=True)
    job = request(compatible=("A",))
    result = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 900}),
        arm="B1", qos_window_provider=qos(), frozen_policy=p, end=5400)
    row = result["queue_ledger"][0]
    assert row["admitted_time"] == 900 and row["policy_action"] == "DELAY"
    assert result["rule_consumption_receipt"][0]["rule_id"]
    assert result["receipt"]["optimizer_calls"] == 0
    m, r = meta_and_receipt()
    m["submit_seconds"] = 900
    assert p.select(m, r, 0, ReservationLedger({"A": 1, "B": 1}))["status"] == "NOT_YET_SUBMITTED"


def test_atomic_gang_and_wan_reservation_double_booking_rejected():
    ledger = ReservationLedger({"A": 2}, {"AB": 100})
    segments = [dict(resource="gpu:A", begin=0, end=1800, quantity=2),
                dict(resource="wan:AB", begin=900, end=1800, quantity=100)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda uid: ledger.reserve(uid, segments), ["one", "two"]))
    assert sum(ok for ok, reason in result) == 1
    assert len(ledger.reservations) == 1
    with pytest.raises(ValueError, match="WHOLE_GANG"):
        ledger.reserve("fraction", [dict(resource="gpu:A", begin=0, end=900, quantity=.5)])


def test_q50_overrun_retains_gpu_and_actual_power_recomputed():
    jobs = [request("a", compatible=("A",), source_site="A"),
            request("b", compatible=("A",), source_site="A")]
    model = FrozenPowerModel(.1, .2, {"A": 1}, .95,
        lambda it, w: np.array(it)+w["cooling_fixture"], "FIXTURE_POWER_AUTHORITY")
    result = run_actual({"A": 1}, jobs, Environment({"a": 2000, "b": 100}), arm="B0",
        qos_window_provider=qos(), end=4500, power_model=model,
        weather=[{"cooling_fixture": .03}]*5)
    rows = {r["job_uid"]: r for r in result["queue_ledger"]}
    assert rows["a"]["completion_observed_time"] == 2000
    assert rows["a"]["release_control_time"] == rows["b"]["admitted_time"] == 2700
    assert np.array_equal(result["occupancy_GPU"][:3, 0], [1, 1, 1])
    assert result["physical"]["IT_recomputed_from_actual_occupation"]
    assert not result["physical"]["planning_power_copied"]
    assert result["physical"]["IT_kw"][3, 0] > result["physical"]["IT_kw"][4, 0]


def test_cc4_once_excess_arrivals_not_deleted_and_under_arrival_preserved():
    book = ForecastBook(tuple([.1]*24), tuple([.2]*24), 0)
    jobs = [request("a", compatible=("A",)), request("b", compatible=("A",))]
    result = run_actual({"A": 1}, jobs, Environment({"a": 1800, "b": 1800}), arm="B0",
        qos_window_provider=qos(), forecast=book, end=900)
    assert len(result["cc4_depletion_ledger"]) == 2
    assert all(r["depletion_count"] == 1 for r in result["cc4_depletion_ledger"])
    assert result["cc4_depletion_ledger"][-1]["excess_submitted_nominal_GPUh"] == pytest.approx(.4)
    assert result["receipt"]["submitted_jobs"] == 2 and result["receipt"]["dropped_jobs"] == 0
    assert book.row(0, 900)["remaining_CC4_Q50_GPUh"] == 0
    assert book.row(1, 900)["remaining_CC4_Q50_GPUh"] == .1


def test_unknown_checkpoint_migration_preserves_compute_and_joint_budget():
    job = request(q50=5400, compatible=("A", "B"), migration_capability=capability())
    p = policy(grammar={"migration_destinations": ["B"]})
    result = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, end=9000)
    phases = [r["event"] for r in result["job_event_ledger"]]
    assert all(phase in phases for phase in ("CHECKPOINT", "SOURCE_WAIT", "TRANSFER", "RESTART", "DESTINATION_RUNNING"))
    assert result["queue_ledger"][0]["migration_count"] == 1
    assert result["receipt"]["actual_compute_GPUh"] == 1.5
    assert result["queue_ledger"][0]["completion_observed_time"] == 7200
    assert result["qos_ledger"][0]["total_intentional_burden_seconds"] == 1800
    m, r = meta_and_receipt(job)
    m.update(state="RUNNING", current_site="A", migration_count=0,
             additional_start_delay_seconds=2700, migration_capability=capability())
    _, reason = migration_guard(m, r, now=1800, accumulated_compute_seconds=1800,
        destination="B", remaining_nominal_seconds=3600,
        reservations=ReservationLedger({"A": 1, "B": 1}, {"AB": 100}))
    assert reason == "SHARED_DELAY_INTERRUPTION_BUDGET_EXCEEDED"


def test_unconfirmed_migration_stays_and_historical_start_not_rewritten():
    running_job = request(submit=-3600, q50=3600, compatible=("A",), state="RUNNING", origin_unknown=False)
    result = run_actual({"A": 1}, [], Environment({"job": 3600}, {"job": 2700}),
        arm="B3", qos_window_provider=qos(), frozen_policy=policy(capacities={"A": 1}, grammar={"migration_destinations": ["B"]}),
        running=[(running_job, "A", -900)], end=3600)
    assert result["carryout"]["controller"]["episode_jobs"]["job"]["start_time"] == -900
    assert result["receipt"]["max_per_site_GPU"]["A"] == 1
    assert not result["migration_receipts"]


def test_cross_midnight_json_restart_preserves_compute_qos_cc4_and_migration():
    job = request(q50=5400, compatible=("A", "B"), migration_capability=capability())
    p = policy(grammar={"migration_destinations": ["B"]})
    first = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, end=2700,
        forecast=ForecastBook(tuple([1.]*24), tuple([2.]*24), 0))
    carry = json.loads(json.dumps(first["carryout"]))
    second = run_actual({"A": 1, "B": 1}, [], Environment({"job": 999999}), arm="B3",
        qos_window_provider=qos(receipts=carry["controller"]["qos_budget_ledger"]), frozen_policy=p,
        wan_capacities={"AB": 100}, begin=2700, end=9000, carryout=carry)
    full = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, end=9000,
        forecast=ForecastBook(tuple([1.]*24), tuple([2.]*24), 0))
    assert np.array_equal(np.concatenate([first["occupancy_GPU"], second["occupancy_GPU"]]), full["occupancy_GPU"])
    assert second["queue_ledger"][0]["completion_observed_time"] == 7200
    assert second["queue_ledger"][0]["migration_count"] == 1
    assert len(second["cc4_depletion_ledger"]) == 1
    assert json.loads(json.dumps(second["qos_budget_ledger"])) == json.loads(json.dumps(full["qos_budget_ledger"]))


def test_b0_b2_same_common_actual_and_future_service_does_not_change_policy():
    jobs = [request("a", compatible=("A",)), request("b", compatible=("A",))]
    results = [run_actual({"A": 1}, jobs, Environment({"a": 1800, "b": 1800}),
                         arm=arm, qos_window_provider=qos(), end=5400) for arm in ("B0", "B2")]
    assert np.array_equal(results[0]["occupancy_GPU"], results[1]["occupancy_GPU"])
    assert results[0]["queue_ledger"] == results[1]["queue_ledger"]
    p = policy()
    m, r = meta_and_receipt()
    a = p.select(m, r, 0, ReservationLedger({"A": 1, "B": 1}))
    # Realized duration is intentionally absent from the policy interface.
    assert a == p.select(deepcopy(m), r, 0, ReservationLedger({"A": 1, "B": 1}))
    with pytest.raises(ValueError, match="PRIVATE_REALIZATION"):
        run_actual({"A": 1}, [request(realized_duration=99)], Environment({"job": 99}),
                   arm="B0", qos_window_provider=qos(), end=900)


def test_literal_midnight_carryout_keeps_inflight_reservations_and_service():
    job = request(submit=84600, q50=5400, migration_capability=capability(),
                  representation_starts_seconds=tuple(range(84600, 97201, 900)))
    p = policy(horizon=97200, grammar={"migration_destinations": ["B"]})
    first = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, begin=82800, end=86400)
    carry = json.loads(json.dumps(first["carryout"]))
    assert carry["controller"]["in_flight"]["job"]["control_checkpoint_seconds"] == 86400
    resumed = run_actual({"A": 1, "B": 1}, [], Environment({"job": 99999}), arm="B3",
        qos_window_provider=qos(receipts=carry["controller"]["qos_budget_ledger"]), frozen_policy=p,
        wan_capacities={"AB": 100}, begin=86400, end=97200, carryout=carry)
    full = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, begin=82800, end=97200)
    assert np.array_equal(np.concatenate([first["occupancy_GPU"], resumed["occupancy_GPU"]]), full["occupancy_GPU"])
    assert resumed["queue_ledger"][0]["completion_observed_time"] == 91800
    assert resumed["qos_ledger"][0]["total_intentional_burden_seconds"] == 1800


def test_unknown_migration_shifted_destination_envelope_rejects_and_overrun_stays():
    p = policy(horizon=5400, grammar={"migration_destinations": ["B"]})
    job = request(q50=5400, migration_capability=capability())
    result = run_actual({"A": 1, "B": 1}, [job], Environment({"job": 5400}), arm="B3",
        qos_window_provider=qos(), frozen_policy=p, wan_capacities={"AB": 100}, end=9000)
    # A nominal remaining interval fits at checkpoint, but the 1800-second
    # interruption moves resumed service beyond the frozen envelope boundary.
    assert not result["migration_receipts"]
    assert any(r.get("reason") == "NO_ENVELOPE_CAPACITY" for r in result["job_event_ledger"])
    m, receipt = meta_and_receipt(request(q50=900, migration_capability=capability()))
    m.update(state="RUNNING", current_site="A")
    _, reason = migration_guard(m, receipt, now=1800, accumulated_compute_seconds=1800,
        destination="B", remaining_nominal_seconds=0,
        reservations=ReservationLedger({"A": 1, "B": 1}, {"AB": 100}))
    assert reason == "Q50_OVERRUN_NO_NOMINAL_MIGRATION_ENVELOPE"


def test_network_wide_transfer_limit_shared_across_distinct_wan_paths():
    ledger = ReservationLedger({"A": 2, "B": 2}, {"AB": 100, "SECOND_PATH": 100})
    m, receipt = meta_and_receipt(request(q50=5400, migration_capability=capability()))
    m.update(state="RUNNING", current_site="A")
    first, reason = migration_guard(m, receipt, now=1800, accumulated_compute_seconds=1800,
        destination="B", remaining_nominal_seconds=3600, reservations=ledger)
    assert reason == "AUTHORIZED"
    assert ledger.reserve("job", first["segments"])[0]
    other = deepcopy(m)
    other["uid"] = "other"
    other["migration_capability"]["wan_path"] = "SECOND_PATH"
    _, other_receipt = meta_and_receipt(request("other", q50=5400, migration_capability=capability()))
    _, reason = migration_guard(other, other_receipt, now=1800, accumulated_compute_seconds=1800,
        destination="B", remaining_nominal_seconds=3600, reservations=ledger)
    assert reason == "NO_CAPACITY"


def test_off_grid_hard_release_observed_without_off_grid_start():
    job = request(compatible=("A",), release_seconds=123.)
    result = run_actual({"A": 1}, [job], Environment({"job": 100}), arm="B0",
                       qos_window_provider=qos(), end=1800)
    assert result["queue_ledger"][0]["admitted_time"] == 900
