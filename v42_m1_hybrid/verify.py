"""Independent exact bounds for the May01 fast-hybrid research.

No pricing producer, Native objective, RMP objective or closure flag is a proof.
The assembled signed dual is checked against the unchanged original CSR and
finite box.  This is a valid Lagrangian/LP bound even when pricing times out;
it does not certify completion of column generation or an integer pricing solve.
"""
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
from scipy import sparse

from v42_m1_research.check_lb import check_rational_dual_certificate

ROOT=Path(__file__).resolve().parents[1]
BASE_HEAD='6122331841e22562d23eb054c4168b5130566f3f'
PREVIOUS='docs/v42_m1_joint_gap_research/'
UNIT_FAMILIES={'route_flow','node_activity','charge_mode','SOC','Pch','Pdis','Q'}
M_RESEARCH_GAP=F(1,20)
A_GAP=F(1,200)


def _same(a,b):
    a,b=np.asarray(a),np.asarray(b)
    return a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()


def _matrix_same(a,b):
    a,b=a.tocsr(),b.tocsr()
    return a.shape==b.shape and all(_same(getattr(a,k),getattr(b,k)) for k in ('indptr','indices','data'))


def _axis(value,size,label):
    a=np.asarray(value)
    if (a.ndim!=1 or a.dtype.kind not in 'iu' or len(set(map(int,a)))!=len(a)
            or np.any(a<0) or np.any(a>=size)):
        raise ValueError('HYBRID_ORIGINAL_AXIS_DRIFT:'+label)
    return a.astype(np.int64,copy=False)


def _owner(name):
    name=str(name)
    if '[' not in name:return None
    family,axis=name.split('[',1)
    if family in UNIT_FAMILIES:return axis[:-1].split(',')[0]
    return None


def verify_decomposition(case,decomposition):
    """Reconstruct every local/mixed row independently from original incidence."""
    if getattr(decomposition,'case_sha',case.case_sha)!=case.case_sha:
        raise ValueError('HYBRID_DECOMPOSITION_CASE_MISMATCH')
    A,d=case.A.tocsr(),case.d
    owners=[_owner(n) for n in d['names']]
    units=sorted({u for u in owners if u is not None})
    if len(units)!=4 or sorted(decomposition.units)!=units:
        raise ValueError('HYBRID_FOUR_ORIGINAL_UNITS_REQUIRED')
    expected_columns={u:np.array([j for j,v in enumerate(owners) if v==u],dtype=np.int64) for u in units}
    nonunit_columns=np.array([j for j,v in enumerate(owners) if v is None],dtype=np.int64)
    expected_rows={u:[] for u in units};nonunit_rows=[];mixed=[]
    for i in range(A.shape[0]):
        a,b=A.indptr[i:i+2]
        row_owners={owners[int(j)] for j,w in zip(A.indices[a:b],A.data[a:b]) if w!=0.}
        if len(row_owners)==1 and None not in row_owners:
            expected_rows[next(iter(row_owners))].append(i)
        elif not row_owners or row_owners=={None}:nonunit_rows.append(i)
        else:mixed.append(i)
    actual_mixed=_axis(decomposition.coupling_rows,A.shape[0],'coupling_rows')
    if not np.array_equal(actual_mixed,np.array(mixed,dtype=np.int64)):
        raise ValueError('HYBRID_MIXED_ROW_PARTITION_DRIFT')
    blocks={**decomposition.units,'NONUNIT':decomposition.nonunit_block}
    oracle_rows={**expected_rows,'NONUNIT':nonunit_rows}
    oracle_columns={**expected_columns,'NONUNIT':nonunit_columns}
    details={}
    for unit,block in blocks.items():
        rows=_axis(block.original_rows,A.shape[0],unit+'_rows')
        cols=_axis(block.original_columns,A.shape[1],unit+'_columns')
        if (not np.array_equal(rows,np.array(oracle_rows[unit],dtype=np.int64)) or
                not np.array_equal(cols,oracle_columns[unit])):
            raise ValueError('HYBRID_COMPLETE_96_SLOT_BLOCK_PARTITION_DRIFT:'+unit)
        expected=A[rows][:,cols].tocsr()
        if not _matrix_same(expected,block.A):
            raise ValueError('HYBRID_ORIGINAL_BLOCK_CSR_COEFFICIENT_DRIFT:'+unit)
        for key in ('names','lower','upper','types','objective'):
            if not _same(d[key][cols],block.d[key]):
                raise ValueError('HYBRID_ORIGINAL_BLOCK_VARIABLE_DRIFT:'+unit+':'+key)
        for key in ('rhs','sense','row_names'):
            if not _same(d[key][rows],block.d[key]):
                raise ValueError('HYBRID_ORIGINAL_BLOCK_ROW_DRIFT:'+unit+':'+key)
        if 'constant' in block.d and F(float(np.asarray(block.d['constant']).item()))!=0:
            raise ValueError('HYBRID_BLOCK_OBJECTIVE_CONSTANT_DOUBLE_COUNT')
        details[unit]=dict(rows=len(rows),columns=len(cols),nnz=expected.nnz,
            original_all_time_physics_and_variable_box_preserved=True)
    if hasattr(decomposition,'nonunit_columns') and not np.array_equal(
            _axis(decomposition.nonunit_columns,A.shape[1],'nonunit_columns'),nonunit_columns):
        raise ValueError('HYBRID_NONUNIT_COLUMN_PARTITION_DRIFT')
    return dict(PASS=True,case_sha=case.case_sha,blocks=details,mixed_coupling_rows=len(mixed),
        original_rows=A.shape[0],original_columns=A.shape[1],
        all_original_rows_exactly_once=True,all_original_columns_exactly_once=True,
        every_original_96_slot_integer_plan_is_in_decomposed_domain=True,
        original_coupling_rows_are_relaxed_only_via_signed_multipliers=True)


def verify_global_lagrangian_bound(case,decomposition,coupling_dual,unit_duals,*,nonunit_dual=None):
    """Check exact global weak duality, including nonunit grid and finite boxes.

    Reassembling y avoids any rounding of c-B.T*lambda used in a Native price
    objective.  The exact residual correction covers every original column.
    No requirement of LP/MIP optimal status is needed for this lower bound.
    """
    begin=perf_counter();inclusion=verify_decomposition(case,decomposition)
    if set(unit_duals)!=set(decomposition.units):raise ValueError('HYBRID_LOCAL_DUAL_UNIT_COVER_INCOMPLETE')
    y={}
    def assign(rows,dual,label):
        rows=np.asarray(rows,dtype=np.int64)
        if isinstance(dual,dict):
            local={}
            for key,value in dual.items():
                j=int(key)
                if not 0<=j<len(rows) or str(j)!=str(key):
                    raise ValueError('HYBRID_RATIONAL_LOCAL_DUAL_AXIS_DRIFT:'+label)
                local[j]=F(value)
        else:
            value=np.asarray(dual,dtype=np.float64)
            if value.shape!=(len(rows),) or not np.isfinite(value).all():
                raise ValueError('HYBRID_LOCAL_DUAL_AXIS_OR_FINITE_DRIFT:'+label)
            local={int(j):F(float(value[j])) for j in np.flatnonzero(value)}
        for j,value in local.items():
            if value:y[str(int(rows[j]))]=str(value)
    assign(decomposition.coupling_rows,coupling_dual,'COUPLING')
    for unit,block in decomposition.units.items():assign(block.original_rows,unit_duals[unit],unit)
    rows=decomposition.nonunit_block.original_rows
    if nonunit_dual is None and len(rows):raise ValueError('HYBRID_RETAINED_NONUNIT_GRID_DUAL_MISSING')
    assign(rows,np.zeros(0) if nonunit_dual is None else nonunit_dual,'NONUNIT')
    certificate=check_rational_dual_certificate(case.A,case.d,y,case_sha=case.case_sha)
    canonical='\n'.join(f'{i}:{y[str(i)]}' for i in sorted(map(int,y))).encode('ascii')
    return dict(PASS=True,case_sha=case.case_sha,scope='FULL_ORIGINAL_C3A_SIGNED_LAGRANGIAN_LP_DUAL',
        independent_decomposition=inclusion,independent_exact_certificate=certificate,
        exact_Global_LB=certificate['exact_bound'],independently_certified_Global_LB=certificate['independently_certified_LB'],
        assembled_original_dual_sha256=hashlib.sha256(canonical).hexdigest(),
        canonical_sparse_original_row_rational_dual=y,
        theorem='ObjCon+b*y+min_original_finite_box((c-A.T*y)*x) <= every original integer objective',
        native_rounded_price_objectives_used_as_proof=False,restricted_master_objective_used_as_Global_LB=False,
        Native_MIP_ObjBound_used_as_exact_Global_LB=False,full_pricing_closure_certified=False,
        structural_integer_hull_strengthening_certified=False,Native_optimize_calls=0,
        checker_wall_seconds=perf_counter()-begin)


def target_thresholds(lb_exact,ub_exact):
    lb,ub=F(lb_exact),F(ub_exact)
    if not 0<=lb<=ub or ub<=0:raise ValueError('HYBRID_EXACT_LB_UB_ORDER_INVALID')
    gap=(ub-lb)/ub;required_lb=(1-M_RESEARCH_GAP)*ub;required_ub=lb/(1-M_RESEARCH_GAP)
    return dict(exact_Global_LB=str(lb),exact_Global_UB=str(ub),exact_Global_Gap=str(gap),
        Global_Gap_percent=float(100*gap),M1_M2_research_target_exact=str(M_RESEARCH_GAP),
        A1_A2_target_exact=str(A_GAP),required_LB_at_current_UB_exact=str(required_lb),
        required_LB_at_current_UB=float(required_lb),required_UB_at_current_LB_exact=str(required_ub),
        required_UB_at_current_LB=float(required_ub),required_LB_increase_exact=str(required_lb-lb),
        required_UB_decrease_exact=str(ub-required_ub),M1_P1_RESEARCH_GAP_5_PERCENT_CERTIFIED=gap<=M_RESEARCH_GAP,
        historical_0p5_percent_gap_certified=gap<=A_GAP,M1_ACCEPTED=False,P2_certificate=None)


def _committed(path):
    if ROOT.resolve().drive.upper()!='D:':raise ValueError('D_DRIVE_REQUIRED')
    return subprocess.check_output(['git','show',BASE_HEAD+':'+path],cwd=ROOT)


def phase0(case):
    """Independently check exact thresholds and the same-case strict baseline.

    Reuse of the previous completed independent LB certificate is explicit;
    this is not a new pricing certificate or a replay of its expensive products.
    """
    begin=perf_counter();receipt_raw=_committed(PREVIOUS+'JOINT_LB_UB_GAP.json')
    prior=json.loads(receipt_raw);identity=json.loads(_committed(PREVIOUS+'SCIENTIFIC_MODEL_IDENTITY.json'))
    if prior.get('PASS') is not True or prior['case_sha']!=case.case_sha or identity['case_sha']!=case.case_sha:
        raise ValueError('HYBRID_COMPLETED_BASELINE_CASE_MISMATCH')
    out='docs/v42_m1_ultracompact_exact_20261006/'
    raw_A=_committed(out+'C3A_A.npz');raw_d=_committed(out+'C3A_DATA.npz')
    if hashlib.sha256(raw_A).hexdigest()!=identity['C3A_matrix_sha256'] or hashlib.sha256(raw_d).hexdigest()!=identity['C3A_data_sha256']:
        raise ValueError('HYBRID_COMPLETED_SOURCE_HASH_DRIFT')
    expected_A=sparse.load_npz(io.BytesIO(raw_A))
    with np.load(io.BytesIO(raw_d),allow_pickle=False) as z:expected_d={k:z[k].copy() for k in z.files}
    if not _matrix_same(case.A,expected_A) or any(not _same(case.d[k],v) for k,v in expected_d.items()):
        raise ValueError('HYBRID_BASELINE_ORIGINAL_SCIENTIFIC_MATRIX_OR_DATA_DRIFT')
    # The original full model is external frozen input, so locate its existing
    # verified D copy from the immutable completed identity; never copy C here.
    copies={Path(r['original_path']).name:r for r in identity['D_frozen_copies']}
    for name,key in (('FULL_A.npz','original_matrix_sha256'),('FULL_DATA.npz','original_data_sha256')):
        source=Path(copies[name]['local_path']).resolve()
        if source.drive.upper()!='D:' or hashlib.sha256(source.read_bytes()).hexdigest()!=identity[key]:
            raise ValueError('HYBRID_ORIGINAL_FROZEN_D_COPY_IDENTITY_DRIFT:'+name)
        if name=='FULL_A.npz':
            if not _matrix_same(case.original_A,sparse.load_npz(source)):
                raise ValueError('HYBRID_ORIGINAL_FULL_CSR_DRIFT')
        else:
            with np.load(source,allow_pickle=False) as z:
                if any(not _same(case.original_d[k],z[k]) for k in z.files):
                    raise ValueError('HYBRID_ORIGINAL_FULL_DATA_DRIFT')
    packet=_committed(PREVIOUS+'FINAL_STRICT_ADMITTED_UB_POINT.npz')
    with np.load(io.BytesIO(packet),allow_pickle=False) as z:
        if z.files!=['point']:raise ValueError('HYBRID_STRICT_BASELINE_PACKET_DRIFT')
        point=z['point'].copy()
    if point.shape!=(case.A.shape[1],) or not np.isfinite(point).all():raise ValueError('HYBRID_STRICT_BASELINE_POINT_AXIS_DRIFT')
    prefix='docs/v42_m1_supercompact_exact_20261006/'
    with np.load(io.BytesIO(_committed(prefix+'C1_DATA.npz')),allow_pickle=False) as z:n=len(z['names'])
    with np.load(io.BytesIO(_committed(prefix+'C2_RETAINED_AXES.npz')),allow_pickle=False) as z:columns=z['columns'].copy()
    aliases=json.loads(_committed(prefix+'C2_ELIMINATION_CERTIFICATES.json'))
    transported=np.zeros(n);transported[columns]=point;defined=set(map(int,columns))
    for row in reversed(aliases):
        j=int(row['column'])
        if j in defined:raise ValueError('HYBRID_ORIGINAL_ALIAS_DUPLICATE')
        transported[j]=row['constant']
        for key,w in row['terms'].items():
            k=int(key)
            if k not in defined or w!=1.:raise ValueError('HYBRID_ORIGINAL_ALIAS_UNPROVED')
            transported[j]+=w*transported[k]
        defined.add(j)
    if len(defined)!=n:raise ValueError('HYBRID_ORIGINAL_ALIAS_INCOMPLETE')
    original_point=transported[:len(case.original_d['names'])]
    if not _same(original_point,case.lift(point)):
        raise ValueError('HYBRID_ORIGINAL_LIFT_SOURCE_DRIFT')
    for d,x,label in ((case.d,point,'C3A'),(case.original_d,original_point,'ORIGINAL')):
        v=x[d['types']!='C'];b=x[d['types']=='B']
        if not np.all(v==np.rint(v)) or not np.all((b==0.)|(b==1.)):
            raise ValueError('HYBRID_STRICT_BASELINE_INTEGER_PATTERN_DRIFT:'+label)
    objective=F(float(case.d['constant']))+sum((F(float(case.d['objective'][j]))*F(float(point[j]))
        for j in np.flatnonzero(case.d['objective'])),F(0))
    if objective!=F(prior['Global_UB_exact']):raise ValueError('HYBRID_BASELINE_EXACT_OBJECTIVE_DRIFT')
    targets=target_thresholds(prior['Global_LB_exact'],prior['Global_UB_exact'])
    if F(prior['certified_Global_Gap_exact'])!=F(targets['exact_Global_Gap']):
        raise ValueError('HYBRID_PRIOR_EXACT_GAP_ARITHMETIC_DRIFT')
    return dict(PASS=True,case_sha=case.case_sha,completed_baseline_HEAD=BASE_HEAD,**targets,
        baseline_packet_sha256=hashlib.sha256(packet).hexdigest(),baseline_point_sha256=hashlib.sha256(point.tobytes()).hexdigest(),
        prior_independent_bound_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
        baseline_original_C3A_and_FULL_CSR_and_all_data_bit_identity=True,baseline_raw_original_integer_pattern_exact=True,
        baseline_LB_admission_scope='PRESERVED_COMPLETED_INDEPENDENT_CERTIFICATE_AT_SAME_EXACT_CASE_HASH',
        expensive_prior_LB_product_certificate_recomputed=False,
        historical_reports_modified=False,new_global_bound_or_pricing_closure_claim=False,
        Native_optimize_calls=0,checker_wall_seconds=perf_counter()-begin)


def verify_full_pricing_closure(case_sha,unit_certificates,*,expected_units):
    """Require checked complete-domain reduced-cost bounds for every block.

    Metadata-only dictionaries, restricted catalogs and Native statuses cannot
    serve as the certificate objects.  DP proof format is deliberately absent
    until its original continuous P/Q/SOC domain inclusion theorem exists.
    """
    raise ValueError('HYBRID_FULL_PRICING_CLOSURE_NOT_IMPLEMENTED_OR_PROVEN; RMP_NOT_GLOBAL')


def _rational_axis_dual(value,size,senses,label):
    if isinstance(value,dict):
        result={}
        for key,coefficient in value.items():
            i=int(key)
            if not 0<=i<size or str(i)!=str(key):raise ValueError('HYBRID_RATIONAL_DUAL_AXIS_DRIFT:'+label)
            result[i]=F(coefficient)
    else:
        a=np.asarray(value,dtype=np.float64)
        if a.shape!=(size,) or not np.isfinite(a).all():raise ValueError('HYBRID_DUAL_AXIS_OR_FINITE_DRIFT:'+label)
        result={int(i):F(float(a[i])) for i in np.flatnonzero(a)}
    for i,q in result.items():
        s=str(senses[i])
        if s not in {'<','>','='} or s=='<' and q>0 or s=='>' and q<0:
            raise ValueError('INVALID_DUAL_ROW_SIGN:'+label)
    return {i:q for i,q in result.items() if q}


def verify_rmp_pricing_lower_bounds(case,decomposition,full_rmp_dual,unit_duals,convexity_duals):
    """Exact complete-domain LP pricing LB proves missing-column nonnegativity.

    For each original unit F_u, LP weak duality supplies beta_u <= min_Fu
    (c_u-B_u.T*lambda)x.  Thus beta_u-eta_u>=0 proves all omitted original
    unit trajectories have nonnegative reduced cost at these exact prices.
    A negative lower bound is inconclusive, not proof of a negative column.
    This does not certify RMP primal optimality or promote its native objective.
    """
    begin=perf_counter();inclusion=verify_decomposition(case,decomposition)
    units=set(decomposition.units)
    if set(unit_duals)!=units or set(convexity_duals)!=units:
        raise ValueError('HYBRID_PRICING_FOUR_UNIT_CERTIFICATE_COVER_INCOMPLETE')
    if isinstance(full_rmp_dual,dict) and 'multipliers' in full_rmp_dual:
        if full_rmp_dual.get('case_sha')!=case.case_sha:raise ValueError('HYBRID_RMP_PRICE_CASE_MISMATCH')
        full_rmp_dual=full_rmp_dual['multipliers']
    A,d=case.A.tocsr(),case.d
    lam=_rational_axis_dual(full_rmp_dual,A.shape[0],d['sense'],'RMP_ORIGINAL_ROWS')
    allowed=set(map(int,decomposition.coupling_rows))|set(map(int,decomposition.nonunit_block.original_rows))
    if not set(lam)<=allowed:raise ValueError('HYBRID_RMP_PRICE_ROW_IS_LOCAL_UNIT_PHYSICS')
    canonical='\n'.join(f'{i}:{lam[i]}' for i in sorted(lam)).encode('ascii')
    checks={}
    for unit,block in decomposition.units.items():
        local_A=block.A.tocsr()
        cols=np.asarray(block.original_columns,dtype=np.int64)
        local={int(j):k for k,j in enumerate(cols)}
        pi=_rational_axis_dual(unit_duals[unit],local_A.shape[0],block.d['sense'],unit)
        price=[F(float(d['objective'][j])) for j in cols]
        for row,q in lam.items():
            a,b=A.indptr[row:row+2]
            for j,w in zip(A.indices[a:b],A.data[a:b]):
                if int(j) in local:price[local[int(j)]]-=q*F(float(w))
        rhs=F(0);products={}
        for row,q in pi.items():
            rhs+=q*F(float(block.d['rhs'][row]))
            a,b=local_A.indptr[row:row+2]
            for j,w in zip(local_A.indices[a:b],local_A.data[a:b]):
                j=int(j);products[j]=products.get(j,F(0))+q*F(float(w))
        correction=F(0)
        for j,c in enumerate(price):
            lo,hi=float(block.d['lower'][j]),float(block.d['upper'][j])
            if not np.isfinite(lo) or not np.isfinite(hi) or lo>hi:
                raise ValueError('HYBRID_PRICING_REQUIRES_ORIGINAL_FINITE_NONEMPTY_BOX')
            residual=c-products.get(j,F(0))
            correction+=residual*F(lo if residual>0 else hi)
        beta=rhs+correction;eta=F(convexity_duals[unit]);rc=beta-eta
        checks[unit]=dict(PASS=True,exact_complete_domain_price_LB=str(beta),
            exact_convexity_dual=str(eta),exact_missing_column_reduced_cost_LB=str(rc),
            every_original_integer_unit_trajectory_in_LP_domain=True,
            missing_columns_nonnegative_reduced_cost_certified=rc>=0,
            status='CERTIFIED_NONNEGATIVE_MISSING_COLUMN_REDUCED_COST' if rc>=0 else 'NOT_PROVEN_NEGATIVE_LOWER_BOUND_IS_INCONCLUSIVE',
            exact_rhs_dual_part=str(rhs),exact_finite_box_residual_part=str(correction),
            Native_optimize_calls=0,Native_MIP_status_or_ObjBound_used=False)
    closure=all(c['missing_columns_nonnegative_reduced_cost_certified'] for c in checks.values())
    return dict(PASS=True,case_sha=case.case_sha,status='ALL_ORIGINAL_UNIT_MISSING_COLUMN_CONSTRAINTS_CERTIFIED' if closure else 'FULL_PRICING_CLOSURE_NOT_PROVEN',
        independent_decomposition=inclusion,unit_certificates=checks,
        full_unit_missing_column_pricing_closure_certified=closure,
        original_RMP_row_rational_dual_sha256=hashlib.sha256(canonical).hexdigest(),
        full_original_continuous_PQ_SOC_route_box_preserved=True,
        RMP_primal_optimality_or_native_objective_certified=False,
        restricted_RMP_native_objective_used_as_Global_LB=False,
        Global_LB_requires_separate_original_signed_dual_certificate=True,
        TIME_LIMIT_is_not_itself_a_closure_proof=True,Native_optimize_calls=0,
        checker_wall_seconds=perf_counter()-begin)
