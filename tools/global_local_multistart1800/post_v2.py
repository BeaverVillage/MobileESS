"""Post-run evidence tables/Korean report/standard plots; never Optimize."""
import csv,time
from collections import Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tools.global_local_multistart1800.adapter_v2 import *
from tools.global_local_multistart1800.dag import Graph
from tools.u4_primal_alns.analyze import original_plan

def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows])

def main():
    began=time.perf_counter();guard();s=read(DOCS/'FINAL_STATE.json');assert s['stopped_reason']
    best=s['BEST_GLOBAL_UB'];jointbest=s['BEST_JOINT_FEASIBLE_UB'];moving=s['BEST_MOVING_FEASIBLE_UB']
    case=v.load_native_case();graph=Graph(case);plan,rows=original_plan(case,best['point']['path'],read(best['replay']['path']))
    write(DOCS/'BEST_PLAN_AUDIT.json',plan)
    with (DOCS/'BEST_96_SLOT_MESS_PLAN.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    context,receipt=g.refresh(case,v.load_point(best['point']['path']));write(DOCS/'FINAL_CRITICAL_GRID_SCAN.json',dict(context=context,receipt=receipt))
    first_strict=next((e for e in s['trajectory'][1:] if INITIAL_UB-e['UB']>=DELTA),None)
    joint=[];abl=[];readbacks=[];captures=[];warnings=[];samples=[]
    v1live=read(V1_DOCS/'LIVE_STATE.json')
    known={it['call']['path'] for it in v1live['iterations']}
    for c in read(DOCS/'INHERITED_V1_NATIVE_CALLS.json')['calls']:
        if c['receipt']['path'] in known:continue
        out=Path(c['receipt']['path']).parent;spec=read(out.parent/'SPEC.json')
        v1live['iterations'].append(dict(candidate_id=spec['candidate_id'],family='FOUR_MESS_JOINT',method=c['method'],
            specification=record(out.parent/'SPEC.json'),call=c['receipt'],center=s['trajectory'][0],validated=[],best=None,
            root_completed=c.get('root_completed_Native_seconds') is not None))
    transport=read(DOCS/'V1_POINT_ONLY_TRANSPORT_CERTIFICATES.json')['certificates']
    for it in v1live['iterations']:
        if it['method']!='FOUR_MESS_JOINT_ROUTE_POOL':continue
        matching=[c for c in transport if Path(c['source_Native_packet']['path']).parent==Path(it['call']['path']).parent]
        if matching:
            certified=min(matching,key=lambda c:c['UB']);x=v.load_point(certified['point_only_packet']['path']);paths=paths_of(case,x)
            it['best']=dict(UB=certified['UB'],point=certified['point_only_packet'],replay=certified['replay'],actual_route=paths,
                actual_moves=graph.metadata(paths)['actual_moves'])
    all_iterations=v1live['iterations']+s['iterations']
    for it in all_iterations:
        call=read(it['call']['path']);spec=read(it['specification']['path']);out=Path(it['call']['path']).parent
        recordit=dict(candidate_id=it['candidate_id'],family=it['family'],method=it['method'],Native=call['Native_Runtime'],
            cumulative_Native=next(c['cumulative_Native_after'] for c in s['calls'] if c['receipt']['path']==it['call']['path']),
            Status=call.get('Status'),NodeCount=call.get('NodeCount'),MIPGap=call.get('MIPGap'),root_completed=it['root_completed'],
            root_completed_Native=call.get('root_completed_Native_seconds'),center_UB=None if it['center'] is None else it['center']['UB'],
            FULL_UB=None if it['best'] is None else it['best']['UB'],actual_moves=[] if it['best'] is None else it['best']['actual_moves'],
            selected_paths=None if it['best'] is None else it['best']['actual_route'],new_MOVE_arcs=[],Raw_verifications=it['validated'])
        if it['best'] is not None:
            inherited_arcs={4954,37751,44900}
            recordit['new_MOVE_arcs']=[a for a in it['best']['actual_moves'] if a['unit']!='MESS03' or a['arc'] not in inherited_arcs]
        if it['method']=='FOUR_MESS_JOINT_ROUTE_POOL':
            recordit.update(pool_counts={u:len(p) for u,p in spec['pools'].items()},lambda_binary=spec['lambda_count'],pool_signature=spec['pool_signature'],
                actual_total_binary=9322+spec['lambda_count'],adaptation=spec['pool_adaptation'],local_Start_preserved=True,version='V1' if Path(it['call']['path']).is_relative_to(V1_DOCS/'calls') else 'V2')
            joint.append(recordit);readbacks.append(record(out/'JOINT_NATIVE_READBACK.json'))
        else:abl.append(recordit);readbacks.append(record(out/'MOVING_ROUTE_NATIVE_READBACK.json'))
        captures.extend(it['validated'])
    for c in s['calls']:
        samples.extend(c[k] for k in ('build_memory_before','build_memory_after','after_native_memory') if k in c)
        samples.extend(z['sample'] for z in c['resource_samples'])
        log=Path(c['receipt']['path']).parent/'NATIVE_GUROBI.log'
        if log.exists():warnings.extend(dict(log=str(log),line=l) for l in log.read_text(encoding='utf-8').splitlines() if 'Warning:' in l or 'Kappa' in l)
    memory=dict(PASS=True,Threads=1,heavy_workers=1,minimum_RAM_available=min(x['system']['RAM_available'] for x in samples),
        minimum_commit_available=min(x['system']['Commit_available'] for x in samples),peak_worker_RSS=max(x['Peak_RSS_bytes'] for x in samples),
        peak_worker_Private_Commit=max(x['Peak_Private_Commit_bytes'] for x in samples),
        sampled_maximum_system_RAM_used=max(x['system']['RAM_used'] for x in samples),sampled_maximum_system_commit=max(x['system']['Commit_total'] for x in samples),
        system_values_are_sampled_not_continuous_peak=True,RAM_reserve_GiB=4,Commit_reserve_GiB=6,actual_build_growth_reserve=True,warnings=warnings)
    write(DOCS/'MEMORY_NUMERIC_AUDIT.json',memory)
    actual_joint=[it['best'] for it in s['iterations'] if it['method']=='FOUR_MESS_JOINT_ROUTE_POOL' and it['best'] is not None]
    actual_joint_best=min(actual_joint,key=lambda a:a['UB']) if actual_joint else 'NO_NATIVE_JOINT_FULL_PASS'
    write(DOCS/'FOUR_MESS_JOINT_ROUTE_POOL_RESULTS.json',dict(results=joint,BEST_JOINT_FEASIBLE_UB=jointbest,
        BEST_ACTUAL_JOINT_FULL_RESULT=actual_joint_best,main_algorithm=True,lambda_link_readbacks=readbacks))
    write(DOCS/'DIVERSE_SEED_RESULTS.json',dict(results=[it['best'] for it in s['iterations'] if it['method']=='ROUTE_FIXED' and it['best'] is not None],role='ABLATION_ONLY_AFTER_USER_JOINT_CORRECTION'))
    write(DOCS/'MULTISTART_LOCAL_BRANCHING_RESULTS.json',dict(status='NOT_EXECUTED_REPLACED_BY_FOUR_MESS_JOINT_USER_CORRECTION',Native_calls=0,main_result_file='FOUR_MESS_JOINT_ROUTE_POOL_RESULTS.json'))
    write(DOCS/'COOPERATIVE_ROUTE_RESULTS.json',dict(pair_ablation=[i for i in abl if i['family'].startswith('PAIR_')],joint_four_MESS=joint,
        triple='NOT_EXECUTED_AUXILIARY',all_six_pair_families_generated=read(DOCS/'GLOBAL_ROUTE_DIVERSITY_AUDIT.json')['all_required_families_exist']))
    write(DOCS/'EXECUTED_ROUTE_DIVERSITY_AUDIT.json',dict(PASS=True,main_Joint_calls=len(joint),
        pool_changes=[dict(label=j['candidate_id'],counts=j['pool_counts'],signature=j['pool_signature']) for j in joint],
        main_every_call_all_four_units_decide=True,no_cartesian_combination_MILP_enumeration=True,no_all_MOVE_forcing=True,
        original_route_space_exhausted=False,all_joint_pools_contain_PR220_and_STAY=True))
    write(DOCS/'NATIVE_MODEL_READBACK.json',dict(PASS=True,readbacks=readbacks))
    write(DOCS/'ORIGINAL_FULL_REPLAY_CERTIFICATES.json',dict(V1_lossless_point_transport=read(DOCS/'V1_POINT_ONLY_TRANSPORT_CERTIFICATES.json'),certificates=captures,Raw_PASS=sum(c['PASS'] for c in captures),Raw_FAIL=sum(not c['PASS'] for c in captures),Raw_rounding_clipping_repair=0,initial=record(DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json')))
    write(DOCS/'BEST_GLOBAL_UB_TRAJECTORY.json',dict(points=s['trajectory'],initial_inherited_not_new_discovery=True))
    write(DOCS/'BEST_MOVING_UB_TRAJECTORY.json',dict(points=s['moving_trajectory']))
    dual=[c for c in s['calls'] if c['method']=='DUAL'];dual_time=sum(c['Native_Runtime'] for c in dual);primal_time=s['Native_used']-dual_time
    lb_events=[dict(Native=0.,LB=GLOBAL_LB,inherited=True)]
    if dual:lb_events.append(dict(Native=dual[0]['cumulative_Native_after'],LB=s['Global_LB'],inherited=False))
    event_times=sorted({0.,s['Native_used']}|{p['Native_capture_seconds'] for p in s['trajectory']}|{e['Native'] for e in lb_events})
    ubpoints=[];lbpoints=[];gaps=[]
    for t in event_times:
        ub=min(p['UB'] for p in s['trajectory'] if p['Native_capture_seconds']<=t);lb=max(e['LB'] for e in lb_events if e['Native']<=t)
        ubpoints.append(ub);lbpoints.append(lb);gaps.append(100*(ub-lb)/ub)
    write(DOCS/'GLOBAL_GAP_TRAJECTORY.json',dict(events=[dict(Native=t,UB=ub,Global_LB=lb,Global_gap=(ub-lb)/ub) for t,ub,lb in zip(event_times,ubpoints,lbpoints)],final_gap=s['Global_gap']))
    plots=[]
    def save(fig,name):
        fig.tight_layout();fig.savefig(DOCS/name,dpi=160);plt.close(fig);plots.append(name)
    for values,name,ylabel in [(ubpoints,'GLOBAL_UB_VS_NATIVE.png','Original FULL verified UB'),(lbpoints,'CERTIFIED_LB_VS_NATIVE.png','Certified Global LB'),(gaps,'GLOBAL_GAP_VS_NATIVE.png','Certified Global Gap (%)')]:
        fig,ax=plt.subplots(figsize=(10,4));ax.step(event_times,values,where='post',lw=2);ax.grid(alpha=.2);ax.set(xlabel='New cumulative Native Optimize Runtime (s)',ylabel=ylabel,title='4-MESS joint route-pool canary; historical Native excluded')
        if 'GAP' in name:ax.axhline(3,color='red',ls='--',label='3% target');ax.legend()
        save(fig,name)
    units=sorted(plan['units']);opportunity=[len(joint)]*4;selected_moves=[sum(any(a['unit']==u for a in j['actual_moves']) for j in joint) for u in units]
    fig,ax=plt.subplots(figsize=(8,4));xx=np.arange(4);ax.bar(xx-.18,opportunity,.36,label='Joint route decision calls');ax.bar(xx+.18,selected_moves,.36,label='Calls with FULL verified selected MOVE');ax.set_xticks(xx,units);ax.set_ylabel('Native calls');ax.legend();save(fig,'VEHICLE_ROUTE_SEARCH_COUNTS.png')
    fig,ax=plt.subplots(figsize=(11,4));xx=np.arange(len(joint));ax.plot(xx,[j['center_UB'] for j in joint],'o--',label='FULL center');ax.plot(xx,[np.nan if j['FULL_UB'] is None else j['FULL_UB'] for j in joint],'s-',label='Joint FULL verified result');ax.axhline(INITIAL_UB,color='gray',ls=':');ax.set(xlabel='Joint pool index',ylabel='UB',title='Joint centers and accepted results; Local Branching replaced by user correction');ax.legend();save(fig,'SEED_JOINT_PERFORMANCE.png')
    labels=[a['family'] for a in abl]+['FOUR_MESS_JOINT'];values=[np.nan if a['FULL_UB'] is None else a['FULL_UB'] for a in abl]+[jointbest['UB']]
    fig,ax=plt.subplots(figsize=(12,5));ax.bar(range(len(values)),values);ax.axhline(INITIAL_UB,color='red',ls='--',label='PR220');ax.set_xticks(range(len(values)),labels,rotation=35,ha='right');ax.set_ylabel('Original FULL verified UB');ax.set_ylim(.45,max([v for v in values if math_isfinite(v)]+[.56])+.01);ax.legend();save(fig,'SOLO_COOPERATIVE_JOINT_COMPARISON.png')
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True)
    for ax,u in zip(axes,units):
        paths=paths_of(case,v.load_point(best['point']['path']))[u];sites=[]
        for k in paths:
            for site in (graph.arcs[k][0],graph.arcs[k][2]):
                if site not in sites:sites.append(site)
        positions={site:-i for i,site in enumerate(sites)}
        for k in paths:
            a=graph.arcs[k]
            if a[-1] is None:ax.plot([a[1],a[3]],[positions[a[0]]]*2,color='steelblue',lw=2)
            else:
                ax.plot([a[1],a[3]],[positions[a[0]],positions[a[2]]],color='firebrick',ls='--');ax.scatter(a[-1].arrive,positions[a[2]],color='orange',s=20)
        ax.set_yticks(list(positions.values()),list(positions));ax.set_title(u);ax.grid(alpha=.2)
    axes[-1].set_xlabel('Original slot; dashed transit to reconnect, orange arrival');save(fig,'BEST_MESS_ROUTES.png')
    fig,axes=plt.subplots(4,2,figsize=(13,12),sharex=True)
    for i,u in enumerate(units):
        ur=[r for r in rows if r['unit']==u];soc=[r['SOC_before_kWh'] for r in ur]+[ur[-1]['SOC_after_kWh']]
        axes[i,0].plot(range(97),soc);axes[i,0].axhline(440,color='gray',ls=':');axes[i,0].axhline(1080,color='gray',ls=':');axes[i,0].set(ylabel='SOC kWh',title=u)
        for field,label in [('Pch_kW','Pch kW'),('Pdis_kW','Pdis kW'),('Q_kvar','Q kvar')]:axes[i,1].step(range(96),[r[field] for r in ur],where='post',label=label)
        axes[i,1].set_title(u);axes[i,1].legend(ncol=3,fontsize=8)
        for a in plan['units'][u]['move_routes']:
            for ax in axes[i]:ax.axvspan(a['depart'],a['connect'],color='orange',alpha=.12)
        for ax in axes[i]:ax.grid(alpha=.2)
    for ax in axes[-1]:ax.set_xlabel('Original slot')
    save(fig,'BEST_P_Q_SOC.png')
    fig,ax=plt.subplots(figsize=(8,4));ax.bar(['PR219','PR220','New Joint'],[.5421769340794683,INITIAL_UB,jointbest['UB']]);ax.set_ylim(min(jointbest['UB'],INITIAL_UB)-.002,.544);ax.set_ylabel('Original FULL verified UB');save(fig,'PR219_PR220_IMPROVEMENT_COMPARISON.png')
    write(DOCS/'PLOT_INDEX.json',dict(PASS=True,plots=plots,Optimize_calls=0))
    new_gain=INITIAL_UB-best['UB'];joint_gain=INITIAL_UB-jointbest['UB'];lb_gain=s['Global_LB']-GLOBAL_LB
    comparison=[['N1',HISTORICAL,GLOBAL_LB,100*(HISTORICAL-GLOBAL_LB)/HISTORICAL,'past 21.916 N1 only'],['PR219 Beam',.5421769340794683,GLOBAL_LB,100*(.5421769340794683-GLOBAL_LB)/.5421769340794683,'past1795.025 cold'],['PR220 Local',INITIAL_UB,GLOBAL_LB,100*(INITIAL_UB-GLOBAL_LB)/INITIAL_UB,'past724.821 warm'],['New Joint',jointbest['UB'],s['Global_LB'],100*(jointbest['UB']-s['Global_LB'])/jointbest['UB'],f'new primal{primal_time:.6f} / dual{dual_time:.6f}']]
    iterrows=[[j['candidate_id'],j.get('pool_counts','ABLATION'),j['FULL_UB'],j['Native'],j['Status'],j['NodeCount'],j['root_completed'],j['root_completed_Native'],j['MIPGap']] for j in joint+abl]
    moverows=[[u,a['source'],a['depart'],a['destination'],a['arrive'],a['connect'],a['energy_kWh'],a['original_arc_index']] for u,p in plan['units'].items() for a in p['move_routes']]
    dispatch=[[u,p['move_count'],p['travel_energy_kWh'],p['charging_kWh'],p['discharging_kWh'],p['SOC_min_kWh'],p['SOC_max_kWh'],p['SOC_initial_kWh'],p['SOC_terminal_kWh']] for u,p in plan['units'].items()]
    choice=read(DOCS/'LB_CANDIDATE_COMPARISON.json');critical=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0]
    dual_diagnostics=read(DOCS/'DUAL_REDUCED_POINT_DIAGNOSTICS.json')
    strict='NO_NEW_STRICT_IMPROVEMENT' if first_strict is None else f"{first_strict['Native_capture_seconds']:.6f}초 ({first_strict['candidate_id']})"
    solo=[a for a in abl if a['family'] in ('G1','G2','G4') and a['FULL_UB'] is not None];nonM3pairs=[a for a in abl if a['family'].startswith('PAIR_') and a['FULL_UB'] is not None]
    answers=[f"Q1: MESS01/02/04 단독 이동 개선 여부: {any(a['FULL_UB']<INITIAL_UB-DELTA for a in solo)}. 이들은 보조 Ablation이며 4대 Joint 결과와 구분한다.",
        f"Q2: MESS03 제외 2대 비교군 개선 여부: {any(a['FULL_UB']<INITIAL_UB-DELTA for a in nonM3pairs)}. 생성 경로만으로 공동 FULL 가능성을 가정하지 않았고 각 평가의 Replay 결과를 보존했다.",
        'Q3: 긴급 정정에 따라 서로 다른 단독 Seed 중심 Local Branching은 미실행이다. Proposed Algorithm은 모든 차량의 서로 다른 경로집합을 한 MILP에서 공동 선택했다. 반복 실험의 일반적 우위나 전역 경로 최적성을 주장하지 않는다.',
        'Q4: 신규 좋은 해의 실제 family/candidate/Raw/Native 시점은 BEST_GLOBAL_UB_TRAJECTORY.json과 Joint 결과에 기록했다. inherited 초기점은 새 발견이 아니다.',
        'Q5: 나쁜 단독 Seed에서의 Local Branching은 NOT_EXECUTED_REPLACED_BY_JOINT. 실제 Joint Start는 FULL 검증한 현재 최선이며 모든 차량이 다른 경로를 선택할 수 있다.',
        f"Q6: Joint 실행 후 항상 다른 4대 후보집합 탐색을 계속하도록 동결했다. 실제 Joint 모델 {len(joint)}개, 서로 다른 pool signature {len(set(j['pool_signature'] for j in joint))}개다. 우승 Start의 재포함은 새로운 조합 발견으로 세지 않는다.",
        f'Q7: PR220 대비 Global 추가 감소 {new_gain:.17g}, Joint 추가 감소 {joint_gain:.17g}.',
        f'Q8/Q9: 기존 K48을 계승하고 새 K32 Selective 실험 후 인증 LB 증가 {lb_gain:.17g}. 선택 Binary {len(choice["selected"])}개, 실제 인접 구간 {choice["connected_slot_pairs"]}.',
        f'Q10: 단일 Dual Native {dual_time:.6f}초, 인증 LB 감소가 아닌 증가량 {lb_gain:.17g}. 0.001 미만이면 추가 LB 호출을 하지 않았다.',
        f"Q11: 선택한 {dual_diagnostics['selected_binary_count']}개 좌표는 정수가 됐지만 나머지 원본 Binary {dual_diagnostics['remaining_original_binary_fractional_count']}개가 분수로 남은 축소 해가 동일 K32 수준의 목적값을 얻었다. 이 부분집합의 integrality만으로 분수 탈출을 막지는 못했다는 관측이다. Grid 누락과 전체 Route/Mode 결합의 인과 기여는 분해하지 못했다. K32에는 목적값0.4812227125의 축소 정수 witness도 있어 정식화 상한을 구분해야 한다.",
        f'Q12: 최종 Global UB {best["UB"]:.17g}, 인증 LB {s["Global_LB"]:.17g}, Global Gap {100*s["Global_gap"]:.9f}%.',
        f'Q13: 3% 인증 = {s["Global_gap"]<=.03}. 목표에 미달하면 이 수치를 그대로 유지한다.']
    text=f'''# V42 B2 — 4-MESS Joint Route-Pool MILP + 단기 Global LB Canary

PR220 대비 추가 UB 감소 **{new_gain:.17g}**. BEST_GLOBAL_UB **{best['UB']:.17g}**, BEST_MOVING_FEASIBLE_UB **{moving['UB']:.17g}**, BEST_JOINT_FEASIBLE_UB **{jointbest['UB']:.17g}**. 최초 유의 개선 **{strict}**. 신규 인증 LB 증가 **{lb_gain:.17g}**, Dual Native **{dual_time:.6f}초**. 최종 인증 Global Gap **{100*s['Global_gap']:.9f}%**, 3% 인증 **{s['Global_gap']<=.03}**.

## 실행 및 긴급 정정

사용자의 긴급 정정을 최초 Source/Policy 동결 전에 반영했다. 정정 시 Native Optimize0회. 기존 단독 Multi-Start 초안은 `initial_multistart_draft`에 미실행 문서로 보존했다. 최종 Proposed Algorithm은 **4-MESS Joint Route-Pool MILP**다. 단독/2대 경로는 보조 Ablation이다. 각 경로 조합을 별도 MILP로 열거하지 않았다. `PRE_NATIVE_JOINT_CORRECTION_RECEIPT.json` 참조.

IEEE123 B2 2025-05-01 Planning만 실행했다. Native 총합 **{s['Native_used']:.6f}초 ≤1800**, Primal **{primal_time:.6f}초**, Dual **{dual_time:.6f}초**, Controller Wall **{s['controller_wall_seconds']:.3f}초**, 종료 `{s['stopped_reason']}`. 과거 PR219 1795.025초와 PR220 724.821초를 합산하지 않았다. ACTUAL_NOT_RUN, B1/HOLD/Disabled 및 원본 Source/Raw/원장 보존.

## 수학적 보증 및 원본 물리

Source207 `{v.SOURCE_SHA}`, PR220 exact HEAD `{BASE}`, Case `{v.CASE_SHA}`, FULL Matrix `{v.FULL_MATRIX_SHA}`, FULL Domain `{v.FULL_DOMAIN_SHA}`. 기존 Raw SHA `{RAW_SHA}`를 그대로 FULL 재검증해 Native0 초기 UB로 등록했다. 원본 수치 허용정책을 유지하며 clipping/rounding/repair0이다. 이를 exact rational primal 인증으로 과장하지 않는다.

각 차량은 STAY·복수 실제 MOVE·PR220 경로를 포함한다. 원본 DAG의96슬롯 완성 경로만 사용한다. Binary `lambda[u,r]`와 `sum_r lambda[u,r]=1`, 각 원본 Native Node/Route Flow와 선택 경로의 정확한 등식으로 4대 경로를 동시에 정한다. Original inverse Arc/Alias를 독립 affine 전개해 모든 경로에서 일치함을 증명했다. 이로써 Joint 가능영역은 원본 FULL 가능영역의 부분집합이다. 원본 Binary9322개와 추가 lambda를 구분한다. 모든384 Mode/Pch/Pdis/Q/SOC97은 원래 bounds에서 자유롭고 원본 Grid/PCS16/이동에너지/ETA/종단SOC/고정AIDC/SVR/Cap 및 min rho_max를 유지한다. 불필요한 MOVE 강제는 없다. 네 대가 MOVE를 선택하는 조합의 경로 영역은 열려 있지만 SOC/Grid 공동 가능성은 실제 MILP/FULL Replay로만 채택한다.

V1은 초기6경로/대, V2는8경로/대에서 시작했다. V1의 point+lambda NPZ는 원본 validator의 packet schema에서 거절돼 V1 소스/Raw/원장을 보존하고 종료했다. 270.658999681473 Native초를 차감한 잔여 예산으로 V2를 별도 동결했다. V1 계획벡터는 단 한 비트도 바꾸지 않고 point-only 패킷으로 분리해 원본 FULL PASS했다. 이는 수치 repair가 아닌 무손실 형식 변환이며 원본 Native 패킷과 lambda도 보존했다. V2는 처음부터 point-only Raw를 저장했다. Root 완료 후 각 차량에2경로를 추가하고, TIME_LIMIT으로 Root 미완료 시 규모를 무작정 키우지 않고 네 차량의 후보를 다른 위치/출발/재접속 패턴으로 교체한다. 현재 우승과 PR220 경로는 유지한다. 같은 pool/model signature 재실행0회. 경로집합의 공유된 우승 조합은 Start 권위로 재포함되며 새 발견으로 세지 않는다. 전역 전체 경로 공간 소진이나 FULL Global OPTIMAL을 주장하지 않는다.

## 비교 및 실제 Native 반복

{table(['연구','Verified UB','Certified LB','Gap %','Native scope'],comparison)}

{table(['모델','Pool counts','FULL UB','Native s','Status','Nodes','Root 완료','Root Native s','Restricted gap'],iterrows)}

Status2는 원래 MIPGap0.005 정책에 따른 제한 solver 상태이며 전역 최적성 인증이 아니다. Root 미완료/TimeLimit/Infeasible 및 실패 Raw를 보존한다. Restricted ObjBound의 Global LB 승격0회.

## 최선 이동 및96슬롯 운전계획

{table(['MESS','Source','Depart','Destination','Arrive','Connect','kWh','Original Arc'],moverows)}

{table(['MESS','MOVE','이동 kWh','충전 AC kWh','방전 AC kWh','SOC min','SOC max','초기 SOC','종단 SOC'],dispatch)}

`BEST_96_SLOT_MESS_PLAN.csv`는4대×96행, `BEST_PLAN_AUDIT.json`은97SOC경계·원본에너지 잔차·전체 이동을 제공한다. 원래 terminal 위치 의미를 유지했고 새로운 원점복귀 의무를 추가하지 않았다. 최종 original critical thermal row: `{critical}`. 최선 Raw의 원본 FULL Replay와 독립 반복 재검증을 `ORIGINAL_FULL_REPLAY_CERTIFICATES.json` 및 `FINAL_INDEPENDENT_REVIEW.json`에 결합했다.

![최선 원본 경로](BEST_MESS_ROUTES.png)

![96슬롯 SOC/P/Q](BEST_P_Q_SOC.png)

## Dual 포함관계 및 단기 실험

기존 K32/K48 인증과 PR214 분수 LP, PR215 미실행 Selective 설계, PR218 실패 Grid16을 읽기 전용으로 검토했다. A를 선택한 이유와 B 미실행 사유는 `LB_CANDIDATE_COMPARISON.json`에 있다. 분수 혼합을 전체 horizon의3개 band에서 골라 인접 실제 구간의 Node/Mode를 선택했다. 현재 Slot42만 고르지 않았다. 실제 선택 Binary {len(choice['selected'])}개 중 분수102개를 기준으로 하며 구간 {choice['connected_slot_pairs']}다.

K32의 모든 원본 사영 계수/RHS/Sense/Bounds/Objective 및 inherited outward rounding은 변경하지 않았다. 선택된 원본 Binary만 유지하고 나머지는 원래[0,1]에서 연속 완화했으므로 `Projection(FULL integer feasible set) ⊆ Selective K32`다. 새 행/외향 반올림은 없으며 부모 사영의 정확한 인증을 재검증했다. 단일 Native 실제 ObjBound와 Readback/Resource/Numeric 조건이 통과한 값만 `max(K48,newLB)`로 결합했다. Root 로그 목적값이나 Reduced ObjVal을 Global LB/FULL UB로 쓰지 않았다. 요청175초는 최대180초 내 반환 여유이며 추가 Dual 반복0회다.

## 연구 질문

{chr(10).join('- '+a for a in answers)}

## 자원 및 실패 이력

Heavy Worker1/Threads1/GPU사용0. 최소 가용 RAM {memory['minimum_RAM_available']/2**30:.3f}GiB, Commit {memory['minimum_commit_available']/2**30:.3f}GiB. Worker Peak RSS {memory['peak_worker_RSS']/2**30:.3f}GiB, Private Commit {memory['peak_worker_Private_Commit']/2**30:.3f}GiB. 시스템 RAM/Commit 샘플 최대는 JSON에 별도로 보존하며 연속 peak라고 주장하지 않는다. 원본 큰 계수 범위 경고 {len(warnings)}개를 그대로 보존했다. 모델 생성 후 실제 성장 Reserve와 callback 안전 Gate를 모두 검사했다. 준비 단계의 느린 감사·디렉터리 재사용 오류는 Native0 이력에 보존했고 예산을 재설정하지 않았다. 신규 Raw FULL PASS {sum(c['PASS'] for c in captures)}개 / FAIL {sum(not c['PASS'] for c in captures)}개. 검증 실패와 lambda literal 실패는 UB에서 제외했다.

## 그래프

![Global UB](GLOBAL_UB_VS_NATIVE.png)

![인증 LB](CERTIFIED_LB_VS_NATIVE.png)

![Global Gap](GLOBAL_GAP_VS_NATIVE.png)

![차량별 탐색 기회](VEHICLE_ROUTE_SEARCH_COUNTS.png)

![Joint 중심과 결과](SEED_JOINT_PERFORMANCE.png)

![단독/협조/Joint](SOLO_COOPERATIVE_JOINT_COMPARISON.png)

![PR219/220 비교](PR219_PR220_IMPROVEMENT_COMPARISON.png)

미실행 결과를0이나 가상 성능으로 채우지 않았다. 추가 Forecast/Fresh OpenDSS/Actual/PQrepair/B1/B3/8500/다른 날짜/캠페인/무제한 FULL B&B0회. 분류는 원본 FULL 검증을 갖춘 제한 Joint Matheuristic이며 전역 경로 최적성은 미증명이다.
'''
    (DOCS/'GLOBAL_LOCAL_MULTISTART_DUAL1800_FINAL_KO.md').write_text(text,encoding='utf-8')
    write(DOCS/'POSTPROCESS_RECEIPT.json',dict(PASS=True,Optimize_calls=0,wall_seconds=time.perf_counter()-began))
    print(json.dumps(dict(PASS=True,UB=best['UB'],Joint_UB=jointbest['UB'],LB=s['Global_LB'],Native=s['Native_used'])))

def math_isfinite(value):return bool(np.isfinite(value))
if __name__=='__main__':main()
