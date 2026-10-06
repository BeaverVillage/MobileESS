"""Independent rational certificate replay from frozen C2. No audit/support imports."""
from .common import *
from fractions import Fraction as Q
from collections import defaultdict,Counter
from v42_redundancy.replay import row_hash
from v42_strengthening.analysis import graph_inputs
import time

def vec(A,d,i):
    a,b=A.indptr[i:i+2];sg=-1 if d['sense'][i]=='>' else 1
    return {int(j):Q(sg*float(w)) for j,w in zip(A.indices[a:b],A.data[a:b])},Q(sg*float(d['rhs'][i]))
def local_proof(A,d,p,retained):
    bl=p['block'];ch,dis,q,stay=[bl[k] for k in ['Pch','Pdis','Q','stay']];total=defaultdict(Q);rr=Q(0)
    for f,weight in zip(p['certificate']['support'],p['certificate']['multipliers']):
        weight=Q(weight);assert weight>=0
        if f<16:
            i=bl['rows'][f];assert i in retained;v,r=vec(A,d,i)
        else:
            name='connected_Pdis' if f==16 else 'connected_Pch';physical=dis if f==16 else ch
            matches=[]
            # Native local supporting rows immediately precede the PCS block.
            for i in range(max(0,bl['rows'][0]-6),bl['rows'][0]):
                v,r=vec(A,d,i)
                if family(d['row_names'][i])==name and physical in v:matches.append((i,v,r))
            assert len(matches)==1;i,v,r=matches[0];assert i in retained
            assert v=={stay:Q(-300),physical:Q(1)} and r==0
            v=dict(v);other=ch if f==16 else dis;assert d['lower'][other]==0;v[other]=Q(-1)
        for j,w in v.items():total[j]+=weight*w
        rr+=weight*r
    slack=Q(p['certificate']['slack']);assert slack>=0 and d['lower'][stay]==0;total[stay]-=slack
    total={j:w for j,w in total.items() if w};target,r=vec(A,d,p['row']);assert total==target and rr==r
    return 'EXACT_NONNEGATIVE_FARKAS_AND_BOUNDS'

def independent_affine(A,d,sites,units):
    N=len(sites);directions={};constants={};timeid={};bindings={};vf=[family(v) for v in d['names']];byname={str(n):j for j,n in enumerate(d['names'])};cache={}
    for j,n in enumerate(d['names']):
        f=vf[j]
        if f in ['Pch','Pdis','Q']:
            u,s,t=str(n).split('[',1)[1][:-1].split(',');k=(units.index(u)*3+['Pch','Pdis','Q'].index(f))*N+sites.index(s);directions[j]={k:Q(1)};constants[j]=Q(0);timeid[j]=int(t)
        elif f.startswith(('injection_','response_')) and d['lower'][j]==d['upper'][j]:
            directions[j]={};constants[j]=Q(float(d['lower'][j]));timeid[j]=int(str(n).split('[',1)[1].split(',')[1 if f.startswith('injection_') else 0])
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if not f.endswith('_binding'):continue
        v,r=vec(A,d,i);piv=[j for j in v if vf[j]==f[:-8]];assert len(piv)==1 and d['sense'][i]=='=';j=piv[0];assert v[j]==1 and j not in bindings;bindings[j]=i
    def expand(j):
        if j in directions:return directions[j],constants[j]
        i=bindings[j];v,r=vec(A,d,i);terms=[(k,-w) for k,w in v.items() if k!=j];result=defaultdict(Q);constant=r;tt=set();key=[]
        for k,w in terms:
            dep,c=expand(k);constant+=w*c;tt.add(timeid[k]);key.append((tuple(dep.items()),w))
        signature=tuple(key)
        if signature in cache:result=cache[signature]
        else:
            for k,w in terms:
                for q,x in directions[k].items():result[q]+=w*x
            result={q:x for q,x in result.items() if x};cache[signature]=result
        assert len(tt)<=1;directions[j]=result;constants[j]=constant;timeid[j]=next(iter(tt)) if tt else int(str(d['names'][j]).split('[',1)[1].split(',')[0]);return result,constant
    for j in bindings:expand(j)
    return directions,constants,timeid,bindings

def run():
    begin=time.perf_counter();A,d=load();B,e=load('C3A');certs=read('C3_ROW_CERTIFICATES.json')
    with np.load(OUT/'C3_RETAINED_AXES.npz') as z:rows=z['rows'];cols=z['columns']
    retained=set(map(int,rows));assert np.array_equal(cols,np.arange(A.shape[1]));assert (A[rows]!=B).nnz==0
    for k in ['rhs','sense','row_names']:assert np.array_equal(d[k][rows],e[k])
    for k in ['names','types','objective','constant']:assert np.array_equal(d[k],e[k])
    assert len(certs)+len(rows)==A.shape[0] and {p['row'] for p in certs}==set(range(A.shape[0]))-retained
    methods=Counter();minimum=None
    for p in certs:
        i=p['row'];assert row_hash(A,d,i)==p['row_SHA256'] and p['classification']=='FULL_LP_REDUNDANT'
        kind=p['kind']
        if kind in ['PCS_FARKAS','Q_LINK_FARKAS']:method=local_proof(A,d,p,retained)
        elif kind=='FLOW_EQUALITY_SUM':
            assert all(j in retained and d['sense'][j]=='=' for j in p['support']);v,r=vec(A,d,i);total=defaultdict(Q);rr=Q(0)
            for j in p['support']:
                w,t=vec(A,d,j);rr+=t
                for k,x in w.items():total[k]+=x
            assert {k:x for k,x in total.items() if x}==v and rr==r;method='EXACT_RETAINED_FLOW_EQUALITY_SUM'
        elif kind in ['EXACT_DUPLICATE','EXACT_PROPORTIONAL_DOMINANCE']:
            j=p['representative'];assert j in retained;v,r=vec(A,d,i);w,t=vec(A,d,j);assert set(v)==set(w);scale=next(iter(v.values()))/next(iter(w.values()));assert scale>0 or d['sense'][i]=='=';assert all(v[k]==scale*w[k] for k in v);assert r==scale*t if d['sense'][i]=='=' else r>=scale*t;method='EXACT_RETAINED_ROW_IMPLICATION'
        elif kind=='ORIGINAL_BOUNDS':
            v,r=vec(A,d,i);upper=sum((w*Q(float(d['upper'][j] if w>0 else d['lower'][j])) for j,w in v.items()),Q(0));assert upper<=r;method='EXACT_C2_VARIABLE_BOUNDS'
        elif kind=='CONSTANT_SAFE':v,r=vec(A,d,i);assert not v;assert r==0 if d['sense'][i]=='=' else r>=0;method='EXACT_CONSTANT_SAFE'
        elif kind=='CORRELATED_UNION_SUPPORT':continue
        else:raise AssertionError(kind)
        methods[method]+=1
    sites,initial,arcs,battery,receipt=graph_inputs();units=sorted(initial);N=len(sites);reach=np.zeros((4,96,N),bool)
    # Independent physical-state inventory includes C2 end-stay aliases; PR161
    # mapping replay proves these exact original connected-state definitions.
    for n in d['names']:
        if str(n).startswith('Pch['):u,s,t=str(n)[4:-1].split(',');reach[units.index(u),int(t),sites.index(s)]=True
    dirs,const,times,defs=independent_affine(A,d,sites,units)
    # Reconstruct the exact local polygon directly from the first C2 block and
    # enumerate pair intersections, independently of production polytope code.
    ids=[i for i,n in enumerate(d['row_names']) if family(n)=='PCS16'][:16];planes=[]
    for i in ids:
        v,r=vec(A,d,i);p=next((x for j,x in v.items() if family(d['names'][j])=='Pdis'),Q(0));q=next((x for j,x in v.items() if family(d['names'][j])=='Q'),Q(0));c=-next(x for j,x in v.items() if family(d['names'][j]) in ['route_flow','node_activity']);planes.append((p,q,c))
    planes.extend([(Q(1),Q(0),Q(300)),(Q(-1),Q(0),Q(300))]);points=set()
    for i,(a,b,c) in enumerate(planes):
        for p,q,r in planes[:i]:
            den=a*q-b*p
            if not den:continue
            x=(c*q-b*r)/den;y=(a*r-c*p)/den
            if all(s*x+t*y<=u for s,t,u in planes):points.add((x,y))
    assert len(points)==12
    tablecache={};supportcache={}
    def exact_support(v,t):
        key=tuple(sorted(v.items()))
        if key not in tablecache:
            table=[]
            for u in range(4):
                values=[]
                for s in range(N):
                    ch=v.get((u*3)*N+s,Q(0));pd=v.get((u*3+1)*N+s,Q(0));qq=v.get((u*3+2)*N+s,Q(0))
                    val=max([Q(0)]+[pd*x+qq*y for x,y in points])+max(Q(0),ch+pd)*Q(300);values.append(val)
                table.append(values)
            tablecache[key]=table
        if (key,t) not in supportcache:
            table=tablecache[key];supportcache[key,t]=sum((max([Q(0)]+[table[u][s] for s in np.flatnonzero(reach[u,t])]) for u in range(4)),Q(0))
        return supportcache[key,t]
    # Independent interval support is batched; exact rational support is a
    # fallback for close certificates. Anti-correlation is checked exactly,
    # rather than copied from production's simultaneous-dispatch error term.
    def interval_support_batch(vectors,ts):
        K=len(vectors);pl=np.zeros((K,4,N));ph=pl.copy();ql=pl.copy();qh=pl.copy();common=pl.copy()
        def enclosure(x):
            y=float(x);return (y if Q(y)<=x else np.nextafter(y,-np.inf),y if Q(y)>=x else np.nextafter(y,np.inf))
        for k,v in enumerate(vectors):
            for u in range(4):
                for s in range(N):
                    pd=v.get((3*u+1)*N+s,Q(0));qq=v.get((3*u+2)*N+s,Q(0));ch=v.get(3*u*N+s,Q(0));pl[k,u,s],ph[k,u,s]=enclosure(pd);ql[k,u,s],qh[k,u,s]=enclosure(qq);common[k,u,s]=enclosure(max(Q(0),ch+pd)*Q(300))[1]
        value=np.zeros((K,4,N))
        for x,y in points:
            xl,xh=enclosure(x);yl,yh=enclosure(y)
            a=np.nextafter(np.maximum.reduce([pl*xl,pl*xh,ph*xl,ph*xh]),np.inf);b=np.nextafter(np.maximum.reduce([ql*yl,ql*yh,qh*yl,qh*yh]),np.inf);value=np.maximum(value,np.nextafter(a+b,np.inf))
        value=np.nextafter(value+common,np.inf);upper=np.zeros(K)
        for u in range(4):upper=np.nextafter(upper+np.max(np.where(reach[u,np.asarray(ts)],value[:,u,:],0),axis=1),np.inf)
        return upper
    bounds=list(csv.DictReader((OUT/'BOUND_TIGHTENING_V2.csv').open(encoding='utf-8')));boundids=set();interval_results={};fallbacks=0
    for start in range(0,len(bounds),256):
        chunk=bounds[start:start+256];js=[int(p['column']) for p in chunk];vs=[dirs[j] for j in js];ts=[times[j] for j in js]
        ups=interval_support_batch(vs,ts);downs=interval_support_batch([{q:-x for q,x in v.items()} for v in vs],ts)
        for j,u,l in zip(js,ups,downs):interval_results[j]=(const[j]-Q(float(l)),const[j]+Q(float(u)))
    for no,p in enumerate(bounds):
        j=int(p['column']);assert j not in boundids;boundids.add(j);tt=times[j];v=dirs[j];c=const[j];lower,upper=interval_results[j]
        if Q(float(p['new_lower']))>lower or Q(float(p['new_upper']))<upper:
            upper=c+exact_support(v,tt);lower=c-exact_support({q:-x for q,x in v.items()},tt);fallbacks+=1
        assert Q(float(p['new_lower']))<=lower and Q(float(p['new_upper']))>=upper,(j,p['name'],'UNSAFE_BOUND')
        assert float(p['old_lower'])==d['lower'][j] and float(p['old_upper'])==d['upper'][j];assert e['lower'][j]==float(p['new_lower']) and e['upper'][j]==float(p['new_upper'])
        if (no+1)%10000==0:print('INDEPENDENT_BOUND_REPLAY',no+1,flush=True)
    for j in set(range(A.shape[1]))-boundids:assert e['lower'][j]==d['lower'][j] and e['upper'][j]==d['upper'][j]
    rho=int(np.flatnonzero(d['names']=='rho_max')[0])
    for p in certs:
        if p['kind']!='CORRELATED_UNION_SUPPORT':continue
        i=p['row'];v,r=vec(A,d,i);aff=defaultdict(Q);base=Q(0);tt=set()
        for j,w in v.items():
            if j==rho:base+=w*Q(float(d['upper'][j] if w>=0 else d['lower'][j]));continue
            tt.add(times[j]);base+=w*const[j]
            for q,x in dirs[j].items():aff[q]+=w*x
        assert len(tt)<=1;upper=base+exact_support({q:x for q,x in aff.items() if x},next(iter(tt)) if tt else 0);assert upper<r-Q(1e-8)*max(Q(1),abs(r),abs(upper));slack=float(r-upper);minimum=slack if minimum is None else min(minimum,slack);methods['INDEPENDENT_EXACT_RATIONAL_ROUTE_PCS_SUPPORT']+=1
    for label in ['C3B','C3C']:
        C,f=load(label);assert (C!=B).nnz==0
        for k in e:assert np.array_equal(f[k],e[k])
    mutations=[];p=next(p for p in certs if p['kind']=='PCS_FARKAS')
    import copy
    for name in ['NEGATIVE_FARKAS','SLACK_CHANGE','REMOVED_SUPPORT']:
        bad=copy.deepcopy(p);keep=retained.copy()
        if name=='NEGATIVE_FARKAS':bad['certificate']['multipliers'][0]='-1'
        elif name=='SLACK_CHANGE':bad['certificate']['slack']=str(Q(bad['certificate']['slack'])+1)
        else:keep.remove(bad['block']['rows'][bad['certificate']['support'][0]])
        rejected=False
        try:local_proof(A,d,bad,keep)
        except (AssertionError,ValueError):rejected=True
        assert rejected;mutations.append(dict(mutation=name,rejected=True))
    result=dict(PASS=True,all_C2_rows_checked=A.shape[0],retained_rows=len(rows),removed_rows=len(certs),removed_row_methods=dict(methods),new_bounds_checked=len(bounds),source_definitions_reconstructed=len(defs),independent_bound_exact_fallbacks=fallbacks,canonical_support_tables=len(tablecache),minimum_security_slack=minimum,columns_eliminated=0,physical_mapping='Identity for all C2 columns',C2_to_C3='Every new bound and removed inequality is a consequence of retained C2 rows and original bounds over the full continuous relaxation',C3_to_C2='Retained native matrix is an exact row subset with all columns/objective/types unchanged; independent certificates reconstruct every missing row',integer_and_full_LP_feasible_sets_identical=True,coefficient_rounding=False,production_deletion_decisions_called=False,mutation_rejections=mutations,wall=time.perf_counter()-begin)
    write('ULTRACOMPACT_INDEPENDENT_VERIFICATION.json',result);print('C3_INDEPENDENT_PASS',result,flush=True);return result
if __name__=='__main__':run()
