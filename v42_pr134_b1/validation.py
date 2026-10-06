"""Pre-launch tests using original accepted PR134 data. No native solve."""
import unittest,tempfile,shutil,pickle,gzip
from unittest.mock import patch
from .common import *
from . import coordinator,worker

class InfrastructureTests(unittest.TestCase):
    def test_concurrent_atomic_writers_do_not_share_tempfile(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'state.json'
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda n:atomic(path,dict(generation=n,payload='x'*10000)),range(80)))
            self.assertIn(read(path)['generation'],range(80));self.assertFalse(list(Path(temp).glob('*.tmp')))
    def test_hourly_trigger_cannot_race_initial_launch(self):
        from . import detach
        from xml.etree import ElementTree as ET
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);atomic(root/'B1_PRODUCTION_FREEZE_MANIFEST.json',dict(Python='python.exe'))
            def fake_ps(script):
                if 'Export-ScheduledTask' in script:return (root/'watchdog_TASK.xml').read_text(encoding='utf16')
                if 'Get-ScheduledTask' in script:return '0'
                return 'S-1-5-21-test' if 'Value' in script else 'test-user'
            before=datetime.now()
            with patch.object(detach,'powershell',side_effect=fake_ps),patch.object(detach.subprocess,'run'):
                detach.register(root,'watchdog','test',True)
            definition=ET.parse(root/'watchdog_TASK.xml');ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
            start=datetime.fromisoformat(definition.find('.//t:StartBoundary',ns).text)
            self.assertGreater((start-before).total_seconds(),3590)
            self.assertTrue(all(n.text=='PT0S' for n in definition.findall('.//t:ExecutionTimeLimit',ns)))
    def test_physical_projection_never_prunes_valid_request(self):
        from .inputs import immutable_unmodelable
        capacities={'A':64};racks={'A':[64]}
        for gpu in [1,4,64]:self.assertTrue(immutable_unmodelable(dict(gpus_requested=gpu,partition='gpu-h100'),capacities,racks)['modelable'])
        for gpu in [None,float('nan'),0,-1,65,1.5]:self.assertFalse(immutable_unmodelable(dict(gpus_requested=gpu,partition='gpu-h100'),capacities,racks)['modelable'])
        self.assertFalse(immutable_unmodelable(dict(gpus_requested=4,partition='cpu'),capacities,racks)['modelable'])
    def test_atomic_identity_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'payload';p.write_bytes(b'original');expected=dict(day='2025-05-01')
            receipt=dict(PASS=True,identity=expected,files=[record(p)])
            self.assertTrue(valid_receipt(receipt,expected,root));p.write_bytes(b'changed');self.assertFalse(valid_receipt(receipt,expected,root))
    def test_pid_reuse_rejected(self):
        own=process();self.assertTrue(same_process(own));wrong=dict(own,created=own['created']+1);self.assertFalse(same_process(wrong))
    def test_verified_checkpoint_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze=dict(run_id='test');cp=coordinator.load_checkpoint(root,freeze);coordinator.save_checkpoint(root,cp);coordinator.save_checkpoint(root,cp)
            (root/'CHECKPOINT.json').write_bytes(b'{corrupt');restored=coordinator.load_checkpoint(root,freeze);self.assertEqual(restored['run_id'],'test')
            self.assertTrue(list(root.glob('CHECKPOINT_CORRUPT_*')))
    def test_live_orphan_checkpoint_adoption(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze=dict(run_id='test',Git_SHA='commit',scientific_SHA='science',day_input_SHA={DAYS[0]:'input'})
            attempt=root/'stages'/DAYS[0]/'A1'/'1';attempt.mkdir(parents=True);request=attempt/'request.json'
            atomic(request,dict(day=DAYS[0],stage='A1',identity=identity(freeze,DAYS[0],'A1'),dependencies={}))
            atomic(root/'ACTIVE.json',dict(request=str(request),day=DAYS[0],stage='A1',worker=process()))
            cp=coordinator.load_checkpoint(root,freeze);coordinator.recover_active_checkpoint(root,freeze,cp)
            self.assertEqual(cp['stages'][DAYS[0]+'/A1']['status'],'RUNNING');self.assertEqual(cp['stages'][DAYS[0]+'/A1']['request'],str(request))
    def test_corrupt_unverified_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'CHECKPOINT.json').write_text('bad');self.assertRaises(ValueError,coordinator.load_checkpoint,root,dict(run_id='test'))
    def test_timeout_isolated_and_not_infeasible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze=dict(run_id='test');cp=coordinator.load_checkpoint(root,freeze);day=DAYS[0];cp['stages'][day+'/A1']=dict(status='RUNNING')
            req=dict(result=str(root/'result.json'),error=str(root/'error.json'))
            atomic(req['error'],dict(type='ValueError',classification='TIMEOUT',error='DATE_TIMEOUT'))
            self.assertEqual(coordinator.result_or_error(root,freeze,cp,day,'A1',req,1),'FAIL')
            self.assertEqual(cp['dates'][day]['status'],'TIMEOUT');self.assertEqual(cp['dates'][DAYS[1]]['status'],'PENDING')
            self.assertEqual(classify('NATIVE_INFEASIBLE_NOT_INDEPENDENTLY_PROVEN'),'INCONCLUSIVE')
    def test_infrastructure_retry_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze=dict(run_id='test');cp=coordinator.load_checkpoint(root,freeze);day=DAYS[0];req=dict(result=str(root/'none'),error=str(root/'none2'))
            outcomes=[]
            for _ in range(3):
                cp['stages'][day+'/A1']=dict(status='RUNNING');outcomes.append(coordinator.result_or_error(root,freeze,cp,day,'A1',req,1))
            self.assertEqual(outcomes,['RETRY','RETRY','FAIL']);self.assertEqual(cp['dates'][day]['infra_retries'],2)
    def test_physical_validator_rejects_each_violation(self):
        summary=dict(convergence_count=96,voltage_violation_count=0,line_current_violation_count=0,transformer_current_violation_count=0,transformer_kva_violation_count=0)
        fresh=dict(converged=True,summary=summary,checker_SHA=CHECKER,all_MESS_PQ_zero=True,NormalAmps_current=True,Planning_tap_replay=False,Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0)
        self.assertTrue(worker.physical_validation(fresh))
        for key in summary:
            bad=dict(fresh,summary=dict(summary,**{key:95 if key=='convergence_count' else 1}));self.assertFalse(worker.physical_validation(bad))
    def test_original_date_ast_equivalence_on_may01(self):
        from .native import date_route
        import v42_boundary.model as boundary
        import v42_exact.validation as validation
        import ast,inspect
        for function in (boundary.planning_grid,validation.check):
            adapted=date_route(function)
            self.assertEqual(adapted.__name__,function.__name__)
            self.assertEqual(adapted.__code__.co_argcount,function.__code__.co_argcount)

def run_tests(root):
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(InfrastructureTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    value=dict(PASS=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),native_optimization_calls=0,
        scientific_inputs_changed=False,identity_and_payload_tamper_rejected=True,timeout_continues_next_date=True,bounded_retries=2)
    atomic(root/'INFRASTRUCTURE_REGRESSION.json',value)
    if not value['PASS']:raise ValueError('INFRASTRUCTURE_TEST_FAILURE')
    return value

def fixed_replay_canary(root):
    """PR134 accepted freeze tests fixed Actual/Fresh port, not a reused date."""
    from .native import bind
    from . import replay
    fixture=root/'FIXED_REPLAY_VALIDATION';fixture.mkdir(exist_ok=True)
    original=read(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json');assert original['PASS'] and original['accepted']
    bundle=read(root/'inputs/2025-05-01/NATIVE_INPUT.json');day=bundle['day'];a1=fixture/'A1';a1.mkdir(exist_ok=True)
    _,_,coeff,power,idle,swing=bind(bundle,root/'inputs'/day,a1)
    controls=original['anchor']['controls'];sites=sorted(bundle['capacities']);caps=np.array([bundle['capacities'][s] for s in sites])
    pcc=np.array([[controls[t][coeff[t].control_names.index('aidc_load_kw['+s+']')] for s in sites] for t in range(96)])
    slope=np.array([[power[s,t].slope for s in sites] for t in range(96)]);intercept=np.array([[power[s,t].intercept_kw for s in sites] for t in range(96)])
    it=(pcc-intercept)/slope;gpu=(it-idle*caps)/swing;q=pcc*np.tan(np.arccos(.95))
    np.savez_compressed(a1/'PLANNING_PHYSICAL.npz',sites=np.array(sites),PCC_P_kw=pcc,PCC_Q_kvar=q,IT_kw=it,GPU=gpu)
    atomic(a1/'A1_FREEZE.json',dict(PASS=True,accepted=True,arm='B1',day=day,selected_jobs=original['selected_jobs'],physical=original['physical'],
        receipt_role='PR134_ACCEPTED_POINT_OPERATIONS_TEST_ONLY',production_date_reused=False))
    f=dict(run_id='OPERATIONS_VALIDATION_ONLY',Git_SHA=BASE,scientific_SHA=BASE,day_input_SHA={day:sha(root/'inputs'/day/'NATIVE_INPUT.json')})
    plan=fixture/'PLANNING_FREEZE';actual=fixture/'ACTUAL';fresh=fixture/'FRESH_AC'
    for p in (plan,actual,fresh):p.mkdir(exist_ok=True)
    replay.freeze_planning(root,day,a1,plan,f);replay.actual(plan,identity(f,day,'PLANNING_FREEZE'),actual)
    result=replay.fresh(root,day,plan,actual,fresh,f,lambda v:atomic(fixture/'progress.json',v))
    fr=read(fresh/'FRESH_RESULT.json');passed=worker.physical_validation(fr)
    value=dict(PASS=passed,operations_port_native_optimization_calls=0,source_accepted_PR134_freeze=record(ROOT/'docs/v42_single_worker_single_thread_a1_m1/INTEGRATED_A1_FREEZE_SINGLE_THREAD.json'),
        fixed_Actual_reoptimization=0,PQ_repair=0,FreshAC=fr,production_date_reused=False,fixture_role='READ_ONLY_ACCEPTED_PR134_FIXED_REPLAY_VALIDATION')
    atomic(root/'OPERATIONS_PORT_VALIDATION.json',value)
    # A physical failure is evidence, not permission to modify power or limits.
    return value

if __name__=='__main__':
    import sys
    root=Path(sys.argv[1]);run_tests(root)
    if '--fresh' in sys.argv:fixed_replay_canary(root)
