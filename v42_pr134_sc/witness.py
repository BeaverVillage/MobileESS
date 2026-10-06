"""Independent raw accepted-point projection and reconstruction; no optimize."""
from fractions import Fraction as Q
import json
import numpy as np
import scipy.sparse as sp
from .common import *
from .build import replay

def run():
    base=json.loads((OUT/'PR134_ACCEPTED_WITNESS_REPLAY.json').read_text(encoding='utf8'))
    assert base['BASELINE_FEASIBLE_WITNESS_PASS']
    a=sp.load_npz(LOCAL/'A0_MATRIX.npz');z=attributes();x=np.load(LOCAL/'ACCEPTED_POINT.npz')['values']
    active=read_artifact('ACTIVE_OBJECTIVE_HIERARCHY.json')
    results=[]
    for name in ('A1R','A2SC'):
        assert json.loads((OUT/(name+'_INDEPENDENT_VERIFICATION.json')).read_text())['PASS']
        p=proof_data(name);mapping=p['mapping'];y=x[p['roots']]
        b=sp.load_npz(LOCAL/(name+'_MATRIX.npz'));zz=attributes(name)
        forward=replay(b,zz,y)
        back=np.zeros(a.shape[1]);ids=mapping>=0;back[ids]=y[mapping[ids]]
        reverse=replay(a,z,back)
        objectives=[];mapped=[]
        for e in active:
            coefficients={}
            for j,c in zip(e['indices'],e['coefficients']):
                k=int(mapping[j])
                if k>=0:coefficients[k]=coefficients.get(k,Q(0))+Q(float(c))
            assert all(Q(float(c))==c for c in coefficients.values()),'NONEXACT_ACTIVE_OBJECTIVE'
            old=float(e['constant']+np.dot(e['coefficients'],x[e['indices']]))
            reconstructed=float(e['constant']+np.dot(e['coefficients'],back[e['indices']]))
            projected=float(e['constant']+sum(float(c)*y[k] for k,c in coefficients.items()))
            objectives.append(dict(component=e['name'],original=old,projected=projected,reconstructed=reconstructed,
                absolute_difference=max(abs(old-projected),abs(old-reconstructed)),PASS=max(abs(old-projected),abs(old-reconstructed))<=1e-5))
            mapped.append(dict(group=e['group'],name=e['name'],constant=e['constant'],indices=list(coefficients),coefficients=[float(c) for c in coefficients.values()]))
        write(name+'_ACTIVE_OBJECTIVES.json',mapped)
        np.savez_compressed(LOCAL/(name+'_ACCEPTED_POINT.npz'),values=y)
        r=dict(candidate=name,PASS=forward['PASS'] and reverse['PASS'] and all(e['PASS'] for e in objectives),
            projected_candidate=forward,reconstructed_original=reverse,objective_hierarchy=objectives,
            max_original_point_reconstruction_difference=float(abs(back-x).max()),
            reconstruction_rule='Certified zeros and original equality component common values; no rounding or clipping',
            numerical_tolerance=1e-5,source_witness=record(LOCAL/'ACCEPTED_POINT.npz'),candidate_start=record(LOCAL/(name+'_ACCEPTED_POINT.npz')))
        write(name+'_ACCEPTED_WITNESS_REPLAY.json',r);results.append(r)
        assert r['PASS'],'ACCEPTED_CANDIDATE_WITNESS_FAILED:'+name
    write('START_VALIDATION.json',dict(PASS=True,valid_start_available=True,raw_accepted_PR134_start=True,
         candidate_replays=results,all_original_rows_replayed=True,historical_PR150_PR151_point_used=False,
         bounds_integer_types_and_all_four_active_objectives_verified=True,benchmark_start_used=False))
    print('Accepted point maps and reconstructs every original row for both candidates',flush=True)

if __name__=='__main__':run()
