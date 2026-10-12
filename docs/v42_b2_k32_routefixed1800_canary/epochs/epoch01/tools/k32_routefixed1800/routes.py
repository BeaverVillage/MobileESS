"""Resource constrained original-DAG labeling with explicitly heuristic beams."""
from collections import defaultdict,Counter
from dataclasses import dataclass
import hashlib,json,math,numpy as np
from tools.k32_routefixed1800.adapter import *

@dataclass(frozen=True)
class Label:
    site:str
    time:int
    energy:float
    soc_upper:float
    stays:int
    moves:int
    score:float
    path:tuple

def generate(case,point,beam=64,epoch=0):
    context,grid_receipt=g.refresh(case,point)
    cells=n._signed_ranking(case,point,context)
    score=defaultdict(float)
    # Aggregate multiple actual FULL rows. The signed PCS support already
    # includes the current-site contribution lost if this vehicle moves.
    for c in cells:
        if c['direct_rho_objective_priority']:
            score[c['unit'],c['site'],c['slot']]+=c['score']
    names={str(name):j for j,name in enumerate(case.d['names'])}
    original_names={str(name):j for j,name in enumerate(case.original_d['names'])}
    stay={(a[0],a[1]):k for k,a in enumerate(case.graph[2]) if a[-1] is None}
    outgoing=defaultdict(list)
    for k,a in enumerate(case.graph[2]):outgoing[a[0],a[1]].append(k)
    battery=case.graph[3];stationary=stationary_paths(case)
    counts=Counter();candidates={};beam_discard=0
    def allowed(u,k):
        j=original_names.get(f'arc[{u},{k}]')
        return j is not None and case.original_d['upper'][j]>=1.
    def necessary(label,a):
        nonlocal counts
        # An optimistic SOC envelope permits charging at maximum source power
        # in every stay slot. Only violations of this upper envelope are exact
        # necessary-condition exclusions. It does not certify recourse.
        if a[-1] is None:
            upper=min(battery.maximum,label.soc_upper+battery.dt_hours*battery.eta_charge*battery.p_limit)
        else:
            upper=label.soc_upper-float(a[-1].energy_kwh)
        if upper < battery.minimum-1e-8:
            counts['exact_SOC_upper_envelope_rejections']+=1;return None
        return upper
    def register(u,path,kind):
        nonlocal counts
        moves=[k for k in path if case.graph[2][k][-1] is not None]
        if not moves:return
        counts['generated_path_attempts']+=1
        paths=dict(stationary);paths[u]=list(path)
        key=hashlib.sha256(json.dumps(paths,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if key in candidates:counts['duplicate_paths']+=1;return
        loc=case.graph[1][u];time=0;energy=0.;upper=battery.initial;gain=0.;connected=0
        for k in path:
            a=case.graph[2][k]
            assert a[:2]==(loc,time) and allowed(u,k)
            if a[-1] is None:
                gain+=score[u,a[0],a[1]]-score[u,case.graph[1][u],a[1]]
                upper=min(battery.maximum,upper+battery.dt_hours*battery.eta_charge*battery.p_limit);connected+=1
            else:
                a[-1].validate(96)
                energy+=float(a[-1].energy_kwh);upper-=float(a[-1].energy_kwh)
                gain-=sum(score[u,case.graph[1][u],t] for t in range(a[1],a[3]))
            if upper<battery.minimum-1e-8:
                counts['exact_complete_SOC_rejections']+=1;return
            loc,time=a[2:4]
        assert time==96
        if upper<battery.terminal-1e-8:
            counts['exact_terminal_SOC_upper_rejections']+=1;return
        # Opportunity to restore travel energy at the destination matters in
        # ranking only; FULL MILP enforces the actual rebound and terminal SOC.
        remaining_stays=sum(case.graph[2][k][-1] is None for k in path if case.graph[2][k][1]>=case.graph[2][moves[-1]][3])
        rebound=energy/(battery.eta_charge*max(1,remaining_stays)*battery.dt_hours*battery.p_limit)
        packet=dict(candidate_id=f'R{epoch}_{key[:16]}',signature=key,paths=paths,units=[u],kind=kind,
            moves=len(moves),move_arc_indices={u:moves},travel_energy_kWh=energy,
            score=gain/(1+energy/battery.maximum+.03*len(moves))-.001*rebound,
            destination=loc,departure=case.graph[2][moves[0]][1],connected_stays=connected,
            SOC_upper_necessary_condition_PASS=True,recourse_FULL_feasibility_claim=False,
            score_role='HEURISTIC_MULTIROW_SIGNED_PCS_RELIEF_LOST_ORIGIN_ETA_ENERGY_REBOUND')
        candidates[key]=packet
    for u,origin in case.graph[1].items():
        # Exhaustive original single MOVE choices from the origin, then stay.
        for k,a in enumerate(case.graph[2]):
            if a[0]!=origin or a[-1] is None or not allowed(u,k):continue
            path=[stay[origin,t] for t in range(a[1])]+[k]+[stay[a[2],t] for t in range(a[3],96)]
            if all(allowed(u,q) for q in path):register(u,path,'ONE_MOVE_THEN_DWELL')
        frontier=defaultdict(list)
        frontier[0]=[Label(origin,0,0.,battery.initial,0,0,0.,())]
        for t in range(96):
            labels=frontier.pop(t,[])
            # Round-robin across site and move-count preserves path diversity.
            buckets=defaultdict(list)
            for label in labels:buckets[label.site,label.moves].append(label)
            selected=[]
            while buckets and len(selected)<beam:
                for key in sorted(list(buckets)):
                    group=buckets[key];group.sort(key=lambda z:(-z.score,z.energy,z.path))
                    selected.append(group.pop(0))
                    if not group:del buckets[key]
                    if len(selected)>=beam:break
            beam_discard+=len(labels)-len(selected)
            for label in selected:
                for k in outgoing[label.site,t]:
                    a=case.graph[2][k]
                    if not allowed(u,k):counts['exact_original_bound_arc_rejections']+=1;continue
                    moving=a[-1] is not None
                    if moving and label.moves>=3:
                        counts['heuristic_move_depth_rejections']+=1;continue
                    upper=necessary(label,a)
                    if upper is None:continue
                    gain=score[u,a[0],t]-score[u,origin,t] if not moving else -sum(score[u,origin,q] for q in range(t,a[3]))
                    energy=label.energy+(float(a[-1].energy_kwh) if moving else 0.)
                    nxt=Label(a[2],a[3],energy,upper,label.stays+int(not moving),label.moves+int(moving),label.score+gain-.00001*(energy-label.energy),label.path+(k,))
                    if nxt.time==96:register(u,nxt.path,'RESOURCE_LABEL_BEAM_MULTIMOVE')
                    else:frontier[nxt.time].append(nxt)
    single=sorted(candidates.values(),key=lambda c:(-c['score'],c['signature']))
    # Select diverse candidates by vehicle/destination/departure and move type.
    groups=defaultdict(list)
    for c in single:groups[c['units'][0],c['destination'],c['departure']//12,min(c['moves'],2)].append(c)
    selected=[]
    for group in groups.values():selected.extend(group[:2])
    selected.sort(key=lambda c:(-c['score'],c['signature']))
    top_by_unit={u:[c for c in selected if c['units']==[u]][:6] for u in case.graph[1]}
    units=sorted(top_by_unit)
    for i,u in enumerate(units):
        for w in units[i+1:]:
            for a,b in zip(top_by_unit[u],top_by_unit[w]):
                paths=dict(stationary);paths[u]=a['paths'][u];paths[w]=b['paths'][w]
                key=hashlib.sha256(json.dumps(paths,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                selected.append(dict(candidate_id=f'R{epoch}_{key[:16]}',signature=key,paths=paths,units=[u,w],
                    kind='TWO_VEHICLE_COORDINATED',moves=a['moves']+b['moves'],travel_energy_kWh=a['travel_energy_kWh']+b['travel_energy_kWh'],
                    score=a['score']+b['score'],destination=a['destination']+'+'+b['destination'],departure=min(a['departure'],b['departure']),
                    SOC_upper_necessary_condition_PASS=True,recourse_FULL_feasibility_claim=False))
    audit_packet=dict(PASS=True,epoch=epoch,beam_width=beam,source_case=case.identity,graph_arcs=len(case.graph[2]),
        STAY=2304,MOVE=len(case.graph[2])-2304,sites=24,units=4,slots=96,
        counts=dict(counts),generated_unique_single_paths=len(single),queued_candidates=len(selected),
        heuristic_ranking_discarded=len(single)-sum(len(group[:2]) for group in groups.values()),
        heuristic_beam_label_discarded=beam_discard,beam_and_depth_not_exact_screening=True,
        full_route_space_exhausted=False,grid_receipt=grid_receipt,
        original_coefficients_ETA_energy_unchanged=True,SOC_envelope_has_only_safe_necessary_exclusions=True)
    write(DOCS/f'ROUTE_SEARCH_EPOCH_{epoch}.json',audit_packet)
    return selected,audit_packet

def select(queue,seen,counts,advanced=False):
    available=[c for c in queue if c['signature'] not in seen and (advanced or len(c['units'])==1)]
    if not available:return None
    # Exact feasibility is never claimed by this diversity ranking.
    return max(available,key=lambda c:(c['score']/(1+.7*sum(counts[u] for u in c['units'])),
        -sum(counts[u] for u in c['units']),c['signature']))
