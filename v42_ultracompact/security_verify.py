"""Independent replay of fresh pre-C2 security and endpoint certificates.

This module never imports the security producer or its deletion functions.
The caller first checks the actual original flow equations and Compact links.
"""
from collections import Counter, defaultdict, OrderedDict
from fractions import Fraction as Q
from itertools import combinations
import numpy as np
from .current_verify import affine, physical_pcs_authority, vec, family

def _enclose(x):
    y=float(x)
    return (y if Q(y)<=x else np.nextafter(y,-np.inf),y if Q(y)>=x else np.nextafter(y,np.inf))

def _native_affine(A,d,sites,units):
    """Independent raw binding reconstruction, no sparse gamma producer."""
    N=len(sites);names=list(map(str,d['names']));index={n:j for j,n in enumerate(names)};families=[family(n) for n in names]
    bindings={}
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if not f.endswith('_binding'):continue
        a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b];pivots=[int(j) for j in js if families[j]==f[:-8]]
        if len(pivots)!=1 or d['sense'][i]!='=':raise ValueError('CURRENT_SECURITY_REPLAY_NATIVE_BINDING_AXIS')
        j=pivots[0]
        if j in bindings or float(ws[list(js).index(j)])!=1:raise ValueError('CURRENT_SECURITY_REPLAY_NATIVE_PIVOT')
        bindings[j]=i
    raw=np.zeros((A.shape[1],2*N));directions={};constants={};times={};coord={}
    for j,i in bindings.items():
        if families[j] not in ('injection_P','injection_Q'):continue
        site,t=names[j].split('[',1)[1][:-1].split(',');t=int(t);q=families[j]=='injection_Q';v,r=vec(A,d,i)
        expected={j:Q(1)}
        for u in units:
            for f,w in ([('Q',-1)] if q else [('Pch',1),('Pdis',-1)]):
                n=f'{f}[{u},{site},{t}]'
                if n in index:expected[index[n]]=Q(w)
        if v!=expected or r:raise ValueError('CURRENT_SECURITY_REPLAY_NATIVE_INJECTION')
        k=sites.index(site)+N*q;coord[j]=k;raw[j,k]=1;directions[j]=raw[j];constants[j]=Q(0);times[j]=t
    for j,i in bindings.items():
        if j in directions:continue
        a,b=A.indptr[i:i+2];tt=int(names[j].split('[',1)[1].split(',')[0]);used=set()
        for k,w in zip(A.indices[a:b],A.data[a:b]):
            if k==j or not w:continue
            if int(k) not in coord or times[int(k)]!=tt or coord[int(k)] in used:raise ValueError('CURRENT_SECURITY_REPLAY_NATIVE_RESPONSE')
            kk=coord[int(k)];used.add(kk);raw[j,kk]=-float(w)
        directions[j]=raw[j];constants[j]=Q(float(d['rhs'][i]));times[j]=tt
    return directions,constants,times,bindings

def verify_current_security(compact,presolve):
    pre=getattr(presolve,'current_security',None)
    if pre is None:return dict(PASS=True,removed_rows=0,bounds_tightened=0),compact.d
    C,c=compact.A,compact.d;sites=list(dict.fromkeys(a[0] for a in compact.arcs if a[-1] is None))
    units=sorted(compact.initial);N=len(sites);H=compact.H
    graph=(sites,compact.initial,compact.arcs,pre['battery'],{})
    planes=physical_pcs_authority(compact.original,compact.original_data,graph)
    limit=Q(float(pre['battery'].p_limit));planes=planes+[(Q(1),Q(0),limit),(Q(-1),Q(0),limit)]
    points=set()
    for (a,b,r),(p,q,s) in combinations(planes,2):
        den=a*q-b*p
        if den:
            x=(r*q-b*s)/den;y=(a*s-r*p)/den
            if all(u*x+v*y<=w for u,v,w in planes):points.add((x,y))
    if not points:raise ValueError('CURRENT_SECURITY_REPLAY_EMPTY_PCS')
    # Every original connected physical block is checked above. Its existence
    # is sufficient for this conservative reach mask; no reachable state is
    # excluded, and the independently checked unit DAG has stay mass <=1.
    reach=np.zeros((len(units),H,N),bool)
    for n in c['names']:
        if str(n).startswith('Pch['):
            u,s,t=str(n)[4:-1].split(',');reach[units.index(u),int(t),sites.index(s)]=True
    native=pre['summary'].get('support_implementation')=='PR160_CERTIFIED_SPARSE_SITE_PQ'
    directions,constants,times,bindings=(_native_affine(C,c,sites,units) if native else affine(C,c,sites,units))
    rho=next((j for j,n in enumerate(c['names']) if str(n)=='rho_max'),None)
    certificates=pre['certificates'];ids=[int(p['row']) for p in certificates]
    if len(ids)!=len(set(ids)):raise ValueError('CURRENT_SECURITY_REPLAY_DUPLICATE_ROW')
    actual={int(p['row']):p for p in presolve.rows if p['kind']=='CURRENT_SECURITY_PCS_UNIT_FLOW_SUPPORT'}
    if set(actual)!=set(ids) or any(actual[i]!=p for i,p in zip(ids,certificates)):raise ValueError('CURRENT_SECURITY_REPLAY_CERTIFICATE_COVER')
    supported={'voltage_upper','voltage_lower','line_thermal_face','transformer_kVA','NormalAmps'}
    def interval(vs,ts):
        if native:
            lo=np.asarray([v[0] for v in vs]);hi=np.asarray([v[1] for v in vs]);values=np.zeros((len(vs),N))
            for x,y in points:
                xl,xh=_enclose(x);yl,yh=_enclose(y)
                pp=np.nextafter(np.maximum.reduce([lo[:,:N]*xl,lo[:,:N]*xh,hi[:,:N]*xl,hi[:,:N]*xh]),np.inf)
                qq=np.nextafter(np.maximum.reduce([lo[:,N:]*yl,lo[:,N:]*yh,hi[:,N:]*yl,hi[:,N:]*yh]),np.inf)
                values=np.maximum(values,np.nextafter(pp+qq,np.inf))
            result=np.zeros(len(vs))
            for u in range(len(units)):result=np.nextafter(result+np.max(np.where(reach[u,np.asarray(ts)],values,0),axis=1),np.inf)
            return result
        K=len(vs);pl=np.zeros((K,len(units),N));ph=pl.copy();ql=pl.copy();qh=pl.copy();extra=pl.copy()
        for k,v in enumerate(vs):
            for u in range(len(units)):
                for site in range(N):
                    pd=v.get((3*u+1)*N+site,Q(0));qq=v.get((3*u+2)*N+site,Q(0));ch=v.get(3*u*N+site,Q(0))
                    pl[k,u,site],ph[k,u,site]=_enclose(pd);ql[k,u,site],qh[k,u,site]=_enclose(qq)
                    extra[k,u,site]=_enclose(max(Q(0),ch+pd)*limit)[1]
        values=np.zeros_like(pl)
        for x,y in points:
            xl,xh=_enclose(x);yl,yh=_enclose(y)
            pp=np.nextafter(np.maximum.reduce([pl*xl,pl*xh,ph*xl,ph*xh]),np.inf)
            qq=np.nextafter(np.maximum.reduce([ql*yl,ql*yh,qh*yl,qh*yh]),np.inf)
            values=np.maximum(values,np.nextafter(pp+qq,np.inf))
        values=np.nextafter(values+extra,np.inf);result=np.zeros(K)
        for u in range(len(units)):
            result=np.nextafter(result+np.max(np.where(reach[u,np.asarray(ts)],values[:,u,:],0),axis=1),np.inf)
        return result
    exact_fallbacks=0;expression_cache=OrderedDict();support_cache=OrderedDict();evaluations=0
    for start in range(0,len(certificates),256):
        chunk=certificates[start:start+256];vectors=[];basevalues=[];ts=[];right=[];pairs=[]
        batchvectors=[];batchts=[];batchpairs=[];batchlookup={}
        for p in chunk:
            i=int(p['row']);v,r=vec(C,c,i);base=Q(0);tt=set();signature=[]
            if c['sense'][i]=='=' or family(c['row_names'][i]) not in supported or p['family']!=family(c['row_names'][i]):raise ValueError('CURRENT_SECURITY_REPLAY_ROW_FAMILY')
            for j,w in v.items():
                if j==rho:
                    endpoint=float(c['upper'][j] if w>0 else c['lower'][j])
                    if not np.isfinite(endpoint):raise ValueError('CURRENT_SECURITY_REPLAY_RHO_BOUND')
                    base+=w*Q(endpoint)
                else:
                    if j not in directions:raise ValueError('CURRENT_SECURITY_REPLAY_UNKNOWN_DEPENDENCY')
                    base+=w*constants[j];tt.add(times[j])
                    # Locally reconstructed immutable direction dictionaries
                    # share identity only when affine() derived the same exact
                    # vector. Constants are handled afresh for each row.
                    signature.append((id(directions[j]),w,j))
            if len(tt)>1:raise ValueError('CURRENT_SECURITY_REPLAY_TIME_COUPLING')
            key=tuple(sorted((identity,w) for identity,w,j in signature));t=next(iter(tt)) if tt else 0
            if key not in expression_cache:
                if native:
                    lo=np.zeros(2*N);hi=lo.copy()
                    for identity,w,j in signature:
                        product=float(w)*directions[j]
                        lo=np.nextafter(lo+np.nextafter(product,-np.inf),-np.inf)
                        hi=np.nextafter(hi+np.nextafter(product,np.inf),np.inf)
                    expression_cache[key]=(lo,hi)
                else:
                    aff=defaultdict(Q)
                    for identity,w,j in signature:
                        for k,z in directions[j].items():aff[k]+=w*z
                    expression_cache[key]={k:w for k,w in aff.items() if w}
                if len(expression_cache)>2048:expression_cache.popitem(last=False)
            vector=expression_cache[key];expression_cache.move_to_end(key);pair=(key,reach[:,t,:].tobytes())
            if pair not in support_cache and pair not in batchlookup:
                batchlookup[pair]=len(batchvectors);batchvectors.append(vector);batchts.append(t);batchpairs.append(pair)
            vectors.append(vector);basevalues.append(base);ts.append(t);right.append(r);pairs.append(pair)
        if batchvectors:
            ups=interval(batchvectors,batchts);evaluations+=len(ups)
            for pair,value in zip(batchpairs,ups):support_cache[pair]=float(value)
        for p,v,base,t,r,pair in zip(chunk,vectors,basevalues,ts,right,pairs):
            u=support_cache[pair];support_cache.move_to_end(pair)
            claimed=Q(float(p['certified_upper_bound']));independent=base+Q(float(u))
            if independent>claimed:
                # Exact fallback only when the two outward interval programs
                # differ at a rounding boundary. No epsilon permits deletion.
                if native:
                    row,rhs=vec(C,c,int(p['row']));aggregate=defaultdict(Q)
                    for j,w in row.items():
                        if j==rho:continue
                        for site,z in enumerate(directions[j]):
                            if z:aggregate[site]+=w*Q(float(z))
                    v={}
                    for z in range(len(units)):
                        for site in range(N):
                            pp=aggregate[site];qq=aggregate[N+site]
                            v[3*z*N+site]=-pp;v[(3*z+1)*N+site]=pp;v[(3*z+2)*N+site]=qq
                total=base
                for z in range(len(units)):
                    best=Q(0)
                    for site in np.flatnonzero(reach[z,t]):
                        ch=v.get(3*z*N+site,Q(0));pd=v.get((3*z+1)*N+site,Q(0));qq=v.get((3*z+2)*N+site,Q(0))
                        best=max(best,max([Q(0)]+[pd*x+qq*y for x,y in points])+max(Q(0),ch+pd)*limit)
                    total+=best
                independent=total;exact_fallbacks+=1
            if independent>claimed or claimed>r or p['rhs']!=str(r) or Q(p['slack'])!=r-claimed:raise ValueError('CURRENT_SECURITY_REPLAY_SUPPORT_NOT_IMPLIED')
        while len(support_cache)>65536:support_cache.popitem(last=False)
    del directions,constants,times,bindings,expression_cache,support_cache
    # Independently derive endpoint envelopes as interval consequences of the
    # actual retained original energy equations, without reading an envelope
    # or recomputing efficiencies from nominal battery parameters.
    named={str(n):j for j,n in enumerate(c['names'])};steps={};endpoints={}
    for i,n in enumerate(c['row_names']):
        f=family(n)
        if f not in ('energy_balance','initial_SOC','terminal_SOC'):continue
        v,r=vec(C,c,i)
        if c['sense'][i]!='=':raise ValueError('CURRENT_SECURITY_REPLAY_SOC_SENSE')
        ss=[j for j in v if family(c['names'][j])=='SOC']
        if f!='energy_balance':
            if len(v)!=1 or len(ss)!=1 or v[ss[0]]!=1:raise ValueError('CURRENT_SECURITY_REPLAY_ENDPOINT_ROW')
            u,t=str(c['names'][ss[0]])[4:-1].split(',');endpoints[u,int(t)]=r;continue
        ss.sort(key=lambda j:int(str(c['names'][j])[4:-1].split(',')[1]))
        if len(ss)!=2 or r:raise ValueError('CURRENT_SECURITY_REPLAY_ENERGY_ROW')
        u,t=str(c['names'][ss[0]])[4:-1].split(',');t=int(t)
        if str(c['names'][ss[1]])!=f'SOC[{u},{t+1}]' or v[ss[0]]!=-1 or v[ss[1]]!=1:raise ValueError('CURRENT_SECURITY_REPLAY_ENERGY_AXIS')
        cs=[];ds=[];travel=Q(0)
        for j,w in v.items():
            f=family(c['names'][j])
            if f=='SOC':continue
            if f in ('Pch','Pdis'):
                uu,s,tt=str(c['names'][j]).split('[',1)[1][:-1].split(',')
                if uu!=u or int(tt)!=t or c['lower'][j]!=0:raise ValueError('CURRENT_SECURITY_REPLAY_POWER_AXIS')
                (cs if f=='Pch' else ds).append(-w if f=='Pch' else w)
            elif f=='route_flow':
                uu,k=str(c['names'][j])[11:-1].split(',');a=compact.arcs[int(k)]
                if uu!=u or a[1]!=t or a[-1] is None or w!=Q(float(a[-1].energy_kwh)) or w<0:raise ValueError('CURRENT_SECURITY_REPLAY_TRAVEL_AXIS')
                travel=max(travel,w)
            else:raise ValueError('CURRENT_SECURITY_REPLAY_ENERGY_UNKNOWN')
        if not cs or not ds or len(set(cs))!=1 or len(set(ds))!=1 or not 0<cs[0]<=ds[0]:raise ValueError('CURRENT_SECURITY_REPLAY_POWER_COEFFICIENT')
        if (u,t) in steps:raise ValueError('CURRENT_SECURITY_REPLAY_ENERGY_DUPLICATE')
        steps[u,t]=(-ds[0]*limit-travel,cs[0]*limit)
    implied={}
    if steps:
        for u in units:
            lo=[Q(float(c['lower'][named[f'SOC[{u},{t}]']])) for t in range(H+1)]
            hi=[Q(float(c['upper'][named[f'SOC[{u},{t}]']])) for t in range(H+1)]
            for t in (0,H):lo[t]=hi[t]=endpoints[u,t]
            for t in range(H):
                a,b=steps[u,t];lo[t+1]=max(lo[t+1],lo[t]+a);hi[t+1]=min(hi[t+1],hi[t]+b)
            for t in range(H-1,-1,-1):
                a,b=steps[u,t];lo[t]=max(lo[t],lo[t+1]-b);hi[t]=min(hi[t],hi[t+1]-a)
            for t in range(H+1):implied[named[f'SOC[{u},{t}]']]=(lo[t],hi[t],'CURRENT_EXACT_SOC_ENDPOINT_ENVELOPE')
    for j,n in enumerate(c['names']):
        f=family(n)
        if f=='Q':implied[j]=(min(y for x,y in points),max(y for x,y in points),'CURRENT_EXACT_PCS_Q_ENVELOPE')
        elif f=='node_activity':
            u,s,t=str(n)[14:-1].split(',')
            if int(t)==0:
                q=Q(int(s==compact.initial[u]));implied[j]=(q,q,'CURRENT_EXACT_SOURCE_FLOW_NODE')
    lower=c['lower'].copy();upper=c['upper'].copy();seen=set()
    for p in pre['bounds']:
        j=int(p['column'])
        if j in seen or j not in implied:raise ValueError('CURRENT_SECURITY_REPLAY_BOUND_AXIS')
        seen.add(j);lo,hi,kind=implied[j]
        lo=max(Q(float(c['lower'][j])),lo);hi=min(Q(float(c['upper'][j])),hi)
        if (p['name']!=str(c['names'][j]) or p['proof']!=kind or p['old_lower']!=c['lower'][j] or p['old_upper']!=c['upper'][j]
            or Q(float(p['new_lower']))>lo or Q(float(p['new_upper']))<hi
            or p['new_lower']<c['lower'][j] or p['new_upper']>c['upper'][j]):raise ValueError('CURRENT_SECURITY_REPLAY_BOUND_NOT_IMPLIED')
        lower[j]=p['new_lower'];upper[j]=p['new_upper']
    if not np.array_equal(pre['lower'],lower) or not np.array_equal(pre['upper'],upper):raise ValueError('CURRENT_SECURITY_REPLAY_BOUND_CERTIFICATE_COVER')
    effective=dict(c,lower=lower,upper=upper)
    for k in c:
        if not np.array_equal(presolve.initial_d[k],effective[k]):raise ValueError('CURRENT_SECURITY_REPLAY_INITIAL_DOMAIN_DRIFT')
    return dict(PASS=True,removed_rows=len(ids),removed_families=dict(Counter(p['family'] for p in certificates)),
        bounds_tightened=len(seen),independent_exact_support_fallbacks=exact_fallbacks,independent_support_evaluations=evaluations,
        original_integer_and_full_LP_domain_preserved=True,Native_optimize_calls=0),effective
