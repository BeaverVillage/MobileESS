"""Execute the formerly escaping route in DEV under real locks and Native0."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r041 import operations as op
from v44.common import read,record,atomic,now
from v44.locks import coordinator

def run():
    from v42_may_campaign_native90.preflight import native_zero
    out=Path('D:/MobileESS_V44/development/R041_REUSED_A1_NATIVE0_20261019');out.mkdir(exist_ok=False)
    old=read(op.OPS/'requests/2025-05-07_B1_attempt002.json')
    with coordinator(out) as lease:
        atomic(out/'PHASE.json',dict(lane='MAIN'))
        request=op.attach(old);request.update(case_root=str(out/'CASE'),campaign_root=str(out),lease=lease,r038_phase='PREPARE_SERIAL',
            wall_resume_parent=str(op.CAMPAIGN/'2025-05-07/B1/attempt001'))
        pointer=out/'request.json';atomic(pointer,request)
        with native_zero() as denied:
            result=op.worker(pointer)
            assert result['preparation_PASS'] is True and not denied
        assert not (out/'CASE/ACTUAL').exists()
        assert read(out/'CASE/progress.json')['stage']=='PRE_ACTUAL_READY'
        assert (out/'B1_A1/2025-05-07.json').exists() and (out/'B1_A1/2025-05-07.request.json').exists()
        atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,real_worker_and_coordinator_scope=True,Native_optimizer_calls=0,
            full_completed_A1_parent_verified=True,Actual_directory_created=False,Actual_executed=False,
            B1_reference_and_B3_cache_proof_published=True,handoff=result['pre_actual_handoff'],source=record(__file__)))
    print(dict(PASS=True,Actual_executed=False,Native_optimizer_calls=0))

if __name__=='__main__':run()
