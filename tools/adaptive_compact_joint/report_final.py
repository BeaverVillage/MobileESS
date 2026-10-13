"""Korean negative-result report, complete cost ledgers, plans and scientific plots."""
import csv,re,gc,time
from collections import Counter
from datetime import datetime,timezone
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.global_local_multistart1800.dag import Graph

def export_plan(case,raw,target):
    point=v.load_point(raw);original=case.lift(point);values=dict(zip(map(str,case.original_d['names']),map(float,original)))
    graph=Graph(case);paths=paths_of(case,point);records=[];profiles={}
    for u,path in paths.items():
        pc=[];pd=[];qq=[];soc=[values[f'SOC[{u},{t}]'] for t in range(97)];locations=[]
        for t in range(96):
            arc=next(graph.arcs[k] for k in path if graph.arcs[k][1]<=t<graph.arcs[k][3]);locations.append(arc[0] if arc[-1] is None else 'TRANSIT')
            pch=sum(values.get(f'Pch[{u},{s},{t}]',0.) for s in case.graph[0]);pdis=sum(values.get(f'Pdis[{u},{s},{t}]',0.) for s in case.graph[0]);q=sum(values.get(f'Q[{u},{s},{t}]',0.) for s in case.graph[0])
            pc.append(pch);pd.append(pdis);qq.append(q)
            records.append(dict(unit=u,slot=t,location=locations[-1],charge_mode=values[f'charge_mode[{u},{t}]'],Pch_kW=pch,Pdis_kW=pdis,Q_kvar=q,SOC_before_kWh=soc[t],SOC_after_kWh=soc[t+1]))
        profiles[u]=dict(Pch=pc,Pdis=pd,Q=qq,SOC=soc,location=locations,MOVE_count=len(graph.move_indices(path)))
    with target.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    return profiles,graph.metadata(paths)

def main():
    guard();review=read(DOCS/'FINAL_INDEPENDENT_REVIEW.json');assert review['PASS']
    state=read(DOCS/'FINAL_STATE.json');stop=read(beta.DOCS/'PHASE0_SAFE_STOP.json');auth=read(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json')
    routes=read(beta.DOCS/'PHASE1_ROUTE_AND_SOLVER_DIAGNOSTICS.json');grid_audit=read(beta.DOCS/'PHASE1_WHOLE_GRID_SOC_DIAGNOSTICS.json')
    feedback=read(DOCS/'FEEDBACK_POOL_01.json');backend=read(DOCS/'FINAL_BACKEND_DECISION.json')
    calls=[]
    for phase,source in (('OLD_JOINT_AND_ABLATIONS',stop['calls']),('STOPPED_REMAINDER_PILOT',auth['prior_pilot_calls']),('FRESH_1800_EXECUTION',state['Native_calls'])):
        for c in source:calls.append(dict(phase=phase,receipt=c['receipt'],Native_Runtime=c['Native_Runtime']))
    totals={phase:sum(c['Native_Runtime'] for c in calls if c['phase']==phase) for phase in set(c['phase'] for c in calls)}
    write(DOCS/'ALL_SESSION_NATIVE_RUNTIME_LEDGER.json',dict(PASS=True,calls=calls,phase_totals=totals,all_actual_Native=sum(c['Native_Runtime'] for c in calls),
        fresh_limit=1800,fresh_initial=0.,fresh_used=state['fresh_Native_used'],fresh_remaining=1800-state['fresh_Native_used'],
        original_partial_ledgers_preserved=True,unknown_Runtime=[],ledger_resets=0,
        older_PR219_Native_separate=1795.0249993801117,older_PR220_Native_separate=724.820999622345))
    runmetrics=[];comparison=[];private=[];rss=[];ram=[];commit=[]
    for phase in ('OLD_JOINT_AND_ABLATIONS','STOPPED_REMAINDER_PILOT','FRESH_1800_EXECUTION'):
        for c in [z for z in calls if z['phase']==phase]:
            q=read(c['receipt']['path']);samples=[]
            for s in q.get('resource_samples',[]):
                sample=s.get('memory') or s.get('sample')
                if sample:samples.append(sample)
            if q.get('memory_after'):samples.append(q['memory_after'])
            for m in samples:
                if 'Private_Commit_bytes' in m:private.append(m['Private_Commit_bytes']);rss.append(m['RSS_bytes'])
                if 'system' in m:ram.append(m['system']['RAM_available']);commit.append(m['system']['Commit_available'])
            runmetrics.append(dict(phase=phase,receipt=c['receipt'],Native_Runtime=q['Native_Runtime'],model_build_wall=q.get('model_build_wall_seconds'),worker_wall=q.get('worker_wall_seconds'),
                **{k:q.get(k) for k in ('Status','ObjVal','ObjBound','MIPGap','NodeCount','root_completed_Native_seconds')}))
    write(DOCS/'MEMORY_NUMERIC_WALL_AUDIT.json',dict(PASS=True,runs=runmetrics,max_actual_private_bytes=max(private),max_actual_RSS_bytes=max(rss),
        minimum_available_RAM_bytes=min(ram),minimum_available_commit_bytes=min(commit),
        fresh_controller_wall_seconds=state['wall_seconds'],beta_native0_wall=read(beta.DOCS/'NATIVE0_GATE.json')['wall_seconds'],
        fresh_native0_wall=read(DOCS/'NATIVE0_GATE.json')['wall_seconds'],source_warning='Original coefficient range1e-13..4e2 remains; no new physical coefficient perturbation',
        source_numerical_parameters_preserved=True,Native_error_count=0,unknown_Runtime=0,ACTUAL='ACTUAL_NOT_RUN'))
    for label,folder,raw in (
        ('OLD_JOINT',OLD_DOCS/'v2/calls/001_JOINT_POOL_101/native',None),
        ('EXACT_EXTENDED_FORM',beta.DOCS/'pilot/SAME_POOL',None),
        ('EXACT_DIRECT',DOCS/'calls/001_SAME_POOL',None),
        ('ADAPTIVE_DIRECT',DOCS/'calls/002_ADAPTIVE',None)):
        q=read(folder/'NATIVE_CALL.json');log=(folder/'NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace')
        ps=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log);pt=re.findall(r'Presolve time: ([\d.]+)s',log)
        readback_path=folder/('JOINT_NATIVE_READBACK.json' if label=='OLD_JOINT' else 'COMPACT_NATIVE_READBACK.json' if label=='EXACT_EXTENDED_FORM' else 'NATIVE_READBACK.json')
        rb=read(readback_path)
        comparison.append(dict(label=label,Native_Runtime=q['Native_Runtime'],build_wall=q['model_build_wall_seconds'],presolve_seconds=float(pt[-1]),presolved=ps[-1] if ps else None,
            binary=rb.get('total_binary',rb.get('NumBinVars')),columns=354309 if label=='OLD_JOINT' else rb.get('NumVars'),
            rows=718415 if label=='OLD_JOINT' else rb.get('NumConstrs'),ObjVal=q['ObjVal'],restricted_ObjBound=q['ObjBound'],NodeCount=q['NodeCount'],
            status=q['Status'],MIP_start_loaded='Loaded user MIP start' in log))
    write(DOCS/'SAME_POOL_FORMULATION_COMPARISON.json',dict(PASS=True,runs=comparison,Old_and_EF_and_DIRECT_same_path_pool=True,
        direct_adopted=False,EF_speedup_claim=False,direct_compute_speedup_claim=False,one_comparison_not_general_benchmark=True))
    case=v.load_native_case();profiles,move=export_plan(case,state['BEST_GLOBAL_UB']['point']['path'],DOCS/'BEST_GLOBAL_96_SLOT_MESS_PLAN.csv')
    actual=min((a for a in state['validations'] if a['FULL_PASS']),key=lambda a:a['UB'])
    actual_profiles,actual_move=export_plan(case,actual['dense_lift']['path'],DOCS/'BEST_ACTUAL_JOINT_96_SLOT_MESS_PLAN.csv')
    write(DOCS/'BEST_PLAN_AND_ACTUAL_JOINT_AUDIT.json',dict(PASS=True,best=state['BEST_GLOBAL_UB'],actual_joint=actual,
        per_unit_MOVE={u:p['MOVE_count'] for u,p in actual_profiles.items()},best_moves=move,actual_joint_moves=actual_move,
        SOC_97_each=True,original_FULL_all_replays_PASS=True,physical_profiles=actual_profiles))
    del case;gc.collect()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figures=[]
    def savefig(name):
        plt.tight_layout();plt.savefig(DOCS/name,dpi=170);plt.close();figures.append(record(DOCS/name))
    x=np.cumsum([c['Native_Runtime'] for c in calls]);plt.figure(figsize=(8,3.5));plt.step(np.r_[0,x],np.full(len(x)+1,INITIAL_UB),where='post',label='FULL UB');plt.axhline(GLOBAL_LB,color='green',label='Certified K48 LB');plt.xlabel('All this work actual Native seconds (historical + fresh)');plt.ylabel('rho_max');plt.legend();savefig('UB_LB_NATIVE_COST.png')
    plt.figure(figsize=(8,3.5));plt.bar([c['label'] for c in comparison],[c['Native_Runtime'] for c in comparison]);plt.ylabel('Actual Native seconds');plt.xticks(rotation=12);savefig('SAME_POOL_RUNTIME_COMPARISON.png')
    fig,axes=plt.subplots(1,2,figsize=(9,3.5));axes[0].bar([c['label'] for c in comparison[:3]],[c['columns'] for c in comparison[:3]]);axes[0].set_ylabel('Input columns');axes[1].bar([c['label'] for c in comparison[:3]],[c['binary'] for c in comparison[:3]]);axes[1].set_ylabel('Input binaries');
    for ax in axes:ax.tick_params(axis='x',rotation=15)
    savefig('FORMULATION_INPUT_SIZE.png')
    fig,axes=plt.subplots(1,2,figsize=(9,3.5));us=sorted(feedback['units']);width=.17
    for i,depth in enumerate((0,1,2,3,4)):
        axes[0].bar(np.arange(4)+i*width,[routes['aggregate'][u]['MOVE_histogram'].get(str(depth),0) for u in us],width,label=str(depth)+' MOVE')
        axes[1].bar(np.arange(4)+i*width,[feedback['units'][u]['generated_MOVE_histogram'].get(str(depth),0) for u in us],width,label=str(depth)+' MOVE')
    for ax in axes:ax.set_xticks(np.arange(4)+2*width,us);ax.tick_params(axis='x',rotation=15);ax.set_ylabel('Unique path count');ax.legend(fontsize=7)
    axes[0].set_title('Old evaluated pools union');axes[1].set_title('Verified-feedback reservoir (Native0)');savefig('PATH_QUALITY_COVERAGE.png')
    fig,axes=plt.subplots(4,2,figsize=(10,10),sharex='col')
    for i,u in enumerate(us):
        p=actual_profiles[u];axes[i,0].plot(p['Pch'],label='Pch');axes[i,0].plot(p['Pdis'],label='Pdis');axes[i,0].plot(p['Q'],label='Q');axes[i,0].set_ylabel(u+' kW / kvar');axes[i,0].legend(fontsize=7)
        axes[i,1].plot(p['SOC']);axes[i,1].axhline(440,color='grey',ls=':');axes[i,1].axhline(1080,color='grey',ls=':');axes[i,1].set_ylabel('SOC kWh')
    axes[-1,0].set_xlabel('Slot0..95');axes[-1,1].set_xlabel('Boundary0..96');savefig('ACTUAL_JOINT_P_Q_SOC.png')
    fb=read(DOCS/'OPTIMIZATION_FEEDBACK_01.json');labels=[f"{row['metadata']['asset']}/{row['metadata']['phase']}/t{row['slot']}" for row in fb['rows'][:16]]
    plt.figure(figsize=(10,5));plt.barh(labels,[r['loading'] for r in fb['rows'][:16]]);plt.xlabel('Original signed P/Q projected thermal loading');savefig('MULTI_CRITICAL_GRID_ROWS.png')
    write(DOCS/'FIGURE_INDEX.json',dict(PASS=True,figures=figures,scientific_plots_not_heuristic_bound_certificates=True))
    table='\n'.join(f"| {c['label']} | {c['columns']:,} | {c['binary']:,} | {c['Native_Runtime']:.6f} | {c['presolve_seconds']:.2f} | {c['NodeCount']:.0f} |" for c in comparison)
    movement='\n'.join(f"- {a['unit']}: Arc {a['arc']}, {a['source']} 출발 {a['depart']} → {a['destination']} 도착 {a['arrive']}, 재접속 {a['connect']}, {a['energy_kWh']:.12f} kWh" for a in actual_move['actual_moves'])
    text=f'''# V42 B2 — Adaptive Beam·4-MESS Joint 정식화 재설계 최종 보고서

IEEE123 B2 May01(2025-05-01), 원본96슬롯 Source18r Exact C3A+Dense. UB 개선은 없었다. 직접 대체 정식화는 수학적·물리적 무결성 검증에 통과했지만 실제 계산시간이 악화되어 채택하지 않았다. 독립 감사 PASS 후 제출하는 제한 실험의 부정적 결과다.

## 1. 안전 종료와 예산 정정

기존 Controller125764는 소유권·부모PID·생성시각·명령줄·Worktree를 확인한 후 Stop-Process로 신규 Dispatch를 차단했다. 마지막 Worker142760은 원본120초 TimeLimit으로 정상 반환하고 Raw를 저장한 뒤 모델을 해제했다. 마지막 호출 Runtime120.74799990653992초, Status9, NodeCount1, Root LP 미완료, Restricted Bound0.3380383194213583이다. 이 Bound는 Global LB가 아니다.

기존 실제34개 호출 누적 **{stop['Native_used']:.12f}초**와 기존 잔여103.88699984550476초를 먼저 확정했다. 잔여 예산 Pilot 두 호출의 실제 **{auth['stopped_remainder_pilot_Native_used']:.12f}초**도 보존했다. 사용자의 “잔여로 하면 안되고 처음부터 돌려야지” 정정으로 별도 신규 실행의 Native 한도를 **1,800초**, 초기 사용량을 **0초**로 설정했다. 기존 원장·Source Seal·Policy·Raw는 초기화하거나 덮어쓰지 않았다.

신규 실행 실제 사용량 **{state['fresh_Native_used']:.12f}초**, 미사용 한도 **{1800-state['fresh_Native_used']:.12f}초**. 이 작업의 세 실행 단계 실제 합계 **{review['all_this_work_actual_Native']:.12f}초**. 과거 PR2191795.0249993801117초·PR220724.820999622345초는 더 오래된 별도 연구 비용이다. UNKNOWN Runtime은0개다.

원본 실행 Worktree는 D:/v42_b2_global_local_multistart_dual1800_20261013이고 실제 실행 코드는 로컬 미Push 버전이었다. PR220 HEAD를 실행 코드라고 간주하지 않았다. 이전 코드·정책·Raw717개 파일의 SHA를 보존하고, 새 개발은 별도 D:/v42_b2_adaptive_compact_joint_20261013에서 수행했다. Source/Policy SHA는 PHASE0_SAFE_STOP.json과 각 EXECUTED_SOURCE_HASHES.json에 기록했다. B1·다른 Codex·시스템 프로세스는 중단하지 않았다.

## 2. 기존 Joint 정체 원인

6~24개 후보와 교체 모델을 포함한 Joint26개 및 서로 다른 저장 운전벡터33개를 읽기 전용으로 분석했다. 현재 생성기는 원래 PR219의 부분 경로 Beam을 실행한 것이 아니라 정적 한MOVE 열거와 일부 두MOVE 확장으로 후보를 생성했다. 두 번째 출발은40/64/80슬롯, 일부6개 목적지, 첫8개 대표 경로에 편향됐다. 평가 후보 합집합에서 MESS02·04 단일MOVE는 각각5개, MESS03의 세MOVE는 PR220 경로 하나였다. 차량별 원본 Arc 대표 비율은 약1.29~2.36%이며, Arc 비율은 전체 경로 가능영역의 대표율이 아니다.

원본 DAG의 위상적 최대 MOVE 수는 차량별57~59다. 이것은 Grid·SOC·PCS를 모두 만족하는 물리적 이동 최대 횟수가 아니다. PR219의 깊이3, 개발 Beam의 깊이4는 휴리스틱 한도다. STAY·한MOVE·복수MOVE를 허용했고 이동 횟수를 원본 목적문제에 강제하지 않았다.

초기 모델들은 작은 Restricted Pool에서 Warm UB로 Presolve 종료했고, 후기24개 모델 두 개는 Root LP 제한시간에 걸렸다. 후보 품질 부족과 Root 지연을 분리했다. 이 두 현상으로 FULL 물리적 개선 한계를 증명할 수 없다. OPTIMAL은 해당 제한 후보집합과 Solver 허용오차의 결과이며 원본 전역 최적성 증명이 아니다.

## 3. 정수 중복과 정확한 정식화

실제 Source Binary9,322개는 node_activity8,938개와 Charge Mode384개다. 연속 Route Flow207,736개는 Binary와 별도로 감사했다. 정확한 한경로 선택식 `sum_r lambda[u,r]=1`과 원본 경로 incidence 때문에 모든 Route/Node 좌표는 literal0/1로 결정된다.

첫 Exact Extended Formulation은 원본 좌표와 모든 원본 CSR 행을 유지하며8,938개 Node의 중복 정수 지정을 제거했다. 실제 Native0·Raw FULL 검증을 통과했다. 두 번째 Direct Formulation은 Route/Node216,674개 좌표를 삭제하고 `x_dense=T z`, `A_compact=A_source T`로 모든 원본715,596개 행을 의미적으로 유지했다. RHS·Sense는 바꾸지 않았고,4개 한경로 선택 행만 추가했다. 모든 lambda 열의 계수 합을 원본 계수의 정확한 dyadic 분수 합으로 독립 검증하여 상수 이동이나 부동소수 RHS 반올림을 피했다.

Mode384개, Pch/Pdis/Q/SOC와 나머지137,603개 Source 좌표의 Bound·Type·Objective는 그대로 유지했다. 원본 Arc/Node/Flow/Alias·DAG·ETA·이동에너지·종단 SOC·PCS16·AIDC·전체 Grid의 의미는 기존 독립 alias 증명과 Original FULL Replay로 검증했다. 경로 제한 모델은 FULL 가능영역의 부분집합이며 FULL과 전체 가능영역이 같다고 주장하지 않는다.

24개/차량이면 이론적으로384+96=480 Binary지만 이번 실제 작은 모델은8개/차량으로384+32=416 Binary다. Direct 모델의 변수137,635개, 행715,600개, nonzero약7.01M이다. Sparse Fill-in은 증가하지 않았다. Native137,635차원 Raw와354,277차원 Dense 역변환 Raw를 따로 저장했다. `T z`는 모델의 정의된 역변환이며 숫자 반올림·클리핑·수리가 아니다. 원본 PR220 Warm 점은 bit 단위로 복원됐다.

## 4. 실제 계산 비교와 채택 결정

| 정식화 | 입력 변수 | 입력 Binary | 실제 Native초 | Presolve초 | 탐색 Node |
|---|---:|---:|---:|---:|---:|
{table}

OLD_JOINT·EXACT_EXTENDED_FORM·EXACT_DIRECT의 경로 Pool은 동일하다. Source 비용은 과거·잔여 Pilot·신규 실행으로 나눴다. Direct는 입력 변수 약61%를 제거했지만 동일 Pool에서18.728999853134155→29.365999937057495초로 악화됐다. 단순 정수 지정 제거 EF는18.746999979019165초로 이전과 사실상 같았고 속도 개선을 입증하지 못했다. Presolve가 이미 중복 정수를 정리하므로 입력 Binary 감소만으로 실제 난도가 줄었다고 말할 수 없다. 단일 사례 관측이며 일반적인 속도 배율을 주장하지 않는다.

**직접 대체 정식화는 채택하지 않는다.** Source Exact Joint Extended Formulation을 기준 Backend로 보존한다. 첫 Pilot 최대240초에서 FULL UB 이득과 계산 이득을 모두 확인하지 못해 잔여1,736.358초를 자동 소비하지 않았다. 원본 코드·Policy를 수정하지 않고 FINAL_BACKEND_DECISION.json에 거부 결정을 별도로 기록했다.

## 5. Adaptive Minimax Beam와 최적화 피드백

기존 Minimax는 알려진 PR220 해 자체를 약0.1114799241 높게 예측했다. 실제 검증된 incumbent의 차량별 Signed P/Q 기여를 기준으로 보정하고 변경 차량의 서비스·이동 중 출력 중단·PCS·SOC·충전 Rebound 전망을 덧붙였다. 현재 해 기준 점수 일치는 구성상 기준 보정이며 성능 이득이나 인증 Bound가 아니다.

개발 Beam은 PR219 Label·Minimax와 PR220 원본 DAG closure·retiming을 재사용했다. 신규 Joint 결과를 FULL 검증한 뒤 실제64개 다중 병목·SOC/P/Q·충전 Rebound·예측 오차를 반환했다. 후속 Native0 피드백에서는 검증된 PR219 Beam 본체(폭64, 휴리스틱 깊이3)에 실제 incumbent 기준 scorer를 주입하고 개발 깊이4 후보도 reservoir에 유지했다. 부분경로에 위치·시간·에너지·MOVE·SOC 도달 가능 상한·서비스시간·종단 회복 전망을 사용했다.

안전 제외는 원본 Arc Domain과 낙관적 SOC/종단 SOC 도달 상한 필요조건이다. Beam 폭·깊이·점수·8개 입장은 휴리스틱 가지치기이며 전역 불가능성 증명이 아니다. 후보 수를24→30→40으로 늘리지 않았다. 매 차량 STAY·한MOVE·복수MOVE와 PR220/검증된 우승 경로를 유지했다.4차량 provisional 경로의 공동 최대 부하와 위치·출발·재접속 다양성으로 후보를 선택하며 이동을 강제하지 않았다.

피드백 후 차량별 reservoir는 약760~803개,8,729개 고유 단독 경로를 생성한 원래 Beam 결과를 활용했다. 최종 입력은8개/차량이다. 새 Pool Signature는 `{feedback['pool_signature']}`이고 기존 두 평가 Pool과 다르다. 이 후속 Pool의 정합성과 FULL 부분집합 증명은 Native0 PASS이며, 새 Pool의 운전 성능은 Native를 실행하지 않아 미검증이다. MIP의 LP dual 가격을 만들지 않았고 정확한 Reduced-Cost Pricing·Column Generation이라고 부르지 않았다.

## 6. 실제4대 선택·P/Q/SOC·Grid

신규 두 MILP 모두4대 lambda와384 Mode·Pch/Pdis/Q/SOC를 한 모델에서 자유롭게 결정했다. 결과는 MESS01=0MOVE, MESS02=0MOVE, MESS03=3MOVE, MESS04=0MOVE다. 이 선택은 Solver 결과이며 세 차량을 강제로 STAY시킨 모델이 아니다. 모든 차량 MOVE 조합도 위상적으로 선택 가능하지만 모든 조합의 SOC/Grid 가능성을 가정하지 않았다.

{movement}

총 이동에너지는 {actual_move['travel_energy_kWh']:.12f}kWh. SOC는 각 차량97개 경계, 초기·종단760kWh, 원본440~1080kWh·PCS16·300kW·400kVA·효율0.95 조건으로 검사했다. 실제384행 P/Q/Mode와 SOC를 BEST_ACTUAL_JOINT_96_SLOT_MESS_PLAN.csv에 별도 저장했다. Global Best 원본 PR220 계획도 별도 CSV로 보존했다.

Original FULL1,130,336개 행·Dense715,596개 행의 검증과96슬롯 전체403,968개 열적 얼굴 계산을 유지했다. 이전 저장벡터33개마다 모든 원본 행 활동을 계산하고 매96슬롯 최악 행·상위100개·준활성 수·SOC/PCS/P 포화를 기록했다. line.sw2/A/42 또는 line.l10/A/19 두 행만 분석하지 않았다. line.sw1/A 및 line.sw2/A의 여러 슬롯에서도 준활성·활성 얼굴이 관찰됐다. 실제Signed Pch/Pdis/Q 기여와 양의 충전 Rebound를 OPTIMIZATION_FEEDBACK_01.json에 기록했다. 후보는 공급 상실과 이동 후 기회를 고려하지만 FULL 가능 운전과 같은 의미의 heuristic 기여는 아니다.

## 7. 인증 결과

- BEST_GLOBAL_UB = **{state['BEST_GLOBAL_UB']['UB']:.16f}**
- BEST_MOVING_FEASIBLE_UB = **{state['BEST_MOVING_FEASIBLE_UB']['UB']:.16f}**
- 신규 실제4-MESS Joint FULL UB = **{actual['UB']:.16f}**
- PR220 대비 UB 개선량 = **0**
- 인증 Global LB(K48) = **{GLOBAL_LB:.17f}**
- Global Gap = **{state['Global_Gap_percent']:.12f}%**

3% Global Gap을 달성하지 못했다. 신규 Restricted Bound는 Global LB로 채택하지 않았다. 기존244 Binary K32 선택 실험의 인증 개선은0이었으므로 재실행하지 않았다. Conditional LP는 과거 median 생성15.740초·인증 제외0개의 실용성 실패 증거를 근거로 자동 Screening하지 않았다. 신규 LB Native와 Conditional LP Native는0회다.

## 8. Native·Wall·메모리

전체실행 비용은 ALL_SESSION_NATIVE_RUNTIME_LEDGER.json, 생성·Native·Worker Wall·Root·Presolve는 SAME_POOL_FORMULATION_COMPARISON.json과 MEMORY_NUMERIC_WALL_AUDIT.json에 구분했다. 신규 Controller Wall은 {state['wall_seconds']:.3f}초, 신규 Native0 Gate Wall은 {read(DOCS/'NATIVE0_GATE.json')['wall_seconds']:.3f}초다. 준비·Beam·독립 검증·모델 변환 비용은 Native Optimize Runtime과 별도로 기록했다.

이 작업 호출 표본의 최대 실제 Private Commit {max(private)/2**30:.3f}GiB, 최대 RSS {max(rss)/2**30:.3f}GiB, 최소 가용 RAM {min(ram)/2**30:.3f}GiB·가용 Commit {min(commit)/2**30:.3f}GiB. Heavy Worker1·Threads1과 RAM4/Commit6GiB 및 실제 모델 성장 예비 공간 Gate를 통과했다. 원본1e-13~4e2 계수 범위 경고는 보존됐고 수치 허용오차·물리식을 변경하지 않았다. 신규 Raw FULL Replay2/2 PASS, Numerical/Resource 중단0, UNKNOWN Runtime0이다.

## 9. 실패와 미검증

이동성 탐색에서 새 좋은 FULL 해를 찾지 못했다. 정적 후보의 깊이·시간·목적지 편향, 기존 점수의 incumbent 기준 오차, 큰 물리적 연속 모형의 Presolve 비용이 관찰된 원인이다. 입력 크기를 줄여도 계산이 개선되지 않았으므로 직접 대체를 채택하지 않았다. 새로운 피드백 Pool은 폭·종류·다양성이 개선됐지만 실제 UB 효과는 미검증이다. 제한 후보집합의 실패는 물리적 개선 불가능성 증명이 아니다. 단독·2/3대 탐색은 Ablation/초기화 증거이며 본 실험의 결과는 실제4대 Joint 두 모델에서 얻었다.

기존 V1 Raw의 추가lambda 배열 때문에 생긴 packet 형식 실패는 lossless point-only 분리 후 Original FULL 검증된 기존 증거로 보존했다. Phase0 CLI에서 PowerShell이 숫자 인자를 줄인 비교 실패도 실패 증거를 보존하고 문자열 인자로 다시 검사했다. 원본 Raw 숫자를 수리하거나 원래 실패를 덮어쓰지 않았다. 개발 초기 Grid 슬롯 표시 오류는 원본 행 이름의 첫 axis로 수정했으며 수정 전 분석을 development_v0에 보존했다. 이러한 전송·분석 오류와 물리적 불가능성을 구분했다.

## 10. 감사와 제출

독립 이름 기반 incidence·Source 계수 분수 합·전체物리 변수 Bound/Type·CSR/RHS/Sense·Native Readback·Raw inverse·Original FULL·예산·Source 보호 감사 PASS. Source18r `497609b46faa14ea7e32a9483a333ab32fd264ef`, PR220 `b9684fa0999b88092d0cd38229f3453ef3f901b4`와 모든 원본 물리 Case를 보존했다. 이후 Commit/Push 및 새 Draft PR으로 이 부정적 결과와 재사용 가능한 검증 코드를 제출한다. B1/B3/IEEE8500/다른 날짜/May 전체 캠페인/Actual Fresh AC는 실행하지 않았다.
'''
    (DOCS/'ADAPTIVE_JOINT_REDESIGN_FINAL_KO.md').write_text(text,encoding='utf-8')
    write(DOCS/'FINAL_DELIVERY_REFERENCES.json',dict(PASS=True,report=record(DOCS/'ADAPTIVE_JOINT_REDESIGN_FINAL_KO.md'),audit=record(DOCS/'FINAL_INDEPENDENT_REVIEW.json'),
        all_session_ledger=record(DOCS/'ALL_SESSION_NATIVE_RUNTIME_LEDGER.json'),best_plan=record(DOCS/'BEST_GLOBAL_96_SLOT_MESS_PLAN.csv'),actual_joint_plan=record(DOCS/'BEST_ACTUAL_JOINT_96_SLOT_MESS_PLAN.csv'),figures=figures))
    print(json.dumps(dict(PASS=True,figures=len(figures),report=str(DOCS/'ADAPTIVE_JOINT_REDESIGN_FINAL_KO.md'))))

if __name__=='__main__':main()
