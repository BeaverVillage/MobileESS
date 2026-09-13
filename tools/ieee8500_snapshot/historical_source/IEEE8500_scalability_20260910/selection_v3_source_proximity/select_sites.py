"""Frozen deterministic topology-only finite search; no OpenDSS import."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import hashlib, json, time
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

ROOT=Path(__file__).resolve().parent; BASE=ROOT.parent
INPUTS=['audit/candidate_pool_static_features.json','audit/candidate_pair_metrics.npz','audit/melbourne_12_anchors.json','audit/melbourne_66_pair_geometry.json','audit/primary_corridors.json','audit/methodology_inputs.json','audit/buses.json']
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def initialize():
    global ids,xy,D,R,G,groups,M,mnorm,mpair,mnn,I,J,dmx,gmx
    old={r['path']:r['sha256'] for r in read(BASE/'FREEZE_MANIFEST.json')['files']}
    for p in INPUTS:assert sha(BASE/p)==old[p],p
    f=read(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')
    for r in f['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    for r in f['inputs']:assert sha(BASE/r['path'])==r['sha256'],r['path']
    a=np.load(BASE/'audit/candidate_pair_metrics.npz',allow_pickle=False)
    ids=a['buses'];xy=a['geographic_xy'];D=a['electrical_tree_distance_ohm'];R=a['shared_upstream_path_ratio'];G=cdist(xy,xy)
    assert len(ids)==638 and list(ids)==sorted(ids)
    features=read(BASE/'audit/candidate_pool_static_features.json');assert [f['bus'] for f in features]==list(ids)
    labels=sorted(set(f['lateral_group'] for f in features)); groups=np.array([labels.index(f['lateral_group']) for f in features])
    assert labels[-1]=='TRUNK_OR_MINOR_LATERAL'
    anchors=read(BASE/'audit/melbourne_12_anchors.json')
    M=np.array([[a['x_east_km'],a['y_north_km']] for a in anchors]);M-=M.mean(axis=0);mnorm=M/np.sqrt(np.mean(np.sum(M*M,axis=1)))
    I,J=np.triu_indices(12,1);md=cdist(M,M);mpair=md[I,J]/np.sqrt(np.mean(md[I,J]**2))
    np.fill_diagonal(md,np.inf);mnn=np.argsort(md,axis=1,kind='stable')[:,:2]
    dmx=float(D.max());gmx=float(G.max())
    # Additional outcome-blind hard guard; retain original objective normalizers.
    rootdist=np.array([f['primary_upstream_impedance_ohm'] for f in features])
    cutoff=float(np.quantile(rootdist,.05,method='linear'))
    guard=read(ROOT/'ROOT_DISTANCE_GUARD_AUDIT.json')
    assert cutoff==guard['root_distance_q05_ohm']
    keep=np.flatnonzero(rootdist>=cutoff)
    ids=ids[keep];xy=xy[keep];groups=groups[keep]
    D=D[np.ix_(keep,keep)];R=R[np.ix_(keep,keep)];G=G[np.ix_(keep,keep)]
    assert len(ids)==guard['remaining_count'] and len(ids)==606

def metrics(batch):
    s=np.atleast_2d(batch);q=xy[s];q=q-q.mean(axis=1,keepdims=True)
    den=np.sqrt(np.mean(np.sum(q*q,axis=2),axis=1));qn=q/den[:,None,None]
    h=np.einsum('ia,bic->bac',mnorm,qn)
    trace=np.hypot(h[:,0,0]+h[:,1,1],h[:,0,1]-h[:,1,0])
    ec=np.sqrt(np.maximum(0,2-2*trace/12))
    gp=G[s[:,I],s[:,J]];dp=D[s[:,I],s[:,J]];rp=R[s[:,I],s[:,J]]
    gn=gp/np.sqrt(np.mean(gp*gp,axis=1))[:,None]
    ep=np.sqrt(np.mean((gn-mpair[None,:])**2,axis=1))
    gm=G[s[:,:,None],s[:,None,:]].copy();gm[:,np.arange(12),np.arange(12)]=np.inf
    nn=np.argsort(gm,axis=2,kind='stable')[:,:,:2]
    retention=np.any(nn[:,:,:,None]==mnn[None,:,None,:],axis=3).sum(axis=(1,2))/24
    counts=np.stack([(groups[s]==i).sum(axis=1) for i in range(4)],axis=1)
    distinct=np.all(np.diff(np.sort(s,axis=1),axis=1)!=0,axis=1)
    v=np.stack([np.maximum(0,ec/.20-1),np.maximum(0,ep/.20-1),np.maximum(0,1-retention/.50),np.maximum(0,1-dp.min(axis=1)/.9129072401559803),np.maximum(0,1-gp.min(axis=1)/2221.532547954318),~distinct],axis=1)
    feasible=(v.max(axis=1)==0)
    # Tuple fields exactly match methodology v2; all labels sorted lowercase.
    objective=np.stack([rp.max(axis=1),rp.mean(axis=1),-dp.min(axis=1)/dmx,-(counts[:,:3]>0).sum(axis=1),-(counts>0).sum(axis=1),(counts*counts).sum(axis=1),-gp.min(axis=1)/gmx,ec,ep,-retention],axis=1)
    objective=np.round(objective,9)
    return {'feasible':feasible,'objective':objective,'vmax':v.max(axis=1),'vsum':v.sum(axis=1),'ec':ec,'ep':ep,'retention':retention,'min_d':dp.min(axis=1),'mean_d':dp.mean(axis=1),'max_r':rp.max(axis=1),'mean_r':rp.mean(axis=1),'min_g':gp.min(axis=1)}

def key(s,m,i=0):
    if m['feasible'][i]:return (0,*m['objective'][i],*map(int,s))
    return (1,round(float(m['vmax'][i]),12),round(float(m['vsum'][i]),12),round(float(m['ec'][i]+m['ep'][i]),12),*map(int,s))

def best(batch,m,feasible_only=False):
    idx=np.flatnonzero(m['feasible']) if feasible_only else range(len(batch))
    return min(idx,key=lambda i:key(batch[i],m,i),default=None)

def local(s,repair,max_sweeps):
    s=s.copy();m=metrics(s);cur=key(s,m);log=[]
    for sweep in range(max_sweeps):
        if repair and m['feasible'][0]:return s,{'sweeps':sweep,'stop':'feasible','trace':log}
        changes=0
        for site in range(12):
            choices=np.setdiff1d(np.arange(len(ids)),np.delete(s,site))
            batch=np.tile(s,(len(choices),1));batch[:,site]=choices
            mm=metrics(batch);i=best(batch,mm,not repair)
            if i is not None:
                kk=key(batch[i],mm,i)
                if kk<cur:
                    s=batch[i].copy();cur=kk;m=metrics(s);changes+=1
            if repair and m['feasible'][0]:break
        if not(repair and m['feasible'][0]):
            batch=np.tile(s,(66,1));batch[np.arange(66),I]=s[J];batch[np.arange(66),J]=s[I]
            mm=metrics(batch);i=best(batch,mm,not repair)
            if i is not None and key(batch[i],mm,i)<cur:
                s=batch[i].copy();m=metrics(s);cur=key(s,m);changes+=1
        log.append({'sweep':sweep+1,'changes':changes,'feasible':bool(m['feasible'][0]),'vmax':float(m['vmax'][0]),'max_r':float(m['max_r'][0])})
        if not changes:return s,{'sweeps':sweep+1,'stop':'no_improvement','trace':log}
    return s,{'sweeps':max_sweeps,'stop':'sweep_limit','trace':log}

def run():
    initialize();start=time.monotonic()
    radius=np.sqrt(np.mean(np.sum((xy-xy.mean(axis=0))**2,axis=1)))
    lo=xy.min(axis=0);hi=xy.max(axis=0);fracs=[.2,.35,.5,.65,.8];starts=set()
    for angle in range(0,360,5):
        t=np.deg2rad(angle);rot=np.array([[np.cos(t),-np.sin(t)],[np.sin(t),np.cos(t)]])
        for scale in [.30,.40,.50,.60,.70,.80,.90]:
            shape=mnorm@rot.T*radius*scale
            for fx in fracs:
                for fy in fracs:
                    target=shape+lo+np.array([fx,fy])*(hi-lo)
                    _,idx=linear_sum_assignment(cdist(target,xy,metric='sqeuclidean'))
                    starts.add(tuple(map(int,idx)))
    batch=np.array(sorted(starts));m=metrics(batch)
    feasible=sorted(np.flatnonzero(m['feasible']),key=lambda i:key(batch[i],m,i))[:32]
    infeasible=sorted(np.flatnonzero(~m['feasible']),key=lambda i:key(batch[i],m,i))[:64]
    summary={'geometric_transforms':12600,'unique_mappings':len(batch),'geometric_feasible_count':int(m['feasible'].sum()),'repair_starts':len(infeasible),'geometric_feasible_retained':len(feasible),'versions':{'numpy':np.__version__,'scipy':scipy.__version__},'global_optimality':'NOT_CERTIFIED','seed':0,'random_draws':0,'source_compile':False,'loads_added':0,'scenario_runs':0}
    print(json.dumps(summary),flush=True)
    pool={tuple(batch[i]) for i in feasible};repair_log=[]
    for j,i in enumerate(infeasible):
        s,log=local(batch[i],True,12);mm=metrics(s)
        if mm['feasible'][0]:pool.add(tuple(s))
        repair_log.append({'start_rank':j+1,'start_indices':batch[i].tolist(),'final_indices':s.tolist(),**log})
        if (j+1)%8==0:print(f'repair {j+1}/64 feasible_pool={len(pool)} elapsed={time.monotonic()-start:.1f}s',flush=True)
    (ROOT/'repair_log.json').write_text(json.dumps(repair_log,indent=2),encoding='utf-8')
    summary['feasible_after_repair']=len(pool)
    if not pool:
        summary['status']='DETERMINISTIC_PROCEDURE_NO_FEASIBLE_SELECTION_FOUND'
        (ROOT/'search_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return
    batch2=np.array(sorted(pool));m2=metrics(batch2);take=sorted(range(len(batch2)),key=lambda i:key(batch2[i],m2,i))[:16]
    descent_log=[]
    for j,i in enumerate(take):
        s,log=local(batch2[i],False,20);pool.add(tuple(s));descent_log.append({'start_rank':j+1,'start_indices':batch2[i].tolist(),'final_indices':s.tolist(),**log})
        print(f'feasible descent {j+1}/{len(take)} max_R={metrics(s)["max_r"][0]:.9f} elapsed={time.monotonic()-start:.1f}s',flush=True)
    finalbatch=np.array(sorted(pool));fm=metrics(finalbatch);bi=best(finalbatch,fm,True);selected=finalbatch[bi]
    summary.update(status='PENDING_INDEPENDENT_VERIFICATION',local_starts=len(take),selected_indices=selected.tolist(),mapping={f'AIDC{i+1:02}':str(ids[b]) for i,b in enumerate(selected)},metrics={k:float(v[bi]) for k,v in fm.items() if k not in ['objective','feasible']},lexicographic_objective=fm['objective'][bi].tolist(),elapsed_seconds=time.monotonic()-start)
    (ROOT/'feasible_local_search_log.json').write_text(json.dumps(descent_log,indent=2),encoding='utf-8')
    (ROOT/'search_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':run()
