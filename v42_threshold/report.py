"""Postprocess immutable executions; never optimize."""
import shutil,re,xml.etree.ElementTree as ET
from .common import *
from .closure import diagnose

def run():
    direct=read(OUT/'B3_THRESHOLD_SOLVER.json');runs=[read(OUT/(k+'_SOLVER.json')) for k in ['W1','W2','DIRECT'] if (OUT/(k+'_SOLVER.json')).exists()]
    dump('ROOT_DATA_AUTHORITY.json',dict(root_sources=[dict(source=s,path=(RELAX/(s+'_ROOT_LP_SOLUTION.npz')).relative_to(ROOT).as_posix(),sha256=sha(RELAX/(s+'_ROOT_LP_SOLUTION.npz'))) for s in SOURCES],
        PR113_B3_root_vector_available=False,PR113_B3_SOLUTION_is_final_incumbent_not_root=True,
        unavailable_root_not_fabricated=True,root_optimization_calls=0))
    good=[r for r in runs if r['validation'] and r['validation']['threshold_certificate_PASS']]
    witness=min(good,key=lambda r:r['validation']['rho']) if good else None
    contradiction=bool(witness and direct['solver_status']==3)
    case='B3_INCONCLUSIVE' if contradiction else classify(witness['validation'] if witness else None,direct['solver_status'])
    if witness:
        shutil.copyfile(OUT/(witness['kind']+'_SOLUTION.npz'),OUT/'B3_THRESHOLD_FEASIBLE_POINT.npz')
        dump('B3_THRESHOLD_POINT_VALIDATION.json',dict(witness['validation'],source=witness['kind'],point_sha256=sha(OUT/'B3_THRESHOLD_FEASIBLE_POINT.npz')))
    upper_candidates=[dict(value=ORIGINAL_UB,source='PR113_FULL_ORIGINAL_INTEGER_START',original=True)]
    promotions=[]
    for r in runs:
        v=r['validation']
        full=None
        if v and v['original_M1_UB_eligible']:
            from v42_certificate.common import original_validation
            with np.load(OUT/(r['kind']+'_SOLUTION.npz'),allow_pickle=False) as z:full=original_validation(z['names'],z['values'])
        if v:
            promotions.append(dict(kind=r['kind'],all_original_binary_integrality_screen=v['original_M1_UB_eligible'],
                independent_full_original_validation=full,promotable_original_UB=bool(full and full['valid_new_UB']),
                screen_alone_not_promotion_authority=True))
        if v and v['B3_feasible_PASS']:upper_candidates.append(dict(value=v['rho'],source=r['kind'],original=bool(full and full['valid_new_UB'])))
    dump('ORIGINAL_M1_PROMOTION_AUDIT.json',dict(PASS=True,points=promotions,
        original_UB_requires_all_original_integrality_and_full_original_physical_grid_validation=True,clip=False,repair=False))
    partial=min(upper_candidates,key=lambda x:x['value'])
    original=min([c for c in upper_candidates if c['original']],key=lambda x:x['value'])
    original_LB=max(S2,T if case=='B3_POSITIVE_CERTIFIED' else S2)
    partial_LB=max(.5718504565144596,T if case=='B3_POSITIVE_CERTIFIED' else .5718504565144596)
    certificate=dict(classification=case,T=T,validated_safe_witness_found=bool(witness),witness_source=witness['kind'] if witness else None,
        validated_witness_rho=witness['validation']['rho'] if witness else None,partial_feasible_upper=partial['value'],partial_upper_source=partial['source'],
        partial_valid_LB=partial_LB,partial_optimum_interval=[partial_LB,partial['value']],
        negative_certificate=case=='B3_NEGATIVE_CERTIFIED',positive_certificate=case=='B3_POSITIVE_CERTIFIED',certificate_valid=case!='B3_INCONCLUSIVE',
        direct_solver_status=direct['solver_status'],unrestricted_threshold_proven_infeasible=case=='B3_POSITIVE_CERTIFIED',
        numerical_contradiction=contradiction,solver_objective_bound_not_rho_bound=True,
        positive_interpretation='opt_B3 > T from native exact-threshold MIP infeasibility; T itself is a valid lower bound, no invented strict epsilon.' if case=='B3_POSITIVE_CERTIFIED' else None,
        negative_interpretation='Validated B3 witness provides opt_B3 <= rho <= T, hence opt_B3-S2 <=0.001.' if case=='B3_NEGATIVE_CERTIFIED' else None,
        attribution='Joint B3 integrality only. No unique route/mode/SOC cause is certified.',
        incumbent_search_failures_not_negative_evidence=True,no_rational_arithmetic_proof_claim=True,
        numerical_boundary_guard=THRESHOLD_MARGIN,threshold_not_relaxed=True,original_M1_UB=original['value'],original_M1_LB=original_LB)
    dump('B3_THRESHOLD_CERTIFICATE.json',certificate)
    diagnose(case);closure=read(OUT/'CAUSAL_BACKWARD_CLOSURE.json')
    numerical=[];root_audits=[]
    for r in runs:
        raw=gzip.decompress((OUT/(r['kind']+'_SOLVER.raw.gz')).read_bytes()).decode()
        warnings=[s.strip() for s in raw.splitlines() if any(k in s for k in ['Warning','quad precision','Numerical'])]
        rootlines=[s.strip() for s in raw.splitlines() if s.startswith('Root relaxation:')]
        completed=any('objective ' in s and 'interrupted' not in s.lower() for s in rootlines)
        root_audits.append(dict(kind=r['kind'],raw_root_lines=rootlines,runner_root_line_present_observation=r['root_completed'],
            independently_completed_feasible_root=completed,root_interrupted=any('interrupted' in s.lower() for s in rootlines),
            root_time_limited=any('time limit' in s.lower() for s in rootlines),
            raw_overall_status=r['solver_status'],overall_status_not_relabelled=True,
            interpretation='The frozen runner root_completed field detects a Root relaxation log line, which may be interrupted or time limited. This independent audit requires the completed objective line; root-line presence is not root completion.'))
        numerical.append(dict(kind=r['kind'],solver_status=r['solver_status'],warnings=warnings,callback_errors=r['callback_errors'],
            point_validation=r['validation'],root_completed=completed,raw_log_sha256=r['raw_log_sha256'],
            zero_objective_bound_is_not_B3_P1_lower_bound=True,numerical_failure=r['solver_status']==12))
    dump('ROOT_COMPLETION_AUDIT.json',dict(runs=root_audits,raw_solver_receipts_preserved=True,optimization_source_unchanged=True))
    dump('NUMERICAL_WARNING_AUDIT.json',dict(inherited_PR113_warnings=read(PR113/'NUMERICAL_WARNING_AUDIT.json'),new_runs=numerical,
        solver_warnings_preserved=True,incumbent_matrix_tolerance=MATRIX_TOL,integer_tolerance=INTEGER_TOL,threshold_margin=THRESHOLD_MARGIN,
        no_threshold_relaxation=True,no_clipping_or_repair=True,no_rational_proof_claim=True))
    flags=dict(BASE_PR=113,BASE_HEAD=BASE,T=T,CERTIFICATE_CLASSIFICATION=case,B3_THRESHOLD_SOLVER_STATUS=direct['solver_status'],
        DIRECT_ROOT_COMPLETED=next(r['independently_completed_feasible_root'] for r in root_audits if r['kind']=='DIRECT'),
        B3_THRESHOLD_FEASIBLE=case=='B3_NEGATIVE_CERTIFIED',B3_SAFE_WITNESS_FOUND=bool(witness),B3_PARTIAL_FEASIBLE_UPPER=partial['value'],
        B3_PROVEN_INFEASIBLE=case=='B3_POSITIVE_CERTIFIED',B3_NEGATIVE_CERTIFICATE=case=='B3_NEGATIVE_CERTIFIED',B3_POSITIVE_CERTIFICATE=case=='B3_POSITIVE_CERTIFIED',
        CAUSAL_BACKWARD_CLOSURE_EARLIEST_SLOT=closure['earliest_causal_predecessor_slot'],CAUSAL_BACKWARD_CLOSURE_EXECUTION=closure['execution'],
        ORIGINAL_M1_UB=original['value'],ORIGINAL_M1_UB_SOURCE=original['source'],INHERITED_ORIGINAL_M1_UB=ORIGINAL_UB,
        ORIGINAL_M1_LB=original_LB,INHERITED_ORIGINAL_M1_LB=S2,ORIGINAL_M1_IMPLIED_GAP=(original['value']-original_LB)/original['value'],
        M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,PRODUCTION_M1_RUN=False,PRODUCTION_P1_ACCEPTED=False,P2_RUN=False,A2_ALLOWED=False,
        A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,MAY_CAMPAIGN_RUN=False,SENSITIVITY_CAMPAIGN_RUN=False,
        NEW_ML_TRAINING=False,RUNTIME_REDESIGNED=False,CC4_REDESIGNED=False,ACTUAL_P_CORRECTION=False,ACTUAL_Q_CORRECTION=False,
        B1_OPTIMIZE_CALLS=0,B2_OPTIMIZE_CALLS=0,B0_WORK_TOUCHED=False,B1_COMPARISON_WORK_TOUCHED=False,
        DIRECT_OPTIMIZE_CALLS=1,WITNESS_OPTIMIZE_CALLS=len(runs)-1,TOTAL_NEW_OPTIMIZE_CALLS=len(runs),PARAMETER_SWEEPS=0,FALLBACKS=0,
        EXPANDED_WINDOW_OPTIMIZE_CALLS=0,DECOMPOSITION_IMPLEMENTED=False,DECOMPOSITION_OPTIMIZE_CALLS=0,NEW_FORMULATION_CUTS=0,
        SCIENTIFIC_ROW_CHANGES=0,NEW_THRESHOLD_ROWS=1,FEASIBILITY_OBJECTIVE_ZERO=True,FULL96_GRID_RETAINED=True,
        TERMINAL_SOC_RETAINED=True,PCS16_RETAINED=True,ROUTE_DOMAIN_COMPLETE=True,B3_RESTORED_BINARY_COUNT=85744,
        PLANNING_VOLTAGE=[.955,1.045],FRESH_AC_ACCEPTANCE_VOLTAGE=[.95,1.05],MESS_P_DECISION_ON=True,MESS_Q_DECISION_ON=True,
        PRESERVED_PROBLEMS=[1,2,3,4,5,6,8,13],EXCLUDED_PROBLEMS_NEW_WORK=False)
    if (OUT/'PYTEST_RESULTS.xml').exists():
        suite=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite')
        flags.update(FULL_TESTS=int(suite.attrib['tests']),NEW_TESTS=int(suite.attrib['tests'])-593,
            TESTS_PASS=int(suite.attrib['failures'])==int(suite.attrib['errors'])==int(suite.attrib.get('skipped',0))==0)
    dump('FINAL_FLAGS.json',flags);dump('FINAL_VERDICT.json',dict(flags,certificate=certificate))
    if case=='B3_NEGATIVE_CERTIFIED':
        nexttext='B3 nonmaterial ceiling certificate를 보존한다. B1/B2 실행은0이며 후속 작업도 별도 사용자 승인 후 정한다. 이번 ceiling은 late-window B3 integrality만 대상으로 하므로 전체 original-M1 gap이나 window 밖의 integrality를 배제하지 않는다. 특정 route/mode/SOC strengthening을 선택하지 않는다.'
    elif case=='B3_POSITIVE_CERTIFIED':
        nexttext='Joint B3 material contribution이 증명됐다. route, mode, buffer의 개별 기여는 아직 분리되지 않았다. 다음 분해 실험은 별도 사용자 승인 후 사전등록하며 이번 PR에서 B1/B2나 production을 자동 실행하지 않는다.'
    else:
        nexttext='Threshold question은 INCONCLUSIVE다. Dependency closure의 earliest slot은0이며 후보 window는0–95다. 이는 가능한 물리 ancestry이고 전체 과거 integrality 복원이 필요·충분하거나 material하다는 증명이 아니다. 확대 B3를 이번에 실행하지 않는다. 사전등록 결과의 root/search/resource 병목을 감사하고 별도 후속 exact feasibility decomposition의 exactness와 bounded fixtures를 먼저 검토한다.'
    bottleneck=case=='B3_INCONCLUSIVE' and direct['solver_status'] in [9,17]
    decomposition='''

## Conditional exact feasibility decomposition design (not implemented)

Master x consists of precisely the 85,744 B3-restored route and charge-mode binaries. Recourse y includes all remaining original variables, including outside-B3 fractional route/modes, Pch/Pdis/Q/SOC and full96 grid auxiliaries. Preserve every original row, the fixed AIDC anchor, initial/terminal SOC, PCS16, voltage band, route authority and the exact rho<=T row. Do not replace B3 with a stronger full-binary original-M1 master.

Normalize recourse rows and all finite bounds as A y <= b-B x, replacing equalities by two inequalities. A Farkas ray lambda>=0 with lambda^T A=0 and lambda^T(b-B xbar)<0 proves infeasible recourse at xbar. The valid master feasibility cut is lambda^T(b-B x)>=0. Sign conventions, variable bounds, stationarity residual and strict ray margin must be independently verified before retaining a cut. An uncertified numerical ray or timed-out recourse generates no cut. Mixed native senses and bound contributions must never be omitted.

Exactness: every B3-feasible (x,y) satisfies each validated Farkas cut. A master assignment plus feasible full recourse is a B3 witness; infeasible master after valid cuts excludes all assignments. This preserves the projection of the original threshold feasible set; early timeout still remains inconclusive. This is a future design, not a production implementation, and no Dantzig-Wolfe/column generation replacement is proposed here.

Bounded fixture proposal: a two-slot legal-route/charge-mode battery instance with finite power/SOC bounds, terminal equality, 16 PCS faces and a grid threshold. Enumerate every binary master assignment and solve exact recourse, compare monolithic and decomposed feasible sets, verify every feasible assignment survives all generated cuts, and deliberately perturb ray sign/bound terms to ensure rejection. Include an outside-window fractional mode fixture, infeasible terminal energy, feasible threshold witness, and a numerical-borderline ray. Fixtures are design only in this PR; no new decomposition optimize calls.

[Gurobi infeasibility analysis](https://docs.gurobi.com/projects/optimizer/en/current/features/infeasibility.html) explains IIS availability and the expense of MIP IIS. Farkas certificates certify continuous recourse, not full-MIP infeasibility by themselves.
''' if bottleneck else '\n\nExact decomposition fallback design is not activated because the conditional inconclusive computational-bottleneck gate did not hold.'
    prose('NEXT_MODIFICATIONS.md','# 다음 작업\n\n'+nexttext+decomposition)
    status=direct['solver_status'];rho=witness['validation']['rho'] if witness else None
    qa=[
    ('왜 다시 B3 optimum 전체를 풀지 않았는가?','이번 primary question은 rho<=T point의 존재다. 원 min-rho optimum 계산 대신 exact hard-row/zero-objective decision model을 한 번 수행했다.'),
    ('threshold T는 정확히 어떻게 계산했는가?',f'Decimal authority로 S2 {S2} +0.001 = {T}를 계산했다. binary float serialization도 THRESHOLD_AUTHORITY에 기록했다.'),
    ('왜 T=0.5732125039436496인가?','PR113 inherited S2 original-M1 LB와 사전등록 material increment0.001의 합이다. F3 값이나 결과를 보고 threshold를 바꾸지 않았다.'),
    ('S2 LB는 B3 lower floor인가?','아니다. S2는 original-M1 reference LB다. S2 relaxation과 B3 feasible set의 포함관계가 자동으로 주어지지 않으므로 partial optimum floor로 설치하지 않았다.'),
    ('S2를 threshold reference로 어떻게 쓰는가?','opt_B3-S2<=0.001의 ceiling을 검사한다. 이는 opt_B3<=S2+0.001라는 decision question이다.'),
    ('threshold feasibility는 scientific question과 동치인가?','F_B3 안에서 rho<=T인 점이 존재하면 optimum<=T다. 기존 feasible upper로 F_B3가 비어 있지 않고 변수/연속 objective는 native bounded feasible set에서 정의되므로 threshold infeasibility는 optimum>T를 의미한다.'),
    ('witness 하나가 왜 negative certificate인가?','B3-restored integrality와 모든 original row를 만족하는 점은 B3 optimum의 upper다. rho<=T면 materiality reference의 기여 ceiling0.001을 확보한다.'),
    ('threshold infeasibility가 왜 positive certificate인가?','Unrestricted F_B3와 rho<=T의 교집합이 비었다는 solver proof는 opt_B3>T를 의미한다. T를 valid LB로 사용할 수 있으나 임의 strict epsilon을 더하지 않는다.'),
    ('heuristic witness search는 scientific replacement인가?','아니다. Root-nearest route들은 제한 subset에서 feasible upper point를 찾는 generator다. Exact direct model의 graph/bounds를 제한하지 않았다.'),
    ('candidate 실패가 왜 negative evidence가 아닌가?','제한 route subset의 infeasibility는 다른 route의 존재를 배제하지 않는다. 이를 B3 전체의 material/nonmaterial certificate로 승격하지 않았다.'),
    ('root flow를 route candidate로 어떻게 변환했는가?','원 time-expanded DAG의 complete0–96 path에서 duration-weighted arc L1 distance를 최소화했다. 이는 selected duration*root-flow 합을 최대화하는 dynamic program이며 원 arc order로 tie를 고정했다.'),
    ('route candidate는 원 graph를 보존하는가?','모든 선택 arc는 native legal route/stay authority에 존재하며 출발/도착/connection/energy와 initial site에서96까지 continuity를 검증했다. 원 scientific direct graph의 arc를 삭제하지 않았다.'),
    ('candidate 수를 결과 후 바꾸었는가?','아니다. BASE F3와 S3 source 각1개, 총2개 joint candidates를 preregister했다. Exact duplicate B3 fixed-route signature만 기록 후 skip할 수 있으며 후보를 추가하지 않는다.'),
    ('PR113 B3 root vector를 사용했다고 주장했는가?','아니다. Native B3 root objective/log는 있지만 saved B3 root vector는 없다. B3_SOLUTION.npz는 최종 incumbent이며 ancestry에서 그 이름으로만 썼다. Route generation은 저장된 BASE F3와 S3 roots를 사용하고 unavailable B3 root를 꾸미지 않았다.'),
    ('B3 restored binary count는 그대로인가?','85,744개다. PR113 mask와 독립 selected-arc rule을 대조했다. 58–95 mode와 occupancy/entry-crossing/departure 관련 route binary authority를 그대로 유지했다.'),
    ('terminal SOC를 유지했는가?','원 terminal equality4개와 초기 equality4개를 유지했다. SOC96=760을 원 sense/RHS/coefficients로 대조했다. TERM_RELAX는 사용하지 않았다.'),
    ('full96 grid를 유지했는가?','원954,560개 rows를 모두 exact 보존했다. 추가는 threshold row1개뿐이며 all96 voltage/line/transformer current/kVA와 individual PCS16을 유지했다.'),
    ('voltage 0.955–1.045를 유지했는가?','Planning band를 그대로 유지했다. Fresh AC0.95–1.05는 상속된 계약이며 이번에 Fresh AC를 실행하지 않았다.'),
    ('threshold row 외 scientific physics 변경이 있는가?','없다. Direct model의 변수/bounds/VTypes/original row order/senses/coefficients/RHS는 PR113 B3와 exact 일치한다.'),
    ('zero objective가 원 feasible set을 바꾸는가?','목적식은 feasible set을 바꾸지 않는다. rho epigraph 변수와 original P1 row semantics는 남으며 hard threshold row가 decision subset을 정의한다.'),
    ('native solver status는?',f'Direct overall status={status}. Raw log와 status를 그대로 저장했고 status9/11/12를 OPTIMAL 또는 INFEASIBLE로 재표기하지 않았다.'),
    ('feasible witness를 발견했는가?',f'Safe independent witness={bool(witness)}; source={witness["kind"] if witness else None}; final classification={case}.'),
    ('validated witness rho는 얼마인가?',f'{rho}. Witness가 없으면 partial upper는 inherited original-feasible start 또는 별도 validated partial point의 rho만 사용한다. Best partial upper={partial["value"]}.'),
    ('threshold slack은 얼마인가?',f'{witness["validation"]["threshold_slack"] if witness else None}. Safe certificate는 rho와 recomputed P1 모두 T-1e-6 이하일 때만 인정한다.'),
    ('maximum matrix residual은?',f'{witness["validation"]["threshold_matrix"]["max_residual"] if witness else None}. 점이 없으면 residual을0으로 꾸미지 않는다. 각 native point validation에 실제 residual을 저장한다.'),
    ('partial point를 original UB로 오인하지 않았는가?','B3 outside binaries가 fractional인 점은 partial upper만 된다. 모든208,312 original binaries integrality 및 full original matrix/graph/battery/grid 검증이 통과해야 original UB 후보가 된다.'),
    ('proven infeasible인가?',f'{case=="B3_POSITIVE_CERTIFIED"}. Only unrestricted DIRECT overall status3가 positive proof authority다. Restricted W1/W2 status3는 이 authority가 아니다.'),
    ('TIME_LIMIT이면 왜 inconclusive인가?','시간 종료는 feasible point 부재나 model infeasibility의 증명이 아니다. independently safe witness 또는 exact infeasibility proof가 없으면 INCONCLUSIVE를 유지한다.'),
    ('numerical warnings는?',f'PR113 basis/quad warning을 보존했다. 새 warnings는 NUMERICAL_WARNING_AUDIT의 각 run에서 actual raw log로 추출했다. Numerical contradiction={contradiction}; rational-arithmetic exact proof를 주장하지 않는다.'),
    ('Threads 설정 이유는?','Preregistration snapshot과 각 start snapshot에서 independent heavy solve를 관측했다. None이면4, heavy이면1이라는 정책을 등록했다. 실제 registered threads='+str(read(OUT/'PREREGISTRATION.json')['threads'])+'이며 성능 우월성을 주장하지 않는다.'),
    ('parallel resource contention이 있었는가?','각 run 시작 전1초 CPU/RSS snapshot을 보존했다. 등록4 threads와 heavy contention이 겹치면 실행 전 중단하는 guard가 있다. Snapshot에서 관측하지 못한 것을 전체 wall-time의 부재 증명으로 과장하지 않는다.'),
    ('slot58 state는 무엇인가?','ROOT_GUIDED_STATES.csv에 inherited BASE/S3의 SOC/mode/P/Q/site/transit mass를 보존했다. Conditional ancestry는 '+closure['execution']+'이며 실시한 경우 CAUSAL_BACKWARD_CLOSURE의 unit별 state_at_58에 기록했다.'),
    ('SOC58은 어떻게 형성됐는가?','Initial760 + slots0–57 eta-adjusted charge − discharge − departure travel-energy debit다. Diagnosis gate가 열리면 stored/reconstructed SOC와 누적 항을 unit/source별로 실제 계산한다.'),
    ('SOC66 ancestry는 어디까지 이어지는가?','원 energy recurrence에서 SOC66→SOC65→...→SOC0로 이어진다. 실제 conditional audit 실행 여부와 source별 energy contributions는 closure file에 기록하며 certificate case에서는 Phase D를 skip한다.'),
    ('earliest causal predecessor slot은?',f'{closure["earliest_causal_predecessor_slot"]}. Diagnosis가 수행되면0은 structural physical dependency 결과이며 관측상의 첫 nonzero charge/travel slot과는 구분한다.'),
    ('58 buffer가 충분했다는 증거가 있는가?','단지58부터 integrality를 복원했다는 이유로 경계 ancestry가 닫혔다고 할 수 없다. Certificate가 없으면 sufficiency를 주장하지 않는다. Threshold certificate 자체도 전체 original-M1 gap의 완전 분해를 뜻하지 않는다.'),
    ('왜 임의 window search를 하지 않았는가?','1h/2h/4h/8h parameter sweep을 하지 않았다. Physics/graph predecessor closure만 계산하며 확대 experiment는 별도 사용자 승인 후다.'),
    ('causal backward closure의 물리적 의미는?','경계SOC/location에 영향을 줄 수 있는 가능한 이전 transition/dispatch/travel dependencies다. 어떤 모든 ancestor가 active/material하다는 뜻이나 Planning의 최적화 coupling을 time-forward causal effect로 읽는 증명이 아니다.'),
    ('line.sw1/A와 어떤 관계가 있는가?','Inherited late66–95 bottleneck faces는 P/Q/location에 의존한다. 그 controls의 SOC/location ancestry는 앞선 history에 이어질 수 있으나 descriptive sensitivity를 unique integer-gap cause로 승격하지 않았다.'),
    ('charge-mode ancestry는?','Pch<=P_limit*mode, Pdis<=P_limit*(1-mode), SOC recurrence를 통해 이전 dispatch에 연결된다. Outside58의 continuous mode는 scientific B3 relaxation으로 남겼다.'),
    ('route ancestry는?','Initial-site flow conservation과 time-expanded legal transitions의 backward reachable ancestry다. Crossing travel arc의 departure와 connection을 포함하며 중간 transit을 가상의 stay로 바꾸지 않았다.'),
    ('travel-energy ancestry는?','Travel energy는 departure slot SOC transition에서 차감된다. At58/66 in-transit state의 earlier departure를 누락하지 않고 graph/energy audit에 반영한다.'),
    ('다음 window를 확장해야 하는가?','Closure0이면0–95를 future candidate로 제안할 수 있지만 필요/충분/material하다는 certificate는 아니다. 이번 PR에서는 expanded-window optimize0이며 automatic 확대를 하지 않았다.'),
    ('exact decomposition이 필요한가?',f'Conditional design gate={bottleneck}. Monolithic unfinished search가 확인된 경우에만 future exactness proof와 bounded fixture design을 NEXT_MODIFICATIONS에 기록했다.'),
    ('Benders feasibility decomposition은 original set을 보존 가능한가?','B3 restored binaries만 master로 두고 나머지 full96 constraints/continuous outside variables를 recourse로 유지하면 가능하다. Verified Farkas feasibility cuts가 모든 feasible projection을 보존해야 하며 bound/sign/ray residual audit가 필요하다.'),
    ('새 cut을 이번에 구현했는가?','없다. Threshold row는 scientific decision question의 정의다. Solver built-in cuts와 future decomposition feasibility-cut design은 구분하며 production cut/decomposition implementation은0이다.'),
    ('B1/B2 optimize calls는0인가?','둘 다0이다. PR113 inherited evidence와 별도중단된 B0/B1 comparison work를 수정하거나 실행하지 않았다.'),
    ('production M1을 실행했는가?','실행하지 않았다. Exact threshold diagnostic은 production P1/P2 acceptance solve가 아니다.'),
    ('M1 accepted인가?','M1_ACCEPTED=false다. Threshold point 또는 threshold infeasibility는 production P1/P2 certificate를 대신하지 않는다.'),
    ('Problem13 final validated인가?','PROBLEM13_FINAL_VALIDATED=false다. A2→M2→Planning→Actual replay→Fresh AC final chain을 실행하지 않았다.'),
    ('다음 정확한 작업은 무엇인가?',nexttext),
    ('기존 original UB/LB와 현재 값은?',f'Inherited UB={ORIGINAL_UB}, S2 LB={S2}. Current validated original UB={original["value"]}, certified original LB={original_LB}, implied gap={(original["value"]-original_LB)/original["value"]*100:.8f}%. Partial upper와 zero-objective bound를 original integer UB/LB로 오인하지 않았다.'),
    ('row aliases 때문에 exactness가 약해졌는가?','Native duplicate row-name alias map은 PR113 그대로다. 원 ordered CSR data/indices/indptr, RHS/senses/bounds/variable axis와 같은 순서의954,560 rows를 exact 비교했다.'),
    ('same complete start를 threshold에서 accepted라고 주장했는가?','아니다. PR113 native B3 acceptance evidence를 보존하지만 rho0.591281은 T를 초과한다. Threshold에는 partial binary seed 또는 independent threshold witness만 넣으며 native rejection/acceptance log를 보존한다.'),
    ('zero-objective BestBd0은 rho LB인가?','아니다. Feasibility objective의 bound는 constant0에 대한 값이다. P1 rho lower certificate는 threshold infeasibility의 논리적 T lower bound 또는 inherited B3/S2 bounds에서만 나온다.'),
    ('Root relaxation log line만 있으면 root completion인가?','아니다. Frozen runner의 root_completed 필드는 log line 존재 관측이며 interrupted/time-limit line도 포함할 수 있다. ROOT_COMPLETION_AUDIT는 completed objective line과 time-limit/interrupted line을 독립 구분하고 FINAL_FLAGS의 DIRECT_ROOT_COMPLETED를 계산한다. 원 receipt/source/status는 수정하지 않았다.'),
    ('threshold 경계 tolerance를 어떻게 처리했는가?','Hard row는 exact T를 유지한다. Native FeasibilityTol/IntFeasTol1e-7, independent matrix1e-6, integer1e-7, epigraph recomputation1e-7 및 safe margin1e-6을 실행 전에 등록했다. Ambiguous near-boundary point는 certificate로 승격하지 않는다.'),
    ('objective recomputation residual은 어떻게 정의하는가?','Zero objective에서는 rho epigraph가 tight할 필요가 없다. All96 original line faces의 maximum을 독립 재계산하고 max(0,recomputed-rho)를 violation으로 기록한다. rho-recomputed는 allowable epigraph slack이다.'),
    ('solver proof와 IIS/Farkas를 혼동했는가?','Native unrestricted MIP INFEASIBLE status는 branch-and-bound proof authority다. LP FarkasDual은 full MIP의 직접 proof가 아니다. IIS API 가능 여부와 미계산 이유를 보존하고 expensive MIP IIS나 extra LP를 자동 실행하지 않았다.'),
    ('execution source를 결과 후 바꾸었는가?','EXECUTION_FREEZE의 optimizer/validator/route/preflight test source를 pre-execution commit에서 동결했다. Actual run markers가 그 commit과 preregistration SHA를 결합한다. Report/closure/verification은 별도 postprocessing source다.'),
    ('기존593 tests와44 bounded checks는?','1464 inherited tracked 파일의SHA를 검증하고 기존593 test suite를 전체 다시 실행한다. Inherited44 bounded check receipt/source도 그대로 보존한다. 추가 execution-evidence tests를 함께 기록한다.'),
    ('범위 밖 numbered Problems를 건드렸는가?','Problems1,2,3,4,5,6,8,13을 보존했다.7,9,10,11,12의 새 실험/redesign/학습은0이다. Runtime/carry-over/known-unknown/response/A1→M1→A2→M2/flexibility contracts를 byte 보존했다.')]
    assert len(qa)>=50
    prose('FINAL_REVIEW_KO.md','# 한국어 최종 검토\n\n'+'\n\n'.join(f'{i}. **{q}**\n\n   {a}' for i,(q,a) in enumerate(qa,1)))
    prose('README.md',f'''# B3 threshold certificate

Exact PR113 base `{BASE}`. T={T}; scientific decision is F_B3 intersect rho<=T with constant-zero objective, not another min-rho run. Matrix audit preserves all original954,560 rows and adds only one threshold row. Two registered root-route witness generators plus one unrestricted direct solve; no B1/B2/production/downstream/cuts.

Final classification **{case}**; direct status={status}; safe witness={bool(witness)}; best partial upper={partial['value']}; proven unrestricted infeasible={case=='B3_POSITIVE_CERTIFIED'}. Candidate-fixed infeasibility never counts as full B3 proof. Numerical warnings/tolerance guard and inherited basis/quad warnings remain visible. Actual original UB={original['value']}, LB={original_LB}; M1_ACCEPTED/PROBLEM13_FINAL_VALIDATED=false.

Preregistration and source checkpoint preceded every optimize call. EXECUTION_FREEZE and execution markers seal those sources; SOURCE_MANIFEST records later reporting code. Independent graph/battery/all96-grid validation does not clip or repair values. The inherited full integer start violates threshold and is not represented as feasible in the new model. A partial B3 witness outside integrality is not an original-M1 UB. See FINAL_REVIEW_KO, B3_THRESHOLD_CERTIFICATE, NUMERICAL_WARNING_AUDIT and NEXT_MODIFICATIONS.

{nexttext}''')
    files=[p for folder in [ROOT/'v42_threshold',ROOT/'tests/v42_threshold'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    dump('SOURCE_MANIFEST.json',dict(BASE_HEAD=BASE,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(files)],
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),execution_freeze_sha256=sha(OUT/'EXECUTION_FREEZE.json'),Korean_questions=len(qa)))
    print('THRESHOLD REPORT',case,'partial upper',partial['value'],'questions',len(qa),flush=True)

if __name__=='__main__':run()
