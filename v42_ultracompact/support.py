"""Correlated unit-flow/PCS/SOC-safe union support with certified rounding."""
from .common import *
from fractions import Fraction as F
from collections import defaultdict
import hashlib,time
from v42_strengthening.analysis import graph_inputs

def domains(A,d):
    sites,initial,arcs,battery,receipt=graph_inputs();units=sorted(initial);N=len(sites)
    live=defaultdict(list);stay={}
    for j,n in enumerate(d['names']):
        if family(n)=='route_flow':
            u,k=str(n)[11:-1].split(',');live[u].append((int(k),arcs[int(k)]))
        elif family(n)=='Pch':
            u,s,t=str(n)[4:-1].split(',');stay[u,s,int(t)]=True
    reach=np.zeros((4,96,N),bool);records={}
    for z,u in enumerate(units):
        # Removed deterministic end stays have node_activity replacements.
        nodes={(initial[u],0)};edges=live[u]
        for t in range(97):
            for k,a in edges:
                if a[1]==t and a[:2] in nodes:nodes.add(a[2:4])
        for (uu,s,t) in stay:
            if uu==u:reach[z,t,sites.index(s)]=True
        records[u]=dict(actual_flow_arcs=len(edges),reachable_connected_states=int(reach[z].sum()),graph_nodes=len(nodes))
    return dict(sites=sites,units=units,reach=reach,arcs=arcs,initial=initial,battery=battery,records=records)

def exact_sources(A,d,dom):
    """Canonical rational sparse directions shared across times and aliases."""
    N=len(dom['sites']);vf=[family(v) for v in d['names']];keys={};vectors={};constants={};times={};defs={};cache={}
    def intern(v):
        v={k:x for k,x in v.items() if x};payload=';'.join(str(k)+':'+str(v[k]) for k in sorted(v));h=hashlib.sha256(payload.encode()).hexdigest()
        if h in vectors:assert vectors[h]==v
        else:vectors[h]=v
        return h
    zero=intern({})
    for j,n in enumerate(d['names']):
        f=vf[j]
        if f in ['Pch','Pdis','Q']:
            u,s,t=str(n).split('[',1)[1][:-1].split(',');coord=(dom['units'].index(u)*3+['Pch','Pdis','Q'].index(f))*N+dom['sites'].index(s)
            keys[j]=intern({coord:F(1)});constants[j]=F(0);times[j]=int(t)
        elif f.startswith(('injection_','response_')) and d['lower'][j]==d['upper'][j]:
            keys[j]=zero;constants[j]=F(float(d['lower'][j]));times[j]=int(str(n).split('[',1)[1].split(',')[1 if f.startswith('injection_') else 0])
    for i,rn in enumerate(d['row_names']):
        f=family(rn)
        if f.endswith('_binding'):
            a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b];matches=[int(j) for j in js if vf[j]==f[:-8]]
            assert len(matches)==1,(i,f,matches);j=matches[0];assert float(ws[list(js).index(j)])==1 and d['sense'][i]=='=';defs[j]=i
    todo=set(defs)
    while todo:
        progress=False
        for j in list(todo):
            i=defs[j];a,b=A.indptr[i:i+2];terms=[(int(k),F(-float(w))) for k,w in zip(A.indices[a:b],A.data[a:b]) if k!=j]
            if any(k not in keys for k,w in terms):continue
            signature=tuple(sorted((keys[k],str(w)) for k,w in terms));c=F(float(d['rhs'][i]))+sum((w*constants[k] for k,w in terms),F(0))
            if signature not in cache:
                v=defaultdict(F)
                for k,w in terms:
                    for q,x in vectors[keys[k]].items():v[q]+=w*x
                cache[signature]=intern(v)
            keys[j]=cache[signature];constants[j]=c;tt={times[k] for k,w in terms};assert len(tt)<=1
            times[j]=next(iter(tt)) if tt else int(str(d['names'][j]).split('[',1)[1].split(',')[0]);todo.remove(j);progress=True
        assert progress,('UNRESOLVED_NATIVE_AFFINE_DEPENDENCIES',len(todo))
    return keys,vectors,constants,times,defs,intern

def exact_screen(A,d,dom,verts,src):
    from .polytope import down,up
    keys,vectors,constants,times,defs,intern=src;N=len(dom["sites"]);width=12*N;rho=int(np.flatnonzero(d["names"]=="rho_max")[0])
    axis=[i for i,n in enumerate(d["row_names"]) if family(n) in ["line_thermal_face","transformer_kVA","voltage_upper","voltage_lower"]]
    upper=np.full(A.shape[0],np.inf);rowkeys={};counts=defaultdict(int);basevalues={};tvalues={};used=set();evaluations=0
    for start in range(0,len(axis),512):
        chunk=axis[start:start+512];mid=[];err=[];ttlist=[];unique={};targets=[]
        for i in chunk:
            sg=-1 if d["sense"][i]==">" else 1;a,b=A.indptr[i:i+2];aff=defaultdict(F);base=F(0);tt=set()
            for j,w in zip(A.indices[a:b],A.data[a:b]):
                w=F(sg*float(w));j=int(j)
                if j==rho:base+=w*F(float(d["upper"][j] if w>=0 else d["lower"][j]));continue
                assert j in keys;tt.add(times[j]);base+=w*constants[j]
                for q,x in vectors[keys[j]].items():aff[q]+=w*x
            aff={q:x for q,x in aff.items() if x};assert len(tt)<=1;t=next(iter(tt)) if tt else 0
            payload=";".join(str(q)+":"+str(aff[q]) for q in sorted(aff));h=hashlib.sha256(payload.encode()).hexdigest();pair=(h,t)
            rowkeys[i]=h;counts[h]+=1;basevalues[i]=base;tvalues[i]=t;used.add(pair)
            if pair not in unique:
                lo=np.zeros(width);hi=np.zeros(width)
                for q,x in aff.items():lo[q]=down(x);hi[q]=up(x)
                m=(lo+hi)/2;error=np.maximum(m-lo,hi-m);unique[pair]=len(mid);mid.append(m);err.append(error);ttlist.append(t)
            targets.append(unique[pair])
        val=union_upper(np.asarray(mid),np.asarray(err),np.asarray(ttlist),dom,verts);evaluations+=len(mid)
        for i,k in zip(chunk,targets):upper[i]=np.nextafter(up(basevalues[i])+float(val[k]),np.inf)
        if start%50000<512:print("EXACT_GROUPED_SUPPORT",start+len(chunk),"directions",len(counts),"batch_union_evaluations",evaluations,flush=True)
    return np.asarray(axis),upper,rowkeys,dict(counts),basevalues,tvalues,{pair:None for pair in used}

def union_upper(mid,err,ts,dom,verts,base=None):
    N=len(dom['sites']);K=len(mid);result=np.zeros(K) if base is None else base.copy()
    lo=np.nextafter(mid-err,-np.inf);hi=np.nextafter(mid+err,np.inf)
    for z in range(4):
        chlo=lo[:,(3*z)*N:(3*z+1)*N];chhi=hi[:,(3*z)*N:(3*z+1)*N]
        pl=lo[:,(3*z+1)*N:(3*z+2)*N];ph=hi[:,(3*z+1)*N:(3*z+2)*N]
        ql=lo[:,(3*z+2)*N:(3*z+3)*N];qh=hi[:,(3*z+2)*N:(3*z+3)*N]
        # ch/dis anti-correlation follows the injection definitions. This term
        # also conservatively covers simultaneous LP charging/discharging and
        # any affine rounding radius. Pch <= 300*connected stay mass.
        mismatch=np.nextafter(np.maximum(0,chhi+ph)*300,np.inf)
        values=np.zeros((K,N))
        for p,q in verts:
            xl,xh=float(p),float(p);yl,yh=float(q),float(q)
            if F(xl)>p:xl=float(np.nextafter(xl,-np.inf))
            if F(xh)<p:xh=float(np.nextafter(xh,np.inf))
            if F(yl)>q:yl=float(np.nextafter(yl,-np.inf))
            if F(yh)<q:yh=float(np.nextafter(yh,np.inf))
            pv=np.nextafter(np.maximum.reduce([pl*xl,pl*xh,ph*xl,ph*xh]),np.inf)
            qv=np.nextafter(np.maximum.reduce([ql*yl,ql*yh,qh*yl,qh*yh]),np.inf)
            values=np.maximum(values,np.nextafter(pv+qv,np.inf))
        values=np.nextafter(values+mismatch,np.inf)
        mask=dom['reach'][z,ts,:];best=np.max(np.where(mask,values,0),axis=1)
        result=np.nextafter(result+best,np.inf)
    return result
