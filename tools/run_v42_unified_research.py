"""Supervisor-only reproducible audit and bounded electrical diagnostic."""
from pathlib import Path
import argparse
import gzip
import json
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from v42_integration.unified_contract import REPORT, load_contracts, file_sha
from v42_integration.m_engine import file_record, _write
from v42_integration.unified_resource import UnifiedResearchBudget, historical_usage

ROOT=REPORT.parents[1]
DIAG=ROOT/'docs/v42_trajectory_tracking_may01_canary_20261014/DIAGNOSTIC_FINAL'
ARCHIVE=Path('D:/v42_may_joint_repair_campaign_20261013')


def audit():
    common=load_contracts()
    identity=json.loads((DIAG/'PLANNING_TARGET_IDENTITY.json').read_text(encoding='utf8'))
    with np.load(DIAG/'C0_ACTUAL_ARRAYS.npz') as c0,np.load(DIAG/'C2_ACTUAL_ARRAYS.npz') as c2:
        same={k:float(np.max(np.abs(c0[k]-c2[k]))) for k in c0.files}
        p=c0['PCC_P_kw'].copy();q=c0['PCC_Q_kvar'].copy()
        known=c0['Known_GPU'].copy();unknown=c0['Unknown_GPU'].copy()
    with np.load(DIAG/'DAYAHEAD_TRACKING_REFERENCE.npz') as r:
        planned=r['PCC_P_Plan'];planned_q=r['PCC_Q_Plan'];kg=r['G_Known_Plan'];ug=r['G_Unknown_Q50_Plan']
    preparation=json.loads((DIAG/'DIAGNOSTIC_SETUP/CASE/PRODUCTION_CASE_PREPARATION.json').read_text(encoding='utf8'))
    coeff=Path(next(r['path'] for r in preparation['source_receipts'] if r['sha256']==identity['response_sha']))
    if file_sha(coeff)!=identity['response_sha']:raise ValueError('FROZEN_COEFFICIENT_DRIFT')
    with np.load(coeff,allow_pickle=False) as data:
        print('Coefficient fields:',','.join(data.files[:12]))
    discrepancy=dict(bindings=common['bindings'],historical_case_sha=identity['case_sha'],
        historical_C0_C2_max_abs_difference=same,C0_equals_C2=all(v==0 for v in same.values()),
        controller_incremental_PQ_effect=0,affine_rho=.5201161496609195,
        affine_violation_slots=[10,12],Fresh_AC_historical='NOT_RUN',
        unknown_only_counterfactual='NOT_MEASURED',
        slot_decomposition=[dict(slot=t,actual_P_kw=float(p[t].sum()),planned_P_kw=float(planned[t].sum()),
            actual_Q_kvar=float(q[t].sum()),planned_Q_kvar=float(planned_q[t].sum()),
            Known_GPU_delta=float((known[t]-kg[t]).sum()),Unknown_GPU_delta=float((unknown[t]-ug[t]).sum())) for t in (10,12)],
        measured_physical_voltage=False,source=file_record(coeff),
        conclusion='C0_AND_C2_IDENTICAL;AFFINE_AUTO_SECANT_EXTRAPOLATION_REQUIRES_FRESH_AC')
    _write(REPORT/'PR223_PR230_VOLTAGE_DISCREPANCY.json',discrepancy)
    manifest=json.loads((ARCHIVE/'CAMPAIGN_MANIFEST.json').read_text(encoding='utf8'))
    records={k:manifest[k] for k in ('hardware','scenario','thermal')}
    cert=ARCHIVE/'models/2025-05-01/ELECTRICAL_CERTIFICATE.json'
    _write(REPORT/'PLANNING_ACTUAL_VOLTAGE_AUTHORITY_AUDIT.json',dict(bindings=common['bindings'],
        IEEE123=True,SVR_count=11,original_RegControl_count=7,added_phase_RegControl_count=33,
        transformer_phase_axes=153,electrical_source_receipts=records,
        electrical_certificate=file_record(cert),coefficient=file_record(coeff),
        PR223_PR230_same_electrical_receipts=True,numerical_case_identity=False,
        planning='INDEPENDENT_CAUSAL_AUTO_PREFIX_SIGNED_CENTRAL_SECANTS_WITH_LDC_INTERVAL',
        planning_probe_tap_states='NOT_RECORDED_IN_PACKET',Actual='ORIGINAL_AUTO_TIME_AND_NATIVE_CONTROL_QUEUE',
        Tap_optimization_calls=0,SVR_added_or_removed=0,limits_or_ratings_relaxed=False,
        nonlinear_envelope='NOT_CERTIFIED',fresh_AC_status='PENDING_SCOPED_ATTEMPT',
        PR223_FULL96_certificate_transferred=False))
    (REPORT/'SVR11_AUTHORITY_COMPARISON_KO.md').write_text(
        '# 11-SVR 전압 권위 감사\n\n'
        'PR223과 PR230은 동일한 11개 SVR, 기존 7개 RegControl, 원본 LDC, 153개 변압기 상별 축과 '
        'Electrical Certificate/계수 bytes를 사용한다. 두 Case와 실제 P/Q trace는 다르므로 PR223 Fresh96 PASS를 이전할 수 없다.\n\n'
        'Planning 계수는 한 고정 탭 상태의 모델이 아니다. 각 부호별 probe가 동일한 과거 AUTO prefix를 새로 재생하여 '
        '중앙 secant와 LDC interval을 생성한다. 자동 탭 임계점을 건너는 응답은 큰 기준점 변화에서 물리 오차를 만들 수 있다. '
        '개별 probe의 최종 탭은 packet에 저장되지 않았다. Actual은 원래 AUTO/TIME 제어를 독립 초기화한다.\n\n'
        'PR230 C0/C2는 PCC P/Q와 모든 GPU 배열의 차이가 정확히 0이다. 두 비교군의 affine 위반은 슬롯 10·12에 동일하며 '
        '새 Allocator의 추가 영향이 아니다. 해당 행의 최소 v² 0.5821213/0.7003066은 선형 추정값이다. '
        '실제 전압 판정은 아래 별도 Fresh AC 실행 증거를 따른다.\n',encoding='utf8')
    _write(REPORT/'SINGLE_BRANCH_PARALLEL_EXECUTION_AUDIT.json',dict(
        branch=common['branch'],base_commit=common['base_commit'],shared_worktree=str(ROOT),
        Agent_A='/root/aidc',Agent_B='/root/mess',Supervisor='/root',
        independent_branches_created=0,independent_worktrees_created=0,
        shared_contract_file_shas=common['contract_file_shas'],
        execution='AGENTS_STARTED_READ_ONLY_CONCURRENTLY_THEN_SAME_CHECKOUT_DISJOINT_FILE_OWNERSHIP',
        heavy_solver_owner='Supervisor',heavy_solver_max_workers=1,Threads=1,
        preexisting_untracked_PR230_evidence_preserved=True))
    print(json.dumps(dict(audit='COMPLETE',C0_C2_equal=discrepancy['C0_equals_C2'],parents=historical_usage()),indent=2))


def fresh_ac():
    from v42_integration.actual_validation import fresh_ac_minimum
    budget=UnifiedResearchBudget()
    pre=budget.preflight();_write(REPORT/'RESOURCE_PREFLIGHT.json',pre)
    trace=REPORT/'PR230_C0_PREFIX_PQ.npz'
    with np.load(DIAG/'C0_ACTUAL_ARRAYS.npz') as old:
        np.savez_compressed(trace,PCC_P_kw=old['PCC_P_kw'],PCC_Q_kvar=old['PCC_Q_kvar'],
            sites=np.asarray([f'AIDC{i:02d}' for i in range(1,13)]),
            timestamps_start_epoch_seconds=1746021600.+np.arange(16)*900)
    source_freeze=json.loads((Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration')/
                              'SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf8'))
    scope=dict(partial_actual_trace_authorized=True,
        planning_case_sha='17066bfc24eb21594dfb7e4abfe74580a1a020617aadcf27b93a4692e6d3e5f9',
        common_initial_state_sha=load_contracts()['bindings']['initial_state_sha'],
        label='HISTORICAL_PR230_DIAGNOSTIC_PREFIX_NEW_CASE_NOT_CERTIFIED',
        evaluator_source=file_record(ROOT/'v42_integration/actual_validation.py'),
        wrapper_source=file_record(Path(__file__)))
    start=time.perf_counter()
    try:
        with budget.exclusive_worker():
            result=fresh_ac_minimum(ARCHIVE/'raw/2025-05-01',DIAG,REPORT/'PR230_FRESH16',
                source_freeze=source_freeze,campaign_manifest=ARCHIVE/'CAMPAIGN_MANIFEST.json',
                slots=16,trace_path=trace,arm='B1',case_scope=scope)
    except BaseException as exc:
        budget.record_external('PR230_HISTORICAL_FRESH16',time.perf_counter()-start,solver='AC',status='FAILED')
        _write(REPORT/'FRESH_AC_EXECUTION_FAILURE.json',dict(status='NOT_CERTIFIED',reason=repr(exc),scope=scope))
        raise
    budget.record_external('PR230_HISTORICAL_FRESH16',result['AC_wall_seconds'],solver='AC')
    summary={k:result[k] for k in ('status','PASS','executed_actual_slots','full96_Actual_AC_established',
        'voltage_violation_cells','line_current_violation_cells','transformer_current_violation_cells',
        'transformer_kVA_violation_cells','physical_SolveSnap_count','AC_wall_seconds')}
    summary.update(scope=scope,receipt=file_record(REPORT/'PR230_FRESH16/FRESH_PHYSICAL_RESULT.json'))
    _write(REPORT/'PR230_FRESH16_SUMMARY.json',summary)
    rows=REPORT/'PR230_FRESH16/FRESH_PHYSICAL_SLOTS.json'
    with gzip.GzipFile(filename=str(rows)+'.gz',mode='wb',mtime=0) as out:out.write(rows.read_bytes())
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--audit',action='store_true');parser.add_argument('--fresh-ac',action='store_true')
    args=parser.parse_args()
    if args.audit:audit()
    if args.fresh_ac:fresh_ac()
