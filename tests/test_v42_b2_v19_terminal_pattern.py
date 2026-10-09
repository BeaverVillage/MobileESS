import numpy as np
from scipy import sparse
from types import SimpleNamespace as NS
from v42_b2_seed_recovery_v19.fixed_pattern import values_for
from v42_b2_seed_recovery_v18.initialization import values_for as old_values_for

def case():
    names=np.array([f'node_activity[M,{site},{t}]' for site in ('A','B') for t in range(97)])
    names=np.concatenate([names,np.array([f'charge_mode[M,{t}]' for t in range(96)])])
    terminal=[96,193]
    A=sparse.csr_matrix((np.ones(2),(np.zeros(2,dtype=int),terminal)),shape=(1,len(names)))
    d=dict(names=names,types=np.array(['B']*len(names)),row_names=np.array(['terminal_location']),rhs=np.array([1.]))
    arcs=[(site,t,site,t+1,None) for site in ('A','B') for t in range(96)]
    route=NS(validate=lambda horizon:None)
    arcs.append(('A',0,'B',1,route))
    return NS(A=A,d=d,graph=(('A','B'),{'M':'A'},arcs,None,None))

def test_reproduces_v18_terminal_zero_bug_and_repairs_original_terminal_equality():
    c=case();paths={'M':list(range(96))}
    ids,old=old_values_for(c,paths,lambda u,t:t<40)
    ids,new=values_for(c,paths,lambda u,t:t<40)
    assert float((c.A@old)[0])==0. and float((c.A@new)[0])==1.
    assert new[96]==1. and new[193]==0.
    assert np.flatnonzero(old!=new).tolist()==[96]

def test_terminal_is_actual_last_destination_without_added_return_to_origin():
    c=case();paths={'M':[192]+list(range(97,192))}
    ids,point=values_for(c,paths,lambda u,t:False)
    assert point[96]==0. and point[193]==1. and float((c.A@point)[0])==1.
