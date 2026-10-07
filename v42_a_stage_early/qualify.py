"""Read-only qualification against two persisted PR172 class solves."""
from dataclasses import replace
from fractions import Fraction
from time import perf_counter
import gzip,pickle
import numpy as np
from v42_pr134_b1.common import read,atomic,record
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_phase1.runner import projected_global_pi,load_cache,serial
from v42_a_stage_phase1.oracle import corrected_certificate
from .policy import OUT,STATIC,HISTORY
from .candidate import recover
from .budget import Budget

def run():
    with gzip.open(STATIC/'INITIAL_STATE.pkl.gz','rb') as f:base,desc,data,domains,ledger,axes,n,grows,lrows,owned=pickle.load(f)
    previous=read(HISTORY/'MAY19/NATIVE_CALLS.json')['calls']
    masterraw={k:v for k,v in np.load(previous[0]['raw_attributes']['path']).items()}
    master=elastic_master(base,grows);pi=projected_global_pi(master,masterraw['Pi']);cp=np.asarray([pi[r] for r in axes.values()])
    roster={r['class_id']:r for r in read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    records=[];budget=Budget()
    for call in previous[1:3]:
        folder=__import__('pathlib').Path(call['folder'])
        matches=[key for key in roster if key.startswith(folder.name)]
        if len(matches)!=1:raise ValueError('HISTORICAL_CLASS_IDENTITY_AMBIGUOUS')
        key=matches[0];want=roster[key];cache=load_cache(want);cache['coupling_axes']=tuple(axes)
        cols=sorted(j for j,c in owned.items() if c==key);rows=list(lrows[key])
        active=replace(base,matrix=base.matrix[rows][:,cols].tocsr(),lower=base.lower[cols],upper=base.upper[cols],senses=base.senses[rows],rhs=base.rhs[rows],
            vtypes=np.full(len(cols),'C'),objectives=cache['snapshot'].objectives)
        certificate=corrected_certificate(active,base.matrix[list(axes.values())][:,cols],cp,pi[rows])
        raw=np.load(call['raw_attributes']['path']);started=perf_counter()
        c=recover(cache,data,domains,ledger,key,cp,certificate['exact_lower_bound'],raw['X'],Fraction(1,100000000),budget)
        records.append(dict(class_id=key,recovered=c is not None,kind=None if c is None else c['kind'],
            candidate_id=None if c is None else c['candidate_id'],exact_rc=None if c is None else str(c['price']),seconds=perf_counter()-started,
            native_local_PASS=None if c is None else c['native_local_replay']['PASS'],raw_PR172=call['raw_attributes']))
    atomic(OUT/'CONCRETE_RECOVERY_QUALIFICATION.json',dict(PASS=all(r['recovered'] and r['native_local_PASS'] for r in records),
        cached_PR172_only=True,new_May19_native_calls=0,records=records))
    print('CONCRETE_RECOVERY_QUALIFICATION',records,flush=True)

if __name__=='__main__':run()
