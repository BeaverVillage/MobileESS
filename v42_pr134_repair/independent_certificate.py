"""Solver-free exact proof verifier; does not import native diagnosis/reducer."""
import argparse,json
from collections import defaultdict,Counter
from fractions import Fraction
import numpy as np,scipy.sparse as sparse
from .common import *

def verify(day):
    target=CASE/day
    rawfile=target/('BOUND_COMPLETE_RAW_FARKAS.npz' if day=='2025-05-17' else 'ORIGINAL_IIS_RAW_FARKAS.npz')
    raw=dict(np.load(rawfile));ray=raw['ray'];rows=raw['rows'];columns=raw['columns']
    completion=None
    if day=='2025-05-19':
        completion=read(OUT/'MAY19_RATIONAL_FARKAS_COMPLETION.json')
        rows=np.array(completion['rows']);multipliers=[Fraction(s) for s in completion['exact_multipliers']]
    else:multipliers=[Fraction.from_float(float(x)) for x in ray]
    a=sparse.load_npz(target/'A0_MATRIX.npz');z=dict(np.load(target/'A0_ATTRIBUTES_CODED.npz'))
    identity=read(OUT/(label(day)+'_INITIAL_IDENTITY.json'))
    if sha(target/'A0_MATRIX.npz')!=identity['original_matrix']['sha256']:raise ValueError('ORIGINAL_MATRIX_SHA')
    names=dict(np.load(target/'ORIGINAL_NATIVE_NAMES.npz'))
    totals=defaultdict(lambda:Fraction(0));rhs=Fraction(0);details=[];sign_ok=True
    for k,weight in enumerate(multipliers):
        if not weight:continue
        r=int(rows[k]);multiplier=weight;sense=str(z['sense'][r])
        if sense=='<' and multiplier<0 or sense=='>' and multiplier>0:sign_ok=False
        rhs+=multiplier*Fraction.from_float(float(z['rhs'][r]))
        start,end=map(int,a.indptr[r:r+2])
        for j,coefficient in zip(a.indices[start:end],a.data[start:end]):
            totals[int(j)]+=multiplier*Fraction.from_float(float(coefficient))
        details.append(dict(row_index=r,name=str(names['rows'][r]),family=str(z['rf_names'][z['rf'][r]]),
            multiplier=str(multiplier),sense=sense,RHS=str(Fraction(float(z['rhs'][r]))),
            counterpart='ORIGINAL_FULL row '+str(r),terms=end-start))
    minimum=Fraction(0);bounddetails=[];bad=[]
    for j,coefficient in sorted(totals.items()):
        if coefficient==0:continue
        value=float(z['lb'][j] if coefficient>0 else z['ub'][j])
        if not np.isfinite(value) or abs(value)>=1e100:
            bad.append(dict(variable=j,coefficient=str(coefficient),bound=value));continue
        term=coefficient*Fraction.from_float(value);minimum+=term
        bounddetails.append(dict(variable=j,name=str(names['vars'][j]),family=str(names['vars'][j]).split('[')[0],
            combined_coefficient=str(coefficient),bound_kind='LB' if coefficient>0 else 'UB',bound=str(Fraction(value)),contribution=str(term)))
    margin=minimum-rhs;passed=sign_ok and not bad and margin>0
    # The same proof also excludes a point accepted by the original 1e-5
    # row/bound checker. Account for every permitted residual conservatively.
    row_norm=sum(abs(w) for w in multipliers);column_norm=sum(abs(v) for v in totals.values())
    allowance=Fraction.from_float(1e-5)*(row_norm+column_norm)
    robust=passed and margin>allowance
    result=dict(PASS=robust,day=day,classification='TRUE_SCIENTIFIC_INFEASIBILITY' if robust else 'INCONCLUSIVE',
        original_matrix=record(target/'A0_MATRIX.npz'),attributes=record(target/'A0_ATTRIBUTES_CODED.npz'),raw_ray=record(rawfile),
        exact_minimum=str(minimum),exact_rhs=str(rhs),exact_positive_contradiction_margin=str(margin),
        margin_float=float(margin),row_signs_valid=sign_ok,unbounded_nonzero_terms=bad,
        all_binary_integer_domains_relaxed=True,LP_infeasibility_proves_original_MIP_infeasibility=passed,
        optimizer_calls=0,production_reducer_or_native_certificate_imported=False,
        residual_terms_discarded=0,tolerance_used_to_ignore_residuals=False,
        original_checker_tolerance=1e-5,exact_worst_case_row_and_bound_residual_allowance=str(allowance),
        allowance_float=float(allowance),contradiction_survives_original_checker_tolerance=robust,
        row_family_counts=dict(Counter(x['family'] for x in details)),weighted_rows=len(details),bound_terms=len(bounddetails),
        rational_completion=record(OUT/'MAY19_RATIONAL_FARKAS_COMPLETION.json') if completion else None,
        proof='Signed original rows imply sum_j c_j*x_j <= exact_rhs. Original bounds imply sum_j c_j*x_j >= exact_minimum. The strict positive rational gap is impossible.',
        numerical_false_infeasibility=False if passed else None)
    table(OUT/(label(day)+'_EXACT_CONFLICT_ROWS.csv'),details,['row_index','name','family','multiplier','sense','RHS','counterpart','terms'])
    table(OUT/(label(day)+'_EXACT_CONFLICT_BOUNDS.csv'),bounddetails,['variable','name','family','combined_coefficient','bound_kind','bound','contribution'])
    write(label(day)+'_INDEPENDENT_EXACT_CERTIFICATE.json',result)
    write(label(day)+'_IIS_CLASSIFICATION.json',result)
    print(day,'independent rational certificate:',passed,'margin',str(margin),'families',result['row_family_counts'],flush=True)
    if not robust:raise ValueError('INDEPENDENT_INFEASIBILITY_NOT_PROVEN')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('day',choices=DAYS);verify(parser.parse_args().day)
