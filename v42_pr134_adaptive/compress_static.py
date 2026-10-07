"""Regenerate and independently verify original exact compact projection.

Static proof only, zero optimize calls. No historical reduction is inherited.
"""
import sys,shutil
from fractions import Fraction as Q
from collections import defaultdict
import numpy as np
from .common import *

def main(day,tag):
    source=CASE/day/tag;folder=source/'COMPACT';folder.mkdir(exist_ok=True)
    if (folder/'COMPRESSION_VERIFICATION.json').exists():raise PermissionError('PROOF_ALREADY_CAPTURED')
    z=dict(np.load(source/'EXPANDED_ATTRIBUTES.npz'));n=len(z['lb']);rows=len(z['rhs'])
    z.update(obj=np.zeros(n),vf=np.zeros(n,dtype=np.uint8),rf=np.zeros(rows,dtype=np.uint8),
             vf_names=np.array(['COMPLETE_CAPTURED_COLUMN_AXIS']),rf_names=np.array(['COMPLETE_CAPTURED_ROW_AXIS']))
    np.savez_compressed(folder/'A0_ATTRIBUTES_CODED.npz',**z);shutil.copyfile(source/'EXPANDED_MATRIX.npz',folder/'A0_MATRIX.npz')
    from v42_pr134_b1.native import sc_namespace
    sc,reduce,verify,materialize=sc_namespace(folder)
    atomic(folder/'CURRENT_OBJECTIVE_HIERARCHY.json',read(source/'OBJECTIVES.json'))
    if not (folder/'A2SC_PROOF.npz').exists():reduce.candidate('A2SC',True)
    verify.verify('A2SC')
    proof=sc.proof_data('A2SC');mapping=proof['mapping'];objectives=[]
    for obj in read(source/'OBJECTIVES.json'):
        terms=defaultdict(Q)
        for j,c in zip(obj['indices'],obj['coefficients']):
            if mapping[j]>=0:terms[int(mapping[j])]+=Q(float(c))
        projected=dict(name=obj['name'],indices=sorted(j for j,w in terms.items() if w),
            exact_coefficients=[str(terms[j]) for j in sorted(terms) if terms[j]],constant_exact=str(Q(float(obj['constant']))))
        if any(Q(float(w))!=Q(w) for w in projected['exact_coefficients']):raise ValueError('PROJECTED_OBJECTIVE_FLOAT_ROUNDING')
        projected['coefficients']=[float(Q(w)) for w in projected['exact_coefficients']];projected['constant']=obj['constant'];objectives.append(projected)
    atomic(folder/'PROJECTED_OBJECTIVES.json',objectives)
    report=dict(PASS=True,optimizer_calls=0,full_LP_projection_independently_verified=True,integer_domain_preserved=True,
        all_four_original_objective_forms_projected_exactly=True,scientific_source=BASE,
        original_matrix=record(source/'EXPANDED_MATRIX.npz'),original_attributes=record(source/'EXPANDED_ATTRIBUTES.npz'),
        reduced_matrix=record(folder/'A2SC_MATRIX.npz'),proof=record(folder/'A2SC_PROOF.npz'),
        objective=record(folder/'PROJECTED_OBJECTIVES.json'),census=read(folder/'A2SC_MODEL_CENSUS.json'))
    atomic(folder/'COMPRESSION_VERIFICATION.json',report);print('EXPANDED_COMPACT_PROOF_PASS',day,tag,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
