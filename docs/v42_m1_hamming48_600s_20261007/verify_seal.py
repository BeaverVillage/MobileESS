"""Independent point/historical bytes/result/manifest checks; no optimization."""
from run_hamming48 import *
def main():
    actual={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    assert read(OUT/'SHA256_MANIFEST.json')['files']==actual,'MANIFEST_FAILED'
    required='PREREGISTRATION.md CENTER_VALIDATION.json SOLVER_PARAMETERS.json NATIVE_SOLVER.log INCUMBENT_TRACE.csv RESULT.json BEST_FULL_REPLAY.json GAP_UPDATE.json FINAL_REVIEW_KO.md'.split()
    assert all((OUT/name).is_file() for name in required)
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    for folder in (OLD,PREVIOUS):
        for name,digest in read(folder/'SHA256_MANIFEST.json')['files'].items():assert sha(folder/name)==digest,'HISTORICAL_MANIFEST_CHANGED'
    r=read(OUT/'RESULT.json');assert r['optimize_calls']==read(OUT/'OPTIMIZE_ONCE.json')['optimize_calls']==1
    assert read(OUT/'VERIFICATION.json')['PASS'] and not r['callback_errors'] and r['solver_exception'] is None
    assert read(OUT/'SOLVER_PARAMETERS.json')['settings']==SETTINGS
    assert set(read(OUT/'SOLVER_PARAMETERS.json')['PR170_effective_differences'])=={'TimeLimit','LogFile'}
    with (OUT/'INCUMBENT_TRACE.csv').open(encoding='utf-8',newline='') as f:trace=list(csv.DictReader(f))
    assert len(trace)==r['MIPSOL_events']
    for row in trace:assert sha(OUT/row['point'])==row['SHA256']
    A,d,_=hc.load()
    with np.load(OUT/'BEST_VALID_POINT.npz') as z:x=z['x'].copy()
    assert hc.replay(A,d,x,True)['PASS'] and hc.physical_reader().check(x,A,d)['PASS']
    assert float(d['objective']@x)==r['UB_new'] and sha(OUT/'BEST_VALID_POINT.npz')==r['best_valid_point_SHA256']
    with np.load(PREVIOUS/'BEST_VALID_POINT.npz') as z:center=z['x'].copy()
    with np.load(OUT/'NEIGHBORHOOD_RESTRICTION.npz') as z:free=z['free'];fixed=z['fixed']
    with np.load(PREVIOUS/'NEIGHBORHOOD_RESTRICTION.npz') as z:assert np.array_equal(free,z['free']) and np.array_equal(fixed,z['fixed'])
    assert np.array_equal(x[fixed],center[fixed]) and np.count_nonzero((x[free]>.5)!=(center[free]>.5))==r['H_best']<=48
    g=read(OUT/'GAP_UPDATE.json');assert g['LB_valid']==LB and not g['neighborhood_ObjBound_used_as_global_LB']
    assert g['absolute_improvement']==UB-r['UB_new'] and g['relative_UB_improvement']==(UB-r['UB_new'])/UB and g['gap_new']==(r['UB_new']-LB)/r['UB_new']
    classification='HAMMING48_600_PRIMAL_IMPROVEMENT_CONFIRMED' if g['absolute_improvement']>=.001 else 'HAMMING48_600_MINOR_IMPROVEMENT' if g['absolute_improvement']>0 else 'HAMMING48_600_NO_VALID_IMPROVEMENT'
    assert r['classification']==classification
    next_action=read(OUT/'NEXT_ACTION_RECOMMENDATION.json');assert next_action['count']==1 and next_action['executed'] is False
    assert all(p.startswith('docs/v42_m1_hamming48_600s_20261007/') for p in git('diff','--name-only',BASE,'HEAD').splitlines())
    print('MANIFEST_FULL_REPLAY_HISTORY_AND_SINGLE_CALL_PASS',len(actual),flush=True)
if __name__=='__main__':main()
