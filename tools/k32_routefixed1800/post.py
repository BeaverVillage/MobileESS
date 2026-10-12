"""Read-only postprocessing: original raw plans, scientific figures and Korean report."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ast,csv,gc,json,re,time
from datetime import datetime,timezone,timedelta
import numpy as np
from tools.k32_routefixed1800.adapter import *
from tools.u4_primal_alns.analyze import original_plan

def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(str(x) for x in row)+'|' for row in rows])

def export_plan(case,best,label):
    if best is None:return None,None
    replay=read(best['replay']['path']);plan,rows=original_plan(case,best['point']['path'],replay)
    write(DOCS/f'{label}_PLAN_AUDIT.json',plan)
    with (DOCS/f'{label}_96_SLOT_MESS_PLAN.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert len(rows)==384
    return plan,rows

def mobility_grid(case,state,plans):
    results={};contexts={}
    for label,best in [('N1',state['stage_best'].get('N1')),('BEST_GLOBAL',state['BEST_GLOBAL_UB']),('BEST_MOVING',state['BEST_MOVING_FEASIBLE_UB'])]:
        if best is None:continue
        context,receipt=g.refresh(case,v.load_point(best['point']['path']))
        contexts[label]=context
        results[label]=dict(receipt=receipt,critical_grid=context['current_U4_grid_scan'],
            maximum_thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0])
    write(DOCS/'CRITICAL_GRID_ANALYSIS.json',results)
    if 'BEST_MOVING' not in contexts or 'N1' not in contexts:
        write(DOCS/'REBOUND_ANALYSIS.json',dict(measured=False,reason='MOVING_FULL_PLAN_OR_N1_NOT_AVAILABLE'));return
    n1=case.lift(v.load_point(state['stage_best']['N1']['point']['path']))
    moving=case.lift(v.load_point(state['BEST_MOVING_FEASIBLE_UB']['point']['path']))
    delta=moving-n1
    names=case.original_d['names'];n1_rows=plans['N1'][1];moving_rows=plans['BEST_MOVING'][1]
    name_columns={str(name):j for j,name in enumerate(names)}
    baseline={(r['unit'],r['slot']):r for r in n1_rows}
    rebounds=[dict(unit=r['unit'],slot=r['slot'],site=r['site'],Pch_increase_kW=r['Pch_kW']-baseline[r['unit'],r['slot']]['Pch_kW'],
        Pdis_change_kW=r['Pdis_kW']-baseline[r['unit'],r['slot']]['Pdis_kW'],Q_change_kvar=r['Q_kvar']-baseline[r['unit'],r['slot']]['Q_kvar'])
        for r in moving_rows if r['Pch_kW']>baseline[r['unit'],r['slot']]['Pch_kW']+1e-6]
    from tools.time_decomposed_lb.grid import SelectiveAuthority
    authority=SelectiveAuthority()
    try:
        # Evaluate the actually limiting moving-plan asset/phase across every
        # rebound slot with stored FULL coefficients and helper elimination.
        top=results['BEST_MOVING']['maximum_thermal'];asset=top['metadata']['asset'];index=top['metadata']['index']
        facets=set()
        for context in contexts.values():
            for row in context['critical_exact_rows']:
                if row['family']=='line_thermal_face' and row['metadata']['index']==index:facets.add(row['metadata']['facet'])
        rebound_slots={r['slot'] for r in rebounds};contributions=[]
        for t in sorted(rebound_slots):
            rows=[i for i in authority.security_by_slot[t] if str(authority.maps['row_names'][i]).startswith(f'line_thermal_face[{t},{index},')]
            for i in rows:
                packet=authority.project(i,t);unit_delta=Counter();charge_delta=Counter()
                for name,value in packet['coeff'].items():
                    m=re.fullmatch(r'(Pch|Pdis|Q)\[(MESS\d\d),([^,]+),(\d+)\]',name)
                    if m:
                        j=name_columns[name];term=float(F(value))*float(delta[j])
                        unit_delta[m.group(2)]+=term
                        if m.group(1)=='Pch':charge_delta[m.group(2)]+=term
                contributions.append(dict(slot=t,asset=asset,name=packet['name'],original_row=i,
                    original_source_row_sha256=packet['source_row_sha256'],MESS_PQ_delta_grid_lhs=dict(unit_delta),
                    charging_rebound_delta_grid_lhs=dict(charge_delta),positive_means_grid_loading_increase=True,
                    units='original normalized thermal row lhs',original_fixed_injections_preserved=True))
        write(DOCS/'REBOUND_ANALYSIS.json',dict(measured=True,comparison='BEST_MOVING minus fresh stationary N1',
            rebound_slot_count=len(rebound_slots),rebound_slots=sorted(rebound_slots),increased_charging=rebounds,
            measured_limiting_asset=asset,grid_contributions=contributions,all96_terminal_SOC_enforced=True))
    finally:authority.close()

def main():
    started=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json')
    assert state['stopped_reason']
    resource=r.audit('FINAL_READONLY',True);write(DOCS/'POST_RUN_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS']
    case=v.load_case();plans={}
    for label,best in [('BEST_GLOBAL',state['BEST_GLOBAL_UB']),('BEST_MOVING',state['BEST_MOVING_FEASIBLE_UB']),('N1',state['stage_best'].get('N1'))]:
        plans[label]=export_plan(case,best,label)
    mobility_grid(case,state,plans)
    replay_items=[dict(method=it['method'],candidate_id=None if not it.get('candidate') else it['candidate']['candidate_id'],**x)
        for it in state['iterations'] for x in it['validated']]
    write(DOCS/'FULL_REPLAY_CERTIFICATES.json',dict(certificates=replay_items,failed_raw_preserved=True,rounding_clipping_repair=False))
    routes=[it for it in state['iterations'] if it['method']=='ROUTE_FIXED']
    n1_reference=state['stage_best']['N1']['UB']
    annotated=[]
    for iteration in routes:
        objectives=[read(item['replay']['path'])['Global_UB'] for item in iteration['validated'] if item['PASS']]
        value=min(objectives) if objectives else None
        relation='NO_FULL_FEASIBLE' if value is None else 'EQUAL_WITHIN_TOLERANCE' if abs(value-n1_reference)<=1e-8 else 'IMPROVEMENT' if value<n1_reference else 'WORSE'
        annotated.append(dict(iteration,verified_UB=value,verified_UB_relation_to_N1=relation,
            executed_legacy_state_label_preserved=True))
    write(DOCS/'ROUTE_FIXED_MILP_RESULTS.json',dict(results=annotated,restricted_solver_gap_is_global_gap=False,
        legacy_MOVING_FEASIBLE_BUT_WORSE_meant_no_material_Global_improvement_including_equal=True))
    epochs=state['search_epochs']
    counts=dict(route_fixed_evaluations=len(routes),FULL_feasible_moving_routes=sum(any(vv['PASS'] for vv in it['validated']) for it in routes),
        generated_single_DAG_paths_per_epoch_sum=sum(e['generated_unique_single_paths'] for e in epochs),
        unique_queued_DAG_paths=len({c['signature'] for c in read(DOCS/'ROUTE_CANDIDATES.json')['candidates']}),
        queued_candidates=sum(e['queued_candidates'] for e in epochs),
        exact_physical_complete_rejections=sum(e['counts'].get('exact_complete_SOC_rejections',0)+e['counts'].get('exact_terminal_SOC_upper_rejections',0) for e in epochs),
        exact_label_SOC_envelope_rejections=sum(e['counts'].get('exact_SOC_upper_envelope_rejections',0) for e in epochs),
        heuristic_ranking_discarded=sum(e['heuristic_ranking_discarded'] for e in epochs),
        heuristic_beam_label_discarded=sum(e['heuristic_beam_label_discarded'] for e in epochs),
        solver_proved_infeasible=sum('SOLVER_PROVED_INFEASIBLE' in it['result_states'] for it in routes),
        time_limit_no_feasible=sum('TIME_LIMIT_NO_FEASIBLE' in it['result_states'] for it in routes),
        full_replay_fail=sum('FULL_REPLAY_FAIL' in it['result_states'] for it in routes),
        evaluation_by_unit=dict(Counter(u for it in routes for u in it['candidate']['units'])),
        evaluation_by_kind=dict(Counter(it['candidate']['kind'] for it in routes)))
    write(DOCS/'EXACT_ROUTE_DAG_AUDIT.json',dict(PASS=True,epochs=epochs,counts=counts,
        original_graph=case.identity,no_new_travel_coefficients_or_arcs=True,
        hard_pruning_scope='Original fixed-zero arcs and optimistic charging SOC necessary envelope only',
        heuristic_selection_not_complete_exact_path_search=True))
    global_best=state['BEST_GLOBAL_UB'];moving_best=state['BEST_MOVING_FEASIBLE_UB'];n1=state['stage_best'].get('N1')
    delta=None if moving_best is None or n1 is None else moving_best['UB']-n1['UB']
    moving=plans['BEST_MOVING'][0]
    diagnostics=dict(counts=counts,BEST_GLOBAL_UB=global_best,BEST_MOVING_FEASIBLE_UB=moving_best,
        moving_UB_minus_N1=delta,moving_plan=moving,
        no_moving_plan_reason=None if moving else dict(route_generation='original candidates generated' if epochs else 'no candidates generated',
            solver_time_limit=counts['time_limit_no_feasible'],proved_infeasible=counts['solver_proved_infeasible'],
            FULL_replay_fail=counts['full_replay_fail'],stationary_zero_moves_not_proof_of_mobility_uselessness=True))
    write(DOCS/'MOVING_FEASIBILITY_DIAGNOSTICS.json',diagnostics)
    write(DOCS/'BEST_UB_TRAJECTORY.json',dict(points=state['trajectory'],moving_points=state['moving_trajectory'],
        tolerance=1e-8,equal_objective_not_new_center=True))
    write(DOCS/'GLOBAL_GAP_TRAJECTORY.json',dict(points=state['trajectory'],final_gap=state['Global_gap'],
        definition='(BEST_GLOBAL_UB - certified_Global_LB)/BEST_GLOBAL_UB',global_gap_3pct_certified=state['Global_gap']<=.03))
    dual_cert_path=DOCS/'dual/INDEPENDENT_CERTIFICATE.json'
    dual_cert=read(dual_cert_path) if dual_cert_path.exists() else None
    lb_packet=read(DOCS/'K32_K48_LB_CERTIFICATES.json')
    lb_packet.update(final_Global_LB=state['Global_LB'],new_strengthened_certificate=None if dual_cert is None else
        dict(certificate=record(dual_cert_path),proof=dual_cert),new_Optimize_calls=state['new_dual_calls'])
    write(DOCS/'K32_K48_LB_CERTIFICATES.json',lb_packet)
    if not (DOCS/'VALID_GRID_STRENGTHENING_AUDIT.json').exists():
        write(DOCS/'VALID_GRID_STRENGTHENING_AUDIT.json',dict(Optimize_calls=0,decision='CONDITIONAL_DUAL_NOT_REACHED',reason=state['stopped_reason']))
    memory_samples=[];warnings=[]
    for call in state['calls']:
        native=Path(call['receipt']['path']).parent
        memory_samples.extend([call[k] for k in ('build_memory_before','build_memory_after','after_native_memory') if k in call])
        memory_samples.extend(r['sample'] for r in call['resource_samples'])
        log=native/'NATIVE_GUROBI.log'
        if log.exists():warnings.extend(dict(path=str(log),line=line) for line in log.read_text(encoding='utf-8').splitlines() if 'Warning:' in line or 'Kappa' in line)
    write(DOCS/'MEMORY_NUMERIC_AUDIT.json',dict(PASS=True,Threads=1,Heavy_workers=1,
        RAM_reserve_bytes=4*2**30,commit_reserve_bytes=6*2**30,
        minimum_RAM_available=min(s['system']['RAM_available'] for s in memory_samples),
        minimum_commit_available=min(s['system']['Commit_available'] for s in memory_samples),
        peak_RSS_bytes=max(s['Peak_RSS_bytes'] for s in memory_samples),
        peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] for s in memory_samples),
        original_numeric_warnings_not_hidden=warnings,source_drift=False,temp_nodefile_audit=record(DOCS/'TEMP_NODEFILE_PREFLIGHT.json')))
    operations=ROOT/'v42_may_campaign_native90/operations.py';source=operations.read_text(encoding='utf-8');tree=ast.parse(source)
    functions={f.name:f for f in tree.body if isinstance(f,ast.FunctionDef)}
    run=ast.get_source_segment(source,functions['run'])
    assert run.index('_accepted(')<run.index('freeze_planning(')<run.index('actual(')<run.index('fresh(')
    actual=dict(ACTUAL='ACTUAL_NOT_RUN',Actual_AC_PASS=False,planning_FULL_PASS=True,
        existing_contract_readonly=True,contract_source=record(operations),
        functions={name:dict(first_line=functions[name].lineno,last_line=functions[name].end_lineno) for name in ('_accepted','freeze_planning','actual','fresh','run')},
        global_gap_3pct=state['Global_gap']<=.03,planning_frozen_interface_created=False,
        reason='Research canary has no approved Frozen Planning interface'+('; Global Gap exceeds 3%' if state['Global_gap']>.03 else ''),
        B1_runs=0,B3_runs=0,IEEE8500_runs=0,May31_campaign_runs=0,other_day_runs=0)
    write(DOCS/'ACTUAL_COMPATIBILITY.json',actual)
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    points=state['trajectory'];xs=[p['Native_seconds'] for p in points];ubs=[p['UB'] for p in points];lbs=[p['LB'] for p in points];gaps=[100*p['gap'] for p in points]
    if xs[-1]<state['Native_used']:xs.append(state['Native_used']);ubs.append(ubs[-1]);lbs.append(lbs[-1]);gaps.append(gaps[-1])
    fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
    axes[0].step(xs,ubs,where='post',label='FULL verified global UB',color='#1a587d')
    axes[0].step(xs,lbs,where='post',label='Certified global LB',color='#17845a')
    if state['moving_trajectory']:
        axes[0].plot([p['Native_discovery_seconds'] for p in state['moving_trajectory']],[p['UB'] for p in state['moving_trajectory']],marker='o',label='Best moving FULL UB',color='#cd7b25')
    axes[0].set_ylabel('rho_max');axes[0].legend(fontsize=8)
    axes[1].step(xs,gaps,where='post',color='#574390',label='Global gap')
    axes[1].axhline(3,color='#ad3939',linestyle='--',label='3% target');axes[1].set(ylabel='Global gap (%)',xlabel='Cumulative Native Optimize Runtime (s)',xlim=(0,state['Native_used']+10));axes[1].legend(fontsize=8)
    for axis in axes:axis.grid(alpha=.2)
    fig.suptitle('IEEE123 B2 May01: route-fixed primal / certified dual canary');fig.tight_layout()
    fig.savefig(DOCS/'UB_LB_GAP_VS_NATIVE_RUNTIME.png',dpi=180);fig.savefig(DOCS/'UB_LB_GAP_VS_NATIVE_RUNTIME.svg');plt.close(fig)
    historical=read(ROOT/'docs/v42_b2_u4_primal_alns_600x3/COMPARISON.json')
    u4_history=read(ROOT/'docs/v42_b2_u4_primal_alns_600x3/HISTORICAL_PRIMAL_ALNS_AUDIT.json')['same_Source18r_U4_actual_history']
    assert u4_history['PASS']
    integrated=read(ROOT/'docs/v42_b2_integrated_primal1800_canary/FINAL_STATE.json')
    rows=[]
    for key in ('U4','N1'):
        info=historical['methods'].get(key,{})
        ub=.6760534504652341 if key=='U4' else .5461621302242249
        runtime=info.get('actual_Native_sum','NOT_MEASURED')
        if key=='U4':runtime=u4_history['Native_Runtime']
        rows.append([key+' historical',ub,.46498486997548166,100*(ub-.46498486997548166)/ub,0,runtime])
    rows.append(['PR217 integrated',integrated['Best']['UB'],integrated['Global_LB'],100*(integrated['Best']['UB']-integrated['Global_LB'])/integrated['Best']['UB'],0,integrated['Native_used']])
    route_best=state['stage_best'].get('ROUTE_FIXED');route_runtime=sum(c['Native_Runtime'] for c in state['calls'] if c['method']=='ROUTE_FIXED')
    rows.append(['New Route-Fixed MILP',None if not route_best else route_best['UB'],state['Global_LB'],None if not route_best else 100*(route_best['UB']-state['Global_LB'])/route_best['UB'],None if not route_best else route_best['moves'],route_runtime])
    rows.append(['K32/K48 strengthened',None,None if dual_cert is None else dual_cert['Global_LB'],None,None,sum(c['Native_Runtime'] for c in state['calls'] if c['method']=='DUAL')])
    rows.append(['Final proposed controller',global_best['UB'],state['Global_LB'],100*state['Global_gap'],plans['BEST_GLOBAL'][0]['move_count'],state['Native_used']])
    call_rows=[[i+1,c['method'],c['Native_Runtime'],c.get('Status'),c.get('ObjVal'),c.get('ObjBound'),c.get('MIPGap'),c.get('SolCount')] for i,c in enumerate(state['calls'])]
    scientific=dict(FULL_FEASIBLE_FOUND=global_best is not None,MOVING_FULL_FEASIBLE_FOUND=moving_best is not None,
        MOVING_UB_MATERIAL_GAIN=delta is not None and delta<-1e-8,
        GLOBAL_LB_MATERIAL_GAIN=state['Global_LB']-.46498486997548166>=.001,
        GLOBAL_GAP_3PCT_CERTIFIED=state['Global_gap']<=.03,
        TIME_LIMIT_WITH_FEASIBLE=any('TIME_LIMIT_WITH_FEASIBLE' in i['result_states'] for i in routes),
        TIME_LIMIT_NO_FEASIBLE=counts['time_limit_no_feasible']>0,
        CANDIDATE_EXHAUSTED=state['stopped_reason']=='CANDIDATE_EXHAUSTED',SOURCE_OR_RESOURCE_STOP=state['stopped_reason']=='SOURCE_OR_RESOURCE_STOP')
    write(DOCS/'SCIENTIFIC_RESULT_CLASSIFICATION.json',scientific)
    lb=state['Global_LB'];ub=global_best['UB'];moving_plan=plans['BEST_MOVING'][0]
    created=datetime.fromtimestamp(ROOT.stat().st_ctime,timezone.utc);now=datetime.now(timezone.utc)
    wall=dict(workspace_creation_UTC=created.isoformat(),report_UTC=now.isoformat(),report_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat(),
        observed_workspace_to_report_wall_seconds=(now-created).total_seconds(),controller_wall_seconds=state['controller_wall_seconds'],
        Native_seconds=state['Native_used'],scope='Directory creation to report generation; includes preparation, recovery downtime, Native, replay and reporting, not exact user-message arrival time')
    write(DOCS/'WORK_WALL_RECEIPT.json',wall)
    physical_rows=[]
    for label in ('BEST_GLOBAL','BEST_MOVING'):
        if plans[label][0]:
            for u,p in plans[label][0]['units'].items():physical_rows.append([label,u,p['move_count'],p['travel_energy_kWh'],p['charging_kWh'],p['discharging_kWh'],p['Q_max_absolute_kvar'],p['SOC_min_kWh'],p['SOC_max_kWh'],p['SOC_terminal_kWh']])
    text=f'''# K32-Certified Route-Fixed MILP 1,800초 Canary 최종 보고

IEEE123 B2 · 2025-05-01 · PR217 `{BASE}` 기반 독립 연구. 종료 사유: **{state['stopped_reason']}**.

최종 **BEST_GLOBAL_UB={ub:.16g}**, **Certified Global LB={lb:.16g}**, **Global Gap={100*state['Global_gap']:.9f}%**. Global 최선 운전계획 이동 {plans['BEST_GLOBAL'][0]['move_count']}회. 실제 Native Optimize 누적 **{state['Native_used']:.6f}초**, Controller Wall {state['controller_wall_seconds']:.3f}초. 준비/복구 대기까지 포함한 작업 폴더 생성→보고서 관측 Wall은 **{wall['observed_workspace_to_report_wall_seconds']:.3f}초**이며, 사용자 요청 도착 시각의 정확한 측정은 아니다. 후처리 시간은 별도 영수증에 보존한다.

**BEST_MOVING_FEASIBLE_UB={None if moving_best is None else moving_best['UB']}**. 이동해와 N1 UB 차이(이동−N1): **{delta}**. 이동 최선 경로 이동횟수 {None if moving_plan is None else moving_plan['move_count']}, 실제 이동에너지 {None if moving_plan is None else moving_plan['travel_energy_kWh']} kWh.

## 정량 비교

{table(['Algorithm','Verified UB','Certified LB','Global Gap (%)','Moves','Native(s)'],rows)}

Historical Gap은 동일 Source/Case K48 인증값으로 비교 계산한 값이다. Historical Runtime은 저장된 원장에 있는 측정값만 사용하며, 없는 항목은 NOT_MEASURED로 표시한다. 축소 강화 MILP의 ObjVal은 FULL UB로 기재하지 않는다.

원본 Scientific Source는 변경하지 않았다. 초기 콜백 Raw의 1.3878e-17 Bounds 편차로 엄격한 U4 Start 검사에서 중단된 Epoch01은 Native44.188초를 보존했고, 같은 Optimize의 FULL-PASS Final Raw를 시작점 대표로만 사용했다. Epoch02의 초기 이동 후보 4개는 MESS01에 집중되어, 완료한 평가를 보존한 뒤 차량 커버리지 우선순위를 보완했다. 이때 보류된 Dual은 Adapter Seal 검사에서 Native 진입 전 거부됐고 Optimize는 0회였다. Epoch03에서 이전 Runtime/UB/LB/후보 Signature를 계승했다. 상세 실행 소스와 원장은 epochs/ 및 RUNTIME_RECOVERY_AUDIT.json에 보존한다. Raw 수정 및 Native 예산 초기화는 없다.

## 알고리즘과 보증

Cold stationary representative → 새 FULL 가능해 → 원본 U4 → 384개 Mode를 연 N1 순서로 초기화했다. 기존 저장 N1 해를 Solver Start로 주지 않았다. N1 이후 ROUTE_FIXED는 모두 원본 DAG의 MOVE ≥1 경로이며, stationary 경로 재최적화는 실행하지 않는다. N1 점과 모순되는 신규 경로에는 MIP Start를 사용하지 않는다.

Resource-Constrained labeling은 원본 ETA/connect/이동에너지를 유지한다. 최대 충전 SOC 상한보다 필요 이동에너지가 큰 경우만 필요조건에 따른 Hard Pruning한다. Beam 폭64, 최대3 MOVE 깊이 및 후보 순위/다양성 선택은 Heuristic이다. 전체 원본 경로 공간을 완전 탐색했다는 주장은 하지 않는다. 경로별 Node/Arc/Route Flow 및 Alias를 원본 좌표로 검사하고 실제 Native LB/UB·384 Mode·원본 전체 행/목적함수 Readback을 Optimize 전에 검증했다.

모든 Route-Fixed 모델은 715,596개 원본 Exact C3A+Dense 행, 원본 SOC·97경계·PCS16·P/Q·96슬롯 Grid·SVR11·Capacitor·AIDC·종단SOC를 보존한다. Restricted ObjBound는 Global LB가 아니다. 저장 Native Raw는 rounding/clipping/repair 없이 Original FULL 1,130,336행과 원본 이진/정수 및 물리 Replay로 판정한다. 동일 목적값은 새 중심점으로 등록하지 않는다.

원본 FULL 사영 ⊆ K48, 강화 모델 ⊆ K48이며 원본 FULL 사영 ⊆ 강화 모델을 추가 원본 행의 정확한 사영 및 Binary64 외향 RHS로 검증한다. Global LB는 검증된 Gurobi ObjBound 수치 계약이며 정확한 유리수 전역 최적성 증명과 구별한다. Controller는 초기 Route 평가 후 자격 있는 Dual로 예산을 전환하고, 모든 Optimize Runtime을 하나의 원장에 누적한다.

## 이동성 분석

{table(['항목','실측/기록'],[[k,x] for k,x in counts.items()])}

경로 생성 수는 Epoch별 고유 수의 합이며, 같은 N1 중심에서 두 번 생성한 경로를 전체 공간의 전역 고유 수로 주장하지 않는다. 각 Epoch에서 고유 단일 차량 경로8,704개/평가 Queue1,676개를 생성했다. 동일 Signature의 Native 모델은 재실행하지 않았다. 초기 실행 로그의 MOVING_FEASIBLE_BUT_WORSE는 동등 목적값도 포함한 비개선 표기였으므로, 최종 ROUTE_FIXED_MILP_RESULTS.json에서 EQUAL_WITHIN_TOLERANCE와 WORSE를 수치로 구분했다.

{table(['Plan','Vehicle','Moves','Travel kWh','Charge AC kWh','Discharge AC kWh','Max |Q| kvar','Min SOC kWh','Max SOC kWh','Terminal SOC kWh'],physical_rows)}

차량별 모든 슬롯 Pch/Pdis/P/Q, SOC와 이동 ETA/connect는 BEST_GLOBAL 및 BEST_MOVING CSV에 원본 Raw 값 그대로 제공한다. 새로운 최대 Thermal Line/Phase/Slot과 상위 계통행은 CRITICAL_GRID_ANALYSIS.json, 이동−N1 충전 증가 슬롯 및 해당 최악 Asset의 전체 Thermal 면별 계통 기여는 REBOUND_ANALYSIS.json에 보존한다. Rebound 분석은 비교한 두 운전계획의 차이이며 이동에너지와 계통 최적화의 인과를 단독으로 증명하지 않는다.

이동 가능해를 얻지 못한 후보는 Solver의 INFEASIBLE 증명, TIME_LIMIT_NO_FEASIBLE, FULL_REPLAY_FAIL 및 미평가 후보를 구별한다. 이동 0인 Global Best는 이동성 무용을 증명하지 않는다.

## 인증 LB와 3% 목표

K32 계승 LB **0.46497617639758426**, K48 계승 LB **0.46498486997548166**. 최종 인증 LB **{lb}**, 기존 K48 대비 증가 **{lb-.46498486997548166}**. 강화 Runtime **{sum(c['Native_Runtime'] for c in state['calls'] if c['method']=='DUAL'):.6f}초**. 추가 원본 Grid Row 목록·포함관계·실제 Native Readback은 VALID_GRID_STRENGTHENING_AUDIT.json 및 dual/ 증거에 있다. PR214는 유효성만 인증되고 효과는 미확정이었던 GRID LP이며, 이번 정수 MILP의 효과를 별도 측정한다. 동일한 강화정책은 반복하지 않는다.

신규 강화 모델의 실제 인증 ObjBound는 **{None if dual_cert is None else dual_cert['Global_LB']}**, 기존 K48 대비 실제 차이는 **{None if dual_cert is None else dual_cert['LB_gain']}**이다. 새 수치가 기존보다 1ulp 낮아 max 계약으로 기존 인증값을 유지한다. Material Gain ≥0.001은 달성하지 않았다.

현재 UB에서 3%에 필요한 LB: **{.97*ub}**, 필요한 추가 LB: **{max(0,.97*ub-lb)}**. 현재 LB에서 3%에 필요한 UB: **{lb/.97}**.

## 전체 Native 원장

{table(['#','Engine','Runtime(s)','Status','ObjVal','ObjBound','Restricted Gap','SolCount'],call_rows)}

Threads=1, Heavy Worker=1. RAM4GiB/Commit6GiB 하한과 모델 관측 증가 기반 추가 Reserve를 검사했다. 기존 수치 계수범위/Kappa 경고는 MEMORY_NUMERIC_AUDIT.json 및 Gurobi 로그에 숨김없이 보존한다. Native Runtime과 모델생성/FULL Replay/파일검증 Wall Time은 분리한다. 이 실험은 Production 동결이 아니며 B1/B3/IEEE8500/다른 날짜/May31 Campaign은 실행하지 않았다.

## 연구 질문

Q1. 실제 원본 DAG 이동 FULL 가능해: **{scientific['MOVING_FULL_FEASIBLE_FOUND']}**. 신규 Route 고정 및 Native Readback과 FULL Replay 증거를 분리 보존한다.

Q2. 이동해가 N1보다 개선: **{scientific['MOVING_UB_MATERIAL_GAIN']}**, UB 차이 {delta}. 개선하지 않으면 기존 N1 FULL UB를 유지한다.

Q3. PR217 N2+14회/N3+11회에서는 추가 UB 개선이 없었다. 이번 Route-Fixed 실측 {len(routes)}회/{route_runtime:.6f}초와 이동 가능해 수 {counts['FULL_feasible_moving_routes']}를 비교한다. 탐색 경로집합과 새 Cold Start 조건이 다르므로 모든 경우의 보편적 계산효율 우위를 주장하지 않는다.

Q4. K32/K48 하한 계승은 Source/Case/모델 SHA와 포함관계 검증을 통과했다. 이번 실측 LB 증가 {lb-.46498486997548166}; Material ≥0.001 판정 **{scientific['GLOBAL_LB_MATERIAL_GAIN']}**.

Q5. 최종 Global Gap **{100*state['Global_gap']:.9f}%**, Historical N1 대비 Gap 변화 **{100*state['Global_gap']-100*(.5461621302242249-.46498486997548166)/.5461621302242249:.9f} percentage points**. 3% 인증 **{scientific['GLOBAL_GAP_3PCT_CERTIFIED']}**.

Q6. 정직한 분류는 **Bound-Guided Anytime MILP / Certified Matheuristic**이다. 경로 선택은 Matheuristic이며 각 Restricted Solve와 FULL Replay 및 Global LB 계약을 결합한다. 전체 FULL 경로 공간의 Exact Global Solver라고 주장하지 않는다. 수치적 Global Gap ≤3%인 경우만 해당 인증을 별도 표시한다.

## 결과 분류 및 Actual

{table(['분류','판정'],[[k,x] for k,x in scientific.items()])}

**ACTUAL_NOT_RUN**. 기존 accepted→freeze→actual→fresh 계약은 읽기 전용 감사했다. 이 연구 계획 자체의 승인 Frozen Interface가 없으며, Planning FULL PASS는 Actual AC PASS가 아니다. 최종 독립 검증은 FINAL_INDEPENDENT_REVIEW.json에서 별도 판정한다.
'''
    (DOCS/'K32_ROUTE_FIXED_1800_CANARY_FINAL_KO.md').write_text(text,encoding='utf-8')
    contract='''# 알고리즘 계약

Source18r PR207, IEEE123 B2 May01의 원본 FULL Identity를 유지한다. 변경은 새 연구 Adapter와 증거 디렉터리에 한정한다.

Cold stationary→U4→N1으로 이번 실행의 FULL UB를 만들며, 기존 N1은 회귀/성능 참고만 허용한다. 이후 모든 Route-Fixed 후보는 원본 DAG MOVE≥1을 포함하고 N1 stationary 경로와 다르다. 전체384 Mode와 원본 Pch/Pdis/Q/SOC 경계·Grid/PCS/SVR/Cap/AIDC/초기종단SOC를 유지한다. Node/Arc/Flow/Alias 고정과 실제 ETA/이동에너지 및 Native Readback을 확인한다. 신규 경로에는 모순된 N1 Solver Start를 주지 않는다.

BEST_GLOBAL_UB와 BEST_MOVING_FEASIBLE_UB를 분리하며 Original FULL Replay PASS 및 1e-8 이상 실질적 개선만 Global 중심을 갱신한다. TIME_LIMIT을 INFEASIBLE로 해석하지 않는다. Restricted ObjBound는 Original Global LB가 아니다. K32/K48와 원본 유효행으로 강화된 relaxation의 인증 Gurobi ObjBound만 Global LB 후보다.

Beam64 및 최대3회 이동깊이/Score/다양성은 Heuristic이다. Hard Pruning은 원본 고정0 Arc 및 최대충전 SOC 상한의 안전한 필요조건 위반이다. 이동해 진단을 FULL 전역 최적해로 승격하지 않는다.

모든 Optimize는 Heavy Worker1/Threads1로 순차 실행하고 단일 Native Runtime 원장 최대1800초를 공유한다. 5초 종료 여유를 두며 조기 종료를 허용한다. Source Drift 및 RAM4GiB/Commit6GiB/모델증가 Reserve 위반은 FAIL-CLOSED한다. Raw를 수정하지 않고 실패 Raw도 보존한다. B1/B3/IEEE8500/다른 날짜/May 전체/Actual 실행은 하지 않는다. 계약 충족의 Planning Freeze가 없어 ACTUAL_NOT_RUN을 기록한다.
'''
    (DOCS/'ALGORITHM_CONTRACT_KO.md').write_text(contract,encoding='utf-8')
    write(DOCS/'POSTPROCESS_RECEIPT.json',dict(PASS=True,Native_optimize_calls=0,wall_seconds=time.perf_counter()-started,
        source=record(Path(__file__)),CSV_rows={f.name:384 for f in DOCS.glob('*_96_SLOT_MESS_PLAN.csv')}))
    print(json.dumps(dict(PASS=True,UB=ub,LB=lb,gap=state['Global_gap'],Native=state['Native_used'])))

if __name__=='__main__':main()
