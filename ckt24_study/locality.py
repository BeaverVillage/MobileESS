"""Topology and local nameplate ratios, explicitly distinct from feasible control."""
from .preflight import *
from .screening import settle
from .traffic import readcsv
from collections import defaultdict,deque

def analyze():
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());adj=defaultdict(list)
    for r in inv['lines']:
        a,b=[r[k].split('.')[0].lower() for k in ['bus1','bus2']]
        adj[a].append((b,'line.'+r['line']));adj[b].append((a,'line.'+r['line']))
    for r in inv['transformers']:
        a=r['windings'][0]['bus'].split('.')[0].lower()
        for w in r['windings'][1:]:
            b=w['bus'].split('.')[0].lower();name='transformer.'+r['transformer']
            adj[a].append((b,name));adj[b].append((a,name))
    def reachable(origin,exclude=None):
        seen={origin};queue=deque([origin])
        while queue:
            a=queue.popleft()
            for b,name in adj[a]:
                if name!=exclude and b not in seen:seen.add(b);queue.append(b)
        return seen
    depth={'sourcebus':0};queue=deque(depth)
    while queue:
        a=queue.popleft()
        for b,_ in adj[a]:
            if b not in depth:depth[b]=depth[a]+1;queue.append(b)
    oriented=[]
    for r in inv['lines']:
        a,b=[r[k].split('.')[0].lower() for k in ['bus1','bus2']]
        upstream,downstream=(a,b) if depth.get(a,10**9)<=depth.get(b,10**9) else (b,a)
        oriented.append(dict(line=r['line'],upstream=upstream,downstream=downstream,
            source_depth_up=depth.get(upstream),source_depth_down=depth.get(downstream),
            authority='Undirected connectivity shortest source depth; bridge test separately determines radial downstream component'))
    csvout('TOPOLOGY_ORIENTATION.csv',oriented);orient={r['line']:r for r in oriented}
    slot=json.loads((DOC/'ORIGINAL_BASELINE_SUMMARY.json').read_text())['peak_slot']
    e=context('local_ratios');settle(e,slot);c=e.ActiveCircuit;loads=[]
    for name in c.Loads.AllNames:
        c.Loads.Name=name;a=c.ActiveCktElement
        power=np.asarray(a.Powers).reshape(-1,2).sum(axis=0)
        loads.append(dict(load=name,bus=a.BusNames[0].split('.')[0].lower(),p_kw=float(power[0]),q_kvar=float(power[1])))
    candidate={r['bus'] for r in readcsv(DOC/'MV_PCC_CANDIDATES.csv')}
    top=readcsv(DOC/'B0_MV_LV_BOTTLENECKS.csv')
    linepeaks={}
    for r in top:linepeaks[r['line']]=max(linepeaks.get(r['line'],0),float(r['loading_pu']))
    rows=[]
    for name in sorted(linepeaks,key=linepeaks.get,reverse=True)[:20]:
        o=orient[name];down=reachable(o['downstream'],'line.'+name);bridge='sourcebus' not in down
        downstream=[r for r in loads if r['bus'] in down] if bridge else []
        p=sum(r['p_kw'] for r in downstream);nc=len(candidate&down) if bridge else 0
        rows.append(dict(line=name,slot=slot,upstream=o['upstream'],downstream=o['downstream'],bridge=bridge,
            downstream_load_p_kw=p if bridge else '',downstream_load_q_kvar=sum(r['q_kvar'] for r in downstream) if bridge else '',
            downstream_candidate_MV_buses=nc,
            local_MESS_P_nameplate_upper_bound_kw=(2400 if nc else 0) if bridge else '',
            local_MESS_nameplate_upper_bound_ratio=(2400/p if nc else 0) if bridge and p>0 else '',
            local_AIDC_feasible_control_ratio='',local_AIDC_ratio_status='NO_FINAL_MAPPING_AND_ACTUAL_JOB_WITNESS',
            rating_ratio_is_schedule_feasibility=False,ports_and_PCS_joint_PQ_certified=False))
    csvout('LOCAL_CONTROL_RATIOS.csv',rows)
    e.ClearAll()

if __name__=='__main__':analyze()
