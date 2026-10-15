"""Supervisor receipts for the read-only PR223 conditional diagnostic."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.unified_contract import digest
from v42_integration.dday_initialization import load_dday_state
from v42_integration.partial_canary import resource_snapshot

BASE='89b4ee6b63ca7847dd6f2cbd2720052f66949d39'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
OLD=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
INITIAL=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'BASELINE_SOURCE_AND_CASE_AUDIT.json').exists():raise FileExistsError('ISOLATED_SOURCE_AUDIT_MUST_NOT_OVERWRITE')
    state=load_dday_state(INITIAL,arm='B3')
    initial=file_record(INITIAL)
    assert initial['sha256']=='d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003'
    assert state['common_initial_state_sha']=='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'
    assert (len(state['running']),sum(r['gpu'] for r in state['running']),len(state['pending']))==(324,472,1300)
    earlier=read(ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP/RECOVERY_01/INDEPENDENT_PR223_SAVED_EVIDENCE_AUDIT.json')
    records=[]
    for key in ('A1','A2'):
        expected=earlier['stages'][key]['artifact'];actual=file_record(expected['path'])
        assert all(expected[k]==actual[k] for k in ('path','bytes','sha256'));records.append(actual)
    freeze=read(OLD/'PLANNING_FREEZE.json')
    freeze_record=file_record(OLD/'PLANNING_FREEZE.json')
    assert freeze_record['sha256']=='098565139dbac38a11add42a6a3cfcd7c1ebafbd4a8e2461a58f6b9f39691ca3'
    records.append(freeze_record)
    mess_path=OLD/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json'
    mess=read(mess_path);mess_record=file_record(mess_path)
    assert mess_record['sha256']=='72be8ee7c73024643bcce927eb2373c40872bc06fb9e9c9da98b6b6b84cb8656'
    assert mess['plan_sha']==digest({k:v for k,v in mess.items() if k!='plan_sha'})
    assert mess['plan_sha']==freeze['stages']['M2']['mess']['plan_sha']
    records.append(mess_record)
    source=Path('D:/v42_common_am_qos_integration_20261013/v42_integration/actual.py')
    assert file_record(source)['sha256']=='e27b6ad697006d33c67c9ddc612bf9508006f38af3052c36ba986f71361dcc38'
    source_text=source.read_text(encoding='utf8')
    assert 'PRE_DDAY_START_COMMAND_NOT_REPLAYED' in source_text
    current=ROOT/'v42_integration/actual.py'
    begin=state['begin_epoch_seconds']
    classification=dict(known_at_D0=len(state['running'])+len(state['pending']),
        previous_D1_unknown_reclassified=sum(r['origin_unknown'] for r in state['running']+state['pending']),
        classification_source='PUBLIC_INITIAL_SUBMIT_AND_STATUS_AT_D0',future_day_Unknown_expected=696,
        future_day_Unknown_status='TO_BE_RECONFIRMED_FROM_PRIVATE_ACTUAL_SOURCE',
        previous_D1_population_not_mixed=True)
    ledger=ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    budget=read(ledger);assert len(budget['calls'])==14 and budget['inflight'] is None
    assert abs(budget['conservative_solve_seconds']-318.68099999427795)<1e-9
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'--',
        'docs/v42_unified_aidc_mess_research_20261014'],cwd=ROOT,text=True).splitlines()
    preserved=[]
    for relative in paths:
        blob=subprocess.check_output(['git','rev-parse',BASE+':'+relative],cwd=ROOT,text=True).strip()
        current_blob=subprocess.check_output(['git','hash-object','--no-filters',relative],cwd=ROOT,text=True).strip()
        if blob!=current_blob:raise ValueError('ISOLATED_PRIOR_REPORT_BYTES_DRIFT:'+relative)
        preserved.append(dict(path=relative,git_blob=blob,byte_equal=True))
    _write(OUT/'PRIOR_ARTIFACT_BYTE_SNAPSHOT.json',dict(status='PASS',base=BASE,files=preserved,
        canonical_native_ledger_included=True,old_files_modified=False))
    _write(OUT/'NATIVE_LEDGER_BEFORE.json',budget)
    resource=resource_snapshot()
    _write(OUT/'RESOURCE_BEFORE.json',resource)
    audit=dict(schema='PR223_FIXED_MESS_DIAGNOSTIC_SOURCE_AUDIT_V1',status='PASS',
        base_commit=BASE,initial_record=initial,initial_semantic_sha=state['common_initial_state_sha'],
        semantic_and_byte_SHA_distinct=True,counts=dict(RUNNING=324,GPU=472,PENDING=1300,AIDC=12,installed_GPU=780,
            historical_completed_UIDs=len(state['historical_completed']),excluded44_active_GPU=0),
        classification=classification,initial_sites_and_elapsed_changed=False,
        KESTREL_OBSERVED_SITE=False,approved_model_initial_state=True,
        evaluation_begin_seconds=begin,evaluation_end_seconds=begin+14400,slots=16,dt_seconds=900,
        source_timezone='FIXED_AEST_UTC+10',old_prefix_gate_used=False,new_D0_A1_gate_used=False,
        saved_planning_records=records,fixed_MESS_plan_sha=mess['plan_sha'],
        historical_known_commands_exactly_executed_claim=False,
        historical_Full96_Fresh_performance_transferred=False,new_joint_optimization_claim=False,
        original_driver_source=file_record(source),current_driver_source=file_record(current),
        prior_artifact_count=len(preserved),new_Gurobi_Native_calls=0,Actual_global_MILP_calls=0,
        native_before=file_record(ledger),used_native_seconds=budget['conservative_solve_seconds'],
        remaining_native_seconds=budget['limit_seconds']-budget['conservative_solve_seconds'],return_reserve_seconds=30.)
    audit['source_audit_sha']=digest(audit)
    _write(OUT/'BASELINE_SOURCE_AND_CASE_AUDIT.json',audit)
    _write(OUT/'PR223_REFERENCE_KNOWN_EXECUTION_AUDIT.json',dict(status='PASS_SOURCE_CONTRACT_NOT_NEW_REPLAY',
        source_record=file_record(source),scope='PR223_REFERENCE_QUEUE_FALLBACK_DIAGNOSTIC_ONLY',
        original_rule=earlier['driver'],historical_C_REF=earlier['original_final_audit_summary'],
        initial_public_known_UIDs=1624,preobserved78_not_future_Unknown=True,
        D0_optimized_commands_used=False,old_prefix_not_a_gate=True,
        original_reference_commands_immutable=True,Actual_corrective_ledger_separate=True,
        no_source_QoS_data_or_checkpoint_authority_added=True))
    print(json.dumps(dict(status='PASS',old_reports_byte_identical=len(preserved),
        initial=state['counts'],fixed_MESS_plan_sha=mess['plan_sha'],classification=classification),indent=2))


if __name__=='__main__':main()
