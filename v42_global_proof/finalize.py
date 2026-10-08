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
    native_by_unit={r['MESS']:r for r in vehicle['vehicles']};vehicle_details=[]
    for r in capacity['selected']['vehicles']:
        n=native_by_unit[r['MESS']];data=dict(r,numerical_native=n)
        if n.get('local_incumbent_replay',{}).get('PASS'):
            lower=F(n['incumbent_support_exact_evaluation'])
            data.update(numerical_feasible_support_lower=float(lower),exact_DP_minus_numerical_feasible_support=float(F(r['U_exact'])-lower),
                numerical_incumbent_is_not_exact_rational_feasibility_certificate=True)
        vehicle_details.append(data)
    write(OUT/'VEHICLE_CAPACITY_GAP_DIAGNOSIS.json',dict(PASS=True,vehicles=vehicle_details,
        selected_grid_label=A['selected_label'],all_exact_upper_bounds_remain_analytical=True,
        native_MIP_ObjBound_is_not_an_independently_exact_upper_bound=True))
    write(OUT/'GLOBAL_INFEASIBILITY_PROOF.json',dict(status='CERTIFIED' if positive or temporal_positive else 'NOT_PROVEN',
        classification=classification,question='Does any original4MESS96slot integer plan achieve rho_max<=3/5?',
        exact_target='3/5',method_A=dict(D_exact=str(D),sum_U_exact=str(U),D_minus_sum_U_exact=str(D-U),
            strict_contradiction=positive,independent_checker='INDEPENDENT_GRID_CAPACITY_CHECK.json'),
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
        RAM_based_automatic_stop=False,MemLimit='default infinity',SoftMemLimit='default infinity',
        optimize_zero_analytical_DP_native_calls=0,unspent_budget_seconds=3600-runtime,
        no_reruns=True,other_tasks_untouched=True))
    trajectory=read(OUT/'CUTOFF_TRAJECTORY.json');last=trajectory['trajectory'][-1] if trajectory['trajectory'] else {}
    soc_improvement=sum(r.get('suffix_SOC_improvement',0) for r in capacity['selected']['vehicles'])
    report=[f'# M1 전역 가능성 검증 결과\n\n판정: **{classification}**. `rho_max ≤ 0.60`인 원본 정수 운전계획의 존재 여부는 '+
        ('독립 replay를 통과한 반례로 확인했다.' if feasible else '전역 모순으로 부정했다.' if positive or temporal_positive else '이번 증거로 확정하지 못했다. **NOT_PROVEN**을 유지한다.'),
        f'기존 Global LB **{LB:.16f}**, UB **{UB:.16f}** → LB **{new_lb:.16f}**, UB **{new_ub:.16f}**. 인증 Gap **{gap:.12f}%**, 목표0.5%, **M1_ACCEPTED={str(accepted).lower()}**. production·P2·downstream은 모두0회다.',
        '\n## 원본 동결과 인증 범위\n',
        f'PR188 exact HEAD `{BASE}`에서 D: 독립 worktree로 시작했다. C3A582,808행/306,040열/5,351,612nnz, 원본9,322binary,4MESS/24서비스지점/96×15분을 보존했다. 기존B2651행을 그대로 덧붙였다. 목적은 원래 `min rho_max`, ObjCon+0, objective SHA256 `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`다. 원본 계수·bounds·types·변수축·frozen A1·RouteTable·ML traffic authority를 exactHEAD Git blob 및 SHA로 대조했다.',
        '기존UB의 C3A·B2·전체inverse Route/SOC/PCS/PQ/Grid/A1 replay는 producer와 별도checker에서PASS다. nativecutoff는 원본MILP를 복원하고 `rho_cutoff_0p60` 한 행만 추가했다. 원본 binary를 LP로 바꾸거나경로·시점·차량배정을 고정하지 않았다. 모든새파일은 신규namespace에 있으며 기존 archivedevidence와 다른A/M프로세스를 수정하거나중단하지 않았다.',
        '저장된ROOT/PR167·169·179·182·187·188 계통행·primal/dual/RC 증거를 재사용했다. historical95행 시작정보와 실제저장101thermal descriptor 및B2active100행의 차이를 숨기지 않는다. sourcecensus를 기준으로 사용했고, allsecurity후보는 활성 voltage/transformer도 포함한다. 과거fractional해의 물리위반은 이번전역결론의 증명이 아니다.',
        '\n## A: Grid–Mobility Capacity Conflict\n',
        f'선택방향 `{A["selected_label"]}`에서 `support ≥ D(3/5)`의 **D={float(D):.16f}**. 원본 inequality에 비음수 multiplier를 곱하고 모든 grid binding등식을 affine RHS까지 정확히 소거했다. frozen grid/AIDC 상수는 그대로 포함한다. 원시Pi를 유효dual이라고가정하지 않고 inequalitysign cone을 새로검사했다. dyadic원본계수와 유리수3/5로 계산한 exact분수와 outwardbinary64 표시를 함께저장한다.',
        f'원본96슬롯 경로/준비시간/PCS/charge-discharge mode와 terminalenergy를 포함한 DP 상한에 SOC66/terminalSOC로부터 나온 suffix소비≤320kWh를 추가했다. **ΣU={float(U):.16f}**, **D−ΣU={float(D-U):.16f}**. SOCsuffix는 이전route/terminal상한을 합계{soc_improvement:.16f}만큼줄였으나 엄밀한양의모순이 성립하지 않는다. 중간SOC전체조건을 완전히푼상한이라고 주장하지 않는다.',
        '|MESS|엄밀DP상한U|NativeStatus|수치maxincumbent|수치MIP상한|\n|---|---:|---:|---:|---:|']
    for r in capacity['selected']['vehicles']:
        n=native_by_unit[r['MESS']]
        report.append(f'|{r["MESS"]}|{r["U_upper"]:.16f}|{n["Status"]}|{n.get("incumbent_support_float")}|{n.get("numerical_support_upper_after_conversion")}|')
    report += ['\n차량별native모델은 각차량의 모든원본physical행·경계·정수선택·96슬롯SOC·PCS와B2행을 유지했다. maximize의incumbent는지원능력상한이 아니다. native ObjBound도 독립exact tree증명이 없으므로 A3에채택하지 않았다. adopt한U는 별도checker가 polygonvertex/모든DAGedge potential/에너지등식으로 검증한엄밀상한이다. 수치incumbent와DP간차이는 `VEHICLE_CAPACITY_GAP_DIAGNOSIS.json`에서각차량별로분리한다.',
        '\n## B: Multi-Time Route/SOC Conflict\n',
        f'원본시간확장그래프53,626arc(이동51,322/STAY2,304),24지점 및4초기위치를검사했다. positive지원요구{temporal["positive_demand_row_count"]}행, critical시점{len(temporal["critical_slots"])}개. 단일시점모순{temporal["pointwise_contradiction_count"]}건, 두시점{temporal["two_time_test_count"]}조합중모순{temporal["two_time_contradiction_count"]}건이다. 모든차량의대체가능성을합산했다. 실제도달불가능한site쌍은존재하지만4대전체모순은증명하지못했다.',
        f'별도unit-multiplier필요량={temporal["necessary_support_inequality"]["demand"]:.12f}, SOC완화route상한={temporal["necessary_support_inequality"]["route_capacity_upper"]:.12f}. 이스케일은A의weighted방향과달라서숫자를직접비교하지않는다. 특정reward최대경로의SOC실패는상한느슨함의진단이며모든정수운전계획의불가능성을뜻하지않는다. F⊆R 및PCSoutward·transitPQ=0·pairreachability를독립checker가검증했다.',
        '\n## C: Original Cutoff Cross-Check\n',
        f'단일full-domaincutoff native상태={cutoff["Status"]}, SolCount={cutoff["SolCount"]}, NodeCount={cutoff["NodeCount"]}, Runtime={cutoff["Runtime"]:.6f}s, Work={cutoff["Work"]:.9f}. 독립판정={independent["classification"]}. 마지막관측open노드={last.get("unexplored_nodes")}. 실제분기변수전체목록은Gurobi callback에서노출하지않으므로미측정으로기록했다. NodeCount/로그/원시callback을실제처리영역증거로보존하며미처리영역을임의로제외하지않았다.',
        'TIME_LIMIT/noincumbent는불가능성이아니다. INFEASIBLE의수치MIP판정도독립exact모순과구분한다. solverStatus/최대처리노드/미해결영역은 `ORIGINAL_CUTOFF_RESULT.json`, native로그및trajectory에있다. native RHSbinary64(0.6)는3/5보다1/45035996273704960작다. 이것만으로exactdecimal경계불가능성을주장하지않는다.',
        '\n## 수치 손실과 구조적 완화, 다음 병목\n',
        f'새A/Bcertificate는exact분수연산으로gridstationarity·상수·rowcone을검사한다. 표시의outwardrounding만남으며D−ΣU의부호는exact로검사했다. 따라서이번실패를dual수치오차만으로설명할수없다. 기존GlobalLB와knownUB사이의gap은정수최적값미확정인상태의인증범위이며trueintegralitygap으로단정하지않는다. 0.5%를위해필요한LB는{UB*.995:.16f}, 추가개선은{max(0.,UB*.995-new_lb):.16f}다.',
        '다음실험에서먼저해결할병목은 **단일weightedgrid지원방향의분리강도**다. 정확한SOCsuffix가상한을크게줄여도grid요구와4대capacity의엄밀모순이남지않았다. 서로다른line/time의요구를한스칼라합으로합치는과정에서상호충돌이상쇄될수있다. native미완료와분리강도실패를구분하고, 이번실패알고리즘을production으로승격하지않는다. 추가실험은이번예산에서자동실행하지않는다.',
        '\n## 실행 예산과 재현\n',
        f'신규native{cutoff["native_calls"]+vehicle["native_calls"]}회, 누적Runtime **{runtime:.6f}s /3,600s**, Work{work:.9f}. cutoff최대1,200s, 각차량최대600s를지켰다. 등록TimeLimit1180/575s와time-onlybudgetreserve를사용했다. Threads=1/worker, 차량maxworkers=2. CPU/RSS/NativeRuntime/Work/ControllerWall을분리했고MemLimit/SoftMemLimit과RAM자동중단은추가하지않았다. A/B및checker의nativeoptimize는0회다.',
        '전체certificates는독립checker가검증했고잘못된sign/constant/types/objective/cutoff/supportuppermutation을거부했다. `python -m v42_global_proof.check_source_cutoff`, `python -m v42_global_proof.check_grid_capacity`, `python -m v42_global_proof.check_temporal`, `python -m v42_global_proof.check_vehicles`는저장증거검사만수행한다. 소비된ONCEtoken을삭제하거나cutoff/vehicles를재실행하지않는다.',
        '\n## Git 및 v42 후속 기준\n',
        '검증된신규변경만기존M브랜치에먼저commit하고PR188 exactHEAD위DraftPR로게시한다. 이후origin/v42의 V42_INTEGRATION_READY.json 및최종HEAD를확인한다. 준비완료시별도임시worktree에서신규namespace변경만반영하고A/M통합회귀전체PASS와무충돌인경우에만fast-forwardpush한다. 미준비/충돌/검증미통과면handoff문서로MHEAD·파일·결과·적용법을게시한다. force merge/push나실패알고리즘의production승격은없다. 이후개발기준은단일v42다. 최종Git/통합상태는handoff와최종대화에기록한다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
    write(OUT/'FINAL_SCIENTIFIC_VERIFICATION.json',dict(PASS=True,classification=classification,
        independent_source_cutoff=True,independent_grid_capacity=True,independent_temporal=True,independent_vehicle=True,
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
