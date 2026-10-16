"""Independent rational implication and complete-polytope projection replay."""
from collections import defaultdict
from fractions import Fraction
import numpy as np


def verify(source,coupling,result,units=None):
    """Verify universal forward/inverse, boxes, all rows, objectives and B.

    The producer's inferred relations are not trusted. Replay each inference
    against the original equations and current component boxes; then check
    every original row, including removed rows. No candidate point or optimizer
    can substitute for these symbolic checks.
    """
    n=source.matrix.shape[1];parent=np.arange(n);low=source.lower.copy();high=source.upper.copy();zero=set()
    proof=result['proof'];target=result['snapshot'];mapping=np.asarray(result['mapping'])
    if (proof['source_snapshot_sha']!=source.fingerprint() or proof['target_snapshot_sha']!=target.fingerprint()
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
    return dict(PASS=True,scope='UNIVERSAL_COMPLETE_CONTINUOUS_LOCAL_POLYTOPE',
        inference_steps_replayed=len(proof['inference_steps']),original_rows_checked=source.matrix.shape[0],
        original_columns_checked=n,all_coupling_rows_checked=coupling.shape[0],
        forward_projection=True,inverse_original_point_lift=True,objective_preserved=True,
        original_boxes_preserved=True,all_removed_rows_exactly_implied=True,
        complete_domain_coverage=True,finite_column_pool_used=False,
        original_UID_primitive_interfaces_verified=units is not None,
        Global_LB_issued=False,actual_native_pricing_certificate_required=True,
        original_integer_FULL_changed=False,Native_calls=0)
