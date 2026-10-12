"""Sparse node-flow formulation from current CSR authority, no historical matrix."""
from collections import defaultdict,Counter
import re
import numpy as np
from scipy import sparse
from v42_degen.identity import signature

def census(A,d):
    def stats(v):
        return dict(min=int(v.min()) if len(v) else 0,max=int(v.max()) if len(v) else 0,mean=float(np.mean(v)),quantiles={str(q):float(np.quantile(v,q)) for q in [0,.25,.5,.75,.9,.99,1]})
    a=np.abs(A.data[A.data!=0]);b=int(np.sum(d['types']=='B'));c=int(np.sum(d['types']=='C'))
    return dict(rows=A.shape[0],columns=A.shape[1],binaries=b,continuous=c,nnz=A.nnz,
        coefficient_range=[float(a.min()),float(a.max())] if len(a) else None,
        nnz_per_row=stats(np.diff(A.indptr)),nnz_per_column=stats(np.diff(A.tocsc().indptr)),
        row_families=dict(Counter(str(n).split('[')[0] for n in d['row_names'])),
        column_families=dict(Counter(str(n).split('[')[0] for n in d['names'])),signature=signature(A,d))

class Compact:
    def __init__(self,A,d,arcs,initial,H,arc_columns=None):
        self.original=A;self.original_data=d;self.arcs=arcs;self.initial=initial;self.H=H
        self.arc_columns={}
        if arc_columns is None:
            for j,n in enumerate(d['names']):
                m=re.fullmatch(r'arc\[([^,]+),(\d+)\]',str(n))
                if m:self.arc_columns[m[1],int(m[2])]=j
        else:self.arc_columns=dict(arc_columns)
        groups=defaultdict(list)
        for k,a in enumerate(arcs):
            assert 0<=a[1]<a[3]<=H
            groups[a[:4]].append(k)
        parallel={k for v in groups.values() if len(v)>1 for k in v}
        outgoing=defaultdict(list);incoming=defaultdict(list);nodes=set()
        for (u,k),j in self.arc_columns.items():
            s,t,z,v=arcs[k][:4];outgoing[u,s,t].append(j);incoming[u,z,v].append(j)
            nodes.update([(u,s,t),(u,z,v)])
            assert d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1
        self.nodes=sorted(nodes,key=lambda x:(x[0],x[2],x[1]));self.n=A.shape[1]
        self.z={key:self.n+k for k,key in enumerate(self.nodes)}
        self.outgoing=outgoing;self.incoming=incoming;self.parallel=parallel
        names=list(map(str,d['names']));types=list(d['types']);lo=list(d['lower']);hi=list(d['upper'])
        for (u,k),j in self.arc_columns.items():
            names[j]=f'route_flow[{u},{k}]';types[j]='B' if k in parallel else 'C'
        rr=[];cc=[];vv=[];rn=[]
        for i,key in enumerate(self.nodes):
            u,s,t=key;names.append(f'node_activity[{u},{s},{t}]');types.append('B');lo.append(0.);hi.append(1.)
            # Source fix is left to C2 exact presolve; C0 links plus original flow imply it.
            rr.append(i);cc.append(self.z[key]);vv.append(1.)
            for j in (incoming[key] if t==H else outgoing[key]):rr.append(i);cc.append(j);vv.append(-1.)
            rn.append(f'node_activity_link[{u},{s},{t}]')
        links=sparse.csr_matrix((vv,(rr,cc)),shape=(len(self.nodes),len(names)))
        self.A=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],len(self.nodes)))],format='csr'),links],format='csr')
        self.d=dict(d,names=np.asarray(names),types=np.asarray(types),lower=np.asarray(lo),upper=np.asarray(hi),
            objective=np.r_[d['objective'],np.zeros(len(self.nodes))],rhs=np.r_[d['rhs'],np.zeros(len(self.nodes))],
            sense=np.r_[d['sense'],np.full(len(self.nodes),'=')],row_names=np.r_[d['row_names'],np.asarray(rn)])
    def forward(self,x):
        y=np.r_[np.asarray(x),np.zeros(len(self.nodes))]
        for key,j in self.z.items():y[j]=sum(x[k] for k in (self.incoming[key] if key[2]==self.H else self.outgoing[key]))
        return y
    def inverse(self,y):return np.asarray(y)[:self.n].copy()
    def mapping(self):
        return dict(original_columns=self.n,compact_columns=self.A.shape[1],route_columns=len(self.arc_columns),node_activity=len(self.nodes),
            parallel_selector_columns=sum(k in self.parallel for u,k in self.arc_columns),
            nodes=[dict(key=list(key),column=j,terms=(self.incoming[key] if key[2]==self.H else self.outgoing[key])) for key,j in self.z.items()],
            original_columns_copied_identically=True,physical_decisions_changed=False)

def subset(A,d,keep):
    return A[keep],dict(d,**{k:d[k][keep] for k in ['rhs','sense','row_names']})

def residual(A,d,x):
    r=A@x-d['rhs'];v=np.where(d['sense']=='=',abs(r),np.where(d['sense']=='<',r,-r))
    return dict(max_row_violation=float(np.max(v,initial=0)),max_bound_violation=float(max(np.max(d['lower']-x,initial=0),np.max(x-d['upper'],initial=0))),
        max_integrality_violation=float(np.max(abs(x[d['types']=='B']-np.rint(x[d['types']=='B'])),initial=0)))
