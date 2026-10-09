"""Native=0 final audit after explicit user cancellation; never resumes a solve."""
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
from datetime import datetime,timezone
import os,shutil,subprocess,sys
import numpy as np
from .core import ROOT,CASE,BASE,RUNTIME,REPORTS,THRESHOLDS,read,write,table
from . import report,publish
from .runner import OLD,check_protection
from v42_m1_hybrid.final_verify import load_case_read_only,_strict_ub
from v42_m1_research.check_lb import check_rational_dual_certificate
from v42_unified.storage import sha

RUN='anytime_may01_20261008_frontier02_continuation'

def finalize():
    path=RUNTIME/RUN;previous=publish.PREDECESSOR
    stopped=perf_counter();t0=read(path/'T0_CLOCK.json')['monotonic_T0']
    REPORTS.mkdir(exist_ok=True)
    for origin,destination in ((path,REPORTS/'artifacts'),(previous,REPORTS/'artifacts/segment01')):
        for source in origin.rglob('*'):
            if source.is_file():
                target=destination/source.relative_to(origin);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                if sha(source)!=sha(target):raise ValueError('CANCELLED_SOURCE_EVIDENCE_COPY_DRIFT')
    ledger=read(path/'NATIVE_RUNTIME_LEDGER.json');original_ledger_sha=sha(path/'NATIVE_RUNTIME_LEDGER.json')
    incomplete=ledger['inflight']
    if incomplete is None:raise ValueError('EXPLICIT_INTERRUPTED_CALL_RECEIPT_REQUIRED')
    calls=ledger['calls'];runtime=sum(c['Native_Runtime'] for c in calls);work=sum(c['Native_Work'] or 0 for c in calls)
    charge=incomplete['allocated_native_seconds']
    write(REPORTS/'NATIVE_RUNTIME_LEDGER.json',dict(schema='USER_CANCELLED_BUDGET_QUARANTINE_V1',case_sha=CASE,
        completed_calls=calls,interrupted_call=incomplete,original_ledger_sha256=original_ledger_sha,
        completed_Native_Runtime=runtime,completed_Native_Work=work,interrupted_Runtime=None,interrupted_Work=None,
        conservative_interrupted_budget_charge=charge,consumed_or_reserved_Native_budget=runtime+charge,
        exact_aggregate_Runtime_and_Work_available=False,Native_budget_ceiling=5400,budget_reset=False,
        historical_ledgers_modified=False,all_failed_segment_costs_included=True,new_Native_optimization_performed=False,
        termination='USER_REQUESTED_STOP',interrupted_candidate_not_admitted=True,original_snapshot=str(REPORTS/'artifacts/NATIVE_RUNTIME_LEDGER.json')))
    events=report.csvread(path/'FRONTIER_EVENTS.csv');last=events[-1]
    packet=publish.packet(last['UB_certificate_path']).with_suffix('.npz')
    # The event names RAW_xx_REPLAY.json; use its independently bound point_path.
    ubcert=read(publish.packet(last['UB_certificate_path']))
    raw_source=Path(ubcert['point_path'])
    if not raw_source.is_file():raise ValueError('LAST_PUBLISHED_STRICT_RAW_MISSING')
    best=REPORTS/'artifacts/BEST_STRICT_UB_POINT.npz';shutil.copyfile(raw_source,best)
    dual=read(previous/'BEST_EXACT_ORIGINAL_DUAL.json')
    write(REPORTS/'artifacts/BEST_EXACT_ORIGINAL_DUAL.json',dual)
    # Hard guard: this finalizer must not run Native optimize or presolve.
    import gurobipy as gp
    def forbidden(*a,**k):raise RuntimeError('POST_USER_STOP_NATIVE_FORBIDDEN')
    gp.Model.optimize=forbidden;gp.Model.presolve=forbidden
    start=perf_counter();case=load_case_read_only();build=perf_counter()-start
    start=perf_counter();strict=_strict_ub(case,best,{});strict.update(case_sha=CASE)
    ubwall=perf_counter()-start
    start=perf_counter();lb=check_rational_dual_certificate(case.A,case.d,dual,case_sha=CASE);lbwall=perf_counter()-start
    if not strict['PASS'] or not lb['PASS'] or F(strict['exact_Global_UB'])!=F(last['exact_UB']) or F(lb['exact_bound'])!=F(last['exact_LB']):raise ValueError('CANCELLED_BEST_PAIR_REPLAY_DRIFT')
    write(REPORTS/'BEST_STRICT_UB_REPLAY.json',strict);write(REPORTS/'BEST_EXACT_LB_CERTIFICATE.json',lb)
    for name,digest in read(previous/'EXECUTED_SOURCE_HASHES.json').items():
        if sha(REPORTS/'artifacts/segment01/EXECUTED_SOURCE_ARCHIVE'/Path(name).name)!=digest:raise ValueError('FIRST_SOURCE_ARCHIVE_DRIFT')
    for name,digest in read(path/'EXECUTED_SOURCE_HASHES.json').items():
        if sha(ROOT/name)!=digest:raise ValueError('EXECUTED_CONTINUATION_SOURCE_DRIFT')
    start=perf_counter();preservation=check_protection(read(path/'BASELINE_PROTECTION.json'));protectionwall=perf_counter()-start
    write(REPORTS/'SOURCE_PRESERVATION_AUDIT.json',preservation)
    oldtests=read(OLD/'ZERO_NATIVE_REGRESSION.json');names=sorted({n.split('::')[0] for n in oldtests['passed']+oldtests['skipped']})+['tests/test_v42_m1_anytime.py']
    env=os.environ.copy();env['V42_ANYTIME_TEST_REPORT']=str(REPORTS/'ZERO_NATIVE_REGRESSION.json')
    start=perf_counter()
    with (REPORTS/'FINAL_TESTS.log').open('w',encoding='utf-8') as log:
        tests=subprocess.run(['python','-m','pytest','-q','-p','v42_m1_anytime.pytest_plugin','-o','cache_dir=cache/pytest_anytime','--basetemp='+str(ROOT/'tmp/pytest_anytime_cancelled_final'),*names],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    testwall=perf_counter()-start;receipt=read(REPORTS/'ZERO_NATIVE_REGRESSION.json')
    if tests.returncode or set(oldtests['passed'])-set(receipt['passed']):raise ValueError('649_PASS_NOT_PRESERVED')
    table(REPORTS/'FRONTIER_EVENTS.csv',events)
    cp=report.csvread(path/'FRONTIER_CHECKPOINTS.csv')
    for row in cp:row.update(full_integer_pricing_closure='NOT_PROVEN',P2_certificate='null',actual_timestamp_not_backdated=True)
    table(REPORTS/'FRONTIER_CHECKPOINTS.csv',cp)
    passages=[]
    for threshold in THRESHOLDS:
        crossing=next((e for e in events if 100*F(e['exact_gap'])<=threshold),None)
        passages.append(dict(threshold_percent=float(threshold),status='REACHED' if crossing else 'NOT_REACHED',
            actual_certificate_completion_seconds='' if crossing is None else crossing['actual_certificate_completion_time'],
            wall_minutes='' if crossing is None else float(crossing['actual_certificate_completion_time'])/60,
            candidate_discovery_seconds='' if crossing is None else crossing['retrospectively_validated_candidate_discovery_time'],
            observation_terminated_by_user=True))
    table(REPORTS/'GAP_FIRST_PASSAGE_TIMES.csv',passages)
    scheduler=read(path/'ADAPTIVE_SCHEDULER_AUDIT.json');scheduler.update(user_requested_stop=True,fixed_Gap_stop_used=False)
    write(REPORTS/'ADAPTIVE_SCHEDULER_AUDIT.json',scheduler)
    ubrows=[dict(method=r['method'],ordinal=r['ordinal'],start_UB=r['start_UB'],best_validated_UB=r['best_validated_UB'],delta_UB=r['certified_gain'],Native_Runtime=r['Native_Runtime'],Work=r['Work'],Wall=r['wall_seconds'],validation_failures=r['validation_failures'],radius=r['radius'],lookback=r['lookback_slots']) for r in scheduler['history'] if r['method'].startswith('U')]
    ubrows.append(dict(method='U4',ordinal=2,start_UB=float(F(last['exact_UB'])),best_validated_UB=float(F(last['exact_UB'])),delta_UB=0,Native_Runtime='NOT_AVAILABLE_USER_INTERRUPTED',Work='NOT_AVAILABLE_USER_INTERRUPTED',Wall='INTERRUPTED',validation_failures='NOT_REPLAYED',radius=144,lookback=16))
    table(REPORTS/'UB_NEIGHBORHOOD_PORTFOLIO.csv',ubrows)
    lbrows=[dict(method=r['method'],candidate_LB=r.get('candidate_LB'),adopted=r.get('adopted'),delta_LB=r['certified_gain'],Wall=r['wall_seconds'],Native_Runtime=r.get('Native_Runtime'),integer_closure='NOT_PROVEN') for r in scheduler['history'] if r['method'].startswith('L')]
    table(REPORTS/'LB_PRICING_CERTIFICATION.csv',lbrows)
    identity=read(path/'SCIENTIFIC_CASE_IDENTITY.json');identity.update(linked_run_ids=[previous.name,RUN],user_requested_stop=True,original_T0_UTC=read(path/'T0_CLOCK.json')['UTC'],baseline_validation_before_original_T0_seconds=read(previous/'SCIENTIFIC_CASE_IDENTITY.json')['baseline_validation_wall_before_T0_seconds'])
    write(REPORTS/'SCIENTIFIC_CASE_IDENTITY.json',identity)
    gap=(F(last['exact_UB'])-F(last['exact_LB']))/abs(F(last['exact_UB']))
    final=dict(PASS=True,status='USER_CANCELLED_PARTIAL_FRONTIER_INDEPENDENTLY_VERIFIED',case_sha=CASE,run_id=RUN,completed_baseline_HEAD=BASE,
        full_75_minute_frontier_completed=False,fixed_Gap_stop_used=False,user_cancelled=True,
        exact_Global_LB=last['exact_LB'],exact_Global_UB=last['exact_UB'],exact_gap=str(gap),certified_gap_percent=float(100*gap),
        completed_Native_Runtime=runtime,completed_Work=work,interrupted_Runtime_and_Work=None,
        conservative_Native_budget_charged=runtime+charge,Wall_to_post_stop_verification_seconds=perf_counter()-t0,
        post_stop_Native_optimize_calls=0,strict_UB=strict,exact_LB=lb,
        tests=dict(passed=len(receipt['passed']),skipped=len(receipt['skipped']),failed=len(receipt['failed'])),historical_649_PASS_preserved=True,
        full_integer_pricing_closure='NOT_PROVEN',M1_ACCEPTED=False,P2_certificate=None,production_promoted=False,
        unfinished_RAW_not_selected=True,terminated_before_30_40_60_75_checkpoints=True)
    write(REPORTS/'INDEPENDENT_FINAL_VERIFICATION.json',final)
    write(REPORTS/'RUNTIME_BREAKDOWN.json',dict(case_sha=CASE,completed_Native_Runtime=runtime,completed_Work=work,
        interrupted_Runtime=None,interrupted_Work=None,conservative_Native_budget_charge=runtime+charge,
        frozen_case_load_wall=build,post_stop_strict_replay_wall=ubwall,post_stop_exact_LB_checker_wall=lbwall,
        post_stop_source_protection_wall=protectionwall,post_stop_regression_wall=testwall,
        original_T0_to_verification_wall=final['Wall_to_post_stop_verification_seconds'],post_stop_wall=perf_counter()-stopped,
        historical_Runtime_or_Wall_not_added=True,original_costs=ledger['costs'],overlapping_costs_do_not_sum=True))
    write(REPORTS/'UNOBSERVED_CHECKPOINTS.json',dict(target_minutes=[30,40,60,75],reason='USER_REQUESTED_STOP',not_extrapolated=True))
    audit=publish.timeline();write(REPORTS/'INDEPENDENT_TIMELINE_AND_BUDGET_AUDIT.json',audit)
    sys.path.insert(0,str(ROOT/'cache/plotting_py311'));points=report.verify_events(path)
    report.plots(points,stopped-t0)
    text=f"""# V42 M1 Anytime 연구 — 사용자 요청 중단 및 PR 마감

사용자 지시에 따라 진행 중인 신규 Anytime 실행만 중단했다. 75분 Frontier는 완료하지 않았다. 기존 실험·production·다른 프로세스는 변경하거나 중단하지 않았다.

동일 May01 / 1499 jobs / 4 MESS / 24 sites / 96 slots, Case SHA `{CASE}`, baseline `{BASE}`에서 시작한 warm-start 후속 연구다.

- 시작 Gap 4.4289785520% → 최종 독립 검증 Gap **{final['certified_gap_percent']:.10f}%**.
- Strict integer UB **{float(F(last['exact_UB'])):.16f}**, 감소 {float(F(identity['warm_start_exact_UB'])-F(last['exact_UB'])):.16f}.
- Exact Global LB **{float(F(last['exact_LB'])):.16f}**, 증가 0. UB의 개선이며 LB strengthening 성공으로 주장하지 않는다.
- 4% / 3.5% 최초 인증: 1.109088분. 3% 최초 인증: 24.876206분. 인증 완료 시각 기준이며 callback 발견으로 소급하지 않았다.
- 완료 26회 Native Runtime **{runtime:.3f}초**, Work **{work:.6f}**. 중단된 27번째 호출의 정확한 Runtime/Work는 미확보다. 해당 호출의 배정 300초를 보수적으로 소비 예산에 포함하여 **{runtime+charge:.3f}초**를 계상했다. 이는 정확한 총 Runtime으로 주장하지 않는다.
- 10분 목표는 실제 11.3524분 관측, 20분은 실제 20.0001분 관측이다. 30/40/60/75분은 사용자 중단으로 NOT_OBSERVED. 2.5/2/1.5/1/0.5%는 NOT_REACHED이며 불가능성 증명이 아니다.
- 회귀 **{len(receipt['passed'])} PASS / {len(receipt['skipped'])} SKIP / {len(receipt['failed'])} FAIL**; 기존649 PASS를 보존했고 SKIP은 PASS로 세지 않았다. 마감 검증 Native optimize=0.
- 마지막 공개·검증된 RAW만 새로 C3A/FULL 전체 binary literal0/1·전체 matrix·Route/SOC/PQ/PCS/grid에서 replay했다. 중단 호출의 더 낮은 잠정 후보는 채택하지 않았다.

## 연구 결과와 한계

U4 충·방전 시간·SOC 연결을 활용한 neighborhood가 인증 UB 개선을 만들었다. 반경·시간창은 사전등록 값에서 바꾸고 모든 원본 행을 보존했다. 최신 궤적의 RMP feedback은 실행했지만 해당 L2 가격의 candidate LB는 기존 최고값보다 낮았다. L3 rational dual mixing도 LB를 높이지 못했다. L4 정수 Pricing은 exact integer closure=NOT_PROVEN이다. 제한 RMP 목적값과 Native BestBd를 Global LB로 쓰지 않았다.

첫 실행의 RMP ledger `track` 인수 호환성 오류는 source archive·실패 receipt와 함께 보존했다. 새 연속 구간은 최초 T0와 모든 완료·실패 비용을 승계했다. 사용자 중단까지 오류 복구 비용을 포함한 동일 Wall을 유지했고 예산을 재설정하지 않았다. 현재 연구는 75분 비교, 40/60분 실용성 또는 75~90분 추가 탐색의 이득을 판단하지 못한다. 이전 C와 동등한 새 대조군도 없으므로 일반적 우월성을 주장하지 않는다. 3% warm-start 최초 인증은 이 May01 사례의 성과이며 May12/A2/M2로 전용하지 않는다.

P2=null, M1_ACCEPTED=false, production 기본 backend와 historical input/ledger는 보존한다. 원래 A186/M188/C3A162와 공통 물리 authority를 변경하지 않았다. 모든 개발·임시·cache·검증·commit 경로는 D:\MobileESS_v42다. C 데이터·repo는 읽기 전용이다.

CSV·SVG는 실제 인증 완료 시각만 사용한다. 미관측 future checkpoints를 채우지 않았다. 독립 최종 검증 Wall과 모델 생성·pricing·replay·exact checker·회귀는 RUNTIME_BREAKDOWN.json에 별도로 기록했다. 과거20.109분·549.057초는 신규 시간에 더하지 않았다.
"""
    (REPORTS/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (REPORTS/'ANYTIME_HANDOFF_KO.md').write_text('사용자 요청으로 중단된 partial Frontier다. 기존 Native를 재시작하거나 ledger를 reset하지 않는다. 후속 연구는 새 인간 요청·새 Run ID·원래 소비/보수 계상 비용 감사 아래 별도로 사전등록해야 한다. best strict RAW 및 exact dual은 artifacts에 있고 동일 Case SHA에서 독립 replay해야 한다. 미완료 후보·가격 closure·P2·다른 날짜 성능은 승계하지 않는다. PR189에 검증된 이번 연구 코드와 증거를 보존한다.\n',encoding='utf-8')
    report.manifest()
    print('USER_CANCELLED_FINAL_VERIFICATION_PASS',final['certified_gap_percent'],final['tests'])

if __name__=='__main__':finalize()
