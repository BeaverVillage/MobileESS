"""Bounded native MESS assembly; no optimize call. Shared with semantic tests."""
from .common import OUT,write,sha
from .flow import add_flow
import gurobipy as gp
import numpy as np
from v42_native.mess import Battery,RouteArc
from v42_integrated.matrix import arrays

def fixture():
    sites=('a','b');initial={'unit':'a'};H=4
    battery=Battery(1.,9.,5.,5.,3.,4.,.95,.95)
    routes=(RouteArc('ab0','a','b',0,1,2,1.,'a'*64),
            RouteArc('ba1','b','a',1,2,3,2.,'b'*64),
            RouteArc('ab1','a','b',1,2,3,2.,'c'*64))
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(H)]
    arcs += [(r.source,r.depart,r.destination,r.connect,r) for r in routes]
    return sites,initial,arcs,battery,H,routes

def native_pair():
    import v42_native.mess as native
    sites,initial,arcs,battery,H,routes=fixture()
    class Budget:
        stage='M1'
        def check(self):pass
    original=native.optimize;captured=[];base=[]
    def grid(model,p,q):
        return [('rho',model.addVar(lb=0.,ub=1.,name='rho_max')),('reserve_shortfall',0.)]
    def hook(model,context):
        model.update();model.setObjective(model.getVarByName('rho_max'));model.update();base.append(model.copy())
        add_flow(model,sites,initial,arcs,battery,H)
    def capture(model,objectives,*args,**kwargs):
        model.setObjective(objectives[0][1]);model.update()
        captured.append(model.copy())
        return None,dict(optimization_calls=0)
    native.optimize=capture
    try:native.solve('M1',Budget(),sites,initial,routes,battery,H,grid,strengthening_hook=hook)
    finally:native.optimize=original
    return base[0],captured[0]

def build_receipt():
    from scipy import sparse
    from v42_degen.identity import signature
    first,second=native_pair()
    try:
        A,d=arrays(first);B,e=arrays(second)
        assert B[:A.shape[0],A.shape[1]:].nnz==0
        assert signature(A,d)==signature(B[:A.shape[0],:A.shape[1]],{**d,'rhs':e['rhs'][:A.shape[0]],'sense':e['sense'][:A.shape[0]]})
        for key in ('names','objective','lower','upper','types'):
            assert np.array_equal(d[key],e[key][:A.shape[1]])
        assert first.NumBinVars==second.NumBinVars and all(e['types'][A.shape[1]:]=='C')
        OUT.mkdir(parents=True,exist_ok=True)
        sparse.save_npz(OUT/'SOC_FLOW_PROTOTYPE_BASE_A.npz',A)
        sparse.save_npz(OUT/'SOC_FLOW_PROTOTYPE_EXTENDED_A.npz',B)
        np.savez_compressed(OUT/'SOC_FLOW_PROTOTYPE_BASE_DATA.npz',**d)
        np.savez_compressed(OUT/'SOC_FLOW_PROTOTYPE_EXTENDED_DATA.npz',**e)
        result=dict(PASS=True,horizon=4,sites=2,units=1,native_constructor=True,optimization_calls=0,
            base=dict(rows=first.NumConstrs,columns=first.NumVars,binaries=first.NumBinVars,nnz=first.NumNZs),
            extended=dict(rows=second.NumConstrs,columns=second.NumVars,binaries=second.NumBinVars,nnz=second.NumNZs),
            original_rows_columns_objective_preserved=True,no_new_binary=True,
            files={p.name:sha(p) for p in OUT.glob('SOC_FLOW_PROTOTYPE_*.npz')})
        write('SOC_FLOW_NATIVE_PROTOTYPE.json',result)
        return result
    finally:first.dispose();second.dispose()
