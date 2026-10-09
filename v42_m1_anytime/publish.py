"""Offline packet binding, timeline audit and delivery of the bounded frontier."""
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch
import json
import shutil
from .core import ROOT,CASE,BASE,REPORTS,RUNTIME,read,write,table
from . import report
from v42_unified.storage import sha

PREDECESSOR=RUNTIME/'anytime_may01_20261008_frontier01'

def packet(runtime_name):
    p=Path(runtime_name)
    if p.is_relative_to(PREDECESSOR):return REPORTS/'artifacts/segment01'/p.relative_to(PREDECESSOR)
    marker='anytime_may01_20261008_frontier02_continuation'
    root=RUNTIME/marker
    if p.is_relative_to(root):return REPORTS/'artifacts'/p.relative_to(root)
    raise ValueError('UNREGISTERED_TIMELINE_PACKET')

def timeline():
    rows=report.csvread(REPORTS/'FRONTIER_EVENTS.csv');checkpoints=report.csvread(REPORTS/'FRONTIER_CHECKPOINTS.csv')
    prior=-1;lb=ub=None
    for r in rows:
        t=float(r['actual_certificate_completion_time']);a=F(r['exact_LB']);b=F(r['exact_UB'])
        if t<prior or not 0<=a<=b or F(r['exact_gap'])!=(b-a)/abs(b):raise ValueError('EXACT_EVENT_GAP_OR_TIME_DRIFT')
        if lb is not None and (a<lb or b>ub):raise ValueError('BEST_BOUND_FRONTIER_REGRESSION')
        for kind in ('LB','UB'):
            p=packet(r[kind+'_certificate_path'])
            if sha(p)!=r[kind+'_certificate_sha256']:raise ValueError('COPIED_FRONTIER_PACKET_HASH_DRIFT')
            c=read(p)
            if not c['PASS'] or c.get('case_sha',CASE)!=CASE:raise ValueError('PACKET_CASE_OR_PROOF_FAILURE')
            key=('exact_Global_UB',) if kind=='UB' else ('exact_Global_LB','exact_bound')
            value=next(F(c[k]) for k in key if k in c)
            if value!=(b if kind=='UB' else a):raise ValueError('EVENT_NOT_BOUND_TO_MATHEMATICAL_CERTIFICATE')
        if float(r['wall_seconds'])+1e-6<t or float(r['retrospectively_validated_candidate_discovery_time'])>t:raise ValueError('FIRST_PASSAGE_BACKDATED')
        prior,lb,ub=t,a,b
    for c in checkpoints:
        t=float(c['actual_snapshot_wall_seconds'])
        eligible=[r for r in rows if float(r['actual_certificate_completion_time'])<=t]
        if not eligible:raise ValueError('CHECKPOINT_BEFORE_CERTIFICATE')
        last=eligible[-1]
        if (F(c['exact_LB']),F(c['exact_UB']))!=(F(last['exact_LB']),F(last['exact_UB'])):raise ValueError('CHECKPOINT_BACKFILLED_FROM_FUTURE')
        if F(c['exact_gap'])!=(F(c['exact_UB'])-F(c['exact_LB']))/abs(F(c['exact_UB'])):raise ValueError('CHECKPOINT_EXACT_GAP_DRIFT')
    passages=report.csvread(REPORTS/'GAP_FIRST_PASSAGE_TIMES.csv')
    for p in passages:
        eligible=[r for r in rows if 100*F(r['exact_gap'])<=F(p['threshold_percent'])]
        if bool(eligible)!=(p['status']=='REACHED'):raise ValueError('FIRST_PASSAGE_STATUS_DRIFT')
        if eligible and float(p['actual_certificate_completion_seconds'])!=float(eligible[0]['actual_certificate_completion_time']):raise ValueError('FIRST_PASSAGE_NOT_FIRST_COMPLETED_CERTIFICATE')
    return dict(PASS=True,case_sha=CASE,events=len(rows),checkpoints=len(checkpoints),first_passage_thresholds=len(passages),Native_optimize_calls=0,original_rows_proofs_bound_to_copied_packets=True,no_checkpoint_backfill=True)

def package(run_id):
    import sys
    sys.path.insert(0,str(ROOT/'cache/plotting_py311'))
    path=RUNTIME/run_id
    # The first failed receipt and ledger remain byte-for-byte unchanged.
    old=read(PREDECESSOR/'NATIVE_RUNTIME_LEDGER.json');new=read(path/'NATIVE_RUNTIME_LEDGER.json')
    n=len(old['calls'])
    for a,b in zip(old['calls'],new['calls'][:n]):
        b={k:v for k,v in b.items() if k!='completed_predecessor_ledger'}
        if a!=b:raise ValueError('FAILED_CALL_COST_CHANGED')
    if read(path/'T0_CLOCK.json')['monotonic_T0']!=read(PREDECESSOR/'T0_CLOCK.json')['monotonic_T0']:raise ValueError('ORIGINAL_WALL_RESET_FORBIDDEN')
    result=report.package(path)
    dest=REPORTS/'artifacts/segment01';dest.mkdir(exist_ok=True)
    for p in PREDECESSOR.rglob('*'):
        if p.is_file():
            target=dest/p.relative_to(PREDECESSOR);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
            if sha(p)!=sha(target):raise ValueError('FAILED_EVIDENCE_COPY_DRIFT')
    for name,digest in read(dest/'EXECUTED_SOURCE_HASHES.json').items():
        if sha(dest/'EXECUTED_SOURCE_ARCHIVE'/Path(name).name)!=digest:raise ValueError('FIRST_EXECUTED_SOURCE_ARCHIVE_DRIFT')
    for name,digest in read(path/'EXECUTED_SOURCE_HASHES.json').items():
        if sha(ROOT/name)!=digest:raise ValueError('CONTINUATION_EXECUTED_SOURCE_DRIFT')
    identity=read(REPORTS/'SCIENTIFIC_CASE_IDENTITY.json')
    original=read(PREDECESSOR/'SCIENTIFIC_CASE_IDENTITY.json')
    identity['continuation_baseline_validation_inside_original_T0_seconds']=identity['baseline_validation_wall_before_T0_seconds']
    identity['baseline_validation_wall_before_T0_seconds']=original['baseline_validation_wall_before_T0_seconds']
    identity['original_experiment_T0_UTC']=read(PREDECESSOR/'T0_CLOCK.json')['UTC']
    identity['linked_run_ids']=[PREDECESSOR.name,run_id]
    write(REPORTS/'SCIENTIFIC_CASE_IDENTITY.json',identity)
    runtime=read(REPORTS/'RUNTIME_BREAKDOWN.json');runtime.update(
        baseline_validation_before_T0_seconds=original['baseline_validation_wall_before_T0_seconds'],
        including_new_baseline_validation_seconds=original['baseline_validation_wall_before_T0_seconds']+result['monotonic_wall_seconds'],
        continuation_validation_within_T0_seconds=identity['continuation_baseline_validation_inside_original_T0_seconds'],
        first_failed_segment_Runtime_included=old['Native_Runtime_sum'],first_failed_segment_Work_included=old['Native_Work_sum'],
        software_error_and_recovery_inside_original_Wall=True,budget_reset=False)
    if runtime['including_new_baseline_validation_seconds']>5400:raise ValueError('ENTIRE_NEW_EXPERIMENT_90_MINUTE_LIMIT_EXCEEDED')
    write(REPORTS/'RUNTIME_BREAKDOWN.json',runtime)
    cp=report.csvread(REPORTS/'FRONTIER_CHECKPOINTS.csv')
    for r in cp:
        try:r['snapshot_delay_from_target_seconds']=max(0.,float(r['actual_snapshot_wall_seconds'])-float(r['target_wall_seconds']))
        except ValueError:r['snapshot_delay_from_target_seconds']=''
        r['timestamp_interpretation']='ACTUAL_SNAPSHOT_NOT_RETROSPECTIVELY_BACKDATED'
    table(REPORTS/'FRONTIER_CHECKPOINTS.csv',cp)
    scheduler=read(REPORTS/'ADAPTIVE_SCHEDULER_AUDIT.json')
    report.korean(result,identity,scheduler,cp,report.csvread(REPORTS/'GAP_FIRST_PASSAGE_TIMES.csv'))
    audit=timeline();write(REPORTS/'INDEPENDENT_TIMELINE_AND_BUDGET_AUDIT.json',dict(audit,failed_ledger_byte_preserved=True,original_T0_preserved=True,old_Native_Runtime_included=old['Native_Runtime_sum']))
    text=(REPORTS/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    text+='\n## 오류와 연속 실행의 비용 보존\n\n첫 구간은 RMP의 `ledger.cost(track=...)` 호환성 오류로 종료했고 해당 최종 receipt는 PASS=false로 보존했다. original matrix/strict RAW/독립 LB/649 회귀의 실패가 아니다. 완료된 Native를 중단하거나 재시작하지 않았다. 새 구간은 동일 최초 monotonic T0와 이전 8회 Native의 Runtime/Work 전부를 승계했다. 예산을 초기화하지 않았다. 오류 확인·수정·재검증과 공백 모두 original Wall에 포함한다. 10분 checkpoint는 재검증 뒤 실제 관측 시각이며 delay를 CSV에 표시했다. 정시 관측이나 first passage를 소급하지 않았다. 첫 구간의 원래 ledger/실패 receipt/실행 source archive는 `artifacts/segment01`에 byte 동일하게 보존했다.\n'
    for minutes in (40,60,75):
        r=next((r for r in cp if r['target_wall_seconds']==str(minutes*60)),None)
        if r:text+=f"\n- {minutes}분 목표의 실제 snapshot {float(r['actual_snapshot_wall_seconds'])/60:.4f}분: UB={r['validated_UB']}, LB={r['certified_LB']}, Gap={r['certified_gap_percent']}%."
    for first,second in ((40,60),(60,75)):
        a=next((r for r in cp if r['target_wall_seconds']==str(first*60)),None);b=next((r for r in cp if r['target_wall_seconds']==str(second*60)),None)
        if a and b:text+=f"\n- {first}→{second}분 추가 탐색: UB 감소 {float(F(a['exact_UB'])-F(b['exact_UB'])):.16g}, LB 증가 {float(F(b['exact_LB'])-F(a['exact_LB'])):.16g}, Gap 감소 {float(100*(F(a['exact_gap'])-F(b['exact_gap']))):.10f}%p."
    text+='\n\n가격 certificate의 finite-box residual 비용과 혼합 가격의 candidate/adoption을 구분했다. 최신 trajectory의 RMP 포함 또는 dual mixing이 효과적이었다는 결론은 해당 L2/L3의 독립 LB 증가가 양수인 경우에만 성립한다. 전체 정수 pricing closure가 없으므로 차량별 convex hull이 부족하다는 원인 또는 특정 grid 결합이 정수 Gap 전부를 만든다는 인과를 증명하지 않았다. 원본 다중 선로·시간 P/Q와 Route/SOC/PCS 결합은 모두 유지되며, 실제 active row와 가격별 결과를 관측 진단으로만 사용한다.\n'
    (REPORTS/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (REPORTS/'ANYTIME_HANDOFF_KO.md').write_text("""# 후속 연구 handoff

동일 May01 case SHA에서만 best point와 rational original-row dual을 독립 검증한 뒤 사용한다. `artifacts/BEST_STRICT_UB_POINT.npz`는 full replay PASS이고 best original dual은 `artifacts/BEST_EXACT_ORIGINAL_DUAL.json`이다. 다른 날짜/A2/M2/P2 또는 production으로 승계하지 않는다.

후속 Native는 새 인간 요청 아래 별도 Run ID와 preregistration을 만들며 이번 budget/ledger를 덮어쓰거나 초기화하지 않는다. archived continuation은 최초 T0를 보존하는 단 한 차례의 명시된 인터페이스 오류 복구용이며 일반 restart API가 아니다. fixed Gap 중단은 없고 원본 물리/전체 CSR/정수 gate를 보존한다. 현재 checkout source HEAD와 executed source archive SHA를 각각 확인한다. 모든 신규 파일과 TEMP/TMP는 D에 둔다.

검증된 신규 연구 파일과 byte 증거만 v42에 commit/push하고 PR189를 계속 사용한다. 원래 A186/M188/C3A162, historical ledgers와 production backend는 보존한다. P2=null/M1_ACCEPTED=false, full integer pricing closure=NOT_PROVEN을 유지한다.
""",encoding='utf-8')
    report.manifest()
    return result

def ready():
    from v42_m1_hybrid import delivery_ready as previous
    with patch.object(previous,'write',lambda *a,**k:None):receipt=previous.ready()
    v=read(REPORTS/'INDEPENDENT_FINAL_VERIFICATION.json');manifest=read(REPORTS/'SHA256_MANIFEST.json')
    if not v['PASS'] or not v['final_90_minutes_PASS'] or not v['Native_75_minutes_PASS'] or v['M1_ACCEPTED'] or v['P2_certificate'] is not None:raise ValueError('FRONTIER_DELIVERY_VERIFICATION_REQUIRED')
    required=set()
    for folder in (REPORTS,ROOT/'v42_m1_anytime'):
        for p in folder.rglob('*'):
            if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in p.parts:required.add(p.relative_to(ROOT).as_posix())
    required.update(('tests/test_v42_m1_anytime.py','Start-V42-M1-Anytime.ps1'))
    if set(manifest['files'])!=required:raise ValueError('FRONTIER_MANIFEST_COMPLETE_COVERAGE_REQUIRED')
    for name,digest in manifest['files'].items():
        if sha(ROOT/name)!=digest:raise ValueError('FRONTIER_MANIFEST_DRIFT:'+name)
    proof=timeline();ledger=read(REPORTS/'NATIVE_RUNTIME_LEDGER.json')
    if ledger['inflight'] is not None or sum(r['Native_Runtime'] for r in ledger['calls'])!=v['Native_Runtime']:raise ValueError('FRONTIER_FINAL_BUDGET_DRIFT')
    tests=read(REPORTS/'artifacts/ZERO_NATIVE_REGRESSION.json');old=read(ROOT/'docs/v42_m1_fast_hybrid_20261008/ZERO_NATIVE_REGRESSION.json')
    if tests['failed'] or set(old['passed'])-set(tests['passed']):raise ValueError('649_PASS_PRESERVATION_REQUIRED')
    receipt.update(schema='V42_INTEGRATION_HYBRID_AND_ANYTIME_FRONTIER_READY_V4',test_counts=v['tests'],native_optimize_calls=len(ledger['calls']),
        anytime_frontier=dict(PASS=True,case_sha=CASE,completed_baseline_HEAD=BASE,run_id=v['run_id'],exact_LB=v['exact_Global_LB'],exact_UB=v['exact_Global_UB'],gap_percent=v['certified_gap_percent'],Native_Runtime=v['Native_Runtime'],Work=v['Work'],Wall=v['monotonic_wall_seconds'],failed_costs_included=True,budget_reset=False,source_manifest_sha256=sha(REPORTS/'SHA256_MANIFEST.json'),timeline_audit=proof,M1_ACCEPTED=False,P2_certificate=None,production_promoted=False),
        Native_call_accounting_by_scope=dict(original_integration=0,historical_May01_joint=7,historical_May01_hybrid=16,new_linked_anytime=len(ledger['calls']),all_preserved_May01=23+len(ledger['calls'])))
    receipt['scientific_state']['new_May01_anytime_frontier']=dict(receipt['anytime_frontier'])
    receipt['anytime_fixed_Global_Gap_stop']=None
    receipt['Native_execution_scope']='linked May01 anytime segments with original monotonic T0 and all failed costs retained'
    receipt['M_handoff']['additional_anytime_contract']=str(REPORTS/'ANYTIME_HANDOFF_KO.md')
    write(ROOT/'V42_INTEGRATION_READY.json',receipt)
    return receipt

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-id');p.add_argument('--ready',action='store_true');a=p.parse_args()
    value=ready() if a.ready else package(a.run_id)
    print('ANYTIME_DELIVERY_PASS',value.get('integration_HEAD',value.get('certified_gap_percent')))
