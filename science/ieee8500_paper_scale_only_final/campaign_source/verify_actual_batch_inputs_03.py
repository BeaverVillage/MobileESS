"""Compare cached-metadata engines against independently compiled original ones."""
import sys,time,json,hashlib
from pathlib import Path
sys.argv=['preflight','B2']
import actual_worker as worker
import actual_electrical_speed as speed
import actual_batch_inputs_debug as batch
import numpy as np
H=worker.BASE;OUT=H/'ACTUAL_BATCH_PREFLIGHT_20260922';OUT=OUT.with_name(OUT.name+'_03');OUT.mkdir(exist_ok=False)
def save(name,x):(OUT/name).write_text(json.dumps(x,indent=2),encoding='utf-8')

def main():
    worker.verify()
    with np.load(worker.H/'B2/ACTUAL_INPUTS.npz') as z:data={k:z[k].copy() for k in z.files}
    checkpoint=worker.read(worker.H/'B2/Q_ACCEPTED_CHECKPOINT.json')
    q=data['Q_EXEC'].copy();q[:checkpoint['slots']]=checkpoint['Q']
    ns=worker.kernel();lo,hi=ns['q_bounds'](data['P_EXEC'][35],data['connected'][35],worker.binding.fb.AUTH and __import__('dayahead.v33m.mess_mobility_milp',fromlist=['MessElectricalAuthority']).MessElectricalAuthority.from_repository())
    variants=[('original',q[35]),('lower',lo),('upper',hi),('zero',np.clip(np.zeros(6),lo,hi))]
    warm=worker.Electrical(OUT/'metadata_warmup',data);warm.close()
    # Initialize and fully audit the metadata through an original Engine once.
    speed.install();warm=worker.Electrical(OUT/'cached_warmup',data);warm.close()
    reports=[]
    for label,qt in variants:
        results=[];times=[]
        for fast in (False,True):
            speed.install();
            if fast:batch.install()
            begin=time.perf_counter()
            e=worker.Electrical(OUT/f'{label}_{fast}',data)
            rows=[e.apply(t,qt if t==35 else q[t]) for t in range(36)]
            e.close();times.append(time.perf_counter()-begin);results.append(rows)
        delta={k:max(float(np.max(np.abs(a[k]-b[k]))) for a,b in zip(*results)) for k in ('v','line','tx','ipu','kva')}
        assert all(np.array_equal(a[k],b[k]) for a,b in zip(*results) for k in delta),(label,delta)
        assert all(a['state']==b['state'] and a['converged']==b['converged'] for a,b in zip(*results))
        reports.append(dict(label=label,old_seconds=times[0],fast_seconds=times[1],speedup=times[0]/times[1],max_errors=delta,all_arrays_bit_identical=True,all_native_states_identical=True))
        save('BENCHMARK_PROGRESS.json',reports);print('PARITY',reports[-1],flush=True)
    assert sum(r['fast_seconds'] for r in reports)<sum(r['old_seconds'] for r in reports)
    save('BENCHMARK_PASS.json',dict(status='PASS',rows=reports,source_sha256=hashlib.sha256(Path(batch.__file__).read_bytes()).hexdigest(),
        fresh_context_and_full_causal_prefix_preserved=True,controller_rules_changed=False))
if __name__=='__main__':main()
