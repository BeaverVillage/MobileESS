"""Validated native-loop implementation for resumed B2 and fresh B3 Actual."""
import sys, traceback
from pathlib import Path
import actual_worker as worker
import actual_electrical_speed as speed
import actual_native_inputs as native

def gate():
    root=worker.BASE/'ACTUAL_NATIVE_PREFLIGHT_20260922'
    b=worker.read(root/'BENCHMARK_PASS.json')
    p=worker.read(root/'FULL_PARITY_PASS.json')
    assert b['status']==p['status']=='PASS'
    assert b['source_sha256']==p['source']['sha256']==worker.sha(Path(native.__file__))
    assert p['slots']==96 and p['all_arrays_bit_identical'] and p['existing_memo_bit_identical']
    authority=worker.read(worker.BASE/'ACTUAL_NATIVE_RESUME_AUTHORITY.json')
    for r in authority['implementation_files']:assert worker.sha(r['path'])==r['sha256']
    speed.install=native.install

def record():
    worker.save(worker.H/'NATIVE_RUNTIME_BINDING.json',dict(status='PASS',
        entry=worker.rec(Path(__file__)),native=worker.rec(Path(native.__file__)),
        parity=worker.rec(worker.BASE/'ACTUAL_NATIVE_PREFLIGHT_20260922/FULL_PARITY_PASS.json'),
        cache_identity='Original exact state namespace retained under bit-identical implementation proof',
        call_order_and_checks_preserved=True,fastmath=False,solver_state_reuse=False,
        original_final_96_slot_verification=True))

def main():
    gate()
    if worker.H.exists():
        assert worker.POLICY=='B2'
        record()
        import actual_resume_fast
        actual_resume_fast.main()
    else:
        import actual_fresh_fast
        def run(*args):
            record()
            return actual_fresh_fast.run(*args)
        worker.run_policy=run
        worker.main()

if __name__=='__main__':
    try:main()
    except BaseException as e:
        worker.H.mkdir(exist_ok=True)
        worker.save(worker.H/'FAILURE_NATIVE.json',dict(error=repr(e),traceback=traceback.format_exc()))
        raise
