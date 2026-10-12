"""Minimax look-ahead labels and cross-product complementary vehicle paths."""
from collections import defaultdict,Counter
from dataclasses import dataclass
import hashlib,json,numpy as np
from tools.minimax_beam1800.adapter import *
from tools.minimax_beam1800.grid import Minimax

@dataclass(frozen=True)
class Label:
    site:str
    time:int
    energy:float
    soc_upper:float
    remaining_charging_opportunity:int
    moves:int
    first_depart:int
    reconnect:int
    relief_vector:tuple
    active_service_windows:tuple
    peak:float
    path:tuple

def generate(case,point,context,epoch=0):
    scoring=Minimax(case,point,context);battery=case.graph[3];base=scoring.baseline_paths
    names={str(n):j for j,n in enumerate(case.original_d['names'])}
    stay={(a[0],a[1]):k for k,a in enumerate(case.graph[2]) if a[-1] is None}
    outgoing=defaultdict(list)
    for k,a in enumerate(case.graph[2]):outgoing[a[0],a[1]].append(k)
    counters=Counter();single={};beam_discard=0
    def allowed(u,k):
        j=names.get(f'arc[{u},{k}]');return j is not None and case.original_d['upper'][j]>=1.
    def register(u,path,kind):
        nonlocal counters
        counters['generated_complete_paths']+=1;loc=case.graph[1][u];t=0;upper=battery.initial
        for k in path:
            a=case.graph[2][k];assert a[:2]==(loc,t)
            if not allowed(u,k):counters['exact_original_arc_domain_rejections']+=1;return
            upper=min(battery.maximum,upper+battery.dt_hours*battery.eta_charge*battery.p_limit) if a[-1] is None else upper-float(a[-1].energy_kwh)
            if upper<battery.minimum-1e-8:counters['exact_SOC_upper_rejections']+=1;return
            loc,t=a[2:4]
        if t!=96:raise ValueError('ORIGINAL_TERMINAL_SLOT_NOT96')
        if upper<battery.terminal-1e-8:counters['exact_terminal_SOC_rejections']+=1;return
        paths={w:list(p) for w,p in base.items()};paths[u]=list(path)
        moves={w:[k for k in p if case.graph[2][k][-1] is not None] for w,p in paths.items()}
        if not sum(map(len,moves.values())):return
        sig=hashlib.sha256(json.dumps(paths,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if sig in single:counters['duplicate_physical_paths']+=1;return
        peak,vector,rebound=scoring.peak(paths)
        changed=[k for k in path if case.graph[2][k][-1] is not None]
        if not changed:return
        first=case.graph[2][changed[0]];last=case.graph[2][changed[-1]]
        before=sum(int(first[3]<=int(slot)) for slot in scoring.times)
        energy=sum(float(case.graph[2][k][-1].energy_kwh) for p in paths.values() for k in p if case.graph[2][k][-1] is not None)
        single[sig]=dict(candidate_id=f'M{epoch}_{sig[:16]}',signature=sig,paths=paths,units=[u],kind=kind,
            moves=sum(map(len,moves.values())),travel_energy_kWh=energy,score=context['current_verified_UB']-peak,
            estimated_peak_loading=peak,critical_relief_vector=(scoring.loading-np.asarray(vector)).tolist(),
            heuristic_rebound_vector=rebound,departure=first[1],first_arrive=first[-1].arrive,first_reconnect=first[3],
            destination=loc,critical_before_reconnect_ratio=1-before/max(1,len(scoring.times)),
            targets_before_reconnect=[int(t) for t in scoring.times if t<first[3]],
            remaining_charging_opportunity=sum(case.graph[2][k][-1] is None for k in path if case.graph[2][k][1]>=last[3]),
            SOC_upper_necessary_condition_PASS=True,rank_is_heuristic=True,recourse_FULL_feasibility_claim=False)
    for u,origin in case.graph[1].items():
        # All physically allowed one-MOVE-and-dwell alternatives are explicit
        # original arcs. Ranking decides priority, not mathematical existence.
        for k,a in enumerate(case.graph[2]):
            if a[-1] is None or a[0]!=origin or not allowed(u,k):continue
            path=[stay[origin,t] for t in range(a[1])]+[k]+[stay[a[2],t] for t in range(a[3],96)]
            register(u,path,'ONE_MOVE_THEN_DWELL')
        u_index=scoring.units.index(u);initial=np.zeros(scoring.m)
        frontier=defaultdict(list);frontier[0]=[Label(origin,0,0.,battery.initial,96,0,-1,0,tuple(initial),(),
            scoring.partial_peak(u,origin,0,initial,battery.initial,96),())]
        for t in range(96):
            labels=frontier.pop(t,[]);unique={z.path:z for z in labels};counters['duplicate_partial_labels']+=len(labels)-len(unique)
            buckets=defaultdict(list)
            for z in unique.values():
                target=int(np.argmax(np.asarray(z.relief_vector))) if z.relief_vector else 0
                buckets[z.site,min(z.moves,2),z.first_depart//12,target//8].append(z)
            selected=[]
            while buckets and len(selected)<64:
                for key in sorted(list(buckets)):
                    group=buckets[key];group.sort(key=lambda z:(z.peak,z.energy,z.path));selected.append(group.pop(0))
                    if not group:del buckets[key]
                    if len(selected)>=64:break
            beam_discard+=len(unique)-len(selected)
            for label in selected:
                for k in outgoing[label.site,t]:
                    a=case.graph[2][k]
                    if not allowed(u,k):counters['exact_original_arc_domain_rejections']+=1;continue
                    moving=a[-1] is not None
                    if moving and label.moves>=3:counters['heuristic_move_depth_rejections']+=1;continue
                    upper=min(battery.maximum,label.soc_upper+battery.dt_hours*battery.eta_charge*battery.p_limit) if not moving else label.soc_upper-float(a[-1].energy_kwh)
                    if upper<battery.minimum-1e-8:counters['exact_label_SOC_upper_rejections']+=1;continue
                    vec=np.asarray(label.relief_vector).copy()
                    # Actual STAY service; transit contributes zero P/Q at all
                    # covered critical times until the stored reconnect slot.
                    if not moving:
                        mask=scoring.times==t;vec[mask]=scoring.support[u_index,scoring.site_id[a[0]],mask]
                    energy=label.energy+(float(a[-1].energy_kwh) if moving else 0.)
                    path=label.path+(k,);reconnect=a[3] if moving else label.reconnect
                    windows=label.active_service_windows+((t,t+1,a[0]),) if not moving else label.active_service_windows
                    nxt=Label(a[2],a[3],energy,upper,96-a[3],label.moves+int(moving),
                        t if moving and label.first_depart<0 else label.first_depart,reconnect,tuple(vec),windows,
                        scoring.partial_peak(u,a[2],a[3],vec,upper,96-a[3]),path)
                    if a[3]==96:register(u,path,'MINIMAX_LOOKAHEAD_MULTIMOVE')
                    else:frontier[a[3]].append(nxt)
    ordered=sorted(single.values(),key=lambda c:(c['estimated_peak_loading'],c['signature']))
    # Retain diverse time/destination/move-count/reconnect groups; all exclusions
    # at this step are explicitly heuristic, not exact infeasibility claims.
    groups=defaultdict(list)
    for c in ordered:groups[c['units'][0],c['departure']//12,c['destination'],min(c['moves'],2),c['first_reconnect']//12].append(c)
    queue=[c for values in groups.values() for c in values[:2]]
    queue.sort(key=lambda c:(c['estimated_peak_loading'],c['signature']))
    top={u:[c for c in queue if c['units']==[u]][:8] for u in case.graph[1]};units=sorted(top);pairs=[]
    for i,u in enumerate(units):
        for w in units[i+1:]:
            cross=[]
            for a in top[u]:
                for b in top[w]:
                    paths={x:list(p) for x,p in base.items()};paths[u]=a['paths'][u];paths[w]=b['paths'][w]
                    sig=hashlib.sha256(json.dumps(paths,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    peak,vec,rebound=scoring.peak(paths)
                    moves=sum(case.graph[2][k][-1] is not None for p in paths.values() for k in p)
                    energy=sum(float(case.graph[2][k][-1].energy_kwh) for p in paths.values() for k in p if case.graph[2][k][-1] is not None)
                    complement=int(np.argmax(a['critical_relief_vector'])!=np.argmax(b['critical_relief_vector']))
                    cross.append(dict(candidate_id=f'M{epoch}_{sig[:16]}',signature=sig,paths=paths,units=[u,w],kind='CROSS_PRODUCT_COOPERATIVE',
                        moves=moves,travel_energy_kWh=energy,score=context['current_verified_UB']-peak,estimated_peak_loading=peak,
                        critical_relief_vector=(scoring.loading-np.asarray(vec)).tolist(),heuristic_rebound_vector=rebound,
                        complementary_critical_targets=bool(complement),departure=min(a['departure'],b['departure']),
                        first_arrive=min(a['first_arrive'],b['first_arrive']),first_reconnect=min(a['first_reconnect'],b['first_reconnect']),
                        destination=a['destination']+'+'+b['destination'],rank_is_heuristic=True,recourse_FULL_feasibility_claim=False))
            counters['cooperative_cross_product_combinations']+=len(cross)
            cross.sort(key=lambda c:(c['estimated_peak_loading'],-c['complementary_critical_targets'],c['signature']))
            pairs.extend(cross[:12]);counters['cooperative_heuristic_deferred']+=max(0,len(cross)-12)
    queue.extend(pairs);queue.sort(key=lambda c:(c['estimated_peak_loading'],c['signature']))
    audit_packet=dict(PASS=True,epoch=epoch,beam_width=64,max_MOVE_depth_per_unit=3,
        generated_unique_single_paths=len(single),queued_single_paths=len(queue)-len(pairs),queued_cooperative=len(pairs),
        counts=dict(counters),heuristic_beam_pruned=beam_discard,heuristic_ranking_deferred=len(single)-(len(queue)-len(pairs)),
        all_exact_physical_exclusions_are_original_arc_or_SOC_necessary_conditions=True,
        no_exact_dominance_claim=True,full_route_space_exhausted=False,
        score_formula='Verified current UB - max_k(base_without_MESS_k + joint route-conditioned PCS support_k + in-horizon travel-rebound estimate_k)',
        partial_lookahead='Original direct arcs with depart>=label time and connect<=critical slot; optimistic separate future choices, SOC upper envelope, no dominance claim',
        original_ETA_energy_and_terminal96_unchanged=True,source_case=case.identity,
        evaluated_history_used_as_solver_start=False)
    write(DOCS/f'ROUTE_SEARCH_EPOCH_{epoch:02d}.json',audit_packet)
    return queue,audit_packet

def choose(queue,seen,counts,index):
    pool=[c for c in queue if c['signature'] not in seen]
    if not pool:return None
    # First four include every vehicle, with genuine moving routes only.
    missing={u for c in pool for u in c['units'] if counts[u]==0}
    if missing:
        single=[c for c in pool if len(c['units'])==1 and c['units'][0] in missing]
        if single:pool=single
    else:
        if index%3==2:
            pairs=[c for c in pool if len(c['units'])==2]
            if pairs:pool=pairs
        # Three score-priority choices, then explicit coverage by vehicle/time.
        if index%4==3:
            least=min(counts[u] for c in pool for u in c['units'])
            pool=[c for c in pool if any(counts[u]==least for u in c['units'])]
    return min(pool,key=lambda c:(c['estimated_peak_loading'],c['signature']))
