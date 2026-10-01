"""Write bounded-experiment receipts without inventing unrun candidate results."""
import gzip,re,xml.etree.ElementTree as ET
from .common import *

REQUIRED='README.md PREREGISTRATION.json PR109_BASE_RECEIPT.json ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json A1_ANCHOR_REUSE_RECEIPT.json ROOT_STATE_MASS_AUDIT.csv ROOT_SPATIAL_PQ_AUDIT.csv ROOT_SPATIAL_PQ_SUMMARY.json ROOT_SLOT_LOADING.csv ROOT_INCUMBENT_SLOT_GAP.csv CRITICAL_SLOT_FREEZE.json O1_FORMULATION.md O1_VALIDATION.csv O1_ORACLE_STATS.csv E1_BETA_TABLE.csv E1_ROOT_VIOLATIONS.csv E1_VALIDITY_PROOF.md E2_BETA_TABLE.csv E2_TRANSPORT_PRECHECK.csv E2_VALIDITY_PROOF.md EPIGRAPH_CUT_SELECTION.json CUT_MATRIX_COST.csv ROOT_LP_COMPARISON.csv ROOT_BOUND_GAIN_REPORT.json MIP_CANARY_OPTIMIZATION.json MIP_CANARY_PROGRESS.csv M1_PRODUCTION_OPTIMIZATION.json M1_PRODUCTION_PROGRESS.csv M1_PHYSICAL_VALIDATION.json M1_ROBUST_VOLTAGE_REPORT.json RESIDUAL_GAP_DIAGNOSIS.json NEXT_MODIFICATIONS.md FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json'.split()

def prose(n,s):(OUT/n).write_text(s.strip()+'\n',encoding='utf8')

def run():
    select=read(OUT/'EPIGRAPH_CUT_SELECTION.json');assert select['E1_CUTS_ADDED']==select['E2_CUTS_ADDED']==0
    source=read(OUT/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json');spatial=read(OUT/'ROOT_SPATIAL_PQ_SUMMARY.json');freeze=read(OUT/'CRITICAL_SLOT_FREEZE.json');stop=read(OUT/'O1_UNIVERSAL_STOP_CERTIFICATE.json')
    old=read(PRIOR/'FINAL_FLAGS.json');resources=read(OUT/'O1_WORKER_RESOURCE_RECEIPT.json');oracle=csvread('O1_ORACLE_STATS.csv')
    physical=read(OUT/'M1_PHYSICAL_VALIDATION.json');robust=read(OUT/'M1_ROBUST_VOLTAGE_REPORT.json')
    reason='No root-violated useful E1/E2 cut exists; full candidate LP not authorized, material-gain gate fails.'
    for prefix in ['MIP_CANARY','M1_PRODUCTION']:
        dump(prefix+'_OPTIMIZATION.json',dict(run=False,optimize_calls=0,reason=reason,passes=[]))
        table(prefix+'_PROGRESS.csv',[],['seconds','incumbent','bound','gap','nodes','status'])
    table('CUT_MATRIX_COST.csv',[dict(candidate=c,new_rows=0,new_columns=0,new_nonzeros=0,built=c=='E0',reason='Inherited F3 reference' if c=='E0' else 'No useful cut; not built') for c in ['E0','E1','E2']])
    table('ROOT_LP_COMPARISON.csv',[
        dict(candidate='E0_F3',run=False,source='PR109 immutable BASE_ROOT_LP_OPTIMIZATION',LB=F3,rows=954560,columns=316743,nonzeros=8282350,LP_seconds_this_task=0,LP_seconds_inherited=203.37864760000957,peak_RSS_bytes_inherited=2340495360),
        dict(candidate='PR109_S2_REFERENCE',run=False,source='PR109 immutable S2_ROOT_LP_OPTIMIZATION',LB=DEFAULT,rows=1795492,columns=524671,nonzeros=10614268,LP_seconds_this_task=0,LP_seconds_inherited=2076.009980300005,peak_RSS_bytes_inherited=3385982976),
        *[dict(candidate=c,run=False,source='Not built: no useful frozen-root violation',LB=None,rows=None,columns=None,nonzeros=None,LP_seconds_this_task=0,LP_seconds_inherited=None,peak_RSS_bytes_inherited=None) for c in ['E1','E2']]])
    gap=(UB-F3)/UB
    gain=dict(selected='E0',PRODUCTION_BASE='M1-F3',selected_LB=F3,source='Inherited F3 OPTIMAL result; no new root solve',LB_gain_vs_F3=0.,LB_gain_vs_S2=F3-DEFAULT,
        existing_UB=UB,implied_gap=gap,material_threshold=.001,material=False,bands={str(z):F3>=z for z in [.60,.62,.65,UB*.995]},
        epigraph_bound_improvement=0.,uninstalled_uniform_cut_LB_ceiling=DEFAULT,uninstalled_uniform_cut_gain_ceiling=DEFAULT-F3,
        ceiling_certificate='CONSTANT_CUT_BOUND_CEILING.json',S2_reference_retained_immutable=True,negative_vs_S2_is_sparse_base_choice_not_new_solve_regression=True)
    dump('ROOT_BOUND_GAIN_REPORT.json',gain)
    flags=dict(BASE_PR=109,BASE_HEAD=HEAD,A1_RERUN=False,A1_ANCHOR_REUSED=True,A1_OPTIMIZE_CALLS=0,SCIENTIFIC_PHYSICS_CHANGED=False,INTEGER_PHYSICAL_SET_CHANGED=False,
        ORIGINAL_INTEGER_PHYSICAL_SET_CHANGED=False,DIAGNOSTIC_ROOT_SOURCE=source['selected'],S3_CERTIFICATE_USED=source['S3_CERTIFICATE_USED'],
        ROOT_MAX_SIMULTANEOUS_SITES=spatial['max_simultaneous_sites'],ROOT_MULTI_SITE_SLOT_FRACTION=spatial['multi_site_slot_fraction'],ROOT_DISTRIBUTED_Q_SLOT_FRACTION=spatial['distributed_Q_slot_fraction'],
        CRITICAL_SLOT_COUNT=6,CRITICAL_SLOTS=freeze['slots'],E2_SLOTS=freeze['E2_slots'],
        E1_ORACLES_SOLVED=select['E1_oracles_solved'],E1_MAX_ROOT_VIOLATION=select['E1_max_root_violation'],E1_CUTS_ADDED=0,
        E2_ORACLES_SOLVED=0,E2_MAX_ROOT_VIOLATION=select['E2_max_root_violation'],E2_CUTS_ADDED=0,E2_TRANSPORT_PRECHECKS=18,
        REACHABLE_SINGLE_STATES=600,REACHABLE_PAIR_STATES=11250,UNIVERSAL_O1_STOP_CERTIFICATE_PASS=True,
        PRIORITY_STATES_EARLY_STOPPED=True,PRIORITY_STOP_REASON=select['priority_stop_reason'],SELECTED_EPIGRAPH_CANDIDATE='E0',PRODUCTION_BASE='M1-F3',
        BASE_F3_LB=F3,PR109_S2_LB=DEFAULT,SELECTED_LB=F3,LB_GAIN_VS_F3=0.,LB_GAIN_VS_S2=F3-DEFAULT,IMPLIED_GAP_WITH_EXISTING_UB=gap,
        UNINSTALLED_UNIFORM_CUT_LB_CEILING=DEFAULT,UNINSTALLED_UNIFORM_CUT_GAIN_CEILING=DEFAULT-F3,
        MATERIAL_ROOT_BOUND_GAIN=False,MIP_CANARY_RUN=False,MIP_CANARY_BEST_BOUND=None,MIP_CANARY_GAP=None,PRODUCTION_AUTHORIZED=False,PRODUCTION_RUN=False,
        M1_P1_INCUMBENT=UB,M1_P1_BOUND=old['M1_P1_BOUND'],M1_P1_GAP=old['M1_P1_GAP'],M1_P1_QUALITY_PASS=False,M1_P2_COMPLETE=False,M1_MOVEMENT_ENERGY=None,M1_MOVEMENT_COUNT=None,M1_ACCEPTED=False,
        RETAINED_INCUMBENT_PHYSICAL_PASS=physical['retained_incumbent_PASS'],RETAINED_INCUMBENT_ROBUST_PASS=robust['retained_incumbent_PASS'],
        NODE83P2_SLOT79_VOLTAGE=robust['validation']['node83p2_slot79_voltage_pu'],NODE83P2_USED_FOR_CUT_TUNING=False,
        NEW_FEASIBLE_UB_FOUND=None,UB_SOURCE='PR109 retained verified integer incumbent; no new MIP incumbent',
        ACTUAL_Q_CORRECTION_ENABLED=False,ACTUAL_P_CORRECTION_ENABLED=False,A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,PROBLEM13_FINAL_VALIDATED=False,
        ROOT_LP_OPTIMIZE_CALLS=dict(E0=0,E1=0,E2=0,S0=0,S1=0,S2=0,S3=0),ORACLE_WORKERS=2,O1_LP_SECONDS=sum(float(r['seconds']) for r in oracle),
        INITIAL_CONSTANT_LOADING_PROBE_SOLVES=6,TRANSPORT_LP_CALLS_INCLUDING_CANONICAL_TRANSIT_RECHECK=36)
    dump('FINAL_FLAGS.json',flags)
    diagnosis=dict(tested_result='Single-slot O1-based spatial/Q epigraph strengthening has no useful violated cut and no material new bound gain.',
        mechanism_scope='This does not disprove spatial averaging in the full model: O1 drops all other-time grid requirements and retained-slot voltage/transformer rows, so its coefficients can be too weak.',
        exact_failure='Every conditional O1 admits a zero-P/Q selected-slot witness below global default, including all pairs. Thus every proposed beta is exactly the inherited global bound.',
        next_candidate='MULTI-TIME / GLOBAL DISCRETE EPIGRAPH COUPLING',LB_weakness_remains=True,LB_dominance_over_incumbent_quality_not_proved=True,
        incumbent_quality='Possible, untested: no incumbent search and no new feasible UB. Existing UB alone does not establish distance to integer optimum.',
        next_computational_question='Develop and preregister a conditional relaxation that retains several critical slots or the full grid horizon; establish validity and re-use frozen states. Do not implement it here.',
        production_oracle_does_not_replace_compact_MILP=True,NO_DW_CG=True,NO_HEURISTIC_CUT=True)
    dump('RESIDUAL_GAP_DIAGNOSIS.json',diagnosis)
    dump('FINAL_VERDICT.json',dict(STOP=True,reason=reason,result=diagnosis['tested_result'],scientific_limitation=diagnosis['mechanism_scope'],next=diagnosis['next_candidate'],M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    prose('NEXT_MODIFICATIONS.md','''# Next exact computational question

The tested single-slot O1 cuts cannot improve beta beyond the inherited global LP lower bound. This follows from complete feasible-witness certificates, not from sampling a few favorable sites. The tested cuts do not materially explain the residual bound gap.

Next candidate: **MULTI-TIME / GLOBAL DISCRETE EPIGRAPH COUPLING**. Preregister a conditional relaxation retaining multiple critical-slot grid requirements, or the full grid horizon, then certify its conditional lower bounds. Full conditional spatial effects remain unresolved because the current O1 discards precisely the grid obligations that can make its zero-P/Q witnesses impossible in full M1.

Incumbent quality remains a possible separate issue, with no new evidence that it dominates. No heuristic search, new family, multi-time oracle, route restriction, Dantzig-Wolfe, column generation, production solve or downstream stage is implemented here.
''')
    prose('O1_FORMULATION.md','''# Conditional O1 relaxation

Each oracle starts with the exact native full-horizon MESS constructor: all four units; the full deduplicated original route authority and exact forward reachability; stay/travel flow and timing; departure travel energy; per-site Pch/Pdis/Q connectivity; original mode rows; individual 400-kVA PCS inner16; original pooled SOC equations; initial and terminal equality and efficiency. No S1/S2/S3 extension is inherited into O1. All binary route/mode columns are relaxed to their original [0,1] bounds.

Only the original non-transformer 16-face P1 line inequalities at the preregistered slot remain at grid level. Their original affine correction, anchor, bias and line ratings are unchanged; F3 auxiliary bindings are eliminated exactly into the native expressions. Fixed AIDC controls remain the inherited anchor. All other-time line rows, and all grid voltage and transformer rows (including at the retained time), are dropped. Every original integer solution projects into this relaxed model. min rho_t <= that solution's max-over-time rho, making a conditional O1 lower bound valid for original full M1.

Connected state y[u,s,t] is the original stay arc at (s,t). TRANSIT is 1-sum_s y, equivalently the sum of travel arcs crossing depart <= t < connect. Departure is transit; connection is a connected stay or a new departing trip. The equivalence follows by summing time-expanded flow on the cut between times t and t+1. Raw mass residuals are audited without clipping. Reachable states are obtained from the original route authority, never from positive root support. Conditioning enforces y=1 with an equality. One or two selected unit states are conditioned; all other decisions remain relaxed. A full original integer point has exactly one physical state for each unit/slot.

LP policy: Method=2, Threads=1, all other parameters default. Two independent workers are measured; no parameter grid, MIP solve or GPU is used. Persistent models may reuse Gurobi's ordinary warm-start state. Each successful optimum also has a finite-box Lagrangian lower certificate: for sign-feasible row multipliers pi, L=pi*b+sum_j min((c-A'pi)_j*lb_j,(c-A'pi)_j*ub_j). Every column has finite original bounds. Projecting dual signs and including reduced-cost bound terms absorbs stationarity error. An outward IEEE roundoff bound is subtracted; the saved sparse Pi is independently rechecked without optimizing. This uses lower bounds, never feasible objective values, as beta.

The inherited certified global bound 0.5722125039436496 is independently valid for every conditional original integer optimum. Computed beta=max(global default, certified O1 lower bound) is therefore valid and at least as strong as either alone. Uncomputed states use only the exact global default.

Exact stopping certificate: independently validate a full-horizon integer route/SOC/PCS witness for all 600 reachable single states. Every witness has Pch=Pdis=Q=0 at the selected slot, and replenishes travel energy during connected times elsewhere. All 600 points are also checked against the actual full O1 matrix. Their retained-slot objectives lie in 0.3730791667–0.4432689579, below the global default. Pair witnesses combine two disjoint unit witnesses; all selected-slot injections stay zero, so the original retained grid rows are the same. This covers all 11250 reachable pairs. Consequently even the exact optimum of every remaining O1 oracle is below the default: no additional solve, including root-positive priority states, can change any coefficient. The priority queue is stopped on this universal certificate; no state is deleted. E2 conditional LPs are not launched; all 18 pair/slot transportation LPs are evaluated using the valid defaults. This is a stronger sufficient proof for the requested no-possible-violation stopping logic. Counts explicitly distinguish optimized states from witness-certified uncomputed states.

These feasible upper witnesses justify only stopping. Their objectives are never used as cut lower coefficients. They need not satisfy discarded voltage or other-time grid rows and are not new feasible full-M1 incumbents. A weak O1 oracle cannot disprove stronger full-grid conditional epigraph coupling.

References: [Gurobi Pi signs and dual convention](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#pi). The box-Lagrangian formula and witness construction above provide the conditional-bound proof.
''')
    prose('E1_VALIDITY_PROOF.md','''# E1 integer physical validity

For every original integer plan, the full time-expanded route path crosses each time cut once. Thus the connected-site stay indicators and transit indicator form exactly one state a*. With a certified full-objective conditional lower bound beta[a] for each reachable state, sum_a beta[a]*y[a]=beta[a*] <= conditional integer optimum <= that plan's original rho. Therefore rho >= sum_a beta[a]*y[a] removes no original physical integer solution. Original P1/P2, all physical/grid constraints and objective order remain unchanged. Conditional O1 is valid by projection and removal of constraints; the inherited S2 global bound is valid on the original physical integer projection by PR109's constructive certificate.

No E1 row is installed: all beta equal the global default and none violates the preregistered certified S3 point by 1e-5. Unreachable states arise only from exact route authority; all reachable states remain represented. No empirical coefficient or witness upper objective is used as a lower bound.
''')
    prose('E2_VALIDITY_PROOF.md','''# E2 integer physical validity

For a pair of units at one frozen time, nonnegative continuous w[a,b] has marginals sum_b w[a,b]=y_m[a] and sum_a w[a,b]=y_n[b]. At integer states a*,b*, these equalities force the unique cell w[a*,b*]=1 and every other cell zero. The inequality rho >= sum beta2[a,b]*w[a,b] becomes rho >= beta2[a*,b*], valid by the conditional full-objective lower-bound definition. Every original integer physical point extends into this unique w; projecting w recovers the original physical set. No new binary, physical constraint, scientific objective or policy is required.

For a fractional frozen root, the tiny transportation LP computes the minimum possible epigraph RHS over all such extensions. If this value is at most rho, some extension preserves the root and the proposed pair cannot cut it. Every one of the six unordered pairs is evaluated at each of the first three frozen slots. Raw canonical state marginals are used with the inherited numerical tolerance and their solver residuals are reported; no mass clipping or silent normalization is performed.

No E2 row or w column is installed. All 11250 beta2 coefficients use only the inherited global certified lower bound. Universal full-O1 feasible witnesses prove no uncomputed conditional LP can increase these coefficients. E2 conditional LP solve count is zero; transportation precheck count is 18 (36 actual calls including a documented canonical-transit recheck). This exact early stopping does not claim that all conditional LPs were solved.
''')
    prose('README.md',f'''# Frozen M1 spatial epigraph experiment

Successor of Draft PR #109 exact head `{HEAD}`. P1 remains MAX_LINE_LOADING; P2 remains movement energy -> movement count. E0/E1/E2 are internal formulation labels. Production base remains M1-F3; no production formulation, physical constraint, old source or evidence byte is changed.

Certified S3 BarX is reused after full-matrix revalidation (maximum residual {source['full_matrix_revalidation']['matrix_max_violation']:.12g}); its interrupted overall solver status is not relabeled. A1 optimize calls=0. State-mass audit maximum residual {spatial['max_mass_residual']:.12g}. The saved interior optimum has at most 24 positive sites and 98.1771% multi-site/distributed-Q unit-slots. These are point-specific diagnostics, not causal gap estimates. Critical slots are {freeze['slots']}; E2 is restricted to {freeze['E2_slots']}.

Fifteen O1 conditional LPs were optimized with Method=2/Threads=1; their certified lower bounds are below the inherited global default. Four bounded fixtures and 74 conditional checks pass. The exact universal stopping certificate validates all 600 reachable single-state full-horizon witnesses, and proves pair validity for all 11250 reachable state pairs. Their selected-slot P/Q are zero; retained-slot loading is 0.3730791667–0.4432689579. Therefore no further conditional O1 solve can raise any beta. Remaining priority states are stopped by proof, with default coefficients; they are not described as solved. E2 conditional LPs=0; all 18 transportation prechecks were solved. All 600 E1 and 11250 E2 coefficients are exactly the inherited certified global bound. See [O1 formulation and stopping scope](O1_FORMULATION.md) and [universal certificate](O1_UNIVERSAL_STOP_CERTIFICATE.json).

E1 maximum root violation={select['E1_max_root_violation']:.12g}; E2={select['E2_max_root_violation']:.12g}. Useful cuts=0. Full E1/E2 root candidates are not built or solved. E0 references the immutable F3 LP bound {F3}, with gain 0 and implied same-UB gap {gap:.8%}; PR109 S2 remains {DEFAULT} and 14.546010% for comparison. No new MIP bound is claimed. The .001 material gate fails, so no canary or production run, no P2, no A2/M2/Actual/Fresh AC/IEEE8500. M1_ACCEPTED=false; PROBLEM13_FINAL_VALIDATED=false.

Even if all uniform-beta cuts were installed, their LP bound could only equal the default: every E1/E2 state mass sums to one, and raising rho in the immutable F3 root point to default passes the full original matrix with residual 7.8648e-12. This zero-optimize [counterfactual ceiling certificate](CONSTANT_CUT_BOUND_CEILING.json) establishes an exact uniform-cut gain of only 0.0003630437, still below .001. No candidate or cut is built for this calculation.

The tested single-slot O1 spatial/Q epigraph cuts do not materially explain the remaining gap. **This does not rule out full-grid spatial coupling:** O1 drops all other-time grid requirements and selected-slot voltage/transformer rows. Next candidate is MULTI-TIME / GLOBAL DISCRETE EPIGRAPH COUPLING, not implemented. Incumbent quality remains untested, and no new feasible UB is found.

Two-worker measured peak aggregate RSS={resources['peak_total_worker_RSS_bytes']} bytes; minimum system available={resources['minimum_system_available_bytes']} bytes. Probe LPs before the pool are included in the 15 total; cached receipts are not counted twice. Six preliminary constant-only one-variable loading calculations used Gurobi defaults (not O1/M1 optimizations); the universal certificate subsequently derives the same constants without optimization. Two initial MPS gzip-write attempts failed before any optimize call because the Windows Gurobi writer does not write .mps.gz here; Python compression preserves the successful raw MPS. All successful O1 LP logs and sparse dual certificates are retained. Each of 18 transport LPs was rechecked once after explicitly choosing the algebraically equivalent TRANSIT=1-sum-site expression; no slots or physical values were reselected or clipped.

Reproduce on the same immutable external inputs: `python -m v42_epigraph.common`; `python -m v42_epigraph.audit select`; `python -m v42_epigraph.audit audit`; `python -m v42_epigraph.oracle templates`; `python -m v42_epigraph.validation`. Launch `python -m v42_epigraph.experiment run` and `python -m v42_epigraph.universal` independently, then `python -m v42_epigraph.audit canonical_state_axis`, `python -m v42_epigraph.experiment prechecks`, and the zero-optimize verification phases. Setup and slot-freeze guards forbid accidental repeat registration. Native user-requested production gates are not entered because no useful cut is found.
''')
    request=Path('C:/Users/kjw39/.codex/attachments/5c732742-7be6-4a16-9d0a-d56b66ef4897/붙여넣은 텍스트.txt').read_text(encoding='utf8')
    section=request.split('47. FINAL_REVIEW_KO')[1].split('48. EXECUTION ORDER')[0]
    questions=re.findall(r'^\d+\. (.+)$',section,re.M);questions=[q.strip() for q in questions];assert len(questions)==50
    answers=[
      'mode/route-energy strengthening 이후에도 동일 UB 대비 S2 implied gap은 14.546010%다. 남은 공간·시간 coupling과 incumbent quality의 기여는 아직 분리되지 않았다.',
      f'{UB:.16f}; 기존 검증 정수 incumbent이며 새 feasible UB는 찾지 않았다.',f'{F3:.16f}; immutable PR109 F3 OPTIMAL artifact를 재사용했다.',f'{DEFAULT:.16f}.',f'UB×0.995 = {UB*.995:.12f}.',
      'S3의 저장된 optimal barrier interior point다. production formulation 선택이 아니다.',f"BarStatus=2, optimum interval 폭 5.1457×10⁻⁹≤10⁻⁷, 전체 행렬 재검증 최대 잔차 {source['full_matrix_revalidation']['matrix_max_violation']:.12g}≤10⁻⁵를 통과했다. overall status=11은 그대로 유지한다.",
      'epsilon=10⁻⁶ 기준 최대 24개다. 저장된 최적점에 대한 수치이며 optimal face 전체의 인과적 측정은 아니다.','384 unit-slot 중 98.1770833%다.','|Q|>10⁻⁶인 site가 둘 이상인 unit-slot은 98.1770833%다.',
      '원래 non-transformer line/phase의 16개 P1 face를 동일 rating, affine correction, anchor와 bias로 평가하고 각 슬롯의 최댓값을 취했다. Transformer loading은 P1 rho 분해에서 제외한다.',
      f"rho_inc[t]-rho_root[t] 내림차순, 동률은 낮은 index 순으로 {freeze['slots']}를 고정했다. 이는 local optimality gap이 아닌 선택 score다. dual/Q/voltage는 보고만 했다.",
      '한 MESS의 site 또는 TRANSIT 상태에 따른 certified rho 하한을 상태 indicator와 결합하는 single-unit disjunctive epigraph 부등식이다.','E1은 내부 formulation label이다. 과학적 목적은 P1 MAX_LINE_LOADING, P2 MIN_INTERVENTION 그대로이며 P3를 만들지 않는다.',
      '원래 full M1의 해당 상태 conditional integer objective에 대한 certified lower bound다. 이번 모든 beta는 상속 global bound 0.5722125039436496다.','조건부 integer optimum 이하인 하한이면 해당 상태의 모든 원래 integer plan에 유효하다. exact optimum을 알 필요가 없다.',
      '모든 4개 MESS의 full-horizon route flow/timing/travel energy, Pch/Pdis/Q connectivity, mode, PCS16, SOC, 초기·terminal SOC·효율과 고정 AIDC anchor를 유지한다.',
      '선택 slot의 non-transformer P1 line face만 남기고, 모든 other-time line 및 모든 voltage/transformer grid rows를 제거했다. 원래 모델에 없던 제약은 추가하지 않았다.',
      '원래 conditional integer plan은 이 relaxation에 투영되며 slot loading은 원래 max-over-time rho 이하이므로 O1 LP 하한도 원래 conditional objective의 하한이다.',
      'TRANSIT=1−sum site stay mass이며 depart≤t<connect인 crossing travel arc 합과 동치다. departure는 transit, connection은 stay 또는 새 departure다. 원시 두 식의 최대 차이 9.39×10⁻¹⁰을 기록하고 clipping하지 않았다.',
      f"{select['E1_max_root_violation']:.12g}; 15개 LP만 실제 solve했다. 600개 reachable-state witness 전수 검증이 모든 나머지 oracle의 최적값이 default보다 낮음을 증명해 priority queue도 중단했다.",
      '0개. S3 root violation≥10⁻⁵ gate를 통과한 cut이 없다.',
      '바꾸지 않는다. Integer plan은 한 상태만 active여서 RHS=그 상태 beta≤plan rho이다. 실제 이번 작업에서는 어떤 cut도 설치하지 않았다.',
      '복수 MESS의 동시 fractional location averaging은 single-unit 부등식으로 남을 수 있어 pair 상태의 conditional 하한을 확인한다.',
      '두 MESS가 상태 (a,b)를 동시에 점유할 때 원래 full M1 conditional objective의 하한이다. 모든 11250개 조합은 default global lower bound를 사용한다.',
      '두 상태 marginal을 연결하는 연속 비음수 joint mass다. Integer 상태에서는 해당 한 cell이 1로 강제된다.',
      'sum_b w[a,b]=y_m[a], sum_a w[a,b]=y_n[b]를 사용한다. 실제 full model에는 w를 추가하지 않았고 작은 transportation precheck에서만 사용했다.',
      f"{select['E2_max_root_violation']:.12g}. top 3 slot×6 pair의 18개 transportation precheck다. Pair O1 LP는 0회이며, 모든 pair의 feasible upper witness 결합 증명으로 계산을 멈췄다.",
      '0개. 모든 precheck가≤10⁻⁷이고 default 이상의 beta가 나올 수 없다는 universal certificate도 있다.','사용하지 않았다. trajectory columns/master/branch-and-price를 만들지 않았다.','사용하지 않았다. cut coefficient는 상속 certified global LB와 조건부 LP dual 하한만 사용한다. Upper witness 값은 오직 stopping proof다.',
      'full model 추가 rows/columns/nonzeros=0/0/0이다. E1/E2는 미구축이다. O1 template은 210544 rows, 235527 continuous columns, 2468066 nonzeros이고 조건 row는 별도다.',
      f'E0 sparse F3의 상속 LB {F3:.12f}, 새 gain=0이다. E1/E2 full root LP는 gate 미통과로 NOT_RUN이다.',
      f'Sparse E0 reference는 S2보다 {F3-DEFAULT:.12f} 낮다. 새 solve가 나빠진 것이 아니라 F3 base 비교값이다. S2 상속 하한은 그대로 보존했다.',
      '아니다. 새 material gain=0<0.001이다. 단순 default 부등식이 F3에서 줄 수 있는 최대 개선도 기존 S2의 0.0003630437 이하다.',
      '아니다. E0=0.5718494602다.','아니다.','아니다.',
      f'E0 F3 동일 UB 대비 {gap:.8%}; 참고 S2는 14.54601025%다. LP implied gap이며 MIP certificate를 갱신하지 않는다.',
      '실행하지 않았다. useful cut gate와 0.001 material gate 모두 실패했다.','NOT_RUN: BestBd/gap은 null이며 측정값을 만들지 않았다.','아니다. canary가 없고 production gate도 열리지 않았다.',
      f'production은 NOT_RUN이다. Retained incumbent UB={UB:.16f}, 기존 MIP LB={old["M1_P1_BOUND"]:.16f}, 기존 gap={old["M1_P1_GAP"]:.8%}를 별도로 유지한다.',
      '실행하지 않았다. P1 0.5% quality certificate가 없고 production도 미실행이다.','아니다. M1_ACCEPTED=false다.',
      f'새 production incumbent는 없다. 기존 incumbent의 route/timing/travel/Pch/Pdis/Q/PCS16/mode/SOC/terminal/AIDC 및 line/transformer/robust 조건을 독립 재검증해 PASS했다. Band는 0.955–1.045다. Retained MIP incumbent node83.2/slot79={robust["validation"]["node83p2_slot79_voltage_pu"]:.12f} pu이며 cut tuning에 쓰지 않았다.',
      '가능하지만 미검증이다. 새 UB가 없으므로 incumbent quality가 dominant라고 결론낼 근거도 없다. 이번에는 heuristic/search 전략을 바꾸지 않았다.',
      '이번 single-slot O1 cuts는 gain을 설명하지 못한다. 그러나 다른 시간의 grid obligation을 제거한 O1 자체가 약하므로 full-grid spatial mechanism을 배제할 수 없다. 다음 가설은 MULTI-TIME / GLOBAL DISCRETE EPIGRAPH COUPLING이다.',
      '여러 critical slot 또는 전체 grid horizon을 유지하는 conditional relaxation을 별도 preregister하고 exact lower certificate를 생성하는 단계다. 이번 작업에서는 구현하지 않았다.',
      'M1 P1/P2 quality acceptance가 성립하지 않았다. A2/M2/Actual/Fresh AC/IEEE8500은 NOT_RUN, Actual P/Q correction OFF, PROBLEM13_FINAL_VALIDATED=false다.'
    ];assert len(answers)==50
    prose('FINAL_REVIEW_KO.md','# 최종 한국어 리뷰\n\n'+'\n\n'.join(f'{i}. {q}\n\n{a}' for i,(q,a) in enumerate(zip(questions,answers),1)))
    # Preserve raw MPS outside checkout; store compact exact bytes as evidence.
    templates=OUT/'oracle_templates';templates.mkdir(exist_ok=True)
    for t in freeze['slots']:
        destination=templates/f'O1_{t}.mps.gz'
        if not destination.exists():destination.write_bytes(gzip.compress((LOCAL/f'O1_{t}.mps').read_bytes(),mtime=0))
    dump('SOURCE_MANIFEST.json',dict(BASE_HEAD=HEAD,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for folder in [ROOT/'v42_epigraph',ROOT/'tests/v42_epigraph'] for p in sorted(folder.glob('*')) if p.is_file()],
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),slot_freeze_sha256=sha(OUT/'CRITICAL_SLOT_FREEZE.json'),A1_anchor_receipt=read(OUT/'A1_ANCHOR_REUSE_RECEIPT.json'),
        templates=[dict(path=(templates/f'O1_{t}.mps.gz').relative_to(ROOT).as_posix(),compressed_sha256=sha(templates/f'O1_{t}.mps.gz'),raw_sha256=sha(LOCAL/f'O1_{t}.mps')) for t in freeze['slots']]))
    print('FINAL REPORT GENERATED',flags,flush=True)

if __name__=='__main__':run()
