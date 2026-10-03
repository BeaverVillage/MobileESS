"""Evidence-based verdicts under the frozen rules; diagnostics stay quarantined."""
from .analytics import *

LEVELS={'CONFIRMED','STRONGLY_SUPPORTED','WEAKLY_SUPPORTED','NOT_SUPPORTED','INCONCLUSIVE'}

def classify_method(m1,m2,root_complete,branch):
    if m2['terminal_optimal'] and not m1['terminal_optimal'] and m2['historical_target_objective_difference']<=1e-8:
        return 'CONFIRMED' if root_complete or branch else 'STRONGLY_SUPPORTED'
    if m1['terminal_optimal'] and m2['terminal_optimal']:return 'NOT_SUPPORTED'
    return 'INCONCLUSIVE'

def classify_degeneracy(bases):
    measured=[b['metrics']['1e-08'] for b in bases.values()]
    if not measured:return 'INCONCLUSIVE'
    if any((m['basic_variables']>=100 and m['primal_degenerate_basic_ratio']>=.5) or (m['nonbasic_variables']>=100 and m['near_zero_RC_nonbasic_ratio']>=.5) for m in measured):return 'STRONGLY_SUPPORTED'
    return 'WEAKLY_SUPPORTED'

def run():
    roots={k:{j:read(f'ROOT_LP_METHOD{j}_{k.upper()}.json') for j in [0,1,2]} for k in ['original','compact']}
    timeline=read('ROOT_PHASE_TIMELINE.json');grid=read('GRID_BLOCK_ATTRIBUTION.json');basis=read('DEGENERACY_AUDIT.json')['bases'];duplicates=read('DUPLICATE_PROPORTIONAL_ROWS.json')['formulations']
    scaled=read('ROW_SCALED_METHOD1_DIAGNOSTIC.json');aux=read('AUX_ELIMINATION_DIAGNOSTIC.json');census=csvread('MATRIX_FAMILY_CENSUS.csv');rules=read('PREREGISTRATION.json')
    method={k:classify_method(roots[k][1],roots[k][2],timeline['MIP'][k]['root_relaxation_completed'],timeline['MIP'][k]['first_branch_observed']) for k in roots}
    order=['CONFIRMED','STRONGLY_SUPPORTED','WEAKLY_SUPPORTED','NOT_SUPPORTED','INCONCLUSIVE']
    methodlevel=min(method.values(),key=order.index)
    scalingmaterial=(scaled['terminal_optimal'] and (not roots['original'][1]['terminal_optimal'] or scaled['solver_runtime']<=.8*roots['original'][1]['solver_runtime']))
    exacts=[int(float(r['count_abs_a_gt_100']))+int(float(r['count_abs_a_lt_1e-12'])) for r in census if r['formulation']=='original'];concentration=max(exacts)/sum(exacts)
    scaling='STRONGLY_SUPPORTED' if scalingmaterial and concentration>=.5 else 'NOT_SUPPORTED' if not scalingmaterial else 'WEAKLY_SUPPORTED'
    kappas=[float(b['Kappa']) for b in basis.values() if b['Kappa'] is not None]
    condition='STRONGLY_SUPPORTED' if any(x>=1e12 for x in kappas) else 'WEAKLY_SUPPORTED' if kappas else 'INCONCLUSIVE'
    deg=classify_degeneracy(basis);dupcount=sum(v['redundant_rows_relative_to_first_representative'] for v in duplicates.values())
    rows=[]
    def add(cause,level,evidence,limit):
        assert level in LEVELS;rows.append(dict(cause=cause,classification=level,numerical_evidence=evidence,causal_limit=limit))
    add('Method=1 pathology',methodlevel,dict(per_formulation=method,Method1={k:roots[k][1] for k in roots},Method2={k:roots[k][2] for k in roots},MIP=timeline['MIP'],historical_barrier_repeat=rules['historical_objectives']),
        'Method2 standalone LP convergence does not guarantee fast MIP crossover/root processing. CONFIRMED only where literal MIP root completion/nonroot callback observed.')
    add('coefficient scaling',scaling,dict(original_dynamic_range=grid['formulations']['original']['dynamic_range'],largest_extreme_family_share=concentration,positive_row_scaled_result=scaled,material_improvement_gate=scalingmaterial),
        'This prescribed positive row normalization tests one exact strategy, not all possible equivalent scaling. No same-unit comparison of scaled and unscaled infeasibility sums.')
    add('poor numerical conditioning',condition,dict(Kappa_estimates=kappas,KappaExact=None,matrix_dynamic_range=grid['formulations']['original']['dynamic_range']),
        'Matrix spread alone is not a basis condition measurement. A terminal basis estimate concerns that basis, not all intermediate bases; KappaExact omitted for excessive factorization cost.')
    add('degeneracy',deg,dict(terminal_optimal_basis_metrics={k:v['metrics'] for k,v in basis.items()},zero_step_pivots=None),
        'No terminal optimal basis means INCONCLUSIVE. High iterations, active inequalities or unbounded helper declarations alone do not prove degenerate pivots.')
    add('redundant rows','WEAKLY_SUPPORTED' if dupcount else 'NOT_SUPPORTED',dict(exact_redundant_counts={k:v['counts'] for k,v in duplicates.items()},total_redundant_relative_to_representative=dupcount),
        'Exact proportional redundancy is established where found; causal slowdown has not been measured by exact removal. Trivial constant rows are counted separately.')
    add('response auxiliary burden','STRONGLY_SUPPORTED' if any(v['grid_nnz_share']>.5 for v in grid['formulations'].values()) else 'WEAKLY_SUPPORTED',dict(grid_structural_shares=grid['formulations'],helpers=81216,partial_projection=aux),
        'Grid prefix is broader than response helpers; full 81216-helper flattening has a concrete nonrepresentable binary64 coefficient, so full elimination speedup is unmeasured. Partial injection elimination may increase nnz.')
    isolates=grid['isolation'];ref=grid['isolation_reference']
    for cause,label in [('voltage rows','NON_SCIENTIFIC_REMOVE_VOLTAGE_LOWER_120S'),('line thermal polygon rows','NON_SCIENTIFIC_REMOVE_LINE_THERMAL_FACE_120S')]:
        r=isolates.get(label);level='STRONGLY_SUPPORTED' if r and r['terminal_optimal'] and ref and not ref['terminal_optimal'] else 'INCONCLUSIVE'
        add(cause,level,dict(isolated_arm=r,full_120s_reference=ref),
            'One-family removal is physics-invalid; progress alone is not a same-objective scientific result. Only voltage_lower was removed, not the complete voltage block.')
    add('compact continuous expansion','WEAKLY_SUPPORTED',dict(original_continuous=108431,compact_continuous=307417,continuous_delta=198986,columns_delta=96,
        original_nnz=8282350,compact_nnz=12678118,nnz_delta=4395768,nnz_increase_fraction=4395768/8282350,Method1=roots['compact'][1]['solver_runtime'],Method2=roots['compact'][2]['solver_runtime']),
        'Most extra continuous variables are retyped inherited binaries; total columns increase by 96. More nnz is a measured structural burden, not an isolated proof of continuous-variable count causing delay.')
    add('binary combinatorics','INCONCLUSIVE',dict(original_binaries=208312,compact_binaries=9422,binary_reduction_fraction=1-9422/208312,
        root_LPs_all_continuous=True,first_branch_observed={k:v['first_branch_observed'] for k,v in timeline['MIP'].items()}),
        'Persistent trouble in fully relaxed LP cannot be attributed to tree enumeration. Binary combinatorics after root has not been resolved by this bounded diagnostic.')
    add('MIP Start','NOT_SUPPORTED',dict(accepted={k:read(f'MIP_ROOT_METHOD2_{k.upper()}_300S.json')['Start_accepted'] for k in roots},primary_differences={k:read(f'MIP_ROOT_METHOD2_{k.upper()}_300S.json')['accepted_Start_primary_max_difference'] for k in roots},UB=UB),
        'PR126 Start accepted with exact primary identity; the remaining bottleneck occurs after incumbent acceptance. This does not claim Start quality is globally optimal.')
    dump('ROOT_CAUSE_CLASSIFICATION.json',dict(preregistered_rules_sha256=sha(OUT/'PREREGISTRATION.json'),causes=rows,certificate_update=False))
    enough=methodlevel in {'CONFIRMED','STRONGLY_SUPPORTED'}
    flags=dict(M1_ACCEPTED=False,M1_ROOT_CAUSE_DIAGNOSED=enough,COMPACT_M1_PRODUCTION_AUTHORIZED=False,PRODUCTION_1800S='NOT_RUN',P2='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False,Benders_calls=0,new_decompositions=0)
    dump('FINAL_FLAGS.json',flags)
    ranks=[dict(rank=1,cause='Method1 root-LP method sensitivity',classification=methodlevel),dict(rank=2,cause='Grid matrix/factorization burden',classification='STRONGLY_SUPPORTED',limit='Structural burden supported; exclusive causal mechanism remains unresolved'),dict(rank=3,cause='Degeneracy / conditioning mechanism',classification=deg if deg!='INCONCLUSIVE' else condition,limit='Measured basis evidence only; absence of basis leaves INCONCLUSIVE')]
    verdict=dict(status='DIAGNOSED_WITH_EXPLICIT_LIMITATIONS' if enough else 'INCONCLUSIVE',ranked_causes=ranks,flags=flags,
        certificate=dict(UB=UB,LB=LB,gap=(UB-LB)/UB,unchanged=True,diagnostic_LP_objective_not_adopted=True),Method1=method,scaling=scaling,degeneracy=deg,conditioning=condition,
        compact=dict(binary_reduction_percent=100*(1-9422/208312),nnz_increase_percent=100*4395768/8282350,
            total_columns_increase=96,continuous_retyping_delta=198986,
            reason_binary_reduction_does_not_remove_root_pathology='Every tested root LP already has all integer variables relaxed. Compact retains the same grid-response block and adds 53.07% nnz through route expressions.',
            branching_advantage='INCONCLUSIVE unless comparative nonroot evidence proves it; neither binary count nor barrier-only speed proves faster branching',
            discard_compact_authorized=False,discard_reason='Root performance does not prove absence of downstream tree benefit; no production Compact adoption either.'),
        direct_cause_sentence='현재 M1이 느린 가장 직접적인 원인은 같은 LP에서 확인한 Method=1의 진행 지연이며, 이를 만드는 구조적 원인은 큰 grid-response 행렬 부담으로 강하게 지지되지만 degeneracy·conditioning의 구체적 인과관계는 '+('basis 증거 범위에서만 지지된다.' if deg!='INCONCLUSIVE' else 'INCONCLUSIVE이다.'))
    dump('FINAL_VERDICT.json',verdict)
    fix='''# Root cause to exact fix priorities

| Priority | Candidate next exact fix | Expected benefit | Exactness risk | Complexity | Scientific impact | Required proof |
|---|---|---|---|---|---|---|
| 1 | Root method and basis-acquisition redesign informed by measured barrier/crossover phases | Reproduce fast barrier convergence while controlling observed crossover/root completion delay | Low for method change; do not infer a completed MIP root from barrier alone | Medium | Preserve every F3 row, bound, type, objective and tolerance | Same matrix/Start identity; terminal root event and postroot observations; no automatic certificate update |
| 2 | Exact sparse response representation that avoids substitution fill-in | Reduce measured grid nnz/factorization burden | Medium: full binary64 flattening fails exact transport; injection-only projection substantially enlarges nnz | High | Exact response equations and physical rows retained | Exact rational bidirectional mapping and representable coefficients, full matrix audits, terminal objective gate |
| 3 | Exact redundant-row simplification, if measured duplicates justify cost | Potentially remove algebraically redundant workload | Medium: retain RHS, sense, domains and affine constants; trivial/duplicate rows do not prove a runtime gain | Medium | Identical feasible set | Primitive dyadic rational comparison of every removed row; same tolerance/domain and objective validation |
| 4 | Additional exact normalization only if basis/units evidence motivates it | Possible conditioning benefit; current row-scale experiment does not authorize broad parameter sweeps | Medium: equivalent rows still change numerical interpretation of absolute tolerance | Medium | Exact real feasible set, original-unit residual audit | Positive scalar proof for all coefficients/RHS; no deletion; same solver tolerances; both-direction point audit |
| 5 | Compact branching evaluation after reproducible root completion | Test whether 95.477% fewer binaries improves the tree | Low model risk, unresolved performance benefit | Medium | Preserve exact compact mapping and Start | Matched root-complete controls, nonroot nodes and equivalent objective; no claims from binary count alone |

No production fix is executed in this task. Priorities reflect measured structural and method evidence, with detailed phase and degeneracy limitations in ROOT_CAUSE_CLASSIFICATION.json. Physics-invalid isolation copies cannot certify any proposed fix.
'''
    (OUT/'ROOT_CAUSE_TO_FIX_MAP.md').write_text(fix,encoding='utf8',newline='\n')
    dump('RESOURCE_RECEIPT.json',dict(sequential_heavy_lane=True,RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,
        snapshots=[dict(file=p.name,sha256=sha(p),CPU_percent=read(p.name)['CPU_percent'],available_RAM_bytes=read(p.name)['RAM']['available'],active_Python_solver_processes=read(p.name)['active_Python_solver_processes']) for p in sorted(OUT.glob('RESOURCE_*.json')) if p.name!='RESOURCE_RECEIPT.json'],
        same_hardware_as_PR126=True,Gurobi_Threads=4,BLAS_OpenMP_threads=1,concurrent_independent_work_allowed=True,
        comparison_scope='New arms are sequential in one M1 lane. Historical wall-time comparisons are indicative because concurrent workloads may differ; controls/settings differences, including Start and Crossover, are disclosed. No claim of a controlled historical absolute speedup.'))
    return verdict

if __name__=='__main__':run()
