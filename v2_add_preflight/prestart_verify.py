"""Meaningful rejection/continuity/physical-witness tests; no optimizer calls."""
import csv,json,tempfile,unittest
from pathlib import Path
import numpy as np
from .prestart import ROOT,DOC,OUT,RUN,read,put,record,digest,INITIAL
from .prestart_acceptance import source_domain,certify,accept,AcceptanceError,execute_a_stage
from .prestart_execution import Scheduler,owned_lock,require_reuse,binding,atomic,require_campaign,validate_stage_result

class PrestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
        cls.native=read(day['files']['native']['path']);cls.windows=read(day['files']['windows']['path'])
        cls.identity=binding(day['day'],'input','scenario','source','acceptance')

    def test_bad_golden_cache_reaches_actual_acceptance_and_is_rejected(self):
        point=read(DOC/'source/aidc_pilot/PLANNING_REFERENCE.json')['selected_jobs']
        called=[]
        def original_stage():called.append(True);return dict(selected_jobs=point)
        with self.assertRaises(AcceptanceError) as caught:
            execute_a_stage(original_stage,bundle=self.native,windows=self.windows,identity=self.identity,
                expected_identity=self.identity,grid_validator=lambda x:dict(PASS=True,identity=self.identity))
        self.assertTrue(called)
        self.assertEqual(sum(v['reason']=='START_WINDOW' for v in caught.exception.certificate['violations']),414)

    def test_reference_full_job_domain_and_joint_resource_validation(self):
        from v42_job_capability import Option
        from dataclasses import asdict
        jobs,b,secs,r,raw=source_domain(self.native,self.windows)
        point={u:asdict(Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),))) for u,j in jobs.items()}
        c=certify(point,self.native,self.windows,identity=self.identity,expected_identity=self.identity)
        self.assertTrue(c['PASS'],c['violations'][:5])
        # Native reference alone does not supply a global LB or grid acceptance.
        with self.assertRaises(AcceptanceError):accept(dict(selected_jobs=point),self.native,self.windows,
            identity=self.identity,expected_identity=self.identity,grid_certificate=dict(PASS=True,identity=self.identity))

    def test_a1_reuse_binds_every_case_and_acceptance_field(self):
        a1=dict(binding=self.identity,acceptance_sha='acceptance',FULL_feasible=True)
        self.assertEqual(require_reuse(a1,self.identity),a1)
        for field in self.identity:
            with self.assertRaises(ValueError):require_reuse(a1,dict(self.identity,**{field:'different'}))

    def test_scheduler_failure_isolated_and_resume_does_not_reexecute(self):
        from v44.stages import CHAINS
        with tempfile.TemporaryDirectory(dir=RUN) as temp:
            calls=[]
            def handler(r):
                i=r['identity'];calls.append((i['day'],i['arm'],i['stage']))
                if i['day']=='2025-05-01' and i['arm']=='B0':raise ValueError('EXPECTED_FIXTURE_FAILURE')
                return dict(PASS=True,Native_seconds=0,artifacts=[])
            handlers={s:handler for s in set(s for c in CHAINS.values() for s in c)}
            s=Scheduler(temp,handlers,{'2025-05-01':{'input':'1'},'2025-05-02':{'input':'2'}},{k:10 for k in handlers},diagnostic_fixture=True)
            r=s.all_dates(['2025-05-01','2025-05-02'])
            self.assertEqual(r[0]['status'],'FAILED');self.assertTrue(all(x['status']=='COMPLETE' for x in r[4:]))
            n=len(calls);s.case('2025-05-02','B3');self.assertEqual(n,len(calls))
            with self.assertRaises(ValueError):s.case('2025-05-01','B0')

    def test_checkpoint_detects_mutated_artifact_and_source(self):
        with tempfile.TemporaryDirectory(dir=RUN) as tmp:
            f=Path(tmp)/'artifact.json';f.write_text('{}')
            handlers={s:lambda r:dict(PASS=True,Native_seconds=0,artifacts=[record(f)]) for s in ('REFERENCE','ACTUAL','FRESH')}
            s=Scheduler(tmp,handlers,{'2025-05-01':{'source':'a'}},{},diagnostic_fixture=True)
            self.assertEqual(s.case('2025-05-01','B0')['status'],'COMPLETE')
            f.write_text('{"changed":true}')
            with self.assertRaises(ValueError):s.case('2025-05-01','B0')

    def test_duplicate_lock_is_denied_without_stale_pid_bypass(self):
        with tempfile.TemporaryDirectory(dir=RUN) as tmp:
            with owned_lock(tmp):
                with self.assertRaises((RuntimeError,OSError)):
                    with owned_lock(tmp):pass
            with owned_lock(tmp):pass

    def test_generic_pass_cannot_authorize_full_stage_or_prefix(self):
        for stage in ('A1','A2','M1','M2','K48_M1','K48_M2','ACTUAL','FRESH'):
            with self.assertRaises(ValueError):validate_stage_result(stage,dict(PASS=True,identity=self.identity),self.identity)

    def test_two_peak_raw_fresh_every_array_and_controls(self):
        for check in read(OUT/'TWO_PEAK_FRESH_CHECKS.json'):
            folder=RUN/'two_peak'/check['case'];peer=folder.with_name(folder.name+'_FRESH')
            for p in (folder,peer):
                rec=read(p/'RECEIPT.json');self.assertTrue(all(record(p/n)['sha256']==h for n,h in rec['files'].items()))
            with np.load(folder/'AC_FULL.npz') as x,np.load(peer/'AC_FULL.npz') as y:
                self.assertEqual(x.files,y.files)
                for k in x.files:self.assertTrue(np.array_equal(x[k],y[k]))
            self.assertEqual(read(folder/'STATES.json'),read(peer/'STATES.json'))
            self.assertEqual(read(folder/'EVENTS.json'),read(peer/'EVENTS.json'))

    def test_finite_original_independent_vehicle_validator_and_scope(self):
        from .prestart_certify import fleet
        proof=fleet()
        self.assertTrue(all(v['PASS'] and v['Q250_PASS'] and v['one_per_STA_PASS'] for v in proof['finite_witnesses']))
        self.assertFalse(proof['full120_voltage_PASS']);self.assertFalse(proof['complete_joint_FULL_model_PASS'])

    def test_all_eight_have_move_and_stay_columns_real_model(self):
        builds=read(OUT/'MESS8_NATIVE0_BUILD_REPORT.json')['builds'];b=next(x for x in builds if x['units']==8)
        self.assertEqual(len(b['context']['reachable_move_columns_by_unit']),8)
        self.assertTrue(all(v>0 for v in b['context']['reachable_move_columns_by_unit'].values()))
        self.assertTrue(all(v>0 for v in b['context']['reachable_stay_columns_by_unit'].values()))
        self.assertEqual(b['model']['constraint_families']['energy_balance'],8*96)
        self.assertEqual(b['model']['constraint_families']['initial_SOC'],8)
        self.assertEqual(b['Native_calls'],0);self.assertFalse(b['IEEE8500_FULL_build_PASS'])

    def test_diagnostic_aidc_rejected_when_reference_and_gpuwork_differ(self):
        r=read(OUT/'AIDC_CAUSAL_DIAGNOSTIC_REJECTION.json')
        self.assertEqual(r['status'],'REJECTED_AS_CERTIFIED_FLEXIBILITY_WITNESS')
        self.assertIsNone(r['nonzero_certified_Actual_flexible_kw'])
        self.assertGreater(r['baseline_frozen_max_error_kw'],1e-7)

    def test_campaign_hold_rejects_before_missing_user_permit_is_read(self):
        with self.assertRaisesRegex(PermissionError,'PRESTART_BLOCKED_WITH_EVIDENCE'):require_campaign('NONEXISTENT_PERMISSION_FILE')

    def test_preserved_baseline_and_date_input_receipts(self):
        baseline=read(OUT/'BASELINE_PRESERVATION.json')
        self.assertTrue(all(record(ROOT/p)['sha256']==h for p,h in baseline['files'].items()))
        m=read(OUT/'MAY01_07_PRESTART_INPUT_MANIFEST.json')
        self.assertEqual(len(m['days']),7);self.assertTrue(m['all_file_receipts_PASS'])
        self.assertFalse(m['all_dates_IEEE8500_electrically_certified'])

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PrestartTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    put('PRESTART_TEST_RESULTS.json',dict(PASS=result.wasSuccessful(),tests=result.testsRun,
        failures=[dict(test=str(t),trace=e) for t,e in result.failures],errors=[dict(test=str(t),trace=e) for t,e in result.errors],
        Native_optimizer_calls=0,fixture_tests_do_not_certify_FULL_stage_or_campaign_readiness=True))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':main()
