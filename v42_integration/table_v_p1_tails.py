"""Exact existential projection of P1-neutral CC4 deviation epigraph tails.

The original integer model and its P2 expressions remain untouched. A tail
may disappear only from the P1 LP representation: it has zero P1 cost, is
continuous in [0,+inf), occurs in one >= row with positive coefficient, and
is not a resource coupling row. Every projected point has a canonical lift.
"""
from dataclasses import replace
from fractions import Fraction
import math
import numpy as np

FAMILIES=frozenset(('CC4_dplus','CC4_dminus','CC4_reserve_timing_dplus','CC4_reserve_timing_dminus'))


def _eligible(snapshot,names,protected):
    csc=snapshot.matrix.tocsc();obj=snapshot.objectives[0].coefficients();found=[];used=set()
    for name,j in sorted(names.items(),key=lambda item:item[1]):
        if name.split('[')[0] not in FAMILIES:continue
        j=int(j);a,b=csc.indptr[j:j+2]
        if b-a!=1:continue
        i=int(csc.indices[a]);c=float(csc.data[a])
        if (i in protected or i in used or snapshot.senses[i]!='>' or not math.isfinite(c) or c<=0
                or snapshot.lower[j]!=0 or not np.isposinf(snapshot.upper[j])
                or snapshot.vtypes[j]!='C' or obj.get(j,0)!=0):continue
        used.add(i);found.append(dict(name=name,column=j,row=i,coefficient=c))
    return found


def verify(original,projected,proof,*,protected_rows=()):
    if len(original.objectives)!=1 or original.objectives[0].name!='rho':
        raise ValueError('ORIGINAL_P1_ONLY_OBJECTIVE_REQUIRED_FOR_TAIL_PROJECTION')
    entries=proof['entries'];columns={r['column'] for r in entries};rows={r['row'] for r in entries}
    if len(columns)!=len(entries) or len(rows)!=len(entries):raise ValueError('P1_TAIL_DUPLICATE_PIVOT')
    # Re-derive every claimed existential ray from original columns; do not
    # trust the selection helper or the proof's claimed support/domain.
    csc=original.matrix.tocsc();cost=original.objectives[0].coefficients()
    for entry in entries:
        j=entry['column'];i=entry['row'];a,b=csc.indptr[j:j+2]
        if (entry['name'].split('[')[0] not in FAMILIES or i in protected_rows or b-a!=1
                or int(csc.indices[a])!=i or original.senses[i]!='>'
                or float(csc.data[a])!=entry['coefficient'] or not math.isfinite(entry['coefficient'])
                or entry['coefficient']<=0 or original.lower[j]!=0 or not np.isposinf(original.upper[j])
                or original.vtypes[j]!='C' or cost.get(j,0)!=0):
            raise ValueError('P1_TAIL_ORIGINAL_SUPPORT_DOMAIN_OBJECTIVE_PROOF_FAILED')
    kept_rows=np.asarray([i for i in range(original.matrix.shape[0]) if i not in rows],dtype=np.int64)
    kept_columns=np.asarray([j for j in range(original.matrix.shape[1]) if j not in columns],dtype=np.int64)
    expected=original.matrix[kept_rows][:,kept_columns].tocsr();actual=projected.matrix.tocsr()
    if not (expected.shape==actual.shape and np.array_equal(expected.indptr,actual.indptr)
            and np.array_equal(expected.indices,actual.indices) and np.array_equal(expected.data,actual.data)):
        raise ValueError('P1_TAIL_RETAINED_MATRIX_BYTES_CHANGED')
    for key in ('lower','upper','vtypes'):
        if not np.array_equal(getattr(original,key)[kept_columns],getattr(projected,key)):
            raise ValueError('P1_TAIL_RETAINED_DOMAIN_CHANGED')
    for key in ('senses','rhs'):
        if not np.array_equal(getattr(original,key)[kept_rows],getattr(projected,key)):
            raise ValueError('P1_TAIL_RETAINED_ROWS_CHANGED')
    remap={int(j):i for i,j in enumerate(kept_columns)}
    obj=original.objectives[0];want={remap[j]:a for j,a in obj.coefficients().items()}
    if (len(projected.objectives)!=1 or projected.objectives[0].name!='rho'
            or projected.objectives[0].coefficients()!=want or projected.objectives[0].constant!=obj.constant):
        raise ValueError('P1_TAIL_OBJECTIVE_CHANGED')
    return dict(PASS=True,all_retained_coefficients_rhs_boxes_types_exact=True,
        all_original_discrete_variables_retained=True,removed_P1_costs_exactly_zero=True,
        forward_projection_valid_for_every_original_point=True,
        reverse_lift='t=max(0,(rhs-sum(other original row terms))/positive original coefficient)',
        reverse_lift_valid_for_every_projected_point=True,original_integer_model_modified=False,
        P2_optimization_or_P2_equivalence_claimed=False)


def project(original,descriptor,*,protected_rows=()):
    from v42_a_stage_domain_v2.lexstage import Objective
    if len(original.objectives)!=1 or original.objectives[0].name!='rho':
        raise ValueError('ORIGINAL_P1_ONLY_OBJECTIVE_REQUIRED_FOR_TAIL_PROJECTION')
    entries=_eligible(original,descriptor.get('globals',{}),set(protected_rows))
    removed_columns={r['column'] for r in entries};removed_rows={r['row'] for r in entries}
    kept_columns=np.asarray([j for j in range(original.matrix.shape[1]) if j not in removed_columns],dtype=np.int64)
    kept_rows=np.asarray([i for i in range(original.matrix.shape[0]) if i not in removed_rows],dtype=np.int64)
    remap={int(j):i for i,j in enumerate(kept_columns)}
    def shift(e):
        if e[0]=='v':
            if int(e[1]) not in remap:raise ValueError('P1_TAIL_OCCURS_IN_SCIENTIFIC_CONTROL_OR_UID_EXPRESSION')
            return ('v',remap[int(e[1])])
        if e[0]=='e':
            if any(int(j) not in remap for j in e[2]):raise ValueError('P1_TAIL_OCCURS_IN_SCIENTIFIC_CONTROL_OR_UID_EXPRESSION')
            return ('e',e[1],np.asarray([remap[int(j)] for j in e[2]],dtype=np.int64),e[3])
        return e
    if entries:
        translated=dict(descriptor,
            units=[dict(u,v={f:{key:shift(e) for key,e in items.items()} for f,items in u['v'].items()}) for u in descriptor['units']],
            known={key:shift(e) for key,e in descriptor['known'].items()},
            risk={key:shift(e) for key,e in descriptor['risk'].items()},
            controls=[[shift(e) for e in group] for group in descriptor['controls']],
            globals={name:remap[int(j)] for name,j in descriptor['globals'].items() if int(j) in remap},
            levels=[(name,shift(e)) for name,e in descriptor['levels'] if name=='rho'])
    else:translated=descriptor
    objective=original.objectives[0]
    projected=replace(original,matrix=original.matrix[kept_rows][:,kept_columns].tocsr(),
        lower=original.lower[kept_columns],upper=original.upper[kept_columns],vtypes=original.vtypes[kept_columns],
        senses=original.senses[kept_rows],rhs=original.rhs[kept_rows],
        objectives=(Objective('rho',tuple((remap[j],a) for j,a in objective.coefficients().items()),objective.constant),)).require()
    proof=dict(PASS=True,schema='EXACT_P1_NEUTRAL_EPIGRAPH_PROJECTION_V1',entries=entries,
        original_LP_sha=original.fingerprint(),projected_LP_sha=projected.fingerprint(),
        removed_columns=len(entries),removed_rows=len(entries),Native_calls=0,
        P1_only=True,original_integer_model_modified=False,coefficient_rounding_allowed=False)
    proof['independent_verification']=verify(original,projected,proof,protected_rows=protected_rows)
    return projected,translated,proof,kept_rows,kept_columns


def lift(original,point,proof):
    x=np.asarray(point,dtype=float);removed={r['column'] for r in proof['entries']}
    keep=np.asarray([j for j in range(original.matrix.shape[1]) if j not in removed],dtype=np.int64)
    if x.shape!=(len(keep),) or not np.all(np.isfinite(x)):raise ValueError('FINITE_PROJECTED_P1_POINT_REQUIRED')
    out=np.zeros(original.matrix.shape[1]);out[keep]=x
    for entry in proof['entries']:
        i,j,c=entry['row'],entry['column'],Fraction(entry['coefficient'])
        a,b=original.matrix.indptr[i:i+2]
        needed=(Fraction(float(original.rhs[i]))-sum((Fraction(float(v))*Fraction(float(out[k]))
            for k,v in zip(original.matrix.indices[a:b],original.matrix.data[a:b]) if k!=j),Fraction(0)))/c
        exact=max(Fraction(0),needed);value=float(exact)
        if not math.isfinite(value):raise ValueError('FINITE_P1_TAIL_LIFT_REQUIRED')
        if Fraction(value)<exact:value=float(np.nextafter(value,np.inf))
        if not math.isfinite(value):raise ValueError('FINITE_P1_TAIL_LIFT_REQUIRED')
        out[j]=value
    if not np.array_equal(out[keep],x):raise ValueError('P1_TAIL_LIFT_CHANGED_RETAINED_POINT')
    return out
