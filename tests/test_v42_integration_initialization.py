"""Synthetic issue-state initialization boundaries; no Optimize execution."""
from dataclasses import asdict, replace
import json

import pytest

from v42_integration.initialization import (InitialRunningJob, initialize_running, load_initialization,
                                           exact_feasibility_model, _capacity, POLICY_ID, PR79_HELPER_SHA)
from v42_integration.m_engine import file_record


def receipt(tmp_path):
    path=tmp_path/"ISSUE_ONLY_FIXTURE.json"
    path.write_text('{"scope":"synthetic issue-only fixture"}',encoding="utf8")
    return file_record(path)


def job(uid, authority, gpu=1, compatible=("A", "B"), **changes):
    return replace(InitialRunningJob(uid,"episode:"+uid,-3600,-900,gpu,compatible,
        authority["sha256"],authority["sha256"]),**changes)


def test_all254_210fixed_44missing59_gpu_mapping_spread_and_reload_all_arms(tmp_path):
    source=receipt(tmp_path)
    sites=tuple("AIDC%02d"%i for i in range(1,13))
    capacities={s:80 for s in sites}
    rows=[job("fixed%03d"%i,source,compatible=sites) for i in range(210)]
    rows += [job("missing%03d"%i,source,2 if i<15 else 1,sites) for i in range(44)]
    fixed={"fixed%03d"%i:sites[i%12] for i in range(210)}
    result=initialize_running(rows,capacities,{s:(80,) for s in sites},fixed,issue_seconds=0,
        source_receipts=[source],expected_counts=dict(running=254,fixed=210,unassigned=44,unassigned_GPU=59),
        output=tmp_path/"ARTIFACTS")
    assert result["decision"]["PASS"]
    assert result["decision"]["fixed_site_changes"]==0
    assert result["capacity_replay"]["input_running_GPU"]==269
    assert sum(result["capacity_replay"]["use_by_site"].values())==269
    mapping=result["policy"]["mapping"]
    assert len({mapping["missing%03d"%i] for i in range(44)})==12
    assert all(mapping[uid]==site for uid,site in fixed.items())
    assert result["policy"]["exact_feasibility"]["Optimize_calls"]==0
    reverse=initialize_running(list(reversed(rows)),capacities,{s:(80,) for s in sites},fixed,
        issue_seconds=0,source_receipts=[source])
    assert reverse["policy"]["mapping"]==mapping
    policies=[load_initialization(tmp_path/"ARTIFACTS/SYNTHETIC_INITIALIZATION_POLICY.json",arm=arm)
              for arm in ("B0","B1","B2","B3")]
    assert all(p["mapping"]==mapping for p in policies)
    assert all(p["KESTREL_OBSERVED_SITE"] is False and p["SOURCE18R_NUMERICALLY_IDENTICAL"] is False for p in policies)
    assert policies[0]["PR79_reuse"]["original_sha"]==PR79_HELPER_SHA


def test_fixed_overload_cannot_move_or_drop_running_gangs(tmp_path):
    source=receipt(tmp_path)
    rows=[job("one",source,2),job("two",source,2)]
    result=initialize_running(rows,{"A":3,"B":3},{"A":(3,),"B":(3,)},{"one":"A","two":"A"},
                              issue_seconds=0,source_receipts=[source])
    assert result["decision"]["status"]=="UNRESOLVED_SOURCE_AUTHORITY"
    assert result["policy"]["mapping"]=={"one":"A","two":"A"}
    assert result["capacity_replay"]["input_running_jobs"]==2
    assert result["capacity_replay"]["dropped_jobs"]==result["capacity_replay"]["split_gangs"]==0


def test_original_gpu_type_preserved_and_rack_nonadditive(tmp_path):
    source=receipt(tmp_path)
    typed=job("typed",source,2,gpu_type="H100")
    result=initialize_running([typed],{"A":8,"B":8},{"A":(1,1,1,1),"B":(2,)},{},issue_seconds=0,
        source_receipts=[source],site_gpu_types={"A":("H100",),"B":("H100",)})
    assert result["decision"]["PASS"] and result["policy"]["mapping"]["typed"]=="B"
    assert result["policy"]["per_job"][0]["gpu_type"]=="H100"
    blocked=initialize_running([typed],{"A":8,"B":8},{"A":(8,),"B":(8,)},{},issue_seconds=0,
        source_receipts=[source],site_gpu_types={"A":("A100",),"B":("A100",)})
    assert not blocked["decision"]["PASS"] and blocked["policy"]["mapping"]["typed"] is None
    assert not blocked["policy"]["exact_feasibility"]["infeasibility_proven"]


def test_verified_episode_pin_identity_timing_and_frozen_site_conflicts(tmp_path):
    source=receipt(tmp_path)
    row=job("prior",source)
    pin=dict(episode_id=row.episode_id,site="B",assigned_at_seconds=-1800,known_start_seconds=-900,
        source_receipt=source,policy_independent=True,episode_capacity_validated=True)
    result=initialize_running([row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},issue_seconds=0,
                             source_receipts=[source],prior_verified_pins={row.uid:pin})
    assert result["policy"]["mapping"][row.uid]=="B"
    assert result["policy"]["per_job"][0]["disposition"]=="EXACT_PRIOR_SITE_RECOVERED"
    for changed in (dict(pin,episode_id="different"),dict(pin,assigned_at_seconds=1),
                    dict(pin,episode_capacity_validated=False)):
        with pytest.raises(ValueError,match="PIN_CAUSAL_OR_IDENTITY"):
            initialize_running([row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},issue_seconds=0,
                               source_receipts=[source],prior_verified_pins={row.uid:changed})
    with pytest.raises(ValueError,match="FROZEN_210_SITE_PIN_CONFLICT"):
        initialize_running([row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{row.uid:"A"},issue_seconds=0,
                           source_receipts=[source],prior_verified_pins={row.uid:pin})


def test_future_labels_grid_results_and_duplicate_episode_rejected(tmp_path):
    source=receipt(tmp_path)
    row=job("one",source)
    for field in ("actual_end_seconds","future_queue","MESS_result","line_loading"):
        with pytest.raises(ValueError,match="NONOBSERVED_OR_FUTURE_INPUT"):
            initialize_running([dict(asdict(row),**{field:123})],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},
                               issue_seconds=0,source_receipts=[source])
    with pytest.raises(ValueError,match="DUPLICATE_INITIAL_UID_OR_EPISODE"):
        initialize_running([row,row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},issue_seconds=0,source_receipts=[source])
    with pytest.raises(ValueError,match="CAUSAL_INITIAL_RUNNING"):
        initialize_running([replace(row,known_start_seconds=1)],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},
                           issue_seconds=0,source_receipts=[source])


def test_greedy_failure_not_infeasibility_and_complete_small_model_native0(tmp_path):
    source=receipt(tmp_path)
    # UID-sorted greedy places 'a' on A; b only fits A. A feasible assignment
    # exists (a->B,b->A), so greedy failure cannot be promoted to INFEASIBLE.
    rows=[job("a",source,2),job("b",source,2,("A",))]
    result=initialize_running(rows,{"A":2,"B":2},{"A":(2,),"B":(2,)},{},issue_seconds=0,source_receipts=[source])
    assert not result["decision"]["PASS"]
    assert result["policy"]["exact_feasibility"]["status"]=="NOT_EXECUTED"
    assert result["decision"]["greedy_failure_is_not_infeasibility"]
    model,variables=exact_feasibility_model(rows,_capacity({"A":2,"B":2},{"A":(2,),"B":(2,)}),{},None,
                                          site_order=("A","B"))
    try:
        assert model.NumVars==3 and model.NumConstrs==4
        assert model.NumBinVars==3 and all(var.Obj==0 for var in variables.values())
        assert model.Params.Threads==1
    finally:model.dispose()


def test_reload_signature_source_drift_and_counts_guard(tmp_path):
    source=receipt(tmp_path)
    row=job("one",source)
    with pytest.raises(ValueError,match="COUNTS_CHANGED"):
        initialize_running([row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},issue_seconds=0,
                           source_receipts=[source],expected_counts={"running":254})
    initialize_running([row],{"A":4,"B":4},{"A":(4,),"B":(4,)},{},issue_seconds=0,
                       source_receipts=[source],output=tmp_path/"OUT")
    path=tmp_path/"OUT/SYNTHETIC_INITIALIZATION_POLICY.json"
    value=json.loads(path.read_text())
    value["mapping"]["one"]="B"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="SHA_MISMATCH"):load_initialization(path)
