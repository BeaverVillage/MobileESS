"""Literal PCC definitions for restricted Phase I, without solver tolerance changes."""
from fractions import Fraction
import numpy as np


def definitions_from_native(model, sites, horizon=96):
    records = []
    for site in sorted(sites):
        for tick in range(horizon):
            name = f'PCC_affine_identity[{site},{tick}]'
            row = model.getConstrByName(name)
            pivot = model.getVarByName(f'PCC_affine_alias[{site},{tick}]')
            if row is None and pivot is None:
                continue
            if row is None or pivot is None or row.Sense != '=':
                raise ValueError('PCC_LITERAL_DEFINITION_NOT_AVAILABLE:'+name)
            records.append(dict(name=name,row=int(row.index),pivot=int(pivot.index)))
    return records


def satisfy_definitions(snapshot, point, definitions):
    """Construct a reference for Phase I only; never admit it as FULL feasible."""
    point = np.asarray(point).copy()
    for entry in definitions:
        i, pivot = entry['row'], entry['pivot']
        if snapshot.senses[i] != '=':
            raise ValueError('PCC_HARD_DEFINITION_MUST_BE_EQUALITY')
        row = snapshot.matrix.getrow(i)
        terms = {int(j): Fraction(float(a)) for j,a in zip(row.indices,row.data)}
        if terms.get(pivot) != 1:
            raise ValueError('PCC_UNIT_PIVOT_REQUIRED')
        exact = Fraction(float(snapshot.rhs[i])) - sum(
            (a*Fraction(float(point[j])) for j,a in terms.items() if j != pivot),Fraction())
        point[pivot] = float(exact)
    return point


def hard_rows(state):
    definitions = state.get('hard_pcc_definitions', ())
    rows = frozenset(int(d['row']) for d in definitions)
    s = state['compact']
    if not rows <= set(state['grows']) or any(s.senses[i] != '=' for i in rows):
        raise ValueError('PCC_HARD_GLOBAL_DEFINITION_AXIS_DRIFT')
    return rows


def compare_forms(snapshot, definitions):
    """Native0 comparison; reject any substitution requiring coefficient rounding.

    The hard form is literal source rows. The alternative eliminates unit PCC
    pivots using exact rational arithmetic, checking representability before
    building an expanded native matrix. A rejection is not a timing speedup.
    """
    from time import perf_counter
    began=perf_counter();A=snapshot.matrix;csc=A.tocsc();pivots={e['pivot']:e for e in definitions}
    excluded={e['row'] for e in definitions};substitutions={}
    for pivot,e in pivots.items():
        row=A.getrow(e['row'])
        terms={int(j):Fraction(float(a)) for j,a in zip(row.indices,row.data)}
        if terms.pop(pivot,None)!=1 or set(terms)&set(pivots):
            raise ValueError('PCC_INDEPENDENT_UNIT_DEFINITIONS_REQUIRED')
        substitutions[pivot]=(Fraction(float(snapshot.rhs[e['row']])),{j:-a for j,a in terms.items()})
    affected=set()
    for pivot in pivots:
        affected.update(map(int,csc.indices[csc.indptr[pivot]:csc.indptr[pivot+1]]))
    checked=0;failure=None;new_nnz=A.nnz-sum(A.getrow(i).nnz for i in excluded)
    for i in sorted(affected-excluded):
        row=A.getrow(i);terms={int(j):Fraction(float(a)) for j,a in zip(row.indices,row.data)}
        rhs=Fraction(float(snapshot.rhs[i]));old=len(terms)
        for pivot in set(terms)&set(pivots):
            coefficient=terms.pop(pivot);constant,definition=substitutions[pivot];rhs-=coefficient*constant
            for j,a in definition.items():terms[j]=terms.get(j,Fraction())+coefficient*a
        terms={j:a for j,a in terms.items() if a};checked+=1
        for j,a in list(terms.items())+[(-1,rhs)]:
            if Fraction(float(a))!=a:
                failure=dict(row=i,column=j,exact=str(a),reason='NONEXACT_BINARY64_SUBSTITUTION_REQUIRES_ROUNDING')
                break
        new_nnz+=len(terms)-old
        if failure:break
    return dict(Native_calls=0,selected='HARD_ORIGINAL_IDENTITY_EQUALITIES',
        hard=dict(original_equivalent=True,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,
            definitions=len(definitions),coefficient_changes=0),
        symbolic=dict(candidate='UNIT_PCC_ELIMINATION',original_equivalent_exact_rational=True,
            native_binary64_equivalence_verified=failure is None,rows=A.shape[0]-len(definitions),
            columns=A.shape[1]-len(definitions),nnz=new_nnz if failure is None else None,
            affected_rows=len(affected-excluded),checked_rows=checked,rejection=failure),
        preparation_wall_seconds=perf_counter()-began,
        performance_improvement_claimed=False,hard_and_exact_symbolic_same_feasible_projection=True)
