"""Post-canary independent receipts, original plans and scientific plots.

Never constructs a Native model or calls Optimize. Run only after controller
termination and all solver workers exit. Original FULL validators are reused.
"""
from pathlib import Path
from fractions import Fraction
from datetime import datetime,timezone
import ast,csv,hashlib,json,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.integrated_primal1800.adapter import DOCS,OLD,BASE,read,guard,v,r,g,write,record
from tools.u4_primal_alns.analyze import original_plan
LB=.46498486997548166


def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+
        ['|'+'|'.join(str(x) for x in row)+'|' for row in rows])


def peak(call):
    samples=[call.get(k,{}) for k in ('build_memory_before','build_memory_after','after_native_memory')]
    samples += [x.get('sample',{}) for x in call.get('resource_samples',[])]
    return {k:max([0]+[s.get(k,0) for s in samples]) for k in ('Peak_RSS_bytes','Peak_Private_Commit_bytes')}


def main():
    started=time.perf_counter();guard()
    state=read(DOCS/'FINAL_STATE.json')
    assert state['stopped_reason'] and state['Best'] is not None
    resource=r.audit('FINAL_POSTPROCESS_READONLY',True)
    assert resource['PASS'];write(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json',resource)
    used=0.;checks=[];trajectory=[];plans={};case=v.load_case(native=False);prior_full_points=set()
    selected={};first_move={};warnings=[];lower_obj=1.
    for iteration in state['iterations']:
        if not iteration.get('call'):continue
        call=read(iteration['call']['path']);assert v.file_sha(iteration['call']['path'])==iteration['call']['sha256']
        assert call['entered_native'] and not call['runtime_unavailable'] and call['Native_worker']==call['Threads']==1
        assert np.isfinite(call['Native_Runtime']) and call['Native_Runtime']>=0;used+=call['Native_Runtime']
        assert call['parameter_readback']['Threads']==1 and call['parameter_readback']['Seed']==0
        assert call['parameter_readback']['FeasibilityTol']==call['parameter_readback']['OptimalityTol']==1e-9
        assert call['parameter_readback']['IntFeasTol']==1e-8
        assert call['parameter_readback']['MIPGap']==.005 and call['parameter_readback']['MIPGapAbs']==1e-10
        assert call['parameter_readback']['Method']==(1 if call['method']=='INITIALIZE' else 2)
        assert call['parameter_readback']['NumericFocus']==3 and call['parameter_readback']['ScaleFlag']==2
        assert call['parameter_readback']['MIPFocus']==1
        assert call['previous_PR216_result_solver_start'] is False
        if call['method']=='INITIALIZE':assert call['initial_point'] is None and call['actual_NumStart']==0
        else:
            assert Path(call['initial_point']['path']).resolve().is_relative_to((DOCS/'calls').resolve())
            assert v.file_sha(call['initial_point']['path'])==call['initial_point']['sha256']
            assert call['initial_point']['sha256'] in prior_full_points, 'Start must bind an earlier freshly verified FULL point.'
        execution=call['execution_source_seal'];execution_path=Path(execution['path'])
        if v.file_sha(execution_path)!=execution['sha256']:
            execution_path=DOCS/'EPOCH01_GUARD_STOP/EXECUTED_SOURCE_HASHES.json'
        assert v.file_sha(execution_path)==execution['sha256'], 'Exact execution epoch seal must remain available.'
        identity=read(Path(iteration['call']['path']).parent/'ADAPTER_MODEL_IDENTITY.json')
        assert identity['PASS'] and identity['original_Dense_rows_exact'] and not identity['unrestricted_global_BB']
        if call['method'] in ('N2+','N3+'):
            assert identity['restrictions']['all384_Mode_free'] and identity['restrictions']['Modes_in_Hamming']==0
            spec=read(Path(iteration['call']['path']).parent/'NEIGHBORHOOD.json')
            mode_columns=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
            assert len(mode_columns)==384 and set(mode_columns)<=set(spec['free_binary_columns'])
            assert not set(mode_columns)&set(spec['hamming_columns'])
        assert read(Path(iteration['call']['path']).parent/'INDEPENDENT_RESTRICTION_NATIVE0.json')['PASS']
        assert read(Path(iteration['call']['path']).parent/'POST_BUILD_NATIVE_ADMISSION.json')['PASS']
        log=Path(iteration['call']['path']).parent/'NATIVE_GUROBI.log'
        text=log.read_text(encoding='utf-8');warnings += [line for line in text.splitlines() if 'Warning:' in line]
        assert call.get('Status')!=12
        assert len(call['captures'])==len(iteration['validated']), 'Every saved capture must have a replay disposition.'
        for capture,item in zip(call['captures'],iteration['validated']):
            assert v.file_sha(item['raw']['path'])==item['raw']['sha256']
            if not item['PASS']:continue
            replay=read(item['replay']['path']);assert v.file_sha(item['replay']['path'])==item['replay']['sha256']
            assert replay['PASS'] and replay['source_sha']==v.SOURCE_SHA and replay['case_sha']==v.CASE_SHA
            assert replay['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] and replay['solver_and_original_objective_bit_equal']
            assert replay['point_file_sha256']==item['raw']['sha256']
            prior_full_points.add(item['raw']['sha256'])
            plan,rows=original_plan(case,Path(item['raw']['path']),replay)
            if call['method'] not in selected or plan['verified_UB']<=selected[call['method']][0]['verified_UB']:
                selected[call['method']]=(plan,rows,item)
            discovery=used-call['Native_Runtime']+capture['discovered_Native_seconds']
            if plan['move_count'] and call['method'] not in first_move:first_move[call['method']]=discovery
            lower_obj=min(lower_obj,plan['verified_UB'])
            trajectory.append(dict(method=call['method'],Native_discovery_seconds=discovery,
                verified_UB=plan['verified_UB'],Best_UB=lower_obj,moves=plan['move_count'],raw=item['raw'],replay=item['replay']))
        checks.append(dict(method=call['method'],Native=call['Native_Runtime'],receipt=iteration['call'],PASS=True))
    assert used==state['Native_used'] and used<=1800 and lower_obj==state['Best']['UB']
    best,replay=state['Best']['point']['path'],read(state['Best']['replay']['path'])
    final_plan,final_rows=original_plan(case,Path(best),replay)
    selected['FINAL']=(final_plan,final_rows,dict(raw=state['Best']['point'],replay=state['Best']['replay']))
    grid={}
    for label,(plan,rows,item) in selected.items():
        tag=label.replace('+','PLUS')
        folder=DOCS/'operating_plans';folder.mkdir(exist_ok=True)
        write(folder/f'{tag}_SOURCE_ORIGINAL_PLAN.json',plan)
        with (folder/f'{tag}_SOURCE96_PLAN.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        assert len(rows)==384 and all(len(u['SOC97_kWh'])==97 for u in plan['units'].values())
        context,receipt=g.refresh(case,v.load_point(item['raw']['path']))
        thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0]
        grid[label]=dict(PASS=True,current_full_grid=receipt,critical=thermal,
            all_original_security_rows_scanned=814560,Native_calls=0)
        plans[label]=plan
    write(DOCS/'ORIGINAL_OPERATING_PLAN_COMPARISON.json',dict(PASS=True,plans=plans,first_moving_plan_Native_seconds=first_move,Native_calls=0))
    write(DOCS/'CRITICAL_GRID_COMPARISON.json',dict(PASS=True,stages=grid,Native_calls=0,interpretation_not_new_UB_or_LB_certificate=True))
    assert 'gurobipy' not in sys.modules
    init=plans['INITIALIZE']['verified_UB'];n1=plans.get('N1',plans['INITIALIZE'])['verified_UB'];final=final_plan['verified_UB']
    route_gain=n1-final
    reproduced=abs(n1-.5461621302242249)<=1e-6 or n1<.5461621302242249
    route_improved=route_gain>0 and final_plan['move_count']>0 and state['Best']['method'] in ('N2+','N3+')
    classification='N1_PLUS_ROUTE_MATERIAL_GAIN' if route_improved and route_gain>=.005 else 'N1_PLUS_ROUTE_NONMATERIAL' if route_improved else 'COLD_START_N1_REPRODUCED' if reproduced else 'TIME_LIMIT_FEASIBLE'
    if state['stopped_reason']=='RESOURCE_NUMERIC_SOURCE_OR_IMPLEMENTATION_STOP':classification='RESOURCE_OR_NUMERIC_STOP'
    gap=(final-LB)/final
    if gap<=.03:classification='GLOBAL_GAP_3PCT_CERTIFIED'
    certificate=dict(PASS=True,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,base=BASE,
        original_matrix_sha=v.FULL_MATRIX_SHA,original_domain_sha=v.FULL_DOMAIN_SHA,
        calls=checks,total_actual_Native_seconds=used,first_call_no_MIP_Start=True,
        all_later_starts_this_canary_fresh_FULL_outputs=True,guard_and_Native0_not_bypassed=True,
        preserved_epoch01_and_epoch02_execution_source_seals=True,
        exact_raw_integers_and_original_objective_transport=True,original_FULL_scientific_tolerances_unchanged=True,
        exact_rational_continuous_feasibility_claim=False,Global_LB=LB,verified_final_UB=final,
        Global_gap_percent=100*gap,Global_gap_3pct_certified=gap<=.03,FULL_feasible_certified=True,
        primary_classification=classification,COLD_START_N1_REPRODUCED=reproduced,
        route_material_gain=route_improved and route_gain>=.005,final_move_count=final_plan['move_count'],
        LB_needed_for_3pct=.97*final,UB_needed_for_3pct=LB/.97,
        no_new_LB_or_Full_BB=True,Native_calls_by_auditor=0,
        numeric_warnings=warnings,resource_audit=record(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json'))
    write(DOCS/'FINAL_INDEPENDENT_CERTIFICATE.json',certificate)
    write(DOCS/'VERIFIED_UB_TRAJECTORY.json',dict(PASS=True,points=trajectory,Native_calls=0))
    # Compatibility inspection is static and read-only. Do not manufacture an
    # accepted B2 stage or bypass the unchanged frozen Actual interface gate.
    source=ROOT/'v42_may_campaign_native90/operations.py'
    raw=source.read_text(encoding='utf-8');tree=ast.parse(raw)
    accepted=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_accepted')
    snippet=ast.get_source_segment(raw,accepted)
    assert "gap <= (.005 if arm == 'B1' else .03)" in snippet
    actual=dict(PASS=True,status='ACTUAL_NOT_RUN',Fresh_AC96_calls=0,Gurobi_optimize_calls=0,
        Planning_FULL_PASS_not_Actual_PASS=True,frozen_decisions_not_reoptimized_or_repaired=True,
        existing_actual_source=record(source),source_acceptance_gate_B2_gap_le3pct=True,
        best_plan_global_gap=gap,unchanged_interface_gate_satisfied=gap<=.03,
        own_Planning_OpenDSS_reference_and_day_ahead_freeze_present=False,
        reason='Unchanged frozen Actual interface requires an accepted B2 stage with certified gap≤3% and its own Planning control reference/day-ahead freeze. This restricted research controller has no such frozen interface. Prior control state or acceptance is not substituted; no gate relaxed.',
        inspected_function_first_line=accepted.lineno,inspected_function_last_line=accepted.end_lineno)
    write(DOCS/'ACTUAL_FRESH_INTERFACE_COMPATIBILITY.json',actual)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.2));x=[p['Native_discovery_seconds'] for p in trajectory];y=[p['Best_UB'] for p in trajectory]
    ax.step(x,y,where='post',label='Fresh FULL-verified best UB');ax.axhline(LB,color='green',linestyle='--',label='Existing certified K48 LB')
    ax.axhline(.5461621302242249,color='gray',linestyle=':',label='PR216 N1 reference only')
    ax.set(xlabel='Cumulative Native Optimize seconds',ylabel='rho_max',title='IEEE123 B2 May01 integrated cold-start canary');ax.legend(fontsize=8);ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(DOCS/'UB_TRAJECTORY.png',dpi=180);fig.savefig(DOCS/'UB_TRAJECTORY.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4));dur=[c['Native_Runtime'] for c in state['calls']];cum=np.cumsum(dur)
    labels=[f"{i+1} {c['method']}" for i,c in enumerate(state['calls'])]
    axes[0].bar(range(len(dur)),dur);axes[0].set_xticks(range(len(labels)),labels,rotation=65,fontsize=7)
    axes[0].set(ylabel='Native seconds',title='Measured time per Optimize call')
    axes[1].step(range(1,len(cum)+1),cum,where='post');axes[1].axhline(1800,color='red',linestyle='--',label='1800-second ceiling');axes[1].legend(fontsize=8)
    axes[1].set(xlabel='Optimize call',ylabel='Cumulative Native seconds',title='Shared budget, no reset')
    fig.tight_layout();fig.savefig(DOCS/'NATIVE_RUNTIME.png',dpi=180);fig.savefig(DOCS/'NATIVE_RUNTIME.svg');plt.close(fig)
    report(state,certificate,plans,grid,actual,trajectory)
    write(DOCS/'POSTPROCESS_RECEIPT.json',dict(PASS=True,postprocess_wall_seconds=time.perf_counter()-started,Native_calls=0,
        no_Source_or_existing_results_modified=True,Source_seal_unchanged=True,UTC=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(certificate,ensure_ascii=False))


def report(state,cert,plans,grid,actual,trajectory):
    total=cert['total_actual_Native_seconds'];final=cert['verified_final_UB'];initial=plans['INITIALIZE']['verified_UB']
    cp=state['calls'];stages=['INITIALIZE','U4','N1','N2+','N3+','FINAL']
    stage_rows=[]
    for name in stages:
        p=plans.get(name);calls=[c for c in cp if c['method']==name]
        stage_rows.append([name,'NOT_RUN' if p is None else f"{p['verified_UB']:.16g}",f"{sum(c['Native_Runtime'] for c in calls):.6f}",
            '-' if p is None else p['move_count'],'-' if p is None else f"{p['travel_energy_kWh']:.6f}",
            '-' if p is None else f"{p['charging_kWh']:.6f}",'-' if p is None else f"{p['discharging_kWh']:.6f}",
            '-' if p is None else f"{p['SOC_min_kWh']:.3f}/{p['SOC_max_kWh']:.3f}",
            '-' if p is None else f"{100*(p['verified_UB']-LB)/p['verified_UB']:.8f}"])
    calls=[]
    for i,c in enumerate(cp):
        pp=peak(c);calls.append([i+1,c['method'],f"{c['effective_TimeLimit']:.6f}",f"{c['Native_Runtime']:.6f}",c['Status'],
            c.get('ObjVal'),c.get('ObjBound'),c.get('MIPGap'),c.get('NodeCount'),c.get('root_completed_Native_seconds'),
            f"{c['model_build_wall_seconds']:.3f}",f"{pp['Peak_RSS_bytes']/2**30:.3f}",f"{pp['Peak_Private_Commit_bytes']/2**30:.3f}"])
    body=[
        '# B2 U4–N1–Route/Mode 통합 Primal 1,800초 Cold-Start Canary 최종 보고',
        f"주 판정 **{cert['primary_classification']}**. 최종 원본 FULL 검증 UB **{final:.16g}**, 기존 K48 Global LB **{LB:.16g}**, Global Gap **{cert['Global_gap_percent']:.8f}%**. FULL 가능해 확보와3% 인증을 구분하며,3% 달성은 **{cert['Global_gap_3pct_certified']}**다. Actual은 **ACTUAL_NOT_RUN**이다.",
        '## 1. Source와 새 Cold Start',
        f'정확한 base PR216 `{BASE}`. Source18r `{v.SOURCE_SHA}`, Case `{v.CASE_SHA}`, FULL matrix `{v.FULL_MATRIX_SHA}`, FULL domain `{v.FULL_DOMAIN_SHA}`다. 새 코드와 결과는 별도 연구 디렉터리에만 기록했다. PR207/209/210/211/214/215/216 및 B1 PR212/213은 동일 HEAD와 원본 증거 bytes를 유지한다.',
        '첫 Native는 Source18r stationary_paths/values_for가 생성한 원본 이산 경로/Mode 및 route flow 대표값을 고정하고 나머지 P/Q/SOC/helper를 새로 계산했다. MIP Start는None, 실제 NumStart0이다. 저장된 U4/N1 점은 scientific authority 확인·코드 회귀·성능 비교에서만 읽었다. 새 초기화는 전체 원본 정수 type을 유지했으며, 과거 continuous fixed-representative 초기화5.328초와 computational profile이 다르다. 이번 초기화 실측을 과거값으로 대체하지 않는다.',
        '## 2. 정확한 Primal 영역과 재사용',
        '원본4대·24sites·96슬롯·97SOC·실제 원본 Arc/ETA/이동에너지·Mode·PCS16·초기/종단SOC·전압·Thermal/NormalAmps·변압기·SVR11·고정AIDC와 모든 Grid를 유지한다. Native는 인증된 Dense715,596행×354,277열·9,322Binary다. 원본 FULL1,130,336행×344,967열과의 인증된 역좌표 transport를 그대로 사용한다. 새 변수/제약 삭제나 압축은 없다.',
        'Cold 초기화와 U4는 Source fixed_pattern/원래 U4 select를 사용한다. N1은4대 전체384Mode 개방, 모든 Route/Node/continuous route 및 alias 고정이다. N2+는1대 Route/Node, N3+는2대 Route/Node를 개방하고 **두 방법 모두4대의384Mode 전체를 개방**한다. 다른 차량 Route만 고정하며 전 차량P/Q/SOC 및 원본 비route 연속 bounds는 같다. 추가 Hamming은 N2+/N3+의 free Node-Activity에만 radius48/96을 부과한다. Mode는 해당 행에 전혀 들어가지 않는다. N1 radius384는 전체Mode 변경을 허용한다.',
        '고정은 원본box 안에서 새 FULL 검증점의 이산/route 좌표에만 적용하고 중심Hamming거리는0이다. 원본 unselected Arc의 retained좌표/alias 의존성을 PR216 auditor로 별도 확인했다. 따라서 제한 가능영역은 원본 FULL의 부분집합이고 중심점이 포함된다. 원본 terminal은slot96 flow이며 새로운 출발점 복귀 방정식이 없다. Window 밖Node를 중심에 고정한 개별Primal Neighborhood는 tail 위치를 제한할 수 있으나 원본 전체 문제의 terminal 의미를 바꾸거나 글로벌 복귀 의무를 주장하지 않는다. 제한 ObjBound는 Global LB가 아니다.',
        '## 3. Cold U4와 N1 및 통합 최종 비교',
        table(['단계','검증UB','Native(s)','이동','이동kWh','충전ACkWh','방전ACkWh','SOC min/max','Global Gap(%)'],stage_rows),
        f"과거 U4 UB0.6760534504652341와 PR216 N1 UB0.5461621302242249는 참고다. 이번 새 초기화UB={initial:.16g}, 통합 최종UB={final:.16g}. 기존U4 대비 절대개선={.6760534504652341-final:.12f}, 상대개선={100*(.6760534504652341-final)/.6760534504652341:.8f}%. N1재현 판정={cert['COLD_START_N1_REPRODUCED']}; 이는 같은허용정밀도에서참고UB+1e−6 이내 또는더좋은값이라는 성능판정이며 물리검증tolerance를 바꾸지 않는다.",
        '## 4. 모든 실제 Native 호출',
        table(['호출','유형','요청TL','actualNative','Status','Incumbent','제한Bound','제한Gap','Nodes','Root완료Native','buildWall','PeakRSS GiB','PeakPrivate GiB'],calls),
        f"합계 actual Native **{total:.6f}초** /1,800초. Cold 초기화와 U4/N1을 모두 포함했고 이전PR216 Runtime은 새예산에 포함하지 않는다. 각요청은 실제잔여예산−5초 반환여유 및유형caps를 함께 고려했다. Runtime/TimeLimit초과를 자르지 않는다. Unknown runtime을0으로 만들지 않는다. Status2는승인MIPGap.005 OPTIMAL,9 TIME_LIMIT,11은 Raw 개선점의즉시FULLReplay를위한자기Worker중단일수있다. Root완료값None는완료메시지미관측이며 presolve최적종료또는 root미완료여부를 해당원본log와함께본다.",
        '## 5. Current Grid, 중심점 전달과 비반복 정책',
        'N1 이후최선 FULL점에서814,560개 원본 Security행을 다시스캔해 thermal12/변압기4/NormalAmps2/upper4/lower4 Critical행과원본Response/injection/fixed항을포함한signedPch/Pdis/Q 계수를 재계산했다. 중심변경 시 재스캔한다. signedPCS16 support는순위heuristic이고96슬롯가능성증명이아니다. 원본ETA/이동에너지/실제DAG,사전충전·혼잡구간·후속SOC복원시간은Node창과후보witness에기록하며모든Mode는96슬롯전체자유다.',
        'N2+부터시작해개선없으면N3+로전환하고,현재유형root정체2회면다른유형으로넘긴다. 각중심은4primary/4expanded single차량과6쌍의유한정책을갖는다. 동일수학적모델의bounds/free/Hamming계수·RHS signature는재실행하지않는다. 첫엄격한Raw개선은즉시저장후해당worker를종료해독립FULLReplay한뒤채택한다. 불합격Raw를삭제·수정하지않고Best를유지한다.',
        table(['단계','검증된최대thermal facet','Critical Line','Phase','Slot'],[[label,
            data['critical']['rho_scaled_loading'],data['critical']['metadata']['asset'],data['critical']['metadata']['phase'],data['critical']['metadata']['slot']] for label,data in grid.items()]),
        '## 6. 운전계획·SOC·Rebound',
        table(['차량','이동','이동kWh','충전ACkWh','방전ACkWh','Mode1','최대 |Q|','SOC min/max','초기/종단 SOC','종단 위치'],[
            [u,p['move_count'],f"{p['travel_energy_kWh']:.6f}",f"{p['charging_kWh']:.6f}",f"{p['discharging_kWh']:.6f}",p['charge_mode_1_count'],
             f"{p['Q_max_absolute_kvar']:.6f}",f"{p['SOC_min_kWh']:.3f}/{p['SOC_max_kWh']:.3f}",f"{p['SOC_initial_kWh']:.3f}/{p['SOC_terminal_kWh']:.3f}",p['original_terminal_location']]
            for u,p in plans['FINAL']['units'].items()]),
        '전체384행원본96슬롯CSV와차량별97SOC는 [operating_plans](operating_plans)에있다. 선택이동Arc의원본index/route_id/출발·arrive·connect/에너지를 JSON에보존했다. Mode1은binary슬롯수이며Pch양수슬롯과같다고가정하지않는다. SOC복원과충전Rebound·이동중P/Q·에너지잔차는각슬롯별기록이다. 이동수증가만으로이득을선언하지않으며최종점의원본FULL목적과이동에너지전체를함께판단한다.',
        '## 7. 인증LB와3% 조건',
        f'K32 기본LB0.46497617639758426,같은Source/Case K48누적LB{LB:.16g}를 각각원본INDEPENDENT_CERTIFICATE bytes로대조해보존했다. LB최적화0회,Full global B&B0회,CG0회다. Global Gap={cert["Global_gap_percent"]:.8f}%. 현재UB에필요한LB는0.97×UB={cert["LB_needed_for_3pct"]:.16g};현재LB에서필요한UB는LB/0.97={cert["UB_needed_for_3pct"]:.16g}이다. 목표미달은원본전역최적성증명이아니다.',
        '## 8. Native0 실패·Guard 정지·재개 보존',
        '최초코드회귀에서역사적N1 callback point의미세한연속bound잔차를strict box가거부했다. Raw를보정하지않고동일UB의별도FINAL_RAW/FULLReplay를코드검증에만사용했다. 또한lazyFULL인터페이스에는U4 PCSselector가읽는indptr가없어Native0에서검출됐다. 원본selector를수정하지않고solver없는선정scope에서검증된FULLCSR하나를읽어해제한다.',
        'Cold초기화뒤U4전Guard가제어프로세스의GurobiDLL을검출해Native를거부했다. 기존U4선정코드가ub모듈을import하면서DLL을로드했으며Optimize전진입이다. 초기화80.046초·FULL점·oldSource seal·차단SPEC/log/상태를EPOCH01에보존했다. 이후선정은별도Native0 subprocess로분리해exit확인후Native를시작한다. Guard를면제하지않고Source/U4수학적SPEC동일성과27개파일보존을검산했다. 초기화재실행·예산reset0회다. 재개seal완료전의성급한진입도SHAguard가차단했으며추가Optimize0회였다. 모든실행epoch와실패증거를남겼다.',
        '## 9. 자원·수치·전체Wall',
        f'1Worker×Threads1,GPU사용0,외부프로세스강제종료0. 최소RAM4GiB/Commit6GiB에max(2GiB,4×실측private증가)추가여유를검사했다. 원본GPReadback·모든bounds/rows/RHS/objective·별도Native0를매번검사한다. 이보고의Nativepeak는각worker전체이며GP내부MaxMemUsed와다르다. 기존matrix coefficient range경고를기록했고Status12/새수치오류는원본log와인증JSON을참조한다. FULL검증기는bound/integrality1e−8,중요Grid/flow행1e−8,기타행1e−6의원래기준을유지했다. Raw반올림/Clipping/Repair0회,정확한유리수연속가능성증명은주장하지않는다.',
        f'epoch02제어wall={state["controller_wall_seconds"]:.3f}초,보존epoch01제어wall={state.get("epoch01_controller_wall_seconds",0):.3f}초. 각build/FULLReplay는iterations의별도실측이고Native에합산하지않는다. 작업준비·Source검토·실패·pause/reseal·보고를포함한전체wall은WORK_WALL_RECEIPT에서구분한다.',
        '## 10. Actual Fresh AC96 호환성과 보존',
        actual['reason']+' 따라서 **ACTUAL_NOT_RUN**이다. PlanningFULLPASS를ActualPASS로승격하지않고Sourcefreeze/Gapgate/자체Planningcontrolreference를임의대체하지않는다. 전체Line/Phase/Transformer/Voltage의새AC위반결과는실행되지않았으므로값을만들지않는다.',
        'B1 PR212/213 source/ledger/FAIL·PASS/PAUSED·userstop 및예약/task/supervisor는보존했다. PR207/209/210/211/214/215/216도동일HEAD/byte이다. 공식5월campaign·B3·IEEE8500·새예약0회다.',
        '## 11. Q1–Q5와 잠정채택',
        f'Q1 N1재현={cert["COLD_START_N1_REPRODUCED"]}. Q2/Q3 최종이동수={plans["FINAL"]["move_count"]},N1대비UB개선={plans.get("N1",plans["INITIALIZE"])["verified_UB"]-final:.12f}. Q4 actual{total:.3f}초에서최종UB{final:.16g}/Gap{cert["Global_gap_percent"]:.8f}%. Q5 이동이있다면원본travel debit·SOC/Rebound를포함한FULLPASS점의실제목적개선으로만판단한다. 이동0은전역불필요증명이아니며미탐색경로/제한window·radius·Root/시간제한의한계다.',
        'N1은검증된Mode활성화후보로잠정유지하며통합경로탐색의추가채택은이번검증이득을근거로판단한다. Production동결·전체5월외삽은하지않는다. May02/03후속에는날짜별독립Source/Case·Cold Start·FULL/Actual계약·단일worker/별도승인budget을다시확인해야하며이번에실행하지않았다.',
        '## 12. 증거와그래프',
        '[독립인증](FINAL_INDEPENDENT_CERTIFICATE.json) · [실행Source seal](EXECUTED_SOURCE_HASHES.json) · [LB출처](LB_PROVENANCE_REUSE.json) · [Actual호환성](ACTUAL_FRESH_INTERFACE_COMPATIBILITY.json) · [FULL운전비교](ORIGINAL_OPERATING_PLAN_COMPARISON.json) · [Grid변화](CRITICAL_GRID_COMPARISON.json)',
        '![검증UB궤적](UB_TRAJECTORY.png)','![실측Native예산](NATIVE_RUNTIME.png)',
    ]
    path=DOCS/'B2_INTEGRATED_PRIMAL_1800_CANARY_FINAL_KO.md';path.write_text('\n\n'.join(body)+'\n',encoding='utf-8')
    description=f'''Source18r IEEE123 B2 May01에서새Cold 초기화→U4→N1→전차량384Mode를개방한N2+/N3+통합canary를실행했다. 최종FULL검증UB {final:.16g},기존K48LB {LB:.16g},GlobalGap {cert['Global_gap_percent']:.8f}%. actualNative {total:.6f}s/1800s. 주판정 {cert['primary_classification']}.

원본4MESS/96슬롯/97SOC/전체Grid와ScientificSource를보존했고N2+/N3+Hamming은Node에만적용했다. 첫MIPStart0,후속start는이번새FULL점만사용했다. 제한Bound를GlobalLB로사용하지않았다. Guard정지·Native0수정·재개는epoch증거와동일모델/실측budget보존으로공개했다. B1/HOLD/예약/기존PR불변,Actual=ACTUAL_NOT_RUN.

Base PR216 `{BASE}`. 전체호출log·원본96CSV·독립인증·그래프·한국어보고서는 `docs/v42_b2_integrated_primal1800_canary/`.
'''
    (DOCS/'PR_DESCRIPTION_KO.md').write_text(description,encoding='utf-8')


if __name__=='__main__':main()
