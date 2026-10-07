"""Read-only original integrality audit; LP points are not production UB."""
from common import *
from collections import defaultdict

def main():
    A,d,_=load()
    with np.load(OUT/'MULTIWINDOW_STRENGTHENED_LP_PRIMAL.npz') as z:x=z['x'][:A.shape[1]]
    groups=defaultdict(list)
    for name,typ,v in zip(d['names'],d['types'],x):
        if typ=='B':groups[str(name).split('[',1)[0]].append(float(v))
    rows=[]
    for family,values in groups.items():
        v=np.array(values);rows.append(dict(family=family,original_binaries=len(v),fractional_at_PR167_1e_minus6_threshold=int(np.count_nonzero((v>1e-6)&(v<1-1e-6))),maximum_original_integrality_violation=float(abs(v-np.rint(v)).max())))
    raw=replay(A,d,x,True)
    write('MULTIWINDOW_ORIGINAL_INTEGRALITY_AUDIT.json',dict(optimize_calls=0,source_point_SHA256=sha(OUT/'MULTIWINDOW_STRENGTHENED_LP_PRIMAL.npz'),original_integrality_replay=raw,rows=rows,not_promoted_to_production_UB=True,fractionality_count_is_point_and_algorithm_dependent_not_a_gap_certificate=True,original_PR167_census_preserved=True))
    print('MULTIWINDOW_ORIGINAL_INTEGRALITY',rows,raw,flush=True)
    assert not raw['PASS'], 'ALL_ORIGINAL_INTEGRAL_CANDIDATE_REQUIRES_FULL_PHYSICAL_REPLAY_BEFORE_FINALIZATION'

if __name__=='__main__':main()
