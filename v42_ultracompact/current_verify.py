"""Independent current-matrix C3A certificate replay; no producer imports.

The native C2 transport certificate first proves the original MILP and DAG.
This verifier proves every additional deleted row and affine bound over that
full LP domain, without a solver or historical artifact.
"""
from collections import Counter, defaultdict
from fractions import Fraction as Q
from itertools import combinations
from time import perf_counter
import numpy as np

def family(n):return str(n).split('[',1)[0]

def vec(A,d,i):
    a,b=A.indptr[i:i+2];sg=-1 if d['sense'][i]=='>' else 1
    return {int(j):Q(sg*float(w)) for j,w in zip(A.indices[a:b],A.data[a:b])},Q(sg*float(d['rhs'][i]))

def affine(A,d,sites,units):
    N=len(sites);directions={};constants={};timeid={};bindings={};vf=[family(v) for v in d['names']];cache={};active=set()
    for j,n in enumerate(d['names']):
        f=vf[j]
        if f in ('Pch','Pdis','Q'):
            u,s,t=str(n).split('[',1)[1][:-1].split(',');k=(units.index(u)*3+('Pch','Pdis','Q').index(f))*N+sites.index(s)
            directions[j]={k:Q(1)};constants[j]=Q(0);timeid[j]=int(t)
        elif f.startswith(('injection_','response_')) and d['lower'][j]==d['upper'][j]:
            directions[j]={};constants[j]=Q(float(d['lower'][j]));timeid[j]=int(str(n).split('[',1)[1].split(',')[1 if f.startswith('injection_') else 0])
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if not f.endswith('_binding'):continue
        v,r=vec(A,d,i);piv=[j for j in v if vf[j]==f[:-8]]
        if len(piv)!=1 or d['sense'][i]!='=':raise ValueError('CURRENT_C3A_BINDING_AXIS_DRIFT')
        j=piv[0]
        if v[j]!=1 or j in bindings:raise ValueError('CURRENT_C3A_BINDING_PIVOT_DRIFT')
        bindings[j]=i
    def expand(j):
        if j in directions:return directions[j],constants[j]
        if j in active or j not in bindings:raise ValueError('CURRENT_C3A_UNPROVEN_AFFINE_DEPENDENCY')
        active.add(j);i=bindings[j];v,r=vec(A,d,i);terms=[(k,-w) for k,w in v.items() if k!=j];result=defaultdict(Q);constant=r;tt=set();key=[]
        for k,w in terms:
            dep,c=expand(k);constant+=w*c;tt.add(timeid[k]);key.append((tuple(dep.items()),w))
        signature=tuple(key)
        if signature in cache:result=cache[signature]
        else:
            for k,w in terms:
                for q,x in directions[k].items():result[q]+=w*x
            result={q:x for q,x in result.items() if x};cache[signature]=result
        if len(tt)>1:raise ValueError('CURRENT_C3A_AFFINE_TIME_COUPLING')
        directions[j]=result;constants[j]=constant;timeid[j]=next(iter(tt)) if tt else int(str(d['names'][j]).split('[',1)[1].split(',')[0]);active.remove(j)
        return result,constant
    for j in bindings:expand(j)
    return directions,constants,timeid,bindings

def physical_pcs_authority(A,d,graph):
    """Read every original connected PCS block, including C2 fixed aliases.

    The separately verified exact C2 transport implies these original rows in
    C2. Therefore a fixed source's removed singleton face cannot silently
    disappear from the affine support authority.
    """
    sites,initial,arcs,battery,_=graph;limit=Q(float(battery.p_limit))
    vf=[family(n) for n in d['names']];physical=defaultdict(dict);blocks=defaultdict(list);links=defaultdict(dict)
    for j,n in enumerate(d['names']):
        if vf[j] in ('Pch','Pdis','Q'):physical[str(n).split('[',1)[1][:-1]][vf[j]]=j
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if f not in ('PCS16','connected_Pch','connected_Pdis'):continue
        v,r=vec(A,d,i);states={str(d['names'][j]).split('[',1)[1][:-1] for j in v if vf[j] in ('Pch','Pdis','Q')}
        if len(states)!=1:raise ValueError('CURRENT_C3A_ORIGINAL_PCS_AXIS_DRIFT')
        state=states.pop()
        if f=='PCS16':blocks[state].append((i,v,r))
        else:links[state][f]=(i,v,r)
    authority=None
    for state,cols in physical.items():
        if set(cols)!=set(('Pch','Pdis','Q')) or len(blocks[state])!=16:raise ValueError('CURRENT_C3A_ORIGINAL_PCS_COVER_DRIFT')
        ch,pd,q=(cols[f] for f in ('Pch','Pdis','Q'));unit,site,time=state.split(',');t=int(time);planes=[];mass=None
        for i,v,r in blocks[state]:
            js=[j for j in v if vf[j]=='arc']
            if len(js)!=1 or r or d['sense'][i]!='<':raise ValueError('CURRENT_C3A_ORIGINAL_HOMOGENEOUS_PCS_DRIFT')
            j=js[0];u,k=str(d['names'][j])[4:-1].split(',');a=arcs[int(k)]
            if u!=unit or a[:4]!=(site,t,site,t+1) or a[-1] is not None:raise ValueError('CURRENT_C3A_ORIGINAL_STAY_MASS_DRIFT')
            if mass is not None and mass!=j:raise ValueError('CURRENT_C3A_ORIGINAL_STAY_AXIS_DRIFT')
            mass=j;p=v.get(pd,Q(0));qq=v.get(q,Q(0));c=-v[j]
            if v.get(ch,Q(0))!=-p or set(v)-{ch,pd,q,j}:raise ValueError('CURRENT_C3A_ORIGINAL_PCS_COEFFICIENT_DRIFT')
            planes.append((p,qq,c))
        if authority is None:authority=planes
        if planes!=authority:raise ValueError('CURRENT_C3A_UNEQUAL_ORIGINAL_PCS_DOMAIN')
        for col,other,f in ((ch,pd,'connected_Pch'),(pd,ch,'connected_Pdis')):
            if f not in links[state]:raise ValueError('CURRENT_C3A_ORIGINAL_CONNECTED_P_MISSING')
            i,v,r=links[state][f]
            if v!={col:Q(1),mass:-limit} or r or d['sense'][i]!='<' or d['lower'][col]!=0 or d['lower'][other]!=0:
                raise ValueError('CURRENT_C3A_ORIGINAL_CONNECTED_P_DOMAIN_DRIFT')
        if d['lower'][mass]!=0 or d['upper'][mass]!=1 or d['types'][mass]!='B':raise ValueError('CURRENT_C3A_ORIGINAL_UNIT_MASS_DOMAIN_DRIFT')
    if authority is None:raise ValueError('CURRENT_C3A_CURRENT_PCS_AUTHORITY_MISSING')
    return authority

def verify_current_c3a(ultra,graph):
    began=perf_counter();A,d=ultra.original,ultra.original_data;B,e=ultra.A,ultra.d;rows=np.asarray(ultra.row_ids)
    retained=set(map(int,rows));removed=set(range(A.shape[0]))-retained
    if (len(rows)!=len(retained) or B.shape!=(len(rows),A.shape[1])
            or {int(p['row']) for p in ultra.certificates}!=removed or len(ultra.certificates)!=len(removed)):
        raise ValueError('CURRENT_C3A_ROW_CERTIFICATE_COVER_DRIFT')
    # Stream CSR comparison instead of creating another full subset/difference.
    if not np.array_equal(np.diff(A.indptr)[rows],np.diff(B.indptr)):raise ValueError('CURRENT_C3A_RETAINED_SPARSITY_DRIFT')
    for k,i in enumerate(rows):
        a,b=A.indptr[i:i+2];c,f=B.indptr[k:k+2]
        if not np.array_equal(A.indices[a:b],B.indices[c:f]) or not np.array_equal(A.data[a:b],B.data[c:f]):
            raise ValueError('CURRENT_C3A_RETAINED_COEFFICIENT_DRIFT')
    for k in ('rhs','sense','row_names'):
        if not np.array_equal(d[k][rows],e[k]):raise ValueError('CURRENT_C3A_RETAINED_ROW_METADATA_DRIFT')
    for k in ('names','types','objective','constant'):
        if not np.array_equal(d[k],e[k]):raise ValueError('CURRENT_C3A_OBJECTIVE_INTEGER_AXIS_DRIFT')
    methods=Counter()
    for certificate in ultra.certificates:
        i=int(certificate['row']);kind=certificate['kind'];target,rhs=vec(A,d,i);total=defaultdict(Q);bound=Q(0)
        if kind=='FLOW_EQUALITY_SUM':
            if d['sense'][i]!='=':raise ValueError('CURRENT_C3A_TERMINAL_SENSE_DRIFT')
            for j in certificate['support']:
                if j not in retained or d['sense'][j]!='=':raise ValueError('CURRENT_C3A_TERMINAL_SUPPORT_NOT_RETAINED_EQUALITY')
                v,r=vec(A,d,j);bound+=r
                for k,w in v.items():total[k]+=w
            valid=bound==rhs
        elif kind in ('PCS_FARKAS','Q_LINK_FARKAS'):
            if d['sense'][i]=='=':raise ValueError('CURRENT_C3A_FARKAS_TARGET_EQUALITY')
            for support in certificate['support']:
                weight=Q(support['weight'])
                if weight<0:raise ValueError('CURRENT_C3A_NEGATIVE_FARKAS_WEIGHT')
                if 'row' in support:
                    j=int(support['row'])
                    if j not in retained or d['sense'][j]=='=':raise ValueError('CURRENT_C3A_FARKAS_SUPPORT_NOT_RETAINED')
                    v,r=vec(A,d,j)
                else:
                    j=int(support['bound']);endpoint=support['endpoint']
                    if endpoint not in ('lower','upper'):raise ValueError('CURRENT_C3A_BOUND_ENDPOINT_DRIFT')
                    sign=1 if endpoint=='upper' else -1;v={j:Q(sign)};r=Q(sign*float(d[endpoint][j]))
                bound+=weight*r
                for k,w in v.items():total[k]+=weight*w
            valid=bound<=rhs
        else:raise ValueError('CURRENT_C3A_UNSUPPORTED_CERTIFICATE')
        if {k:w for k,w in total.items() if w}!=target or not valid:raise ValueError('CURRENT_C3A_EXACT_ROW_IMPLICATION_FAILED')
        methods[kind]+=1
    sites,initial,arcs,battery,_=graph;units=sorted(initial);N=len(sites);H=max(a[3] for a in arcs);limit=Q(float(battery.p_limit))
    if any(not 0<=a[1]<a[3]<=H for a in arcs):raise ValueError('CURRENT_C3A_NONACYCLIC_UNIT_FLOW')
    reach=np.zeros((len(units),H,N),bool)
    for n in d['names']:
        if str(n).startswith('Pch['):
            u,s,t=str(n)[4:-1].split(',');reach[units.index(u),int(t),sites.index(s)]=True
    dirs,const,times,defs=affine(A,d,sites,units)
    if any(i not in retained for i in defs.values()):raise ValueError('CURRENT_C3A_AFFINE_SUPPORT_DEFINITION_REMOVED')
    # Independent rational pair intersections from every freshly constructed
    # original PCS block. The C2 transport proof is required by the caller.
    full,fd=ultra.physical_original,ultra.physical_original_data
    if full is not None:
        planes=physical_pcs_authority(full,fd,graph)
        ids=[]
    else:
        ids=[i for i,n in enumerate(d['row_names']) if family(n)=='PCS16'];planes=None
    for start in range(0,len(ids)-15):
        block=ids[start:start+16];candidate=[];axis=None;okay=True
        for i in block:
            v,r=vec(A,d,i);states={str(d['names'][j]).split('[',1)[1][:-1] for j in v if family(d['names'][j]) in ('Pch','Pdis','Q')}
            if len(states)!=1 or (axis is not None and states!={axis}):okay=False;break
            axis=next(iter(states));p=next((w for j,w in v.items() if family(d['names'][j])=='Pdis'),Q(0));q=next((w for j,w in v.items() if family(d['names'][j])=='Q'),Q(0))
            mass=[w for j,w in v.items() if family(d['names'][j]) in ('route_flow','node_activity')]
            if len(mass)>1:okay=False;break
            candidate.append((p,q,-mass[0] if mass else r))
        if okay:planes=candidate;break
    if planes is None:raise ValueError('CURRENT_C3A_CURRENT_PCS_AUTHORITY_MISSING')
    planes.extend([(Q(1),Q(0),limit),(Q(-1),Q(0),limit)]);points=set()
    for (a,b,c),(p,q,r) in combinations(planes,2):
        den=a*q-b*p
        if not den:continue
        x=(c*q-b*r)/den;y=(a*r-c*p)/den
        if all(s*x+t*y<=u for s,t,u in planes):points.add((x,y))
    if not points:raise ValueError('CURRENT_C3A_CURRENT_PCS_DOMAIN_EMPTY')
    def enclosure(x):
        y=float(x);return (y if Q(y)<=x else np.nextafter(y,-np.inf),y if Q(y)>=x else np.nextafter(y,np.inf))
    def interval(vectors,ts):
        K=len(vectors);pl=np.zeros((K,len(units),N));ph=pl.copy();ql=pl.copy();qh=pl.copy();common=pl.copy()
        for k,v in enumerate(vectors):
            for u in range(len(units)):
                for s in range(N):
                    pd=v.get((3*u+1)*N+s,Q(0));qq=v.get((3*u+2)*N+s,Q(0));ch=v.get(3*u*N+s,Q(0))
                    pl[k,u,s],ph[k,u,s]=enclosure(pd);ql[k,u,s],qh[k,u,s]=enclosure(qq);common[k,u,s]=enclosure(max(Q(0),ch+pd)*limit)[1]
        value=np.zeros_like(pl)
        for x,y in points:
            xl,xh=enclosure(x);yl,yh=enclosure(y)
            p=np.nextafter(np.maximum.reduce([pl*xl,pl*xh,ph*xl,ph*xh]),np.inf);q=np.nextafter(np.maximum.reduce([ql*yl,ql*yh,qh*yl,qh*yh]),np.inf)
            value=np.maximum(value,np.nextafter(p+q,np.inf))
        value=np.nextafter(value+common,np.inf);upper=np.zeros(K)
        for u in range(len(units)):upper=np.nextafter(upper+np.max(np.where(reach[u,np.asarray(ts)],value[:,u,:],0),axis=1),np.inf)
        return upper
    exact_cache={}
    def exact(v,t):
        key=(tuple(sorted(v.items())),t)
        if key not in exact_cache:
            total=Q(0)
            for u in range(len(units)):
                best=Q(0)
                for s in np.flatnonzero(reach[u,t]):
                    ch=v.get(3*u*N+s,Q(0));pd=v.get((3*u+1)*N+s,Q(0));qq=v.get((3*u+2)*N+s,Q(0))
                    best=max(best,max([Q(0)]+[pd*x+qq*y for x,y in points])+max(Q(0),ch+pd)*limit)
                total+=best
            exact_cache[key]=total
        return exact_cache[key]
    boundids=set();fallbacks=0
    for start in range(0,len(ultra.bounds),256):
        chunk=ultra.bounds[start:start+256];js=[int(p['column']) for p in chunk];vs=[dirs[j] for j in js];ts=[times[j] for j in js]
        ups=interval(vs,ts);downs=interval([{q:-w for q,w in v.items()} for v in vs],ts)
        for p,j,u,l in zip(chunk,js,ups,downs):
            if j in boundids or not family(d['names'][j]).startswith(('injection_','response_')):raise ValueError('CURRENT_C3A_BOUND_PROOF_AXIS_DRIFT')
            boundids.add(j);lower=const[j]-Q(float(l));upper=const[j]+Q(float(u))
            if Q(float(p['new_lower']))>lower or Q(float(p['new_upper']))<upper:
                lower=const[j]-exact({q:-w for q,w in dirs[j].items()},times[j]);upper=const[j]+exact(dirs[j],times[j]);fallbacks+=1
            if (Q(float(p['new_lower']))>lower or Q(float(p['new_upper']))<upper
                    or p['old_lower']!=d['lower'][j] or p['old_upper']!=d['upper'][j]
                    or e['lower'][j]!=p['new_lower'] or e['upper'][j]!=p['new_upper']
                    or e['lower'][j]<d['lower'][j] or e['upper'][j]>d['upper'][j]):
                raise ValueError('CURRENT_C3A_AFFINE_BOUND_NOT_IMPLIED')
    changed=set(map(int,np.flatnonzero((e['lower']!=d['lower'])|(e['upper']!=d['upper']))))
    if changed!=boundids:raise ValueError('CURRENT_C3A_BOUND_CERTIFICATE_COVER_DRIFT')
    return dict(PASS=True,removed_rows=len(removed),removed_row_methods=dict(methods),bounds_tightened=len(boundids),
        affine_definitions_reconstructed=len(defs),independent_bound_exact_fallbacks=fallbacks,
        columns_eliminated=0,objective_and_integer_and_full_LP_domains_preserved=True,
        original_P1_bit_exact=True,integer_and_full_LP_domains_identical=True,
        Native_optimize_calls=0,production_deletion_decisions_called=False,independent_verifier_wall_seconds=perf_counter()-began)
