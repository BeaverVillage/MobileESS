"""Read-only rehydration test of the exact previous B1 physics ranking."""
from fast_prepare import *
from v41r4_search_runtime import MAY_OUT,BASE_OUT,configure,prepare_ranking
from v41r4_search_worker import sync
import numpy as np

day='2025-05-04';sync(day);configure(day,'B1');prepare_ranking(day)
from dayahead.v41 import physics_ranking as ranking
r=ranking.INSTANCE
with np.load(BASE_OUT/day/'V41R3_RANKING_PHYSICS.npz') as z:
    for key,value in (('S',r.S),('active_S',r.AS),('active_rho',r.Arho),('B0_envelope',r.env),('weights',r.weight)):
        np.testing.assert_array_equal(z[key],value)
ranked,_=r.tier(sorted(r.jobs))
top=[r.describe(u,k,rank=i+1,P1_hat_active=p) for i,(u,k,p,e,l,g) in enumerate(ranked[:20])]
assert top==read(BASE_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json')['initial_priority_tier_top_20']
proof=read(MAY_OUT/day/'PREPARATION_REUSE_AUDIT.json')
source=MAY_OUT/day/'PREPARATION_REUSE_AUDIT.json'
target=MAY_OUT/'regression/PREPARATION_REUSE_BINDING_TEST.json'
assert source.resolve().is_relative_to(MAY_OUT) and target.resolve().is_relative_to(MAY_OUT)
source.rename(target)
save(MAY_OUT/'regression/CACHED_RANKING_EXACT_TEST.json',dict(status='PASS',day=day,
    all_S_and_active_arrays_bitwise_equal=True,top_20_rankings_exact=True,
    candidate_count=r.count,candidate_set_SHA=r.domain_digest.hexdigest(),
    source=record(ROOT/'v41r4_search_runtime.py'),optimizer_calls=0,Actual_reads=0,
    prior_ranking=record(BASE_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json'),reuse=proof))
print('CACHED_RANKING_BINDING_EXACT_PASS',flush=True)
