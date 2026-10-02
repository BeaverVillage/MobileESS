"""Preserve inherited lexicographic objective expressions without solving P2."""
import re
import numpy as np
from scipy import sparse
from .common import *
from .build import LOCAL
def audit():
    graph,sites,initial,bundle,battery=graph_inputs()
    with np.load(LOCAL/'AXIS_START.npz',allow_pickle=False) as z:
        old=z['original_names'];new=z['compact_names'];x=z['original_values'];y=z['compact_values']
    T=sparse.load_npz(LOCAL/'INVERSE_T.npz')
    energy=np.zeros(len(old));count=np.zeros(len(old));tie=np.zeros(len(old));moves=0
    for j,name in enumerate(old):
        match=re.fullmatch(r'arc\[([^,]+),(\d+)\]',str(name))
        if not match:continue
        k=int(match[2]);tie[j]=k+1
        if graph[k][-1] is not None:energy[j]=graph[k][-1].energy_kwh;count[j]=1;moves+=1
    vectors={};reports={}
    for label,v in [('movement_energy_kwh',energy),('movement_count',count),('original_arc_tie',tie)]:
        compact=np.asarray(v@T).ravel();vectors[label+'_original']=v;vectors[label+'_compact']=compact
        assert abs(float(v@x)-float(compact@y))<=1e-9
        # Energy/count have no stay terms and must remain identical on every scientific move,
        # independently of the one saved incumbent's possibly zero movement count.
        if label!='original_arc_tie':
            for j in np.flatnonzero(v):
                row=T[j];assert row.nnz==1 and row.data[0]==1 and compact[row.indices[0]]==v[j]
            assert np.count_nonzero(compact)==np.count_nonzero(v)
        reports[label]=dict(PASS=True,original_nonzero_coefficients=int(np.count_nonzero(v)),compact_nonzero_coefficients=int(np.count_nonzero(compact)),
            inherited_start_value=float(v@x),mapped_start_value=float(compact@y),exact_transport='c_compact=c_original T; energy/count are coefficient-for-coefficient identity on all retained moves')
    np.savez_compressed(LOCAL/'P2_OBJECTIVE_VECTORS.npz',**vectors)
    result=dict(PASS=True,P2_status='NOT_RUN',P2_optimize_calls=0,lexicographic_movement_contract=['movement_energy_kwh','movement_count'],
        inherited_primary_and_tie_contract_unchanged=True,P1_lock_required=True,unit_reachable_movement_columns=moves,
        vectors=reports,vector_snapshot_sha256=sha(LOCAL/'P2_OBJECTIVE_VECTORS.npz'))
    dump('P2_OBJECTIVE_CONTRACT.json',result);return result
if __name__=='__main__':print(audit(),flush=True)
