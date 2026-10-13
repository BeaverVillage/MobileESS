"""Balanced original-DAG global families, minimax ranking and time-space diversity."""
from collections import defaultdict,Counter
from itertools import combinations
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.dag import Graph
from tools.minimax_beam1800.grid import Minimax

def distance(graph,a,b):
    def location(path):
        out=[None]*96
        for k in path:
            ar=graph.arcs[k]
            for t in range(ar[1],ar[3]):out[t]=ar[0] if ar[-1] is None else ('TRANSIT',ar[0],ar[2])
        return out
    return sum(x!=y for u in a for x,y in zip(location(a[u]),location(b[u])))

def generate(case,point,context,epoch=0):
    import tools.minimax_beam1800.grid as score_module
    score_module.DOCS=DOCS
    graph=Graph(case);scorer=Minimax(case,point,context);base=paths_of(case,point)
    stay={u:graph.complete(u,[]) for u in graph.origins};single={};pool=[];seen=set();counts=Counter()
    def register(paths,family,units,kind):
        for u,p in paths.items():graph.validate(u,p)
        sig=hashlib.sha256(json.dumps(paths,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if sig in seen:return
        seen.add(sig);meta=graph.metadata(paths)
        if meta['moves']==0 or paths==base:return
        dist=distance(graph,paths,base)
        if family=='G3' and dist<24:counts['G3_near_route_deferred']+=1;return
        peak,vec,rebound=scorer.peak(paths)
        first=min(a['depart'] for a in meta['actual_moves']);connect=min(a['connect'] for a in meta['actual_moves'])
        destinations=tuple(sorted({a['destination'] for a in meta['actual_moves']}))
        target=int(np.argmax(scorer.loading-np.asarray(vec)))
        cand=dict(candidate_id=f'E{epoch}_{family}_{sig[:12]}',signature=sig,paths=paths,units=units,
            family=family,stage='GLOBAL' if len(units)==1 else 'COOPERATIVE',kind=kind,
            score=INITIAL_UB-peak,estimated_peak_loading=peak,heuristic_rebound_vector=rebound,
            critical_relief_vector=(scorer.loading-np.asarray(vec)).tolist(),distance_slots_from_center=dist,
            diversity_key=[units,first//12,destinations,connect//12,meta['moves'],context['rows'][target]['original_row']],
            rank_is_heuristic=True,recourse_FULL_feasibility_claim=False,**meta)
        counts[family]+=1;pool.append(cand);return cand
    for i,u in enumerate(sorted(graph.origins),1):
        group=[]
        for k,a in enumerate(graph.arcs):
            if a[-1] is None or a[0]!=graph.origins[u] or k not in graph.available[u]:continue
            path=graph.complete(u,[k]);paths=dict(stay);paths[u]=path
            c=register(paths,'G'+str(i),[u],'SOLO_WITH_OTHER_THREE_STAY')
            if c:group.append(c)
        group.sort(key=lambda c:(c['estimated_peak_loading'],-c['distance_slots_from_center'],c['signature']))
        # Coverage across first-depart band and destination before score pruning.
        groups=defaultdict(list)
        for c in group:groups[str(c['diversity_key'][1:4])].append(c)
        diverse=sorted((a[0] for a in groups.values()),key=lambda c:(c['estimated_peak_loading'],c['signature']))
        single[u]=diverse[:24]
        # Two-MOVE distant paths use genuine original links and complete suffixes.
        for c in diverse[:8]:
            first=graph.move_indices(c['paths'][u])[0];ar=graph.arcs[first]
            for dest in list(dict.fromkeys([graph.origins[u]]+list(case.graph[0])))[:6]:
                for dep in (40,64,80):
                    k=graph.moves.get((ar[2],dest,dep))
                    if k is None or dep<ar[3] or k not in graph.available[u]:continue
                    paths=dict(stay);paths[u]=graph.complete(u,[first,k]);register(paths,'G'+str(i),[u],'TWO_MOVE_COMPLETE_DAG')
    for u,w in combinations(sorted(single),2):
        family='PAIR_'+u+'_'+w
        for a in single[u][:8]:
            for b in single[w][:8]:
                paths=dict(stay);paths[u]=a['paths'][u];paths[w]=b['paths'][w]
                register(paths,family,[u,w],'TWO_MESS_OTHER_TWO_STAY')
    for u in ('MESS01','MESS02','MESS04'):
        for a in single[u][:8]:
            paths={w:list(p) for w,p in base.items()};paths[u]=a['paths'][u]
            register(paths,'ADD_TO_PR220_'+u,[u,'MESS03'],'PR220_PLUS_ONE_SEPARATE_FAMILY')
    # Three-MESS candidates are generated, not required; evaluation depends on evidence/budget.
    for us in combinations(sorted(single),3):
        for ordinal in range(2):
            if any(len(single[u])<=ordinal for u in us):continue
            paths=dict(stay)
            for u in us:paths[u]=single[u][ordinal]['paths'][u]
            register(paths,'TRIPLE_'+'_'.join(us),list(us),'OPTIONAL_THREE_MESS')
    pool.sort(key=lambda c:(c['estimated_peak_loading'],-c['distance_slots_from_center'],c['signature']))
    required=['G1','G2','G3','G4']+['PAIR_'+u+'_'+w for u,w in combinations(sorted(single),2)]
    audit=dict(PASS=True,epoch=epoch,generated_counts=dict(counts),required_families=required,
        all_required_families_exist=all(counts[f]>0 for f in required),original_DAG_ETA_energy_terminal=True,
        existing_MESS03_route_not_required_for_solo_or_pairs=True,heuristic_ranking_not_exact_exclusion=True,
        full_route_space_exhausted=False,score_source='PR219 Minimax PCS/SOC/rebound heuristic',
        diversity_axes='moving units, first depart band, destinations, reconnect band, MOVE count, critical row, location-distance slots',
        scoring_center_vector=v.vector_sha(point))
    assert audit['all_required_families_exist']
    return pool,audit

def choose(pool,family,seen,used_keys):
    candidates=[c for c in pool if c['family']==family and c['signature'] not in seen]
    if not candidates:return None
    fresh=[c for c in candidates if str(c['diversity_key']) not in used_keys]
    return min(fresh or candidates,key=lambda c:(c['estimated_peak_loading'],-c['distance_slots_from_center'],c['signature']))
