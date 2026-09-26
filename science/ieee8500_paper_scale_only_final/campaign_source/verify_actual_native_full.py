"""Independent 96-slot original/native parity and existing memo compatibility."""
import sys, time, json, hashlib
from pathlib import Path
sys.argv=['preflight','B2']
import actual_worker as w
import actual_electrical_speed as speed
import actual_native_inputs as native
import numpy as np
OUT=w.BASE/'ACTUAL_NATIVE_PREFLIGHT_20260922'
with np.load(w.H/'B2/ACTUAL_INPUTS.npz') as z:data={k:z[k].copy() for k in z.files}
q=data['Q_EXEC'].copy()
results=[];timings=[]
for fast in (False,True):
    speed.install(False)
    if fast:native.install()
    start=time.perf_counter();e=w.Electrical(OUT/f'full_{fast}',data)
    build=time.perf_counter()-start;rows=[];st=time.perf_counter()
    for t in range(96):rows.append(e.apply(t,q[t]))
    e.close();results.append(rows);timings.append(dict(native=fast,build_s=build,replay_s=time.perf_counter()-st))
    print('FULL',timings[-1],flush=True)
keys=('v','line','tx','ipu','kva')
assert all(np.array_equal(a[k],b[k]) for a,b in zip(*results) for k in keys)
assert all(a['state']==b['state'] and a['converged']==b['converged'] for a,b in zip(*results))
progress=w.read(w.H/'B2/Q_EVALUATION_PROGRESS.json')
key=hashlib.sha256(speed.electrical_key(data,35,q[35])).hexdigest()
cache=w.H/'B2/EXACT_STATE_CACHE/slot_35'/progress['prefix_sha'][:16]
meta=w.read(cache/(key[:24]+'.json'));p=cache/(key[:24]+'.npz')
assert meta['full_key']==key and meta['arrays_sha256']==w.sha(p)
with np.load(p) as z:
    assert all(np.array_equal(z[k],results[1][35][k]) for k in keys)
assert meta['nonarrays']['state']==results[1][35]['state']
(OUT/'FULL_PARITY_PASS.json').write_text(json.dumps(dict(status='PASS',slots=96,all_arrays_bit_identical=True,
    all_native_states_identical=True,existing_memo_bit_identical=True,timings=timings,
    memo_prefix_sha=progress['prefix_sha'],source=w.rec(Path(native.__file__)),
    original_q_controller_and_search_unchanged=True,original_final_independent_engine=True),indent=2),encoding='utf-8')
print('FULL_PARITY_AND_EXISTING_MEMO_PASS',flush=True)
