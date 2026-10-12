"""Small, read-only exhibits; no Native solve or global candidate promotion."""
from pathlib import Path
from fractions import Fraction
import gzip,pickle,sys
import numpy as np
import scipy.sparse as sp
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_pr134_b1.common import read,record,atomic,now
from v42_a_stage_domain_v2.fast_pricing import verify_primal
from tools.b1_exact_pricing import strengthened_bound

DOC=ROOT/'docs/v42_b1_rootcause_20261012'

def run():
    one=Path(r'D:\v42_b1_only_may_20261012_03\dates\B1\2025-05-01\attempts\attempt_01\output')
    folder=one/'PHASE_I/S0';identity=read(folder/'MODEL_IDENTITY.json');native=read(folder/'NATIVE_RESULT.json')
    A=sp.load_npz(identity['matrix']['path']);attrs=np.load(identity['attributes']['path']);raw=np.load(native['raw_attributes']['path'])
    with gzip.open(one/'STATIC/SCIENTIFIC_INTERFACES.pkl.gz','rb') as stream:desc=pickle.load(stream)
    names={v:k for k,v in desc['globals'].items()};lo,hi=A.indptr[6526:6528]
    terms=[dict(column=int(j),variable=names.get(int(j)),coefficient=float(c),X=float(raw['X'][j]),
                exact_term=str(Fraction(float(c))*Fraction(float(raw['X'][j])))) for j,c in zip(A.indices[lo:hi],A.data[lo:hi])]
    exact=sum((Fraction(float(c))*Fraction(float(raw['X'][j])) for j,c in zip(A.indices[lo:hi],A.data[lo:hi])),Fraction(0))-Fraction(float(attrs['rhs'][6526]))
    assert exact==Fraction(1,131072)
    scaled_terms=[Fraction(t['exact_term'])/2**35 for t in terms]
    assert sum(scaled_terms,Fraction(0))==exact/2**35
    controls=[]
    for slot,row in enumerate(desc['controls']):
        for control,e in enumerate(row):
            if e[0]=='e' and 12000 in e[2]:controls.append(dict(slot=slot,control=control,expression=str(e)))
    evidence=dict(schema='MAY01_ORIGINAL_NUMERICAL_EXHIBIT_V1',result=record(one.parent/'RESULT.json'),
        saved_restricted_row=6526,full_initial_original_row=16078,
        full_original_row_mapping_evidence='Exact CSR coefficient/RHS/sense match checked by prefix snapshot inspection before user stop',
        sense=str(attrs['senses'][6526]),RHS=float(attrs['rhs'][6526]),terms=terms,exact_residual=str(exact),
        original_tolerance='1/1000000',maximum_term=max(abs(float(Fraction(t['exact_term']))) for t in terms),
        CC4_GPU_allocation_row=True,slot=11,AIDC01_p_control=controls,
        native_status=native['status'],Runtime=native['native_seconds'],Barrier_iterations=native['BarIterCount'],simplex_iterations=native['IterCount'],
        parameters=read(folder/'SOLVER_PARAMETERS.json'),compiled=read(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
        matrix=identity['matrix'],attributes=identity['attributes'],raw=native['raw_attributes'],log=record(folder/'NATIVE_SOLVER.log'),
        dyadic_row_scale_example=dict(factor='1/34359738368',scaled_exact_residual=str(exact/2**35),
            original_coordinate_residual_unchanged=True,scaling_alone_does_not_repair_the_rejected_point=True),
        changed_raw_point=False,additional_Native_calls=0,new_global_candidate_generated=False,
        Barrier_Crossover_Postsolve_causal_isolation='Not established: raw postsolve result and iteration counters are available; crossover trajectory is not logged',UTC=now())
    atomic(DOC/'MAY01_NUMERIC_EXHIBIT.json',evidence)
    del A,attrs,raw
    out=Path(r'D:\v42_b1_only_may_20261012_04\dates\B1\2025-05-03\attempts\attempt_01\output')
    d=read(out/'P1/S1/PRICE/FULL_PRICING_RESULT.json');required={x['class_id']:x for x in read(out/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    with gzip.open(out/'STATIC/SCIENTIFIC_INTERFACES.pkl.gz','rb') as stream:descriptor=pickle.load(stream)
    cases=[]
    for block in d['block_certificates']:
        if Fraction(block['minimum_rc_lower_bound'])>=Fraction(-1,100000000):continue
        folder=out/'P1/S1/PRICE/B'/block['class_id'][:12];r=read(folder/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json');q=required[block['class_id']]
        assert record(q['external_full_block_cache']['path'])==q['external_full_block_cache']
        with gzip.open(q['external_full_block_cache']['path'],'rb') as stream:cache=pickle.load(stream)
        proof=strengthened_bound(cache['snapshot'],cache['B'],r['global_coupling_pi'],r['local_raw_pi'])
        oldLB=Fraction(r['certificate']['exact_lower_bound']);newLB=Fraction(proof['exact_lower_bound'])
        assert newLB>=oldLB and newLB==0
        activeRaw=Fraction(r['active_raw_point_price']);activeLB=Fraction(r['active_local_lower_bound'])
        fullPoint=Fraction(r['oracle_point_price'])+activeLB
        local_native=read(folder/'NATIVE_RESULT.json');raw=np.load(local_native['raw_attributes']['path'])
        local_exact=None;membership=None
        if block['class_id'].startswith(('c5e7','f602')):
            local_exact=verify_primal(cache['snapshot'],raw['X'])
            assert local_exact['PASS']
            stay=[(key,int(expr[1])) for u in cache['units'] for key,expr in u['v']['y'].items() if expr[0]=='v' and raw['X'][int(expr[1])]!=0]
            active_keys=set(key for u in descriptor['units'] if u['class_key']==block['class_id'] for key in u['v']['y'])
            membership=[dict(site_start=list(key),full_column=j,count=float(raw['X'][j]),in_initial_active_STAY=key in active_keys) for key,j in stay]
        strengthened_delta=newLB-activeRaw
        cases.append(dict(class_id=block['class_id'],cardinality=q['cardinality'],
            active_raw_point_price=str(activeRaw),active_local_lower_bound=str(activeLB),
            full_lower_bound=str(oldLB),full_primal_point_price=str(fullPoint),
            original_oracle_point_price=str(Fraction(r['oracle_point_price'])),
            full_point_minus_active_raw_upper=str(fullPoint-activeRaw),
            minimum_rc_lower_bound=r['minimum_rc_lower_bound'],
            exact_box_roundoff_correction=r['certificate']['exact_box_roundoff_correction'],
            original_box_dual_residual_nonzero=sum(Fraction(x)!=0 for x in r['certificate']['certificate']['residuals']),
            strengthened_certificate=proof,strengthened_delta_against_original_active_raw=str(strengthened_delta),
            closes_at_original_epsilon=bool(strengthened_delta>=Fraction(-1,100000000)),
            full_primal_exact_replay=None if local_exact is None else dict(PASS=local_exact['PASS'],exact=True,violations=local_exact['violations']),
            full_STAY_witness_membership=membership,certificate=record(folder/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json'),
            full_native=record(folder/'NATIVE_RESULT.json')))
    atomic(DOC/'MAY03_CERTIFICATE_STRENGTHENING.json',dict(schema='MAY03_READ_ONLY_CERTIFICATE_STRENGTHENING_V1',
        classes=cases,additional_Native_calls=0,raw_X_or_Pi_modified=False,
        original_full_physical_domain_unchanged=True,old_FAIL_promoted=False,
        closed_against_original_active_raw=sum(c['closes_at_original_epsilon'] for c in cases),
        unresolved_against_original_active_raw=sum(not c['closes_at_original_epsilon'] for c in cases),
        production_integration=False,UTC=now()))
    print('Saved May01 exhibit and five exact Pricing certificate comparisons; Native=0.')

if __name__=='__main__':run()
