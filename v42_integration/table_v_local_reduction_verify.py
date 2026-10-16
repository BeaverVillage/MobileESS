"""Independent rational implication and complete-polytope projection replay."""
from collections import defaultdict
from fractions import Fraction
import numpy as np


def verify_bounds(source,target,proof):
    """Independent replay: original rows imply boxes; boxes imply deletions."""
    if source.fingerprint()!=proof['source_snapshot_sha'] or target.fingerprint()!=proof['target_snapshot_sha']:
        raise ValueError('BOUND_ABSORPTION_SOURCE_OR_TARGET_DRIFT')
    low=source.lower.copy();high=source.upper.copy();A=source.matrix
    for i in proof['singleton_rows']:
        a,b=A.indptr[i:i+2]
        if b-a!=1:raise ValueError('UNPROVED_SINGLETON_BOUND')
        j=int(A.indices[a]);coefficient=Fraction(float(A.data[a]));q=Fraction(float(source.rhs[i]))/coefficient
        value=float(q)
        if not np.isfinite(value) or abs(value)>=1e100 or Fraction(value)!=q:raise ValueError('INEXACT_SINGLETON_BOUND')
        sense=str(source.senses[i]);lower=sense in ('=','>') if coefficient>0 else sense in ('=','<')
        upper=sense in ('=','<') if coefficient>0 else sense in ('=','>')
        if lower:low[j]=max(low[j],value)
        if upper:high[j]=min(high[j],value)
        if low[j]>high[j]:raise ValueError('BOUND_ABSORPTION_INFEASIBLE_BOX')
    if not np.array_equal(low,target.lower) or not np.array_equal(high,target.upper):raise ValueError('UNPROVED_TIGHTENED_BOX')
    kept=np.asarray(proof['kept_rows'])
    if kept.ndim!=1 or len(set(map(int,kept)))!=len(kept) or any(not 0<=i<A.shape[0] for i in kept):
        raise ValueError('BOUND_ABSORPTION_ROW_AXIS')
    expected=A[kept].tocsr();actual=target.matrix
    if (expected.shape!=actual.shape or not np.array_equal(expected.indptr,actual.indptr)
            or not np.array_equal(expected.indices,actual.indices) or not np.array_equal(expected.data,actual.data)
            or not np.array_equal(source.rhs[kept],target.rhs)
            or not np.array_equal(source.vtypes,target.vtypes) or source.objectives!=target.objectives):
        raise ValueError('BOUND_ABSORPTION_RETAINED_MODEL_DRIFT')
    def coefficients(matrix,i):
        a,b=matrix.indptr[i:i+2]
        return {int(j):Fraction(float(c)) for j,c in zip(matrix.indices[a:b],matrix.data[a:b]) if c}
    def scale_between(left,right):
        if not left or set(left)!=set(right):raise ValueError('PARALLEL_ROW_SUPPORT_DRIFT')
        j=next(iter(left));scale=left[j]/right[j]
        if any(left[k]!=scale*right[k] for k in left):raise ValueError('PARALLEL_ROW_COEFFICIENT_DRIFT')
        return scale
    for t,i in enumerate(kept):
        if str(source.senses[i])==str(target.senses[t]):continue
        if str(target.senses[t])!='=' or i not in proof.get('opposing_rows',{}):raise ValueError('UNPROVED_OPPOSING_ROW_EQUALITY')
        j=proof['opposing_rows'][i]
        if not 0<=j<A.shape[0]:raise ValueError('OPPOSING_ROW_AXIS')
        scale=scale_between(coefficients(A,j),coefficients(A,i));other=str(source.senses[j])
        if scale<0:other={'<':'>','>':'<','=':'='}[other]
        if ({str(source.senses[i]),other}!={'<','>'}
                or Fraction(float(source.rhs[j]))!=scale*Fraction(float(source.rhs[i]))):
            raise ValueError('UNPROVED_OPPOSING_ROW_EQUALITY')
    retained=set(map(int,kept))
    for i in range(A.shape[0]):
        start,end=A.indptr[i:i+2];sums=[Fraction(0),Fraction(0)];finite=[True,True]
        for j,c in zip(A.indices[start:end],A.data[start:end]):
            c=Fraction(float(c));ends=(low[j],high[j]) if c>0 else (high[j],low[j])
            for k,bound in enumerate(ends):
                if np.isfinite(bound) and abs(bound)<1e100:sums[k]+=c*Fraction(float(bound))
                else:finite[k]=False
        rhs=Fraction(float(source.rhs[i]));sense=str(source.senses[i])
        implied=(finite[1] and sums[1]<=rhs if sense=='<' else finite[0] and sums[0]>=rhs if sense=='>'
                else all(finite) and sums[0]==sums[1]==rhs)
        if implied:continue
        t=int(proof['row_targets'][i])
        if not 0<=t<target.matrix.shape[0]:raise ValueError('REMOVED_ROW_NOT_EXACTLY_IMPLIED_BY_PROVED_BOX_OR_PARALLEL_ROW')
        scale=scale_between(coefficients(A,i),coefficients(target.matrix,t));other=str(target.senses[t]);q=scale*Fraction(float(target.rhs[t]))
        if scale<0:other={'<':'>','>':'<','=':'='}[other]
        if not (other in ('<','=') and q<=rhs if sense=='<' else other in ('>','=') and q>=rhs if sense=='>' else other=='=' and q==rhs):
            raise ValueError('PARALLEL_ROW_NOT_IMPLIED_BY_RETAINED_ROW')
    return dict(PASS=True,removed_rows_checked=A.shape[0]-len(kept),singleton_inferences_checked=len(proof['singleton_rows']),
        all_original_points_satisfy_new_boxes=True,all_removed_rows_implied_by_new_boxes=True,Native_calls=0)


def verify(source,coupling,result,units=None):
    """Verify universal forward/inverse, boxes, all rows, objectives and B.

    The producer's inferred relations are not trusted. Replay each inference
    against the original equations and current component boxes; then check
    every original row, including removed rows. No candidate point or optimizer
    can substitute for these symbolic checks.
    """
    n=source.matrix.shape[1];parent=np.arange(n);low=source.lower.copy();high=source.upper.copy();zero=set()
    proof=result['proof'];final=result['snapshot'];target=result.get('pre_bound_snapshot',final);mapping=np.asarray(result['mapping'])
    if (proof['source_snapshot_sha']!=source.fingerprint() or proof['target_snapshot_sha']!=final.fingerprint()
            or proof.get('zero_alias_target_snapshot_sha',proof['target_snapshot_sha'])!=target.fingerprint()
            or np.any(source.vtypes!='C') or np.any(target.vtypes!='C')):
        raise ValueError('LOCAL_PROJECTION_SOURCE_OR_TARGET_DRIFT')
    def representative(j):
        while parent[j]!=j:j=int(parent[j])
        return j
    def expression(matrix,row,coordinate):
        a,b=matrix.indptr[row:row+2];values=defaultdict(Fraction)
        for j,c in zip(matrix.indices[a:b],matrix.data[a:b]):
            k=coordinate(int(j))
            if k is not None:values[k]+=Fraction(float(c))
        return {j:c for j,c in values.items() if c}
    def inferred_coordinate(j):
        k=representative(j)
        return None if k in zero else k
    for step in proof['inference_steps']:
        kind=step['kind']
        if kind=='BOUND_ZERO':
            j=step['column']
            if not source.lower[j]==source.upper[j]==0:raise ValueError('UNPROVED_BOUND_ZERO')
            zero.add(j);continue
        i=step['row']
        if source.rhs[i]!=0:raise ValueError('NONZERO_RHS_ZERO_OR_ALIAS_INFERENCE')
        terms=expression(source.matrix,i,inferred_coordinate);sense=str(source.senses[i])
        if kind=='ROW_ALIAS':
            keep,drop=step['keep'],step['drop']
            if (sense!='=' or set(terms)!={keep,drop} or terms[keep]!=-terms[drop]
                    or representative(keep)!=keep or representative(drop)!=drop
                    or min(high[keep],high[drop])<max(low[keep],low[drop])):
                raise ValueError('UNPROVED_EXACT_VARIABLE_ALIAS')
            parent[drop]=keep;low[keep]=max(low[keep],low[drop]);high[keep]=min(high[keep],high[drop])
        elif kind=='ROW_ZERO':
            targets=set(step['columns'])
            nonnegative=all(low[j]>=0 if c>0 else high[j]<=0 for j,c in terms.items())
            nonpositive=all(high[j]<=0 if c>0 else low[j]>=0 for j,c in terms.items())
            valid=(sense=='=' and len(terms)==1) or (nonnegative and sense in ('=','<')) or (nonpositive and sense in ('=','>'))
            if not terms or targets!=set(terms) or not valid or any(not low[j]<=0<=high[j] for j in targets):
                raise ValueError('UNPROVED_EXACT_VARIABLE_ZERO')
            zero.update(targets)
        else:raise ValueError('UNKNOWN_LOCAL_IMPLICATION_STEP')
    reps=sorted({representative(j) for j in range(n)}-zero)
    position={j:k for k,j in enumerate(reps)}
    expected=np.asarray([-1 if representative(j) in zero else position[representative(j)] for j in range(n)])
    if mapping.shape!=(n,) or not np.array_equal(mapping,expected) or not np.array_equal(result['representatives'],reps):
        raise ValueError('UNPROVED_LOCAL_COLUMN_MAPPING')
    lows=np.full(len(reps),-np.inf);highs=np.full(len(reps),np.inf)
    for j,k in enumerate(mapping):
        if k<0:
            if not source.lower[j]<=0<=source.upper[j]:raise ValueError('LIFT_ZERO_OUTSIDE_ORIGINAL_BOX')
        else:lows[k]=max(lows[k],source.lower[j]);highs[k]=min(highs[k],source.upper[j])
    if not np.array_equal(lows,target.lower) or not np.array_equal(highs,target.upper):
        raise ValueError('EXACT_INTERSECTION_BOX_DRIFT')
    def projected_coordinate(j):return int(mapping[j]) if mapping[j]>=0 else None
    targets=np.asarray(result['row_targets']);kept=np.asarray(result['kept_rows'])
    if len(targets)!=source.matrix.shape[0] or len(kept)!=target.matrix.shape[0]:raise ValueError('LOCAL_ROW_MAPPING_AXIS')
    for i in range(source.matrix.shape[0]):
        lhs=expression(source.matrix,i,projected_coordinate);rhs=Fraction(float(source.rhs[i]));sense=str(source.senses[i]);t=int(targets[i])
        if t<0:
            if lhs or not (rhs==0 if sense=='=' else rhs>=0 if sense=='<' else rhs<=0):
                raise ValueError('REMOVED_ORIGINAL_LOCAL_ROW_NOT_TAUTOLOGY')
            continue
        if not 0<=t<target.matrix.shape[0]:raise ValueError('INVALID_RETAINED_ROW_TARGET')
        scale=Fraction(result['row_multipliers'][i]);other=expression(target.matrix,t,lambda j:j)
        expected_sense=str(target.senses[t]) if scale>0 else {'<':'>','>':'<','=':'='}[str(target.senses[t])]
        if (not scale or lhs!={j:scale*c for j,c in other.items()} or sense!=expected_sense
                or rhs!=scale*Fraction(float(target.rhs[t]))):raise ValueError('ORIGINAL_LOCAL_ROW_LIFT_NOT_EXACT')
    for t,i in enumerate(kept):
        if targets[i]!=t or Fraction(result['row_multipliers'][i])!=1:raise ValueError('RETAINED_ORIGINAL_ROW_NOT_IDENTICAL')
    if coupling.shape[0]!=result['B'].shape[0] or result['B'].shape[1]!=len(reps):raise ValueError('COUPLING_AXIS_DRIFT')
    for i in range(coupling.shape[0]):
        if expression(coupling,i,projected_coordinate)!=expression(result['B'],i,lambda j:j):
            raise ValueError('GLOBAL_COUPLING_LIFT_NOT_EXACT')
    if len(source.objectives)!=len(target.objectives):raise ValueError('OBJECTIVE_COUNT_DRIFT')
    for before,after in zip(source.objectives,target.objectives):
        coefficients=defaultdict(Fraction)
        for j,c in before.coefficients().items():
            if mapping[j]>=0:coefficients[int(mapping[j])]+=c
        if (before.name!=after.name or before.constant!=after.constant
                or {j:c for j,c in coefficients.items() if c}!=after.coefficients()):raise ValueError('LOCAL_OBJECTIVE_LIFT_NOT_EXACT')
    if units is not None:
        if len(units)!=len(result['units']):raise ValueError('LOCAL_DESCRIPTOR_COUNT_DRIFT')
        def decode(e):
            if e[0]=='c':return Fraction(float(e[1])),{}
            if e[0]=='v':return Fraction(0),{int(e[1]):Fraction(1)}
            if e[0]!='e':raise ValueError('UNKNOWN_PRIMITIVE_EXPRESSION')
            values=defaultdict(Fraction)
            for j,c in zip(e[2],e[3]):values[int(j)]+=Fraction(float(c))
            return Fraction(float(e[1])),{j:c for j,c in values.items() if c}
        for original,mapped in zip(units,result['units']):
            if {k:v for k,v in original.items() if k!='v'}!={k:v for k,v in mapped.items() if k!='v'}:
                raise ValueError('LOCAL_UID_AUTHORITY_DESCRIPTOR_DRIFT')
            if set(original['v'])!=set(mapped['v']):raise ValueError('LOCAL_PRIMITIVE_FAMILY_DRIFT')
            for family,items in original['v'].items():
                if set(items)!=set(mapped['v'][family]):raise ValueError('LOCAL_PRIMITIVE_KEY_DRIFT')
                for key,e in items.items():
                    constant,values=decode(e);projected=defaultdict(Fraction)
                    for j,c in values.items():
                        if mapping[j]>=0:projected[int(mapping[j])]+=c
                    if (constant,{j:c for j,c in projected.items() if c})!=decode(mapped['v'][family][key]):
                        raise ValueError('LOCAL_PRIMITIVE_LIFT_NOT_EXACT')
    bounds=result.get('bound_absorption')
    if bounds is not None:bound_verification=verify_bounds(target,final,bounds)
    else:
        if final.fingerprint()!=target.fingerprint():raise ValueError('MISSING_BOUND_ABSORPTION_PROOF')
        bound_verification=None
    return dict(PASS=True,scope='UNIVERSAL_COMPLETE_CONTINUOUS_LOCAL_POLYTOPE',
        exact_bound_absorption=bound_verification,
        inference_steps_replayed=len(proof['inference_steps']),original_rows_checked=source.matrix.shape[0],
        original_columns_checked=n,all_coupling_rows_checked=coupling.shape[0],
        forward_projection=True,inverse_original_point_lift=True,objective_preserved=True,
        original_boxes_preserved=True,all_removed_rows_exactly_implied=True,
        complete_domain_coverage=True,finite_column_pool_used=False,
        original_UID_primitive_interfaces_verified=units is not None,
        Global_LB_issued=False,actual_native_pricing_certificate_required=True,
        original_integer_FULL_changed=False,Native_calls=0)
