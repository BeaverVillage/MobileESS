"""Separate original feasible uppers, partial intervals, and execution gates."""
from datetime import datetime,timezone
import shutil
import xml.etree.ElementTree as ET
from .common import *
from .certificates import analyze,INHERITED

REQUIRED='''PREREGISTRATION.json SCOPE_CORRECTION_ADDENDUM.json PR112_BASE_RECEIPT.json MIP_START_IMPORT_AUDIT.json MIP_START_NATIVE_ACCEPTANCE.json MIP_START_PHYSICAL_VALIDATION.json MIP_START_GRID_VALIDATION.json PARTIAL_INTEGRALITY_COMPARISON.csv B1_ROUTE_CERTIFICATE.json B2_ROUTE_MODE_CERTIFICATE.json B3_BUFFER_CERTIFICATE.json OPTIMUM_INTERVAL_SUMMARY.csv PRIMAL_QUALITY_COMPARISON.csv DUAL_BOUND_COMPARISON.csv ROOT_CAUSE_CLASSIFICATION.json PRODUCTION_AUTHORIZATION.json FINAL_FLAGS.json FINAL_VERDICT.json VERIFICATION.json NEXT_MODIFICATIONS.md FINAL_REVIEW_KO.md SOURCE_MANIFEST.json'''.split()

def prose(name,s):(OUT/name).write_text(s.strip()+'\n',encoding='utf8')
def point_difference(names,values,reference):
    diff=np.abs(values-reference);result={}
    for label,prefixes in dict(route=['arc['],mode=['charge_mode['],P=['Pch[','Pdis['],Q=['Q['],SOC=['SOC[']).items():
        mask=np.asarray([str(n).startswith(tuple(prefixes)) for n in names]);d=diff[mask]
        result.update({label+'_changed_values':int(np.sum(d>TOL)),label+'_max_abs_difference':float(d.max()) if len(d) else 0.})
    return result
def armtext(c):
    return f'{c["execution"]}; status={c["solver_status"]}; new native BestBd={c["raw_BestBd"]}; partial optimum interval=[{c["lower"]:.12f}, {c["upper"]:.12f}], width={c["width"]:.12f}; material={c["material"]}, negative certificate={c["negative_certificate"]} ({c["conclusion"]}).'

def run():
    runs,certs,classification=analyze();axis=load_axis();names,start=load_start();accepted=read(OUT/'MIP_START_NATIVE_ACCEPTANCE.json')
    warningaudit=[]
    for a,r in runs.items():
        raw=gzip.decompress((OUT/(a+'_SOLVER.log.gz')).read_bytes()).decode()
        warnings=[line.strip() for line in raw.splitlines() if 'Warning' in line or 'quad precision' in line or 'Numerical' in line]
        warningaudit.append(dict(arm=a,solver_status=r['solver_status'],root_completed=r['root_complete'],raw_BestBd=r['raw_BestBd'],
            warnings=warnings,final_matrix_validation=r['matrix_validation'],numerical_failure=r['solver_status']==12,
            incomplete_root_intermediate_LP_values_used_as_certificate=False,
            bound_authority='Only final native ObjBound plus inherited certified bounds; no transient simplex objective/dual value is promoted.',
            raw_log_sha256=sha(OUT/(a+'_SOLVER.log.gz'))))
    dump('NUMERICAL_WARNING_AUDIT.json',dict(checks=warningaudit,scientific_physics_or_NumericFocus_retuned=False,
        solver_warnings_not_hidden=True,no_rational_exact_arithmetic_certificate_claim=True))
    dump('LOWER_BOUND_PROVENANCE_AUDIT.json',dict(arms=[dict(arm=a,new_native_BestBd=r['raw_BestBd'],
        inherited_same_arm_LB=read(PRIOR/(INHERITED[a]+'_OPTIMIZATION.json'))['certified_global_LB'],effective_valid_partial_LB=r['valid_partial_LB'],
        inherited_bound_stronger_than_new_native=bool(r['raw_BestBd'] is None or r['raw_BestBd']<r['valid_partial_LB']),
        proof='Exact unchanged partial domain/rows retain inherited same-arm certificate. Effective partial LB is max(F3, inherited same-arm bound, new native bound); raw native bound remains separately visible.') for a,r in runs.items()],
        S2_not_installed_as_partial_lower_floor=True))
    candidates=[(START_UB,'PR112_P_FIXED_ROUTE',start)]
    for arm,r in runs.items():
        if r['validated_original_UB'] is not None:
            with np.load(OUT/(arm+'_SOLUTION.npz'),allow_pickle=False) as z:v=z['values']
            candidates.append((r['validated_original_UB'],arm,v))
    best,bestsource,bestvalues=min(candidates,key=lambda x:x[0]);lb=max([S2]+[c['global_LB'] for c in certs.values()]);gap=(best-lb)/best
    assert best>=lb-OBJ_TOL
    points=[('retained_old_incumbent',OLD_UB,axis['start'],True,True,True)]
    for a in ['P_FIXED_ALL','P_FIXED_ROUTE']:
        r=read(PRIOR/(a+'_OPTIMIZATION.json'))
        with np.load(PRIOR/(a+'_SOLUTION.npz'),allow_pickle=False) as z:assert np.array_equal(z['names'],names);v=z['values']
        valid=r['full_original_integer_validation'];points.append(('PR112_'+a,r['original_feasible_UB'],v,valid['valid_new_UB'],valid['physical']['PASS'],valid['robust_grid']['PASS']))
    with np.load(OUT/'MIP_START_NATIVE_ACCEPTED.npz',allow_pickle=False) as z:assert np.array_equal(z['names'],names);accepted_values=z['values']
    points.append(('native_B3_accepted_initial_start',accepted['accepted_initial_objective'],accepted_values,True,True,True))
    for a,r in runs.items():
        if r['validated_original_UB'] is not None:
            with np.load(OUT/(a+'_SOLUTION.npz'),allow_pickle=False) as z:v=z['values']
            points.append((a+'_original_integer_incumbent',r['validated_original_UB'],v,True,True,True))
    primal=[]
    for label,objective,v,valid,physical,grid in points:
        primal.append(dict(point=label,original_feasible_UB=objective,binary_valid=valid,physical_valid=physical,grid_valid=grid,
            original_M1_implied_gap=(objective-lb)/objective,**point_difference(names,v,axis['start'])))
    table('PRIMAL_QUALITY_COMPARISON.csv',primal)
    dual=[dict(arm='F3_inherited',execution='REUSED',solver_status=2,raw_native_BestBd=None,original_global_LB=F3,partial_LB=None,partial_upper=None,interval_width=None,
        original_feasible_UB=best,global_implied_gap=(best-F3)/best,optimize_seconds=0,build_seconds=0,nodes=None,root_complete=True,negative_certificate=None),
        dict(arm='S2_inherited',execution='REUSED',solver_status=2,raw_native_BestBd=None,original_global_LB=S2,partial_LB=None,partial_upper=None,interval_width=None,
        original_feasible_UB=best,global_implied_gap=(best-S2)/best,optimize_seconds=0,build_seconds=0,nodes=None,root_complete=True,negative_certificate=None)]
    for a,c in certs.items():
        r=runs.get(a);dual.append(dict(arm=a,execution=c['execution'],solver_status=c['solver_status'],raw_native_BestBd=c['raw_BestBd'],original_global_LB=c['global_LB'],
            partial_LB=c['lower'],partial_upper=c['upper'],interval_width=c['width'],original_feasible_UB=best,
            global_implied_gap=(best-c['global_LB'])/best,optimize_seconds=r['optimize_wall_seconds'] if r else 0,
            build_seconds=r['build_seconds'] if r else 0,nodes=r['node_count'] if r else None,root_complete=r['root_complete'] if r else None,
            negative_certificate=c['negative_certificate']))
    table('DUAL_BOUND_COMPARISON.csv',dual)
    table('RUN_GAP_COMPARISON.csv',[dict(arm=a,solver_status=r['solver_status'],native_BestBd=r['raw_BestBd'],native_incumbent=r['solver_incumbent'],
        native_relative_gap=(r['solver_incumbent']-r['raw_BestBd'])/abs(r['solver_incumbent']) if r['raw_BestBd'] is not None else None,
        effective_partial_LB=certs[a]['lower'],partial_feasible_upper=certs[a]['upper'],partial_interval_width=certs[a]['width'],
        normalized_partial_interval_width=certs[a]['width']/certs[a]['upper'],original_global_implied_gap=gap,
        native_gap_not_replaced_by_inherited_floor=True) for a,r in runs.items()])
    if best<START_UB-OBJ_TOL:
        np.savez_compressed(OUT/'BEST_NEW_ORIGINAL_M1_SOLUTION.npz',names=names,values=bestvalues)
        dump('BEST_NEW_ORIGINAL_M1_RECEIPT.json',dict(PASS=True,UB=best,source=bestsource,validation=runs[bestsource]['original_integer_validation'],
            matrix=runs[bestsource]['matrix_validation'],P1_only=True,P2_complete=False,M1_ACCEPTED=False,repair=False))
    case=classification['ROOT_CAUSE_CLASS']
    nextdirection={
        'CASE_A_ROUTE_INTEGRALITY_MATERIAL':'다음 후속 후보는 route/state/trajectory strengthening이다. 이번 PR에서는 구현하지 않는다. 나머지 mode/buffer incremental 기여는 저장한 interval 범위에서만 해석한다.',
        'CASE_B_MODE_INCREMENT_MATERIAL':'다음 후속 후보는 mode-dispatch perspective/disjunctive strengthening이다. 검증된 mode incremental lower bound에 근거하며 primal mode-plan 개선과 구분한다.',
        'CASE_C_INTERTEMPORAL_INCREMENT_MATERIAL':'다음 후속 후보는 multi-time energy/trajectory strengthening이다. buffer가 추가한 route/mode와 기존 SOC 결합의 공동 효과이며 terminal equality 단독 원인으로 해석하지 않는다.',
        'CASE_D_PARTIAL_NONMATERIAL_SEARCH_QUALITY_NEXT':'다음 후속 대상으로 full-horizon native primal/branching/search 전략을 검토한다. late partial models의 비물질성은 window 밖의 전체 integrality gap까지 배제하지 않는다.',
        'CASE_E_INCONCLUSIVE':'B3의 남은 optimum interval을 먼저 줄여 positive bound 또는 가까운 validated partial upper certificate를 확보해야 한다. 현재 증거로 route/mode/trajectory cut을 선택하지 않는다. 새 original-integer start는 보존하되 추가 arm·fallback·production을 자동 실행하지 않는다.'}[case]
    if case=='CASE_E_INCONCLUSIVE' and any(not r['root_complete'] for r in runs.values()):
        nextdirection+=' 이번 root/crossover 미완료와 numerical 경고를 먼저 감사한다. 별도 사전등록 후 안정적인 root/basis 검증 또는 B3 discrete point를 고정한 full96 continuous LP의 feasible-upper 구성으로 certificate를 시도하는 것이 다음 계산 후보다. 이 fixed-window LP는 upper witness를 만드는 제한 subset이며 그 BestBd를 B3/global lower bound로 사용할 수 없다. 단순 시간 연장이나 weaker arm 반복을 해결책으로 간주하지 않는다.'
    total=sum(r['optimize_calls'] for r in runs.values())
    flags=dict(BASE_PR=112,BASE_HEAD=BASE,SCOPE_CORRECTION_APPLIED=True,SCOPE_CORRECTION_BEFORE_OPTIMIZATION=True,
        ORIGINAL_PREREGISTRATION_PRESERVED=True,PREPARE_RESULTS_PRESERVED=True,
        BEST_VALIDATED_ORIGINAL_M1_UB=best,BEST_UB_SOURCE=bestsource,BEST_CERTIFIED_ORIGINAL_M1_LB=lb,FINAL_IMPLIED_GAP=gap,
        INHERITED_S2_REFERENCE_GAP=(best-S2)/best,MIP_START_ACCEPTED=accepted['PASS'],MIP_START_ACCEPTED_IN='Native B3 MIP',
        NATIVE_FULL_BINARY_ACCEPTANCE_OPTIMIZATION_RUN=False,START_ACCEPTANCE_FOLDED_INTO_B3=True,
        FIRST_NATIVE_INCUMBENT=accepted['accepted_initial_objective'],OLD_UB_FALLBACK=False,
        ROOT_CAUSE_CLASS=case,PRODUCTION_M1_RUN=False,PRODUCTION_M1_P1_ACCEPTED=False,P2_RUN=False,M1_ACCEPTED=False,
        PROBLEM13_FINAL_VALIDATED=False,A2_ALLOWED=False,A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,
        FINAL_RESPONSE_KERNEL_RUN=False,MAY_FULL_CAMPAIGN_RUN=False,SENSITIVITY_CAMPAIGN_RUN=False,NEW_ML_TRAINING=False,
        CC4_RUNTIME_REDESIGNED=False,ACTUAL_P_CORRECTION_ENABLED=False,ACTUAL_Q_CORRECTION_ENABLED=False,
        SCIENTIFIC_PHYSICS_CHANGED=False,P1_P2_CONTRACT_CHANGED=False,COMPLETE_ROUTE_DOMAIN_RETAINED=True,FULL96_GRID_RETAINED=True,
        TERMINAL_SOC_EQUALITY_RETAINED=True,PCS16_RETAINED=True,PLANNING_VOLTAGE=[.955,1.045],ACTUAL_FRESH_ACCEPTANCE_VOLTAGE=[.95,1.05],
        CUSTOM_CUTS_ADDED=0,TERM_RELAX_RERUN=False,A1_OPTIMIZE_CALLS=0,S1_OPTIMIZE_CALLS=0,S2_OPTIMIZE_CALLS=0,S3_OPTIMIZE_CALLS=0,
        DIAGNOSTIC_OPTIMIZE_CALLS=total,EXECUTION_ORDER=classification['sequential_execution_order'],FALLBACK_RUNS=0,
        NUMBERED_PROBLEMS_SCOPE=[1,2,3,4,5,6,8,13],EXCLUDED_PROBLEMS_NEW_WORK=False)
    for a,c in certs.items():flags.update({a+'_RUN':c['run'],a+'_EXECUTION':c['execution'],a+'_STATUS':c['solver_status'],a+'_PARTIAL_LB':c['lower'],
        a+'_PARTIAL_UPPER':c['upper'],a+'_INTERVAL_WIDTH':c['width'],a+'_MATERIAL':c['material'],a+'_NEGATIVE_CERTIFICATE':c['negative_certificate']})
    if (OUT/'PYTEST_RESULTS.xml').exists():
        suite=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite')
        flags.update(FULL_TESTS=int(suite.attrib['tests']),NEW_TESTS=int(suite.attrib['tests'])-541,
            FULL_TESTS_PASS=int(suite.attrib['failures'])==int(suite.attrib['errors'])==0)
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(ROOT_CAUSE_CLASS=case,best_original_feasible_UB=best,best_original_certified_LB=lb,implied_gap=gap,
        MIP_start_accepted=True,B1_B2_B3=certs,next=nextdirection,production=False,P1_accepted=False,P2_run=False,M1_ACCEPTED=False,
        PROBLEM13_FINAL_VALIDATED=False,A2_allowed=False,downstream=False))
    for a in runs:shutil.copyfile(LOCAL/(a+'_OPTIMIZE_STARTED.json'),OUT/(a+'_EXECUTION_MARKER.json'))
    prose('NEXT_MODIFICATIONS.md',f'# 다음 작업 방향\n\n{nextdirection}\n\nRoot cause: {case}. 별도 후속 작업에서 원 96-slot grid, terminal SOC, PCS16, complete route domain, P1/P2 contract를 유지해야 한다. 이번 작업에는 remedy, production, P2, downstream 실행이 없다.')
    prose('README.md',f'''# PR112 MIP start와 B3-first certificate

Exact base PR112 `{BASE}`. 실행 전 checkpoint는 B3_EXECUTION_MARKER.json의 execution_commit에 동결되어 있다. 원 preregistration은 보존하고, 신규 결과 전에 작성한 SCOPE_CORRECTION_ADDENDUM.json으로 unconditional B1/B2/B3 rerun을 B3-first sequential gate로 수정했다.

Best validated original-M1 UB={best:.12f}, best original certified LB={lb:.12f}, implied global gap={gap*100:.8f}%. Native B3가 complete 96-slot start를 `{accepted['accepted_initial_objective']:.12f}`의 initial incumbent로 받아들였다. 별도 full-binary acceptance/prod solve는 하지 않았다. 모든 original binaries가 integer인 accepted initial vector는 full original matrix/physical/grid 검증을 통과했다.

{chr(10).join('- '+a+': '+armtext(c) for a,c in certs.items())}

분류: **{case}**. Native start acceptance와 P1/P2 production acceptance는 별개다. M1_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false, production/P2/downstream=false.

Feasible sets: F_original_integer ⊆ F_B3 ⊆ F_B2 ⊆ F_B1 ⊆ F_F3. 검증된 stronger feasible upper는 weaker arm으로 전달할 수 있고, weaker lower bound는 stronger arm으로 전달할 수 있다. B3 BestBd를 B1/B2 lower bound로 전달하지 않는다. S2는 original-M1 reference LB이며 partial optimum interval의 floor로 사용하지 않는다. OPTIMAL 또는 좁은 interval만으로 nonmaterial이라고 부르지 않고, partial upper-S2<=0.001 여부를 확인한다.

Effective partial lower bound에는 동일 model의 inherited PR112 bound가 포함된다. LOWER_BOUND_PROVENANCE_AUDIT.json과 dual CSV에 new raw BestBd를 별도로 표시하므로, inherited bound를 신규 solve의 bound 개선으로 오인하지 않는다.

기존 native 중복 row 이름은 MPS alias로 바뀌어도 모든 행의 순서/계수/RHS/sense가 정확히 일치한다. 첫 두 prepare assertion과 당시 산출물을 PREPARE_ATTEMPT_HISTORY.json 및 prepare_before_scope_correction/에 보존했다. 이 과정의 optimization 호출은 0이다.

Joint solver strategy는 결과 전에 한 번 사전등록했다. 4 threads에 따른 성능 우월성을 주장하지 않는다. certificate의 유효성은 feasible-set inclusion, native solver bound, 독립 feasibility/domain 검증에 근거한다. Solver builtin cuts는 최적화 과정이며 새 handmade formulation cut은 추가하지 않았다. [Gurobi parameters](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html), [MIP starts](https://docs.gurobi.com/projects/examples/en/current/overview/starts.html).

FINAL_REVIEW_KO.md, OPTIMUM_INTERVAL_SUMMARY.csv, PRIMAL_QUALITY_COMPARISON.csv, DUAL_BOUND_COMPARISON.csv를 함께 읽는다. SOURCE_MANIFEST.json/EXECUTION_FREEZE.json은 source를, VERIFICATION.json은 matrix/domain/gate와 preserved bytes를 검증한다. inherited 44 bounded checks를 재실행하거나 수정하지 않고 receipt/source hashes를 검증했다.

{nextdirection}
''')
    qa=[
    ('정확한 출발점과 계보는?',f'PR112 exact head {BASE}다. 새 branch는 이 commit에서 생성했고 실행 전 checkpoint와 final commit을 그 계보 위에 쌓는다. PR111 등 다른 formulation을 새로 상속하지 않았다.'),
    ('scope correction은 어떻게 남겼는가?','원 PREREGISTRATION.json을 삭제·덮어쓰지 않았다. addendum에 timestamp, base commit, 원 파일 SHA, 사용자 correction SHA, 신규 optimization marker가 없었다는 사실과 B3-first gate를 기록했다.'),
    ('prepare 오류와 기존 산출물은 숨겼는가?','숨기지 않았다. 첫 두 native identity/row-name assertion의 history를 남겼고 correction 당시 NPZ·physical/grid·P1 CSV와 source를 별도 snapshot으로 보존했다. exact matrix 대조는 row-index alias를 명시해 마쳤으며 prepare optimization은 0이다.'),
    ('왜 M1은 아직 완전히 해결되지 않았는가?',f'현재 original-M1 implied gap은 {gap*100:.8f}%이며 production P1/P2 acceptance certificate는 없다. 이번 B3-first certificate task의 종료와 M1 acceptance를 혼동하지 않는다.'),
    ('3.225% gap의 정확한 의미는?',f'PR112 validated UB {START_UB:.12f}와 inherited S2 LB {S2:.12f}의 차이를 UB로 나눈 {(START_UB-S2)/START_UB*100:.8f}%다. 정확한 optimum gap이 아니라 certified original lower/feasible upper가 정의하는 implied gap이다.'),
    ('이번 best original feasible UB와 certified LB는?',f'UB={best:.12f}, source={bestsource}; original certified LB={lb:.12f}. partial feasible upper는 original binaries 모두 integer이고 full validation을 통과한 경우에만 이 UB 후보에 포함했다.'),
    ('F3와 S2 lower bound는 무엇이 다른가?',f'F3 LB={F3:.12f}, S2 certified original-M1 LB={S2:.12f}. 이번 partial models는 exact F3에 일부 integrality만 복원한다. S2 evidence는 재실행하지 않고 original global reference로 사용한다.'),
    ('S2를 B3 optimum interval의 lower floor로 사용해도 되는가?','자동으로 사용할 수 없다. S2 feasible set과 각 부분 integrality F3 model의 포함관계는 별도다. partial interval은 F3와 동일 partial model의 valid bounds를 사용하며, S2는 materiality 기준과 original global LB에만 사용한다.'),
    ('새 UB는 왜 original-M1 feasible인가?','원 binary, bounds, route flow, charge-mode, P/Q, initial/terminal SOC, recurrence, travel debit, PCS16, full96 grid 및 robust voltage/transformer를 독립 검증했다. 원 행렬에서 최대 row residual도 기록했고 clipping·repair는 하지 않았다.'),
    ('왜 route를 그대로 두고 UB가 크게 줄었는가?','PR112 retained mode가 모두 discharge mode여서 충전할 수 없었고, all-stay route와 terminal equality에서 순방전도 사용할 수 없었다. mode와 dispatch를 풀면 기존 route에서도 에너지를 저장·방전하고 P/Q를 함께 선택할 수 있다. 그 original-feasible 개선은 0.078333467988이다.'),
    ('mode 재최적화는 무엇을 증명하는가?','기존 integer mode-plan/continuous-dispatch quality가 materially suboptimal이었다는 직접 증거다. fixed-all LP는 옛 objective를 재현했고 fixed-route/free-binary-mode model만 큰 feasible 개선을 보였다.'),
    ('그것이 mode LP relaxation gap의 증명인가?','아니다. primal integer plan을 더 잘 찾는 효과와 LP hull을 강화하여 lower bound를 올리는 효과는 다르다. mode incremental contribution은 nested optimum intervals로 별도 판단한다.'),
    ('complete native start의 axis는 얼마나 큰가?','316,743개 native variable이며 original binary 208,312개를 포함한다. 각 unit의 96개 charge_mode와 97개 SOC 및 모든 native route/Pch/Pdis/Q/auxiliary 값을 정확히 복원했다.'),
    ('variable mapping에서 빠지거나 이름을 추정한 값이 있는가?','native 이름 누락은 0이다. 값은 PR112 source solution과 bitwise 일치한다. serialized plan의 supplemental/unreachable 키는 native axis 밖의 추가 정보이며 missing native value를 추정하거나 임의 보충하지 않았다.'),
    ('binary fidelity는 어떻게 점검했는가?','원 binary 값의 최대 fractionality가 0인 imported point를 보존했다. 실제 accepted initial vector에도 모든 original binary의 integrality를 다시 검사했다. partial incumbent에는 복원 subset과 전체 original binaries를 구분해 검사한다.'),
    ('bounds와 auxiliary 값은 그대로인가?','original MPS bounds와 native constructor bounds가 정확히 일치한다. start는 bounds와 full matrix를 만족하며 auxiliary 값도 axis에 포함한다. 임의 rounding, projection, local repair를 하지 않았다.'),
    ('SOC recurrence와 travel energy를 점검했는가?','full matrix의 original energy_balance와 native physical validator를 함께 사용했다. travel energy는 original departure convention 그대로 차감한다. deliberate terminal/route/PCS 위반점이 거부되는 새 테스트도 추가했다.'),
    ('PCS16과 actual circle feasibility는 보존되는가?','individual original PCS16 행을 모두 유지한다. 원 integer start의 native physical circle check도 통과했다. aggregate PCS로 바꾸거나 400-kVA rating을 수정하지 않았다.'),
    ('full-grid와 Planning voltage authority는?', '원 96-slot voltage/line/transformer current·kVA 행을 모두 유지하고 0.955–1.045 pu의 robust Planning band를 검증했다. Actual/Fresh의 0.95–1.05 acceptance band를 Planning으로 대신 사용하지 않았다.'),
    ('initial/terminal SOC는 바뀌었는가?','네 unit 모두 original initial/terminal 760 kWh equality를 유지한다. diagnostic B3/B2/B1에 TERM_RELAX를 넣지 않았고 counterfactual reference를 production candidate로 승격하지 않았다.'),
    ('objective를 독립 재계산했는가?',f'imported rho={START_UB:.12f}; 원 coefficients의 all96 non-transformer face 최대값은 {read(OUT/"MIP_START_GRID_VALIDATION.json")["independently_recomputed_P1"]:.15f}다. objective는 원 rho_max의 단일 minimization 계수이며 다른 목적식으로 바꾸지 않았다.'),
    ('native solver가 새 start를 실제 사용했는가?',f'그렇다. native B3 raw log의 Loaded user MIP start와 initial MIPSOL vector를 보존했다. accepted initial objective={accepted["accepted_initial_objective"]:.12f}다. 이 actual accepted point는 original full-integer physical/grid 검증도 통과했다.'),
    ('별도 full-binary acceptance solve를 실행했는가?','아니다. scope correction의 B3-first/minimal-solve 정책에 따라 acceptance를 B3 native MIP 안에 함께 기록했다. B3는 partial binary model이지만 accepted initial point 자체는 모든 original binaries가 integer이고 exact original physical rows를 만족한다. production acceptance를 주장하지 않는다.'),
    ('옛 UB로 fallback하는 것을 어떻게 막았는가?','처음 loaded start, first incumbent, SolCount 및 final incumbent<=0.5912812634331275+tolerance를 함께 검사한다. old start와 alternate start는 넣지 않는다. 이 조건이 실패하면 raw rejection evidence를 보존하고 certificate 결과로 진행하지 않는다.'),
    ('왜 신규 solve를 B3부터 시작했는가?','PR112가 이미 세 arm을 600초씩 수행했기 때문이다. strongest B3의 validated feasible upper가 가까우면 weaker B2/B1의 비물질성을 추가 optimization 없이 증명할 수 있다. unconditional 장시간 rerun은 correction으로 폐기했다.'),
    ('B3의 integrality domain은?', '58–95를 점유하는 original stay/travel arcs, window node departure arcs 및 window charge modes 85,744개를 binary로 복원한다. 나머지 binary만 continuous로 완화하며 원 행·bounds·route alternatives·SOC coupling은 모두 유지한다.'),
    ('B2의 domain과 실행 gate는?', '66–95 route/stay/travel 및 charge modes 67,436개다. B3 material positive certificate가 있을 때만 신규 실행한다. B3 nonmaterial upper가 검증되면 nesting certificate로 대체한다.'),
    ('B1의 domain과 실행 gate는?', '66–95 route/stay/travel 67,316개이며 mode는 relaxed다. B2 material certificate가 있을 때만 신규 실행한다. B2 또는 B3 stronger feasible upper가 nonmaterial이면 추가 solve 없이 upper를 전달할 수 있다.'),
    ('feasible-set 포함관계는?', 'F_original_integer ⊆ F_B3 ⊆ F_B2 ⊆ F_B1 ⊆ F_F3다. 복원 binary 집합은 반대 방향으로 더 커진다. independently enumerated occupancy/departure rule을 inherited exact domains와 대조해 strict nesting을 확인했다.'),
    ('각 partial BestBd가 왜 original-M1 valid LB인가?','모든 original integer feasible point가 각 partial model에 들어간다. 따라서 partial optimum 및 그 certified lower bound는 original integer optimum 이하이다. 원 constraints를 유지하고 integrality 일부만 완화했으므로 이 방향이 성립한다.'),
    ('B3 lower bound를 B1/B2로 전달할 수 있는가?','안 된다. stronger feasible set의 minimum은 weaker minimum보다 높을 수 있다. lower bound는 weaker에서 stronger로만 전달한다. upper는 stronger feasible point가 weaker에서도 feasible이므로 반대 방향으로 전달한다.'),
    ('B3 nonmaterial certificate는 B1/B2를 어떻게 대신하는가?','검증된 B3 point가 upper U를 제공하면 opt_B1<=opt_B2<=opt_B3<=U다. U-S2<=0.001이면 세 optimum 모두 같은 reference에 대한 contribution ceiling을 만족한다. 이 경우 B1/B2 execution은 NOT_RUN_NESTING_CERTIFIED로 기록한다.'),
    ('negative certificate의 정확한 정의는?', 'solver-validated partial feasible upper에서 upper-S2<=0.001가 성립하거나 그와 동등한 certified optimum interval로 같은 ceiling을 증명해야 한다. OPTIMAL 또는 좁은 interval이라도 optimum이 높으면 positive 결과이며 자동 negative가 아니다.'),
    ('positive certificate 기준은?', 'valid partial lower bound-S2>=0.001다. 이 threshold를 넘어선 rigorous solver bound를 보존한다. positive partial materiality와 route/mode/buffer의 incremental attribution은 별도 판정한다.'),
    ('timeout과 negative certificate는 왜 다른가?','timeout은 남은 search tree/optimum interval을 닫지 못한 computational 상태다. BestBd 정체만으로 더 좋은 partial solution이나 높은 optimum을 배제할 수 없다. feasible upper ceiling 또는 충분한 optimum evidence가 없으면 INCONCLUSIVE다.'),
    ('interrupted run을 OPTIMAL로 바꾸었는가?','아니다. native status를 그대로 저장한다. callback의 positive/negative certificate candidate stop은 INTERRUPTED일 수 있으며 final bound와 saved point 검증으로 certificate validity를 판단한다. BarStatus도 overall status로 대체하지 않는다.'),
    ('B3의 실제 결과는?',armtext(certs['B3'])),
    ('B2의 실제 실행/결과는?',armtext(certs['B2'])),
    ('B1의 실제 실행/결과는?',armtext(certs['B1'])),
    ('mode-only incremental 기여는 얼마까지 증명되는가?',f'{classification["mode_increment_interval"]}. lower=max(0,L_B2-U_B1), upper=U_B2-L_B1를 사용한다. time-limited BestBd끼리의 차이를 optimum 차이로 표현하지 않는다.'),
    ('buffer incremental 기여는 얼마까지 증명되는가?',f'{classification["buffer_increment_interval"]}. 추가 58–65 mode/route 및 crossing actions가 기존 full96 SOC/terminal coupling과 결합하는 공동 효과다. interval이 허용하지 않으면 material increment 또는 특정 SOC 단독 원인을 단정하지 않는다.'),
    ('terminal-SOC counterfactual reference는 무엇인가?','PR112에서 original F3 terminal equality4개만 제거한 LP rho=0.5449188149384189, F3 대비 감소=0.026930645263362307였다. terminal equality가 LP objective를 material하게 제약한다는 evidence이며 integer gap 단독 원인 증명은 아니다. 이번에는 재실행하지 않았다.'),
    ('terminal SOC를 제거하면 안 되는 이유는?','original scientific battery contract와 feasible-set 정의를 바꾸기 때문이다. 그런 point는 original feasible UB가 아니며 기존 acceptance에 사용할 수 없다. 이번 primary B3에는 original terminal equality를 유지한다.'),
    ('late horizon은 필수 충전 회복 구간인가?','그렇게 주장하지 않는다. frozen root는 slot66에서 약1080 kWh를 보유하고 terminal760까지 약320 kWh 순방전한다. 충전/방전·travel recurrence를 실제 값으로 해석하며 late charging recovery라는 예시를 관측 사실로 바꾸지 않는다.'),
    ('line.sw1/A bottleneck의 물리적 의미는?','PR112 root의 phase-A feeder sensitivity가 active late block의 대부분 P1 face를 정의한다. line.sw1/A가 30개 중29개 slot에서 binding이다. P/Q와 위치가 affine current를 바꾸지만 단일 feeder 관측만으로 discrete optimum 원인을 확정하지 않는다.'),
    ('왜 66–95이고 40–46이 아닌가?','원 coefficients/vector의 all96 epigraph slack과 absolute dual mass로 찾은 primary T_ACTIVE가66–95다. P1 dual mass99.99998482%가 이 구간에 있다. PR110의40–46은 incumbent-root loading 차이 ranking이므로 historical evidence로만 보존한다.'),
    ('fractional location/Q가 gap 원인을 바로 증명하는가?','아니다. root는 site mass와 P/Q를 분산하지만 descriptive averaging과 optimum materiality는 다르다. 원 physics를 유지한 partial-integrality certificates로 lower/upper interval을 확인해야 한다.'),
    ('incumbent quality와 bound quality를 어떻게 분리했는가?','PRIMAL_QUALITY_COMPARISON에는 original-feasible UB, physical/grid/binary validity와 route/mode/P/Q/SOC difference를 기록한다. DUAL_BOUND_COMPARISON에는 certified global LB, partial interval, status/time/nodes/root와 negative certificate를 별도로 기록한다.'),
    ('numerical artifact 가능성은 어떻게 점검했는가?','native/MPS matrix 계수·RHS·sense·bounds·순서를 exact 비교하고 original name axis, independent face objective, physical/grid validation, binary fidelity를 검사한다. deliberate corrupted terminal/route/PCS points는 거부된다. NUMERICAL_WARNING_AUDIT에 basis/quad precision 등 실제 native warnings를 보존하며 미완료 root의 중간 LP 값은 certificate로 쓰지 않는다. 이는 exact rational bound proof를 뜻하지 않으며 numerical failure를 과학적 결과로 포장하지 않는다.'),
    ('4 threads가 이전 1 thread보다 우수하다고 주장하는가?','주장하지 않는다. complete new start와 여러 preregistered solver controls가 함께 바뀌었으므로 단일 parameter 효과를 분리한 비교가 아니다. certificate validity는 thread count가 아니라 unchanged feasible sets, valid solver bound와 saved-point 검증에 근거한다.'),
    ('solver strategy는 결과를 보고 반복 선택했는가?','아니다. primary joint strategy를 실행 전에 source checkpoint에 동결했고 fallback은0개다. Method2/NodeMethod1, Threads4, Seed20260929, MIPFocus1, Heuristics0.1, DegenMoves0, CutPasses1, MIPGap0, absolute gap0.0005 및1800초 optimize-only를 사용한다.'),
    ('native builtin cutting planes가 새 formulation remedy인가?','solver 내부의 mathematically valid branch-and-cut 과정과 저장소에 새 hand-designed cuts를 구현하는 것은 다르다. 이번 code에는 user/lazy/heuristic formulation cut, Top-K, Hamming restriction, 새 trajectory master가 없다.'),
    ('build time과 optimize time은 구분했는가?','model read, mapping, domain checks의 build time과 optimize 호출 wall/native runtime을 별도로 저장한다. root barrier/crossover/relaxation, branch node events, peak RSS 및 actual-observation progress도 보존한다.'),
    ('production M1 결과는?', 'NOT_RUN이다. scope correction 이후 이번 PR은 sequential certificate와 reporting까지만 진행한다. production authority file은 이 결정을 명시하며 original preregistration의 earlier gate가 superseded됐음을 기록한다.'),
    ('P1이 0.5% acceptance에 도달했는가?',f'current original implied gap={gap*100:.8f}%다. production P1 acceptance는 false이며 B3 diagnostic 또는 native start acceptance를 production acceptance로 대신하지 않는다.'),
    ('P2를 실행할 자격이 생겼는가?','production P1 accepted 이전에는 P2를 실행하지 않는다. 이번에는 P2_RUN=false다. 후속 P2는 original MIN_INTERVENTION movement energy→movement count tuple과 P1 objective lock, fixed AIDC anchor를 유지해야 한다.'),
    ('M1_ACCEPTED와 PROBLEM13_FINAL_VALIDATED는?', '둘 다 false다. M1은 P1/P2 acceptance를 모두 요구한다. Problem13 최종 validation에는 그 후 A2→M2→frozen Planning→Actual replay→Fresh AC가 필요하므로 이번 certificate 결과로 true를 설정하지 않는다.'),
    ('A2 또는 downstream으로 넘어가도 되는가?','안 된다. A2/M2/Actual/Fresh AC/IEEE8500/final kernel/May·sensitivity campaign은 실행하지 않았다. Actual P/Q correction도 OFF다. primary certificate task의 종료는 downstream gate 통과가 아니다.'),
    ('가장 근거가 강한 root-cause class는?',f'{case}다. threshold crossing만으로0.001 이상의 incremental effect를 주장하지 않고 certified intervals가 허용하는 범위로 분류했다. 부족한 certificate가 있으면 INCONCLUSIVE를 유지한다.'),
    ('다음 정확한 remedy 방향은?',nextdirection),
    ('numbered Problems와 기존 architecture를 바꾸었는가?','대상은1,2,3,4,5,6,8,13이며 직접 연구 대상은Problem13 M1이다. Problems7,9,10,11,12의 새 연구·redesign·학습·실험은 없다. Runtime/carry-over/causality/response/flexibility 및 A1→M1→A2→M2 contract는 기존 tracked bytes로 보존했다.'),
    ('PR112 evidence와 execution source의 보존은?', '1400개 inherited tracked 파일 SHA를 확인한다. original preregistration과 prepare snapshot도 SHA로 대조한다. EXECUTION_FREEZE와 actual execution marker commit이 optimization source를 결합하며 postprocessing source는 별도로 SOURCE_MANIFEST에 기록한다.'),
    ('새 partial incumbent를 언제 original UB로 채택하는가?','모든 original binaries의 integrality, full matrix, route/mode/SOC/PCS 및 reconstructed original grid validation이 통과할 때만 채택한다. fractional-outside partial point는 partial feasible upper certificate로만 사용하며 원 integer UB로 오인하지 않는다.')]
    assert len(qa)>=50
    prose('FINAL_REVIEW_KO.md','# 한국어 최종 검토\n\n'+'\n\n'.join(f'{i}. **{q}**\n\n   {answer}' for i,(q,answer) in enumerate(qa,1)))
    files=[p for folder in [ROOT/'v42_certificate',ROOT/'tests/v42_certificate'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    dump('SOURCE_MANIFEST.json',dict(BASE_HEAD=BASE,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(files)],
        frozen_execution_sha256=sha(OUT/'EXECUTION_FREEZE.json'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),scope_addendum_sha256=sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json'),
        original_template_sha256=sha(LOCAL/'F3.mps'),final_review_questions=len(qa)))
    print('REPORT COMPLETE',case,'UB',best,'LB',lb,'gap',gap,'questions',len(qa),flush=True)
if __name__=='__main__':run()
