"""Fixed-budget diverse original DAG admission with immutable incumbent pins."""
from collections import defaultdict
from types import SimpleNamespace

import pytest

from v42_integration.mess_beam_diversity import diversify_pool, optimistic_path_possible
from v42_native.mess import RouteArc


class Graph:
    def __init__(self):
        self.horizon = 96
        self.origins = {f"MESS{i:02d}":"A" for i in range(1,5)}
        self.arcs = [(s,t,s,t+1,None) for s in ("A","B","C") for t in range(96)]
        self.moves = {}
        for origin,destination in (("A","B"),("A","C"),("B","C"),("C","A")):
            for tick in (12,24,48,72):
                route = RouteArc(f"{origin}{destination}{tick}", origin, destination,
                    tick,tick+2,tick+2,1.,"1"*64)
                self.moves[origin,destination,tick] = len(self.arcs)
                self.arcs.append((origin,tick,destination,tick+2,route))
        self.stay = {(a[0],a[1]):k for k,a in enumerate(self.arcs) if a[-1] is None}
        self.available = {u:set(range(len(self.arcs))) for u in self.origins}
    def validate(self, unit, path):
        site,tick = self.origins[unit],0
        for k in path:
            if k not in self.available[unit] or self.arcs[k][:2] != (site,tick):
                raise ValueError("ORIGINAL_DAG")
            site,tick = self.arcs[k][2:4]
        if tick != 96:
            raise ValueError("FULL96")
    def complete(self,unit,moves=()):
        site,tick,path = self.origins[unit],0,[]
        for k in moves:
            a=self.arcs[k]
            if a[0] != site or a[1] < tick:
                raise ValueError("ORIGINAL_DAG")
            path.extend(self.stay[site,t] for t in range(tick,a[1]));path.append(k)
            site,tick=a[2:4]
        path.extend(self.stay[site,t] for t in range(tick,96))
        self.validate(unit,path)
        return path


def fixture():
    graph=Graph()
    battery=SimpleNamespace(initial=10.,minimum=1.,maximum=20.,terminal=10.,
        dt_hours=.25,eta_charge=.95,p_limit=2.)
    baseline={u:graph.complete(u) for u in graph.origins}
    protected={u:[graph.complete(u,[graph.moves["A","B",12],graph.moves["B","C",24]])] for u in graph.origins}
    pools={u:[baseline[u],protected[u][0],graph.complete(u,[graph.moves["A","B",48]])] for u in graph.origins}
    def signed_joint_peak(paths):
        # Coupled signed contributions on two phases. Sending all vehicles to
        # the same useful site can rebound on the OTHER phase.
        loading=[.9,.8]
        for path in paths.values():
            final=graph.arcs[path[-1]][2]
            contribution={"A":(0.,0.),"B":(-.04,.02),"C":(.01,-.03)}[final]
            loading=[a+b for a,b in zip(loading,contribution)]
        return max(loading)
    return graph,battery,baseline,protected,pools,signed_joint_peak


def test_all_four_diverse_fixed_size_and_stay_moving_incumbents_preserved():
    args=fixture()
    pools,receipt=diversify_pool(*args,size=8)
    graph,battery,baseline,protected,original,score=args
    assert set(pools)==set(graph.origins)
    for unit,paths in pools.items():
        assert len(paths)==8 and len({tuple(p) for p in paths})==8
        assert baseline[unit] in paths and protected[unit][0] in paths
        for path in paths:
            graph.validate(unit,path)
        assert set(receipt["units"][unit]["generated_destinations"])=={"B","C"}
        assert receipt["units"][unit]["generated_departure_bands"]==[1,2,4,6]
        assert 1 in receipt["units"][unit]["selected_move_classes"]
        assert 2 in receipt["units"][unit]["selected_move_classes"]
    assert receipt["incumbent_registry_mutations"]==0
    assert receipt["Native_optimize_calls"]==0
    assert receipt["FULL_UB"] is False and receipt["Global_LB"] is False


def test_deterministic_same_budget_and_cannot_drop_many_protected_paths():
    args=fixture()
    a,receipt=diversify_pool(*args,size=6)
    b,again=diversify_pool(*args,size=6)
    assert a==b and receipt["pool_sha"]==again["pool_sha"]
    graph,battery,baseline,protected,pools,score=args
    unit="MESS01"
    protected[unit]=[graph.complete(unit,[graph.moves["A","B",t]]) for t in (12,24,48,72)]
    with pytest.raises(ValueError,match="CANNOT_DROP_VERIFIED_INCUMBENTS"):
        diversify_pool(graph,battery,baseline,protected,pools,score,size=3)


def test_optimistic_energy_rejection_does_not_claim_grid_or_soc_dispatch_feasibility():
    graph,battery,baseline,protected,pools,score=fixture()
    route=graph.arcs[graph.moves["A","B",12]][-1]
    battery.initial=battery.maximum=battery.terminal=1.
    battery.minimum=.5; battery.p_limit=0.
    assert not optimistic_path_possible(graph,battery,graph.complete("MESS01",[graph.moves["A","B",12]]))
