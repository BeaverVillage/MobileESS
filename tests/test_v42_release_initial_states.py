from copy import deepcopy
from pathlib import Path

import pytest

from v42_integration import release_initial_states as api


def request(uid="j", submit="2025-05-01T12:00:00+00:00"):
    return dict(job_uid=uid, submit_time=submit, GPU_gang=4, source_member="source", source_row=1)


def event(end="2025-05-04T12:00:00+00:00"):
    return dict(id="j", submit_time="2025-05-01T12:00:00+00:00", start_time="2025-05-01T13:00:00+00:00",
        end_time=end, gpus_requested=4)


def test_future_completion_cannot_change_public_prefix():
    boundary = api.midnight("2025-05-02")
    first = api.causal_event(event(), request(), boundary)
    second = api.causal_event(event("2025-05-25T12:00:00+00:00"), request(), boundary)
    assert first == second
    assert first["observed_completion_seconds"] is None
    assert first["observed_start_seconds"] == api.seconds("2025-05-01T13:00:00+00:00")


def test_exact_midnight_completion_is_observed():
    boundary = api.midnight("2025-05-02")
    value = api.causal_event(event("2025-05-01T14:00:00+00:00"), request(), boundary)
    assert value["observed_completion_seconds"] == boundary


def test_future_unknown_uid_removed_before_source_projection():
    begin = api.midnight("2025-05-02")
    plan = dict(known_population=[request()])
    actual = dict(post_issue_arrivals=[request("future", "2025-05-02T01:00:00+00:00")])
    assert [r["job_uid"] for r in api.public_population(plan, actual, begin)] == ["j"]
    with pytest.raises(ValueError, match="FUTURE_UNKNOWN_REQUEST_AT_D0"):
        api.causal_event(dict(event(), id="future", submit_time="2025-05-02T01:00:00+00:00"), actual["post_issue_arrivals"][0], begin)


def test_current_gpu_request_is_bound_to_raw_source():
    with pytest.raises(ValueError, match="RAW_IMMUTABLE_GPU_REQUEST_MISMATCH"):
        api.causal_event(dict(event(), gpus_requested=2), request(), api.midnight("2025-05-02"))


def test_date_boundary_uses_fixed_utc_plus_ten():
    assert api.midnight("2025-05-01") == 1746021600
    assert api.midnight("2025-05-31") - api.midnight("2025-05-01") == 30 * 86400


def prior_case():
    begin = api.midnight("2025-05-02")
    base = dict(boundary_source_state="RUNNING", GPU_gang=4, source_submit_seconds=begin - 30000,
        observed_start_seconds=begin - 1000, source_member="raw", frozen_Q50_total_seconds=100,
        compatible_sites=["AIDC01", "AIDC02"], current_model_site=None)
    fixed = dict(base, job_uid="fixed", source_row=0, current_model_site="AIDC01")
    missing = [dict(base, job_uid="j" + str(i), source_row=i + 1) for i in range(2)]
    plan = dict(day="2025-05-02", issue_time="2025-05-01T18:00:00+10:00",
        capacities={"AIDC01": 8, "AIDC02": 8}, rack_compatibility={"AIDC01": [8], "AIDC02": [8]},
        known_population=[dict(job_uid=r["job_uid"]) for r in [fixed] + missing])
    refs = [dict(job_uid=r["job_uid"], source_member="raw", source_row=r["source_row"],
        submit_time="2025-05-01T05:40:00+00:00", GPU_gang=4, Q50_total_seconds=100,
        state_at_D1_cutoff="PENDING", reference_site="AIDC01", site_authority_source="USER_DEFINED_GRID_BLIND_REFERENCE_PLACEMENT")
        for r in [fixed] + missing]
    ref = dict(rows=refs, audit=dict(actual_reads=0, voltage_reads=0, optimizer_calls=0, full_reference_ready=True))
    receipt = dict(path="ref", sha256="same", bytes=12)
    freeze = dict(day=plan["day"], freeze_before_Actual_truth=True, reference=receipt)
    candidate = dict(Actual_begin_seconds=begin, initial_source_roster=[fixed] + missing)
    return candidate, plan, ref, freeze, receipt


def test_entire_overloaded_prior_site_group_is_rejected():
    candidate, plan, ref, freeze, receipt = prior_case()
    recovery = api.prior_reference_pins(candidate, plan, {}, ref, freeze, reference_record=receipt)
    assert recovery["validated_pins"] == {}
    assert recovery["overloaded_reference_site_groups_rejected_entirely"] == ["AIDC01"]
    assert len(recovery["rejected"]) == 2


def test_reference_of_another_date_cannot_authorize_sites():
    candidate, plan, ref, freeze, receipt = prior_case()
    freeze["day"] = "2025-05-01"
    with pytest.raises(ValueError, match="PRIOR_REFERENCE_NOT_SAME_DAY"):
        api.prior_reference_pins(candidate, plan, {}, ref, freeze, reference_record=receipt)


def test_cc4_requires_same_day_issue_and_anonymous_forecast(tmp_path):
    cc4 = dict(target_day="2025-05-02", issue_time="2025-05-01T08:00:00+00:00", future_job_ids=[],
        prediction_index=413, Q50_GPUh=[0] * 24, nominal_unknown_GPU_96=[0] * 96)
    path = tmp_path / "CC4.json"
    api.write_json(path, cc4)
    plan = dict(issue_time="2025-05-01T18:00:00+10:00", forecast_inputs=dict(current_CC4=cc4))
    assert api.verify_cc4("2025-05-02", plan, path)["PASS"]
    with pytest.raises(ValueError, match="CC4_FROZEN_DAY_ROW"):
        api.verify_cc4("2025-05-03", plan, path)


def test_lossless_compression_never_overwrites_source(tmp_path):
    path = tmp_path / "prefix.json.gz"
    value = dict(uid="공개", events=[1, 2, 3])
    receipt = api.write_json(path, value, compressed=True)
    assert api.read(path) == value
    assert api.checked(receipt) == path
    with pytest.raises(FileExistsError):
        api.write_json(path, value, compressed=True)


def test_may01_original_initializer_full_object_reproduction():
    original = Path("D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration")
    if not original.exists():
        pytest.skip("The authoritative local May01 source is not present on this host")
    result = api.reproduce_may01(original / "V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json",
        "D:/v42_may_joint_repair_campaign_20261013/raw", original)
    assert result["complete_object_equal"]
    assert result["semantic_sha"] == api.INITIAL_SEMANTIC
    assert result["Native_Optimize_calls"] == 0
