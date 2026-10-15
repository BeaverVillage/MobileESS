"""Supervisor physical prefix evaluation after the measured replay gates."""
from pathlib import Path
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

OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
OLD=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
LEDGER=OUT.parent/'UNIFIED_NATIVE_RUNTIME_LEDGER.json'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    status_path=OUT/'C0_C1_FRESH_AC_STATUS.json'
    if status_path.exists():raise FileExistsError('ISOLATED_FRESH_RECEIPT_MUST_NOT_OVERWRITE')
    before=file_record(LEDGER)
    common=read(OUT/'C0_C1_COMMON_INPUT_CERTIFICATE.json')
    if common['status']!='PASS':raise ValueError('ISOLATED_COMMON_INPUT_GATE_REQUIRED')
    result=read(OUT/'COMPARISON_COMPLETE.json')
    if result.get('status')!='EXECUTED' or not result.get('real_16_slot_replay'):
        raise ValueError('ISOLATED_REAL_16_SLOT_REPLAY_REQUIRED')
    inputs=read(OUT/'COMMON_RUN_INPUTS.json')
    freeze=read(OLD/'PLANNING_FREEZE.json')
    mess=read(OLD/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    execution=read(OLD/'MESS_ACTUAL_EXECUTION_RECEIPT.json')
    if mess['plan_sha']!=inputs['fixed_MESS_plan_sha']:raise ValueError('ISOLATED_FRESH_FIXED_MESS_DRIFT')
    # Freeze the exact current evaluation code separately from the read-only
    # historical Planning source and raw input receipts.
    names=['v42_integration/isolated_unknown.py','v42_integration/actual.py',
        'v42_integration/actual_validation.py','v42_integration/aidc_sensitivity_runtime.py',
        'v42_integration/qos.py','v42_integration/sensitivity_policy.py',
        'v42_integration/production_case.py','tools/run_v42_isolated_fresh.py']
    records=[file_record(ROOT/p) for p in names]
    current_freeze=dict(science_version='PR223_FIXED_MESS_ISOLATED_UNKNOWN_RANKING_DIAGNOSTIC_V1',
        files=records,source_sha=digest(records))
    _write(OUT/'FRESH_ACTUAL_SOURCE_FREEZE.json',current_freeze)
    report=dict(status='NOT_RUN',scope='FIXED_PR223_M2_REAL_FIRST16_ONLY',slots=16,
        Gurobi_Native_calls=0,Actual_global_MILP_calls=0,full96_claim=False,
        historical_Fresh_performance_transferred=False,variants={},wall_seconds=0.)
    began=perf_counter()
    with no_native() as attempts:
        for label in ('C0','C1'):
            snapshot=resource_snapshot()
            memory=snapshot['memory']
            _write(OUT/(label+'_RESOURCE_BEFORE_FRESH.json'),snapshot)
            if memory['AvailableMBytes']<8192 or memory['PercentCommittedBytesInUse']>=75:
                report['variants'][label]=dict(status='NOT_RUN',reason='RAM_COMMIT_GATE');break
            p=OUT/label/'ACTUAL_GPU_PQ.npz'
            with np.load(p,allow_pickle=False) as packet:
                arrays={k:packet[k].copy() for k in packet.files}
            if arrays['GPU'].shape!=(16,12) or arrays['PCC_P_kw'].shape!=(16,12):
                raise ValueError('ISOLATED_EXACT_FIRST16_PHYSICAL_ARRAY_REQUIRED')
            if any(not np.isfinite(arrays[k]).all() for k in ('GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar')):
                raise ValueError('ISOLATED_FINITE_ACTUAL_POWER_REQUIRED')
            actual=read(OUT/label/'ACTUAL_RESULT.json')
            receipt=actual['receipt']
            if receipt.get('capacity_violations',0) or receipt.get('dropped_jobs',0):
                raise ValueError('ISOLATED_PHYSICAL_REPLAY_GATE_FAILED')
            trace=OUT/label/'FRESH_INPUT_TRACE.npz'
            np.savez_compressed(trace,sites=arrays['sites'],timestamps_start_epoch_seconds=arrays['slot_start_seconds'],
                GPU=arrays['GPU'],compute_GPU=arrays['compute_GPU'],IT_kw=arrays['IT_kw'],
                PCC_P_kw=arrays['PCC_P_kw'],PCC_Q_kvar=arrays['PCC_Q_kvar'])
            start=perf_counter()
            try:
                fresh=fresh_ac_minimum(RAW,OUT/label,OUT/label/'FRESH_16',source_freeze=current_freeze,
                    campaign_manifest='D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json',
                    slots=16,mess_plan=mess,mess_execution_receipt=execution,trace_path=trace,arm='B3',
                    case_scope=dict(partial_actual_trace_authorized=True,
                        evaluation_case_sha=inputs['diagnostic_case_sha'],
                        common_initial_state_sha=inputs['initial_semantic_sha'],
                        known_contract='PR223_REFERENCE_DIAGNOSTIC_NOT_EXACT_OPTIMIZED_PLAN',
                        policy=label,fixed_MESS_plan_sha=mess['plan_sha'],
                        new_D0_joint_optimization=False,full96=False))
                report['variants'][label]=dict(status=fresh['status'],receipt=file_record(OUT/label/'FRESH_16/FRESH_PHYSICAL_RESULT.json'),
                    measured_wall_seconds=perf_counter()-start,AC_wall_seconds=fresh['AC_wall_seconds'],
                    installed_SVR_count=11,original_RegControl=7,
                    voltage_violation_cells=fresh['voltage_violation_cells'],
                    line_current_violation_cells=fresh['line_current_violation_cells'],
                    transformer_current_violation_cells=fresh['transformer_current_violation_cells'],
                    transformer_kVA_violation_cells=fresh['transformer_kVA_violation_cells'])
            except Exception as exc:
                report['variants'][label]=dict(status='FAIL',error_type=type(exc).__name__,error=str(exc),
                    measured_wall_seconds=perf_counter()-start)
    after=file_record(LEDGER)
    if before!=after:raise ValueError('ISOLATED_FRESH_NATIVE_LEDGER_MUST_REMAIN_BYTE_IDENTICAL')
    report.update(status='PASS' if len(report['variants'])==2 and all(v['status']=='PASS' for v in report['variants'].values())
        else 'NOT_CERTIFIED',wall_seconds=perf_counter()-began,blocked_native_attempts=attempts,
        canonical_native_ledger_byte_identical=True,canonical_ledger=after)
    _write(status_path,report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
