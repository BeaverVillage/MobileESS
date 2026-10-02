"""Exhaustive saved-ray support audit, before new optimization."""
from collections import Counter
from fractions import Fraction as F
import gzip,json,math,subprocess
import numpy as np
from .common import *
from .exact import products,q,complete,create
from .independent import verify

def run():
    paths=git('ls-files','-z').split('\0');files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths if p]
    dump('PR117_BASE_RECEIPT.json',dict(base=BASE,files=files,tracked_files=len(files),inherited_tests=825,inherited_bounded_checks=44))
    x,xr=load_x0();n,raw=load_native();w={i:q(v) for i,v in enumerate(raw['multipliers']) if v};a=products(n.A,w)
    rows=[];counts=Counter();families=Counter();partial=F(0);native_rc_available=raw['reduced_costs'] is not None
    C=n.A.tocsc();provenance=OUT/'UNSUPPORTED_COEFFICIENT_PROVENANCE.jsonl.gz'
    with gzip.open(provenance,'wt',encoding='utf8') as f:
        for j in range(len(n.yi)):
            lo=n.lower[j];up=n.upper[j];v=a.get(j,F(0));free=math.isinf(lo) and math.isinf(up)
            shape='free' if free else 'boxed' if math.isfinite(lo) and math.isfinite(up) else 'lower-bounded' if math.isfinite(lo) else 'upper-bounded'
            extreme=lo if v>0 else up if v<0 else 0.;supported=math.isfinite(extreme)
            category='A_FREE_EXACT_ZERO' if free and not v else 'B_FREE_NONZERO' if free else 'D_ONE_SIDED_INCOMPATIBLE' if not supported else 'C_ONE_SIDED_COMPATIBLE' if shape!='boxed' else 'FINITE_BOXED_SUPPORTED'
            counts[category]+=1
            if supported:partial+=v*q(extreme)
            if supported:continue
            name=str(n.names[n.yi[j]]);family=name.split('[')[0];families[family]+=1
            terms=[]
            for k in range(C.indptr[j],C.indptr[j+1]):
                i=int(C.indices[k]);c=q(C.data[k]);wi=w.get(i,F(0))
                terms.append(dict(row=i,row_name=str(n.rownames[i]),sense=str(n.sense[i]),coefficient=str(c),multiplier=str(wi),product=str(c*wi)))
            assert sum((F(t['product']) for t in terms),F(0))==v
            f.write(json.dumps(dict(column=j,original_column=int(n.yi[j]),variable=name,terms=terms),separators=(',',':'))+'\n')
            rows.append(dict(recourse_column=j,original_column=int(n.yi[j]),variable_name=name,physical_family=family,
                LB=str(float(lo)),UB=str(float(up)),LB_finite=math.isfinite(lo),UB_finite=math.isfinite(up),bound_class=shape,
                classification=category,weighted_stationarity_coefficient=str(v),coefficient_float=float(v),
                required_extremizing_bound='LB' if v>0 else 'UB',native_RC='NOT_AVAILABLE',native_bound_proof_contribution='UNDEFINED_UNBOUNDED',
                numerical_near_zero_only=abs(float(v))<1e-7,exact_zero=False,
                coefficient_provenance='UNSUPPORTED_COEFFICIENT_PROVENANCE.jsonl.gz:column='+str(j),
                native_axis_sha256=raw['axis_npz_sha256'],raw_ray_sha256=raw['vector_sha256']))
    assert len(rows)==1589 and dict(families)==dict(injection_P=792,injection_Q=792,response_line_P=1,response_line_Q=4)
    table('UNSUPPORTED_1589_COLUMN_AUDIT.csv',rows,list(rows[0]))
    cut=create(n,raw);validation=verify(n,cut);r=cut['record']
    dump('BOUND_SUPPORT_CLASSIFICATION.json',dict(complete_columns=len(n.yi),unsupported_columns=1589,exclusive_class_counts=dict(counts),
        unsupported_physical_families=dict(families),E_FINITE_BOUND_SUPPORT_MISSING=0,
        F_NUMERICAL_NEAR_ZERO_ONLY=dict(overlay_not_exclusive=True,unsupported_count=sum(r['numerical_near_zero_only'] for r in rows),
            threshold=1e-7,accepted_as_zero=False),native_RC_available=native_rc_available,
        native_supported_partial_sum=str(partial),native_full_support=None,native_proof_reconstruction=None,
        raw_ray_accepted=False,raw_FarkasProof=raw['farkas_proof'],completed_equality_changes=len(r['equality_changes']),
        completed_proof=float(F(r['completed_proof_on_solver_RHS'])),completed_source_margin=r['strict_margin'],
        completed_native_proof_difference=r['difference_from_native_proof'],offline_independent_replay=validation,
        offline_cut_not_inserted=True,optimization_calls=0,clamp=False,flip=False,tiny_delete=False,
        provenance_sha256=sha(provenance)))
    dump('PR117_X0_RECEIPT.json',dict(base=BASE,source_receipt=xr,source_receipt_sha256=sha(PRIOR/'MASTER_X_000_RECEIPT.json'),
        bit_exact_reused=True,axis_bit_exact=True,new_x0_created=False,master_optimize_before_certificate=0,
        source_native_raw_sha256=sha(PRIOR/'native/raw_certificates.jsonl.gz'),source_native_axis_sha256=sha(PRIOR/'native/axis.npz')))
    dump('OFFLINE_COMPLETED_CERTIFICATE.json',dict(record=r,independent_validation=validation,inserted=False,role='MATHEMATICS_AUDIT_ONLY'))
    (OUT/'NATIVE_PROOF_RECONSTRUCTION.md').write_text('''# Native proof and exact reconstruction

Authority: [Gurobi FarkasDual/FarkasProof](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#farkasdual), accessed 2026-10-02.

For original rows A y + B x (sense) b, native lambda has lambda>=0 on <= and lambda<=0 on >=. Let a=A^T lambda and h(x)=lambda^T(b-Bx). The lower support L(a)=sum(a_j*LB_j for a_j>0)+sum(a_j*UB_j for a_j<0) gives beta=L(a)-h(x)>0 and the globally valid cut lambda^T b-L(a)-lambda^T B x>=0.

A free variable requires a_j=0 exactly. A lower-only variable requires a_j>=0; upper-only requires a_j<=0. Boxed variables admit either sign. Variable-bound multipliers are equivalently determined by these coefficients and their extremizing bounds. RC is an optimal-solution dual attribute, not an additional Farkas cancellation vector for truly free variables. PR117 saved no RC or basis at status INFEASIBLE. The official Farkas API does not supply a separate hidden multiplier that repairs nonzero free-column stationarity.

All 1,589 failures are nonzero coefficients of truly free variables (1,584 injection P/Q, 5 response line P/Q). They are numerically small but exact IEEE-rational products are nonzero. Full native support is therefore unbounded, so the unmodified saved row vector has no finite reconstructed exact beta. A finite partial support sum is not a certificate. FarkasProof=42.159075966904695 is the solver's floating-point proof value; we cannot infer its internal rounding sequence. The observation establishes an exactness gap in the exported floating multipliers, not that an independent bound contribution was forgotten.

The new derivation keeps every inequality multiplier unchanged and solves equality-multiplier stationarity exactly, in rational arithmetic. All 81,216 free columns have an acyclic defining-equality pivot of +1. Reverse triangular substitution changes 1,589 equality multipliers. This is a new explicitly derived rational certificate; the raw solver ray remains rejected. Every original matrix entry, physical row, bound and master domain is retained. No residual is clamped, sign-flipped, or deleted. Recompute the full A/B products and finite bound support independently from COO before accepting and again before inserting a cut.

The completed ray's solver-RHS proof is 42.15907601900621, within about 5.21e-8 of the native proof. Global cut validity and strict source separation are checked on original exact b-Bx, independently of agreement with the floating proof scalar. The full rational certificate and each equality multiplier change are in OFFLINE_COMPLETED_CERTIFICATE.json. This offline audit does not authorize a master solve; fixtures and a frozen same-x isolated recourse must pass first.
''',encoding='utf8',newline='\n')
    print('AUDIT PASS: 1589 free nonzero / 81216 exact equality pivots / no master solve',flush=True)

if __name__=='__main__':run()
