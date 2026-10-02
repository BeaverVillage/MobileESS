"""Read-only V1 census and preregistration, without any optimize call."""
import gzip, json, shutil, time
import numpy as np
from scipy import sparse
import gurobipy as gp
from .common import *
from .representation import from_model, audit

def census(A, rhs, lower, upper):
    nonzero=abs(A.data[A.data!=0]); row=np.asarray(abs(A).sum(axis=1)).ravel(); col=np.asarray(abs(A).sum(axis=0)).ravel()
    def extent(v): return [float(v.min()),float(v.max())] if len(v) else None
    return dict(rows=A.shape[0],variables=A.shape[1],nonzeros=A.nnz,
        free_variables=int(np.sum(np.isneginf(lower)&np.isposinf(upper))),
        fixed_variables=int(np.sum(lower==upper)),zero_columns=int(np.sum(col==0)),constant_rows=int(np.sum(row==0)),
        nonzero_magnitude=extent(nonzero),row_L1_norm_range=extent(row),column_L1_norm_range=extent(col),
        RHS_range=extent(rhs),nonzero_RHS_magnitude=extent(abs(rhs[rhs!=0])),
        coefficient_dynamic_range=float(nonzero.max()/nonzero.min()),density=float(A.nnz/(A.shape[0]*A.shape[1])))

def run():
    assert git('rev-parse','HEAD')==BASE
    files=git('ls-files').splitlines()
    receipt=[dict(path=p,sha256=sha(ROOT/p)) for p in files]
    assert len(files)==1615 and all(sha(PRIOR/p)==r['sha256'] for p,r in zip(files,receipt))
    dump('PR115_BASE_RECEIPT.json',dict(base=BASE,tracked_files=len(files),PASS=True,files=receipt,
        inherited_tests=708,inherited_bounded_checks=44,
        bounded_receipt_sha256=sha(ROOT/'docs/v42_m1_integrality_gap_root_cause/WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')))
    # Separate local copies for inherited read-only tests; never change the source cache.
    for folder in ['THRESHOLD_LOCAL','V42_CERTIFICATE_LOCAL','V42_TWO_LOCAL']:
        src=PRIOR.parent/folder; dst=ROOT.parent/folder; dst.mkdir(parents=True,exist_ok=True)
        for p in src.iterdir():
            if p.is_file() and not (dst/p.name).exists(): shutil.copy2(p,dst/p.name)
    from v42_threshold.common import resource_snapshot
    resource=resource_snapshot(); assert not resource['other_heavy_solve']
    resource.update(threads=4,fixture_threads=1,sequential=True,method=1,parameter_sweep=False,
        real_optimization_calls=0,B0_B1_executed=False)
    dump('RESOURCE_RECEIPT.json',resource)
    root=PRIOR.parent/'BENDERS_LOCAL'
    local=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(root.iterdir()) if p.is_file()]
    old=json.loads((ROOT/'docs/v42_mess_exact_benders/B3_PROGRESS_RECONCILIATION.json').read_text())
    assert old['source_master_point_available'] is False
    dump('PR115_FIRST_X_RECEIPT.json',dict(status='UNRECOVERABLE_FROM_AVAILABLE_EVIDENCE',restored=False,
        source_x_sha256=None,master_resolved=False,local_inventory=local,
        inherited_receipt_sha256=sha(ROOT/'docs/v42_mess_exact_benders/B3_PROGRESS_RECONCILIATION.json'),
        evidence='V1 executed engine only persisted source_x with a successfully constructed cut; first certificate threw before any cut. Raw master log contains objective/status only, no assignment.',
        cannot_substitute_prior_incumbent=True))
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    comparisons=[];v1=[];v2=[]
    from v42_benders.canonical import from_model as canonical
    from v42_benders.audit import mask
    for label in ['full','B3']:
        m=gp.read(str(ROOT.parent/'THRESHOLD_LOCAL/F3.mps'),env=env)
        if label=='B3':m.addConstr(m.getVarByName('rho_max')<=.5732125039436496,name='exact_B3_threshold');m.update()
        n=from_model(m,None if label=='full' else mask());can=canonical(m,None if label=='full' else mask())
        na=audit(m,n); assert na['PASS'] and n.source_hash==can.original_hash
        a=census(can.A,can.b,np.full(len(can.yi),-np.inf),np.full(len(can.yi),np.inf))
        a.update(partition=label,scientific_original_rows=m.NumConstrs,equality_duplication_rows=int(np.sum(n.sense=='=')),
            explicit_finite_bound_rows=len(can.bound_columns),original_fixed_continuous_variables=int(np.sum(n.lower==n.upper)),
            bookkeeping_rows_deleted=0,constant_rows_retained=True)
        v1.append(a);b=census(n.A,n.b,n.lower,n.upper);b.update(partition=label,**na);v2.append(b)
        comparisons.append(dict(partition=label,PASS=True,V1_rows=can.A.shape[0],V2_rows=n.A.shape[0],
            columns=n.A.shape[1],V1_nonzeros=can.A.nnz,V2_nonzeros=n.A.nnz,
            removed_representation_rows=len(can.bound_columns)+int(np.sum(n.sense=='=')),scientific_row_difference=0,
            objective_bitwise_equal=bool(np.array_equal(n.c,can.c)),source_hash=n.source_hash))
        del can,n;m.dispose();print(label,'READ-ONLY MATRIX CENSUS PASS',flush=True)
    env.dispose()
    warnings=[s.strip() for s in gzip.decompress((ROOT/'docs/v42_mess_exact_benders/B3_recourse.log.gz').read_bytes()).decode().splitlines() if any(k in s.lower() for k in ['warning','kappa','numerical'])]
    dump('V1_NUMERICAL_ROOT_CAUSE_AUDIT.json',dict(status='MEASURED_NOT_CAUSALLY_IDENTIFIED',partitions=v1,
        inherited_Kappa=5.11554e15,warnings=warnings,sole_cause_claim=False,
        classification='Equality duplication, bound-row expansion and coefficient dynamic range are measured representation features; their causal effect on Kappa cannot be isolated without a same-x experiment.'))
    dump('NATIVE_BOUND_RECOURSE_AUDIT.json',dict(PASS=True,partitions=v2,real_optimize_calls=0))
    dump('V1_V2_MATRIX_COMPARISON.json',dict(PASS=True,partitions=comparisons))
    prereg=dict(base=BASE,frozen_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        Method=1,Seed=20260929,InfUnbdInfo=1,DualReductions=0,Threads=4,fixture_threads=1,
        FeasibilityTol=1e-7,OptimalityTol=1e-7,IntFeasTol=1e-7,NumericFocus=1,SoftMemLimit=12.,
        strict_margin=1e-8,proof_comparison_absolute=1e-7,proof_comparison_relative=1e-7,
        primary='native mixed-sense bound-supported Farkas',fallback='normalized Phase-I only after rejected/unavailable native certificate',
        PhaseI_weights='positive reciprocal power of two >= max(1,abs(original RHS), row max abs coefficient); frozen per original row, independent of x',
        near_zero='Reject cut if rounded or exact source separation <= 1e-8; never classify from tiny positive Phase-I objective alone.',
        same_x_budget_seconds=1800,B3_budget_seconds=1800,canary_seconds=600,production_seconds=1800,
        production_progress='canary validated cuts only, independent original UB, finite global LB, LB improves inherited .5722125039436496 by >=1e-4 or certified gap <=.005; no numerical contradiction',
        P2_A2_M2='requires separate user approval even after accepted P1',
        same_x_required=True,new_master_substitution_for_missing_x=False,parameter_sweep=False,
        science_changes=False,Actual_P_correction=False,Actual_Q_correction=False,
        prepare_optimize_calls=0,source_checkpoint='to be sealed before fixture execution')
    dump('PREREGISTRATION.json',prereg)
    docs={
    'NATIVE_BOUND_RECOURSE_SPEC.md':'''# Native bound recourse
Keep every original row, sense and continuous bound. Partition columns by the exact original ordered xi/yi axes; outside B3 binaries retain native [0,1] bounds as continuous variables. No cleanup is enabled. The inverse map is the identity row axis and xi/yi column indices.
For fixed x, each RHS is the correctly rounded exact rational expression b_i - sum_j B_ij*x_j, using stored IEEE source coefficients. Certificate calculations use the unrounded original expression. Solver FarkasProof is compared against the separately reconstructed rounded solver RHS; the scientific cut uses original b and B. No tolerance-based coefficient deletion or scientific RHS adjustment is permitted.
''',
    'NATIVE_FARKAS_DERIVATION.md':'''# Frozen native Farkas derivation
For A y + B x {<=,>=,=} b, native lambda is >=0 on <= rows, <=0 on >= rows and unrestricted on equalities. Let a=A^T lambda, h(x)=lambda^T(b-Bx), and L(a)=sum a_j*lb_j for a_j>0 plus a_j*ub_j for a_j<0. Every required bound must be finite; free-variable coefficients must cancel exactly. Then feasibility implies L(a)<=h(x). The cut h(x)-L(a)>=0 is globally necessary. Native FarkasProof equals L(a)-lambda^T(rounded solver RHS). Reconstruct that quantity independently and compare; also require strict separation on the original unrounded source expression. The bound-completed stationarity is a - lower_multiplier + upper_multiplier=0, with lower=max(a,0), upper=max(-a,0); a need not itself be small.
All arithmetic for cut provenance uses rational values of stored IEEE doubles. Outward round the feasibility affine expression above its exact value over original x bounds. No clamp, global sign flip, or tiny coefficient deletion is allowed.
For minimization optimum, Pi<=0 on <=, Pi>=0 on >=, equality unrestricted. r=c-A^T Pi and native-bound support L(r) give theta>=Pi^T(b-Bx)+L(r)+objective_constant. Independently check reduced costs, bound support, source tightness and primal feasibility; round the affine lower bound down globally.
Source: [Gurobi linear constraint attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html). No verbatim solver documentation is reproduced here.
''',
    'PHASE1_FORMULATION.md':'''# Frozen auxiliary Phase-I formulation
For each <= row add -s_i, for >= add +s_i, and for = add -s_i+ + s_i-. All artificial variables are nonnegative and unbounded above. Original A, b, B, senses and native y bounds remain unchanged. Minimize sum w_i*s_i (or w_i*(s_i+ + s_i-)). w_i is a positive reciprocal power of two based on max(1,abs(original b_i), max abs A_i/B_i coefficient), independent of x. No artificial variable enters production recourse or a physical witness. Feasible original recourse admits zero artificial values. Exact auxiliary optimum zero is equivalent to original feasibility; numerical near-zero output additionally requires direct original primal validation.
''',
    'PHASE1_DUAL_CUT_DERIVATION.md':'''# Frozen Phase-I dual cut
Minimization Pi has mixed-sense optimal dual signs. Artificial reduced costs are w_i+Pi_i on <=, w_i-Pi_i on >=, and w_i+Pi_i / w_i-Pi_i for equality. They must be nonnegative exactly for their unbounded-above domains. Original y reduced costs are r=-A^T Pi, completed using existing finite native bounds only. Define phi(x)=Pi^T(b-Bx)+L(r). This is a global lower bound on the nonnegative auxiliary optimum. Any original-feasible x has auxiliary optimum zero, hence phi(x)<=0. The necessary separating cut is -phi(x)>=0, outward rounded above. Require terminal optimal auxiliary status, valid primal auxiliary point, independent exact bound-supported dual reconstruction, reduced-cost agreement, source objective tightness and separation >1e-8. Positive auxiliary objective alone is insufficient. Normalization changes dual magnitude and numerical conditioning, but not the zero optimum feasible set or this validity argument. No sweep of normalization is authorized.
'''}
    for name,body in docs.items():(OUT/name).write_text(body,encoding='utf8')
    dump('DERIVATION_FREEZE.json',dict(created_before_optimize=True,files=[dict(path=p,sha256=sha(OUT/p)) for p in ['PREREGISTRATION.json',*docs]]))

if __name__=='__main__':run()
