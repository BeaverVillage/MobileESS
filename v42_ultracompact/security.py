"""Fresh PR160/161 reductions before exact C2 presolve.

All numbers are the current stored IEEE binary rationals. Security decisions
use outward interval support of the original homogeneous PCS and unit DAG
flow domain. No row ID or operational point is transported from a prior case.
"""
from collections import Counter, defaultdict, OrderedDict
from fractions import Fraction as F
from time import perf_counter
import numpy as np

from .polytope import vertices, down, up
from .support import domains, exact_sources, union_upper
from scipy import sparse

SECURITY_FAMILIES = frozenset(('voltage_upper', 'voltage_lower',
    'line_thermal_face', 'transformer_kVA', 'NormalAmps'))
SOURCES = ('v42_ultracompact/security.py', 'v42_ultracompact/security_verify.py',
    'v42_ultracompact/independent_interval.py',
    'v42_ultracompact/current_verify.py', 'v42_ultracompact/support.py',
    'v42_ultracompact/polytope.py')

def family(n): return str(n).split('[', 1)[0]

def _row(A, d, i):
    a,b=A.indptr[i:i+2];sg=-1 if d['sense'][i]=='>' else 1
    return {int(j):F(sg*float(w)) for j,w in zip(A.indices[a:b],A.data[a:b]) if w},F(sg*float(d['rhs'][i]))

def _pcs(compact, graph):
    # The independent replay checks every physical block. The producer also
    # rejects unequal stored planes instead of borrowing another state's PCS.
    A,d=compact.original,compact.original_data;blocks=defaultdict(list)
    for i,n in enumerate(d['row_names']):
        if family(n)!='PCS16': continue
        v,r=_row(A,d,i);cols={family(d['names'][j]):j for j in v if family(d['names'][j]) in ('Pch','Pdis','Q')}
        axes={str(d['names'][j]).split('[',1)[1][:-1] for j in cols.values()}
        mass=[j for j in v if family(d['names'][j])=='arc']
        if len(axes)!=1 or len(mass)!=1 or r or d['sense'][i]!='<':raise ValueError('CURRENT_SECURITY_PCS_AXIS_DRIFT')
        p=v.get(cols.get('Pdis'),F(0));q=v.get(cols.get('Q'),F(0))
        if v.get(cols.get('Pch'),F(0))!=-p or set(v)-set(cols.values())-set(mass):raise ValueError('CURRENT_SECURITY_PCS_PLANE_DRIFT')
        blocks[axes.pop()].append((p,q,-v[mass[0]]))
    planes=next(iter(blocks.values()),None)
    if planes is None or len(planes)!=16 or any(p!=planes for p in blocks.values()):raise ValueError('CURRENT_SECURITY_UNEQUAL_PCS')
    limit=F(float(graph[3].p_limit));planes=planes+[(F(1),F(0),limit),(F(-1),F(0),limit)]
    points=vertices(planes)
    if not points:raise ValueError('CURRENT_SECURITY_EMPTY_PCS')
    return points

def _soc(A,d,graph):
    """Exact envelope from actual energy rows; fractional flow is sufficient."""
    sites,initial,arcs,battery,_=graph;H=max(a[3] for a in arcs);names={str(n):j for j,n in enumerate(d['names'])}
    endpoints={};balances={};vf=[family(n) for n in d['names']]
    for i,n in enumerate(d['row_names']):
        fam=family(n)
        if fam not in ('initial_SOC','terminal_SOC','energy_balance'):continue
        v,r=_row(A,d,i);soc=[j for j in v if vf[j]=='SOC']
        if d['sense'][i]!='=':raise ValueError('CURRENT_SECURITY_SOC_SENSE_DRIFT')
        if fam!='energy_balance':
            if len(v)!=1 or len(soc)!=1 or v[soc[0]]!=1:raise ValueError('CURRENT_SECURITY_SOC_ENDPOINT_DRIFT')
            u,t=str(d['names'][soc[0]])[4:-1].split(',');endpoints[u,int(t)]=r
            continue
        if len(soc)!=2 or r:raise ValueError('CURRENT_SECURITY_ENERGY_AXIS_DRIFT')
        parsed=[(j,*str(d['names'][j])[4:-1].split(',')) for j in soc]
        parsed.sort(key=lambda p:int(p[2]));(j,u,t),(k,uu,tt)=parsed;t=int(t);tt=int(tt)
        if uu!=u or tt!=t+1 or v[j]!=-1 or v[k]!=1:raise ValueError('CURRENT_SECURITY_ENERGY_SOC_DRIFT')
        charge=set();discharge=set();cost=F(0)
        for q,w in v.items():
            f=vf[q]
            if f=='SOC':continue
            if f in ('Pch','Pdis'):
                owner,site,time=str(d['names'][q]).split('[',1)[1][:-1].split(',')
                if owner!=u or int(time)!=t or d['lower'][q]!=0:raise ValueError('CURRENT_SECURITY_ENERGY_POWER_DRIFT')
                (charge if f=='Pch' else discharge).add(-w if f=='Pch' else w)
            elif f=='route_flow':
                owner,index=str(d['names'][q])[11:-1].split(',');a=arcs[int(index)]
                if owner!=u or a[1]!=t or a[-1] is None or w!=F(float(a[-1].energy_kwh)) or w<0:raise ValueError('CURRENT_SECURITY_ENERGY_TRAVEL_DRIFT')
                cost=max(cost,w)
            else:raise ValueError('CURRENT_SECURITY_ENERGY_UNKNOWN_TERM')
        if len(charge)!=1 or len(discharge)!=1:raise ValueError('CURRENT_SECURITY_ENERGY_COEFFICIENT_DRIFT')
        c=charge.pop();p=discharge.pop()
        if not 0<c<=p:raise ValueError('CURRENT_SECURITY_ENERGY_COEFFICIENT_SIGN')
        if (u,t) in balances:raise ValueError('CURRENT_SECURITY_ENERGY_DUPLICATE')
        balances[u,t]=(c,p,cost)
    if not balances:return {}  # Small transport-only models need no SOC.
    envelopes={};limit=F(float(battery.p_limit))
    for u in sorted(initial):
        lo=[F(float(d['lower'][names[f'SOC[{u},{t}]']])) for t in range(H+1)]
        hi=[F(float(d['upper'][names[f'SOC[{u},{t}]']])) for t in range(H+1)]
        for t in (0,H):
            if (u,t) not in endpoints:raise ValueError('CURRENT_SECURITY_SOC_ENDPOINT_MISSING')
            lo[t]=hi[t]=endpoints[u,t]
        for t in range(H):
            c,p,cost=balances[u,t];lo[t+1]=max(lo[t+1],lo[t]-p*limit-cost);hi[t+1]=min(hi[t+1],hi[t]+c*limit)
        for t in reversed(range(H)):
            c,p,cost=balances[u,t];lo[t]=max(lo[t],lo[t+1]-c*limit);hi[t]=min(hi[t],hi[t+1]+p*limit+cost)
        if any(l>h for l,h in zip(lo,hi)):raise ValueError('CURRENT_SECURITY_SOC_ENVELOPE_EMPTY')
        envelopes[u]=(lo,hi)
    return envelopes

def _site_sources(A,d,sites,units):
    """PR160 affine_source: stored direct bindings on aggregate site P/Q.

    Return None for a genuinely different affine dependency graph; that graph
    uses the generic exact-rational path below instead. No approximate match
    or coefficient threshold selects this path.
    """
    N=len(sites);named=list(map(str,d['names']));lookup={n:j for j,n in enumerate(named)}
    vf=[family(n) for n in named];definitions=[]
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if not f.endswith('_binding'):continue
        a,b=A.indptr[i:i+2];matches=[int(j) for j in A.indices[a:b] if vf[j]==f[:-8]]
        if len(matches)!=1 or d['sense'][i]!='=':raise ValueError('CURRENT_SECURITY_DIRECT_BINDING_AXIS')
        j=matches[0]
        if float(A[i,j])!=1:raise ValueError('CURRENT_SECURITY_DIRECT_BINDING_PIVOT')
        definitions.append((i,j))
    T=np.zeros((A.shape[1],2*N));base=np.zeros((A.shape[1],1));times=np.full(A.shape[1],-1,int);coords={}
    for i,j in definitions:
        if not vf[j].startswith('injection_'):continue
        site,t=named[j].split('[',1)[1][:-1].split(',');t=int(t);q=vf[j]=='injection_Q'
        if vf[j] not in ('injection_P','injection_Q'):return None
        a,b=A.indptr[i:i+2];actual={named[k]:float(w) for k,w in zip(A.indices[a:b],A.data[a:b]) if k!=j and w}
        expected={}
        for u in units:
            for f,w in ([('Q',-1.)] if q else [('Pch',1.),('Pdis',-1.)]):
                n=f'{f}[{u},{site},{t}]'
                if n in lookup:expected[n]=w
        if actual!=expected or d['rhs'][i]!=0:raise ValueError('CURRENT_SECURITY_DIRECT_INJECTION_DRIFT')
        coord=sites.index(site)+N*q;coords[j]=coord;T[j,coord]=1.;times[j]=t
    for i,j in definitions:
        if vf[j].startswith('injection_'):continue
        a,b=A.indptr[i:i+2];used=set();tt=int(named[j].split('[',1)[1].split(',')[0])
        for k,w in zip(A.indices[a:b],A.data[a:b]):
            if k==j or not w:continue
            if int(k) not in coords:return None
            coord=coords[int(k)]
            if coord in used or times[k]!=tt:raise ValueError('CURRENT_SECURITY_DIRECT_RESPONSE_AXIS')
            used.add(coord);T[j,coord]=-float(w)
        base[j,0]=float(d['rhs'][i]);times[j]=tt
    return T,base,times

def _screen_site(A,d,graph,points,direct,progress):
    """Original PR160 sparse gamma enclosure, with explicit subnormal guard."""
    dom=domains(A,d,graph);T,base,times=direct;N=len(graph[0]);rho=next((j for j,n in enumerate(d['names']) if str(n)=='rho_max'),None)
    axis=[i for i,n in enumerate(d['row_names']) if family(n) in SECURITY_FAMILIES and d['sense'][i]!='='];certs=[];unknown=Counter();eligible=0
    def enclosure(C,X):
        value=C@X;mag=abs(C)@abs(X);k=2*np.diff(C.indptr)[:,None]+4;u=np.finfo(float).eps/2
        if np.any(k*u>1/8):raise ValueError('CURRENT_SECURITY_GAMMA_CONTRACT')
        error=np.nextafter(4*(k*u/(1-k*u))*mag+(k+4)*np.nextafter(0.,1.),np.inf)
        return np.nextafter(value-error,-np.inf),np.nextafter(value+error,np.inf)
    for start in range(0,len(axis),4096):
        chosen=[];ts=[];extra=[];rhs=[]
        for i in axis[start:start+4096]:
            a,b=A.indptr[i:i+2];tt={int(times[j]) for j in A.indices[a:b] if times[j]>=0};e=F(0);valid=len(tt)<=1;sg=-1 if d['sense'][i]=='>' else 1
            for j,w in zip(A.indices[a:b],A.data[a:b]):
                if times[j]>=0:continue
                if j!=rho:valid=False;break
                w=F(sg*float(w));endpoint=float(d['upper'][j] if w>0 else d['lower'][j])
                if not np.isfinite(endpoint):valid=False;break
                e+=w*F(endpoint)
            if not valid:unknown[family(d['row_names'][i])]+=1;continue
            chosen.append(i);ts.append(next(iter(tt)) if tt else 0);extra.append(up(e));rhs.append(F(sg*float(d['rhs'][i])))
        if chosen:
            C=(sparse.diags(np.where(d['sense'][chosen]=='>',-1.,1.))@A[chosen]).tocsr()
            lo,hi=enclosure(C,T);_,bh=enclosure(C,base);upper=bh[:,0];values=np.zeros((len(chosen),N))
            for p,q in points:
                pl,ph=down(p),up(p);ql,qh=down(q),up(q)
                pv=np.nextafter(np.maximum.reduce([lo[:,:N]*pl,lo[:,:N]*ph,hi[:,:N]*pl,hi[:,:N]*ph]),np.inf)
                qv=np.nextafter(np.maximum.reduce([lo[:,N:]*ql,lo[:,N:]*qh,hi[:,N:]*ql,hi[:,N:]*qh]),np.inf)
                values=np.maximum(values,np.nextafter(pv+qv,np.inf))
            for z in range(len(dom['units'])):upper=np.nextafter(upper+np.max(np.where(dom['reach'][z,np.asarray(ts),:],values,0),axis=1),np.inf)
            upper=np.nextafter(upper+np.asarray(extra),np.inf);eligible+=len(chosen)
            for i,value,r in zip(chosen,upper,rhs):
                if np.isfinite(value) and F(float(value))<=r:
                    certs.append(dict(row=i,kind='CURRENT_SECURITY_PCS_UNIT_FLOW_SUPPORT',family=family(d['row_names'][i]),
                        certified_upper_bound=float(value),rhs=str(r),slack=str(r-F(float(value))),arithmetic='PR160_CERTIFIED_SPARSE_SITE_PQ'))
        if progress:progress(dict(phase='M_CURRENT_SECURITY_SUPPORT',rows_scanned=min(start+4096,len(axis)),rows_total=len(axis),rows_proven=len(certs)))
    return certs,dict(security_rows_scanned=len(axis),security_rows_eligible=eligible,unsupported_families=dict(unknown),
        support_implementation='PR160_CERTIFIED_SPARSE_SITE_PQ',affine_support_evaluations=eligible)

def _finish(A,d,graph,points,certs,summary,start):
    env=_soc(A,d,graph);qlo=min(q for p,q in points);qhi=max(q for p,q in points)
    lower=d['lower'].copy();upper=d['upper'].copy();bounds=[]
    for j,n in enumerate(d['names']):
        f=family(n);lo=float(lower[j]);hi=float(upper[j]);method=None
        if f=='Q':lo=max(lo,down(qlo));hi=min(hi,up(qhi));method='CURRENT_EXACT_PCS_Q_ENVELOPE'
        elif f=='SOC':
            u,t=str(n)[4:-1].split(',');t=int(t)
            if u in env:lo=max(lo,down(env[u][0][t]));hi=min(hi,up(env[u][1][t]));method='CURRENT_EXACT_SOC_ENDPOINT_ENVELOPE'
        elif f=='node_activity':
            u,s,t=str(n)[14:-1].split(',')
            if int(t)==0:lo=hi=float(s==graph[1][u]);method='CURRENT_EXACT_SOURCE_FLOW_NODE'
        if lo>hi:raise ValueError('CURRENT_SECURITY_BOUND_CONTRADICTION')
        if lo!=lower[j] or hi!=upper[j]:
            bounds.append(dict(column=j,name=str(n),old_lower=float(lower[j]),old_upper=float(upper[j]),new_lower=lo,new_upper=hi,proof=method));lower[j]=lo;upper[j]=hi
    summary.update(removed_security_families=dict(Counter(c['family'] for c in certs)),pre_bound_families=dict(Counter(family(p['name']) for p in bounds)),
        original_PCS_exact_vertices=len(points),historical_row_indices_read=0,SOC_aggregate_bounds_used_for_site_union_deletions=False,
        Native_optimize_calls=0,wall_seconds=perf_counter()-start)
    return dict(certificates=certs,bounds=bounds,lower=lower,upper=upper,summary=summary)

def prepare_current_security(compact,graph,progress=None):
    start=perf_counter();A,d=compact.A,compact.d;points=_pcs(compact,graph)
    direct=_site_sources(A,d,list(graph[0]),sorted(graph[1]))
    if direct is not None:
        certs,summary=_screen_site(A,d,graph,points,direct,progress);del direct
        return _finish(A,d,graph,points,certs,summary,start)
    dom=domains(A,d,graph);src=exact_sources(A,d,dom);keys,vectors,constants,times,defs,_=src
    rho=next((j for j,n in enumerate(d['names']) if str(n)=='rho_max'),None)
    width=3*len(dom['units'])*len(dom['sites']);certs=[];eligible=0;unsupported=Counter()
    # Stored coefficients repeat over time. Cache exact affine enclosures by
    # their full rational expression, and support by the actual reach mask.
    # Bounded caches add at most ~40 MiB of dense data for the 4 x 24-site case;
    # they change neither a coefficient nor an implication decision.
    affine_cache=OrderedDict();support_cache=OrderedDict();evaluations=0
    axis=[i for i,n in enumerate(d['row_names']) if family(n) in SECURITY_FAMILIES and d['sense'][i]!='=']
    for startrow in range(0,len(axis),512):
        chunk=axis[startrow:startrow+512];mid=[];err=[];ts=[];targets=[];basevalues=[];rhsvalues=[];actual=[];unique={};batchpairs=[]
        for i in chunk:
            v,r=_row(A,d,i);base=F(0);signature=[];tt=set();valid=True
            for j,w in v.items():
                if j==rho:
                    endpoint=float(d['upper'][j] if w>0 else d['lower'][j])
                    if not np.isfinite(endpoint):valid=False;break
                    base+=w*F(endpoint)
                elif j in keys:
                    base+=w*constants[j];tt.add(times[j]);signature.append((keys[j],w))
                else:valid=False;break
            if not valid or len(tt)>1:
                unsupported[family(d['row_names'][i])]+=1;continue
            eligible+=1;t=next(iter(tt)) if tt else 0;signature=tuple(sorted(signature));pair=(signature,dom['reach'][:,t,:].tobytes())
            if pair not in support_cache and pair not in unique:
                if signature not in affine_cache:
                    aff=defaultdict(F)
                    for key,w in signature:
                        for q,x in vectors[key].items():aff[q]+=w*x
                    lo=np.zeros(width);hi=lo.copy()
                    for q,x in aff.items():lo[q]=down(x);hi[q]=up(x)
                    m=(lo+hi)/2;affine_cache[signature]=(m,np.maximum(m-lo,hi-m))
                    if len(affine_cache)>8192:affine_cache.popitem(last=False)
                m,error=affine_cache[signature];affine_cache.move_to_end(signature)
                unique[pair]=len(mid);mid.append(m);err.append(error);ts.append(t);batchpairs.append(pair)
            actual.append(i);targets.append(pair);basevalues.append(base);rhsvalues.append(r)
        if mid:
            upper=union_upper(np.asarray(mid),np.asarray(err),np.asarray(ts),dom,points)
            evaluations+=len(upper)
            for pair,value in zip(batchpairs,upper):support_cache[pair]=float(value)
        for i,pair,base,r in zip(actual,targets,basevalues,rhsvalues):
            bound=float(np.nextafter(up(base)+support_cache[pair],np.inf));support_cache.move_to_end(pair)
            if np.isfinite(bound) and F(bound)<=r:
                certs.append(dict(row=i,kind='CURRENT_SECURITY_PCS_UNIT_FLOW_SUPPORT',
                    family=family(d['row_names'][i]),certified_upper_bound=bound,rhs=str(r),
                    slack=str(r-F(bound)),arithmetic='OUTWARD_IEEE_INTERVAL_EXACT_BINARY_RATIONAL_AFFINE'))
        while len(support_cache)>65536:support_cache.popitem(last=False)
        if progress and startrow%25000<512:progress(dict(phase='M_CURRENT_SECURITY_SUPPORT',rows_scanned=startrow+len(chunk),rows_total=len(axis),rows_proven=len(certs)))
    # Release the large affine source graph before exact C2 and final C3A.
    del src,keys,vectors,constants,times,defs,_,dom,affine_cache,support_cache
    env=_soc(A,d,graph);qlo=min(q for p,q in points);qhi=max(q for p,q in points)
    lower=d['lower'].copy();upper=d['upper'].copy();bounds=[]
    for j,n in enumerate(d['names']):
        f=family(n);lo=float(lower[j]);hi=float(upper[j]);method=None
        if f=='Q':lo=max(lo,down(qlo));hi=min(hi,up(qhi));method='CURRENT_EXACT_PCS_Q_ENVELOPE'
        elif f=='SOC':
            u,t=str(n)[4:-1].split(',');t=int(t)
            if u in env:lo=max(lo,down(env[u][0][t]));hi=min(hi,up(env[u][1][t]));method='CURRENT_EXACT_SOC_ENDPOINT_ENVELOPE'
        elif f=='node_activity':
            u,s,t=str(n)[14:-1].split(',')
            if int(t)==0:lo=hi=float(s==graph[1][u]);method='CURRENT_EXACT_SOURCE_FLOW_NODE'
        if lo>hi:raise ValueError('CURRENT_SECURITY_BOUND_CONTRADICTION')
        if lo!=lower[j] or hi!=upper[j]:
            bounds.append(dict(column=j,name=str(n),old_lower=float(lower[j]),old_upper=float(upper[j]),new_lower=lo,new_upper=hi,proof=method))
            lower[j]=lo;upper[j]=hi
    return dict(certificates=certs,bounds=bounds,lower=lower,upper=upper,
        summary=dict(security_rows_scanned=len(axis),security_rows_eligible=eligible,
            unsupported_families=dict(unsupported),removed_security_families=dict(Counter(c['family'] for c in certs)),
            pre_bound_families=dict(Counter(family(p['name']) for p in bounds)),
            original_PCS_exact_vertices=len(points),affine_support_evaluations=evaluations,historical_row_indices_read=0,
            SOC_aggregate_bounds_used_for_site_union_deletions=False,Native_optimize_calls=0,wall_seconds=perf_counter()-start))
