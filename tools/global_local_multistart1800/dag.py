"""Original DAG paths and forward/backward route closure, no invented arcs."""
from collections import defaultdict
import hashlib,json,numpy as np
from tools.global_local_multistart1800.adapter import *

class Graph:
    def __init__(self,case):
        self.case=case;self.arcs=case.graph[2];self.origins=case.graph[1]
        self.stay={(a[0],a[1]):k for k,a in enumerate(self.arcs) if a[-1] is None}
        self.moves={(a[0],a[2],a[1]):k for k,a in enumerate(self.arcs) if a[-1] is not None}
        names={str(n):j for j,n in enumerate(case.original_d['names'])}
        self.available={u:{k for k in range(len(self.arcs)) if (j:=names.get(f'arc[{u},{k}]')) is not None and case.original_d['upper'][j]>=1.} for u in self.origins}
        self.outgoing=defaultdict(list)
        for k,a in enumerate(self.arcs):self.outgoing[a[0],a[1]].append(k)
    def complete(self,u,moves):
        site,t=self.origins[u],0;path=[]
        for k in moves:
            a=self.arcs[k];assert a[-1] is not None and a[0]==site and t<=a[1]<a[3]<=96
            path.extend(self.stay[site,s] for s in range(t,a[1]));path.append(k);site,t=a[2:4]
        path.extend(self.stay[site,s] for s in range(t,96));assert set(path)<=self.available[u]
        return path
    def move_indices(self,path):return [k for k in path if self.arcs[k][-1] is not None]
    def validate(self,u,path):
        site,t=self.origins[u],0
        for k in path:
            a=self.arcs[k];assert k in self.available[u] and a[:2]==(site,t)
            if a[-1] is not None:a[-1].validate(96)
            site,t=a[2:4]
        assert t==96;return True
    def metadata(self,paths):
        moves=[dict(unit=u,arc=k,source=self.arcs[k][0],depart=self.arcs[k][1],destination=self.arcs[k][2],
            arrive=self.arcs[k][-1].arrive,connect=self.arcs[k][3],energy_kWh=self.arcs[k][-1].energy_kwh)
            for u,p in paths.items() for k in self.move_indices(p)]
        return dict(moves=len(moves),travel_energy_kWh=sum(float(a['energy_kWh']) for a in moves),actual_moves=moves)
    def candidate(self,paths,label):
        for u,p in paths.items():self.validate(u,p)
        return dict(candidate_id=label,paths=paths,score=0.,**self.metadata(paths))
    def ablations(self,base,priority_sites):
        unit='MESS03';moves=self.move_indices(base[unit]);assert moves==[4954,40511,47108]
        candidates=[];skips=[]
        def add(label,newmoves,extra=None):
            try:
                paths={u:list(p) for u,p in base.items()};paths[unit]=self.complete(unit,newmoves)
                if extra:
                    u,k=extra;paths[u]=self.complete(u,[k])
                assert paths!=base;c=self.candidate(paths,label)
                if not any(c['paths']==x['paths'] for x in candidates):candidates.append(c)
            except (AssertionError,KeyError,ValueError) as e:skips.append(dict(label=label,reason=repr(e)))
        add('A1_FIRST_MOVE_ONLY',[moves[0]]);add('A2_FIRST_TWO_MOVES',moves[:2])
        for depart in (2,6,0,8):
            k=self.moves.get(('STA08','IDC06',depart))
            if k is not None and self.arcs[k][3]<=69:
                add('A3_FIRST_DEPARTURE_CHANGED',[k,*moves[1:]])
                if any(c['candidate_id'].startswith('A3') for c in candidates):break
        for site in priority_sites[unit]+['IDC05','IDC01','IDC03']:
            if site in ('STA08','IDC06'):continue
            a=self.moves.get(('STA08',site,4));b=self.moves.get((site,'IDC05',69))
            if a is not None and b is not None and self.arcs[b][3]<=81:
                add('A4_FIRST_DESTINATION_RECONNECTED',[a,b,moves[2]])
                if any(c['candidate_id'].startswith('A4') for c in candidates):break
        for depart in (65,67,71,73):
            k=self.moves.get(('IDC06','IDC05',depart))
            if k is not None and self.arcs[k][3]<=81:
                add('A5_SECOND_MOVE_RETIMED',[moves[0],k,moves[2]])
                if any(c['candidate_id'].startswith('A5') for c in candidates):break
        for u in sorted(self.origins):
            if u==unit:continue
            for site in priority_sites[u]:
                k=self.moves.get((self.origins[u],site,4))
                if k is not None:
                    add('A6_FIRST_MOVE_PLUS_'+u,[moves[0]],(u,k))
                    if any(c['candidate_id'].startswith('A6') for c in candidates):break
            if any(c['candidate_id'].startswith('A6') for c in candidates):break
        return candidates,skips
    def closure(self,u,path,start,stop,sites,terminal_any=False,extra_paths=()):
        # Cut only at actual center vertices, never inside a transit interval.
        vertices=[self.arcs[k][:2] for k in path]+[(self.arcs[path[-1]][2],96)]
        source=next(v for v in vertices if v[1]>=start);end=next(v for v in vertices if v[1]>=stop)
        start,stop=source[1],end[1];sites=set(sites)|{source[0],end[0]}
        inner={k for k in self.available[u] if start<=self.arcs[k][1]<self.arcs[k][3]<=stop and self.arcs[k][0] in sites and self.arcs[k][2] in sites}
        for k in path:
            if start<=self.arcs[k][1] and self.arcs[k][3]<=stop:inner.add(k)
        for p in extra_paths:
            for k in p:
                a=self.arcs[k]
                if start<=a[1] and a[3]<=stop and k in self.available[u]:inner.add(k)
        forward={source}
        for t in range(start,stop):
            for s in sorted({s for s,when in forward if when==t}):
                for k in self.outgoing[s,t]:
                    if k in inner:forward.add(self.arcs[k][2:4])
        ends={v for v in forward if v[1]==stop} if terminal_any else {end}
        reverse=set(ends)
        for t in range(stop-1,start-1,-1):
            for k in inner:
                a=self.arcs[k]
                if a[1]==t and a[2:4] in reverse:reverse.add(a[:2])
        kept={k for k in inner if self.arcs[k][:2] in forward and self.arcs[k][2:4] in reverse}
        assert source in reverse and end in forward
        outer=[k for k in path if self.arcs[k][1]<start or self.arcs[k][1]>=stop]
        allowed=kept|set(outer);assert set(path)<=allowed
        # Shortest distinct original arc path is an openness witness; it
        # proves topology/ETA/domain only, not alternate SOC/Grid feasibility.
        states={(source[0],start,False,False):(0.,())};center=set(path)
        for t in range(start,stop):
            active=[(s,d,m,c,p) for (s,when,d,m),(c,p) in list(states.items()) if when==t]
            for site,different,moving,cost,prefix in active:
                for k in self.outgoing[site,t]:
                    if k not in kept:continue
                    a=self.arcs[k];key=(a[2],a[3],different or k not in center,moving or a[-1] is not None)
                    value=(cost+(float(a[-1].energy_kwh) if a[-1] else 0.)+.001,prefix+(k,))
                    if key not in states or value[0]<states[key][0]:states[key]=value
        outer_moves=any(self.arcs[k][-1] is not None for k in outer)
        alternatives=sorted((cost,p) for (s,t,d,m),(cost,p) in states.items() if t==stop and d and (m or outer_moves) and (s,t) in ends)
        assert alternatives,'NO_DIFFERENT_ROUTE_WITNESS'
        prefix=[k for k in path if self.arcs[k][1]<start];suffix=[k for k in path if self.arcs[k][1]>=stop]
        witness=prefix+list(alternatives[0][1])+suffix;self.validate(u,witness)
        return dict(unit=u,start=start,stop=stop,sites=sorted(sites),terminal_any=terminal_any,
            allowed_arcs=sorted(allowed),inner_arcs=sorted(kept),outer_fixed_arcs=outer,witness=witness,
            forward_vertices=len(forward),backward_vertices=len(reverse),dangling_arcs_removed=len(inner-kept),
            site_and_window_restriction_is_heuristic=True,forward_backward_exclusion_exact_within_selected_corridor=True)
