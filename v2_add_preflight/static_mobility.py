"""Reuse r043 node-flow Compact and exact Static Presolve, without edits.

Grid rows depend only on nonroute coordinates. Original unit aliases/fixed
values are verified by the original independent rational transport checker
before being composed with the pre-screened full electrical blocks.
"""
import time,pickle,threading
import numpy as np
import scipy.sparse as sp
import psutil
from .static_common import *
from .prestart_native import inputs

def exact_unit_alias_closure(p):
    """Static equality forest; direct equations checked by original verifier.

    Flatten each unit-alias component in root-to-leaf proof order. Every
    pivot points to a retained root; no original nonunit/dense pivot is used.
    This avoids revisiting the entire mobility matrix for each alias depth.
    """
    from collections import defaultdict,deque
    A,d=p.A,p.d;parent=np.arange(A.shape[1]);adj=defaultdict(list)
    def root(j):
        while parent[j]!=j:parent[j]=parent[parent[j]];j=int(parent[j])
        return j
    eligible=np.flatnonzero((d['sense']=='=')&(np.diff(A.indptr)==2)&(d['rhs']==0))
    for i in eligible:
        a,b=A.indptr[i:i+2];j,k=map(int,A.indices[a:b]);w=A.data[a:b]
        if w[0]!=-w[1] or abs(w[0])!=1.:continue
        x,y=root(j),root(k)
        if x==y:continue
        parent[x]=y;adj[j].append((k,int(i)));adj[k].append((j,int(i)))
    groups=defaultdict(list)
    for j in adj:groups[root(j)].append(j)
    plans={}
    for nodes in groups.values():
        low=max(d['lower'][j] for j in nodes);high=min(d['upper'][j] for j in nodes)
        if low>high:raise ValueError('EXACT_UNIT_ALIAS_DOMAIN_CONTRADICTION')
        binary=any(d['types'][j]=='B' for j in nodes)
        candidates=[j for j in nodes if d['lower'][j]==low and d['upper'][j]==high and (not binary or d['types'][j]=='B')]
        if not candidates:continue
        selected=min(candidates);seen={selected};queue=deque([selected])
        while queue:
            j=queue.popleft()
            for k,i in adj[j]:
                if k in seen:continue
                seen.add(k);queue.append(k)
                plans[k]=({selected:1.},0.,i,'EXACT_STATIC_UNIT_ALIAS_CLOSURE')
    count=p.substitute(plans)
    return dict(unit_alias_variables=count,components=len(groups),
        proof='Root-to-leaf original unit equality forest; retained root box/type implies each eliminated domain',
        nonunit_or_dense_pivots=0)

def build():
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_may_campaign_native90.m_model import verify_transport
    res=init();start=time.perf_counter();dest=RUN/'mobility';dest.mkdir(exist_ok=True)
    pack=RUNTIME/'integration/FULL96_MATRIX_PORT_PACK'
    A=sp.load_npz(pack/'MOBILITY.npz')
    with np.load(pack/'MOBILITY_DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    sites,initial,routes,battery,receipt=inputs(read(day['files']['native']['path']),INITIAL)
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    peak=[0];done=threading.Event()
    def sample():
        while not done.wait(.1):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();error=None;proof=None
    try:
        c=Compact(A,d,arcs,initial,96);p=Presolve(c.A,c.d)
        closure_rounds=[]
        while True:
            guard(start);step=exact_unit_alias_closure(p);closure_rounds.append(step)
            if len(closure_rounds)%12==0:print('EXACT ALIAS STATIC ROUND',len(closure_rounds),step,flush=True)
            if step['unit_alias_variables']==0:break
        closure=dict(rounds=closure_rounds,unit_alias_variables=sum(s['unit_alias_variables'] for s in closure_rounds),
            optimizer_calls=0,preprocessing_only=True)
        print('EXACT UNIT ALIAS CLOSURE TOTAL',closure['unit_alias_variables'],len(closure_rounds),flush=True)
        for name in ('fixed','row_scan','audit_pivots'):
            original=getattr(p,name)
            def guarded(*a,_fn=original,**kw):
                guard(start);out=_fn(*a,**kw);guard(start);return out
            setattr(p,name,guarded)
        B,e=p.run()
        # Instance wrappers are observers only, never persisted or executed
        # as original algorithm functions by a campaign.
        for name in ('fixed','row_scan','audit_pivots'):delattr(p,name)
        proof=verify_transport(c,p)
        sp.save_npz(dest/'SELECTED.npz',B);np.savez_compressed(dest/'DOMAIN.npz',**e)
        with (dest/'TRANSPORT.pkl').open('wb') as f:pickle.dump(dict(compact=c,presolve=p,graph=(sites,initial,arcs,battery,receipt)),f,pickle.HIGHEST_PROTOCOL)
        # Transport of grid input coordinates is exactly a fixed value or one
        # retained unit alias. No floating coefficient products are introduced.
        pos={int(j):k for k,j in enumerate(p.col_ids)};steps={int(s['column']):s for s in p.steps}
        def resolve(j):
            if j in pos:return pos[j],0.
            s=steps[j]
            if not s['terms']:return -1,float(s['constant'])
            assert len(s['terms'])==1 and next(iter(s['terms'].values()))==1. and s['constant']==0
            return resolve(int(next(iter(s['terms']))))
        mapping=np.array([resolve(j)[0] for j in range(A.shape[1])],dtype=np.int64)
        offset=np.array([resolve(j)[1] for j in range(A.shape[1])])
        np.savez_compressed(dest/'ORIGINAL_MAP.npz',column=mapping,constant=offset)
        report=dict(PASS=True,proof=proof,original=dict(variables=A.shape[1],rows=A.shape[0],nonzeros=A.nnz,binary=int(np.sum(d['types']=='B'))),
            selected=dict(variables=B.shape[1],rows=B.shape[0],nonzeros=B.nnz,binary=int(np.sum(e['types']=='B'))),
            steps=len(p.steps),rounds=p.rounds,static_unit_alias_closure=closure,original_8_unit_route_domain_unchanged=True,
            source_algorithms=[record(ROOT/q) for q in ('v42_supercompact/formulation.py','v42_supercompact/presolve.py')],
            transport=record(dest/'TRANSPORT.pkl'),grid_coordinate_map=record(dest/'ORIGINAL_MAP.npz'),
            Native_calls=0,resources=res)
    except BaseException as exc:
        import traceback
        error=repr(exc);report=dict(PASS=False,error=error,traceback=traceback.format_exc(),Native_calls=0)
    finally:done.set();th.join(1)
    report.update(wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0])
    put('ORIGINAL_STATIC_PRESOLVE_MESS8.json',report)
    print('ORIGINAL STATIC PRESOLVE',report['PASS'],error,flush=True)

if __name__=='__main__':build()
