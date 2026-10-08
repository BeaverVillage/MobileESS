"""Post-experiment publication of actual certified steps, not callbacks."""
from datetime import datetime,timezone
from fractions import Fraction as F
from pathlib import Path
import csv
import os
import shutil
import numpy as np
from v42_unified.storage import sha
from .core import ROOT,BASE,CASE,REPORTS,write,read,table,TARGETS

def csvread(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def verify_events(path):
    rows=csvread(path/'FRONTIER_EVENTS.csv');last_lb=None;last_ub=None;last_time=-1;checked=[]
    for row in rows:
        lb,ub=F(row['exact_LB']),F(row['exact_UB']);t=float(row['actual_certificate_completion_time'])
        if row['case_sha']!=CASE or not 0<=lb<=ub or F(row['exact_gap'])!=(ub-lb)/abs(ub):raise ValueError('FRONTIER_EXACT_CASE_OR_GAP_DRIFT')
        if t<last_time or last_lb is not None and (lb<last_lb or ub>last_ub):raise ValueError('FRONTIER_MONOTONICITY_DRIFT')
        for kind in ('LB','UB'):
            packet=Path(row[kind+'_certificate_path'])
            if sha(packet)!=row[kind+'_certificate_sha256']:raise ValueError('FRONTIER_CERTIFICATE_PACKET_DRIFT')
        if float(row['wall_seconds'])+1e-6<t:raise ValueError('CERTIFICATE_COMPLETION_BACKDATED')
        checked.append(dict(time=t,lb=float(lb),ub=float(ub),gap=float(100*(ub-lb)/abs(ub))))
        last_lb,last_ub,last_time=lb,ub,t
    return checked

def package(path):
    verify=read(path/'INDEPENDENT_FINAL_VERIFICATION.json')
    if not verify['PASS'] or not verify['final_90_minutes_PASS'] or not verify['Native_75_minutes_PASS']:
        raise ValueError('COMPLETED_SAME_CASE_WITHIN_PREREGISTERED_LIMITS_REQUIRED')
    points=verify_events(path)
    ledger=read(path/'NATIVE_RUNTIME_LEDGER.json');scheduler=read(path/'ADAPTIVE_SCHEDULER_AUDIT.json')
    if ledger['inflight'] is not None or any(c['runtime_unavailable'] for c in ledger['calls']):raise ValueError('COMPLETE_NATIVE_LEDGER_REQUIRED')
    runtime=sum(c['Native_Runtime'] for c in ledger['calls']);work=sum(c['Native_Work'] or 0 for c in ledger['calls'])
    if runtime!=ledger['Native_Runtime_sum'] or work!=ledger['Native_Work_sum'] or runtime>5400:raise ValueError('NATIVE_ACCOUNTING_MISMATCH')
    REPORTS.mkdir(parents=True,exist_ok=True);destination=REPORTS/'artifacts';destination.mkdir(exist_ok=True)
    for source in path.rglob('*'):
        if source.is_file():
            target=destination/source.relative_to(path);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            if sha(source)!=sha(target):raise ValueError('ARTIFACT_BYTE_COPY_DRIFT')
    required=('SCIENTIFIC_CASE_IDENTITY.json','FRONTIER_EVENTS.csv','FRONTIER_CHECKPOINTS.csv','GAP_FIRST_PASSAGE_TIMES.csv',
        'BEST_STRICT_UB_REPLAY.json','BEST_EXACT_LB_CERTIFICATE.json','ADAPTIVE_SCHEDULER_AUDIT.json',
        'NATIVE_RUNTIME_LEDGER.json','INDEPENDENT_FINAL_VERIFICATION.json')
    for name in required:shutil.copyfile(path/name,REPORTS/name)
    # Certification status was unchanged throughout: no P2 or exact integer
    # price-closure certificate is retroactively inserted into a checkpoint.
    checkpoints=csvread(REPORTS/'FRONTIER_CHECKPOINTS.csv')
    for row in checkpoints:row['full_integer_pricing_closure']='NOT_PROVEN';row['P2_certificate']='NOT_RUN'
    present={str(row['target_wall_seconds']) for row in checkpoints}
    missing=[t for t in TARGETS if str(t) not in present]
    if missing:write(REPORTS/'UNOBSERVED_CHECKPOINTS.json',dict(targets=missing,reason=verify['termination'],not_padded_as_measurements=True))
    table(REPORTS/'FRONTIER_CHECKPOINTS.csv',checkpoints)
    ubrows=[];lbrows=[]
    for row in scheduler['history']:
        if row['method'].startswith('U'):
            ubrows.append(dict(method=row['method'],ordinal=row['ordinal'],start_UB=row['start_UB'],best_validated_UB=row['best_validated_UB'],
                delta_UB=row['certified_gain'],Native_Runtime=row['Native_Runtime'],Work=row['Work'],Wall=row['wall_seconds'],
                strict_integer_candidates=row['strict_candidates'],failed_validations=row['validation_failures'],radius=row['radius'],lookback=row['lookback_slots'],
                improvement_per_Wall_second=row['certified_gain']/row['wall_seconds'],Native_restricted_bound_is_Global_LB=False))
        else:lbrows.append(dict(method=row['method'],start_LB=row.get('start_LB'),candidate_LB=row.get('candidate_LB'),best_LB=row.get('certified_LB'),
            adopted=row.get('adopted'),delta_certified_LB=row['certified_gain'],Wall=row['wall_seconds'],Native_Runtime=row.get('Native_Runtime'),
            weight=row.get('dual_stabilization_weight'),certificate=row.get('certificate'),status=row.get('status','EXACT_DUAL_REPLAYED'),integer_closure='NOT_PROVEN'))
    table(REPORTS/'UB_NEIGHBORHOOD_PORTFOLIO.csv',ubrows)
    table(REPORTS/'LB_PRICING_CERTIFICATION.csv',lbrows)
    identity=read(path/'SCIENTIFIC_CASE_IDENTITY.json')
    write(REPORTS/'RUNTIME_BREAKDOWN.json',dict(PASS=True,case_sha=CASE,run_id=verify['run_id'],Native_Runtime=runtime,Native_Work=work,
        Native_wall_finished_seconds=verify['Native_finished_wall_seconds'],Wall_from_verified_T0_seconds=verify['monotonic_wall_seconds'],
        baseline_validation_before_T0_seconds=identity['baseline_validation_wall_before_T0_seconds'],
        including_new_baseline_validation_seconds=identity['baseline_validation_wall_before_T0_seconds']+verify['monotonic_wall_seconds'],
        old_20p109_minutes_not_added=True,old_549p057_Native_seconds_not_added=True,costs=ledger['costs'],calls=ledger['calls'],
        costs_can_overlap_do_not_sum=True,presolve_in_Native=True,process_CPU_and_RSS_samples_in_calls=True))
    write(REPORTS/'FRONTIER_INDEPENDENT_EVENT_AUDIT.json',dict(PASS=True,case_sha=CASE,verified_events=len(points),
        mathematical_gap_recomputed=True,all_certificate_file_hashes_reverified=True,discovery_time_not_used_as_first_passage=True))
    plots(points,verify['monotonic_wall_seconds'])
    korean(verify,identity,scheduler,checkpoints,csvread(path/'GAP_FIRST_PASSAGE_TIMES.csv'))
    manifest()
    return verify

def plots(points,end):
    os.environ['MPLCONFIGDIR']=str(ROOT/'cache/matplotlib_anytime')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none','font.size':10})
    points=points+[dict(points[-1],time=end)];x=[p['time']/60 for p in points]
    for name,fields,ylabel in [('GAP_VS_WALL_TIME.svg',('gap',),'Certified Global Gap (%)'),('LB_UB_VS_TIME.svg',('lb','ub'),'Original objective rho_max')]:
        fig,ax=plt.subplots(figsize=(9,4.5))
        for f in fields:ax.step(x,[p[f] for p in points],where='post',label={'gap':'Certified gap','lb':'Exact Global LB','ub':'Strict integer UB'}[f],linewidth=1.8)
        ax.set(xlabel='Actual Wall Time since verified warm start (minutes)',ylabel=ylabel,xlim=(0,max(x)))
        ax.set_title('May01 / 1,499 jobs / 4 MESS / 96 slots — certified completion times')
        ax.grid(alpha=.25);ax.legend();fig.tight_layout();fig.savefig(REPORTS/name);plt.close(fig)

def korean(v,identity,scheduler,checkpoints,passages):
    checkpoint_lines=[]
    for target in (0,600,1200,1800,2400,3600,4500):
        row=next((r for r in checkpoints if r['target_wall_seconds']==str(target)),None)
        checkpoint_lines.append(f"| {target/60:g} | {'NOT_OBSERVED' if row is None else format(float(row['certified_gap_percent']),'.10f')} | {'—' if row is None else format(float(row['actual_snapshot_wall_seconds'])/60,'.4f')} |")
    checkpoint_lines.append(f"| 최종 검증 | {v['certified_gap_percent']:.10f} | {v['monotonic_wall_seconds']/60:.4f} |")
    threshold_lines=[f"| {r['threshold_percent']}% | {r['status']} | {r['wall_minutes'] or '—'} |" for r in passages]
    stats={}
    for method in ('U1','U2','U3','U4','L1','L2','L3','L4'):
        rows=[r for r in scheduler['history'] if r['method']==method]
        stats[method]=dict(calls=len(rows),gain=sum(r['certified_gain'] for r in rows),wall=sum(r['wall_seconds'] for r in rows))
    best=max(('U1','U2','U3','U4'),key=lambda k:stats[k]['gain']/max(stats[k]['wall'],1e-9))
    baseline_lb=F(identity['warm_start_exact_LB']);baseline_ub=F(identity['warm_start_exact_UB'])
    text=f'''# V42 M1 Anytime Global Gap–Runtime Frontier 결과

동일 May01/1,499-job에서 **이미 인증된 4.4289785520%**를 시작값으로 삼은 warm-start 후속 연구다. 신규 종료 조건으로 3% 또는 5%를 지정하지 않았다. 시작 이후의 최종 인증 Gap은 **{v['certified_gap_percent']:.10f}%**이며 Native window와 최종 검증 한계를 지켰다. P2는 null이고 **M1_ACCEPTED=false**다.

## 실제 Wall 체크포인트

| 목표 분 | 당시 인증 Gap % | 실제 snapshot 분 |
|---:|---:|---:|
{chr(10).join(checkpoint_lines)}

다음은 Solver 발견 시각이 아니라 **독립 인증 완료 시각**의 최초 통과 기록이다. 미도달 값은 소급·추정하지 않았다.

| 임계 Gap | 상태 | 최초 인증 분 |
|---:|---|---:|
{chr(10).join(threshold_lines)}

## 최종 독립 결과와 시간

- Strict integer UB: **{float(F(v['exact_Global_UB'])):.16f}**, T0 이후 감소 {float(baseline_ub-F(v['exact_Global_UB'])):.16f}.
- Exact Global LB: **{float(F(v['exact_Global_LB'])):.16f}**, T0 이후 증가 {float(F(v['exact_Global_LB'])-baseline_lb):.16f}.
- Global Gap: **{v['certified_gap_percent']:.10f}%**.
- 신규 Native Runtime **{v['Native_Runtime']:.3f}초**, Work **{v['Work']:.6f}**.
- 검증된 T0부터 최종 검증 Wall **{v['monotonic_wall_seconds']/60:.4f}분**; 신규 시작값 검증 {identity['baseline_validation_wall_before_T0_seconds']:.3f}초는 별도 기록했다. 이를 포함한 신규 실험 비용은 {(identity['baseline_validation_wall_before_T0_seconds']+v['monotonic_wall_seconds'])/60:.4f}분이다. 과거 20.109분과 Native549.057초는 더하지 않았다.
- 마지막 Native task 완료 **{v['Native_finished_wall_seconds']/60:.4f}분**, 최종 90분 PASS **{v['final_90_minutes_PASS']}**, Native75분 PASS **{v['Native_75_minutes_PASS']}**.
- 회귀 **{v['tests']['passed']} PASS / {v['tests']['skipped']} SKIP / {v['tests']['failed']} FAIL**, 기존649 PASS 유지, 테스트 Native=0. SKIP은 PASS로 세지 않았다.

## UB와 LB 성과 구분

가장 큰 인증 UB 개선/Wall 효율을 낸 방법은 **{best}**였다. 방법별 호출·검증 실패·gain·Wall·반경·시간창은 [portfolio](UB_NEIGHBORHOOD_PORTFOLIO.csv)에 있다. 모든 모델은 이전 strict best를 중심으로 생성했고, 사전등록한 반경·시간창·역할 대상을 단계 경계에서 바꿨다. 원본 모든 Grid/Route/SOC/PQ/PCS 행과 continuous box를 유지했으며 neighborhood는 UB 탐색에만 썼다. 현재 warm-start는 이전 C의 결과이므로 이전 C에서 **추가 UB 개선이 있었는지**와 이번 효율을 구분한다. 동등한 시작해·예산의 새로운 C 대조군은 실행하지 않았으므로 일반적 알고리즘 우월성은 입증하지 않는다.

{chr(10).join(f"- {k}: {s['calls']}회, 인증 gain {s['gain']:.14f}, 실제 task Wall {s['wall']:.3f}초." for k,s in stats.items())}

L1은 기존 original-row 가격에서 full96 local LP dual을 재최적화했다. L2는 **최신 strict UB의 4개 trajectory**를 original local/FULL physics·literal gate로 검사하여 RMP catalog에 포함했다. L3는 exact rational convex mixing으로 가격을 안정화한 뒤 전체 CSR에서 검증했다. 강한 인증 LB만 보존했으며 RMP 목적값·Native BestBd는 Global LB가 아니다. 방법별 실제 후보 LB와 adoption은 [LB 인증 표](LB_PRICING_CERTIFICATION.csv)에 있다. L4는 완전 full96 MILP 가격을 평가했으나 Native OPTIMAL 및 ObjBound만으로 exact integer optimum이나 전체 missing-column closure를 증명하지 않았다. **Full integer Pricing closure=NOT_PROVEN**이다. Integer price RAW의 exact priced objective와 LP certificate 차이는 별도 artifact에 남겼으며 hard rational primal rows 또는 완전 branch proof가 없다면 인증하지 않는다.

## 수렴 해석과 논문 기준

40분과 60분 결과는 위 실제 checkpoint 값이다. 75분까지 추가 탐색의 이득은 60분 snapshot 대비 마지막 인증 UB/LB/Gap 차이로 판단한다. **90분 전체를 Native로 계산하지 않았다**. 75분에 Native를 끝내고 최종 독립 검증을 수행했으므로 75~90분 추가 Native의 반사실적 효과는 측정하지 않았다. 정체 구간에서는 최근 인증 gain/Wall과 무개선 횟수로 후보를 바꿨다. 작은 LP 재최적화 효과, 제한 catalog의 가격 한계, 정수 가격 closure 미인증과 물리적 전역 infeasibility를 구분한다. no incumbent·TIME_LIMIT·음수 reduced-cost lower bound 자체는 불가능성 증명이 아니다. 단일 사례의 곡선이 논문의 보편적 M1/M2 3% 또는5% 기준을 확정하지 않는다. 실제 첫 통과시간과 미도달·비용을 근거로 May01의 적용 가능성과 tradeoff만 논의하며 M2 일반화는 별도 입력 검증이 필요하다.

## 데이터·증거·재현

Case SHA `{CASE}`, 완료 baseline HEAD `{BASE}`, Run ID `{v['run_id']}`. 4 MESS/24sites/96slots와 `min rho_max`, A1 anchor, DATA/Route/Battery/Grid/원본 C3A/FULL 및 tolerances를 보존했다. 모두 `D:\\MobileESS_v42`에서 개발·실행했고 C repository/data는 읽기 전용으로 취급했다. historical ledger와 production backend를 변경하지 않았다. May12/A2/M2/May B1/Actual/Fresh AC로 전용하거나 자동 실행하지 않았다.

타임스탬프는 monotonic T0와 UTC를 기록했다. callback 점의 발견과 나중의 실제 인증 완료시간은 [events](FRONTIER_EVENTS.csv)에 각각 있다. 인증된 계단 곡선은 [Gap–Wall SVG](GAP_VS_WALL_TIME.svg), [LB/UB–Wall SVG](LB_UB_VS_TIME.svg)이며 잠정 callback 또는 제한 native bound를 포함하지 않는다. 진행 중 Native Runtime은 완료 호출의 실제 Runtime에 마지막 **실제 callback sample**을 더해 표시하며 sample age도 저장했다. extrapolation이나 회귀 소급은 없다. 모델 생성·pricing·RMP·전체 replay·exact certificate·검증·I/O와 CPU/RSS, Work는 [runtime](RUNTIME_BREAKDOWN.json) 및 [ledger](NATIVE_RUNTIME_LEDGER.json)에 분리돼 있다. 중첩 비용을 합산하지 않는다. No MemLimit/SoftMemLimit/메모리 자동 종료, Threads=1이며 각 모델은 등록된 TimeLimit 또는 자연 종료를 따랐다.
'''
    (REPORTS/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')

def manifest():
    files={}
    for folder in (REPORTS,ROOT/'v42_m1_anytime'):
        for p in folder.rglob('*'):
            if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in p.parts:files[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ('tests/test_v42_m1_anytime.py','Start-V42-M1-Anytime.ps1'):files[name]=sha(ROOT/name)
    write(REPORTS/'SHA256_MANIFEST.json',dict(PASS=True,case_sha=CASE,completed_baseline_HEAD=BASE,files=files,self_hash_excluded=True))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);args=p.parse_args()
    from .core import RUNTIME
    v=package(RUNTIME/args.run_id);print('ANYTIME_FRONTIER_PACKAGED',v['certified_gap_percent'])
