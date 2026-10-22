"""Complete Source-YY original-row reference, fixed B0 AIDC M1 only.

Reuses the previous original 16-face grid producer. The sole source-text
adaptation is the index of the 48 MESS derivative axes (24 instead of12).
Native0 component rows are written before static screening; no solve occurs.
"""
import inspect, textwrap, time, math, threading
import numpy as np
import scipy.sparse as sp
import psutil
from .static_common import *
from .full_native import FullGrid,stats
from .full_pack import local_point, numerical, domain
from .prestart_native import native_zero

PACK=RUN/'SOURCE_YY_FULL96'
N_AUX=34329

class YYGrid(FullGrid):
    def __init__(self,start,rec):
        self.started=start;self.blocks=[];self.slots=[];self.equivalence=[]
        self.axes=read(OUT/'SOURCE_YY_GRID_AXES.json');self.manifest=dict(records=[rec])
        self.parent=np.flatnonzero(self.axes['parent_mask']);self.security=np.flatnonzero(self.axes['security_mask'])
        self.cos=np.cos(2*np.pi*np.arange(16)/16);self.sin=np.sin(2*np.pi*np.arange(16)/16)

body=textwrap.dedent(inspect.getsource(FullGrid.build))
assert body.count('[12:')==9
ns=dict(FullGrid.build.__globals__,put=put,guard=guard)
exec(compile(body.replace('[12:','[24:'),__file__,'exec'),ns)
YYGrid.build=ns['build']

def build():
    import gurobipy as gp
    from v42_integrated.matrix import arrays
    init();start=time.perf_counter();PACK.mkdir(exist_ok=True)
    from shutil import copy2
    old=RUNTIME/'integration/FULL96_MATRIX_PORT_PACK'
    for name in ('MOBILITY.npz','MOBILITY_DOMAIN.npz','MOBILITY_POINT.npy','OBJECTIVES.json','MOBILITY_RECEIPT.json'):
        if not (PACK/name).exists():copy2(old/name,PACK/name)
        assert record(PACK/name)['sha256']==record(old/name)['sha256']
    mob=read(PACK/'MOBILITY_RECEIPT.json')
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
    nbase=len(md['names']);nfull=nbase+96*N_AUX;names={str(n):j for j,n in enumerate(md['names'])}
    peak=[0];done=threading.Event()
    def sample():
        while not done.wait(.1):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start()
    blocks=[];err=None
    try:
        # A zip path can exist before its central directory has been flushed.
        # Consume only the completed horizon manifest, never file existence
        # or a timing delay as an input-commit signal.
        manifest=OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json'
        while not manifest.exists():guard(start);time.sleep(3)
        coefficients=read(manifest);assert coefficients['PASS']
        committed={r['slot']:r for r in coefficients['records']}
        for t in range(96):
            guard(start);folder=PACK/f'{t:02d}';folder.mkdir(exist_ok=True)
            if (folder/'RECEIPT.json').exists():blocks.append(read(folder/'RECEIPT.json'));continue
            path=RUN/'coefficients'/f'{t:02d}.npz'
            # Bounded producer dependency; this is an isolated preparation job.
            while not path.exists():guard(start);time.sleep(3)
            time.sleep(.2)
            rec=dict(slot=t,**record(path));assert rec['sha256']==committed[t]['sha256']
            g=YYGrid(start,rec)
            m=gp.Model('SOURCE_YY_ORIGINAL_FULL_COMPONENT');m.Params.OutputFlag=0
            sites=list(mob['sites']);p={(s,0):m.addVar(lb=-gp.GRB.INFINITY,name='port_P_'+s) for s in sites}
            q={(s,0):m.addVar(lb=-gp.GRB.INFINITY,name='port_Q_'+s) for s in sites}
            try:
                with native_zero():
                    objectives=g.build(m,p,q);m.setObjective(objectives[0][1]);m.update();A,d=arrays(m)
                assert len(d['names'])==34378 and d['names'][48]=='rho_max'
                with np.load(path) as z:a={k:z[k] for k in z.files}
                # Local reference uses a conservative epigraph value1. Voltage
                # feasibility is recorded, never assumed from old DY witnesses.
                point=local_point(d,a,g.axes,1.);local=numerical(A,d['rhs'],d['sense'],point,d)
                ii=[];jj=[];vv=[]
                for k,s in enumerate(sites):
                    for u in INITIAL:
                        for prefix,sign in [('Pdis',1.),('Pch',-1.)]:
                            key=f'{prefix}[{u},{s},{t}]'
                            if key in names:ii.append(k);jj.append(names[key]);vv.append(sign)
                        key=f'Q[{u},{s},{t}]'
                        if key in names:ii.append(24+k);jj.append(names[key]);vv.append(1.)
                ii.append(48);jj.append(names['rho_max']);vv.append(1.)
                for k in range(N_AUX):ii.append(49+k);jj.append(nbase+t*N_AUX+k);vv.append(1.)
                S=sp.csr_matrix((vv,(ii,jj)),shape=(A.shape[1],nfull))
                B=(A@S).tocsr();B.eliminate_zeros();B.sort_indices()
                assert B.shape==(210617,nfull) and np.all(np.isin(S.data,[-1.,1.]))
                sp.save_npz(folder/'MATRIX.npz',B)
                np.savez_compressed(folder/'DOMAIN.npz',names=d['names'][49:],lower=d['lower'][49:],upper=d['upper'][49:],types=d['types'][49:])
                np.savez_compressed(folder/'ROWS.npz',rhs=d['rhs'],sense=d['sense'],local_names=d['row_names'])
                np.save(folder/'POINT.npy',point[49:])
                rr=dict(slot=t,rows=B.shape[0],columns=nfull,nonzeros=B.nnz,local_Native0=local,
                    coefficient=rec,all_blocks=g.blocks,
                    files={p.name:record(p) for p in folder.iterdir() if p.is_file()})
                (folder/'RECEIPT.json').write_text(__import__('json').dumps(rr,indent=2),encoding='utf-8');blocks.append(rr)
            finally:m.dispose()
            put('SOURCE_YY_FULL_REFERENCE_PROGRESS.json',dict(completed=t+1,wall_seconds=time.perf_counter()-start))
            if t%4==0:print('SOURCE_YY FULL',t,B.nnz,round(time.perf_counter()-start,1),flush=True)
    except Exception as exc:
        import traceback
        err=dict(error=repr(exc),traceback=traceback.format_exc())
    finally:done.set();th.join(1)
    ma=sp.load_npz(PACK/'MOBILITY.npz')
    identity=dict(source=SOURCE,hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),
        fixed_AIDC='Original May01 B0 Planning only',mobility=record(PACK/'MOBILITY.npz'),
        domain=record(PACK/'MOBILITY_DOMAIN.npz'),blocks=[dict(slot=b['slot'],files=b['files'],coefficient=b['coefficient']) for b in blocks])
    put('SOURCE_YY_ORIGINAL_FULL_REFERENCE.json',dict(PASS=err is None and len(blocks)==96,error=err,
        case_sha=digest(identity),identity=identity,binary=int(np.sum(md['types']=='B')),
        continuous=nfull-int(np.sum(md['types']=='B')),variables=nfull,
        rows=ma.shape[0]+sum(b['rows'] for b in blocks),nonzeros=ma.nnz+sum(b['nonzeros'] for b in blocks),
        grid_slots=len(blocks),component_Native0_only=True,whole_Native0=False,
        fixed_B0_M1_only=True,A1_A2_M2_bound=False,Native_optimize_calls=0,
        wall_seconds=time.perf_counter()-start,peak_RSS_bytes=peak[0]))

if __name__=='__main__':build()
