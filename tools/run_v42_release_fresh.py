"""Offline original 11-SVR Fresh verification of RC01 first16 Actual power.

Realized interval exogenous data are used only here, after controller execution.
This certificate does not replace current-instant candidate admission evidence.
"""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_integration.actual_validation import fresh_ac_minimum
from v42_integration.isolated_unknown import no_native
from v42_integration.partial_canary import resource_snapshot

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
OLD=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
LEDGERS=[RC.parent.parent/'UNIFIED_NATIVE_RUNTIME_LEDGER.json',RC/'A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json']

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--actual',type=Path,default=RC/'AIDC/REPLAY02');args=parser.parse_args()
    out=args.actual;target=out/'OFFLINE_FRESH_16_STATUS.json'
    if target.exists():raise FileExistsError('RELEASE_FRESH_MUST_NOT_OVERWRITE')
    before=[file_record(p) for p in LEDGERS]
    common=read(out/'COMMON_RUN_INPUTS.json');done=read(out/'COMPARISON_COMPLETE.json')
    assert done['status']=='COMPARISON_COMPLETE' and not done['new_D0_full_chain']
    executed=read(out/'EXECUTED_SOURCE.json');assert all(file_record(r['path'])==r for r in executed['files'])
    mess=read(OLD/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    execution=read(OLD/'MESS_ACTUAL_EXECUTION_RECEIPT.json')
    assert mess['plan_sha']==common['MESS_plan_sha']
    historical=read(OLD/'PLANNING_FREEZE.json')['source_freeze']
    by_path={r['path']:r for r in historical['files']}
    for r in executed['files']+[file_record(__file__)]:
        if r['path'] in by_path:assert by_path[r['path']]==r
        by_path[r['path']]=r
    records=list(by_path.values())
    freeze=dict(science_version='RC01_BASIC_INITIAL_STAY_OPTIONAL_PENDING_PRESITE_OFFLINE_FRESH_V1',
        files=records,source_sha=digest(records))
    _write(out/'OFFLINE_FRESH_SOURCE_FREEZE.json',freeze)
    report=dict(status='NOT_RUN',scope='DIAGNOSTIC_PR223_FIXED_MESS_FIRST16_OFFLINE_REALIZED_AC',
        observation_scope='RETROSPECTIVE_INTERVAL_END_EXOGENOUS_NOT_CONTROLLER_INPUT',slots=16,
        full96_claim=False,new_D0_full_chain=False,current_candidate_safety_certified_by_this_report=False,
        Native_calls=0,variants={})
    began=perf_counter()
    with no_native() as attempts:
        for label in ('C0','C1'):
            base=out/label;snapshot=resource_snapshot();_write(base/'RESOURCE_BEFORE_FRESH.json',snapshot)
            mem=snapshot['memory']
            if mem['AvailableMBytes']<8192 or mem['PercentCommittedBytesInUse']>=75:
                report['variants'][label]=dict(status='NOT_RUN',reason='RAM_COMMIT_GATE');break
            actual=read(base/'ACTUAL_RESULT.json');assert actual['slots']==16
            assert actual['release_case_sha']==common['release_case_sha']
            assert not any(actual['receipt'][k] for k in ('capacity_violations','dropped_jobs','future_duration_controller_reads','future_completion_controller_reads'))
            with np.load(base/'ACTUAL_GPU_PQ.npz',allow_pickle=False) as packet:a={k:packet[k].copy() for k in packet.files}
            assert all(a[k].shape==(16,12) and np.isfinite(a[k]).all() for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar'))
            trace=base/'OFFLINE_FRESH_INPUT.npz'
            if trace.exists():raise FileExistsError('RELEASE_FRESH_INPUT_MUST_NOT_OVERWRITE')
            np.savez_compressed(trace,sites=a['sites'],timestamps_start_epoch_seconds=a['slot_start_seconds'],
                **{k:a[k] for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar')})
            t=perf_counter()
            fresh=fresh_ac_minimum(RAW,base,base/'OFFLINE_FRESH_16',source_freeze=freeze,
                campaign_manifest='D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json',
                slots=16,mess_plan=mess,mess_execution_receipt=execution,trace_path=trace,arm='B3',
                case_scope=dict(partial_actual_trace_authorized=True,evaluation_case_sha=common['release_case_sha'],
                    common_initial_state_sha=common['historical_PR223_source']['initial_semantic_sha'],
                    policy=label,observation_scope=report['observation_scope'],new_D0_joint_optimization=False,full96=False))
            rows=read(base/'OFFLINE_FRESH_16/FRESH_PHYSICAL_SLOTS.json')
            physical=[r['physical'] for r in rows]
            report['variants'][label]=dict(status=fresh['status'],receipt=file_record(base/'OFFLINE_FRESH_16/FRESH_PHYSICAL_RESULT.json'),
                measured_wall_seconds=perf_counter()-t,AC_wall_seconds=fresh['AC_wall_seconds'],
                installed_SVR_count=11,original_RegControl=7,
                violations={k:fresh[k] for k in ('voltage_violation_cells','line_current_violation_cells',
                    'transformer_current_violation_cells','transformer_kVA_violation_cells')},
                physical_keys=sorted(physical[0]))
    after=[file_record(p) for p in LEDGERS];assert before==after
    report.update(status='PASS' if len(report['variants'])==2 and all(r['status']=='PASS' for r in report['variants'].values()) else 'NOT_CERTIFIED',
        blocked_native_attempts=attempts,wall_seconds=perf_counter()-began,Native_ledgers_byte_identical=True,ledgers=after)
    _write(target,report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
