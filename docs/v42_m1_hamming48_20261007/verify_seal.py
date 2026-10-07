"""Verify result provenance, saved points, unchanged history and byte manifest, no solves."""
from run_hamming48 import *
def main():
    manifest=read(OUT/'SHA256_MANIFEST.json')['files']
    actual={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    assert manifest==actual,'MANIFEST_FAILED'
    required='PREREGISTRATION.md BASE_IDENTITY.json CENTER_INCUMBENT_VALIDATION.json HAMMING24_AUTHORITY.json HAMMING48_MODEL_AUTHORITY.json SOLVER_PARAMETERS.json MIP_START_VALIDATION.json NATIVE_SOLVER.log INCUMBENT_TRACE.csv HAMMING48_RESULT.json BEST_CANDIDATE_FULL_REPLAY.json BEST_CANDIDATE_PHYSICAL_REPLAY.json BEST_CANDIDATE_GRID_REPLAY.json TRAJECTORY_DIFF.json CRITICAL_GRID_EFFECT.csv UB_COMPARISON.json GAP_UPDATE.json VERIFICATION.json FINAL_REVIEW_KO.md'.split()
    assert all((OUT/name).is_file() for name in required)
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    for name,digest in read(OLD/'SHA256_MANIFEST.json')['files'].items():assert sha(OLD/name)==digest,'PR169_MANIFEST_CHANGED'
    r=read(OUT/'HAMMING48_RESULT.json');assert r['optimize_calls']==read(OUT/'OPTIMIZE_ONCE.json')['optimize_calls']==1
    assert read(OUT/'VERIFICATION.json')['PASS']
    assert not r['callback_errors'] and r['solver_exception'] is None
    with (OUT/'INCUMBENT_TRACE.csv').open(encoding='utf-8',newline='') as f:trace=list(csv.DictReader(f))
    assert len(trace)==r['MIPSOL_events']
    for row in trace:assert sha(OUT/row['point'])==row['SHA256']
    A,d,_=hc.load()
    with np.load(OUT/'BEST_VALID_POINT.npz') as z:x=z['x'].copy()
    assert hc.replay(A,d,x,True)['PASS']
    assert float(d['objective']@x)==r['UB_new']
    assert sha(OUT/'BEST_VALID_POINT.npz')==r['best_valid_point_SHA256']
    assert read(OUT/'GAP_UPDATE.json')['LB_valid']==LB and read(OUT/'GAP_UPDATE.json')['neighborhood_ObjBound_used_as_global_LB'] is False
    assert read(OUT/'NEXT_EXPERIMENT_RECOMMENDATION.json')['count']==1 and not read(OUT/'NEXT_EXPERIMENT_RECOMMENDATION.json')['executed']
    changed=git('diff','--name-only',BASE,'HEAD').splitlines();assert all(p.startswith('docs/v42_m1_hamming48_20261007/') for p in changed)
    print('MANIFEST_RESULT_AND_HISTORY_PASS',len(actual),'files; optimize=1',flush=True)
if __name__=='__main__':main()
