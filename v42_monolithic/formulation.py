"""Exact sparse linear substitution of stay arcs by z minus departures."""
from collections import defaultdict,Counter
from dataclasses import asdict
from fractions import Fraction as F
import re,time
import numpy as np
from scipy import sparse
import gurobipy as gp

class Compact:
    def __init__(self,original,graph,initial,horizon):
        self.original=original;self.graph=graph;self.initial=initial;self.H=horizon
        self.old_names=np.array(original.getAttr('VarName'));self.old_types=np.array(original.getAttr('VType'));self.oldA=original.getA().tocsr()
        self.old_b=np.array(original.getAttr('RHS'));self.old_sense=np.array(original.getAttr('Sense'));self.old_lb=np.array(original.getAttr('LB'));self.old_ub=np.array(original.getAttr('UB'));self.old_c=np.array(original.getAttr('Obj'))
        self.arc_columns={};self.stays={};self.outgoing=defaultdict(list);self.incoming=defaultdict(list);self.node_arcs=defaultdict(list)
        groups=defaultdict(list)
        for k,a in enumerate(graph):
            assert a[1]<a[3]<=horizon,'NOT_DAG_TIME_ORDER'
            groups[a[:4]].append(k)
        self.parallel={key:ks for key,ks in groups.items() if len(ks)>1}
        self.parallel_ks={k for ks in self.parallel.values() for k in ks}
        for j,name in enumerate(self.old_names):
            match=re.fullmatch(r'arc\[([^,]+),(\d+)\]',str(name))
            if match:
                unit,k=match[1],int(match[2]);assert 0<=k<len(graph) and self.old_types[j]=='B' and self.old_lb[j]==0 and self.old_ub[j]==1
                self.arc_columns[unit,k]=j;a=graph[k]
                self.node_arcs[unit,a[0],a[1]].append(k)
                if a[-1] is None:self.stays[unit,a[0],a[1]]=j
                else:self.outgoing[unit,a[0],a[1]].append(k);self.incoming[unit,a[2],a[3]].append(k)
        staycols=set(self.stays.values());self.keep=np.array([j for j in range(len(self.old_names)) if j not in staycols],dtype=int);self.position={int(j):k for k,j in enumerate(self.keep)}
        nodes=set(self.node_arcs)
        for (unit,k),j in self.arc_columns.items():a=graph[k];nodes.add((unit,a[2],a[3]))
        self.nodes=sorted(nodes,key=lambda v:(v[0],v[2],v[1]));self.z={key:len(self.keep)+k for k,key in enumerate(self.nodes)}
        self.names=list(self.old_names[self.keep]);self.types=list(self.old_types[self.keep]);self.lower=list(self.old_lb[self.keep]);self.upper=list(self.old_ub[self.keep])
        self.movement_columns={};self.selectors=[]
        for (unit,k),j in self.arc_columns.items():
            if graph[k][-1] is None:continue
            p=self.position[j];self.names[p]=f'movement_flow[{unit},{k}]';self.types[p]='B' if k in self.parallel_ks else 'C';self.movement_columns[unit,k]=p
            if k in self.parallel_ks:self.selectors.append(p)
        for unit,site,t in self.nodes:
            self.names.append(f'node_activity[{unit},{site},{t}]');self.types.append('B');self.lower.append(float(t==0 and site==initial[unit]));self.upper.append(float(site==initial[unit]) if t==0 else 1.)
        self.names=np.array(self.names);self.types=np.array(self.types);self.lower=np.array(self.lower);self.upper=np.array(self.upper)
        rows=[];cols=[];data=[]
        for p,j in enumerate(self.keep):rows.append(j);cols.append(p);data.append(1.)
        for key,j in self.stays.items():
            rows.append(j);cols.append(self.z[key]);data.append(1.)
            unit,site,t=key
            for k in self.outgoing[key]:rows.append(j);cols.append(self.movement_columns[unit,k]);data.append(-1.)
        self.T=sparse.csr_matrix((data,(rows,cols)),shape=(len(self.old_names),len(self.names)))
        self.A=(self.oldA@self.T).tocsr();self.c=np.asarray(self.old_c@self.T).ravel()
        # Audit every possible sum of floating coefficients independently as rationals.
        touched=set(int(i) for i in self.oldA[:,list(staycols)].tocoo().row);checks=0
        for i in touched:
            exact={}
            for p in range(self.oldA.indptr[i],self.oldA.indptr[i+1]):
                j=int(self.oldA.indices[p]);a=F.from_float(float(self.oldA.data[p]))
                for q in range(self.T.indptr[j],self.T.indptr[j+1]):
                    k=int(self.T.indices[q]);exact[k]=exact.get(k,F(0))+a*int(self.T.data[q])
            actual=dict(zip(map(int,self.A[i].indices),map(float,self.A[i].data)))
            for j,v in exact.items():assert F.from_float(actual.get(j,0.))==v,'NONEXACT_MATRIX_SUBSTITUTION'
            assert not set(actual)-set(exact);checks+=1
        self.exact_substitution_rows=checks
        # Original stay bounds retained as expression bounds. Terminal node definitions
        # complete the original t=0..H-1 flow equations at t=H.
        er=[];ec=[];ev=[];rhs=[];senses=[];labels=[]
        def add(d,s,b,label):
            i=len(rhs)
            for j,v in d.items():
                if v:er.append(i);ec.append(j);ev.append(v)
            rhs.append(b);senses.append(s);labels.append(label)
        for key,j in self.stays.items():
            d=dict(zip(map(int,self.T[j].indices),map(float,self.T[j].data)))
            add(d,'>',self.old_lb[j],'connected_lower_'+str(key));add(d,'<',self.old_ub[j],'connected_upper_'+str(key))
        for key,z in self.z.items():
            unit,site,t=key
            if t!=horizon:continue
            d={z:1.};previous=(unit,site,t-1)
            if previous in self.stays:
                j=self.stays[previous]
                for k,v in zip(self.T[j].indices,self.T[j].data):d[int(k)]=d.get(int(k),0.)-v
            for k in self.incoming[key]:p=self.movement_columns[unit,k];d[p]=d.get(p,0.)-1.
            add(d,'=',0.,'terminal_node_definition_'+str(key))
        self.extra=sparse.csr_matrix((ev,(er,ec)),shape=(len(rhs),len(self.names)))
        self.extra_b=np.array(rhs);self.extra_sense=np.array(senses);self.extra_names=labels
    def forward(self,old):
        old=np.asarray(old);new=np.zeros(len(self.names));new[:len(self.keep)]=old[self.keep]
        for key,p in self.z.items():
            unit,site,t=key
            if t<self.H:new[p]=sum(old[self.arc_columns[unit,k]] for k in self.node_arcs[key])
            else:
                prev=(unit,site,t-1);new[p]=old[self.stays[prev]] if prev in self.stays else 0.
                new[p]+=sum(old[self.arc_columns[unit,k]] for k in self.incoming[key])
        return new
    def inverse(self,new):return np.asarray(self.T@np.asarray(new)).ravel()
    def connected(self,new,unit,site,t):
        key=(unit,site,t)
        return float(new[self.z[key]]-sum(new[self.movement_columns[unit,k]] for k in self.outgoing[key])) if key in self.z else 0.
    def build(self,env):
        start=time.perf_counter();m=gp.Model('V42_EXACT_NODE_ACTIVITY',env=env)
        self.variables=m.addMVar(len(self.names),lb=self.lower,ub=self.upper,vtype=self.types.tolist());m.update();m.setAttr('VarName',m.getVars(),self.names.tolist())
        m.addMConstr(self.A,self.variables,self.old_sense,self.old_b)
        m.addMConstr(self.extra,self.variables,self.extra_sense,self.extra_b)
        m.setObjective(self.c@self.variables+self.original.ObjCon,gp.GRB.MINIMIZE);m.update()
        expected=sparse.vstack([self.A,self.extra],format='csr');actual=m.getA()
        assert actual.shape==expected.shape and (actual!=expected).nnz==0,'COMPACT_API_MATRIX_TRANSPORT'
        assert np.array_equal(m.getAttr('VType'),self.types) and np.array_equal(m.getAttr('LB'),self.lower) and np.array_equal(m.getAttr('UB'),self.upper)
        self.build_seconds=time.perf_counter()-start;return m
    def residual(self,new):
        r=self.A@new-self.old_b;e=self.extra@new-self.extra_b
        v=np.where(self.old_sense=='=',abs(r),np.where(self.old_sense=='<',r,-r));w=np.where(self.extra_sense=='=',abs(e),np.where(self.extra_sense=='<',e,-e))
        return max(0.,np.max(v,initial=0),np.max(w,initial=0),np.max(self.lower-new,initial=0),np.max(new-self.upper,initial=0))
