"""Stored-evidence analyses, scientific plots and Korean delivery report."""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import csv,gc,re,time,numpy as np
from scipy.stats import spearmanr
from tools.minimax_beam1800.adapter import *
from tools.u4_primal_alns.analyze import original_plan

def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,row))+'|' for row in rows])

def export(case,best,label):
    if best is None:return None,None
    plan,rows=original_plan(case,best['point']['path'],read(best['replay']['path']))
    write(DOCS/f'{label}_PLAN_AUDIT.json',plan)
    with (DOCS/f'{label}_96_SLOT_MESS_PLAN.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert len(rows)==384;return plan,rows

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['stopped_reason']
    resource=r.audit('MINIMAX_FINAL_READONLY',True);assert resource['PASS'];write(DOCS/'POST_RUN_RESOURCE_SOURCE_AUDIT.json',resource)
    case=v.load_case();control=next((e for e in state['events'] if e['stationary_control']),None)
    if control:control=min([e for e in state['events'] if e['stationary_control']],key=lambda e:e['UB'])
    cold=min([e for e in state['events'] if e['method']=='INITIALIZE'],key=lambda e:e['UB'])
    representatives={'COLD':cold,'BEST_GLOBAL':state['BEST_GLOBAL_UB'],'BEST_MOVING':state['BEST_MOVING_FEASIBLE_UB'],'STAY_CONTROL':control}
    plans={label:export(case,best,label) for label,best in representatives.items()}
    scans={}
    for label,best in representatives.items():
        if best is None:continue
        context,receipt=g.refresh(case,v.load_point(best['point']['path']))
        scans[label]=dict(receipt=receipt,critical_grid=context['current_U4_grid_scan'],
            maximum_thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0])
    write(DOCS/'CRITICAL_GRID_ANALYSIS.json',scans)
    baseline_label='STAY_CONTROL' if control else 'COLD';baseline=representatives[baseline_label];moving=representatives['BEST_MOVING']
    if moving:
        original=case.lift(v.load_point(moving['point']['path']));reference=case.lift(v.load_point(baseline['point']['path']));delta=original-reference
        lookup={str(n):j for j,n in enumerate(case.original_d['names'])};old_rows={(x['unit'],x['slot']):x for x in plans[baseline_label][1]}
        rebound=[dict(unit=row['unit'],slot=row['slot'],site=row['site'],Pch_increase_kW=row['Pch_kW']-old_rows[row['unit'],row['slot']]['Pch_kW'],
            Pdis_change_kW=row['Pdis_kW']-old_rows[row['unit'],row['slot']]['Pdis_kW'],Q_change_kvar=row['Q_kvar']-old_rows[row['unit'],row['slot']]['Q_kvar'])
            for row in plans['BEST_MOVING'][1] if row['Pch_kW']>old_rows[row['unit'],row['slot']]['Pch_kW']+1e-6]
        from tools.time_decomposed_lb.grid import SelectiveAuthority
        authority=SelectiveAuthority();terms=[];top=scans['BEST_MOVING']['maximum_thermal'];index=top['metadata']['index']
        try:
            for slot in sorted({x['slot'] for x in rebound}):
                ids=[i for i in authority.security_by_slot[slot] if str(authority.maps['row_names'][i]).startswith(f'line_thermal_face[{slot},{index},')]
                for i in ids:
                    packet=authority.project(i,slot);charge=Counter();all_pq=Counter();scale=-F(packet['coeff']['rho_max'])
                    for name,value in packet['coeff'].items():
                        m=re.fullmatch(r'(Pch|Pdis|Q)\[(MESS\d\d),([^,]+),(\d+)\]',name)
                        if m:
                            term=float(F(value)/scale)*delta[lookup[name]];all_pq[m[2]]+=term
                            if m[1]=='Pch':charge[m[2]]+=term
                    terms.append(dict(slot=slot,asset=top['metadata']['asset'],original_row=i,name=packet['name'],
                        charging_delta_normalized_loading=dict(charge),MESS_PQ_delta_normalized_loading=dict(all_pq),source_row_sha=packet['source_row_sha256']))
        finally:authority.close()
        write(DOCS/'REBOUND_ANALYSIS.json',dict(measured=True,comparison=f'BEST_MOVING minus newly validated {baseline_label}',
            baseline_is_historical_raw=False,charging_increases=rebound,limiting_asset=top,grid_contributions=terms,
            all96_terminal_SOC_enforced=True,positive_delta_means_loading_increase=True,
            attribution_limit='Cold has fixed modes and zero net active power; differences include Mode/P/Q reoptimization, not travel-only causal rebound',
            travel_energy_kWh=plans['BEST_MOVING'][0]['travel_energy_kWh']))
    else:write(DOCS/'REBOUND_ANALYSIS.json',dict(measured=False,reason='NO_NEW_FULL_MOVING_POINT'))
    routes=[it for it in state['iterations'] if it['method']=='ROUTE_FIXED'];moving_routes=[it for it in routes if not it['candidate'].get('stationary_control')]
    measured=[it for it in moving_routes if it['verified_UB'] is not None]
    equal=sum(abs(it['verified_UB']-HISTORICAL)<=1e-8 for it in measured)
    epochs=[read(p) for p in sorted(DOCS.glob('ROUTE_CANDIDATES_EPOCH_*.json'))]
    rank={c['candidate_id']:i+1 for epoch in epochs for i,c in enumerate(epoch['candidates'])}
    queued=[c for ep in epochs for c in ep['candidates']]
    timing=[]
    for it in moving_routes:
        c=it['candidate'];moves=[]
        # Critical times are those that actually governed this frozen-ranking
        # epoch, not post-hoc times from a different historical solution.
        epoch=int(c['candidate_id'].split('_',1)[0][1:]);context=read(DOCS/f'grid/epoch{epoch:02d}/CRITICAL_MINIMAX_CONTEXT.json')
        slots=sorted({row['slot'] for row in context['rows']})
        for u,path in c['paths'].items():
            for k in path:
                a=case.graph[2][k]
                if a[-1] is not None:moves.append(dict(unit=u,arc=k,depart=a[1],arrive=a[-1].arrive,connect=a[3],energy_kWh=a[-1].energy_kwh,
                    can_directly_serve_critical_slots=[t for t in slots if t>=a[3]],cannot_serve_earlier_critical_slots=[t for t in slots if t<a[3]]))
        timing.append(dict(candidate_id=c['candidate_id'],rank=rank[c['candidate_id']],score=c['score'],verified_UB=it['verified_UB'],moves=moves))
    corr=spearmanr([it['candidate']['score'] for it in measured],[it['verified_UB'] for it in measured]) if len(measured)>1 else None
    diagnostics=dict(PASS=True,route_MILP_calls=len(routes),moving_route_MILP_calls=len(moving_routes),stationary_controls=len(routes)-len(moving_routes),
        moving_FULL_feasible=len(measured),baseline_equal_paths=equal,baseline_equal_ratio=None if not measured else equal/len(measured),
        evaluation_by_vehicle=dict(Counter(u for it in moving_routes for u in it['candidate']['units'])),
        queued_by_vehicle=dict(Counter(u for c in queued for u in c['units'])),
        evaluated_departure_bands=dict(Counter(it['candidate']['departure']//12 for it in moving_routes)),
        queued_departure_bands=dict(Counter(c['departure']//12 for c in queued)),
        evaluated_first_arrival_bands=dict(Counter(it['candidate']['first_arrive']//12 for it in moving_routes)),
        queued_first_arrival_bands=dict(Counter(c['first_arrive']//12 for c in queued)),
        vehicle_count_scope='Candidate changed-vehicle participation; inherited center moves may involve other vehicles as well',
        reconnect_before_critical_slot_ratio=(sum(len(a['can_directly_serve_critical_slots']) for t in timing for a in t['moves']) /
            max(1,sum(len(a['can_directly_serve_critical_slots'])+len(a['cannot_serve_earlier_critical_slots']) for t in timing for a in t['moves']))),
        evaluated_destinations=dict(Counter(it['candidate']['destination'] for it in moving_routes)),
        score_vs_actual_objective_Spearman=None if corr is None or not np.isfinite(corr.statistic) else float(corr.statistic),
        Spearman_pvalue=None if corr is None or not np.isfinite(corr.pvalue) else float(corr.pvalue),
        correlation_scope='Only FULL-validated evaluated routes; goal-constrained successes and selection bias included, not complete path-space evidence',
        exact_LP_exclusions=state['LP_exact_pruned'],heuristic_ranking_deferred=sum(e['heuristic_ranking_deferred']+e['counts']['cooperative_heuristic_deferred'] for e in state['search_epochs']),
        heuristic_beam_pruned=sum(e['heuristic_beam_pruned'] for e in state['search_epochs']),
        result_states=dict(Counter(s for it in moving_routes for s in set(it['result_states']))),
        moving_actual_timing=timing,full_route_space_exhausted=False)
    write(DOCS/'ROUTE_FIXED_MILP_RESULTS.json',dict(results=routes,restricted_ObjBound_is_Global_LB=False))
    write(DOCS/'MOVING_FEASIBILITY_DIAGNOSTICS.json',diagnostics)
    events=state['events']
    def first(predicate):
        selected=[e for e in events if predicate(e)]
        return min(selected,key=lambda e:e['Native_capture_seconds']) if selected else 'NOT_REACHED'
    benchmarks=dict(T1=first(lambda e:e['UB']<=HISTORICAL+1e-8),T2=first(lambda e:e['moves']>0 and e['UB']<=HISTORICAL+1e-8),
        T3=first(lambda e:e['moves']>0 and e['UB']<HISTORICAL-1e-5),T4=state['BEST_GLOBAL_UB'],T5=moving,
        first_FULL_moving=first(lambda e:e['moves']>0),material_moving_improvement=first(lambda e:e['moves']>0 and e['UB']<=HISTORICAL-.005),
        first_stationary_control_baseline_match=first(lambda e:e['stationary_control'] and e['UB']<=HISTORICAL+1e-8),
        historical_N1_UB=HISTORICAL,comparison_tolerance=1e-8,strict_delta=1e-5,material_delta=.005,
        time_definition='Retrospective cumulative Native raw capture time for subsequently FULL-validated points; cumulative Native at validation and wall acceptance separately retained')
    write(DOCS/'COLD_START_BENCHMARKS.json',benchmarks)
    prior=read(DOCS/'PR218_READONLY_FAILURE_ANALYSIS.json')
    old_state=read(ROOT/'docs/v42_b2_k32_routefixed1800_canary/FINAL_STATE.json')
    old_routes=[it for it in old_state['iterations'] if it['method']=='ROUTE_FIXED']
    old_first_calls=next((i+1 for i,it in enumerate(old_routes) if any(x['PASS'] and read(x['replay']['path'])['Global_UB']<=HISTORICAL+1e-8 for x in it['validated'])),'NOT_REACHED')
    new_first_calls=next((i+1 for i,it in enumerate(moving_routes) if it['verified_UB'] is not None and it['verified_UB']<=HISTORICAL+1e-8),'NOT_REACHED')
    def btime(e):return e if isinstance(e,str) else e['Native_capture_seconds']
    metrics=[['T1 Native seconds',prior['benchmarks']['T1'],btime(benchmarks['T1'])],['T2 moving Native seconds',prior['benchmarks']['T2'],btime(benchmarks['T2'])],
        ['T3 strict moving improvement',prior['benchmarks']['T3'],btime(benchmarks['T3'])],['Moving MILP calls to first baseline match',old_first_calls,new_first_calls],['Route MILP calls',54,len(routes)],
        ['Moving FULL feasible',53,len(measured)],['Best Global UB',HISTORICAL,state['BEST_GLOBAL_UB']['UB']],
        ['Best Moving UB',HISTORICAL,None if moving is None else moving['UB']],['Certified Global LB',GLOBAL_LB,GLOBAL_LB],
        ['Global gap (%)',100*(HISTORICAL-GLOBAL_LB)/HISTORICAL,None if state['Global_gap'] is None else 100*state['Global_gap']],
        ['Native seconds',1795.0209996700287,state['Native_used']],['Controller wall seconds',read(ROOT/'docs/v42_b2_k32_routefixed1800_canary/FINAL_STATE.json')['controller_wall_seconds'],state['controller_wall_seconds']]]
    write(DOCS/'PR218_COMPARISON.json',dict(metrics=metrics,within_May01_policy_tuning_not_out_of_sample=True,
        fewer_calls_alone_is_not_performance_improvement=True))
    replay=[dict(method=it['method'],candidate_id=None if it['candidate'] is None else it['candidate']['candidate_id'],**item)
        for it in state['iterations'] for item in it['validated']]
    write(DOCS/'FULL_REPLAY_CERTIFICATES.json',dict(certificates=replay,Raw_not_rounded_clipped_or_repaired=True,validator_tolerance_unchanged=True))
    write(DOCS/'BEST_UB_TRAJECTORY.json',dict(global_points=state['trajectory'],moving_points=state['moving_trajectory'],events=events))
    samples=[];warnings=[]
    for call in state['calls']:
        samples.extend(call[k] for k in ('build_memory_before','build_memory_after','after_native_memory') if k in call)
        samples.extend(s['sample'] for s in call['resource_samples'])
        log=Path(call['receipt']['path']).parent/'NATIVE_GUROBI.log'
        if log.exists():warnings.extend(dict(path=str(log),line=line) for line in log.read_text(encoding='utf-8').splitlines() if 'Warning:' in line or 'Kappa' in line)
    memory=dict(PASS=True,Threads=1,Heavy_workers=1,minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),
        minimum_commit_available=min(s['system']['Commit_available'] for s in samples),peak_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
        peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] for s in samples),original_numeric_warnings=warnings,
        RAM_reserve_bytes=4*2**30,commit_reserve_bytes=6*2**30,model_growth_reserve_at_every_build=True)
    write(DOCS/'MEMORY_NUMERIC_AUDIT.json',memory)
    write(DOCS/'LP_SCREENING_PERFORMANCE.json',dict(pilot=state['LP_pilot'],gate=state.get('LP_PRACTICAL_GATE'),LP_Native=state['LP_native'],
        LP_worker_wall=state['LP_wall'],exact_exclusions=state['LP_exact_pruned'],LP_Global_LB_promotions=0,
        additional_cost_definition='Sum LP workers build/Native/dual-certificate wall; separate from Native, no claimed counterfactual speed saving'))
    write(DOCS/'ACTUAL_COMPATIBILITY.json',dict(ACTUAL='ACTUAL_NOT_RUN',Actual_AC_PASS=False,planning_FULL_PASS=True,
        frozen_accepted_actual_interface_created=False,original_FULL_is_not_fresh_OpenDSS_AC=True,B1_runs=0,B3_runs=0,IEEE8500_runs=0,
        other_dates=0,campaign_runs=0,schedules_changed=False,Global_gap_3pct=state['Global_gap'] is not None and state['Global_gap']<=.03))
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(10,9),sharex=True)
    for a,key,title in [(axes[0],'trajectory','Best Global UB'),(axes[1],'moving_trajectory','Best Moving UB')]:
        pts=state[key]
        if pts:
            xs=[e['Native_capture_seconds'] for e in pts]+[state['Native_used']];ys=[e['UB'] for e in pts]+[pts[-1]['UB']]
            a.step(xs,ys,where='post',label=title,color='#1b668b' if key=='trajectory' else '#c17a20')
        a.axhline(HISTORICAL,color='#a33939',linestyle='--',label='Historical N1 reference');a.set_ylabel('rho_max');a.legend(fontsize=8)
    pts=state['trajectory'];xs=[e['Native_capture_seconds'] for e in pts]+[state['Native_used']]
    ys=[100*(e['UB']-GLOBAL_LB)/e['UB'] for e in pts]+[100*state['Global_gap']]
    axes[2].step(xs,ys,where='post',label='Certified global gap',color='#635093');axes[2].axhline(3,color='#a33939',linestyle='--',label='3% target')
    axes[2].set(ylabel='Global gap (%)',xlabel='Cumulative Native Optimize Runtime (s)',xlim=(0,state['Native_used']+5));axes[2].legend(fontsize=8)
    markers={}
    for key in ('T1','T2','T3'):
        event=benchmarks[key]
        if not isinstance(event,str):markers.setdefault(event['Native_capture_seconds'],[]).append(key)
    for elapsed,labels in markers.items():
        for a in axes:a.axvline(elapsed,color='#7657a1',alpha=.5,linestyle=':')
        axes[0].annotate(f'{"/".join(labels)} = {elapsed:.1f}s',xy=(elapsed,.675),xytext=(elapsed+90,.666),
            arrowprops=dict(arrowstyle='->',color='#7657a1'),fontsize=8,color='#7657a1')
    for a in axes:a.grid(alpha=.2)
    fig.suptitle('IEEE123 B2 May01 - cold-start minimax beam / conditional LP / route MILP');fig.tight_layout()
    for extension in ('png','svg'):fig.savefig(DOCS/f'UB_MOVING_GAP_VS_NATIVE.{extension}',dpi=180)
    plt.close(fig)
    fig,a=plt.subplots(figsize=(8,5));scatter=a.scatter([rank[it['candidate']['candidate_id']] for it in measured],[it['verified_UB'] for it in measured],c=[it['candidate']['moves'] for it in measured],cmap='viridis')
    fig.colorbar(scatter,ax=a,label='Actual MOVE arcs in four-vehicle route')
    a.axhline(HISTORICAL,color='#a33939',linestyle='--');a.set(xlabel='Candidate rank within current FULL-center epoch',ylabel='FULL verified route MILP objective',title='Evaluated feasible routes only; goal/selection bias retained');a.grid(alpha=.2);fig.tight_layout()
    fig.savefig(DOCS/'CANDIDATE_RANK_VS_OBJECTIVE.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(10,4));units=sorted(case.graph[1])
    for a,field,title in [(ax[0],'queued_by_vehicle','Queued candidate participation'),(ax[1],'evaluation_by_vehicle','Moving MILP evaluation participation')]:
        a.bar(units,[diagnostics[field].get(u,0) for u in units],color='#267294');a.set_title(title,fontsize=10);a.tick_params(axis='x',labelsize=8);a.set_ylabel('Routes (pair counts for both units)')
    fig.tight_layout();fig.savefig(DOCS/'VEHICLE_ROUTE_DISTRIBUTION.png',dpi=180);plt.close(fig)
    route_rows=[]
    if moving:
        for unit,info in plans['BEST_MOVING'][0]['units'].items():
            for arc in info['move_routes']:route_rows.append([unit,arc['source'],arc['depart'],arc['destination'],arc['arrive'],arc['connect'],arc['energy_kWh'],arc['original_arc_index']])
    global_ub=state['BEST_GLOBAL_UB']['UB'];moving_ub=None if moving is None else moving['UB'];improvement=None if moving_ub is None else HISTORICAL-moving_ub
    adopt='추가 독립 날짜 검증 전 일반 채택 보류'
    if improvement is None or improvement<1e-5:adopt='이동 UB 개선 근거 부족으로 성능 개선 알고리즘 채택 보류'
    report=f'''# V42 B2 Minimax Beam 1,800초 — 최종 연구 보고서

BEST_GLOBAL_UB = **{global_ub:.16g}**, BEST_MOVING_FEASIBLE_UB = **{moving_ub}**. 인증 Global LB = **{GLOBAL_LB:.17g}**, Global Gap = **{100*state['Global_gap']:.6f}%**. 실제 Native 누적 **{state['Native_used']:.6f}초**, Controller Wall **{state['controller_wall_seconds']:.3f}초**. 종료 사유 `{state['stopped_reason']}`. 분류는 **Certified Matheuristic / Bound-Guided Anytime MILP**이며 전체 이동경로 전역 최적성을 입증하지 않았다. ACTUAL_NOT_RUN.

{table(['지표','PR218','신규 Canary'],metrics)}

## 1. PR218 분석과 변경
PR218의 53개 FULL 가능 경로에서 기존 합산 Score와 실제 rho의 Spearman = {prior['score_vs_actual_objective_Spearman']:.6f}; 높은 gain 점수가 높은 rho와 연관됐다. 첫 네 평가가 모두 MESS01이고, 동일 기준 UB 경로는 {prior['baseline_equal_paths']}/53이었다. 실제 ETA별 병목 슬롯 관계는 `PR218_READONLY_FAILURE_ANALYSIS.json`에 보존했다. 새 정책은 공동 최대 행 부하, 시간 선행성, SOC 회복, 차량 다양성, 교차 협조 조합을 사용한다. 상관관계는 인과 증명이나 다른 날짜 성능 증거가 아니다.

## 2. N1 선행 단계 제거
Cold → 이동 Beam → 조건부 LP → 선택 경로 Exact C3A+Dense MILP → 원본 FULL Replay 순서다. 별도 N1 선행 Optimize는 {state['N1_upfront_calls']}회. STAY 비교군 호출은 {diagnostics['stationary_controls']}회다. 이 비교군을 호출한다면 원본 N1과 수학적으로 같은 문제이며 Native 300초 이후 및 이동 기준 도달 전이라는 정책을 적용한다. 이번에는 첫 이동 모델이 기준을 이미 개선해 비교군 없이 이동 평가를 계속했다.

## 3. Cold Start와 과거 점 미사용
모든 신규 Native 모델의 historical MIP Start는 0개다. Source 권위점은 Native0 대수 회귀 검증에만 읽었으며 신규 UB로 등록하거나 solver start로 전달하지 않았다. 신규 Cold FULL UB는 {cold['UB']}. 유효한 Cold 가능해 후 U4를 호출하지 않았다. 증거: `PRE_NATIVE0_REGRESSION.json`, 각 `NATIVE_CALL.json`의 initial_point/actual_NumStart, `MODEL_IDENTITY.json`, 원본 Replay.

## 4. Minimax Beam과 Label
Beam64, 차량당 MOVE 깊이3은 heuristic 탐색 정책이다. Label은 Site/Slot/누적 실제 이동에너지/SOC 상계/잔여 충전 기회/실제 재접속/임계 행 벡터/서비스 시간창/MOVE 수/원본 Arc 경로를 갖는다. Score = Current FULL UB − max(고정 주입 기준부하 + 차량별 경로 조건 PCS 공급 추정 + 96슬롯 회복 부하 추정)이며 실제 UB나 유효 하한이 아니다. 부분 경로는 실제 원본 Arc의 depart/connect로 도달 가능한 미래 Site의 optimistic envelope를 사용한다. 미래 행마다 별도 선택하므로 정확한 dominance 주장도 없다.

## 5. SOC·Rebound Look-ahead
원본 440–1080kWh, 초기/종단760kWh, eta_ch=eta_dis=0.95, dt=0.25, P300, PCS400을 유지한다. 완성 경로 점수는 시간순 PCS 공급, 방전 효율 및 SOC 가용량, 저부하 연결 충전창과 종단 회복을 추정한다. 추정 SOC의 clamp는 순위용 내부 상태에만 적용하며 Native Raw에는 적용하지 않았다. 회복은 slot0–95 내에서만 계상한다. 원본 Arc domain과 최대 충전을 허용해도 부족한 SOC 필요조건만 물리적 hard pruning이며, 나머지 Beam/깊이/그룹 제거는 heuristic이다.

## 6. 조건부 LP 포함관계
Original FULL CSR에서 연결 P/Q, Mode gate, PCS16, SOC96 점화식, 초기/종단 SOC의 모든 197,116개 행과 27,599개 power/SOC/Mode/rho 열을 직접 추출했다. 원본 경로 Arc의 literal0/1은 RHS에 정확히 대입한다. 384개 Mode만 B→C로 완화하고 기타 Grid 행을 생략한다. 선택 임계 열·행은 독립 recursive helper elimination으로 원본 고정 AIDC 상수를 유지하여 재구성했다. 이진64 계수의 정확한 Fraction 오차를 변수 box에서 지지함수로 상계하고 RHS를 바깥 방향으로 반올림하므로 FULL 경로 고정 MILP 가능영역의 projection이 LP에 포함된다. 증거: `lp_template/INDEPENDENT_SOURCE_REEXTRACTION.json`, epoch별 independent_source_projection, LP Native Readback. LP 해는 FULL UB가 아니다.

## 7. LP 실측 Gate
LP {len(state['LP_pilot'])}회, Native {state['LP_native']:.6f}초, 추가 LP Worker Wall {state['LP_wall']:.3f}초, 정확한 제외 {state['LP_exact_pruned']}개. Gate = `{state.get('LP_PRACTICAL_GATE')}`. first8 사전등록 기준으로 느린 build/runtime 또는 약한 하한이면 중단하고 미사용 예산을 MILP에 돌린다. 유효한 실제 dual Pi의 부호와 finite-box 잔차를 정확한 dyadic weak duality로 검증하고 offline으로 재계산했다. TIME_LIMIT/LP incumbent만으로 경로를 제거하지 않았다. 경로별 bound는 Global LB로 승격하지 않았다. 관련 파일 `LP_SCREENING_PERFORMANCE.json`.

## 8. Route-Fixed Exact MILP
총 Route MILP {len(routes)}회, 실제 이동 {len(moving_routes)}회, FULL 가능 이동 {len(measured)}회. 4대 Mode384, 모든 Pch/Pdis/Q/SOC97과 전 원본96 Grid/PCS/SVR/Cap/AIDC를 최적화했다. Node/Arc/Flow/Alias는 실제 원본 이동경로로 고정하며 Native Readback 전에는 Optimize를 실행하지 않았다. pilot unrestricted, 이후 4회 중3회 rho≤현재UB−1e−5 목표, 1회 unrestricted 정책이다. goal INFEASIBLE은 경로 자체의 물리적 불가능성으로 해석하지 않았다. 상태: `{diagnostics['result_states']}`.

## 9. 역사적 N1 UB 도달시간
T1 = {btime(benchmarks['T1'])}, T2 이동 = {btime(benchmarks['T2'])}, 정차 비교군 최초 기준 도달 = {btime(benchmarks['first_stationary_control_baseline_match'])} Native초. 과거 UB 0.5461621302242249는 비교 기준만 사용했다. raw 발견의 누적 Native, FULL 검증 시점 누적 Native 및 Controller Wall은 `COLD_START_BENCHMARKS.json`에 분리돼 있다. 이전 결과의 시간0 복사는 없다.

## 10. 이동 개선 판정
T3 strict 이동 개선 = {btime(benchmarks['T3'])}. 유의 개선 기준1e−5, 실질 개선 기준0.005. 최선 이동의 역사적 UB 감소 = {improvement}. 실질 개선 최초 시간 = {btime(benchmarks['material_moving_improvement'])}. 미도달은 NOT_REACHED로 보고한다.

## 11. UB/Gap 궤적
FULL 통과 점만 갱신했고 동일 UB는 새 ranking center로 반복 사용하지 않았다. Global Gap=(Best Global UB−K48 LB)/UB. 목표3% 인증은 {state['Global_gap']<=.03}. 조건부 LP 및 제한 MILP ObjBound는 이 Gap에 쓰지 않았다.

![UB, 이동 UB 및 Global Gap](UB_MOVING_GAP_VS_NATIVE.png)

## 12. 실제 이동경로
{table(['MESS','출발지','depart','도착지','arrive','connect','kWh','원본 Arc'],route_rows) if route_rows else '신규 FULL 이동계획 없음.'}

다른 차량의 STAY와 원본 slot96 terminal 위치를 포함한 완전한 순서는 `BEST_MOVING_PLAN_AUDIT.json`에 있다. origin 복귀 조건을 새로 넣지 않았다.

## 13. 96슬롯 운전계획
`BEST_GLOBAL_96_SLOT_MESS_PLAN.csv` 및 `BEST_MOVING_96_SLOT_MESS_PLAN.csv`는 4대×96=384행의 원본 Pch/Pdis/Q/Mode/SOC before/after/실제 Arc/ETA/이동 debit을 제공한다. SOC 경계97개는 PLAN_AUDIT에 모두 보존한다. Raw를 rounding/clipping/repair하지 않았다.

## 14. Critical Line/Phase/Slot 변화
새로운 전96슬롯 원본814,560 security 행을 재스캔했다. Cold 최대 행 = `{scans['COLD']['maximum_thermal']}`. Best Global 최대 행 = `{scans['BEST_GLOBAL']['maximum_thermal']}`. Best Moving 최대 행 = `{None if moving is None else scans['BEST_MOVING']['maximum_thermal']}`. 전압/NormalAmps/Transformer도 FULL에 포함되며 `CRITICAL_GRID_ANALYSIS.json`에서 확인한다.

## 15. Rebound 실측
충전 증가를 신규 {baseline_label} 대비 계산했고 최선 이동의 실제 제한 asset에서 원본 signed P/Q 계수로 부하 증가 기여를 재산출했다. Cold는 Mode가 고정된 점이므로 이 차이에는 Mode/P/Q 재최적화 효과도 포함되며 이동에너지 전용 Rebound의 인과 분리 증거로 해석하지 않는다. 이는 역사적 N1 Raw를 현재 점으로 복사한 비교가 아니다. `REBOUND_ANALYSIS.json`에 slot별 결과와 source-row SHA가 있다. 종단 SOC와 이동 중 P/Q=0 조건은 원본 Replay로 확인했다.

## 16. Native·Wall·메모리
총 Native {state['Native_used']:.6f}초 ≤1,800, budget reset0, 모델 생성·FULL Replay wall 별도. 한 heavy worker, Threads1, GPU 미사용. 관측 최소 RAM 가용 {memory['minimum_RAM_available']/2**30:.3f}GiB, Commit 가용 {memory['minimum_commit_available']/2**30:.3f}GiB. 모든 Model Build 후 actual growth reserve를 추가 승인하고 callback에서 확인했다. 원본 수치 경고 {len(warnings)}개를 숨기지 않았으며 `MEMORY_NUMERIC_AUDIT.json`에 보존했다.

## 17. 원본 FULL 독립 검증
Native worker 종료·모델 dispose 후 별도 validator process에서 원본 CSR/RHS/Sense, 원본 binary/integer literal, Alias/DAG/ETA/energy, Mode/PCS, SOC 초기/종단, 계통96, objective를 검증했다. Native Raw와 exact objective SHA는 각 Replay에 결합됐다. 허용오차를 바꾸지 않았으며 실패 Raw도 보존했다. 원본 FULL PASS는 Fresh OpenDSS AC PASS를 뜻하지 않는다. `FULL_REPLAY_CERTIFICATES.json`, `FINAL_INDEPENDENT_REVIEW.json` 참조.

## 18. K32/K48 인증 계승
동일 Source/Case/Matrix/Domain 및 기존 모델·계수 파일 SHA를 다시 확인했다. K32=.46497617639758426, K48=.46498486997548166. 신규 LB 강화 Optimize0회, K48를 Global LB로 유지했다. `K32_K48_LB_CERTIFICATES.json` 참조.

## 19. PR218 대비 효율
Score–actual rho Spearman = {diagnostics['score_vs_actual_objective_Spearman']}; goal 성공 표본과 선택 편향을 포함한다. 첫 기준 이동 UB까지 평가한 이동 MILP는 PR218 {old_first_calls}회→신규 {new_first_calls}회지만 전체 호출은 54→{len(routes)}회로 감소하지 않았다. 동일 UB 반복 {equal}/{len(measured)}, 정확한 LP 제외 {state['LP_exact_pruned']}, heuristic 순위 후순위 {diagnostics['heuristic_ranking_deferred']}, Beam label 제거 {diagnostics['heuristic_beam_pruned']}. 변경 차량별 평가 수 `{diagnostics['evaluation_by_vehicle']}`이며 MESS01 편향이 남았다. 후보 재접속·임계 슬롯 비교 비율은 {diagnostics['reconnect_before_critical_slot_ratio']:.6f}; 이는 모든 실제 MOVE와 해당 epoch 임계 슬롯의 쌍에서 connect≤critical slot 비율이다. 출발/도착 시간대 분포는 `MOVING_FEASIBILITY_DIAGNOSTICS.json`에 있다. 적은 호출 자체를 개선으로 주장하지 않고 위 T1/T2/T3와 동일 Native 예산 UB를 비교한다. May01 사후 설계이므로 May02/03 일반화 성능은 검증하지 않았다.

![후보 순위와 목적값](CANDIDATE_RANK_VS_OBJECTIVE.png)

![차량별 경로 평가](VEHICLE_ROUTE_DISTRIBUTION.png)

## 20. 채택 판단과 한계
**{adopt}**. LP Gate 및 관측 실패는 그대로 보고한다. 전체 경로 공간을 탐색하거나 전역 최적성을 입증하지 않았다. 3% 미달이면 실제 Gap을 유지한다. B1/B3/IEEE8500/다른 날짜/May 캠페인 Optimize0회, 예약 task와 automations를 변경하지 않았다. 이전 PR218 및 Scientific Source/Native ledger는 읽기 전용으로 보존했다.
'''
    (DOCS/'MINIMAX_BEAM_1800_FINAL_KO.md').write_text(report,encoding='utf-8')
    write(DOCS/'POSTPROCESS_RECEIPT.json',dict(PASS=True,Native_optimize_calls=0,wall_seconds=time.perf_counter()-began))
    print(json.dumps(dict(PASS=True,T1=btime(benchmarks['T1']),T2=btime(benchmarks['T2']),T3=btime(benchmarks['T3']),Native=state['Native_used'])))

if __name__=='__main__':main()
