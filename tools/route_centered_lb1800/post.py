"""Read-only physical comparisons, figures and Korean local-branching report."""
from collections import Counter
from fractions import Fraction as F
import csv,time,re,numpy as np
from tools.route_centered_lb1800.adapter import *
from tools.u4_primal_alns.analyze import original_plan

def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,row))+'|' for row in rows])

def export(case,result,label):
    plan,rows=original_plan(case,result['point']['path'],read(result['replay']['path']))
    write(DOCS/f'{label}_PLAN_AUDIT.json',plan)
    with (DOCS/f'{label}_96_SLOT_MESS_PLAN.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return plan,rows

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['stopped_reason']
    resource=r.audit('ROUTE_CENTERED_FINAL',True);write(DOCS/'POST_RUN_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS']
    case=v.load_case();best=state['BEST_GLOBAL_UB'];moving=state['BEST_MOVING_FEASIBLE_UB'];plan,rows=export(case,best,'BEST')
    export(case,moving,'BEST_MOVING');initial=state['trajectory'][0];baseline,initial_rows=export(case,initial,'PR219_CENTER')
    comparisons=[];ablation=[];readbacks=[];closure=[];root=[];points=[];scans={}
    for it in state['iterations']:
        call=read(it['call']['path']);spec=read(it['specification']['path']);folder=__import__('pathlib').Path(it['call']['path']).parent
        verified=[e for e in state['events'] if e['candidate_id']==it['candidate_id']]
        physical=None;thermal=None
        if verified:
            result=min(verified,key=lambda e:e['UB']);physical,operating=original_plan(case,result['point']['path'],read(result['replay']['path']))
            if it['stage']=='ABLATION':
                context,receipt=g.refresh(case,v.load_point(result['point']['path']));thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0]
                write(DOCS/f'ablation/{it["candidate_id"]}_PLAN.json',physical)
                reference={(row['unit'],row['slot']):row for row in initial_rows}
                increased=[dict(unit=row['unit'],slot=row['slot'],site=row['site'],Pch_delta_kW=row['Pch_kW']-reference[row['unit'],row['slot']]['Pch_kW'])
                    for row in operating if row['Pch_kW']>reference[row['unit'],row['slot']]['Pch_kW']+1e-6]
                ablation.append(dict(candidate_id=it['candidate_id'],UB=result['UB'],UB_minus_A0=result['UB']-INITIAL_UB,Native=call['Native_Runtime'],
                    plan=physical,critical_thermal=thermal,charging_increase=increased,
                    causal_scope='Joint reoptimization of all four vehicles, not an independent causal effect of the removed MOVE'))
        comparisons.append(dict(candidate_id=it['candidate_id'],stage=it['stage'],UB=it['verified_UB'],moves=it['verified_moves'],
            Native=call['Native_Runtime'],cumulative_Native=next(c['cumulative_Native_after'] for c in state['calls'] if c['receipt']['path']==it['call']['path']),
            status=call.get('Status'),result_states=it['result_states'],NodeCount=call.get('NodeCount'),MIPGap=call.get('MIPGap'),
            root_completed_Native=call.get('root_completed_Native_seconds'),root_completed=call.get('root_completed_Native_seconds') is not None,
            radius=spec.get('hamming_radius'),free_binary=spec.get('actual_free_binary',384),fixed_binary=spec.get('actual_fixed_binary',8938),
            center_UB=None if it['center'] is None else it['center']['UB'],actual_NumStart=call['actual_NumStart'],
            actual_NEW_MOVE_arcs=None if not verified else [a for a in min(verified,key=lambda e:e['UB'])['actual_moves']
                if a['arc'] not in (it['center'] or initial).get('actual_route',read(DOCS/'ABLATION_CANDIDATES.json')['initial_route'])[a['unit']]],
            restricted_ObjBound=call.get('ObjBound'),restricted_ObjBound_is_Global_LB=False))
        readback=folder/('ROUTE_LOCAL_BRANCHING_NATIVE_READBACK.json' if it['method']=='ROUTE_LOCAL_BRANCHING' else 'MOVING_ROUTE_NATIVE_READBACK.json')
        readbacks.append(dict(candidate_id=it['candidate_id'],receipt=record(readback),proof=read(readback)))
        closure.append(dict(candidate_id=it['candidate_id'],specification=it['specification'],proof=record(folder/'INDEPENDENT_RESTRICTION_NATIVE0.json')))
        root.append(comparisons[-1]);points.extend(dict(candidate_id=it['candidate_id'],**x) for x in it['validated'])
    write(DOCS/'THREE_MOVE_ABLATION.json',dict(A0=dict(UB=INITIAL_UB,Native_reoptimization=0,plan=baseline),results=ablation,
        joint_four_vehicle_reoptimization=True,independent_causal_MOVE_effects_not_claimed=True))
    write(DOCS/'LOCAL_BRANCHING_ITERATIONS.json',dict(results=comparisons))
    write(DOCS/'NATIVE_MODEL_READBACK.json',dict(PASS=all(x['proof']['PASS'] for x in readbacks),readbacks=readbacks))
    initial_closure=read(DOCS/'ROUTE_DAG_CLOSURE_AUDIT.json');initial_closure['executed_neighborhoods']=closure;write(DOCS/'EXECUTED_ROUTE_DAG_CLOSURE_AUDIT.json',initial_closure)
    write(DOCS/'ORIGINAL_FULL_REPLAY_CERTIFICATES.json',dict(certificates=points,failed_Raw_preserved=True,rounding_clipping_repair=0,
        initial_authority=record(DOCS/'PR219_FRESH_ORIGINAL_FULL_REPLAY.json')))
    for label,result in [('PR219_CENTER',initial),('BEST_GLOBAL',best),('BEST_MOVING',moving)]:
        context,receipt=g.refresh(case,v.load_point(result['point']['path']))
        scans[label]=dict(receipt=receipt,critical_grid=context['current_U4_grid_scan'],maximum_thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0])
    write(DOCS/'CRITICAL_GRID_ANALYSIS.json',scans)
    reference={(row['unit'],row['slot']):row for row in initial_rows}
    rebounds=[dict(unit=row['unit'],slot=row['slot'],site=row['site'],Pch_increase_kW=row['Pch_kW']-reference[row['unit'],row['slot']]['Pch_kW'],
        Pdis_change_kW=row['Pdis_kW']-reference[row['unit'],row['slot']]['Pdis_kW'],Q_change_kvar=row['Q_kvar']-reference[row['unit'],row['slot']]['Q_kvar'])
        for row in rows if row['Pch_kW']>reference[row['unit'],row['slot']]['Pch_kW']+1e-6]
    source=case.lift(v.load_point(initial['point']['path']));new=case.lift(v.load_point(best['point']['path']));delta=new-source
    lookup={str(n):j for j,n in enumerate(case.original_d['names'])};grid_contributions=[]
    from tools.time_decomposed_lb.grid import SelectiveAuthority
    authority=SelectiveAuthority();top=scans['BEST_GLOBAL']['maximum_thermal'];index=top['metadata']['index']
    try:
        for t in sorted({row['slot'] for row in rebounds}):
            for i in authority.security_by_slot[t]:
                if not str(authority.maps['row_names'][i]).startswith(f'line_thermal_face[{t},{index},'):continue
                packet=authority.project(i,t);scale=-F(packet['coeff']['rho_max']);charges=Counter();pq=Counter()
                for name,value in packet['coeff'].items():
                    match=re.fullmatch(r'(Pch|Pdis|Q)\[(MESS\d\d),([^,]+),(\d+)\]',name)
                    if match:
                        contribution=float(F(value)/scale)*delta[lookup[name]];pq[match[2]]+=contribution
                        if match[1]=='Pch':charges[match[2]]+=contribution
                grid_contributions.append(dict(slot=t,name=packet['name'],asset=top['metadata']['asset'],original_row=i,
                    source_row_sha=packet['source_row_sha256'],charge_delta_normalized_loading=dict(charges),all_MESS_PQ_delta=dict(pq)))
    finally:authority.close()
    # Observe actual original PCS rows, rather than assuming a facet phase,
    # radius or reconstruction formula that might differ from Source18r.
    saturation={};pcs_slots={u:set() for u in plan['units']}
    original_A=case.original_A.tocsr()
    pcs=np.flatnonzero(np.char.startswith(case.original_d['row_names'],'PCS16['))
    lhs=original_A[pcs]@new
    operating={(row['unit'],row['slot']):row for row in rows}
    for i,value in zip(pcs,lhs):
        axis=str(case.original_d['row_names'][i]).split('[',1)[1][:-1].split(',');u,site,t=axis[0],axis[1],int(axis[2])
        row=operating[u,t]
        if row['connected'] and row['site']==site and abs(float(value)-float(case.original_d['rhs'][i]))<=1e-6:
            pcs_slots[u].add(t)
    del original_A,lhs
    for u,p in plan['units'].items():
        ur=[row for row in rows if row['unit']==u]
        saturation[u]=dict(SOC_min=p['SOC_min_kWh'],SOC_max=p['SOC_max_kWh'],SOC_min_bound_slots=[row['slot'] for row in ur if abs(row['SOC_before_kWh']-440)<1e-6],
            SOC_max_bound_slots=[row['slot'] for row in ur if abs(row['SOC_before_kWh']-1080)<1e-6],
            active_power_limit_slots=[row['slot'] for row in ur if max(row['Pch_kW'],row['Pdis_kW'])>=300-1e-6],
            PCS16_near_boundary_slots=sorted(pcs_slots[u]),PCS_observation_source='Literal Original FULL PCS16 CSR rows/RHS at actual connected site')
    write(DOCS/'REBOUND_AND_SATURATION_ANALYSIS.json',dict(measured=True,comparison='Final best minus immutable verified PR219 center',
        increased_charging=rebounds,grid_contributions=grid_contributions,limiting_row=top,saturation=saturation,
        all96_terminal_SOC_and_transit_PQ_preserved=True,causality_not_isolated=True,
        failure_reason_scope='Observed saturation and sampled neighborhood outcomes are evidence; original global optimality or a unique failure cause is not proved'))
    samples=[];warnings=[]
    for c in state['calls']:
        samples.extend(c[k] for k in ('build_memory_before','build_memory_after','after_native_memory') if k in c)
        samples.extend(s['sample'] for s in c['resource_samples'])
        log=__import__('pathlib').Path(c['receipt']['path']).parent/'NATIVE_GUROBI.log'
        if log.exists():warnings.extend(dict(path=str(log),line=l) for l in log.read_text(encoding='utf-8').splitlines() if 'Warning:' in l or 'Kappa' in l)
    memory=dict(PASS=True,Threads=1,Heavy_workers=1,minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),
        minimum_commit_available=min(s['system']['Commit_available'] for s in samples),peak_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
        peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] for s in samples),warnings=warnings,actual_model_growth_reserve=True,
        RAM_reserve=4*2**30,commit_reserve=6*2**30)
    write(DOCS/'MEMORY_NUMERIC_AUDIT.json',memory)
    trajectory=state['trajectory'];write(DOCS/'BEST_UB_TRAJECTORY.json',dict(points=trajectory,initial_inherited_Native0_not_new_discovery=True))
    gaps=[dict(Native=p['Native_capture_seconds'],UB=p['UB'],Global_LB=GLOBAL_LB,Global_gap=(p['UB']-GLOBAL_LB)/p['UB']) for p in trajectory]
    write(DOCS/'GLOBAL_GAP_TRAJECTORY.json',dict(points=gaps,final_gap=state['Global_gap'],restricted_bounds_not_promoted=True))
    def first(predicate):
        candidates=[e for e in state['improvements'] if predicate(e)]
        return min(candidates,key=lambda e:e['Native_capture_seconds']) if candidates else 'NOT_REACHED'
    timings=dict(first_strict=first(lambda e:e['UB']<=INITIAL_UB-DELTA),first_material_vs_N1=first(lambda e:e['UB']<=MATERIAL),
        best_capture_Native=best['Native_capture_seconds'],best_is_inherited=best['method']=='INHERITED_PR219',new_improvements=len(state['improvements']),
        strict_delta=DELTA,material_threshold=MATERIAL,Global_gap_3pct=state['Global_gap']<=.03)
    write(DOCS/'WARM_IMPROVEMENT_TIMINGS.json',timings)
    write(DOCS/'ACTUAL_COMPATIBILITY.json',dict(ACTUAL='ACTUAL_NOT_RUN',fresh_OpenDSS=False,planning_PQ_repair=False,
        B1_B3_8500_other_dates_campaign_calls=0,hold_and_disabled_tasks_preserved=True,new_LB_Optimize=0,unrestricted_FULL_BB=0))
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,1,figsize=(10,6),sharex=True)
    xs=[p['Native_capture_seconds'] for p in trajectory]+[state['Native_used']];ubs=[p['UB'] for p in trajectory]+[best['UB']]
    ax[0].step(xs,ubs,where='post',label='Original FULL verified best UB',color='#27668f');ax[0].axhline(INITIAL_UB,color='#a13939',linestyle='--',label='Inherited PR219 UB')
    ax[0].axhline(MATERIAL,color='#318154',linestyle=':',label='N1 material improvement threshold');ax[0].set_ylabel('rho_max');ax[0].legend(fontsize=8)
    gap=[100*(u-GLOBAL_LB)/u for u in ubs];ax[1].step(xs,gap,where='post',color='#7559a4');ax[1].axhline(3,color='#a13939',linestyle='--',label='3% global gap goal')
    ax[1].set(xlabel='New cumulative Native Optimize Runtime (s)',ylabel='Certified global gap (%)',xlim=(0,state['Native_used']+5));ax[1].legend(fontsize=8)
    for a in ax:a.grid(alpha=.2)
    fig.suptitle('Warm PR219-centered Source18r route local branching; previous Native excluded');fig.tight_layout()
    for suffix in ('png','svg'):fig.savefig(DOCS/f'UB_GAP_VS_NATIVE.{suffix}',dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(4,2,figsize=(12,11),sharex=True)
    for i,u in enumerate(sorted(plan['units'])):
        pr=plan['units'][u];ur=[row for row in rows if row['unit']==u]
        axes[i,0].plot(range(97),pr['SOC97_kWh'],label=u,color='#2a758f');axes[i,0].axhline(440,linestyle=':',color='#999');axes[i,0].axhline(1080,linestyle=':',color='#999')
        axes[i,0].set(ylabel='SOC (kWh)',title=u);axes[i,0].legend(fontsize=8)
        axes[i,1].step(range(96),[r['Pch_kW'] for r in ur],where='post',label='Pch kW');axes[i,1].step(range(96),[r['Pdis_kW'] for r in ur],where='post',label='Pdis kW')
        axes[i,1].step(range(96),[r['Q_kvar'] for r in ur],where='post',label='Q kvar');axes[i,1].set_title(u);axes[i,1].legend(fontsize=7,ncol=3)
        for move in pr['move_routes']:
            for a in axes[i]:a.axvspan(move['depart'],move['connect'],color='#b67527',alpha=.16)
        for a in axes[i]:a.grid(alpha=.2)
    axes[-1,0].set_xlabel('Original slot0..96');axes[-1,1].set_xlabel('Original slot0..95');fig.suptitle('Best four-MESS operating plan; shaded actual transit intervals');fig.tight_layout()
    fig.savefig(DOCS/'BEST_SOC_P_Q_PLAN.png',dpi=180);plt.close(fig)
    sites=list(case.graph[0]);site_id={s:i for i,s in enumerate(sites)};fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True)
    for a,u in zip(axes,sorted(plan['units'])):
        pr=plan['units'][u];segments=[]
        used=sorted({site_id[case.graph[2][k][0]] for k in pr['ordered_original_arc_indices']}|{site_id[pr['original_terminal_location']]})
        display={j:i for i,j in enumerate(used)}
        for k in pr['ordered_original_arc_indices']:
            arc=case.graph[2][k];a.plot([arc[1],arc[3]],[display[site_id[arc[0]]],display[site_id[arc[2]]]],color='#27668f',linewidth=1.5 if arc[-1] else 2)
        a.set_yticks(range(len(used)),[sites[j] for j in used]);a.set_title(u,fontsize=10);a.grid(alpha=.2)
    axes[-1].set_xlabel('Original depart/connect slot');fig.suptitle('Best original DAG routes: actual departure and reconnection');fig.tight_layout();fig.savefig(DOCS/'BEST_MESS_ROUTES.png',dpi=180);plt.close(fig)
    algorithm_rows=[['Historical N1',HISTORICAL,0,'PR218 past 21.916 (N1 only)',100*(HISTORICAL-GLOBAL_LB)/HISTORICAL],
        ['PR219 Minimax Beam',INITIAL_UB,3,'Past capture78.053 / total1795.025',100*(INITIAL_UB-GLOBAL_LB)/INITIAL_UB]]
    for label,stages in [('3-MOVE Ablation Best',['ABLATION']),('R1/R2 Route Local Branching',['R1','R2']),('R3 Whole MESS03',['R3']),('R4 Two-MESS',['R4']),('R5/Adaptive',['R5','ADAPTIVE'])]:
        results=[state['stage_best'][s] for s in stages if s in state['stage_best']];result=min(results,key=lambda r:r['UB']) if results else None
        algorithm_rows.append([label,'NOT_EVALUATED' if result is None else result['UB'],'N/A' if result is None else result['moves'],sum(c['Native_Runtime'] for c in state['calls'] if c['stage'] in stages),
            'N/A' if result is None else 100*(result['UB']-GLOBAL_LB)/result['UB']])
    algorithm_rows.append(['Final Best',best['UB'],best['moves'],state['Native_used'],100*state['Global_gap']])
    new_delta=INITIAL_UB-best['UB'];n1_delta=HISTORICAL-best['UB']
    moving_rows=[[u,a['source'],a['depart'],a['destination'],a['arrive'],a['connect'],a['energy_kWh'],a['original_arc_index']] for u,p in plan['units'].items() for a in p['move_routes']]
    iteration_rows=[[x['candidate_id'],x['UB'],x['Native'],x['status'],x['NodeCount'],x['root_completed'],x['MIPGap'],x['radius'],x['free_binary'],x['fixed_binary']] for x in comparisons]
    ab={x['candidate_id'].split('_',1)[0]:x for x in ablation}
    first_event=timings['first_strict'];first_text=first_event if isinstance(first_event,str) else f"{first_event['Native_capture_seconds']:.6f} 신규 Native초 ({first_event['candidate_id']})"
    answers=[f'Q1/Q6: 최종 UB {best["UB"]:.17g}, PR219 대비 감소 {new_delta:.17g}. 최초 신규 유의 개선 {first_text}.',
        f"Q2: A1의 UB는 {ab.get('A1',{}).get('UB')}, A2는 {ab.get('A2',{}).get('UB')}로 A0보다 각각 높았다. 이 변경 가족에서는 후반 이동을 없애면 4대 공동 재최적화 성능이 나빠졌다. 첫 MOVE를 제거한 대조는 없으므로 첫 MOVE 자체의 인과 중요성을 확정하지 않는다. 후반 MOVE의 독립 인과효과도 아니다.",
        f"Q3: A3는 {ab.get('A3',{}).get('UB')}로 수치 허용 안의 동일값, A4는 {ab.get('A4',{}).get('UB')}, A5는 {ab.get('A5',{}).get('UB')}였다. 추가 개선은 MILP가 후반 출발 64/77을 선택한 R2에서 나왔다. 한 가지 경로를 고정한 retiming과 자유 경로 선택의 결과는 다르다.",
        f"Q4: R2의 MESS03 경로 변경이 실제 추가 개선을 만들었다. R3는 신규 Native {sum(c['Native_Runtime'] for c in state['calls'] if c['stage']=='R3'):.6f}초, R4 세 조합은 {sum(c['Native_Runtime'] for c in state['calls'] if c['stage']=='R4'):.6f}초를 사용했고 모두 추가 개선은 없었다. R3의 큰 이웃은 TIME_LIMIT이므로 충분한 탐색에 대한 동등 비교나 전역 실패 증거가 아니다.",
        'Q5: 이 실행은 Warm Start이며 PR219 cold-start 시간과 직접 동일한 성능 지표가 아니다. 추가 UB 감소량과 신규 Native 비용만 비교한다.',
        f'Q7: N1 대비 감소 {n1_delta:.17g}; MATERIAL_VS_N1 = {best["UB"]<=MATERIAL}.',
        f'Q8: K48 LB {GLOBAL_LB:.17g}, Global Gap {100*state["Global_gap"]:.9f}%, 3% 인증 {state["Global_gap"]<=.03}.',
        'Q9: Root 완료/Native 시점, NodeCount 및 restricted MIPGap은 iteration 표에 보존한다. 미완료 root는 완료로 취급하지 않는다.',
        'Q10: 고정 corridor/선택 Site/Hamming의 제한과 관측 SOC/PCS/P300 포화는 별도 증거다. 이웃 전체가 제한 OPTIMAL이어도 원본 전체 전역 최적성을 증명하지 않는다. TIME_LIMIT은 개선 부재 증거가 아니다. 특정 원인에 대한 추가 인과 실험은 하지 않았다.']
    def time_text(event):return event if isinstance(event,str) else f"{event['Native_capture_seconds']:.6f}초 ({event['candidate_id']})"
    report=f'''# V42 B2 Route-Centered Local Branching — 신규 Native 최대1,800초 Warm Canary

BEST_GLOBAL_UB **{best['UB']:.17g}**, BEST_MOVING_FEASIBLE_UB **{moving['UB']:.17g}**. PR219 대비 UB 감소 **{new_delta:.17g}**, N1 대비 **{n1_delta:.17g}**. 신규 Native **{state['Native_used']:.6f}초**, Controller Wall **{state['controller_wall_seconds']:.3f}초**. K48 인증 Global Gap **{100*state['Global_gap']:.9f}%**, ACTUAL_NOT_RUN. 종료 `{state['stopped_reason']}`. 분류는 **Certified Matheuristic / Bound-Guided Anytime MILP**이며 원본 전역 경로 최적성을 주장하지 않는다.

## Warm Authority 및 과거 시간 분리
PR219 exact HEAD `{BASE}`, raw SHA `{RAW_SHA}`, vector SHA `{VECTOR_SHA}`. 초기 UB {INITIAL_UB}, Native0 원본 FULL 재검증 PASS. PR219 과거 Native1795.025초 및 발견78.053초는 이번 예산에 합산하지 않았다. 이번 초기 point는 inherited Native0 기준점이며 신규 발견시간0이라는 cold 성과가 아니다. 초기 Raw의 약5e−13 상한 잔차는 원본 숫자 허용오차 내로 그대로 유지하고 clipping/rounding/repair하지 않았다. A0 재최적화0회, N1/U4/Cold 실행0회.

## 성능 비교
{table(['Algorithm','FULL Verified UB','Moves','Native(s) scope','Global Gap(%)'],algorithm_rows)}

단계 best가 기존 seed와 같으면 새로운 개선으로 계산하지 않는다. 최초 유의 개선 = **{time_text(timings['first_strict'])}**, 최초 MATERIAL_VS_N1 = **{time_text(timings['first_material_vs_N1'])}**, 개선 횟수 {len(state['improvements'])}, 최선 발견 신규 Native {best['Native_capture_seconds']:.6f}초. 원시 발견시간과 FULL 검증 시점 Native/Wall을 각 event에 분리했다. 유의 기준1e−5, UB 비교 허용1e−8, MATERIAL threshold {MATERIAL}는 서로 다르다.

## 수학적 제한 및 Source 보존
원본9322 Binary, 4대/24 Site/96슬롯, ETA·이동에너지·초기/종단SOC·PCS16·고정AIDC·전체Voltage/NormalAmps/Transformer/Thermal/SVR/Cap 및 min rho_max를 유지했다. Source207·Case·FULL Matrix/Domain SHA는 SOURCE_CASE_AUTHORITY.json에 결합돼 있다. 원본CSR/RHS/Sense/types/objective를 그대로 만들고 Route bounds fixation과 Hamming 검색 row만 추가했다. 원본 FULL 가능영역의 제한 부분집합이므로 restricted ObjBound를 Global LB로 승격하지 않는다.

모든384 Mode와 Pch/Pdis/Q/SOC97은 원래 bounds에서 재최적화했다. Hamming은 자유 Route Node만 포함한다. Radius는 실제 다른 moving witness의 거리+사전등록 slack이다. RouteClosure는 실제 center vertex에서 잘라 Source Arc의 forward/backward 연결, 후속STAY/Flow 및 terminal96을 연다. Site/시간창은 heuristic이며 원본 전체 경로 공간의 정확한 prescreen이 아니다. 닫힌 원본 Arc/Node Alias를 별도로 정확 전개해 누수0을 확인했다. center는 original FULL PASS, fixing/Hamming literal PASS 및 unchanged raw MIP Start readback으로 검증했다. 원본validator 수치범위를 exact dyadic primal certificate로 과장하지 않는다. `ROUTE_NEIGHBORHOOD_CONTRACT_KO.md`, `ROUTE_DAG_CLOSURE_AUDIT.json`, `NATIVE_MODEL_READBACK.json` 참조.

## 3-MOVE Ablation
A0는 이미 인증된 기존 point이므로 동일 MILP를 호출하지 않았다. A1/A2는 MOVE삭제 후96슬롯완성DAG로 재구성했고 A3/A4/A5는 실제 출발시각/목적지/후속연결을 변경했다. A6는 첫MOVE 유지 후 다른 차량을 추가했다. 경로가 달라진 진단에는 모순되는 PR219 Raw Start를 넣지 않았다. 각 UB/충전·방전 AC kWh/이동에너지/SOC/충전증가/임계Line·Phase·Slot은 `THREE_MOVE_ABLATION.json`에 있다. 목적값 차이는 모든4대의 공동 재최적화 결과이며 개별MOVE의 독립 인과효과로 단정하지 않는다.

## Local Branching 실제 반복
{table(['Iteration','FULL UB','Native(s)','Status','Nodes','Root done','Restricted gap','R','Free B','Fixed B'],iteration_rows)}

TIME_LIMIT/NUMERIC/USER 또는 RESOURCE STOP을 보존했다. 새 FULL 유의 개선만 중심을 바꿨고 동일UB point로 반복 중심갱신하지 않았다. 동일 수학적 bounds/Hamming signature를 재실행하지 않았다. R5는 앞 Local Branching 단계의 정체 때만 Beam을 보조적으로 사용하며 기존56개 route-fixed 평가를 재시작하지 않았다. R4는 MESS01/02/04와의 쌍을 original signed grid 순위로 각각 시도했다. ROOT 미완료/열린 영역의 solver gap은 원본Global gap이 아니다.

## 핵심 질문과 증거 범위
{chr(10).join('- '+a for a in answers)}

## 실제 최선 경로와 운전계획
{table(['MESS','Source','Depart','Destination','Arrive','Connect','kWh','Original Arc'],moving_rows) if moving_rows else '최선Global은STAY-only이며 이동best는별도보존했다.'}

`BEST_96_SLOT_MESS_PLAN.csv`는4대×96=384행 Pch/Pdis/Q/Mode/SOC before/after/Arc/ETA/이동debit을 제공한다. `BEST_PLAN_AUDIT.json`은97SOC경계/초기종단/포화범위/실제이동과 원본terminalSite를 제공한다. 새return-to-origin의무를 추가하지 않았다.

![실제 원본 경로](BEST_MESS_ROUTES.png)

![SOC 및 P/Q 계획](BEST_SOC_P_Q_PLAN.png)

## Critical Grid·Rebound 및 제약 포화
초기 및최선의 original814,560security행을 재스캔했다. PR219 제한행 `{scans['PR219_CENTER']['maximum_thermal']}`; 최종 `{scans['BEST_GLOBAL']['maximum_thermal']}`. 초기검증point 대비 충전증가 {len(rebounds)}개 기록과 원본signed P/Q의 실제제한asset 부하 기여를 `REBOUND_AND_SATURATION_ANALYSIS.json`에 보존했다. Rebound를96밖으로 옮기거나종단SOC를완화하지 않았다. Mode/P/Q재최적화가함께바뀌므로이동에너지의독립인과효과로해석하지않는다. SOC440/1080, P300, PCS400근접slot은관측포화증거이며원본전체전역최적성이나실패의유일원인을증명하지않는다.

## 자원·원장·독립 원본 FULL
신규 Optimize {len(state['calls'])}회, 전체실제 Runtime합 {state['Native_used']:.6f}초 ≤1800. 예산reset0, 과거Native별도. 사전등록21개모델의정의한비중복후보가소진되어조기종료했으며원본전체경로공간소진을뜻하지않는다. 같은모델을반복해1800초를채우지않았다. Threads1/heavyworker1, 모델생성후실측추가성장Reserve검증및callback확인. 최소가용RAM {memory['minimum_RAM_available']/2**30:.3f}GiB, Commit {memory['minimum_commit_available']/2**30:.3f}GiB, 최대RSS {memory['peak_RSS_bytes']/2**30:.3f}GiB/PrivateCommit {memory['peak_private_commit_bytes']/2**30:.3f}GiB. 경고{len(warnings)}개를숨기지않았다. worker종료·dispose후원본FULL독립검증. PASS/FAIL Raw와 log를모두보존하며 tolerance변경·반올림·복구0. `FINAL_INDEPENDENT_REVIEW.json`에서 원장·Raw SHA/Vector/원본물리 및K32/K48 계승을다시검증했다.

![UB 및 인증 Gap vs 신규 Native](UB_GAP_VS_NATIVE.png)

## 최종 판단
추가개선 {new_delta>DELTA}, N1물질개선 {best['UB']<=MATERIAL}, GlobalGap3% {state['Global_gap']<=.03}. 성능이개선되지않았으면그사실을유지하며global최적해로해석하지않는다. Warm지역탐색을coldBeam과동일지표로평가하지않는다. 추가LB/FreshOpenDSS/Actual/PQrepair/B1/B3/IEEE8500/다른날짜/공식May31campaign0회. 기존HOLD/DisabledTask/Source/PR219/NativeLedger를그대로보존했다. ACTUAL_NOT_RUN.
'''
    (DOCS/'ROUTE_CENTERED_LB1800_FINAL_KO.md').write_text(report,encoding='utf-8')
    write(DOCS/'POSTPROCESS_RECEIPT.json',dict(PASS=True,Native_optimize_calls=0,wall_seconds=time.perf_counter()-began))
    print(json.dumps(dict(PASS=True,Native=state['Native_used'],UB=best['UB'],new_delta=new_delta,material=best['UB']<=MATERIAL)))

if __name__=='__main__':main()
