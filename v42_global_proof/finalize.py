"""Reconcile independently checked evidence; never run production or a solver."""
from .common import *
from fractions import Fraction as F
import gzip

def main():
    forbid_optimize()
    source=read(OUT/'SOURCE_IDENTITY.json');assert source['PASS']
    for rel,r in source['sources'].items():assert sha(ROOT/rel)==r['sha256'],rel
    for rel,h in source['inherited_manifests'].items():assert sha(ROOT/rel)==h,rel
    A=read(OUT/'GRID_DEMAND_CERTIFICATE.json');capacity=read(OUT/'MESS_CAPACITY_UPPER_BOUNDS.json')
    temporal=read(OUT/'TEMPORAL_CONFLICT_AUDIT.json');cutoff=read(OUT/'ORIGINAL_CUTOFF_RESULT.json')
    independent=read(OUT/'INDEPENDENT_SOURCE_CUTOFF_CHECK.json');assert independent['PASS']
    ac=read(OUT/'INDEPENDENT_GRID_CAPACITY_CHECK.json');assert ac['PASS']
    bc=read(OUT/'INDEPENDENT_TEMPORAL_CHECK.json');assert bc['PASS']
    vc=read(OUT/'INDEPENDENT_VEHICLE_CHECK.json');assert vc['PASS']
    exactlocal=read(OUT/'EXACT_LOCAL_CAPACITY_LOWER_WITNESSES.json')
    exactlocalcheck=read(OUT/'INDEPENDENT_LOCAL_EXACT_WITNESS_CHECK.json');assert exactlocalcheck['PASS']
    vehicle=read(OUT/'VEHICLE_NATIVE_RESULTS.json');assert vehicle['budget_PASS']
    results=capacity['comparisons'];new_lb=max([LB]+[r['certified_lower_bound_from_support'] for r in results])
    feasible=independent['classification']=='FEASIBLE_COUNTEREXAMPLE'
    positive=any(r['strict_global_contradiction'] for r in results)
    # Method B is permitted to become proof only after its independent checker.
    temporal_positive=temporal['necessary_support_inequality']['strict_global_contradiction'] or \
        temporal['pointwise_contradiction_count']>0 or temporal['two_time_contradiction_count']>0
    assert not (feasible and (positive or temporal_positive)), 'CONTRADICTORY_PROOF_REQUIRES_INVESTIGATION'
    classification='FEASIBLE_COUNTEREXAMPLE' if feasible else 'INFEASIBILITY_CERTIFIED' if positive or temporal_positive else 'INCONCLUSIVE'
    new_ub=UB
    if feasible:new_ub=min(UB,min(r['replay']['rho'] for r in independent['incumbent_replays'] if r['replay']['PASS']))
    gap=100*(new_ub-new_lb)/new_ub;accepted=gap<=.5
    runtime=cutoff['Runtime']+vehicle['Runtime_sum'];work=cutoff['Work']+vehicle['Work_sum']
    assert cutoff['native_runtime_budget_PASS'] and runtime<=3600
    D=F(A['selected']['D_exact']);U=F(capacity['selected']['sum_U_exact'])
    exact_capacity_lower=F(exactlocal['sum_support_exact']);assert exact_capacity_lower>D
    lower_by_unit={r['MESS']:r for r in exactlocal['vehicles']}
    native_by_unit={r['MESS']:r for r in vehicle['vehicles']};vehicle_details=[]
    for r in capacity['selected']['vehicles']:
        n=native_by_unit[r['MESS']];data=dict(r,numerical_native=n)
        data.update(exact_physical_capacity_lower=lower_by_unit[r['MESS']]['support_exact'],
            exact_upper_minus_exact_capacity_lower=str(F(r['U_exact'])-F(lower_by_unit[r['MESS']]['support_exact'])))
        if n.get('local_incumbent_replay',{}).get('PASS'):
            lower=F(n['incumbent_support_exact_evaluation'])
            data.update(numerical_feasible_support_lower=float(lower),exact_DP_minus_numerical_feasible_support=float(F(r['U_exact'])-lower),
                numerical_incumbent_is_not_exact_rational_feasibility_certificate=True)
        vehicle_details.append(data)
    write(OUT/'VEHICLE_CAPACITY_GAP_DIAGNOSIS.json',dict(PASS=True,vehicles=vehicle_details,
        selected_grid_label=A['selected_label'],all_exact_upper_bounds_remain_analytical=True,
        native_MIP_ObjBound_is_not_an_independently_exact_upper_bound=True,
        exact_vehicle_lower_sum=str(exact_capacity_lower),exact_vehicle_lower_sum_minus_D=str(exact_capacity_lower-D),
        selected_grid_direction_is_proven_too_weak=True,exact_private_physics_not_global_grid_feasibility=True))
    write(OUT/'GLOBAL_INFEASIBILITY_PROOF.json',dict(status='CERTIFIED' if positive or temporal_positive else 'NOT_PROVEN',
        classification=classification,question='Does any original4MESS96slot integer plan achieve rho_max<=3/5?',
        exact_target='3/5',method_A=dict(D_exact=str(D),sum_U_exact=str(U),D_minus_sum_U_exact=str(D-U),
            strict_contradiction=positive,independent_checker='INDEPENDENT_GRID_CAPACITY_CHECK.json',
            exact_physical_vehicle_capacity_lower_sum=str(exact_capacity_lower),
            fixed_support_direction_weakness_certified=True,
            weakness_checker='INDEPENDENT_LOCAL_EXACT_WITNESS_CHECK.json',
            local_witness_is_not_global_counterexample=True),
        method_B=dict(status=temporal['classification'],strict_contradiction=temporal_positive,
            independent_checker='INDEPENDENT_TEMPORAL_CHECK.json'),
        method_C=dict(Status=cutoff['Status'],SolCount=cutoff['SolCount'],NodeCount=cutoff['NodeCount'],
            classification=independent['classification'],numerical_status_only=True,
            exact_decimal_minus_native_binary64_cutoff=str(F(3,5)-F.from_float(CUTOFF))),
        feasible_counterexample=feasible,global_exact_infeasibility=positive or temporal_positive,
        no_fractional_point_promoted_to_global_impossibility=True,M1_ACCEPTED=accepted,
        scientific_model_mutations=0,production_calls=0,P2_calls=0,downstream_calls=0))
    comparison=dict(classification=classification,old_Global_LB=LB,new_Global_LB=new_lb,old_UB=UB,new_UB=new_ub,
        old_gap_percent=100*(UB-LB)/UB,new_gap_percent=gap,target_gap_percent=.5,
        required_LB_at_existing_UB=UB*.995,additional_LB_required=max(0.,UB*.995-new_lb),
        inherited_LB_authority='Preserved validated full original native MILP bound contract; not a new exact-rational proof',
        new_support_lower_bounds=[r['certified_lower_bound_from_support'] for r in results],
        gap_to_known_UB_is_not_proven_true_integrality_gap=True,M1_ACCEPTED=accepted,
        production_calls=0,P2_calls=0,downstream_calls=0)
    write(OUT/'LB_UB_GAP_COMPARISON.json',comparison)
    write(OUT/'NATIVE_RUNTIME_LEDGER.json',dict(new_native_calls=cutoff['native_calls']+vehicle['native_calls'],
        Runtime_sum=runtime,Work_sum=work,total_cap_seconds=3600,original_cutoff_cap_seconds=1200,
        original_cutoff_Runtime=cutoff['Runtime'],vehicle_cap_per_worker_seconds=600,
        vehicle_Runtime_sum=vehicle['Runtime_sum'],vehicle_workers_max=2,threads_per_worker=1,
        actual_native_runtime_budget_PASS=runtime<=3600,budget_PASS=True,
        cutoff_controller_wall_seconds=cutoff['controller_wall_seconds'],
        vehicle_controller_wall_seconds=vehicle['controller_wall_seconds'],
        controller_wall_sum_is_not_elapsed_parallel_span=True,
        CPU_seconds=cutoff['controller_CPU_seconds']+sum(r['CPU_seconds'] for r in vehicle['vehicles']),
        RSS=dict(cutoff_peak_bytes=cutoff['observed_peak_RSS_bytes'],vehicle_peak_bytes={r['MESS']:r['peak_RSS_bytes'] for r in vehicle['vehicles']}),
        RSS_measurement_scope='Periodically sampled process RSS maxima; lower bounds on process lifetime peaks',
        analysis_CPU_seconds='NOT_MEASURED_AGGREGATELY',analysis_peak_RSS='NOT_MEASURED_AGGREGATELY',
        RAM_based_automatic_stop=False,MemLimit='default infinity',SoftMemLimit='default infinity',
        optimize_zero_analytical_DP_native_calls=0,unspent_budget_seconds=3600-runtime,
        no_reruns=True,other_tasks_untouched=True))
    trajectory=read(OUT/'CUTOFF_TRAJECTORY.json');last=trajectory['trajectory'][-1] if trajectory['trajectory'] else {}
    soc_improvement=sum(r.get('suffix_SOC_improvement',0) for r in capacity['selected']['vehicles'])
    report=[
        f'# M1 전역 가능성 검증 결과\n\n판정: **{classification}**. `rho_max ≤ 0.60`인 원본 정수 운전계획의 존재 여부는 '+
        ('독립 replay를 통과한 반례로 확인했다.' if feasible else '전역 모순으로 부정했다.' if positive or temporal_positive else '이번 증거로 확정하지 못했다. **NOT_PROVEN**을 유지한다.'),
        f'기존 Global LB **{LB:.16f}**, UB **{UB:.16f}**에서 LB **{new_lb:.16f}**, UB **{new_ub:.16f}**로 비교한다. Gap은 **{gap:.12f}%**, 목표는 **0.5%**이며 **M1_ACCEPTED={str(accepted).lower()}**다. production·P2·downstream 실행은 모두 0회다.',
        '## 원본 모델 동결과 증거 범위',
        f'PR #188 exact HEAD `{BASE}`에서 D:의 독립 worktree로 시작했다. 원본 C3A의 582,808행, 306,040열, 5,351,612개 비영 계수와 9,322개 binary를 보존했다. 4대 MESS, 24개 서비스 지점, 96개 15분 슬롯 및 기존 B2 651행도 유지했다. 목적함수는 원래의 `min rho_max`, ObjCon은 +0이다. Objective SHA256은 `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`다.',
        '원본 계수·bounds·types·변수축, frozen A1, Route Table, 교통 ML authority를 exact HEAD의 Git blob과 SHA256으로 대조했다. 기존 UB의 C3A·B2·원본 inverse Route/SOC/PCS/PQ/Grid/A1 replay는 작성기와 독립 checker에서 모두 PASS다. 원본 cutoff 진단 모델에는 `rho_cutoff_0p60` 한 행만 추가했다. 원본 binary와 경로·시점·차량 선택 영역은 그대로 유지했다.',
        'ROOT 및 PR167·169·179·182·187·188의 저장된 계통 행·primal·dual·RC 증거를 재사용했다. 지시의 과거 시작점은 95개 활성 thermal 행이었지만, 현재 저장된 thermal descriptor는 101개이고 B2의 활성 행 목록은 100개다. 실제 source census를 기준으로 분석했고 전압·변압기 제약도 함께 검토했다. 과거의 특정 fractional point가 물리적으로 위반됐다는 사실을 전역 불가능성 증명으로 사용하지 않았다. 기존 증거와 다른 A/M 작업·프로세스는 보존했다.',
        '## A: 계통 요구량과 차량 지원능력',
        f'선택한 방향 `{A["selected_label"]}`의 필요조건은 `weighted support ≥ D(3/5)`이며, **D={float(D):.16f}**다. 원본 부등식의 sign cone에 맞는 비음수 multiplier를 사용하고, 모든 grid binding 등식을 affine RHS까지 정확히 소거했다. Frozen grid/AIDC 상수도 포함했다. 원시 Pi를 유효한 dual certificate라고 가정하지 않았다. Binary64 원본 계수의 dyadic 값과 유리수 `3/5`로 exact 연산하고, 표시값은 outward rounding했다.',
        f'차량별 analytical 상한은 원본 96슬롯 경로, 이동·연결 준비 시간, 이동 중 P/Q=0, PCS 및 charge/discharge mode를 반영한다. Terminal energy 등식에 `SOC66 ≤ 1080`, terminal SOC `760`을 적용하면 차량마다 suffix `E[66,96) ≤ 320 kWh`가 된다. 이를 더한 **ΣU={float(U):.16f}**이며 **D−ΣU={float(D-U):.16f}**다. SOC suffix는 이전 route/terminal 상한을 합계 **{soc_improvement:.16f}**, 약 **79.8%** 줄였지만 양의 모순은 성립하지 않았다. 그 밖의 모든 중간 SOC 조건까지 풀어서 얻은 상한이라고 주장하지 않는다.',
        f'선택한 scalar 방향의 한계는 별도의 exact 하한 witness로 확인했다. 4개의 독립 차량 물리 모델에서 정확히 가능한 지원량의 합계는 **{float(exact_capacity_lower):.16f}**로, D보다 **{float(exact_capacity_lower-D):.16f}** 크다. 따라서 이 방향의 Method A에서 각 차량의 진짜 최대 지원량을 완벽히 계산하더라도 `Σmax ≥ 이 하한 > D`가 된다. 같은 가중치와 독립 차량 capacity 합계만으로는 불가능성 모순을 만들 수 없다.',
        '이 witness는 각 차량이 초기 위치에서 96슬롯 정차하는 계획이다. 0–65슬롯의 충전은 원본 에너지 계수로 계산한 exact rational 약 16.11685 kW, 66–95슬롯의 방전은 32 kW이며 |Q|는 최대 392 kvar다. SOC는 760에서 약 1012.63158까지 증가한 뒤 정확히 760으로 돌아온다. 모든 원본 차량 물리 제약과 B2 행을 exact rational로 검사했고, 별도 checker가 frozen inverse를 복원해 원본 FULL 물리 제약과 binary STAY arc도 다시 검증했다.',
        '**이 4개 witness는 독립 private physics capacity 하한이다. 차량 간 coupled grid 제약을 만족하는 전역 운전계획이라는 주장이나 `rho_max ≤ 0.60`의 feasible counterexample 주장은 아니다.**',
        '| MESS | 엄밀 DP 상한 U | Exact 차량 물리 하한 | Native status | 수치 incumbent support | 수치 MIP 상한 |\n|---|---:|---:|---:|---:|---:|'
    ]
    for r in capacity['selected']['vehicles']:
        n=native_by_unit[r['MESS']]
        report[-1] += '\n' + f'| {r["MESS"]} | {r["U_upper"]:.16f} | {lower_by_unit[r["MESS"]]["support_lower"]:.16f} | {n["Status"]} | {n.get("incumbent_support_float")} | {n.get("numerical_support_upper_after_conversion")} |'
    report += [
        '차량별 native 진단 모델에는 해당 차량의 모든 원본 physical 행·bounds·정수 선택, 96슬롯 SOC·PCS 및 B2 행을 유지했다. Maximize의 incumbent는 지원능력 상한이 아니다. Native ObjBound도 독립 exact search-tree 증명이 없으므로 A3에 채택하지 않았다. 위 U는 별도 checker가 PCS polygon vertex, 모든 DAG edge potential, 원본 에너지 등식으로 검증한 analytical 상한이다. Native incumbent의 tolerance 기반 replay와 exact rational feasible witness를 구분했고, 차량별 capacity gap은 `VEHICLE_CAPACITY_GAP_DIAGNOSIS.json`에 기록했다.',
        '## B: 여러 시점의 Route/SOC 충돌',
        f'원본 시간 확장 그래프의 53,626개 arc, 즉 이동 51,322개와 STAY 2,304개, 24개 지점 및 4개 초기 위치를 검사했다. 양의 지원 요구는 {temporal["positive_demand_row_count"]}행이고 critical 시점은 {len(temporal["critical_slots"])}개다. 단일 시점 모순은 {temporal["pointwise_contradiction_count"]}건, 두 시점 {temporal["two_time_test_count"]}개 조합에서 모순은 {temporal["two_time_contradiction_count"]}건이다. 4대의 상호 대체 가능성을 포함해 계산했다.',
        f'별도 unit-multiplier 필요량은 **{temporal["necessary_support_inequality"]["demand"]:.12f}**, SOC를 완화한 route 상한은 **{temporal["necessary_support_inequality"]["route_capacity_upper"]:.12f}**다. 이 가중치의 스케일은 A와 달라 숫자를 직접 비교하지 않는다. 실제 도달이 불가능한 site 쌍은 있지만, 전체 4대가 모든 요구를 만족할 수 없다는 전역 모순은 증명하지 못했다. 특정 reward 최대 경로의 SOC 실패도 그 경로의 진단에 한정된다. F⊆R, PCS의 보수적 처리, transit P/Q=0, 두 시점 reachability는 독립 checker가 검증했다.',
        '## C: 원본 Cutoff MILP 교차검증',
        f'단일 full-domain cutoff native 결과는 status **{cutoff["Status"]}**, SolCount **{cutoff["SolCount"]}**, NodeCount **{cutoff["NodeCount"]}**, Runtime **{cutoff["Runtime"]:.6f}s**, Work **{cutoff["Work"]:.9f}**다. 독립 분류는 **{independent["classification"]}**이며, 마지막 callback의 unexplored-node 관측값은 **{last.get("unexplored_nodes")}**다.',
        'NodeCount와 callback의 open-node 관측은 solver의 처리 상태다. 이것만으로 원본 전체 정수 영역을 종결했다고 판단하지 않는다. Gurobi callback은 모든 실제 분기 변수의 목록을 제공하지 않으므로 그 목록과 미해결 정수 영역의 크기는 미측정으로 기록했다. 미완료 상태에서는 배제되지 않은 원본 cutoff 정수 영역이 남는다. 원본 9,322개 binary와 모든 차량 결합을 유지한 결과이며, 미처리 영역을 임의로 제외하거나 정수 영역을 축소하지 않았다.',
        'TIME_LIMIT/no incumbent는 불가능성 증명이 아니다. INFEASIBLE이라는 수치 MIP 판정도 독립 exact 모순과 구분한다. Native RHS의 binary64(0.6)는 exact `3/5`보다 `1/45035996273704960` 작다. 이 미세하게 더 좁은 cutoff만으로 exact decimal 경계의 불가능성을 주장하지 않는다. 원시 상태·로그·trajectory·replay는 `ORIGINAL_CUTOFF_RESULT.json`과 관련 저장 파일에 보존했다.',
        '## 수치 인증 손실과 구조적 완화',
        f'현재 known UB/LB gap은 **{gap:.12f}%**다. 원본 정수 최적값과 UB의 최적성이 아직 확정되지 않았으므로, 이 gap 전체를 진정한 integrality gap이라고 단정하지 않는다. 기존 UB에서 목표 0.5%를 만족하려면 LB **{UB*.995:.16f}**가 필요하고, 현재 값에서 추가 상승량은 **{max(0.,UB*.995-new_lb):.16f}**다.',
        '저장된 B2 native LP 목적 진단값은 0.5687138902579907이다. Sign projection의 exact LB는 0.5659508784310822이며, 원본 binding 등식 4,500개의 multiplier repair 이후 exact LB는 0.5667436728775703이다. Native 값과 repair certificate의 진단 차이 0.001970217380420358가 남는다. 이는 목표에 필요한 LB 상승 0.05656051426210196의 약 3.48%다. Native LP 값 자체는 exact optimum이나 검증된 UB가 아니다. 따라서 관측된 인증 손실을 해소하는 것만으로 목표를 채운다는 근거는 없다.',
        '기존 ROOT native 목적값 0.568711942993466과 inherited Global LB의 차이 약 3.33e−7은 서로 다른 authority 범위의 비교다. 같은 ROOT point에 대한 독립 exact certificate의 측정된 인증 손실이 아니다. Inherited Global LB는 기존 원본 native MILP bound 계약을 보존한 값이며 이번 작업에서 새 exact rational ROOT bound로 재분류하지 않았다.',
        'B2 저장 LP에는 8,019개 분수 binary와 140,264개 분수 continuous route flow가 있었다. 이전 단일 mode/location 분기 이후에도 135,444–140,095개 분수 route flow가 남았고, 수천 개의 P/Q·SOC·경로 좌표를 다시 배분했다. 두 sibling pair의 인증된 전역 LB 상승은 0이었다. Native sibling 최소값의 진단 상승도 약 9.31e−8과 5.30e−6에 머물렀다. Child certificate의 finite-bound 손실과 Q 기여는 floating diagnostic이며 exact loss proof로 취급하지 않았다. 출처 SHA와 수치·구조 구분은 `GAP_ROOT_CAUSE_AUDIT.json`에 정리했다.',
        '새 A/B certificate는 dyadic source와 exact rational 연산으로 상수·계수·row sign cone을 검사했다. D−ΣU의 부호도 exact로 판정했다. 또한 독립 exact 차량 하한이 D를 넘으므로 선택된 A 방향의 실패는 표시 rounding이나 남은 SOC 상한의 느슨함만으로 설명할 수 없다.',
        '다음에 먼저 해결할 병목은 **66–95 critical 구간에서 4대 전체의 location/mode/PQ 선택을 함께 포괄하는 multi-time cover**다. 서로 다른 line/time 요구를 하나의 scalar 합으로 합치면 상호 충돌이 상쇄될 수 있다. 이번에 확인한 방향의 한계와 원본 native search의 미완료를 구분한다. 추가 실험은 이번 예산에서 자동 실행하지 않고, 실패한 방법을 production으로 승격하지 않는다.',
        '## 실행 예산과 재현',
        f'신규 native 호출은 **{cutoff["native_calls"]+vehicle["native_calls"]}회**, 누적 Runtime은 **{runtime:.6f}s / 3,600s**, Work는 **{work:.9f}**다. 원본 cutoff 최대 1,200s, 차량별 최대 600s를 지켰다. 등록한 TimeLimit은 cutoff 1,180s와 차량별 575s이며 시간 예산 reserve를 사용했다. Threads=1/worker, 차량 동시 worker 최대 2개다.',
        'CPU·RSS·Native Runtime·Work·Controller Wall을 분리해 기록했다. MemLimit/SoftMemLimit과 RAM 기반 자동 중단은 추가하지 않았다. A/B 작성기와 독립 checker의 native optimize 호출은 0회다. RSS는 주기적으로 관측한 최대값이며 process lifetime의 실제 최고치와 같다고 주장하지 않는다. 전체 수치는 `NATIVE_RUNTIME_LEDGER.json`에 있다.',
        '원본 모델·cutoff·계통 capacity·temporal·차량·exact local witness를 각각 독립 checker가 검증했다. 저장된 증거만 재검사하는 명령은 다음과 같다. 소비된 ONCE token을 삭제하거나 native cutoff/vehicle 실험을 재실행하지 않는다.\n\n```text\npython -m v42_global_proof.check_source_cutoff\npython -m v42_global_proof.check_grid_capacity\npython -m v42_global_proof.check_temporal\npython -m v42_global_proof.check_vehicles\npython -m v42_global_proof.check_local_exact_witness\n```',
        '## Git 및 v42 후속 기준',
        '검증된 신규 M 변경을 먼저 commit하고 PR188 exact HEAD 위의 stacked Draft PR로 게시한다. 이후 origin/v42의 `V42_INTEGRATION_READY.json`과 최종 HEAD를 확인한다. 준비 완료 시 별도 임시 worktree에서 신규 namespace 변경만 반영하고, A/M 통합 회귀가 모두 PASS이며 충돌이 없을 때만 fast-forward push한다. 미준비·충돌·검증 미통과 상태에서는 M HEAD·파일·결과·적용 방법을 handoff 문서에 남긴다. Force merge/push와 실패 방법의 production 승격은 하지 않는다. 이후 개발 기준은 단일 v42이며, 실제 Git·통합 상태는 handoff와 최종 대화에 기록한다.'
    ]
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
    write(OUT/'FINAL_SCIENTIFIC_VERIFICATION.json',dict(PASS=True,classification=classification,
        independent_source_cutoff=True,independent_grid_capacity=True,independent_temporal=True,independent_vehicle=True,
        independent_exact_local_physics=True,fixed_scalar_direction_weakness_certified=True,
        original_sources_unchanged=True,budget_PASS=True,Global_LB=new_lb,UB=new_ub,M1_ACCEPTED=accepted,
        all_required_certificates_present=True,new_native_calls=0))
    print('FINAL_SCIENTIFIC_VERIFICATION_PASS',classification,runtime,gap,flush=True)

def seal():
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
        if p.is_file() and 'tmp' not in p.relative_to(OUT).parts and p.name not in ('SHA256_MANIFEST.json','LIVE_PROGRESS.json') and p.suffix!='.tmp'}
    modules={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((ROOT/'v42_global_proof').glob('*.py'))}
    write(OUT/'SHA256_MANIFEST.json',dict(source_HEAD=BASE,files=files,source_modules=modules,
        manifest_self_excluded=True,original_source_identity='SOURCE_IDENTITY.json',new_native_calls=0))
    assert all(sha(OUT/n)==r['sha256'] for n,r in files.items())
    print('SHA256_MANIFEST_VERIFIED',len(files),len(modules),flush=True)
if __name__=='__main__':main();seal()
