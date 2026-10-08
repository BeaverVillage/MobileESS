import itertools
from v42_a_stage_primal.mincost import transport

def test_integer_transport_finds_three_cycle_and_matches_exhaustive_assignment():
    # No pair swap is supported, but a three-class cycle is feasible and better.
    edges={('a',0):(1,4),('a',1):(1,3),('b',1):(1,4),('b',2):(1,3),('c',2):(1,4),('c',0):(1,4)}
    flow,cost=transport(dict(a=1,b=1,c=1),{0:1,1:1,2:1},edges)
    feasible=[]
    for p in itertools.permutations(range(3)):
        if all((c,t) in edges for c,t in zip(('a','b','c'),p)):feasible.append(sum(edges[c,t][1] for c,t in zip(('a','b','c'),p)))
    assert cost==min(feasible)==10
    assert flow['a',1]==flow['b',2]==flow['c',0]==1

def test_integer_transport_respects_histogram_mass_and_edge_bounds():
    edges={('a',0):(1,0),('a',1):(3,2),('b',0):(2,1),('b',1):(2,0)}
    flow,cost=transport({'a':3,'b':2},{0:3,1:2},edges)
    assert flow=={('a',0):1,('a',1):2,('b',0):2,('b',1):0} and cost==6
