"""Preregister and compare matrices without an optimize call."""
import shutil
import gurobipy as gp
from .common import *

def setup():
    assert git('rev-parse','HEAD')==BASE and not (OUT/'PREREGISTRATION.json').exists()
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    resource=resource_snapshot();threads=1 if resource['other_heavy_solve'] else 4
    dump('RESOURCE_PREREGISTRATION.json',resource)
    files=git('ls-files').splitlines();assert len(files)==1464
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,BASE_HEAD=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in files]))
    dump('PR113_BASE_RECEIPT.json',dict(BASE_PR=113,BASE_HEAD=BASE,branch=git('branch','--show-current'),
        inherited_B3=read(PR113/'B3_BUFFER_CERTIFICATE.json'),inherited_global_UB=ORIGINAL_UB,inherited_S2_LB=S2,
        inherited_PR113_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(PR113.rglob('*')) if p.is_file()]))
    dump('THRESHOLD_AUTHORITY.json',dict(T=T,decimal_calculation='0.5722125039436496 + 0.001 = 0.5732125039436496',
        inherited_S2_original_global_LB=S2,S2_is_not_partial_B3_floor=True,reference='PR113 inherited S2 materiality reference',
        hard_row='rho_max <= 0.5732125039436496',objective='minimize zero',negative='validated B3 rho <= T with numerical guard',
        positive='full exact threshold-feasibility model proven INFEASIBLE',timeout='INCONCLUSIVE unless independent validated witness exists'))
    dump('PREREGISTRATION.json',dict(BASE_PR=113,BASE_HEAD=BASE,created_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        threshold=T,threshold_not_relaxed=True,B3_window=WINDOW,B3_restored_binaries=85744,threads=threads,
        threads_reason='1 if observed independent heavy solver else 4. No thread performance superiority attribution.',
        direct_seconds=1800.,candidate_seconds=240.,candidate_count=2,root_sources=SOURCES,primary_strategies=1,fallbacks=0,
        settings=COMMON_SETTINGS,strategy_rationale='Pure feasibility hard threshold, dual simplex Method1 avoids inherited slow barrier/crossover; MIPFocus1/Heuristics0.2 seek a witness. NumericFocus1 and tighter feasibility/integrality tolerances audit inherited warnings. Joint strategy; no parameter sweep.',
        witness_policy='Two complete root-nearest paths, one per BASE F3 and S3 source; fix only B3 route binaries to each path. Modes remain original B3 binaries; P/Q/SOC/outside variables free. Failed/INFEASIBLE restricted candidates cannot prove full B3 infeasibility. Exact duplicate fixed B3 route masks are skipped with evidence, count never expanded.',
        direct_solve_mandatory=True,direct_start='Validated witness if one exists; otherwise W1 B3 route plus rounded root mode partial seed, all continuous/outside variables undefined. Original complete start violates threshold and is never misrepresented as feasible here.',
        safety=dict(matrix_tolerance=MATRIX_TOL,integer_tolerance=INTEGER_TOL,rho_recomputation_tolerance=RHO_TOL,threshold_acceptance_margin=THRESHOLD_MARGIN,
            rule='No threshold epsilon relaxation. Accept only rho AND independently recomputed P1 <= T-1e-6. Reject ambiguous boundary point, retain raw result; no second optimization.'),
        early_stop='Stop candidate search on independently validated safe witness; run mandatory exact direct solve once, stopping at first native solution. Never continue after certificate. Unsafe first solution retained as numerical-borderline INCONCLUSIVE, no retune.',
        INFEASIBLE_authority='Only exact unrestricted direct model status3. Floating-point solver proof at registered tolerances, not an exact rational proof. INF_OR_UNBD/Numeric/interruption/time limit without validated point are inconclusive.',
        IIS='Availability reported; expensive full-MIP IIS not automatically computed. Farkas dual is LP-only, not a complete MIP infeasibility proof.',
        B1_optimize_calls=0,B2_optimize_calls=0,production=False,P2=False,downstream=False,new_cuts=False,
        scope=[1,2,3,4,5,6,8,13],excluded_new_work=[7,9,10,11,12],causal_closure='Diagnosis only iff threshold scientific classification remains inconclusive; no expanded-window solve',
        decomposition='Design/exactness proof/bounded fixture proposal only iff inconclusive with computational bottleneck',
        official_parameters='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html',
        official_tolerances='https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/tolerances_scaling.html'))
    dump('ROOT_GUIDED_WITNESS_PREREGISTRATION.json',dict(candidate_count=2,sources=SOURCES,ranking='duration-weighted L1 to root route flow on original complete time-expanded graph',
        route_only_bounds_fixed='authorized B3 route variables only',mode_seed='root mode >=0.5 =>1, otherwise0, only as partial MIP start; mode bounds not fixed',
        candidate_seconds=240.,candidate_parameter_sweep=False,search_failure_not_negative_evidence=True,exact_direct_not_pruned=True))
    # Preserve location-independent inherited test runtime, outside the repository.
    inherited_runtime=ROOT.parent/'V42_CERTIFICATE_LOCAL';inherited_runtime.mkdir(exist_ok=True)
    old_runtime=Path('C:/Users/kjw39/Documents/Codex/2026-10-01/files-pasted-by-the-user-repository/work/V42_CERTIFICATE_LOCAL')
    for name in ['F3.mps','B3_OPTIMIZE_STARTED.json']:
        shutil.copyfile(old_runtime/name,inherited_runtime/name)
    shutil.copyfile(inherited_runtime/'F3.mps',LOCAL/'F3.mps')
    assert sha(LOCAL/'F3.mps')==read(PR112/'F3_TEMPLATE_RECEIPT.json')['sha256']
    dump('INHERITED_RUNTIME_REUSE.json',dict(PASS=True,new_optimization_calls=0,
        purpose='Read-only inherited 593-test fixtures use a relative runtime path; copy original sealed MPS and inherited B3 marker there without changing tracked sources.',
        template_sha256=sha(LOCAL/'F3.mps'),inherited_marker_sha256=sha(inherited_runtime/'B3_OPTIMIZE_STARTED.json')))
    audit()
    from .routes import generate
    generate()
    print('THRESHOLD PREPARATION PASS',T,'threads',threads,flush=True)

def audit():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    base=gp.read(str(LOCAL/'F3.mps'),env=env);base.setAttr('VType',['B' if x else 'C' for x in domains()]);base.update()
    target=threshold_model(env);A=base.getA();B=target.getA();a=axis();names=list(a['names'])
    assert base.getAttr('VarName')==target.getAttr('VarName')==names
    assert base.getAttr('VType')==target.getAttr('VType')
    assert np.array_equal(base.getAttr('LB'),target.getAttr('LB')) and np.array_equal(base.getAttr('UB'),target.getAttr('UB'))
    b=B[:-1];assert np.array_equal(A.indptr,b.indptr) and np.array_equal(A.indices,b.indices) and np.array_equal(A.data,b.data)
    assert base.getAttr('RHS')==target.getAttr('RHS')[:-1] and base.getAttr('Sense')==target.getAttr('Sense')[:-1]
    assert base.getAttr('ConstrName')==target.getAttr('ConstrName')[:-1]
    with np.load(PR113/'MPS_ROW_ALIAS_AXIS.npz',allow_pickle=False) as z:
        assert base.getAttr('ConstrName')==list(z['mps_names']) and np.array_equal(z['native_names'],a['rownames'])
    rho=names.index('rho_max');last=B[-1];assert last.nnz==1 and last.indices[0]==rho and last.data[0]==1
    assert target.getConstrs()[-1].RHS==T and target.getConstrs()[-1].Sense=='<'
    assert np.count_nonzero(target.getAttr('Obj'))==0 and target.ObjCon==0
    assert np.count_nonzero(base.getAttr('Obj'))==1 and base.getVars()[rho].Obj==1
    assert int(domains().sum())==85744
    from v42_certificate.common import restore
    assert np.array_equal(domains(),[restore(str(n),str(k),'B3',arcs()) for n,k in zip(a['names'],a['original_types'])])
    assert all(base.getConstrs()[int(i)].RHS==760 and base.getConstrs()[int(i)].Sense=='=' for i in a['terminal_rows'])
    initial_rows=np.flatnonzero(a['rownames']=='initial_SOC');assert len(initial_rows)==4
    dump('B3_THRESHOLD_MATRIX_IDENTITY.json',dict(PASS=True,template_sha256=sha(LOCAL/'F3.mps'),PR113_B3_domain_sha256=sha(PR113/'B3_DOMAIN.json.gz'),
        variable_axis_exact=True,variables=316743,original_rows=954560,threshold_rows=954561,original_nonzeros=8282350,threshold_nonzeros=8282351,
        B3_binaries=85744,bounds_exact=True,domain_exact=True,original_coefficients_exact=True,original_RHS_exact=True,original_senses_exact=True,
        original_row_order_and_aliases_exact=True,removed_rows=0,original_row_changes=0,new_rows=1,new_row_name='B3_THRESHOLD_RHO',
        threshold_row_coefficient=1,threshold_RHS=T,objective_changes_only='rho coefficient1 to constant zero',initial_SOC_equalities=4,terminal_SOC_equalities=4,
        full96_grid_retained=True,PCS16_retained=True,robust_voltage=[.955,1.045],route_pruning=0,no_new_physics=True,audit_optimize_calls=0))
    prose('B3_THRESHOLD_FORMULATION.md',f'''# B3 threshold decision

Let F_B3 be the exact PR113 partial-integrality set (85,744 restored binaries; all 954,560 original F3 rows). The scientific decision set is F_B3 intersect {{rho_max <= {T}}}; objective is identically zero. Its native axis has 316,743 variables and exactly one additional nonzero/row. Original rho epigraph semantics, full96 physics/grid/PCS16 and terminal equalities remain unchanged.

A validated threshold witness gives opt_B3 <= T and hence opt_B3-S2 <=0.001. Proven infeasibility of the unrestricted decision model gives opt_B3 >T. A failed route-fixed subset never proves that the unrestricted set is empty. S2 is a reference, not an installed lower floor on B3. At exact threshold equality the user's nonmaterial ceiling includes equality; acceptance conservatively requires a 1e-6 margin without changing the hard row.

Root candidates fix only restored route bounds, as upper-witness generators. The exact direct model has no fixed bounds, omitted arcs, additional SOC/voltage relaxations, or route candidate restrictions. One mandatory direct solve follows candidate search even if a witness was found; a complete safe witness makes its feasibility acceptance terminate at the first solution. No B1/B2/prod/decomposition solve follows.

Constant objectives describe feasibility problems in the [Gurobi objective documentation](https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/objectives.html). Native status3 is a solver-certified floating-point MIP infeasibility result at registered tolerances; it is not a rational-arithmetic proof. Numerical-boundary points are never declared certificates.''')
    base.dispose();target.dispose();env.dispose()

if __name__=='__main__':setup()
