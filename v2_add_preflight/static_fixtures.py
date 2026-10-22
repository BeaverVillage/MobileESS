"""May01-only orchestration/admission fault injection; no scientific solver."""
import io,unittest,tempfile
from unittest.mock import patch
from .static_common import *

def run():
    init();tests=[]
    from . import prestart_verify as prior
    prior.RUN=RUN/'fixtures';prior.RUN.mkdir(exist_ok=True)
    names=['test_bad_golden_cache_reaches_actual_acceptance_and_is_rejected',
        'test_reference_full_job_domain_and_joint_resource_validation',
        'test_a1_reuse_binds_every_case_and_acceptance_field',
        'test_checkpoint_detects_mutated_artifact_and_source',
        'test_duplicate_lock_is_denied_without_stale_pid_bypass',
        'test_generic_pass_cannot_authorize_full_stage_or_prefix']
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite(prior.PrestartTests(n) for n in names))
    tests.append(dict(name='Original FULL acceptance/reuse/checkpoint/duplicate-worker rejection',PASS=result.wasSuccessful(),
        tests=result.testsRun,output=stream.getvalue(),scientific_FULL_claim=False))
    from .prestart_execution import Scheduler
    from v44.stages import CHAINS
    with tempfile.TemporaryDirectory(dir=prior.RUN) as temp:
        calls=[]
        def handler(r):
            i=r['identity'];calls.append((i['arm'],i['stage']))
            if i['arm']=='B1':raise ValueError('ISOLATED_STAGE_FAILURE')
            return dict(PASS=True,Native_seconds=0,artifacts=[])
        handlers={s:handler for chain in CHAINS.values() for s in chain}
        s=Scheduler(temp,handlers,{'2025-05-01':{'input':'same-May01-fixture'}},{k:10 for k in handlers},diagnostic_fixture=True)
        first=s.case('2025-05-01','B0');n=len(calls);again=s.case('2025-05-01','B0')
        same=n==len(calls)
        failure=s.case('2025-05-01','B1')
        tests.append(dict(name='May01 successful checkpoint resumes without reexecution; B1 failure leaves B0 intact',
            PASS=first['status']=='COMPLETE' and again['status']=='COMPLETE' and same and failure['status']=='FAILED',fixture=True))
    from . import static_execution as e
    try:e.campaign('NONEXISTENT_PERMIT')
    except PermissionError as exc:tests.append(dict(name='HOLD before approval IO',PASS=str(exc)=='PRESTART_BLOCKED_WITH_EVIDENCE'))
    else:tests.append(dict(name='HOLD before approval IO',PASS=False))
    with patch.object(e.Path,'exists',return_value=True),patch.object(e,'read',return_value={'status':'READY_FOR_MAY01_CAMPAIGN_APPROVAL'}):
        try:e.campaign('FORGED_READY')
        except PermissionError as exc:tests.append(dict(name='Forged readiness cannot launch unbound source worker',PASS='CERTIFIED_CURRENT_CASE_STAGE_HANDLERS' in str(exc)))
        else:tests.append(dict(name='Forged readiness cannot launch unbound source worker',PASS=False))
    for day in ('2025-05-02','2025-05-07'):
        try:e.request(day,'B0')
        except PermissionError:tests.append(dict(name='Reject non-May01 '+day,PASS=True))
        else:tests.append(dict(name='Reject non-May01 '+day,PASS=False))
    return put('ORIGINAL_STAGE_AND_CHECKPOINT_FIXTURES.json',dict(PASS=all(t['PASS'] for t in tests),checks=tests,
        Native_calls=0,Actual_or_Fresh_scientific_runs=0,case_interface_and_FULL_Native0_certified=False))

if __name__=='__main__':run()
