"""Truthful gated results, Korean review, immutable bytes and evidence seals."""
import json
from .common import *
from .engine import relative_gap
from .runner import PROGRESS

def not_run(name,reason):
    if not (OUT/name).exists():
        record=dict(executed=False,status='NOT_RUN',reason=reason,accepted=False)
        if 'AUTHORIZATION' in name:record.update(authorized=False,budget_seconds=1800,max_runs=1)
        if 'P2' in name:record.update(P1_lock=None,inherited_P1_lock_tolerance=1e-7,lex_order=['movement_energy','movement_count'])
        dump(name,record)

def run():
    b=read('B3_CERTIFICATE.json');br=read('B3_DECOMPOSITION_RESULT.json')
    gate=read('FULL_M1_CANARY_AUTHORIZATION.json')
    if not gate['authorized']:
        not_run('FULL_M1_CANARY_RESULT.json','B3_EXACTNESS_PERFORMANCE_GATE_NOT_PASSED')
        table('FULL_M1_CANARY_PROGRESS.csv',[],PROGRESS)
    not_run('M1_PRODUCTION_AUTHORIZATION.json','FULL_M1_CANARY_NOT_AUTHORIZED_OR_NO_CLEAR_PROGRESS')
    not_run('M1_P1_DECOMPOSITION_RESULT.json','PRODUCTION_GATE_NOT_PASSED')
    not_run('M1_P2_DECOMPOSITION_RESULT.json','PRODUCTION_P1_NOT_ACCEPTED')
    p1=read('M1_P1_DECOMPOSITION_RESULT.json');p2=read('M1_P2_DECOMPOSITION_RESULT.json')
    lb=max(ORIGINAL_LB,b['partial_valid_LB'])
    ub=ORIGINAL_UB
    for result in [read('FULL_M1_CANARY_RESULT.json'),p1]:
        if result.get('executed'):
            if result.get('lower') is not None:lb=max(lb,result['lower'])
            if result.get('upper') is not None:ub=min(ub,result['upper'])
    flags=dict(FIXTURE_EXACTNESS_PASS=read('FIXTURE_EXACTNESS.json')['PASS'],RECOURSE_IS_LP=read('RECOURSE_LP_AUDIT.json')['PASS'],
        B3_CLASSIFICATION=b['classification'],B3_DECOMPOSITION_RUN=True,
        FULL_M1_CANARY_RUN=read('FULL_M1_CANARY_RESULT.json').get('executed',False),
        PRODUCTION_P1_RUN=p1.get('executed',False),PRODUCTION_P1_ACCEPTED=p1.get('accepted',False),
        P2_RUN=p2.get('executed',False),M1_ACCEPTED=bool(p1.get('accepted') and p2.get('P2_complete')),
        A1_RUN=False,A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,
        PROBLEM13_FINAL_VALIDATED=False,Actual_P_correction=False,Actual_Q_correction=False,Actual_PQ_repair=False,
        MESS_P_decision=True,MESS_Q_decision=True,B0_B1_WORK_TOUCHED=False,EXCLUDED_PROBLEMS_NEW_WORK=False,
        ORIGINAL_M1_UB=ub,ORIGINAL_M1_LB=lb,ORIGINAL_M1_IMPLIED_GAP=relative_gap(ub,lb),
        B3_feasibility_cuts=b['feasibility_cuts'],B3_optimality_cuts=b['optimality_cuts'],
        full_M1_feasibility_cuts=p1.get('feasibility_cuts',0),full_M1_optimality_cuts=p1.get('optimality_cuts',0))
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(verdict='INCONCLUSIVE' if not flags['M1_ACCEPTED'] else 'M1_ACCEPTED_DOWNSTREAM_NOT_AUTHORIZED',
        fixture_exactness=flags['FIXTURE_EXACTNESS_PASS'],recourse_LP=flags['RECOURSE_IS_LP'],
        B3=b['classification'],B3_status=b['result_status'],original_M1_UB=ub,original_M1_LB=lb,
        original_M1_gap=flags['ORIGINAL_M1_IMPLIED_GAP'],M1_ACCEPTED=flags['M1_ACCEPTED'],
        A2_M2_automatic_authorization=False,PROBLEM13_FINAL_VALIDATED=False))
    inherited=ROOT/'docs/v42_m1_b3_threshold_certificate/NUMERICAL_WARNING_AUDIT.json'
    dump('NUMERICAL_WARNING_AUDIT.json',dict(inherited_PR113_PR114=json.loads(inherited.read_text(encoding='utf8')),
        inherited_receipt_sha256=sha(inherited),new_B3_recourse=br['recourse_log'],
        unsafe_statuses_produce_no_cuts=True,uncertifiable_source=br['status']=='STOP_UNCERTIFIABLE',
        numerical_contradiction=any(r.get('reason') in ['GLOBAL_BOUND_CONTRADICTION','ASSEMBLED_POINT_VALIDATION'] for r in br['progress']),
        rational_certificate_scope='Cut validity on stored IEEE model coefficients, not rational proof of a timed-out LP or a global optimum',
        no_physics_retuning=True,no_Actual_repair=True))
    dump('FIXTURE_DEVELOPMENT_AUDIT.json',dict(first_fixture_coverage_check='J bound-ray coverage assertion failed; 12 census/optimum/cut-validity checks had passed',
        correction='Original J Q>=17 was already excluded by PCS16, so explicit finite bounds were not essential. Replaced J-only constraint with a bounded transformer auxiliary upper=1, lower>=1.1*travel stay.',
        near_zero_safeguard_passed=True,invalid_cut_used=False,production_physics_changed=False,
        corrected_fixtures_completed_before_B3=True,final_exhaustive_assignments=1536))
    (OUT/'NEXT_MODIFICATIONS.md').write_text('''# Next modifications

The current verdict and gates in FINAL_VERDICT.json are authoritative. Do not resume full M1, P2, A2 or M2 from an inconclusive threshold result. Preserve all evidence and use a separately preregistered implementation change if a new experiment is requested.

Potential implementation work: keep exact canonical audit/certificates but benchmark an equivalent LP representation that leaves original finite bounds native and maps their reduced-cost/Farkas contributions back to explicit canonical rows. Avoid treating simplex phase-I objectives or the zero-objective master bound as rho bounds. Investigate free-variable handling and doubled equalities without dropping scientific rows, relaxing bounds, pruning routes or changing voltage/SOC/PCS authority. An equivalent representation still needs exhaustive fixture/cut validation before a new full run. For residuals with unbounded support, implement exact rational stationary-ray reconstruction or a proved existing-row implication; never invent bounds or accept an uncertified ray.

The sequential baseline has no asynchronous recourse, no aggregation and no cut aging/deletion. Any performance comparison needs the same hardware, threads and resource observation scope. M2 uses the same explicit anchor/state engine and keeps route, mode, P, Q, SOC as decisions; M1 values can initialize Start only.
''',encoding='utf8')
    qa=[
    ('왜 route와 P/Q/SOC를 분해해도 joint optimization인가?','Master candidate마다 원래 전기·배터리 feasible set을 recourse가 검사하고 유효 cut으로 모든 discrete 대안을 연결한다. 최종 x/y는 같은 M-stage solution이다.'),
    ('물리적으로 무엇이 joint인가?','Route, stay/travel, charge mode, Pch/Pdis, Q, SOC, grid response가 원래 coupling 식을 동시에 만족한다.'),
    ('Master 변수는 무엇인가?','Full original M1은 route 207,928개와 mode 384개, 합계 208,312 binary다. B3 diagnostic만 85,744 binary다.'),
    ('Recourse 변수는 무엇인가?','Full M1은 108,431 continuous column이다. Pch/Pdis/Q/SOC/rho와 모든 grid auxiliary가 포함된다. B3는 outside binaries도 continuous로 남아 230,999 column이다.'),
    ('Mode가 master인 이유는?','충전/방전의 discrete authority를 유지하기 위해서다. Full M1에서 96 slots × 4 units 모두 binary다.'),
    ('SOC가 recourse인 이유는?','SOC는 continuous이고 고정 x에서 효율·travel debit을 포함하는 recurrence가 선형이다.'),
    ('Travel energy coupling은?','Departure slot의 original arc energy×x가 SOC recurrence RHS에 그대로 들어간다. Arrival 또는 connection 시점으로 옮기지 않는다.'),
    ('Grid coupling은 어디에 남는가?','All96 voltage, line, transformer current/kVA 행이 continuous recourse에 그대로 남는다. 고정 AIDC anchor도 유지된다.'),
    ('A1/A2는 왜 그대로 두는가?','이번 범위는 MESS solver implementation 검증이다. Exact compact AIDC optimizer와 outer architecture는 보존한다.'),
    ('M1/M2에만 Benders를 쓰는 이유는?','현재 M-stage의 binary route/mode와 continuous electrical/battery 분할이 고정 x LP를 만든다는 구조를 검증했다.'),
    ('Original feasible set을 보존하는가?','Stored matrix의 sign/duplication/column partition과 finite bounds를 exact audit했다. Full M1 모든 original binary를 master에 둔다. 모델 계수 차이는 0이다.'),
    ('Route pruning이 있는가?','없다. 새 Top-K, Hamming, trajectory pool, arc deletion은 없다. 기존 constructor의 original reachability authority만 그대로다.'),
    ('D-W/CG와 다른 점은?','전체 original discrete axis를 master에 유지한다. Trajectory column을 생성하거나 제한하지 않는다.'),
    ('Heuristic인가?','유효 Farkas/dual cuts를 이용하는 exact formulation이다. Timeout은 global solution 증명이 아니므로 INCONCLUSIVE로 보고한다.'),
    ('Global optimality를 유지할 수 있는가?','Cut validity와 모든 domain 보존이 유지되면 master lower bound와 검증된 assembled UB로 원래 global gap을 증명할 수 있다. 현재 full-scale acceptance 여부는 flags를 따른다.'),
    ('Recourse가 LP인가?','PASS. Remaining integer, quadratic, SOS, general constraint는 없다. PCS16/grid/SOC는 original linear rows다.'),
    ('Farkas cut은?','Canonical Ay≤b−Bx에서 λ≥0, Aᵀλ=0이면 λᵀ(b−Bx)≥0은 necessary feasibility condition이다. Strict negative source margin을 검증한다.'),
    ('Optimality cut은?','Min rho dual π≤0의 affine lower approximation을 theta≥πᵀb−πᵀBx로 master에 추가한다. Residual support와 rounding 보정도 포함한다.'),
    ('Bound contribution은 왜 필요한가?','Finite lower/upper bounds도 feasible set과 Farkas/dual stationarity의 일부다. 빠뜨리면 valid proof를 잃는다. Fixture J가 필수 bound case를 검사한다.'),
    ('Equality sign 처리는?','각 original equality를 정방향과 역방향 두 inequality로 보존한다. > row는 전체 부호를 반전한다.'),
    ('Numerical ray 검증은?','Sign, stored sparse products의 exact rational residual, bound support, strict margin, generated affine와 every known feasible assignment를 독립 검사한다. Infinite required support이면 NO CUT/STOP이다.'),
    ('Bounded fixture exactness는?',f"{flags['FIXTURE_EXACTNESS_PASS']}. A–L 12개 case, 각각 128개, 총 1,536 assignments를 두 LP representation으로 열거했다."),
    ('Monolithic optimum과 일치하는가?','모든 fixture에서 native census, canonical census, monolithic MILP, Benders P1 optimum과 selected route/mode optimum equivalence가 일치한다. 이것은 full M1 optimum claim이 아니다.'),
    ('Adversarial fixtures는?','SOC/grid/terminal/PCS16/upper voltage/transformer/threshold/degeneracy/near-zero/bounds/travel energy/route-dependent PQ를 포함한다. 48 payload mutations와 near-zero guard를 거부했다.'),
    ('B3 threshold 결과는?',b['classification']+'; native status '+b['result_status']+'.'),
    ('PR114보다 진전됐는가?',f"Registered progress gate={b['progress_beyond_root_bottleneck']}. Master가 candidate를 반환한 사실만으로 성능 향상을 주장하지 않는다."),
    ('B3 witness/proof가 나왔는가?',f"Certificate valid={b['certificate_valid']}. Threshold T={THRESHOLD}; zero-objective master bound는 rho LB가 아니다."),
    ('Full M1 canary를 실행했는가?',str(flags['FULL_M1_CANARY_RUN'])+'; authorization/result files에 이유를 기록했다.'),
    ('Full M1 UB/LB는?',f'Original validated UB={ub:.16g}, best valid global LB={lb:.16g}. B3 fractional point를 original UB로 승격하지 않는다.'),
    ('Gap은?',f"{flags['ORIGINAL_M1_IMPLIED_GAP']:.16g}, 즉 {100*flags['ORIGINAL_M1_IMPLIED_GAP']:.8f}%."),
    ('0.5%에 도달했는가?',str(flags['ORIGINAL_M1_IMPLIED_GAP']<=.005)+'.'),
    ('P1 accepted인가?',str(flags['PRODUCTION_P1_ACCEPTED'])+'. Good incumbent만으로 acceptance하지 않는다.'),
    ('P2를 실행했는가?',str(flags['P2_RUN'])+'. Production P1 acceptance 뒤에만 허용된다.'),
    ('Movement ordering은?','Inherited final contract movement energy → movement count다. Legacy reserve/tie를 P2 scientific tuple에 추가하지 않는다.'),
    ('P1 lock은 유지되는가?','P2 recourse에 rho≤accepted P1+1e-7를 넣는다. Energy component lock tolerance는 inherited 1e-8이다. 새 relaxation은 없다.'),
    ('M1 accepted인가?',str(flags['M1_ACCEPTED'])+'. P2 lex completion도 필요하다.'),
    ('A2를 실행했는가?','False. 이번 PR에서 자동 downstream production은 허용하지 않는다.'),
    ('M2를 실행했는가?','Production False. Reusable interface와 bounded tests만 구현한다.'),
    ('M2도 route/P/Q/SOC joint인가?','동일 engine이 explicit new anchor/state의 native model을 만든다. Route/mode/P/Q/SOC는 모두 의사결정 변수다.'),
    ('M1 route를 M2에 고정했는가?','아니다. 모든 original route bounds와 domain을 유지한다.'),
    ('Warm start와 fixing의 차이는?','Start는 solver hint다. LB/UB나 flow/domain을 바꾸지 않는다. Full M1 existing point는 exact axis와 physical/grid validation을 통과했다.'),
    ('Outer iteration 의미는?','A1→M1→A2→M2는 AIDC/MESS block-coordinate co-optimization이다. Accepted block의 footprint를 다음 block에서 freeze한다.'),
    ('Inner decomposition 의미는?','M-stage 내 master(route/mode)↔recourse(P/Q/SOC/grid)의 exact solver 반복이다. 물리적 최종 M-stage solution은 joint다.'),
    ('Full-grid rows는 어디에 있는가?','Canonical recourse에 original coefficient/RHS/sense를 유지한다. Discrete-only 행만 master에도 중복한다.'),
    ('Planning voltage는?','0.955–1.045 pu 그대로다. Eventual Fresh AC acceptance 0.95–1.05 pu와 혼동하지 않는다.'),
    ('Terminal SOC는?','모든 unit의 original equality와 96-slot recurrence를 유지한다. Relaxation 없다.'),
    ('PCS16은?','Individual 16-face linear inner polygon을 그대로 보존한다. 새 circle approximation 또는 capacity increase는 없다.'),
    ('Line.sw1/A bottleneck은?','Original line-face loading/rho 행과 fixed AIDC contribution에 포함된다. 특정 bottleneck row만 고르거나 다른 line을 삭제하지 않는다.'),
    ('Recourse count는?',str(b['recourse_calls'])+' B3 calls. Full M1 count는 별도 result의 executed 여부를 따른다.'),
    ('Feasibility cut 수는?',str(b['feasibility_cuts'])+' B3 cuts. Fixture census certificates와 full-scale cuts를 구분한다.'),
    ('Optimality cut 수는?',str(b['optimality_cuts'])+' B3 cuts. Threshold feasibility stage는 optimality cut이 필요 없다. Fixture P1에서는 dual cuts를 검증했다.'),
    ('Master iterations는?',str(b['iterations'])+' B3 iterations.'),
    ('Master time은?',str(b['master_seconds'])+' seconds; total wall에는 build/loop/certificate overhead가 포함된다.'),
    ('Recourse time은?',str(b['recourse_seconds'])+' seconds; solver-reported sum이다.'),
    ('Root bottleneck이 완화됐는가?',f"Registered gate={b['performance_gate']}. Terminal recourse/proof/witness가 없는 첫 master solve만으로는 통과하지 않는다."),
    ('Numerical warnings는?','PR113/114 warnings를 원문 receipt/hash와 함께 보존한다. New recourse warnings/status/residual/tolerances는 numerical audit와 raw logs에 저장한다.'),
    ('Thread 설정은?',str(read('RESOURCE_RECEIPT.json').get('B3_threads'))+' maximum configured threads. Sequential loop이며 recourse 동시 병렬 실행은 없다. Snapshot을 continuous absence proof로 표현하지 않는다.'),
    ('Current root-cause interpretation은?','Exact domain에서 제한된 수치/시간 budget만 관찰한다. Incomplete LP의 phase-I objective 또는 ancestry slot0은 integrality materiality/proof가 아니다.'),
    ('Next step은?','Equivalent native-bound LP representation과 certified residual handling을 별도 preregister/test할 수 있다. 현재 gate가 실패하면 full M1/A2/M2를 우회하지 않는다.'),
    ('PROBLEM13_FINAL_VALIDATED인가?','False. 이번 decomposition 검증만으로 Fresh AC/Actual/downstream acceptance를 증명하지 않는다.'),
    ('Cut aging/deletion은?','없다. Exact coefficient hash deduplication만 허용한다. 모든 provenance와 active/inactive history를 보존한다.'),
    ('Uncertifiable cut을 사용했는가?','없다. Strict certificate 실패는 cut을 추가하기 전에 STOP한다. Full experiment의 stop reason은 progress/result에 남긴다.'),
    ('기존 tests/44 checks는?','Inherited 643 tests를 full suite에서 보존한다. Original 44 bounded-check receipt와 bytes도 검증한다. 새 bounded fixture와 adapter tests는 별도다.'),
    ('Exact base와 bytes는?','PR114 exact 964b2c65964ff38089dab53c4e2fa03149d729f7에서 새 branch를 생성했다. Inherited 1,533 tracked file SHA와 Git diff를 검증한다.'),
    ]
    text='# V42 exact MESS Benders 검토\n\n'+''.join(f'{i}. **Q. {q}**\n\n   A. {a}\n\n' for i,(q,a) in enumerate(qa,1))
    (OUT/'FINAL_REVIEW_KO.md').write_text(text.rstrip()+'\n',encoding='utf8')
    (OUT/'README.md').write_text('''# Exact joint MESS Benders validation

Read FINAL_VERDICT.json and FINAL_REVIEW_KO.md first. Canonicalization and both cut derivations were committed before cut code. All original finite bounds and both equality directions remain explicit. Exact rational bound-compensated certificates are weaker, globally valid cuts on the stored linear model; no uncertified numerical ray is accepted.

`python -m v42_benders.fixtures` reproduces the bounded census and comparison. `python -m v42_benders.audit` performs real-model structural/matrix/warm-start audits without optimization. `python -m v42_benders.runner` is a once-only, preregistered B3 diagnostic guarded by a local execution marker. Do not rerun it or downstream production without new authorization/preregistration. `v42_benders.stage.solve_mess_stage_exact_benders` uses explicit anchor/state/authority and the same engine for M1 and M2. `v42_benders.production` enforces sequential registered gates and never runs A2/M2.

Cut payloads support independent fixture replay. Raw B3 logs, execution source checkpoint, partition axes and original inherited model receipt preserve provenance. Status/timeouts and non-run gated artifacts are explicit. All inherited files remain unchanged.
''',encoding='utf8')
    receipt=read('PR114_BASE_RECEIPT.json')
    changed=[r['path'] for r in receipt['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not changed,changed
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,files=len(receipt['files']),modified_files=changed,
        exact_base=BASE,actual_source_worktree_bytes_compared=True,
        inherited_44_bounded_check_receipt_sha256=sha(ROOT/'docs/v42_m1_integrality_gap_root_cause/WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')))
    print('REPORT',read('FINAL_VERDICT.json')['verdict'],'QA',len(qa),flush=True)

if __name__=='__main__':run()
