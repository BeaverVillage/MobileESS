"""Static exact presolve. Every algebraic deletion stores its local equation.

No optimizer, historical primal values or deletion verifier is used here.
Non-unit/dense pivots are cost-audited and retained, never rounded away.
"""
from fractions import Fraction as F
from collections import Counter,defaultdict
import hashlib,struct,time,math
import numpy as np
from scipy import sparse
from .formulation import census

def represent(x):
    y=float(x)
    if not math.isfinite(y) or F(y)!=x:raise ValueError('NONREPRESENTABLE_EXACT_COEFFICIENT')
    return y

class Presolve:
    def __init__(self,A,d):
        self.A=A.copy();self.d={k:v.copy() if isinstance(v,np.ndarray) else v for k,v in d.items()}
        self.row_ids=np.arange(A.shape[0]);self.col_ids=np.arange(A.shape[1]);self.steps=[];self.rounds=[];self.rows=[];self.bound=[];self.costs={};self.rejected=[]
        self.initial_names=d['names'].copy();self.initial_d=d;self.fixed_known={}
    def row_delete(self,gone,proofs):
        if not gone:return
        keep=np.asarray([i for i in range(self.A.shape[0]) if i not in gone]);self.rows.extend(proofs)
        self.A=self.A[keep];self.row_ids=self.row_ids[keep]
        for k in ['rhs','sense','row_names']:self.d[k]=self.d[k][keep]
    def substitute(self,plans):
        if not plans:return 0
        A,d=self.A,self.d;n=A.shape[1];gone=set(plans);keep=[j for j in range(n) if j not in gone];pos={j:k for k,j in enumerate(keep)}
        # Independent simultaneous pivots must depend only on retained columns.
        assert all(not gone.intersection(expr) for expr,const,row,kind in plans.values())
        rr=[];cc=[];vv=[];off=np.zeros(n)
        for j in keep:rr.append(j);cc.append(pos[j]);vv.append(1.)
        for j,(expr,c,row,kind) in plans.items():
            off[j]=c
            for k,w in expr.items():rr.append(j);cc.append(pos[k]);vv.append(w)
        T=sparse.csr_matrix((vv,(rr,cc)),shape=(n,len(keep)))
        C=(A@T).tocsr();C.eliminate_zeros();C.sort_indices();rhs=d['rhs']-A@off
        objective=np.asarray(d['objective']@T).ravel();constant=float(d['constant'])+float(d['objective']@off)
        affected=np.unique(A[:,sorted(gone)].tocoo().row)
        # Stored binary rationals must survive sparse sums exactly, including RHS.
        rejected=set()
        for i in affected:
            expr=defaultdict(F);r=F(float(d['rhs'][i]))
            a,b=A.indptr[i:i+2]
            for j,w in zip(A.indices[a:b],A.data[a:b]):
                if j in plans:
                    terms,k,_,_=plans[j];r-=F(float(w))*F(float(k))
                    for q,v in terms.items():expr[pos[q]]+=F(float(w))*F(float(v))
                else:expr[pos[int(j)]]+=F(float(w))
            a,b=C.indptr[i:i+2];actual=dict(zip(C.indices[a:b],C.data[a:b]));expr={k:v for k,v in expr.items() if v}
            assert set(actual)==set(expr)
            try:
                exactvalues={j:represent(v) for j,v in expr.items()};exactrhs=represent(r)
            except ValueError:
                rejected.update(int(j) for j in A.indices[A.indptr[i]:A.indptr[i+1]] if j in plans)
                continue
            # Use the exact representable result, avoiding summation-order rounding.
            for q in range(a,b):C.data[q]=exactvalues[int(C.indices[q])]
            rhs[i]=exactrhs
        if rejected:
            self.rejected.extend(dict(column=int(self.col_ids[j]),reason='Exact substituted coefficient/RHS is not representable in original binary64 numerical authority') for j in sorted(rejected))
            return self.substitute({j:p for j,p in plans.items() if j not in rejected})
        defs={int(row) for expr,c,row,kind in plans.values() if row is not None}
        for j,(expr,c,row,kind) in plans.items():
            self.steps.append(dict(column=int(self.col_ids[j]),name=str(d['names'][j]),kind=kind,constant=c,
                terms={str(int(self.col_ids[k])):w for k,w in expr.items()},defining_row=int(self.row_ids[row]) if row is not None else None,
                old_lower=float(d['lower'][j]),old_upper=float(d['upper'][j]),proof='Exact defining equality or identical original variable bounds; substituted bounds independently checked.'))
        self.A=C;self.d=dict(d,rhs=rhs,objective=objective,constant=np.asarray(constant),**{k:d[k][keep] for k in ['names','types','lower','upper']});self.col_ids=self.col_ids[keep]
        self.row_delete(defs,[dict(row=int(self.row_ids[i]),kind='ELIMINATED_DEFINITION',proof='Stored inverse reconstruction equality',round=len(self.rounds)) for i in defs])
        return len(plans)
    def fixed(self):
        A,d=self.A,self.d;plans={}
        # All singleton equalities imply fixed constants, even with unbounded auxiliary LB/UB.
        for i in np.flatnonzero((np.diff(A.indptr)==1)&(d['sense']=='=')):
            a=A.indptr[i];j=int(A.indices[a]);v=F(float(d['rhs'][i]))/F(float(A.data[a]))
            try:c=represent(v)
            except ValueError:continue
            if not d['lower'][j]<=c<=d['upper'][j]:raise ValueError('EXACT_FIXED_CONTRADICTION')
            if j in plans:assert plans[j][1]==c
            else:plans[j]=({},c,int(i),'FIXED_ZERO' if c==0 else 'FIXED_CONSTANT')
            identity=int(self.col_ids[j]);self.fixed_known[identity]=dict(column=identity,name=str(d['names'][j]),kind='FIXED_ZERO' if c==0 else 'FIXED_CONSTANT',constant=c,defining_row=int(self.row_ids[i]),proof='Exact singleton equality; bounds fix value even if numerical-authority-preserving elimination is unavailable')
            if d['lower'][j]!=c or d['upper'][j]!=c:
                self.bound.append(dict(column=identity,name=str(d['names'][j]),old_lower=float(d['lower'][j]),old_upper=float(d['upper'][j]),new_lower=c,new_upper=c,proof='SINGLETON_EQUALITY:'+str(int(self.row_ids[i]))))
                d['lower'][j]=d['upper'][j]=c
        for j in np.flatnonzero(d['lower']==d['upper']):
            plans.setdefault(int(j),({},float(d['lower'][j]),None,'FIXED_ZERO' if d['lower'][j]==0 else 'FIXED_CONSTANT'))
        return self.substitute(plans)
    def row_scan(self):
        A,d=self.A,self.d;groups={};gone=set();proofs=[];unknown=0;categories=Counter()
        # Exact primitive dyadic vectors identify proportional equality/inequality rows.
        for i in range(A.shape[0]):
            a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b];sg=-1 if d['sense'][i]=='>' else 1;s='=' if d['sense'][i]=='=' else '<';rhs=F(sg*float(d['rhs'][i]))
            if not len(js):
                safe=(rhs==0 if s=='=' else rhs>=0)
                if not safe:raise ValueError('CONSTANT_INFEASIBLE_ROW')
                gone.add(i);proofs.append(dict(row=int(self.row_ids[i]),kind='CONSTANT_SAFE',rhs=str(rhs),round=len(self.rounds)));categories['CONSTANT_SAFE']+=1;continue
            if s=='=' and all(d['lower'][j]==d['upper'][j] for j in js):
                assert sum(F(sg*float(w))*F(float(d['lower'][j])) for j,w in zip(js,ws))==rhs
                gone.add(i);proofs.append(dict(row=int(self.row_ids[i]),kind='FIXED_BOUND_EQUALITY',round=len(self.rounds)));categories['FIXED_BOUND_EQUALITY']+=1;continue
            rat=[(sg*float(w)).as_integer_ratio() for w in ws];den=max(q for p,q in rat);ints=[p*(den//q) for p,q in rat];g=math.gcd(*ints);ints=[p//g for p in ints]
            if s=='=' and ints[0]<0:ints=[-v for v in ints]
            scale=F(sg*float(ws[0]))/ints[0];rr=rhs/scale
            key=(s,js.tobytes(),tuple(ints))
            if key in groups:
                rep,old=groups[key]
                if (s=='=' and rr==old) or (s=='<' and rr>=old):
                    gone.add(i);proofs.append(dict(row=int(self.row_ids[i]),kind='EXACT_PROPORTIONAL_IMPLICATION',representative=int(self.row_ids[rep]),round=len(self.rounds)));categories['PROPORTIONAL']+=1;continue
                if s=='<' and rr<old:
                    gone.add(rep);proofs.append(dict(row=int(self.row_ids[rep]),kind='EXACT_PROPORTIONAL_IMPLICATION',representative=int(self.row_ids[i]),round=len(self.rounds)));groups[key]=(i,rr);categories['DOMINATED']+=1
            else:groups[key]=(i,rr)
            if s=='<' and len(js)==1:
                w=F(sg*float(ws[0]));j=int(js[0]);v=float(d['upper'][j] if w>0 else d['lower'][j])
                if abs(v)<1e90 and w*F(v)<=rhs:
                    gone.add(i);proofs.append(dict(row=int(self.row_ids[i]),kind='SINGLETON_BOUND_IMPLIED',round=len(self.rounds)));categories['SINGLETON_BOUND_IMPLIED']+=1
            unknown+=int(i not in gone)
        self.row_delete(gone,proofs)
        return len(gone),dict(categories)
    def audit_pivots(self,execute=True):
        A,d=self.A,self.d;C=A.tocsc();defs={};families=[str(n).split('[')[0] for n in d['names']]
        # Minimum-support exact equation per variable, preferring its native grid binding.
        for i in np.flatnonzero(d['sense']=='='):
            a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b]
            if len(js)<2:continue
            for j,w in zip(js,ws):
                if abs(w)!=1:continue
                j=int(j);fam=families[j];grid=fam.startswith(('response_','injection_'));flow=fam=='route_flow';node=fam=='node_activity'
                if not(grid or flow or node):continue
                if grid and str(d['row_names'][i]).split('[')[0]!=fam+'_binding':continue
                if j not in defs or len(js)<defs[j][0]:defs[j]=(len(js),int(i),float(w))
        plans={};reserved=set();aliases={};costs=[];rowsets={}
        def rowset(q):
            if q not in rowsets:rowsets[q]=set(map(int,A.indices[A.indptr[q]:A.indptr[q+1]]))
            return rowsets[q]
        for j,(length,i,pivot) in sorted(defs.items(),key=lambda v:(v[1][0],v[0])):
            a,b=A.indptr[i:i+2];expr={int(k):-float(w)/pivot for k,w in zip(A.indices[a:b],A.data[a:b]) if k!=j};constant=float(d['rhs'][i])/pivot
            consumers=C.indices[C.indptr[j]:C.indptr[j+1]];down=[int(q) for q in consumers if q!=i];before=int(sum(A.indptr[q+1]-A.indptr[q] for q in down)+length)
            after=0;afterfill=0;exprset=set(expr)
            for q in down:
                size=len(rowset(q)|exprset)-1;after+=size;afterfill+=size**2
            delta=after-before;positive=sum(abs(w) for w in expr.values());cfmin=min(map(abs,expr.values()));cfmax=max(map(abs,expr.values()))
            record=dict(column=int(self.col_ids[j]),name=str(d['names'][j]),definition=int(self.row_ids[i]),definition_nnz=length,consumers=len(down),rows_saved=1,columns_saved=1,
                nnz_before=before,nnz_after_union_upper=after,nnz_delta_upper=delta,fill_proxy_before=sum((A.indptr[q+1]-A.indptr[q])**2 for q in down)+length**2,
                fill_proxy_after=afterfill,
                expression_coefficient_min=cfmin,expression_coefficient_max=cfmax,decision='KEEP',reason='Substitution not structurally beneficial or safe bound transport unavailable')
            kind='UNIQUE_DEFINITION'
            if length==2 and list(expr.values())[0]==1 and constant==0:
                k=next(iter(expr));samebounds=d['lower'][k]>=d['lower'][j] and d['upper'][k]<=d['upper'][j]
                integerok=d['types'][j]!='B' or d['types'][k]=='B'
                if delta<0 and samebounds and integerok and j not in reserved and k not in plans and i not in reserved:
                    if execute:
                        plans[j]=(expr,constant,i,'DETERMINISTIC_FLOW' if families[j]=='route_flow' else 'DUPLICATE_AUXILIARY');reserved.add(k)
                    record.update(decision='SUBSTITUTE' if execute else 'ELIGIBLE',reason='Unit alias; retained dependency bounds imply eliminated bounds; exact nnz decrease; no coefficient multiplication')
            # Identical affine auxiliaries (same stored RHS/dependencies) allow unit alias.
            if families[j].startswith(('response_','injection_')):
                key=(tuple(sorted(expr.items())),constant)
                if key in aliases and j not in plans and j not in reserved:
                    k,ri=aliases[key]
                    if k not in plans and d['lower'][k]>=d['lower'][j] and d['upper'][k]<=d['upper'][j]:
                        # Definition removed; consumers rename j to k, possibly cancel exact equal coefficients.
                        if execute:plans[j]=({k:1.},0.,i,'DUPLICATE_AUXILIARY');reserved.add(k)
                        record.update(decision='SUBSTITUTE' if execute else 'ELIGIBLE',reason='Identical exact affine definitions, unit alias without scaling',nnz_delta_upper=-length,fill_proxy_after=record['fill_proxy_before']-length**2)
                elif j not in plans:aliases[key]=(j,i)
            costs.append(record);self.costs[record['column']]=record
        if not execute:return 0,costs
        # Guard against definition rows simultaneously selected through different variables.
        unique={};used=set()
        for j,p in plans.items():
            if p[2] not in used:unique[j]=p;used.add(p[2])
        # A retained dependency cannot become eliminated elsewhere in this batch.
        dependencies={k for p in unique.values() for k in p[0]}
        unique={j:p for j,p in unique.items() if j not in dependencies}
        n=self.substitute(unique)
        accepted={int(self.steps[-k]['column']) for k in range(1,n+1)} if n else set()
        for rec in costs:
            if rec['decision']=='SUBSTITUTE' and rec['column'] not in accepted:rec.update(decision='KEEP',reason='Batch dependency conflict; reconsider next round')
            self.costs[rec['column']]=rec
        return n,costs
    def run(self):
        while True:
            start=time.perf_counter();before=(self.A.shape,self.A.nnz);fixed=self.fixed();rows,cat=self.row_scan();subs,_=self.audit_pivots();after=(self.A.shape,self.A.nnz)
            self.rounds.append(dict(round=len(self.rounds)+1,rows_before=before[0][0],columns_before=before[0][1],nnz_before=before[1],fixed=fixed,rows_deleted=rows,substitutions=subs,rows_after=after[0][0],columns_after=after[0][1],nnz_after=after[1],wall=time.perf_counter()-start,categories=str(cat)))
            print('STATIC_ROUND',self.rounds[-1],flush=True)
            if before==after:break
        return self.A,self.d
    def forward(self,x):return np.asarray(x)[self.col_ids].copy()
    def inverse(self,y):
        x=np.zeros(len(self.initial_names));x[self.col_ids]=y
        for p in reversed(self.steps):x[p['column']]=p['constant']+sum(w*x[int(k)] for k,w in p['terms'].items())
        return x
