"""Report measured window-oracle results without new optimization."""
import re
from .common import *

REQUIRED='''README.md PREREGISTRATION.json PR110_BASE_RECEIPT.json BASE_F3_IDENTITY.json A1_ANCHOR_REUSE.json FROZEN_CRITICAL_SLOTS.json MULTITIME_WINDOW_FREEZE.json W7_FORMULATION.md W7_MATRIX_CENSUS.json W7_VALIDATION.csv W7_ORACLE_STATS.csv G1_BETA_TABLE.csv G1_ROOT_PRECHECK.csv G1_VALIDITY_PROOF.md G2_BETA_TABLE.csv G2_TRANSPORT_PRECHECK.csv G2_VALIDITY_PROOF.md G3_TIME_PAIR_FREEZE.json G3_REACHABLE_STATE_PAIRS.csv G3_ROOT_MARGINAL_FEASIBILITY.csv G3_BETA_TABLE.csv G3_TRANSPORT_PRECHECK.csv G3_VALIDITY_PROOF.md ROUTE_FLOW_INTEGRALITY_DIAGNOSIS.json EPIGRAPH_SELECTION.json CUT_MATRIX_COST.csv ROOT_LP_COMPARISON.csv ROOT_BOUND_GAIN_REPORT.json MIP_CANARY_OPTIMIZATION.json MIP_CANARY_PROGRESS.csv M1_PRODUCTION_OPTIMIZATION.json M1_PRODUCTION_PROGRESS.csv M1_PHYSICAL_VALIDATION.json M1_ROBUST_VOLTAGE_REPORT.json RESIDUAL_GAP_DIAGNOSIS.json NEXT_MODIFICATIONS.md FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json'''.split()

def prose(n,s):
    (OUT/n).write_text(s.strip()+'\n',encoding='utf8')

def run():
    selection=read(OUT/'EPIGRAPH_SELECTION.json');census=read(OUT/'W7_MATRIX_CENSUS.json');resources=read(OUT/'W7_WORKER_RESOURCE_RECEIPT.json')
    stop=read(OUT/'W7_UNIVERSAL_STOP_CERTIFICATE.json');root=read(OUT/'ROOT_SOURCE_RECEIPT.json')
    loading=[]
    with (PRIOR/'ROOT_SLOT_LOADING.csv').open(encoding='utf8') as f:
        for r in csv.DictReader(f):loading.append({k:float(v) for k,v in r.items()})
    inside=[r for r in loading if int(r['time']) in WINDOW];outside=[r for r in loading if int(r['time']) not in WINDOW]
    imax=max(inside,key=lambda r:r['rho_root']);omax=max(outside,key=lambda r:r['rho_root'])
    diagnosis=dict(NEXT_DOMINANT_HYPOTHESIS='FULL-HORIZON GRID CONDITIONAL RELAXATION',implemented=False,
        source='Immutable PR110 ROOT_SLOT_LOADING.csv',source_sha256=sha(PRIOR/'ROOT_SLOT_LOADING.csv'),root_source='S3 certified barrier point, not overall OPTIMAL',
        inside_window_max=imax,outside_window_max=omax,inside_P1_root_dual_mass=sum(r['root_dual_mass'] for r in inside),
        outside_P1_root_dual_mass=sum(r['root_dual_mass'] for r in outside),outside_minus_inside_max_loading=omax['rho_root']-imax['rho_root'],
        W7_effective_coefficients_stronger_than_O1=False,matched_raw_O1_W7_comparison_performed=False,window_boundary_dominance_proved=False,
        rationale='Substantial grid stress lies outside slots 40-46: slot 89 controls the inherited global root and essentially all P1 dual mass lies outside. This satisfies section 40 independently of any raw matched O1/W7 increase.',
        incumbent_quality_investigation='Separate untested future hypothesis',better_full_M1_feasible_UB_found=False,current_UB_proved_poor=False,
        conclusion_scope='Only tested seven-slot G1/G2/G3 epigraph mechanisms are nonmaterial; full-horizon grid coupling remains unresolved')
    dump('RESIDUAL_GAP_DIAGNOSIS.json',diagnosis)
    flags=dict(BASE_PR=110,BASE_HEAD=HEAD,A1_RERUN=False,A1_ANCHOR_REUSED=True,A1_OPTIMIZE_CALLS_THIS_TASK=0,
        S0_OPTIMIZE_CALLS=0,S1_OPTIMIZE_CALLS=0,S2_OPTIMIZE_CALLS=0,S3_OPTIMIZE_CALLS=0,
        SCIENTIFIC_PHYSICS_CHANGED=False,ORIGINAL_INTEGER_PHYSICAL_SET_CHANGED=False,
        WINDOW_START=40,WINDOW_END=46,WINDOW_SIZE=7,FROZEN_CRITICAL_SLOTS=CRITICAL,G3_TIME_PAIRS=TIME_PAIRS,
        W7_ROWS=census['rows'],W7_COLUMNS=census['columns'],W7_NONZEROS=census['nonzeros'],
        W7_ORACLE_CALLS=10,W7_CONDITIONAL_ORACLE_CALLS=4,W7_AUXILIARY_UPPER_WITNESS_CALLS=6,
        W7_ORACLE_TOTAL_SECONDS=resources['total_LP_seconds'],W7_ORACLE_TOTAL_CPU_SECONDS=resources['total_CPU_seconds'],
        W7_POOL_WALL_SECONDS=resources['wall_seconds'],W7_MAX_PROCESS_RSS=resources['max_process_RSS'],W7_PEAK_AGGREGATE_RSS=resources['peak_aggregate_RSS'],W7_WORKERS=2,W7_THREADS=1,
        G1_MAX_ROOT_VIOLATION=selection['G1_MAX_ROOT_VIOLATION'],G1_CUTS_ADDED=0,
        G2_MAX_ROOT_VIOLATION=selection['G2_MAX_ROOT_VIOLATION'],G2_CUTS_ADDED=0,
        G3_MARGINAL_HULL_VIOLATION_COUNT=0,G3_MAX_ROOT_VIOLATION=selection['G3_MAX_ROOT_VIOLATION'],G3_BLOCKS_ADDED=0,
        ROUTE_FLOW_PAIR_PROJECTION_ALREADY_IMPLIED=True,SELECTED_GLOBAL_EPIGRAPH_CANDIDATE='G0',PRODUCTION_BASE='M1-F3',
        F3_LB=F3,S2_REFERENCE_LB=DEFAULT,SELECTED_LB=F3,LB_GAIN_VS_F3=0.,LB_GAIN_VS_S2=F3-DEFAULT,
        IMPLIED_GAP_WITH_EXISTING_UB=(UB-F3)/UB,S2_REFERENCE_IMPLIED_GAP=(UB-DEFAULT)/UB,MATERIAL_ROOT_BOUND_GAIN=False,
        FULL_ROOT_OPTIMIZE_CALLS=0,FULL_ROOT_CANDIDATES_BUILT=[],MIP_CANARY_RUN=False,MIP_CANARY_BEST_BOUND=None,MIP_CANARY_GAP=None,
        PRODUCTION_AUTHORIZED=False,PRODUCTION_RUN=False,M1_P1_INCUMBENT=UB,M1_P1_BOUND=.571849460049452,M1_P1_GAP=.14600227083478132,
        M1_P1_VALUES_SOURCE='Unchanged inherited verified integer UB and inherited MIP bound/gap; no new MIP',M1_P1_QUALITY_PASS=False,
        M1_P2_COMPLETE=False,M1_ACCEPTED=False,RETAINED_INCUMBENT_PHYSICAL_PASS=True,RETAINED_INCUMBENT_ROBUST_VOLTAGE_PASS=True,
        NEW_PRODUCTION_INCUMBENT=False,NEXT_DOMINANT_HYPOTHESIS=diagnosis['NEXT_DOMINANT_HYPOTHESIS'],
        A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,
        ACTUAL_P_CORRECTION_ENABLED=False,ACTUAL_Q_CORRECTION_ENABLED=False,PROBLEM13_FINAL_VALIDATED=False)
    dump('FINAL_FLAGS.json',flags)
    ceiling=read(PRIOR/'CONSTANT_CUT_BOUND_CEILING.json')
    dump('ROOT_BOUND_GAIN_REPORT.json',dict(selected='G0',certified_LB=F3,source='Inherited F3 optimum, no new full root solve',
        delta_LB_vs_F3=0.,delta_LB_vs_S2=F3-DEFAULT,existing_UB=UB,implied_same_UB_gap=(UB-F3)/UB,
        S2_reference_LB=DEFAULT,S2_reference_implied_gap=(UB-DEFAULT)/UB,material=False,material_threshold=.001,
        diagnostic_bands={str(x):F3>=x for x in [.60,.62,.65,UB*.995]},
        counterfactual_uniform_cut_ceiling=DEFAULT,counterfactual_gain_vs_F3=DEFAULT-F3,
        ceiling_source_sha256=sha(PRIOR/'CONSTANT_CUT_BOUND_CEILING.json'),inherited_ceiling_matrix_residual=ceiling['original_F3_point_with_rho_raised_to_default']['matrix_max_violation'],
        proof='All coefficient tables equal default. State/joint mass sums to one. G3 reachable support is already implied by original pure route flow through path decomposition. The inherited F3 optimum with rho raised to default remains matrix-feasible. Thus even every uniform G1/G2/G3 extension could reach only default, gain 0.000363 < 0.001. No candidate was built or solved.'))
    rows=[]
    for label,lb,source in [('G0',F3,'Inherited F3'),('S2_REFERENCE',DEFAULT,'Inherited S2'),('G1',None,'NOT_BUILT: no useful cut'),('G2',None,'NOT_BUILT: no useful block'),('G3',None,'NOT_BUILT: no useful block')]:
        rows.append(dict(candidate=label,status=source,optimize_calls=0,certified_LB=lb,delta_LB_vs_F3=None if lb is None else lb-F3,
            delta_LB_vs_S2=None if lb is None else lb-DEFAULT,implied_same_UB_gap=None if lb is None else (UB-lb)/UB,
            rows=954560 if label=='G0' else None,columns=316743 if label=='G0' else None,nonzeros=8282350 if label=='G0' else None,
            presolved_rows=None,presolved_columns=None,presolved_nonzeros=None,wall_seconds=None,barrier_seconds=None,crossover_seconds=None,peak_RSS=None))
    table('ROOT_LP_COMPARISON.csv',rows)
    table('CUT_MATRIX_COST.csv',[dict(candidate=g,rows_added=0,columns_added=0,nonzeros_added=0,built=False,reason='Inherited reference only' if g=='G0' else 'No useful precheck effect') for g in ['G0','G1','G2','G3']])
    for name in ['MIP_CANARY','M1_PRODUCTION']:
        dump(name+'_OPTIMIZATION.json',dict(run=False,status='NOT_RUN',optimize_calls=0,authorized=False,BestBd=None,gap=None,reason='No useful G1/G2/G3 block and material gate failed',inherited_UB=UB))
        table(name+'_PROGRESS.csv',[],['seconds','incumbent','BestBd','gap','node_count'])
    dump('FINAL_VERDICT.json',dict(status='STOP_NONMATERIAL_WINDOW_EPIGRAPH',selected='G0',M1_ACCEPTED=False,
        full_root_run=False,MIP_canary_run=False,production_run=False,cut_counts=dict(G1=0,G2=0,G3=0),
        complete_stopping_certificate=True,conditional_LP_solves=4,auxiliary_upper_witness_LP_solves=6,
        next_hypothesis=diagnosis['NEXT_DOMINANT_HYPOTHESIS'],next_hypothesis_implemented=False,
        conclusion=diagnosis['conclusion_scope']))
    prose('W7_FORMULATION.md',r'''
# W7 exact seven-slot relaxation

The window was frozen before optimization as original slots 40–46 inclusive. Slot indices and every anchor/correction coefficient retain their original full-day meaning. The full native model keeps all four units and all 96 slots: unit route flow, stay/travel timing and travel energy, connectivity of Pch/Pdis/Q, charge mode, SOC recurrences, initial SOC, terminal SOC equality, efficiencies and original PCS inner16/400-kVA authority. Route/mode integrality alone is relaxed to original continuous bounds. No native physical row is dropped.

`grid.py` copies the original sparse F3 grid construction and adds only the time-membership guard. All retained-slot non-transformer phase-line P1 faces, voltage lower/upper rows (0.955–1.045 pu), transformer current and kVA rows, injection/response bindings and original fixed AIDC anchor/correction terms remain. Grid rows and their auxiliary bindings outside 40–46 are omitted. The census is 260,894 rows, 241,449 continuous columns and 1,771,579 nonzeros. `W7_MODEL.mps.gz` records the exact precondition template; the native-row-axis receipt records anonymous MPS row names and unchanged row order.

Use one `rho_max` with the original normalized non-transformer phase-line faces on the seven retained slots, and minimize it. Original global rho is a maximum across all 96 slots, so rho_global >= rho_window on every original feasible plan. Projection of any original conditional integer plan onto retained W7 columns is feasible: F_original(condition) subset F_W7_LP(condition). Hence the W7 conditional LP optimum is a lower bound for original conditional global P1. Retained hard voltage/transformer constraints have no substitute or relaxed ratings.

All real W7 LPs use Method=2, Threads=1; two outer processes, no parameter search. Four conditional solves are distinguished from six auxiliary upper-witness solves. The latter add generic inactive-unit conditions (all stay at the initial site and zero power), optimize the other two relaxed units, and supply feasible W7 upper points solely for a stopping proof. They do not restrict any production/original formulation, derive from no incumbent neighborhood, and never supply lower coefficients. Their fractional active units and missing outside grid prevent treating them as full-M1 incumbents.

The implemented coefficient is max(inherited certified global S2 default, certified W7 conditional lower bound). Unsolved reachable cells use only default=0.5722125039436496. A complete feasible upper certificate proves every conditional W7 optimum <=0.3441896824355414 (matrix tolerance 1e-5; a margin >0.228 separates this from default). Thus all effective coefficients remain default. Raw W7 optima are not mislabeled as the stronger global default.

Sparse Pi certificates independently revalidate the four lower bounds without optimization. With sign-feasible Pi, L=Pi*b + min_{l<=x<=u}(c-A'Pi)*x is a valid box-Lagrangian lower bound. IEEE rounding allowance is subtracted outward. Finite bounds on original free F3 response auxiliaries follow from their exact equality bindings and bounded physical controls, recorded in `W7_IMPLIED_AUXILIARY_BOUND_PROOF.json`; these derived certificate bounds never change solver domains. See Gurobi's [Pi convention](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#pi).

Twelve bounded fixture families enumerate complete routes and solve integer charge modes, with 70 G1/G2/G3 conditional comparisons against full-grid integer P1 optima. All pass, including actual charging/discharging/Q-only/joint-PQ activity, SOC/terminal SOC, retained voltage, transformer and P1 binding cases. Additional tests verify outside-grid dropping, retained transformer authority, exact grid row census, reachable-pair enumeration and derived auxiliary bounds.

No full G1/G2/G3 root candidate is built: prechecks prove no useful effect. The unchanged F3 reference identity is revalidated at zero optimize calls. All original integer physical plans remain available.
''')
    shared='''
## Complete coefficient classification and stopping proof

For each of six unordered pairs of units, the saved full W7 feasible upper point keeps the pair inactive in the window and achieves rho <=0.3441896824355414. Every one of 600 G1 states and 4,952 G3 reachable pairs has a complete original route path, validated for continuity, crossing-time state, travel energy, all unit physical matrix rows/bounds and initial/terminal SOC. Charging to repay travel energy occurs only outside the window. Window Pch/Pdis/Q stays exactly zero. The `W7_COMPLETE_PATH_LIFT_AUDIT.csv` covers all 5,552 lifts; changes to all retained grid/auxiliary row activities are exactly zero. Combine two independent single-unit lifts with the corresponding inactive-pair point to cover all 11,250 G2 cells. There are no cross-unit native physical rows.

Thus every conditioned W7 LP has a feasible point strictly below default; all effective coefficients are default, including every unsolved priority or other reachable cell. This is a complete upper-certificate stopping proof, not extrapolation from the four conditional solves. All states remain present. Upper objectives are never cut coefficients or full-M1 incumbents. Four sign-feasible dual certificates are independently revalidated; the other LPs are accurately labeled upper witnesses. Tiny marginal transport LPs are separate from the ten real W7 LP calls.
'''
    prose('G1_VALIDITY_PROOF.md','''# G1 validity and separation

For each frozen m,t the crossing-arc state masses y[a] sum to one. An integer original route selects exactly one site or TRANSIT. Each effective beta[a] lower-bounds original conditional global P1, so rho >= sum beta[a]*y[a] preserves every integer feasible plan. At fractional root points this is a strengthening candidate, not an assumed original LP inequality.

All 600 coefficients equal default. The 24 root prechecks have maximum violation -5.145727399735733e-9, below nonviolation tolerance 1e-7 and installation threshold 1e-5. G1 cuts installed: zero. Two conditional G1 LPs were solved; the universal proof covers every other priority/state. W7 retains a strictly richer grid constraint set than O1 at a contained conditioned slot, but no matched raw comparison was made and effective beta did not increase over PR110.
'''+shared)
    prose('G2_VALIDITY_PROOF.md','''# G2 validity and separation

For each unordered pair at frozen slots 41,44,43, nonnegative joint w has row/column sums equal to the two y marginals. At integer y only the selected joint cell can be positive, with mass one. Its beta2 lower-bounds original conditional global P1. Extending an original integer plan with this one cell proves validity without deleting original rows or paths.

All 11,250 beta2 coefficients equal default; every coupling has total mass one. All 18 exact-marginal transportation prechecks pass and return the constant default RHS (maximum root violation -5.145727288713431e-9). No w column, linking row or G2 epigraph cut is installed. One conditional G2 LP was solved. Two independent original unit lifts in each inactive-pair W7 witness certify every remaining cell.
'''+shared)
    prose('G3_VALIDITY_PROOF.md','''# G3 validity, exact support and separate gain sources

Freeze (40,43), (43,46), (40,46), (41,44). For each unit and pair, exact DAG dynamic programming enumerates crossing-arc state pairs occurring on some original initial-to-terminal route. Prefixes extend through original stay arcs; states use the native departure/transit/arrival convention. Counts per unit are 200,205,625,208, totaling 4,952 cells across four units. No root mass or oracle result filters support.

Joint v>=0 has time-one/time-two state marginals, supported on reachable pairs. An original integer route extends with one active cell; gamma lower-bounds that conditional global P1, hence rho>=sum gamma*v preserves it. There is no trajectory master, D-W, CG or branch-and-price.

The pure route network is directed, acyclic, single-commodity unit flow with integral supply; its node-arc incidence is totally unimodular and every feasible flow decomposes into initial-to-terminal paths. Pair states on these paths induce a reachable joint distribution with the exact two time marginals. Therefore pair-support projection is already implied for all pure feasible route flows. This does not assert integrality of joint grid/SOC/PQ relaxation.

All 16 inherited-root marginal feasibility tests pass; marginal-hull violations: zero. All 16 support-restricted transportation prechecks pass. Uniform gamma yields maximum violation -5.1457271776911284e-9. Route-projection gain is zero and epigraph useful violation is false, reported separately. One conditional G3 LP was solved; all remaining pairs are certified by complete reachable route lifts. G3 blocks installed: zero.
'''+shared)
    prose('NEXT_MODIFICATIONS.md',f'''# Next diagnosis only

Favor FULL-HORIZON GRID CONDITIONAL RELAXATION. On the immutable inherited S3 point, window max loading is {imax['rho_root']:.15f} at slot {int(imax['time'])}; outside max is {omax['rho_root']:.15f} at slot {int(omax['time'])}. P1 root dual mass is {diagnosis['inside_P1_root_dual_mass']:.12g} inside versus {diagnosis['outside_P1_root_dual_mass']:.12g} outside. This measured outside stress meets request section 40; no matched raw O1/W7 beta increase or boundary-dominance claim is required.

Current effective W7 coefficients remain default. All tested discrete mechanisms are weak, which also leaves incumbent-quality investigation as a future hypothesis. No better feasible full-M1 solution has been found, and current UB is not proved poor. No feasibility pump, local branching, heuristic change, route restriction or neighborhood search occurred. The W7 fractional upper witnesses are solely oracle stopping evidence.

Neither next investigation is implemented. This result concerns the fixed seven-slot experiment only and does not eliminate full 96-slot grid coupling. Stop before full root candidates, canary, production, P2 and A2/M2/Actual/Fresh AC/IEEE8500. Scientific physics and Actual P/Q OFF remain frozen.
''')
    prose('README.md',f'''# Seven-slot M1 global epigraph experiment

Exact base: Draft PR110, {HEAD}. Selection: G0, unchanged sparse M1-F3. G1 cuts=0, G2 cuts=0, G3 blocks=0. Selected inherited LP LB={F3:.16f}, gain vs F3=0, gain vs S2={F3-DEFAULT:.16f}; same-UB implied gap={(UB-F3)/UB*100:.8f}%. No new full root LP/MIP, production or downstream run. M1 accepted=false.

W7 retains all native four-unit/96-slot physics and every original grid requirement on preregistered slots 40–46, including robust voltage and transformer rows. It has 260,894 rows / 241,449 continuous columns / 1,771,579 nonzeros. Four conditional LPs and six upper-witness LPs use two workers, Method=2 and Threads=1. Sum LP wall={resources['total_LP_seconds']:.3f}s, CPU={resources['total_CPU_seconds']:.3f}s, pool wall={resources['wall_seconds']:.3f}s; peak aggregate RSS={resources['peak_aggregate_RSS']} bytes. Raw logs, full upper points, sparse dual certificates, exact MPS and derived-bound proofs are included.

Complete 5,552 native route/energy/SOC lifts plus six independently matrix-validated inactive-pair W7 upper points prove every 600 G1, 11,250 G2 and 4,952 G3 conditional optimum lies below default. All coefficient tables therefore equal inherited S2 global LB. All 24 G1, 18 G2 and 16 G3 prechecks show no useful violation. Sixteen cross-time root marginal tests pass. Pure route-flow path decomposition already implies reachable-pair marginal support. Even all uninstalled uniform cuts have only counterfactual ceiling {DEFAULT:.16f}, gain {DEFAULT-F3:.16f}<0.001. These upper witnesses are fractional W7 points, never full-M1 incumbents or lower coefficients.

537 tests and 70 bounded full-integer conditional comparisons pass. Saved S3 remains overall INTERRUPTED with optimal barrier certificate; its full-matrix point is revalidated without optimization. The inherited verified integer plan passes independent native physical and robust-grid validation. Original tracked bytes, default F3 fingerprint, A1 anchor and all scientific physics remain unchanged.

The next diagnosis favors FULL-HORIZON GRID CONDITIONAL RELAXATION because inherited binding slot 89 and essentially all P1 dual mass lie outside the seven-slot window. No next investigation is implemented; current UB is not shown poor. Read FINAL_REVIEW_KO.md for all 50 answers; VERIFICATION.json and SOURCE_MANIFEST.json seal the evidence.

Reproduction order (costly steps are one-shot): common setup/identity, validation, oracle template, reachability, experiment, universal, precheck, pytest, verify duals/incumbent, report, verify verify. `W7_WORKERS_STARTED.json` guards the real-LP batch against reruns. Read saved certificates for verification instead of reoptimizing immutable A1/S2/S3 or full candidates. Input SHA receipts identify the inherited private runtime caches; those caches are not bundled. The exact saved W7 matrix and upper/dual/path evidence support standalone matrix checks.
''')
    request=Path('C:/Users/kjw39/.codex/attachments/72081e5d-4301-4534-b4da-aa27f14149f2/붙여넣은 텍스트.txt').read_text(encoding='utf8')
    section=request.split('50. FINAL_REVIEW_KO — 50 QUESTIONS')[1].split('51. EXECUTION ORDER')[0]
    questions=re.findall(r'^\d+\. (.+)$',section,re.M);assert len(questions)==50
    answers=[
        '같은 UB에서 약 14.55%인 LP gap의 지배 원인이 full-grid/PQ/discrete coupling인지 아직 밝혀지지 않았다. PR110 single-slot 결과만으로 full-grid coupling을 배제할 수 없었다.',
        f'{UB:.16f}. 기존 검증된 integer UB를 재사용했으며 새 full-M1 UB는 없다.',f'{F3:.16f}.',f'{DEFAULT:.16f}.',
        f'S2 reference 기준 {(UB-DEFAULT)/UB*100:.8f}%; 선택된 G0/F3 기준 {(UB-F3)/UB*100:.8f}%. 기존 MIP gap과 LP implied gap은 구분한다.',
        f'동일 UB의 99.5%인 {UB*.995:.16f}.',
        'O1은 다른 시간의 grid 요구와 retained-slot voltage/transformer를 제거했다. 조건부 oracle upper가 global default보다 낮아 유효 계수가 default를 넘지 못했다.',
        '원래 시간 인덱스의 40–46 inclusive, 정확히 7개다.',
        '기존 frozen critical [41,44,43,40,42,46]의 min/max다. incumbent-root loading 차이는 선택 score이며 true local optimality gap이 아니다.',
        '연속 window를 만들기 위해서만 포함했다. 결과에 따른 재선택은 없다.',
        '4개 unit/96-slot route flow, stay/travel 시간·energy, Pch/Pdis/Q 연결, charge mode, PCS16, SOC recurrence·초기·terminal equality·효율을 모두 유지했다.',
        '40–46의 원래 non-transformer P1 faces, robust 0.955–1.045 voltage, transformer current/kVA, injection/response bindings 및 고정 AIDC/correction 항을 유지했다.',
        '40–46 밖의 grid requirements와 해당 auxiliary bindings를 제거한다. native full-horizon MESS 행은 제거하지 않는다.',
        '원 conditional integer plan의 투영은 W7 LP feasible이고 rho_global>=rho_window다. feasible set 확대와 integrality relaxation으로 conditional minimum은 valid lower bound다.',
        '7-slot non-transformer normalized phase-line maximum rho_W7의 최소화다. P1/P2는 바꾸지 않았다.',
        '각 unit/frozen time/state를 조건으로 하는 W7 lower bound 기반 single-state epigraph다.',
        '효과적인 계수는 전부 default=0.5722125039436496으로 PR110보다 증가하지 않았다. raw W7 조건부 LP 두 개는 약 0.299390/0.270355; matched raw O1 비교는 수행하지 않았다. 모든 나머지 조건도 upper certificate로 default 이하임을 증명했다.',
        '-5.145727399735733e-9 (24개 precheck).','0개.',
        '41/44/43에서 두 unit의 동시 state에 조건부 W7 beta2와 joint mass w를 사용하는 formulation이다.',
        '두 unit이 같은 7-slot grid 요구를 동시에 부담할 때의 conditional coupling을 본다.',
        '18개 transport LP 모두 feasible, 모든 beta2가 default여서 RHS도 default다. 최대 violation -5.145727288713431e-9; useful violation 없다.',
        '0개; w/linking columns·rows도 설치하지 않았다.',
        '동일 unit의 두 시간 state pair와 원래 reachable support를 연결하는 joint v epigraph다.',
        '(40,43), (43,46), (40,46), (41,44).',
        'start-middle, middle-end, window endpoints, 상위 interior critical pair를 사전에 정해 temporal interaction을 검증했다. 결과 후 변경하지 않았다.',
        '원 time-expanded DAG의 initial-to-terminal route에 두 crossing-time state가 동시에 나타나는 경우다. exact DP로 unit당 200/205/625/208, 총 4,952개를 확인했다.',
        '두 시간의 state marginal을 연결하는 nonnegative joint mass다. reachable pair에만 support를 두며 integer route는 하나의 cell을 선택한다.',
        '예. 16개 exact-marginal feasibility LP 모두 PASS; hull violation 0개다.',
        '순수 unit single-commodity DAG flow는 incidence TU 및 path decomposition으로 integral하다. SOC/PQ/grid를 결합한 relaxation 전체가 integral하다는 뜻은 아니다.',
        'route-support projection은 이미 implied라 추가 gain 0이다. conditional grid epigraph도 모두 default라 useful violation이 없다. 두 원인을 별도로 보고했다.',
        '-5.1457271776911284e-9 (16개 supported transport precheck).','0개.',
        '동일하다. 원 scientific physics/domain/rows는 유지되고 추가 production cut도 0개다. retained incumbent의 독립 physical/robust voltage 검증도 PASS다.',
        '사용하지 않았다. 저장된 경로는 reachability/증명의 witness이며 trajectory master columns가 아니다.',
        '새 G1/G2/G3 full root는 미구축이다. inherited F3는 954,560 rows /316,743 columns /8,282,350 nonzeros. 별도 W7 oracle은 260,894 /241,449 /1,771,579다.',
        f'새 full root solve는 없고 선택된 G0의 inherited certified LB={F3:.16f}다.',
        '0. 모든 uniform cut을 가정해도 ceiling gain은 +0.0003630437418684629로 material threshold 미달이다.',
        '-0.0003630437418684629. S2를 production base로 carry하지 않은 reference 비교이며 새 solver 결과의 하락이 아니다.',
        '통과하지 않았다. root 후보/600초 canary 이전에 STOP했다.','아니오.','아니오.','아니오.',
        '실행하지 않았다. real W7 LP 10회는 conditional 4회+upper witness 6회이며 canary가 아니다.',
        'NOT_RUN/null. 기존 MIP bound 0.571849460049452/gap 14.60022708%는 inherited 값으로만 남긴다.',
        '실행하지 않았다. production authorization=false; P2도 NOT_RUN이다.',
        'false. P1 0.5% quality와 P2 quality가 충족되지 않았다. 기존 plan의 physical PASS만으로 acceptance를 선언하지 않는다.',
        f'우선 진단 후보다. window root max {imax["rho_root"]:.9f}(slot {int(imax["time"])})보다 밖의 {omax["rho_root"]:.9f}(slot {int(omax["time"])})가 높고 P1 dual mass가 거의 전부 밖에 있다. §40의 outside stress 증거에 따른 선택이며 구현하지 않았다.',
        '별도 미검증 미래 가설이다. tested discrete convexification은 약했지만 outside grid stress가 현재 우선 진단을 지지한다. 더 좋은 full-M1 feasible UB를 찾지 않았으므로 현 UB가 나쁘다고 단정하지 않는다.',
        'M1 P1/P2 quality 및 acceptance gate가 실패했기 때문이다. A2/M2/Actual/Fresh AC/IEEE8500 미실행, Actual P/Q OFF, PROBLEM13_FINAL_VALIDATED=false를 유지한다.'
    ];assert len(answers)==50
    prose('FINAL_REVIEW_KO.md','# 최종 검토 — 50개 질문\n\n'+'\n\n'.join(f'{i}. **{q}**\n\n   {a}' for i,(q,a) in enumerate(zip(questions,answers),1)))
    if not (OUT/'W7_MODEL.mps.gz').exists():
        with (LOCAL/'W7.mps').open('rb') as source,(OUT/'W7_MODEL.mps.gz').open('wb') as target:
            with gzip.GzipFile(fileobj=target,mode='wb',mtime=0) as compressed:shutil.copyfileobj(source,compressed)
    sources=[p for folder in [ROOT/'v42_window',ROOT/'tests/v42_window'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    dump('SOURCE_MANIFEST.json',dict(base_head=HEAD,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(sources)],
        exact_W7_mps_sha256=sha(LOCAL/'W7.mps'),frozen_before_real_optimization=True,inherited_sources_sealed_by='PR110_BASE_RECEIPT.json and LEGACY_PRESERVATION_AUDIT.json'))
    print('REPORT COMPLETE',len(REQUIRED),flush=True)

if __name__=='__main__':run()
