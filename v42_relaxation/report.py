"""Evidence-driven final receipts and the requested Korean review."""
import xml.etree.ElementTree as ET
from .base import *
from .lp import records

REQUIRED='README.md PREREGISTRATION.json PR108_BASE_RECEIPT.json PR108_A1_ANCHOR_REUSE.json PR108_MIP_START_RECEIPT.json BASE_F3_IDENTITY.json BASE_ROOT_LP_OPTIMIZATION.json BASE_ROOT_LP_SOLUTION_SUMMARY.json BASE_ROOT_LP_SOLUTION.npz ROOT_FRACTIONALITY_BY_FAMILY.csv ROOT_ROUTE_SPLIT_AUDIT.csv ROOT_ROUTE_SPLIT_SUMMARY.json MODE_HULL_ROOT_VIOLATIONS.csv MODE_HULL_ROOT_SUMMARY.json ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json ROOT_ENERGY_DISAGGREGATION_IIS.json STRENGTHENING_CANDIDATES.json S1_MODE_HULL_FORMULATION.md S2_ARC_ENERGY_FORMULATION.md INTEGER_PROJECTION_PROOF.md BOUNDED_INTEGER_EQUIVALENCE.csv PR108_INCUMBENT_EXTENSION.json STRUCTURAL_COMPARISON.csv ROOT_LP_STRENGTHENING_COMPARISON.csv ROOT_BOUND_GAIN_REPORT.json SELECTED_STRENGTHENING.json MIP_CANARY_OPTIMIZATION.json MIP_CANARY_PROGRESS.csv MIP_CANARY_SOLVER.display.txt MIP_CANARY_SOLVER.raw.gz M1_PRODUCTION_OPTIMIZATION.json M1_PRODUCTION_PROGRESS.csv M1_PHYSICAL_VALIDATION.json M1_ROBUST_VOLTAGE_REPORT.json M1_Q_UTILIZATION.csv RESIDUAL_RELAXATION_DIAGNOSIS.json NEXT_MODIFICATIONS.md FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json'.split()

QUESTIONS=['현재 blocker는 왜 단순 solver runtime 문제가 아닌가?','PR108 UB는?','PR108 LB는?','현재 gap은?',
 '0.5%를 위해 대략 어느 LB가 필요한가?','baseline F3 root LP를 정확히 재현했는가?',
 'root에서 fractional stay arc는 몇 개인가?','fractional travel arc는?','fractional charge_mode는?',
 '한 시점에 최대 몇 site로 fractional split되는가?','route splitting이 얼마나 빈번한가?',
 'H1/H2/H3 valid inequality는 무엇인가?','baseline root가 H1을 위반하는가?','H2를 위반하는가?','H3를 위반하는가?',
 '최대 위반량은?','mode hull을 왜 실행하거나 생략했는가?','mode hull은 integer feasible set을 바꾸는가?',
 'energy pooling hypothesis는 무엇인가?','fixed-root energy-flow LP는 feasible했는가?','infeasible이면 무엇을 의미하는가?',
 'feasible이면 왜 S2를 실행하지 않는가?','arc-energy G 변수의 물리적 의미는?','travel arc에서 energy는 어떻게 변하는가?',
 'stay arc에서 energy는 어떻게 변하는가?','terminal SOC는 어떻게 보존되는가?','S2가 original SOC를 대체했는가?',
 'integer physical projection equivalence는 PASS인가?','PR108 incumbent는 모든 candidate에서 feasible한가?',
 '각 candidate의 rows/columns/nonzeros는?','각 candidate의 root LP LB는?','각 candidate의 delta LB는?','implied gap은?',
 'selected strengthening은?','selection 이유는?','LB가 0.62 이상 올라갔는가?','LB가 0.65 이상 올라갔는가?',
 'root strengthening이 material했는가?','MIP canary를 실행했는가?','canary 300초 BestBd/gap은?',
 'canary 600초 BestBd/gap은?','production이 authorized됐는가?','production을 실행했는가?','final P1 gap은?',
 'P2를 실행했는가?','physical validation은 PASS인가?','robust voltage는 PASS인가?',
 'original route/SOC/PCS physics가 바뀌었는가?','아직 남은 relaxation weakness는 무엇인가?','A2를 왜 실행하지 않았는가?']

def absent(prefix,reason):
    if (OUT/(prefix+'_OPTIMIZATION.json')).exists():return
    dump(prefix+'_OPTIMIZATION.json',dict(run=False,optimize_calls=0,reason=reason,passes=[]))
    table(prefix+'_PROGRESS.csv',[],['component_seconds','incumbent','bound','gap','nodes','status'])
    (OUT/(prefix+'_SOLVER.display.txt')).write_text('NOT RUN: '+reason+'\n',encoding='utf8')
    (OUT/(prefix+'_SOLVER.raw.gz')).write_bytes(gzip.compress(b'',mtime=0))

def checkpoint(seconds):
    with (OUT/'MIP_CANARY_PROGRESS.csv').open(encoding='utf8') as f:rows=list(csv.DictReader(f))
    eligible=[r for r in rows if r.get('component_seconds') and float(r['component_seconds'])<=seconds and r.get('bound')]
    if not eligible:return dict(seconds=seconds,bound=None,gap=None,reason='No prior bound observation')
    r=max(eligible,key=lambda r:float(r['component_seconds']))
    return dict(seconds=seconds,bound=float(r['bound']),gap=float(r['gap']) if r.get('gap') else None,
        sampled_seconds=float(r['component_seconds']),callback_age_seconds=float(r['observation_age_seconds']) if r.get('observation_age_seconds') else None)

def run():
    recovery=read(OUT/'S3_NUMERICAL_RECOVERY.json') if (OUT/'S3_NUMERICAL_RECOVERY.json').exists() else None
    interior_recovery=read(OUT/'S3_INTERIOR_RECOVERY.json') if (OUT/'S3_INTERIOR_RECOVERY.json').exists() else None
    capture=read(OUT/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json') if (OUT/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json').exists() else None
    selected=read(OUT/'SELECTED_STRENGTHENING.json');root=read(OUT/'BASE_ROOT_LP_OPTIMIZATION.json');comparisons=records()
    fraction={r['family']:r for r in csv.DictReader((OUT/'ROOT_FRACTIONALITY_BY_FAMILY.csv').open(encoding='utf8'))}
    route=read(OUT/'ROOT_ROUTE_SPLIT_SUMMARY.json');mode=read(OUT/'MODE_HULL_ROOT_SUMMARY.json')
    energy=read(OUT/'ROOT_ENERGY_DISAGGREGATION_FEASIBILITY.json');labels=read(OUT/'STRENGTHENING_CANDIDATES.json')['authorized']
    energy_certificate=read(OUT/'ROOT_ENERGY_INTERVAL_CERTIFICATE.json')
    energy_margin=max(c['contradiction_margin_kWh'] for c in energy_certificate['certificates'])
    exact=read(OUT/'BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json');extension=read(OUT/'PR108_INCUMBENT_EXTENSION.json')
    if selected['material']:
        assert (OUT/'MIP_CANARY_OPTIMIZATION.json').exists() and read(OUT/'MIP_CANARY_OPTIMIZATION.json')['run'], 'AUTHORIZED_CANARY_STILL_REQUIRED'
    reason='All valid strengthening root gains are below .001; mandatory STOP before MIP canary.'
    absent('MIP_CANARY',reason)
    canary=read(OUT/'MIP_CANARY_OPTIMIZATION.json');canary_run=canary['run']
    if not (OUT/'PRODUCTION_AUTHORIZATION.json').exists():
        dump('PRODUCTION_AUTHORIZATION.json',dict(authorized=False,reason='No authorized proof canary',canary_run=False))
    gate=read(OUT/'PRODUCTION_AUTHORIZATION.json')
    if gate['authorized']:
        assert (OUT/'M1_PRODUCTION_OPTIMIZATION.json').exists() and read(OUT/'M1_PRODUCTION_OPTIMIZATION.json')['run'], 'AUTHORIZED_PRODUCTION_STILL_REQUIRED'
    absent('M1_PRODUCTION','Production gate not passed; no production solve.')
    production=read(OUT/'M1_PRODUCTION_OPTIMIZATION.json');production_run=production['run']
    prior=read(OUT/'PR108_MIP_START_RECEIPT.json')
    if not production_run:
        dump('M1_PHYSICAL_VALIDATION.json',dict(run=False,new_production_validation=False,
            retained_PR108_incumbent_validation=prior['physical'],retained_incumbent_PASS=prior['physical']['PASS']))
        dump('M1_ROBUST_VOLTAGE_REPORT.json',dict(run=False,new_production_validation=False,
            retained_PR108_incumbent_validation=prior['grid'],retained_incumbent_PASS=prior['grid']['PASS']))
        table('M1_Q_UTILIZATION.csv',[],['MESS','time','site','P','Q','Q_utilization','status'])
    chosen=production if production_run else canary if canary_run else None
    p=chosen['passes'][0] if chosen else dict(incumbent=UB,bound=LB,gap=(UB-LB)/UB,quality_PASS=False)
    physical=read(OUT/'M1_PHYSICAL_VALIDATION.json');grid=read(OUT/'M1_ROBUST_VOLTAGE_REPORT.json')
    physical_pass=physical['PASS'] if production_run else prior['physical']['PASS']
    robust_pass=grid['PASS'] if production_run else prior['grid']['PASS']
    complete=production.get('complete',False)
    accepted=bool(production_run and complete and physical_pass and robust_pass)
    flags=dict(BASE_PR=108,BASE_HEAD=HEAD,BASE_FORMULATION='M1-F3',BASE_F3_IDENTITY_PASS=read(OUT/'BASE_F3_IDENTITY.json')['PASS'],
        A1_RERUN=False,A1_ANCHOR_REUSED=True,A1_OPTIMIZE_CALLS_THIS_TASK=0,SCIENTIFIC_PHYSICS_CHANGED=False,
        ORIGINAL_INTEGER_PHYSICAL_SET_CHANGED=False,INTEGER_PHYSICAL_PROJECTION_IDENTICAL=True,LP_RELAXATION_IDENTICAL=False,
        BASE_ROOT_LP_BOUND=root['bound'],BASE_ROOT_LP_SECONDS=root['seconds'],
        FRACTIONAL_STAY_COUNT=int(fraction['stay_arcs']['fractional_count']),FRACTIONAL_TRAVEL_COUNT=int(fraction['travel_arcs']['fractional_count']),
        FRACTIONAL_CHARGE_MODE_COUNT=int(fraction['charge_mode']['fractional_count']),
        MAX_SIMULTANEOUS_FRACTIONAL_SITES=route['maximum_simultaneous_fractional_sites'],
        MODE_HULL_VIOLATION_COUNT=mode['violation_count'],MODE_HULL_MAX_VIOLATION=mode['maximum_violation'],
        MODE_HULL_CAN_IMPROVE_CURRENT_ROOT=mode['MODE_HULL_CAN_IMPROVE_CURRENT_ROOT'],ENERGY_POOLING_WITNESS=energy['ENERGY_POOLING_WITNESS'],
        INDEPENDENT_ENERGY_CERTIFICATE=energy_certificate['independent_arithmetic_certificate'],ENERGY_CERTIFICATE_MARGIN_KWH=energy_margin,
        S1_RUN='S1' in labels,S2_RUN='S2' in labels,S3_RUN='S3' in labels,INTEGER_PROJECTION_EQUIVALENCE_PASS=exact['PASS'] and extension['PASS'],
        SELECTED_STRENGTHENING=selected['selected'],SELECTED_ROOT_LP_BOUND=selected['selected_root_LB'],ROOT_LB_GAIN=selected['delta_LB'],
        IMPLIED_GAP_WITH_PR108_UB=selected['implied_gap'],MATERIAL_ROOT_BOUND_GAIN=selected['material'],
        MIP_CANARY_RUN=canary_run,MIP_CANARY_BEST_BOUND=canary['passes'][0]['bound'] if canary_run else None,
        MIP_CANARY_GAP=canary['passes'][0]['gap'] if canary_run else None,MIP_CANARY_NODES=canary['passes'][0]['nodes'] if canary_run else None,
        ROOT_LP_OPTIMIZE_CALLS=dict(S0=1,S1=1 if 'S1' in labels else 0,S2=1 if 'S2' in labels else 0,S3=(5 if capture else 3 if interior_recovery else 2 if recovery else 1) if 'S3' in labels else 0),
        S3_LP_INTERIOR_FALLBACK_ATTEMPTED=bool(interior_recovery),S3_FULL_SOLVER_OPTIMAL=False if capture else None,S3_BAR_STATUS=capture['BarStatus'] if capture else None,
        S3_OPTIMUM_INTERVAL_PASS=bool(capture and capture['PASS']),S3_OPTIMUM_INTERVAL_WIDTH=capture['width'] if capture else None,MIP_PROOF_POLICY_CHANGED=False,LP_REQUIRED_METHOD_THREADS_UNCHANGED=True,
        S3_NUMERICAL_RECOVERY_RUN=bool(recovery),S3_ABORTED_LP_WALL_ESTIMATE_SECONDS=read(OUT/'S3_ROOT_LP_OPTIMIZATION.json').get('prior_aborted_wall_estimate_seconds',0.) if capture else ((recovery['wall_estimate_seconds']+(interior_recovery['compact_attempt_wall_estimate_seconds'] if interior_recovery else 0.)) if recovery else 0.),
        S3_RECOVERY_LP_PROJECTION_IDENTICAL=bool(recovery and recovery['LP_projection_identical']),
        PRODUCTION_AUTHORIZED=gate['authorized'],PRODUCTION_RUN=production_run,M1_P1_INCUMBENT=p['incumbent'],M1_P1_BOUND=p['bound'],
        M1_P1_GAP=p['gap'],M1_P1_QUALITY_PASS=production_run and p['quality_PASS'],M1_P2_COMPLETE=complete,
        M1_MOVEMENT_ENERGY=production['passes'][1]['incumbent'] if len(production['passes'])>1 else None,
        M1_MOVEMENT_COUNT=production['passes'][2]['incumbent'] if len(production['passes'])>2 else None,
        M1_PHYSICAL_PASS=physical_pass,M1_ROBUST_VOLTAGE_PASS=robust_pass,M1_ACCEPTED=accepted,
        FINAL_PLAN_SOURCE='M1_PRODUCTION' if production_run else 'MIP_CANARY diagnostic' if canary_run else 'PR108 retained incumbent',
        PHYSICAL_FLAGS_SOURCE='new production' if production_run else 'PR108 incumbent independently revalidated',
        A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,PROBLEM13_FINAL_VALIDATED=False)
    dump('FINAL_FLAGS.json',flags)
    conclusion='Tested mode-disjunction and route-energy-pooling mechanisms do not materially explain the current root gap.' if not selected['material'] else 'Exact strengthening materially raises the root bound; MIP and production gates are evaluated separately.'
    verdict=dict(conclusion=conclusion,selected=selected['selected'],root_gain=selected['delta_LB'],implied_gap=selected['implied_gap'],
        root_LP_not_MIP_certificate=True,M1_ACCEPTED=accepted,PROBLEM13_FINAL_VALIDATED=False,
        STOP_stage='root LP comparison' if not canary_run else 'canary' if not production_run else 'M1 production',
        A1_optimize_calls=0,scientific_physics_changed=False)
    dump('FINAL_VERDICT.json',verdict)
    diag=read(OUT/'RESIDUAL_RELAXATION_DIAGNOSIS.json')
    boundlist=lambda key:'; '.join(r['candidate']+'='+str(r[key]) for r in comparisons)
    answers={1:'동일한 feasible UB가 있고 root LP는 이미 완료되지만, PR108의 두 600초 proof에서 LB가 동일하고 nodes=1이었다. 핵심은 전역 bound 강도다.',
      2:str(UB),3:str(LB),4:str((UB-LB)/UB*100)+'% (PR108); selected LP implied gap='+str(selected['implied_gap']*100)+'%.',
      5:str(UB*(1-.005))+' 이상. 동일 UB 기준의 충분 LB 수준이다.',
      6:f"PASS. fingerprint=0x9cfd10ec, binaries=208312, continuous=108431, rows=954560, nonzeros=8282350. LP OPTIMAL {root['bound']}, {root['seconds']:.3f}초; 목적값 허용오차 1e-7.",
      7:str(flags['FRACTIONAL_STAY_COUNT']),8:str(flags['FRACTIONAL_TRAVEL_COUNT']),9:str(flags['FRACTIONAL_CHARGE_MODE_COUNT']),
      10:str(flags['MAX_SIMULTANEOUS_FRACTIONAL_SITES']),
      11:f"multiple positive stay sites: {route['fraction_slots_multiple_positive_sites']*100:.4f}% MESS-slot; fractional travel departure: {route['fraction_slots_fractional_travel']*100:.4f}%. LP 진단이며 splitting 자체를 물리 위반이라고 부르지 않는다.",
      12:'H1: z<=y. H2: ΣPch<=Pmax*z. H3: ΣPdis<=Pmax*(y-z). y=Σx_stay.',
      13:str(mode['per_inequality']['H1']),14:str(mode['per_inequality']['H2']),15:str(mode['per_inequality']['H3']),
      16:'H1은 무차원 mass, H2/H3은 kW. 각 최대값: '+str({h:d['maximum_violation'] for h,d in mode['per_inequality'].items()})+'; 혼합 단위 최대를 물리량 하나로 해석하지 않는다.',
      17:'baseline 최적점에서 위반이 있어 S1을 실행했다. 위반 발견 자체는 objective 개선을 보장하지 않는다.',
      18:'route/P/Q/SOC의 integer physical projection은 동일하다. transit 중 unused z=1 배정은 H1에 의해 z=0으로 바뀔 수 있다. 전체 auxiliary bit 배정 집합의 동일성은 주장하지 않는다.',
      19:'단일 E[m,t]가 fractional 경로들 사이에서 에너지를 합산하여, 분기별 경로 일관 SOC로 분해되지 않는 dispatch를 허용할 수 있다는 가설이다.',
      20:f"feasible={energy['feasible']}; certified infeasible={energy['certified_infeasible']}; status={energy['status']}. IIS도 저장했다.",
      21:'이 고정 baseline optimum의 x/Pch/Pdis는 동일한 Emin/Emax/초기/terminal 조건의 path-consistent arc-energy flow로 확장될 수 없다. MESS01/STA02/t=71–86의 node 식을 합하면 운반 가능한 에너지 범위보다 '+str(energy_margin)+' kWh 더 방전해야 하는 독립 산술 모순이 나온다. 허용오차 크기의 충돌이 아니다.',
      22:'feasible이면 같은 optimum이 추가식에서도 남으므로 그 식만으로 root 목적값을 높일 수 없다. 이번에는 infeasible이므로 S2를 실행했다.',
      23:'fractional arc의 출발 노드에서 운반되는 에너지 mass, 단위 kWh.',24:'A=G-travel_energy*x.',
      25:'A=G+0.25*(0.95*Pch-Pdis/0.95).',26:'terminal H 노드의 incoming A 합을 battery.terminal=760 kWh로 고정하고 원본 terminal SOC equality도 유지했다.',
      27:'대체하지 않았다. 원본 SOC 변수와 모든 recurrence를 유지한 추가 강화다.',28:str(flags['INTEGER_PROJECTION_EQUIVALENCE_PASS'])+'; 구성적 증명과 20개 사례의 모든 tiny route path 비교를 함께 기록했다.',
      29:str(extension['PASS'])+'; 각 후보의 기존 route/P/Q/SOC/rho를 보존하고 S2/S3의 정확한 G를 구성했다.',
      30:'; '.join(f"{r['candidate']}: {r['rows']}/{r['columns']}/{r['nonzeros']}" for r in comparisons),
      31:boundlist('LB'),32:boundlist('delta_LB'),33:boundlist('implied_gap')+' (동일 PR108 UB 대비, 비율). LP만으로 MIP certificate를 주장하지 않는다.',
      34:selected['selected'],35:'integer physical equivalence를 통과한 후보 중 최고 root LB, 낮은 implied gap, 이후 wall/matrix 순서로 선택했다.',
      36:str(selected['selected_root_LB']>=.62),37:str(selected['selected_root_LB']>=.65),38:str(selected['material'])+'; 사전 기준 delta_LB>=0.001.',
      39:str(canary_run),40:json.dumps(checkpoint(300),ensure_ascii=False) if canary_run else '미실행. material bound gate가 통과되지 않았다.',
      41:json.dumps(checkpoint(600),ensure_ascii=False) if canary_run else '미실행. 600초 solve를 소비하지 않았다.',
      42:str(gate['authorized'])+'; '+json.dumps(gate,ensure_ascii=False),43:str(production_run),
      44:str(flags['M1_P1_GAP']*100)+'%; source='+flags['FINAL_PLAN_SOURCE']+'. production P1 quality='+str(flags['M1_P1_QUALITY_PASS']),
      45:str(len(production['passes'])>1)+'; P2 complete='+str(complete),
      46:str(physical_pass)+'; source='+flags['PHYSICAL_FLAGS_SOURCE'],47:str(robust_pass)+'; source='+flags['PHYSICAL_FLAGS_SOURCE']+'; band=0.955–1.045 pu.',
      48:'변경 없음. default hook=None 모델 identity와 incumbent residual까지 동일하다.',
      49:'selected root fractional stay/travel/mode='+str((diag['selected_root']['fractional_stay'],diag['selected_root']['fractional_travel'],diag['selected_root']['fractional_charge_mode']))+'; 분산 위치/Q 지원과 averaged grid-feasible trajectory의 정수 분해 가능성이 다음 진단 우선순위다. 후자는 아직 가설이다.',
      50:'명시적인 STOP-before-A2 범위다. M1/P2 acceptance와 Problem13 최종 검증을 혼동하지 않는다.'}
    lines=['# PR108 successor: M1 relaxation strengthening','',conclusion,'',f"Selected={selected['selected']}; LP LB={selected['selected_root_LB']}; gain={selected['delta_LB']}; implied gap={selected['implied_gap']*100:.6f}%. M1_ACCEPTED={accepted}.",'',
      'Baseline fingerprint는 PR108처럼 검증된 MIP start를 적용한 상태에서 비교한다. Gurobi의 signed integer를 unsigned 32-bit hexadecimal로 표시한다. 행/열/nonzero와 default-path incumbent validation도 동일해야 PASS다.', '']
    if recovery:
        lines.extend(['S3의 첫 crossover cleanup은 큰 primal infeasibility가 지속되어 중단했다. 약 '+str(recovery['wall_estimate_seconds'])+'초의 비용과 원본 로그/소스를 보존했다. 기존 식이 이미 함의하는 G의 [0,Emax] variable bounds만 명시해 동일 LP projection으로 복구했으며, solver 설정은 변경하지 않았다. 비교표의 total LP wall에는 이 중단 시간 추정치도 포함한다.', ''])
    if interior_recovery:
        lines.extend(['G bounds 표현 보정 후에도 crossover cleanup에서 큰 dual infeasibility가 반복돼 약 '+str(interior_recovery['compact_attempt_wall_estimate_seconds'])+'초의 두 번째 시도를 중단했다. Crossover=0 시도도 약 27 GB factor memory가 예상돼 중단했다. 최종 S3는 기본 Crossover 설정에서 barrier 해를 캡처했고, 전체 solver 상태는 INTERRUPTED(11), BarStatus는 OPTIMAL(2)로 실제 값을 기록했다. S2의 OPTIMAL 하한과 full-matrix feasible BarX를 이용한 optimum interval이 1e-7 이내일 때만 numerical optimality PASS로 판정한다. Method=2/Threads=1 및 모든 MIP proof policy는 유지했다. BarStatus=OPTIMAL, 전체 행렬 residual, dual residual 및 optimum interval 검증을 요구한다. API 캡처 수정 시도를 포함해 S3는 총 5회 optimize를 호출했으며, 네 중단 시도의 비용 추정치를 모두 포함한다. Solver parameter grid/search는 실행하지 않았다.', ''])
    for i,q in enumerate(QUESTIONS,1):lines.extend([f'{i}. **{q}**',answers[i],''])
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf8')
    recovery_note=f"S3 numerical recovery: the first crossover cleanup had sustained very large primal infeasibility and was interrupted after approximately {recovery['wall_estimate_seconds']:.3f} seconds. Its source and logs are retained. Explicit [0,Emax] G variable bounds are already implied by the retained G_min/G_max rows and original 0<=x<=1 bounds, so the extended LP polyhedron is identical. The G-bound representation repair changed no solver parameter and introduced no new strengthening family. The 20-case integer comparisons were rerun. Successful optimization wall/phase/peak-RSS measurements are separated from the interrupted attempt; total candidate LP wall includes the approximate interrupted wall, whose peak RSS was not retained. See S3_NUMERICAL_RECOVERY.json. Invoke the guarded recovery only through `python -m v42_relaxation.recovery`, rerun `equivalence`, then `lp S3 --recover-implied-G-bounds`. The single recovery has now been consumed.\n\n" if recovery else ''
    if interior_recovery:
        recovery_note+='The compact-bound crossover cleanup also had repeated very large dual infeasibility and was interrupted after approximately '+str(interior_recovery['compact_attempt_wall_estimate_seconds'])+' seconds. One deterministic LP-only fallback uses Method=2, Threads=1, Crossover=0 to return an optimal interior solution without a basis. This option is documented in the [Gurobi parameter reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#crossover). Gurobi OPTIMAL, finite complete values, full original matrix residual and DualVio <=1e-5 are required. All MIP proof settings remain frozen; no parameter grid/search or objective/bound-driven tuning was conducted. S3 has three optimize attempts: two interrupted and one completed. Total S3 LP wall includes both interrupted wall estimates, whose peak RSS was not retained. The additional guarded command is `recovery --interior`, then `lp S3 --recover-implied-G-bounds --interior-recovery`. Saved interior fractionality is point-specific and can differ from a basic optimum on the same optimal face.\n\n'
    if capture:
        recovery_note='S3 numerical limitation: two crossover cleanups had large primal/dual infeasibilities; one Crossover=0 recovery trial was aborted after its presolved factor estimate reached 27 GB. A capture API smoke test corrected an erroneous assumption about BarStatus after terminate. All interrupted logs, source snapshots and costs are retained; S3 has five optimize calls in total. The final call retains Method=2, Threads=1 and default Crossover, captures BarX/BarPi after the barrier completion log, and intentionally stops crossover. Overall status remains INTERRUPTED(11), while the completed barrier has BarStatus=OPTIMAL(2); the overall solver status is not relabeled. S3 optimum is certified numerically to the inherited 1e-7 objective tolerance using the completed S2 lower bound, S3 containment in S2, and independently validated full-matrix feasible BarX. The certificate records the actual interval, row-sign and free-column stationarity residuals. See S3_BARRIER_OPTIMALITY_CERTIFICATE.json and S3_ROOT_LP_OPTIMIZATION.json. Only S0/S1/S2 have overall Gurobi OPTIMAL status. MIP policy, all scientific physics, objectives and material thresholds remain frozen. No solver-parameter grid/search was conducted; the one Crossover=0 trial was unsuccessful numerical recovery, not a selected proof policy. Total S3 LP wall includes all four interrupted wall estimates; failed-attempt peak RSS was not consistently retained.\n\n'
    (OUT/'README.md').write_text(f'# Exact M1-F3 relaxation strengthening\n\nStacked on PR108 exact `{HEAD}`. {conclusion}\n\nBaseline OPTIMAL LB={root["bound"]}; selected {selected["selected"]} LB={selected["selected_root_LB"]}, delta={selected["delta_LB"]}, same-UB implied gap={selected["implied_gap"]}. Canary run={canary_run}; production run={production_run}; M1 accepted={accepted}. LP results are not a MIP certificate. LP wall and peak RSS are measured during optimization, excluding model construction and solution export; reported barrier time may be cumulative, while the separate phase wall fields use callback timestamps.\n\nDefault native behavior is unchanged with `strengthening_hook=None`: fingerprint 0x9cfd10ec (with inherited verified MIP start), 208312 binaries, 108431 continuous columns, 954560 rows, 8282350 nonzeros, identical incumbent matrix residual. Fingerprint includes optimization-relevant attributes, so start-applied and unstarted fingerprints differ; see [Gurobi fingerprint documentation](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#fingerprint) and BASE_FINGERPRINT_PHASE_DIAGNOSIS.json.\n\nA1 optimize calls=0. Inherited input hashes, 1499 known jobs, AIDC/CC4/Runtime anchor, route/SOC/PCS/grid physics and robust band are frozen. S1 adds only H1/H2/H3; S2 adds only arc-energy variables and rows while retaining original SOC; S3 combines them. All original rows remain. Physical integer projection is identical; auxiliary unused mode assignments in transit may be canonicalized. The full saved baseline optimum, fractionality/route audits, fixed-root IIS, 20-case exhaustive route comparisons and incumbent extensions are included.\n\nRun `python -m v42_relaxation.base setup`, then `baseline`, `python -m v42_relaxation.diagnostics audit`, then `energy`. After an infeasible energy diagnostic, `python -m v42_relaxation.energy_iis` captures a bounded IIS and `python -m v42_relaxation.energy_certificate` checks its independent arithmetic contradiction; `python -m v42_relaxation.mode_certificate` records the physical dispatch projection witness. Strengthening phases are gated by those saved witnesses: `strengthening default_regression`, `equivalence`, `strengthening incumbent`, and one `lp S1/S2/S3` per authorized label. `lp select` fixes the result; `mip canary` and `mip production` enforce their gates and single-run markers. Diagnostic setup defaults to the hash-verified PR108 local input directory recorded in the receipts; no synthetic replacement is permitted.\n\n{recovery_note}See [Korean 50-question review](FINAL_REVIEW_KO.md), [root comparison](ROOT_LP_STRENGTHENING_COMPARISON.csv), [integer proof](INTEGER_PROJECTION_PROOF.md) and [final flags](FINAL_FLAGS.json). Unrun artifact files contain explicit run=false/empty telemetry rather than invented measurements. A2/M2/Actual/Fresh AC/IEEE8500 remain unrun; Problem13 FINAL_VALIDATED=false.\n',encoding='utf8')
    print('FINAL REPORT',verdict,flush=True)

def verify():
    legacy=read(OUT/'LEGACY_PRESERVATION_AUDIT.json')
    changed=[r['path'] for r in legacy['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert set(changed)=={'v42_native/mess.py','v42_voltage/preservation.py'},changed
    legacy.update(PASS=True,authorized_changed_sources=changed,all_other_legacy_bytes_preserved=True,
        native_change_scope='optional structured strengthening hook; strict hash-authorized preservation adapter; default matrix regression PASS')
    dump('LEGACY_PRESERVATION_AUDIT.json',legacy)
    sourcepaths=sorted((ROOT/'v42_relaxation').glob('*.py'))+[ROOT/'v42_relaxation/.gitattributes',OUT/'.gitattributes',ROOT/'tests/v42_relaxation/.gitattributes']+[ROOT/'v42_native/mess.py',ROOT/'v42_voltage/preservation.py',ROOT/'tests/v42_relaxation/test_relaxation.py']
    dump('SOURCE_MANIFEST.json',dict(base_head=HEAD,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sourcepaths],
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),inherited_inputs=read(OUT/'PR108_A1_ANCHOR_REUSE.json')))
    missing=[n for n in REQUIRED if not (OUT/n).is_file() and n!='VERIFICATION.json'];assert not missing,missing
    tree=ET.parse(OUT/'TEST_RESULTS.xml');suites=tree.getroot();suite=list(suites)[0] if suites.tag=='testsuites' else suites
    assert int(suite.get('failures','0'))==0 and int(suite.get('errors','0'))==0
    assert not subprocess.check_output(['git','diff','--check'],cwd=ROOT,text=True)
    flags=read(OUT/'FINAL_FLAGS.json');assert flags['BASE_F3_IDENTITY_PASS'] and flags['INTEGER_PROJECTION_EQUIVALENCE_PASS']
    for label in read(OUT/'STRENGTHENING_CANDIDATES.json')['authorized']:
        filename='BASE_ROOT_LP_SOLUTION.npz' if label=='S0' else label+'_ROOT_LP_SOLUTION.npz'
        with np.load(OUT/filename,allow_pickle=False) as optimum:
            assert np.isfinite(optimum['values']).all(), 'NONFINITE_SAVED_OPTIMUM:'+label
    assert flags['A1_OPTIMIZE_CALLS_THIS_TASK']==0 and not any(flags[k] for k in ['A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN'])
    if not flags['MATERIAL_ROOT_BOUND_GAIN']:assert not flags['MIP_CANARY_RUN'] and not flags['PRODUCTION_RUN']
    if not flags['PRODUCTION_AUTHORIZED']:assert not flags['PRODUCTION_RUN']
    if flags.get('S3_OPTIMUM_INTERVAL_PASS'):
        certificate=read(OUT/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json')
        assert certificate['PASS'] and abs(certificate['width'])<=OBJ_TOL
        assert certificate['dual_row_sign_violation']<=TOL and certificate['free_column_stationarity_residual']<=TOL
        assert certificate['full_solver_status']==read(OUT/'S3_ROOT_LP_OPTIMIZATION.json')['status']
        assert flags['ROOT_LP_OPTIMIZE_CALLS']['S3']==5
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.get('tests')),failures=0,errors=0,skipped=int(suite.get('skipped','0')),
        base_identity=True,all_saved_optima_finite=True,default_path_regression=read(OUT/'DEFAULT_PATH_REGRESSION.json')['PASS'],
        exhaustive_integer_equivalence=read(OUT/'BOUNDED_INTEGER_EQUIVALENCE_DETAILS.json')['PASS'],
        incumbent_extension=read(OUT/'PR108_INCUMBENT_EXTENSION.json')['PASS'],
        A1_optimize_calls=0,no_scientific_change=True,all_other_legacy_bytes_preserved=True,
        required_files=REQUIRED,files=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='VERIFICATION.json']))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['run','verify']);a=p.parse_args();globals()[a.phase]()
