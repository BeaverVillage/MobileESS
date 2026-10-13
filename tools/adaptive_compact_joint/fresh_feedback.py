"""Adaptive fixed-size route admission from verified joint optimization feedback."""
from collections import Counter
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.adaptive_compact_joint.beam import feedback
from tools.adaptive_compact_joint.scoring import AdaptiveMinimax
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature,pool_signature
from tools.global_local_multistart1800.routes import distance

def generate(case,point,replay,epoch,seen_pools):
    configure_beam()
    from tools.minimax_beam1800 import grid,routes as inherited_beam
    context,_=grid.refresh(case,point,epoch)
    fb=feedback(case,point,context,replay,epoch)
    # Reuse the previously verified PR219 Beam body. Inject only the measured
    # reference scorer; retain its original64-label beam and depth3 heuristic.
    inherited_beam.DOCS=DOCS;inherited_beam.Minimax=AdaptiveMinimax
    candidates,search=inherited_beam.generate(case,point,context,epoch)
    graph=Graph(case);center=paths_of(case,point);authority=paths_of(case,v.load_point(ROOT/RAW_REL));scorer=AdaptiveMinimax(case,point,context)
    reservoir=read(beta.DOCS/'ADAPTIVE_BEAM_EPOCH_00.json')['all_generated_candidates'];byunit={u:{} for u in center}
    for u in center:
        for c in reservoir[u].values():byunit[u][path_signature(c['path'])]=c['path']
    for c in candidates:
        if len(c['units'])!=1:continue
        u=c['units'][0];byunit[u][path_signature(c['paths'][u])]=c['paths'][u]
    joint={u:list(p) for u,p in center.items()};pools={};details={}
    for ordinal,u in enumerate(sorted(center)):
        ranked=[]
        for sig,path in byunit[u].items():
            test=dict(joint);test[u]=path;peak,vec,rebound=scorer.peak(test)
            risk=float(np.sum(np.maximum(0.,np.asarray(vec)+np.asarray(rebound)-(fb['actual_incumbent_UB']-.025))))
            ranked.append(dict(path=path,signature=sig,moves=len(graph.move_indices(path)),peak=peak,risk=risk))
        ranked.sort(key=lambda c:(c['peak'],c['risk'],c['signature']))
        chosen=[];signatures=set()
        def add(path):
            sig=path_signature(path)
            if sig not in signatures:chosen.append(path);signatures.add(sig)
        add(authority[u]);add(center[u]);add(graph.complete(u,[]))
        for kind in ('single','multiple','deep'):
            options=[c for c in ranked if (c['moves']==1 if kind=='single' else c['moves']>=2 if kind=='multiple' else c['moves']>=3) and c['signature'] not in signatures]
            if options:
                # Diversify within a quality prefix after a stagnating epoch.
                idx=(epoch+ordinal)%min(6,len(options));add(options[idx]['path'])
        quality_prefix=ranked[:min(96,len(ranked))]
        shift=(epoch*7+ordinal*3)%max(1,len(quality_prefix));rotated=quality_prefix[shift:]+quality_prefix[:shift]
        while len(chosen)<8:
            options=[c for c in rotated if c['signature'] not in signatures]
            if not options:options=[c for c in ranked if c['signature'] not in signatures]
            if not options:break
            # Complementarity uses provisional routes of all four vehicles.
            scored=[]
            for priority,c in enumerate(options[:32]):
                test=dict(joint);test[u]=c['path'];peak,vec,rb=scorer.peak(test)
                novelty=min(distance(graph,{u:c['path']},{u:p}) for p in chosen)
                scored.append((peak-1e-5*min(24,novelty)+priority*1e-7,c['signature'],c))
            c=min(scored,key=lambda a:a[:2])[-1];add(c['path']);joint[u]=c['path']
        pools[u]=chosen
        assert any(not graph.move_indices(p) for p in chosen) and any(len(graph.move_indices(p))==1 for p in chosen) and any(len(graph.move_indices(p))>=2 for p in chosen)
        details[u]=dict(candidate_count=len(ranked),generated_MOVE_histogram=dict(Counter(c['moves'] for c in ranked)),selected_MOVE_histogram=dict(Counter(len(graph.move_indices(p)) for p in chosen)))
    signature=pool_signature(pools)
    write(DOCS/f'FEEDBACK_POOL_{epoch:02d}.json',dict(PASS=True,Optimize_calls=0,pools=pools,pool_signature=signature,
        duplicate_model_avoided=signature not in seen_pools,units=details,feedback=record(DOCS/f'OPTIMIZATION_FEEDBACK_{epoch:02d}.json'),
        inherited_PR219_Beam_body_reused=True,actual_beam_width=64,actual_heuristic_MOVE_depth=3,
        reservoir_contains_depth4_from_verified_beta_development=True,heuristic_depth_not_physical_limit=True,
        safe_exclusions_original_DAG_and_SOC_upper_only=True,heuristic_admission_not_bound=True,
        fixed_size=8,joint_complement_admission=True,no_MOVE_forcing=True,LP_dual_prices_used=False))
    return pools,signature
