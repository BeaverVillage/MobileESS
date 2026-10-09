import numpy as np
from types import SimpleNamespace as NS
from test_v42_b2_v19_feasibility_init import case
from v42_b2_seed_recovery_v19 import initialization as init
from v42_b2_seed_recovery_v19.fixed_pattern import discrete_stationary,integer_representatives

def represented_case():
    c=case();c.d['names']=np.append(c.d['names'],['route_flow[M1,1]'])
    c.d['types']=np.append(c.d['types'],['C']);return c

def test_stationary_fixes_continuous_c3a_route_representative_without_rounding_point():
    c=represented_case();ids,values=discrete_stationary(c)
    assert 6 in ids and values[list(ids).index(6)]==0.
    assert c.d['types'][6]=='C'
    low,high,_=init.pattern_bounds(c,np.zeros(7),np.ones(7),stationary=True,free_modes=range(96))
    assert low[6]==high[6]==0.

def test_f3_route_restriction_covers_original_routes_represented_continuously():
    c=represented_case();original=c.d['types'].copy()
    low,high,_=init.pattern_bounds(c,np.zeros(7),np.ones(7),sites=['S0'],free_modes=range(96))
    a,b,_=init.pattern_bounds(c,np.zeros(7),np.ones(7),sites=['S0','STA2'],free_modes=range(96))
    assert high[6]==0. and b[6]==1.
    assert np.array_equal(c.d['types'],original)
