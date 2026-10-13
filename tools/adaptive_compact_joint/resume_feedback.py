"""Feedback every pool; expensive label expansion periodically, fixed8 admission."""
from collections import Counter,defaultdict
from tools.adaptive_compact_joint.resume_adapter import *
from tools.adaptive_compact_joint.beam import feedback
from tools.adaptive_compact_joint.scoring import AdaptiveMinimax
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature,pool_signature
from tools.global_local_multistart1800.routes import distance

def generate(case,point,replay,epoch,seen):
    configure()
    from tools.minimax_beam1800 import grid,routes as beam_body
    context,_=grid.refresh(case,point,epoch)
    fb=feedback(case,point,context,replay,epoch);scorer=AdaptiveMinimax(case,point,context);graph=Graph(case)
    reservoir_path=DOCS/'BEAM_RESERVOIR.json'
    reservoir=read(reservoir_path)['units'] if reservoir_path.exists() else {u:{} for u in graph.origins}
    expanded=not reservoir_path.exists() or epoch%6==0
    if expanded:
        beam_body.DOCS=DOCS;beam_body.Minimax=AdaptiveMinimax
        queue,search=beam_body.generate(case,point,context,epoch)
        for c in queue:
            if len(c['units'])==1:
                u=c['units'][0];path=c['paths'][u];reservoir[u][path_signature(path)]=path
        beta_pool=read(beta.DOCS/'ADAPTIVE_BEAM_EPOCH_00.json')['all_generated_candidates']
        for u in reservoir:
            for c in beta_pool[u].values():reservoir[u][c['path_signature']]=c['path']
        write(reservoir_path,dict(PASS=True,units=reservoir,last_expansion_epoch=epoch,beam_width=64,heuristic_depth3=True,depth4_reservoir=True))
    base=paths_of(case,point);authority=paths_of(case,v.load_point(ROOT/RAW_REL));joint={u:list(p) for u,p in base.items()}
    all_ranked={}
    for u in sorted(base):
        for path in (graph.complete(u,[]),base[u],authority[u]):reservoir[u][path_signature(path)]=path
        ranked=[]
        for sig,path in reservoir[u].items():
            test=dict(joint);test[u]=path;peak,vec,rebound=scorer.peak(test);moves=graph.move_indices(path)
            meta=graph.metadata({u:path})['actual_moves'];key=(moves and meta[0]['depart']//12,tuple(sorted({m['destination'] for m in meta})),len(moves),moves and meta[-1]['connect']//12)
            ranked.append(dict(signature=sig,path=path,peak=peak,risk=float(np.sum(np.maximum(0.,np.asarray(vec)+np.asarray(rebound)-(fb['actual_incumbent_UB']-.025)))),moves=len(moves),diversity_key=str(key)))
        ranked.sort(key=lambda a:(a['peak'],a['risk'],a['signature']));all_ranked[u]=ranked
    # More than one deterministic admission variant handles exhausted signatures;
    # each has all4 decision rights and never enumerates route combinations as MILPs.
    selected=None
    for variant in range(12):
        pools={};joint={u:list(p) for u,p in base.items()}
        for ui,u in enumerate(sorted(base)):
            ranked=all_ranked[u];chosen=[];sigs=set()
            def add(path):
                sig=path_signature(path)
                if sig not in sigs:chosen.append(path);sigs.add(sig)
            add(authority[u]);add(base[u]);add(graph.complete(u,[]))
            for depth in (1,2,3):
                options=[a for a in ranked if (a['moves']==1 if depth==1 else a['moves']>=depth) and a['signature'] not in sigs]
                if options:
                    idx=(epoch*3+ui+variant*7)%min(len(options),48);add(options[idx]['path'])
            groups=defaultdict(list)
            for a in ranked:groups[a['diversity_key']].append(a)
            representatives=sorted((group[0] for group in groups.values()),key=lambda a:(a['peak'],a['signature']))
            shift=(epoch*11+ui*7+variant*13)%max(1,len(representatives));order=representatives[shift:]+representatives[:shift]+ranked
            while len(chosen)<8:
                options=[a for a in order if a['signature'] not in sigs]
                if not options:break
                scored=[]
                for priority,a in enumerate(options[:24]):
                    test=dict(joint);test[u]=a['path'];peak,_,_=scorer.peak(test)
                    novelty=min(distance(graph,{u:a['path']},{u:p}) for p in chosen)
                    scored.append((peak-1e-5*min(24,novelty)+priority*1e-7,a['signature'],a))
                best=min(scored,key=lambda a:a[:2])[-1];add(best['path']);joint[u]=best['path']
            pools[u]=chosen
            assert len(chosen)==8 and any(not graph.move_indices(p) for p in chosen) and any(len(graph.move_indices(p))==1 for p in chosen) and any(len(graph.move_indices(p))>=2 for p in chosen)
        signature=pool_signature(pools)
        if not all(form+'|'+signature in seen for form in ('JOINT','DIRECT')):selected=(pools,signature,variant);break
    if selected is None:return None,None
    pools,signature,variant=selected
    write(DOCS/f'ADAPTIVE_POOL_{epoch:03d}.json',dict(PASS=True,Optimize_calls=0,pools=pools,pool_signature=signature,epoch=epoch,variant=variant,
        feedback=record(DOCS/f'OPTIMIZATION_FEEDBACK_{epoch:02d}.json'),expensive_Beam_expansion=expanded,
        actual_result_feedback_every_pool=True,beam_width=64,heuristic_MOVE_depth3=True,original_physical_depth_not_restricted=True,
        fixed_pool_size=8,no_MOVE_forcing=True,LP_dual_prices_used=False,
        units={u:dict(reservoir=len(reservoir[u]),selected_MOVE_histogram=dict(Counter(len(graph.move_indices(p)) for p in pools[u]))) for u in pools}))
    return pools,signature
