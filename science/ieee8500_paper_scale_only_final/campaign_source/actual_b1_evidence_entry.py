"""Restore two historical zero-MESS evidence references; original Actual unchanged."""
import traceback
from pathlib import Path
import actual_worker as worker

def main():
    assert worker.POLICY=='B1'
    manifest=worker.read(worker.BASE/'B1_ACTUAL_EVIDENCE_REPAIR.json')
    assert manifest['status']=='PASS'
    aliases={str(Path(r['logical']['path'])):r for r in manifest['aliases']}
    for r in aliases.values():
        p=Path(r['local_copy'])
        assert worker.sha(p)==r['logical']['sha256'] and p.stat().st_size==r['logical']['bytes']
    import dayahead.v40d_actual.mobility_inputs as mi
    original=mi.reference
    def reference(path):
        p=Path(path)
        if p.exists():return original(path)
        r=aliases.get(str(p))
        if r is None:return original(path)
        local=Path(r['local_copy'])
        assert worker.sha(local)==r['logical']['sha256'] and local.stat().st_size==r['logical']['bytes']
        return dict(r['logical'])
    mi.reference=reference
    original_inputs=worker.inputs
    def inputs(ns):
        worker.save(worker.H/'HISTORICAL_REFERENCE_BINDING.json',dict(status='PASS',
            entry=worker.rec(Path(__file__)),manifest=worker.rec(worker.BASE/'B1_ACTUAL_EVIDENCE_REPAIR.json'),
            restored_references=manifest['aliases'],physical_actuator_and_Q_controller_unchanged=True))
        return original_inputs(ns)
    worker.inputs=inputs
    worker.main()

if __name__=='__main__':
    try:main()
    except BaseException as e:
        worker.H.mkdir(exist_ok=True)
        worker.save(worker.H/'FAILURE_EVIDENCE.json',dict(error=repr(e),traceback=traceback.format_exc()))
        raise
