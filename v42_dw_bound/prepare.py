"""Read-only checkpoint authority and preregistration, no optimize calls."""
from .common import *
from fractions import Fraction as F
import numpy as np
from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_dw_root.models import hash_column
from v42_degen.identity import inputs,signature

def prepare():
    gate('prepare');assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    assert not (OUT/'DW_DUAL_BOUND_PREREGISTRATION.json').exists(),'APPEND_ONLY_PREREGISTRATION'
    assert read(OUT/'DW_CORRECTED_BOUND_BOUNDED_FIXTURES.json')['PASS']
    theorem=dict(PASS=True,formula='delta_m=min(0,beta_m); alpha_prime_m=alpha_m+delta_m',
      algebra=[
        'For every v in X_m, rc_m(v)>=r_m_star>=beta_m. If beta_m<0, rc_m(v)-delta_m>=beta_m-beta_m=0; otherwise rc_m(v)-delta_m>=beta_m>=0.',
        'With minimization Pi<=0 on <= rows, Pi>=0 on >= rows, unrestricted equality Pi, every feasible point satisfies c_z z+sum c_m v >= constant+Pi h+(c_z-G^T Pi)z+sum (c_m-B_m^T Pi)v.',
        'For lambda>=0 and each sum lambda_m=1, corrected column inequalities imply sum lambda_m (c_m-B_m^T Pi)v>=sum alpha_prime_m.',
        'Thus L=constant+Pi h+min_proven_box_z(c_z-G^T Pi)z+sum alpha_prime_m is a valid full-DW lower bound. No assumption of zero residual on free/global variables is made.',
        'For an exactly optimal RMP dual with strong duality, its global-box dual plus sum alpha equals z_RMP, giving the textbook expression z_RMP+sum delta. The floating solver ObjVal is NOT substituted for an exact dual objective.',
        'Restricted feasible columns are a subset of the full master columns, so exact restricted optimum U=z_RMP bounds full optimum above. Real solver U is accepted only with native OPTIMAL, all-original-row postsolve1e-6 and strict bounds/route1e-8 under the registered numerical authority.',
        'L>=T proves materiality; U<=T proves nonmateriality. Equality at T follows the requested <= nonmaterial decision convention. No original-integer UB is inferred from U.'],
      implementation_refinement='Exact Fraction global dual and finite proven coordinate enclosures pay every global stationarity residual. Native global ObjBound is lowered by fixed1e-8 and rounded down before forming beta/delta. Only inequality-sign-valid raw Pi is used; no sign projection or pricing-dual alteration.',
      bounded_enumeration_proof_SHA=sha(OUT/'DW_CORRECTED_BOUND_BOUNDED_FIXTURES.json'),formal_proof_before_scientific_runner=True)
    write('DW_CORRECTED_DUAL_THEOREM.json',theorem)
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    write('BASE_BYTE_FREEZE.json',dict(base=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths if p]))
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    assert signature(B,e)==read(OLD/'DW_BASE_MODEL_IDENTITY.json')['reference']
    blocks=prototypes(B,e,owner,row_owner,native)
    full_owner=np.full(A.shape[0],-1,dtype=np.int8)
    for i in range(A.shape[0]):
        deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(deps)==1 and -1 not in deps:full_owner[i]=next(iter(deps))
    full={}
    for m,b in enumerate(blocks):
        rr=np.flatnonzero(full_owner==m);cc=b.columns
        data=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.))
        matrix=A[rr][:,cc];full[m]=(matrix,data,pure_binary_equalities(matrix,data))
    records=pool();assert len(records)==1048;checks=[]
    for directory,h in records:
        m=UNITS.index(h['MESS']);b=blocks[m]
        with np.load(directory/h['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];c=float(z['objective'])
            assert np.array_equal(z['original_columns'],b.columns) and hash_column(x,a,c)==h['SHA256']
            assert np.array_equal(b.B@x,a) and float(b.d['objective']@x)==c
            exact,error=b.exact_coupling(x,a);assert error<=1e-12
            for i,n,q in zip(z['exact_rows'],z['exact_numerators'],z['exact_denominators']):assert exact[int(i)]==F(int(n),int(q))
        physical=b.validate(x,True);matrix,data,mask=full[m];raw=corrected_rows(matrix,data,x,True,mask)
        assert physical['PASS'] and raw['PASS'],h['file']
        checks.append(dict(file=(directory/h['file']).relative_to(ROOT).as_posix(),file_SHA=sha(directory/h['file']),column_SHA=h['SHA256'],MESS=h['MESS'],PASS=True,axis_exact=True,
          full_original_local_rows=matrix.shape[0],original_row_max=raw['max_constraint_violation'],raw_integer_exact=True,physical_route_movement_mode_PQ_SOC_terminal_travel_PCS_PASS=True))
    write('DW_BOUND_CHECKPOINT_AUDIT.json',dict(PASS=True,base=BASE,initial_columns=4,generated_columns=1044,total_columns=1048,checks=checks,optimization_calls=0,old_pricing_replay_calls=0,
          terminal_iteration263_dual_reused=False,matrix_partition_unchanged=True,reference_signature=signature(B,e)))
    write('DW_DUAL_BOUND_PREREGISTRATION.json',dict(type='NEW_FULL_DOMAIN_CORRECTED_DUAL_BOUND_EXPERIMENT',base=BASE,branch='codex/v42-m1-dw-certified-dual-bound-v1',
        total_new_heavy_budget_seconds=3600,heavy_budget_authority='Cumulative wall spent within sequential native RMP/pricing optimize calls; build/read-only audits/certificate arithmetic/checkpoint I/O/regression separately timed, as requested.',
        per_RMP_max_seconds=300,per_pricing_max_seconds=300,MAX_HEAVY_WORKERS=1,Gurobi_Threads=1,environment=ENV,
        solver_tolerance=EPS,affine_postsolve_tolerance=POST,physical_bounds_and_route_integer_authority_unchanged=True,
        beta_authority='Finite terminal native minimization ObjBound, never incumbent or root objective. Terminal status OPTIMAL or TIME_LIMIT only; incumbent, if any, must pass physical/postsolve/objective transport audit.',
        beta_safe_formula='down(Fraction(ObjBound)-Fraction(1e-8))',delta='min(0,beta_safe)',
        corrected_LB='down(exact_global_box_dual + sum(Fraction(alpha_m)+Fraction(delta_m)))',
        textbook_formula_only_with_exact_strong_duality='z_RMP+sum min(0,beta_m)',
        upper_authority='Native OPTIMAL RMP ObjVal with independent master and full original-row reconstruction audit under pre-existing numerical contract; upper on DW LP, never original integer UB.',
        material_threshold=T_MATERIAL,stop_criteria=['Corrected certified L>=threshold => PROVEN_MATERIAL','Validated RMP U<=threshold => PROVEN_NONMATERIAL','All four terminal OPTIMAL rc>=-1e-8 and bracket gap<=1e-6 => numerical exact-CG convergence','RMP not optimal / numerical or sign audit failure => STOP','Total native optimize wall budget<=3600; no extra budget'],
        pricing_first_negative_termination=False,pricing_callback_termination=False,heuristic_pricing=False,full_original_local_domain=True,horizon=96,
        optimal_negative_addition='Only terminal OPTIMAL, validated exact rc<-1e-8; at most one most-negative trajectory per block, at most4 per iteration; only after materiality remains undecided.',
        TIME_LIMIT_incumbent_column_addition=False,no_column_deletion_or_aging=True,
        repeated_search_policy='If no OPTIMAL negative column and no decision, continue unresolved FULL native pricing models at the SAME frozen dual in sequential rounds; each call<=300s. Prior OPTIMAL pricing results remain valid only at that identical dual. No RMP re-solve without appended columns.',
        warm_basis='Only previous OPTIMAL basis at identical rows with old columns unchanged and newly appended columns at lower bound. No solver parameter sweep.',
        warm_pricing_start='Previous OPTIMAL physical trajectory as MIP Start only; no fixing/domain/bound modification.',
        checkpoint_columns=1048,checkpoint_audit_SHA=sha(OUT/'DW_BOUND_CHECKPOINT_AUDIT.json'),theorem_SHA=sha(OUT/'DW_CORRECTED_DUAL_THEOREM.json'),
        base_history_byte_freeze_SHA=sha(OUT/'BASE_BYTE_FREEZE.json'),
        pricing_bound_documentation='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound',
        branch_and_price=False,production_M1=False,P2=False,A2=False,M2=False,Actual=False,Fresh_AC=False,May_production=[0,0,0]))
    print('BOUND_PREREG_CHECKPOINT_PASS',len(checks),flush=True)
def freeze():
    write('EXECUTION_FREEZE.json',dict(sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_dw_bound').glob('*.py'))],
       preregistration_SHA=sha(OUT/'DW_DUAL_BOUND_PREREGISTRATION.json'),preopt_source_commit_required=True))
if __name__=='__main__':
    import sys
    if '--freeze-only' not in sys.argv:prepare()
    freeze()
