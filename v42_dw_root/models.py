from .common import *
import hashlib
import numpy as np
import gurobipy as gp
from v42_integrated.matrix import arrays,audit
from v42_degen.identity import signature,digest
from v42_strengthening.analysis import graph_inputs
from fractions import Fraction as F

def subset(e,rows,cols,rownames):
    return dict(names=e['names'][cols],rhs=e['rhs'][rows],sense=e['sense'][rows],lower=e['lower'][cols],upper=e['upper'][cols],types=e['types'][cols],objective=e['objective'][cols],constant=np.array(0.),row_names=rownames[rows])
def build(A,d,name):
    m=gp.Model(name);m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.Threads=1
    x=m.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],obj=d['objective'],vtype='C')
    m.update();vs=m.getVars();m.setAttr('VType',vs,d['types'].tolist());m.setAttr('VarName',vs,d['names'].tolist())
    m.addMConstr(A,x,d['sense'],d['rhs']);m.update();m.setAttr('ConstrName',m.getConstrs(),d['row_names'].tolist());m.ObjCon=float(d['constant']);m.update()
    B,e=arrays(m)
    assert np.array_equal(B.indptr,A.indptr) and np.array_equal(B.indices,A.indices) and np.array_equal(B.data,A.data)
    for key in ('names','rhs','sense','lower','upper','types','objective','constant','row_names'):
        assert np.array_equal(e[key],d[key]),('NATIVE_BLOCK_TRANSPORT_FAILED',key)
    return m
def hash_column(x,a,c):
    h=hashlib.sha256()
    for v in (np.asarray(x,dtype=np.float64),np.asarray(a,dtype=np.float64),np.asarray([c],dtype=np.float64)):
        h.update(str(v.shape).encode());h.update(v.tobytes())
    return h.hexdigest()

class Block:
    def __init__(self,B,e,owner,row_owner,native,m):
        self.unit=UNITS[m];self.columns=np.flatnonzero(owner==m);self.rows=np.flatnonzero(row_owner==m);self.global_rows=np.flatnonzero(row_owner==-1)
        self.A=B[self.rows][:,self.columns];self.B=B[self.global_rows][:,self.columns];self.d=subset(e,self.rows,self.columns,native)
        self.model=build(self.A,self.d,'DW_PRICE_'+self.unit);self.vars=self.model.getVars();self.mask=self.d['types']!='C'
        self.sites,self.initial,self.arcs,self.battery,self.graph=graph_inputs()
        self.CSC=self.B.tocsc()
        # Actual coupling graph has one native injection +/-1 entry per P/Q
        # coordinate, no coupling entry for route/mode/SOC. Thus pricing
        # coefficients c-B'Pi are exact sign changes, with no sum rounding.
        assert np.all(np.diff(self.CSC.indptr)<=1) and np.all(np.abs(self.CSC.data)==1.)
    def price(self,pi,alpha):
        cost=self.d['objective']-self.B.T@pi
        for j in np.flatnonzero(np.diff(self.CSC.indptr)):
            k=self.CSC.indptr[j];assert cost[j]==self.d['objective'][j]-self.CSC.data[k]*pi[self.CSC.indices[k]]
        self.model.setAttr('Obj',self.vars,cost.tolist());self.model.ObjCon=-float(alpha);self.model.update()
        return np.asarray(cost)
    def validate(self,x,physical=True):
        raw=audit(self.A,self.d,x,integral=True,tolerance=1e-8);exact=np.array_equal(x[self.mask],np.rint(x[self.mask]))
        result=dict(PASS=raw['PASS'] and exact,raw=raw,integer_pattern_exact=exact,repairs=0)
        if not result['PASS'] or not physical:return result
        from v42_native.mess import validate
        from v42_bootstrap.attribution import supplemental_physical
        values=dict(zip(map(str,self.d['names']),map(float,x)));u=self.unit
        for k in range(len(self.arcs)):values.setdefault(f'arc[{u},{k}]',0.)
        for s in self.sites:
            for t in range(96):
                for f in ('Pch','Pdis','Q'):values.setdefault(f'{f}[{u},{s},{t}]',0.)
        chosen=[k for k in range(len(self.arcs)) if values[f'arc[{u},{k}]']>.5]
        plan=dict(values=values,initial_sites={u:self.initial[u]},chosen_arcs={u:chosen},mode='MILP')
        routes=[a[-1] for a in self.arcs if a[-1] is not None]
        route=validate(plan,self.sites,routes,self.battery,96);extra=supplemental_physical(plan,self.sites,self.battery)
        result.update(PASS=bool(result['PASS'] and route['PASS'] and extra['charge_mode_and_connection_PASS']),route_SOC_PCS=route,mode_connection=extra,
                      movement_count=sum(self.arcs[k][-1] is not None for k in chosen),movement_energy=sum(self.arcs[k][-1].energy_kwh for k in chosen if self.arcs[k][-1] is not None),
                      native_unreachable_zero_constants_only=True)
        return result
    def column(self,x):
        a=np.asarray(self.B@x).ravel();c=float(self.d['objective']@x)
        return a,c,hash_column(x,a,c)
    def exact_coupling(self,x,a):
        exact={};coo=self.B.tocoo()
        for i,j,w in zip(coo.row,coo.col,coo.data):
            if x[j]!=0:exact[int(i)]=exact.get(int(i),F(0))+F(float(w))*F(float(x[j]))
        error=max((abs(q-F(float(a[i]))) for i,q in exact.items()),default=F(0))
        return exact,float(error)
    def census(self):
        m=self.model
        return dict(MESS=self.unit,rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs,
                    signature=signature(self.A,self.d),native_row_names_SHA=digest(self.d['row_names']),full_original_domain=True,horizon=96,all_original_local_rows=True,
                    pricing_cost_exact_sign_changes=True,coupling_nnz=self.B.nnz,original_route_domain_SHA=self.graph['route_file']['sha256'])

class Master:
    def __init__(self,B,e,owner,row_owner,native):
        self.columns=np.flatnonzero(owner==-1);self.rows=np.flatnonzero(row_owner==-1);self.A=B[self.rows][:,self.columns]
        self.d=subset(e,self.rows,self.columns,native);self.d['constant']=e['constant'];assert np.all(self.d['types']=='C')
        self.model=build(self.A,self.d,'DW_ROOT_RMP');self.z=self.model.getVars();self.coupling=self.model.getConstrs()
        self.conv=[self.model.addConstr(gp.LinExpr()==1,name=f'DW_convexity[{u}]') for u in UNITS];self.model.update()
        self.lambdas=[];self.column_data=[]
    def add(self,m,x,a,c,key):
        ix=np.flatnonzero(a);column=gp.Column(a[ix].tolist()+[1.],[self.coupling[i] for i in ix]+[self.conv[m]])
        v=self.model.addVar(lb=0,obj=c,name=f'lambda[{UNITS[m]},{len(self.lambdas)}]',column=column)
        self.lambdas.append(v);self.column_data.append(dict(unit=m,x=x.copy(),a=a,c=c,key=key));self.model.update()
    def raw_audit(self):
        z=np.asarray(self.model.getAttr('X',self.z));res=self.A@z-self.d['rhs']
        for v,c in zip(self.lambdas,self.column_data):res+=float(v.X)*c['a']
        s=self.d['sense'];vio=np.maximum(0,np.where(s=='=',abs(res),np.where(s=='<',res,-res)))
        convex=max(abs(sum(v.X for v,c in zip(self.lambdas,self.column_data) if c['unit']==m)-1) for m in range(4))
        bounds=max(float(np.maximum(self.d['lower']-z,0).max()),float(np.maximum(z-self.d['upper'],0).max()),max(-v.X for v in self.lambdas))
        return dict(PASS=bool(np.isfinite(z).all() and vio.max(initial=0)<=1e-8 and convex<=1e-8 and bounds<=1e-8),master_row_max_violation=float(vio.max(initial=0)),convexity_max_violation=float(convex),bounds_max_violation=float(max(0,bounds)))
