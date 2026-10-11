"""Small exact C3A implication and bound attacks; no native optimizer."""
from copy import deepcopy
from math import cos, sin, pi
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse

from v42_supercompact.formulation import Compact
from v42_supercompact.presolve import Presolve
from v42_may_campaign_native90.m_model import verify_transport
from v42_ultracompact.current import reduce_current_c3a, POLICY
from v42_ultracompact.current_verify import verify_current_c3a

def fixture(H=2):
    from v42_native.mess import RouteArc
    sites=('A','B');initial={'MESS01':'A'}
    route=RouteArc('AB','A','B',0,1,1,1.,'a'*64)
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(H)]+[('A',0,'B',1,route)]
    live=list(range(H))+list(range(H+1,2*H))+[2*H]
    states=[('A',t,t) for t in range(H)]+[('B',t,H+t) for t in range(1,H)]
    names=[f'arc[MESS01,{k}]' for k in live]
    for s,t,k in states:names.extend(f'{f}[MESS01,{s},{t}]' for f in ('Pch','Pdis','Q'))
    names+=[f'response_line_P[{t},0]' for t in range(H)]+['rho_max'];pos={n:j for j,n in enumerate(names)}
    n=len(names);lo=np.zeros(n);hi=np.ones(n);types=np.full(n,'C');types[:len(live)]='B';rows=[];rhs=[];sense=[];labels=[]
    def add(terms,r,s,label):rows.append({pos[k]:v for k,v in terms.items() if v});rhs.append(r);sense.append(s);labels.append(label)
    for site in sites:
        for t in range(H):
            terms={}
            for k in live:
                a=arcs[k];v=int(a[:2]==(site,t))-int(a[2:4]==(site,t))
                if v:terms[f'arc[MESS01,{k}]']=v
            add(terms,int(site=='A' and t==0),'=','flow')
    add({f'arc[MESS01,{k}]':1 for k in live if arcs[k][3]==H},1,'=','terminal_location')
    for site,t,k in states:
        ch,pd,q=(f'{f}[MESS01,{site},{t}]' for f in ('Pch','Pdis','Q'));mass=f'arc[MESS01,{k}]'
        hi[pos[ch]]=hi[pos[pd]]=300;lo[pos[q]]=-400;hi[pos[q]]=400
        add({ch:1,mass:-300},0,'<','connected_Pch');add({pd:1,mass:-300},0,'<','connected_Pdis')
        add({q:1,mass:-400},0,'<','connected_Qmax');add({q:1,mass:400},0,'>','connected_Qmin')
        for f in range(16):
            p=cos(2*pi*f/16);qq=sin(2*pi*f/16)
            add({pd:p,ch:-p,q:qq,mass:-400*cos(pi/16)},0,'<','PCS16')
    for t in range(H):
        target=f'response_line_P[{t},0]';lo[pos[target]]=-np.inf;hi[pos[target]]=np.inf
        terms={target:1}
        for site,tt,k in states:
            if tt==t:
                terms[f'Pdis[MESS01,{site},{t}]']=-.25;terms[f'Pch[MESS01,{site},{t}]']=.25
                terms[f'Q[MESS01,{site},{t}]']=-.125
        add(terms,1+t,'=',f'response_line_P_binding[{t},0]')
    rr=[];cc=[];vv=[]
    for i,row in enumerate(rows):
        for j,v in row.items():rr.append(i);cc.append(j);vv.append(v)
    A=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),n));obj=np.zeros(n);obj[-1]=1
    d=dict(names=np.asarray(names),lower=lo,upper=hi,types=types,objective=obj,constant=np.asarray(0.),rhs=np.asarray(rhs,float),sense=np.asarray(sense),row_names=np.asarray(labels))
    battery=SimpleNamespace(p_limit=300.,pcs_kva=400.)
    graph=(sites,initial,arcs,battery,{})
    compact=Compact(A,d,arcs,initial,H);presolve=Presolve(compact.A,compact.d);presolve.run()
    assert verify_transport(compact,presolve)['PASS']
    return reduce_current_c3a(presolve.A,presolve.d,graph,physical_original=(A,d)),graph,compact,presolve

def test_selected_current_c3a_is_real_lp_exact_reduction():
    ultra,graph,_,_=fixture()
    assert ultra.proof['PASS'] and ultra.proof['C3A_policy']==POLICY
    assert ultra.proof['removed_row_methods']['PCS_FARKAS']>=18
    assert ultra.proof['removed_row_methods']['Q_LINK_FARKAS']>=4
    assert ultra.proof['bounds_tightened']==2
    assert ultra.proof['baseline']['columns']==ultra.proof['selected']['columns']
    assert ultra.proof['baseline']['binaries']==ultra.proof['selected']['binaries']
    assert ultra.proof['selected']['nnz']<ultra.proof['baseline']['nnz']
    assert ultra.proof['Native_optimize_calls']==0
    assert verify_current_c3a(ultra,graph)['objective_and_integer_and_full_LP_domains_preserved']

@pytest.mark.parametrize('attack',('negative_weight','removed_support','retained_coefficient','objective','unsafe_bound','missing_bound','row_axis','original_pcs'))
def test_current_c3a_rejects_mutations(attack):
    ultra,graph,_,_=fixture();ultra=deepcopy(ultra)
    if attack=='negative_weight':ultra.certificates[0]['support'][0]['weight']='-1'
    elif attack=='removed_support':
        c=next(p for p in ultra.certificates if p['kind']=='PCS_FARKAS');c['support'][0]['row']=c['row']
    elif attack=='retained_coefficient':ultra.A.data[0]=np.nextafter(ultra.A.data[0],np.inf)
    elif attack=='objective':ultra.d['objective']=ultra.d['objective'].copy();ultra.d['objective'][-1]=2
    elif attack=='unsafe_bound':
        p=ultra.bounds[0];p['new_upper']=0.;ultra.d['upper'][p['column']]=0.
    elif attack=='missing_bound':ultra.bounds.pop()
    elif attack=='row_axis':ultra.row_ids[0]=ultra.row_ids[1]
    else:
        i=next(i for i,n in enumerate(ultra.physical_original_data['row_names']) if n=='PCS16')
        ultra.physical_original.data[ultra.physical_original.indptr[i]]*=2
    with pytest.raises(ValueError,match='CURRENT_C3A_'):verify_current_c3a(ultra,graph)

def test_presolve_does_not_copy_immutable_csr_or_mutate_input_bounds():
    ultra,graph,compact,_=fixture();lo=compact.d['lower'].copy();hi=compact.d['upper'].copy()
    p=Presolve(compact.A,compact.d)
    assert p.A is compact.A
    p.run()
    assert np.array_equal(compact.d['lower'],lo) and np.array_equal(compact.d['upper'],hi)
