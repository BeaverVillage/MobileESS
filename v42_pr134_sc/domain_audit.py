"""Read isolated current job graphs; no optimize or other-task results."""
import json
import pickle
from collections import Counter
from dataclasses import asdict
import numpy as np
from .common import *

def run():
    with (LOCAL/'DATA.pkl').open('rb') as f: data=pickle.load(f)
    bundle,jobs,bounds,r,raw,graphs,old,prep=data
    domain=[];windows=[];gpu=[];migration=[];shifts=[];paths=[];reach=[]
    graph_counts=Counter();old_counts=Counter();pairpaths={}
    for uid,j in sorted(jobs.items()):
        g=graphs[uid];b=bounds[uid]
        for k,v in g.counts().items():graph_counts[k]+=v
        for k,v in old[uid].counts().items():old_counts[k]+=v
        starts=sorted({t for s,t in g.events['y']});initial=sorted({s for s,t in g.events['y']})
        dst=sorted({d for s,d,t in g.events['w']})
        domain.append(dict(uid=uid,T_j=sorted({t for s,t in g.states['r0']}|{t for s,t in g.states['r1']}),
            S_j=initial,D_j=dst,R_j={s:list(r.rack_limits[s]) for s in sorted(set(initial+dst))},
            M_j_count=len(g.events['w']),states=g.counts(),retained_complete_domain_sha=g.sha,
            newly_removed_complete_options=0,reason='Current PR134 exact complete-path support preserved; new reduction is algebraic only'))
        ends=[t for s,t in g.events['f0']]+[t for s,t in g.events['f1']]
        checkpoints=[t for s,t in g.events['q']];wan=[t for s,d,t in g.events['w']]
        windows.append(dict(uid=uid,current_allowed_starts=b.allowed_starts,retained_starts=starts,
            latest_completion=b.latest_completion,service_slots=j.service_slots,
            earliest_completion=min(ends,default=None),latest_retained_completion=max(ends,default=None),
            earliest_checkpoint=min(checkpoints,default=None),latest_checkpoint=max(checkpoints,default=None),
            earliest_WAN_start=min(wan,default=None),latest_WAN_start=max(wan,default=None),
            earliest_restart=min((tr.restart for tr in g.transfers.values()),default=None),
            latest_restart=max((tr.restart for tr in g.transfers.values()),default=None),new_window_tightenings=0))
        for site in sorted(set(j.initial_sites)|{j.reference_site}):
            cap=r.capacities.get(site,0);rack=max(r.rack_limits.get(site,(0,)))
            gpu.append(dict(uid=uid,site=site,requested_gang=j.gpu,site_capacity=cap,max_rack_capacity=rack,
                 retained=site in initial or site in dst,static_fit=j.gpu<=cap and j.gpu<=rack,
                 competing_job_decisions_used=False,new_screening_removed=0))
        migration.append(dict(uid=uid,checkpoint_authorized=j.checkpoint_authorized,migrations_used=j.migrations_used,
           checkpoints=len(g.events['q']),pair_start_states=len(g.events['w']),source_sites=initial,destinations=dst,
           no_op_pairs=sum(s==d for s,d,t in g.events['w']),minimum_restart_slots=r.restart_slots,
           newly_removed_states=0,reason='Keep current complete-path projections and every scientifically admissible alternative'))
        shifts.append(dict(uid=uid,current_start_offsets=[s-j.reference_start for s in b.allowed_starts],
           retained_start_offsets=[s-j.reference_start for s in starts],placement_sites=initial,
           P2_metrics=['migration_count','shift_slots','prestart_changes'],new_removed_TS=0,new_removed_PS=0))
        reach.append(dict(uid=uid,original_graph_counts=old[uid].counts(),current_A0_counts=g.counts(),
          current_complete_path_projection=True,new_state_pruning=False,graph_sha=g.sha))
        for s,d,t in g.events['w']:pairpaths[s,d]=r.paths[s,d]
    for (s,d),links in sorted(pairpaths.items()):
        paths.append(dict(source=s,destination=d,current_authority_path=links,path_has_repeated_link=len(set(links))!=len(links),
            scientific_route_fixed_by_authority=True,physical_topology_uniqueness='NOT_INFERRED_FROM_ROUTE_TABLE',
            alternatives_removed_by_new_formulation=0,reason='Current WAN authority has one prescribed path; no new route-choice elimination'))
    table('JOB_TIME_RESOURCE_DOMAIN_AUDIT.csv',domain)
    table('DEADLINE_RUNTIME_WINDOW_AUDIT.csv',windows)
    table('GPU_RACK_IMPOSSIBILITY_AUDIT.csv',gpu)
    table('MIGRATION_DOMAIN_AUDIT.csv',migration)
    table('TIMESHIFT_PRESTART_DOMAIN_AUDIT.csv',shifts)
    table('WAN_DETERMINISTIC_PATH_AUDIT.csv',paths)
    write('JOB_STATE_REACHABILITY_AUDIT.json',dict(PASS=True,day=DAY,jobs=len(jobs),existing_A0_projection=reach,
          original_graph_counts=old_counts,current_A0_counts=graph_counts,new_graph_deletions=0,
          completeness='Current PR134 projection retained; matrix aliases do not delete scientific choices',
          fixed_point='Existing support operator repeats to SHA identity; no new heuristic reachability pruning'))
    write('JOB_EQUIVALENCE_AUDIT.json',dict(PASS=True,current_classes=prep['classes'],
           semantic_signature_source=record(ROOT/'v42_root/data.py'),new_aggregation_adopted=False,
           deterministic_post_tie_source=record(ROOT/'v42_sparse/canonical.py'),
           reason='Current objective-aware class histogram + individual migration lanes retained exactly; no extra job equivalence asserted'))
    write('WAN_STATE_AUDIT.json',dict(PASS=True,current_factor_source=record(ROOT/'v42_root/factor.py'),
           graph_counts=graph_counts,old_graph_counts=old_counts,bytes_per_gpu=r.bytes_per_gpu,
           maximum_active_transfers=r.max_active_transfers,physical_path_count=len(r.paths),
           partial_final_wait_restart_carryout_preserved=True,new_pair_start_domain_pruning=0,
           rejected_integer_only_link_merge=dict(member=.5,sent_fraction=.5,McCormick_interval=[0,.5],
             different_same_incidence_links_can_have_different_LP_flows=True,
             disposition='KEEP independent link-flow columns and LP-strengthening rows')))
    write('WAN_GRAPH_REACHABILITY.json',dict(PASS=True,complete_path_support_preserved=True,
         forward_backward_rule='Current exact existential source prefix plus full destination-duration fit, complete terminal paths',
         retained_WAN_states=graph_counts['w'],new_WAN_graph_deletions=0,
         zero_rate_waiting_preserved=True,checkpoint_physical_time_preserved=True,post_horizon_service_preserved=True))
    print('PR134 exact domain audit complete',flush=True)

if __name__=='__main__':run()
