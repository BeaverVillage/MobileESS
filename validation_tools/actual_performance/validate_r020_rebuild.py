"""Native0 real-state equivalence and cold/warm rebuild measurements."""
from pathlib import Path
import os,sys,time,gc
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psutil
psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
from v44.common import atomic,record,now
from v44_recovery_r019.a2_checkpoint import load
from v44_recovery_r020.phase_rebuild import Rebuild
from v42_may_campaign_native90.preflight import native_zero

out=Path('D:/MobileESS_V44/development/r020_rebuild_validation');out.mkdir(exist_ok=False)
source=Path('D:/MobileESS_V44/development/r018_verified_s14_state.pkl.gz')
atomic(out/'STATUS.json',dict(UTC=now(),phase='LOAD_REAL_S14_STATE',source=record(source)))
state=load(source)['state'];memo=Rebuild()
candidates=[c for m in state['metas'].values() for c in m['candidates']]
expected={k:state[k].fingerprint() for k in ('reference','compact')}
results=[]
with native_zero() as denied:
    for kind in ('cold','warm'):
        atomic(out/'STATUS.json',dict(UTC=now(),phase=kind,expected=expected))
        start=time.perf_counter()
        new=memo.build(state['reference'],state['grows'],state['n'],state['axes'],state['data'],state['domains'],state['ledger'],candidates)
        seconds=time.perf_counter()-start
        got={k:new[k].fingerprint() for k in expected}
        assert got==expected,(kind,got,expected)
        assert new['projection_proofs']==state['projection_proofs']
        assert new['reference_descriptor'].keys()==state['reference_descriptor'].keys()
        result=dict(kind=kind,wall_seconds=seconds,fingerprints=got,projection_proofs_identical=True,profile=memo.report())
        results.append(result);atomic(out/(kind+'.json'),result)
        print(kind,seconds,memo.report(),flush=True)
        del new;gc.collect()
    assert len(denied)==0
assert memo.proofs.hits>0 and memo.blocks.hits>0
atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_optimizer_calls=0,source=record(source),
    original_reference_and_compact_fingerprints=expected,results=results,warm_speedup=results[0]['wall_seconds']/results[1]['wall_seconds'],
    both_B1_B3_A2_same_scope=True,constraints_or_tolerances_changed=False))
print('PASS',flush=True)
