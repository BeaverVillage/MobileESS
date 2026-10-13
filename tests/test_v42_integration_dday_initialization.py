"""PR125 DD00 reuse and common queue model; no solver or Actual replay."""
from copy import deepcopy
import json

import pandas as pd
import pytest

from v42_integration.dday_initialization import (initialize_from_candidate,load_dday_state,
    FIXED,FALLBACK,REUSED,ARMS,_episode)
from v42_integration.policy import digest


@pytest.fixture
def inputs():
    begin=pd.Timestamp("2025-05-01",tz="Etc/GMT-10").timestamp();issue=begin-21600
    known=[];native=[];roster=[]
    defs=[("fixed",4,"RUNNING","B",issue-900),
          ("a",1,"RUNNING",None,begin-1000),("b",2,"RUNNING",None,begin-2000),
          ("pending-z",1,"PENDING",None,None),("pending-a",1,"PENDING",None,None),
          ("done",1,"COMPLETED",None,issue-900)]
    for i,(uid,gpu,state,site,start) in enumerate(defs):
        submit=issue-10000 if state!="PENDING" else issue-9000
        compatible=["B","C"] if gpu==4 else ["A","B","C"]
        source=dict(job_uid=uid,GPU_gang=gpu,submit_time=submit,Q50_total_seconds=50,
            compatible_sites=compatible,source_member="fixture",source_row=i,
            request_version_history="UNVERIFIED_SOURCE_PROXY",release_seconds=begin if state=="PENDING" else None)
        known.append(source)
        native.append(dict(source,state="RUNNING" if state in {"RUNNING","COMPLETED"} else "PENDING",
            current_site_if_running=site,full_requested_seconds=3600,cohort="normal|gpu-proxy"))
        roster.append(dict(job_uid=uid,GPU_gang=gpu,boundary_source_state=state,
            source_submit_seconds=submit,observed_start_seconds=start,
            observed_completion_seconds=begin-900 if state=="COMPLETED" else None,
            observed_control_release_seconds=begin-900 if state=="COMPLETED" else None,
            current_model_site=site,original_native_site=site,
            elapsed_compute_seconds_at_boundary=None if start is None else begin-start,
            frozen_Q50_total_seconds=50,compatible_sites=compatible,origin_unknown=False,
            source_member="fixture",source_row=i))
    plan=dict(day="2025-05-01",known_population=known,capacities={"A":3,"B":6,"C":4},
        rack_compatibility={"A":[3],"B":[6],"C":[4]},forecast_inputs={"current_CC4":{"fixture":True}})
    packet=dict(known_population=native,runtime_provider="fixture")
    actual=dict(post_issue_arrivals=[])
    candidate=dict(Actual_begin_seconds=begin,Actual_end_seconds=begin+86400,slots=96,
        planning_issue_seconds=issue,initial_source_roster=roster,excluded_UIDs=["done"])
    candidate["initial_state_sha"]=digest(candidate)
    return candidate,plan,packet,actual


def make(inputs,**options):
    options.setdefault("pr129_recovery",dict(audit_completed=True,validated_pins={}))
    return initialize_from_candidate(*inputs,**options)


def save(tmp_path,freeze):
    path=tmp_path/"FREEZE.json";path.write_text(json.dumps(freeze),encoding="utf8");return path


def test_existing_pr125_fixed_first_hard_q50_overrun_and_deterministic_fallback(inputs):
    before=deepcopy(inputs)
    freeze=make(inputs)
    rows={r["uid"]:r for r in freeze["running"]}
    assert freeze["mapping"]=={"a":"A","b":"A","fixed":"B"}
    assert freeze["site_GPU_use"]=={"A":3,"B":4,"C":0}
    assert rows["fixed"]["initial_site_authority"]==FIXED
    assert rows["a"]["initial_site_authority"]==FALLBACK
    assert rows["fixed"]["q50"]==50 and rows["fixed"]["elapsed_compute_seconds"]==22500
    assert rows["fixed"]["gpu"]==4
    assert freeze["PR125_reference_audit"]["optimizer_calls"]==0
    assert freeze["counts"]["running_GPU"]==7
    assert inputs==before
    shuffled=deepcopy(inputs);shuffled[0]["initial_source_roster"].reverse()
    shuffled[0]["initial_state_sha"]=digest({k:v for k,v in shuffled[0].items() if k!="initial_state_sha"})
    result=make(shuffled)
    assert result["mapping"]==freeze["mapping"] and result["running"]==freeze["running"]


def test_complete_submit_uid_fcfs_queue_no_initial_admission_and_past_completed_exclusion(inputs):
    freeze=make(inputs)
    assert [r["uid"] for r in freeze["pending"]]==["pending-a","pending-z"]
    assert [r["queue_position"] for r in freeze["pending"]]==[1,2]
    assert all(r["site"] is None and r["metadata"]["release_seconds"]==freeze["begin_epoch_seconds"] for r in freeze["pending"])
    assert all(r["metadata"]["protected"] is None and r["metadata"]["batch_eligible"] is None for r in freeze["pending"])
    assert len(freeze["historical_completed"])==1 and freeze["historical_completed"][0]["job_uid"]=="done"
    assert not {r["uid"] for r in freeze["running"]+freeze["pending"]}.intersection(freeze["excluded_44uids"])
    assert freeze["MODEL_ASSUMPTION"] and not freeze["KESTREL_OBSERVED_SITE"] and not freeze["KESTREL_OBSERVED_QUEUE"]
    assert freeze["Actual_full96_status"]==freeze["Fresh_AC_full96_status"]=="NOT_RUN"


def pin(inputs):
    row=next(r for r in inputs[0]["initial_source_roster"] if r["job_uid"]=="a")
    return dict(PASS=True,episode_id=_episode("a",row["source_submit_seconds"]),site="C",
        observed_start_seconds=row["observed_start_seconds"],gpu=1,
        assigned_at_seconds=inputs[0]["planning_issue_seconds"],policy_independent=True,
        future_completion_used=False,grid_or_policy_result_used=False)


def test_validated_reference_pin_reused_before_residual_placement(inputs):
    freeze=make(inputs,pr129_recovery=dict(audit_completed=True,validated_pins={"a":pin(inputs)}))
    assert freeze["mapping"]=={"a":"C","b":"A","fixed":"B"}
    assert freeze["PR129_reused_jobs"]==1 and freeze["PR125_fallback_jobs"]==1
    assert next(r for r in freeze["running"] if r["uid"]=="a")["initial_site_authority"]==REUSED
    for change in (dict(episode_id="other"),dict(future_completion_used=True),
                   dict(grid_or_policy_result_used=True),dict(assigned_at_seconds=inputs[0]["Actual_begin_seconds"]+1)):
        bad=dict(pin(inputs),**change)
        with pytest.raises(ValueError,match="PIN_IDENTITY_CAUSAL_AUTHORITY"):
            make(inputs,pr129_recovery=dict(audit_completed=True,validated_pins={"a":bad}))


def test_pr129_cannot_move_fixed_site_or_pin_nonrunning_uid(inputs):
    row=next(r for r in inputs[0]["initial_source_roster"] if r["job_uid"]=="fixed")
    p=dict(pin(inputs),episode_id=_episode("fixed",row["source_submit_seconds"]),gpu=4,
           observed_start_seconds=row["observed_start_seconds"],site="C")
    with pytest.raises(ValueError,match="FIXED151_CONFLICT"):
        make(inputs,pr129_recovery=dict(audit_completed=True,validated_pins={"fixed":p}))
    with pytest.raises(ValueError,match="NOT_IN_DDAY_RUNNING"):
        make(inputs,pr129_recovery=dict(audit_completed=True,validated_pins={"pending-a":pin(inputs)}))


def test_no_future_grid_mess_or_source_proxy_outcome_enters_site_or_metadata(inputs):
    expected=make(inputs)
    changed=deepcopy(inputs)
    for row in changed[1]["known_population"]:
        row.update(actual_end_seconds=10**12,future_queue="AFTER00",line_loading=1000,MESS_result=9000,
                   end_observed_by_day_end="2099-01-01T00:00:00Z",actual_remaining=-5)
    result=make(changed)
    assert result["mapping"]==expected["mapping"]
    assert result["running"]==expected["running"] and result["pending"]==expected["pending"]
    forbidden={"actual_end_seconds","future_queue","line_loading","MESS_result","end_observed_by_day_end","actual_remaining"}
    assert all(not forbidden.intersection(r["metadata"]) for r in result["running"]+result["pending"])


def test_four_arm_reload_same_sha_and_corruption_rejected(inputs,tmp_path):
    freeze=make(inputs);path=save(tmp_path,freeze)
    loaded=[load_dday_state(path,arm=arm) for arm in ARMS]
    assert all(p["common_initial_state_sha"]==freeze["common_initial_state_sha"] for p in loaded)
    assert all(p["mapping"]==freeze["mapping"] and p["pending"]==freeze["pending"] for p in loaded)
    changed=deepcopy(freeze);changed["mapping"]["a"]="C"
    path=save(tmp_path,changed)
    with pytest.raises(ValueError,match="FREEZE_SHA_DRIFT"):load_dday_state(path)
    changed["freeze_sha"]=digest({k:v for k,v in changed.items() if k!="freeze_sha"})
    path=save(tmp_path,changed)
    with pytest.raises(ValueError,match="PAYLOAD_SHA_DRIFT"):load_dday_state(path)


def test_original_compatible_mask_not_widened_and_greedy_failure_not_infeasible(inputs):
    changed=deepcopy(inputs)
    row=next(r for r in changed[0]["initial_source_roster"] if r["job_uid"]=="a")
    row["compatible_sites"]=["C"]
    changed[0]["initial_state_sha"]=digest({k:v for k,v in changed[0].items() if k!="initial_state_sha"})
    with pytest.raises(ValueError,match="REQUEST_SPECIFIC_COMPATIBILITY"):
        make(changed)
    changed=deepcopy(inputs);changed[1]["capacities"]["B"]=3
    with pytest.raises(ValueError,match="GREEDY_NOT_FOUND_NO_INFEASIBILITY_CLAIM"):
        make(changed)


def test_runtime_and_cc4_identifiers_retained_when_parent_adds_provider_binding(inputs):
    baseline=make(inputs)
    added=make(inputs,provider_identifiers={"planning_provider_sha":"planning-only-provider"})
    for key,value in baseline["provider_identifiers"].items():
        assert added["provider_identifiers"][key]==value
    assert added["provider_identifiers"]["planning_provider_sha"]=="planning-only-provider"
    assert added["common_initial_state_sha"]!=baseline["common_initial_state_sha"]
    with pytest.raises(ValueError,match="FROZEN_PROVIDER_IDENTIFIER_DRIFT"):
        make(inputs,provider_identifiers={"CC4_provider_sha":"incorrect-CC4-source"})


def test_direct_adapter_cannot_authorize_without_completed_pr129_audit(inputs):
    with pytest.raises(ValueError,match="REFERENCE_REUSE_AUDIT_REQUIRED"):
        initialize_from_candidate(*inputs)
