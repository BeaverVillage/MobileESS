"""Exact qualification of the proposed concrete-column convex-hull projection.

Embedding verified vertices proves compact -> expanded. It does not prove
expanded -> compact: the unchanged native LP retains fractional WAN directions.
This module neither prices candidates nor changes the native formulation.
"""
from fractions import Fraction
import numpy as np
from v42_a_stage_early.candidate import point_for_option,exact_coupling
from v42_a_stage_phase1.core import primal_replay

def exact_replay(snapshot,point):
    """Replay the ORIGINAL binary64 rows and boxes as exact rationals."""
    x=tuple(Fraction(float(v)) for v in point);A=snapshot.matrix;worst=Fraction(0)
    for i in range(A.shape[0]):
        lo,hi=A.indptr[i:i+2]
        activity=sum((Fraction(float(v))*x[int(j)] for j,v in zip(A.indices[lo:hi],A.data[lo:hi]) if x[int(j)]),Fraction(0))
        residual=activity-Fraction(float(snapshot.rhs[i]));sense=snapshot.senses[i]
        violation=abs(residual) if sense=='=' else residual if sense=='<' else -residual
        worst=max(worst,violation)
    bound=Fraction(0)
    for j,v in enumerate(x):
        if abs(snapshot.lower[j])<1e100:bound=max(bound,Fraction(float(snapshot.lower[j]))-v)
        if abs(snapshot.upper[j])<1e100:bound=max(bound,v-Fraction(float(snapshot.upper[j])))
    return dict(PASS=worst==0 and bound==0,max_exact_row_violation=str(worst),max_exact_bound_violation=str(bound),
        original_rows=A.shape[0],original_columns=A.shape[1],rounding_or_tolerance_used=False)

def fractional_wan_witness(cache,job,resources,stay,migration,cardinality):
    s=point_for_option(cache,job,resources,stay,cardinality)
    m=point_for_option(cache,job,resources,migration,cardinality)
    if not exact_replay(cache['snapshot'],s)['PASS'] or not exact_replay(cache['snapshot'],m)['PASS']:
        raise ValueError('ENDPOINT_EXACT_REPLAY_FAIL')
    x=(s+m)/2;original=x.copy();changed=set()
    for unit in cache['units']:
        for e in unit['v'].get('link_bytes',{}).values():
            if e[0]=='v':j=int(e[1]);x[j]=0;changed.add(j)
            elif e[0]=='e' and len(e[2])==1:
                if e[1]!=0:raise ValueError('NONZERO_WAN_EXPRESSION_CONSTANT')
                j=int(e[2][0]);x[j]=0;changed.add(j)
            else:raise ValueError('NONEXACT_SINGLE_VARIABLE_WAN_PROJECTION')
    exact=exact_replay(cache['snapshot'],x)
    return x,dict(PASS=exact['PASS'],exact_native_replay=exact,numerical_native_replay=primal_replay(cache['snapshot'],x),
        initial_point='one half original STAY endpoint + one half frozen migration endpoint',
        modification='only original encoded link_bytes variables set to zero; no row, bound, physics or tolerance changed',
        modified_variable_count=sum(original[j]!=x[j] for j in changed),
        feasible_point_is_fractional=True,physical_schedule_claimed=False)

def separator(columns,axes,resource_payload,old_B):
    """A exact linear coupling inequality valid for old block + given vertices.

No old WAN/ACTIVE coefficients is checked structurally. With concrete path
columns, W / A has a positive lower bound. The native fractional witness can
retain A>0 while W=0 under the original link-byte LP relaxation.
"""
    wan=[i for i,k in enumerate(axes) if k[0]=='WAN'];active=[i for i,k in enumerate(axes) if k[0]=='ACTIVE']
    if old_B[wan+active].nnz:raise ValueError('OLD_BLOCK_HAS_WAN_OR_ACTIVE_SUPPORT_NO_ZERO_BASE_PROOF')
    ratios=[]
    for c in columns:
        W=sum((Fraction(c.get(i,0)) for i in wan),Fraction(0));A=sum((Fraction(c.get(i,0)) for i in active),Fraction(0))
        if A:
            if W<=0:raise ValueError('CONCRETE_COLUMN_WITHOUT_POSITIVE_WAN')
            ratios.append(W/A)
        elif W<0:raise ValueError('NEGATIVE_WAN_CONCRETE_COUPLING')
    if not ratios:raise ValueError('MIGRATION_SEPARATOR_REQUIRES_FROZEN_MIGRATION')
    ratio=min(ratios)
    coefficients={i:Fraction(1) for i in wan};coefficients.update({i:-ratio for i in active})
    values=[sum((v*Fraction(c.get(i,0)) for i,v in coefficients.items()),Fraction(0)) for c in columns]
    if min(values)<0:raise ValueError('COMPACT_SEPARATOR_INVALID')
    return coefficients,dict(PASS=True,definition='sum(original WAN scaled coupling) - exact_ratio * sum(original ACTIVE coupling) >= 0',
        exact_ratio=str(ratio),old_block_zero_coupling_rows_verified=True,all_frozen_column_values=list(map(str,values)),
        valid_for_entire_old_native_block_plus_nonnegative_frozen_column_hull=True,unused_payload_metadata=str(resource_payload))

def evaluate_separator(coefficients,B,point):
    coupling=exact_coupling(B,point)
    value=sum((a*coupling.get(i,Fraction(0)) for i,a in coefficients.items()),Fraction(0))
    return value,coupling
