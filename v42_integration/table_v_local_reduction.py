"""Exact zero/alias projection of a complete continuous local polytope.

No domain sampling, epsilon coefficient dropping, optimizer, or integer
compression. Complete original rows and the coupling matrix remain the source
of the projection and of its independently replayable certificate.
"""
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction as F
import numpy as np
import scipy.sparse as sp

VERSION='LOCAL_EXACT_ZERO_ALIAS_PROJECTION_V1'


class NonBinary64Projection(ValueError):
    pass


def binary64(value):
    value=F(value)
    out=float(value)
    if not np.isfinite(out) or F(out)!=value:
        raise NonBinary64Projection('NONEXACT_BINARY64_LOCAL_PROJECTION')
    return out


def fold_row(matrix,i,mapping):
    a,b=matrix.indptr[i:i+2];terms=defaultdict(list)
    for j,c in zip(matrix.indices[a:b],matrix.data[a:b]):
        target=int(mapping[int(j)])
        if target>=0:terms[target].append(float(c))
    result={}
    for j,values in terms.items():
        value=F(values[0]) if len(values)==1 else sum(map(F,values),F(0))
        if value:result[j]=value
    return result


def _matrix(rows,width):
    rr=[];cc=[];vv=[]
    for i,row in enumerate(rows):
        for j,value in sorted(row.items()):rr.append(i);cc.append(j);vv.append(binary64(value))
    return sp.csr_matrix((vv,(rr,cc)),shape=(len(rows),width),dtype=float)


def _signature(row,sense,rhs):
    items=sorted(row.items());pivot=items[0][1]
    if pivot<0:sense={'<':'>','>':'<','=':'='}[sense]
    return (sense,tuple((j,c/pivot) for j,c in items),F(float(rhs))/pivot)


def _map_expression(expression,mapping):
    if expression[0]=='c':return expression
    if expression[0]=='v':
        j=int(mapping[int(expression[1])])
        return ('v',j) if j>=0 else ('c',0.)
    if expression[0]!='e':raise ValueError('UNKNOWN_LOCAL_PRIMITIVE_EXPRESSION')
    values=defaultdict(F)
    for j,c in zip(expression[2],expression[3]):
        target=int(mapping[int(j)])
        if target>=0:values[target]+=F(float(c))
    values={j:c for j,c in values.items() if c}
    if not values:return ('c',expression[1])
    if expression[1]==0 and len(values)==1 and next(iter(values.values()))==1:
        return ('v',next(iter(values)))
    js=sorted(values)
    return ('e',expression[1],np.asarray(js,dtype=np.int64),np.asarray([binary64(values[j]) for j in js]))


def reduce_block(snapshot,coupling,units=(),*,max_rounds=100):
    """Return an exact complete-polytope projection or reject representation.

    Only zeros are fixed: global coupling constants and RHS are never rounded.
    Equalities may identify x=y, with the exact intersection of their boxes.
    Every implied relation is recorded before it is used. Row deletion is
    limited to rational tautologies and exact proportional duplicates.
    """
    snapshot.require();A=snapshot.matrix;B=coupling.tocsr(copy=False)
    n=A.shape[1]
    if type(max_rounds) is not int or max_rounds<1:raise ValueError('POSITIVE_PROPAGATION_ROUNDS_REQUIRED')
    if np.any(snapshot.vtypes!='C'):raise ValueError('CONTINUOUS_LOCAL_POLYTOPE_ONLY')
    if B.shape[1]!=n or not B.has_canonical_format or not np.isfinite(B.data).all():
        raise ValueError('CANONICAL_COMPLETE_COUPLING_REQUIRED')
    parent=list(range(n));zero=set();steps=[]
    def root(j):
        while parent[j]!=j:parent[j]=parent[parent[j]];j=parent[j]
        return j
    for j in range(n):
        if snapshot.lower[j]==snapshot.upper[j]==0:
            zero.add(j);steps.append(dict(kind='BOUND_ZERO',column=j))
    for turn in range(max_rounds):
        lower={};upper={};changed=False
        for j in range(n):
            k=root(j);lower[k]=max(lower.get(k,-np.inf),snapshot.lower[j]);upper[k]=min(upper.get(k,np.inf),snapshot.upper[j])
        for i in range(A.shape[0]):
            if snapshot.rhs[i]!=0:continue
            a,b=A.indptr[i:i+2];terms=defaultdict(list)
            for j,c in zip(A.indices[a:b],A.data[a:b]):
                k=root(int(j))
                if k not in zero:terms[k].append(float(c))
            row={k:sum(map(F,values),F(0)) for k,values in terms.items()}
            row={k:v for k,v in row.items() if v};sense=str(snapshot.senses[i])
            if not row:continue
            if sense=='=' and len(row)==2:
                (a,ca),(b,cb)=row.items()
                if ca==-cb:
                    if min(upper[a],upper[b])<max(lower[a],lower[b]):raise ValueError('EXACT_ALIAS_BOUND_CONTRADICTION')
                    keep,drop=sorted((a,b));steps.append(dict(kind='ROW_ALIAS',row=i,keep=keep,drop=drop))
                    parent[drop]=keep;lower[keep]=max(lower[a],lower[b]);upper[keep]=min(upper[a],upper[b]);changed=True
                    continue
            nonnegative=all(lower[j]>=0 if c>0 else upper[j]<=0 for j,c in row.items())
            nonpositive=all(upper[j]<=0 if c>0 else lower[j]>=0 for j,c in row.items())
            if (sense=='=' and len(row)==1) or (nonnegative and sense in ('=','<')) or (nonpositive and sense in ('=','>')):
                targets=sorted(row)
                if any(not lower[j]<=0<=upper[j] for j in targets):raise ValueError('EXACT_ZERO_BOUND_CONTRADICTION')
                steps.append(dict(kind='ROW_ZERO',row=i,columns=targets))
                zero.update(targets);changed=True
        zero={root(j) for j in zero}
        if not changed:break
    representatives=sorted(set(root(j) for j in range(n))-zero)
    positions={j:k for k,j in enumerate(representatives)}
    mapping=np.asarray([-1 if root(j) in zero else positions[root(j)] for j in range(n)],dtype=np.int64)
    lower=np.full(len(representatives),-np.inf);upper=np.full(len(representatives),np.inf)
    for j,k in enumerate(mapping):
        if k>=0:lower[k]=max(lower[k],snapshot.lower[j]);upper[k]=min(upper[k],snapshot.upper[j])
    signatures={};rows=[];kept=[];targets=[];multipliers=[]
    for i in range(A.shape[0]):
        row=fold_row(A,i,mapping);sense=str(snapshot.senses[i]);rhs=F(float(snapshot.rhs[i]))
        if not row:
            okay=(rhs==0 if sense=='=' else rhs>=0 if sense=='<' else rhs<=0)
            if not okay:raise ValueError('EXACT_EMPTY_ROW_CONTRADICTION')
            targets.append(-1);multipliers.append('0');continue
        key=_signature(row,sense,snapshot.rhs[i])
        if key in signatures:
            target=signatures[key];pivot=next(iter(sorted(row.items())))[1]
            other=next(iter(sorted(rows[target].items())))[1]
            targets.append(target);multipliers.append(str(pivot/other));continue
        signatures[key]=len(rows);targets.append(len(rows));multipliers.append('1');rows.append(row);kept.append(i)
    matrix=_matrix(rows,len(representatives));coupling_rows=[fold_row(B,i,mapping) for i in range(B.shape[0])]
    newB=_matrix(coupling_rows,len(representatives));objectives=[]
    for objective in snapshot.objectives:
        coefficients=defaultdict(F)
        for j,c in objective.coefficients().items():
            if mapping[j]>=0:coefficients[int(mapping[j])]+=c
        for c in coefficients.values():binary64(c)
        objectives.append(replace(objective,terms=tuple((j,c) for j,c in sorted(coefficients.items()) if c)))
    projected=replace(snapshot,matrix=matrix,lower=lower,upper=upper,
        senses=snapshot.senses[kept].copy(),rhs=snapshot.rhs[kept].copy(),
        vtypes=np.full(len(representatives),'C'),objectives=tuple(objectives)).require()
    mapped_units=[dict(u,v={family:{key:_map_expression(e,mapping) for key,e in items.items()}
        for family,items in u['v'].items()}) for u in units]
    return dict(snapshot=projected,B=newB,units=mapped_units,mapping=mapping,
        representatives=np.asarray(representatives,dtype=np.int64),kept_rows=np.asarray(kept,dtype=np.int64),
        row_targets=np.asarray(targets,dtype=np.int64),row_multipliers=multipliers,
        proof=dict(version=VERSION,source_snapshot_sha=snapshot.fingerprint(),target_snapshot_sha=projected.fingerprint(),
            original_rows=A.shape[0],original_columns=n,original_NNZ=A.nnz,
            reduced_rows=matrix.shape[0],reduced_columns=matrix.shape[1],reduced_NNZ=matrix.nnz,
            inference_steps=steps,propagation_rounds=turn+1,propagation_converged=not changed,
            original_integer_FULL_changed=False,global_RHS_or_constant_changed=False,
            mathematical_equivalence_independently_verified=False,performance_improvement_claimed=False))


def lift_point(result,point):
    mapping=result['mapping'];point=np.asarray(point)
    if point.shape!=(result['snapshot'].matrix.shape[1],):raise ValueError('REDUCED_LOCAL_POINT_AXIS')
    out=np.zeros(len(mapping),dtype=point.dtype);used=mapping>=0;out[used]=point[mapping[used]]
    return out
