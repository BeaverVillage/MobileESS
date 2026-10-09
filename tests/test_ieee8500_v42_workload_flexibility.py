"""Audit original UID/mask conservation and the limited power upper bound."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from ieee8500_v42.workload_flexibility import audit_current_may01, occupancy_by_job, sha
from v42_final.native import canonical_jobs


ROOT=Path(__file__).resolve().parents[1]
PINNED=ROOT/'ieee8500_v42/data/workload_flexibility'
DATA=ROOT/'ieee8500_v42/data/v42_inputs'


class WorkloadFlexibilityAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.result=audit_current_may01(output_dir=cls.temp.name)
        cls.native=json.loads((PINNED/'NATIVE_INPUT.json').read_text(encoding='utf-8-sig'))
        cls.windows=json.loads((PINNED/'WINDOWS.json').read_text(encoding='utf-8-sig'))
        with (Path(cls.temp.name)/'FLEXIBLE_WORKLOAD_JOB_MASKS.csv').open(encoding='utf-8-sig',newline='') as f:
            cls.jobs={r['job_uid']:r for r in csv.DictReader(f)}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_partial_slot_and_future_start_preserve_exact_service(self):
        rows=[dict(job_uid='partial',status='REFERENCE_ASSIGNED',reference_start=24,GPU_gang=4,nominal_remaining_seconds=1350),
              dict(job_uid='later',status='REFERENCE_ASSIGNED',reference_start=27,GPU_gang=2,nominal_remaining_seconds=900),
              dict(job_uid='expired',status='REFERENCE_ASSIGNED',reference_start=0,GPU_gang=10,nominal_remaining_seconds=0)]
        a=occupancy_by_job(rows)
        np.testing.assert_array_equal(a['partial'][:4],[4,2,0,0])
        np.testing.assert_array_equal(a['later'][:5],[0,0,0,2,0])
        self.assertEqual(a['expired'].sum(),0)
        self.assertEqual(a['partial'].sum()*900,4*1350)

    def test_effective_masks_match_original_current_authority(self):
        original={r['job_id']:r for r in canonical_jobs(self.native)}
        raw={r['job_uid']:r for r in self.native['known_population']}
        windows={r['job_id']:r for r in self.windows}
        self.assertEqual(len(self.jobs),1649)
        for uid,row in self.jobs.items():
            if uid not in original:
                self.assertEqual((row['effective_TS'],row['effective_PS'],row['effective_MG_checkpoint_candidate']),('False','False','False'))
                continue
            self.assertEqual(row['effective_TS']=='True',windows[uid]['can_timeshift'])
            self.assertEqual(row['effective_PS']=='True',bool(original[uid]['can_prestart_place']))
            self.assertEqual(row['source_current_Q50_checkpoint_candidate']=='True',bool(original[uid]['can_checkpoint_migrate']))
            self.assertEqual(row['qos'],raw[uid]['cohort'].split('|')[0])
            self.assertEqual(row['protected']=='True',raw[uid]['cohort'].split('|')[3]=='True')
        with (Path(self.temp.name)/'FLEXIBLE_WORKLOAD_AUDIT.csv').open(encoding='utf-8-sig',newline='') as f:
            for cell in csv.DictReader(f):
                for job in json.loads(cell['eligible_jobs_and_source_masks']):
                    self.assertTrue(job['TS'] or job['PS'] or job['MG_checkpoint_mature'])
                    if job['MG_checkpoint_mature']:
                        self.assertLessEqual(int(self.jobs[job['uid']]['current_reference_earliest_eligible_checkpoint']),int(cell['issue_origin_slot']))

    def test_current_and_native_reference_separate_and_bound_excludes_idle_CC4(self):
        result=self.result
        with np.load(Path(self.temp.name)/'KNOWN_JOB_FLEXIBILITY_BOUND.npz',allow_pickle=False) as arr:
            known=np.zeros((96,12));index={s:i for i,s in enumerate(result['sites'])}
            # Separate direct source-only calculation on the Native R0 axis.
            for row in self.native['known_population']:
                if row['planning_site']=='UNASSIGNED':
                    self.assertEqual(row['exact_service_seconds'],0)
                    continue
                for t in range(96):
                    slot=t+24;start=row['reference_start_if_authorized']
                    seconds=max(0,min(900,row['exact_service_seconds']-(slot-start)*900)) if slot>=start else 0
                    known[t,index[row['planning_site']]]+=row['GPU_gang']*seconds/900
            np.testing.assert_allclose(arr['native_reference_known_gpu'],known,rtol=0,atol=1e-12)
            self.assertGreater(np.max(abs(arr['known_gpu']-known)),1)
            self.assertTrue(np.all(arr['eligible_gpu']<=arr['known_gpu']+1e-10))
            power=json.loads((DATA/'POWER_AUTHORITY.json').read_text(encoding='utf-8-sig'))
            np.testing.assert_allclose(arr['P_upper_bound_kw'],arr['eligible_gpu']*arr['C1_slope']*power['current_IT_swing_kW_per_active_GPU'],rtol=1e-13)
            np.testing.assert_allclose(arr['Q_upper_bound_kvar'],arr['P_upper_bound_kw']*np.tan(np.arccos(power['PF_AIDC'])),rtol=1e-13)
        receipt=result['receipt']
        self.assertFalse(receipt['anonymous_CC4_flexibility_claimed'])
        self.assertFalse(receipt['certified_admissible_candidate_weights'])
        self.assertFalse(receipt['AIDC_direction']['Q_independently_controllable'])
        self.assertEqual(receipt['Native_optimization_calls'],0)
        self.assertEqual(receipt['OpenDSS_calls'],0)

    def test_portable_input_bytes_and_no_campaign_mutation(self):
        receipt=self.result['receipt'];manifest=receipt['pinned_current_input_manifest']
        for name,record in manifest['files'].items():
            self.assertEqual(sha(PINNED/name),record['sha256'])
            self.assertTrue(record['byte_identical_copy'])
        self.assertTrue(receipt['source_readonly_identity_PASS'])
        self.assertTrue(receipt['UID_exact_compute_seconds_identity_PASS'])
        self.assertTrue(receipt['current_inputs_portable_fallback_used'])


if __name__=='__main__':
    unittest.main()
