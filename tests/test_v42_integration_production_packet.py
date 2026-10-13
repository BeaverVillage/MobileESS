from copy import deepcopy
import unittest

from v42_integration.production_case import assemble_native_bundle


class ProductionPacketTests(unittest.TestCase):
    def setUp(self):
        row=dict(job_uid='j',planning_eligible=True,current_site_if_running=None,service_slots=2,
            GPU_gang=2,state='PENDING',submit_time='2025-04-30T07:00:00+00:00',elapsed_seconds=None,
            V10_Q50_total_seconds=1500.)
        self.old=dict(known_population=[row],issue_time='2025-04-30T08:00:00+00:00',
            day='2025-05-01',network='grid',alpha_BG=1.,capacities={'s':4},
            racks=[dict(aidc_id='s',compatibility_GPU_limit=4)],WAN={},battery={},initial_MESS_sites={},
            C0_Q50=[1.],C0_Q90=[2.],C0_binding={},runtime_provider={},runtime_reserve_gamma=1.,
            runtime_survival_kernel={},traffic_forecast_sha='traffic',unknown_nominal_GPU=[1.,2.],
            CC4_reserve_GPU=[3.,4.],electrical_certificate=dict(path='old',sha256='old'),
            grid_outputs={},route_table=dict(path='oldroute',sha256='route',bytes=8),
            new_timeshift_authority=dict(path='old',sha256='same',bytes=1),reference={'old':'source'})
        self.template=deepcopy(self.old)
        self.raw=deepcopy(self.old)
        self.raw['known_population']=[dict(job_uid='j',state='PENDING',GPU_gang=2,
            submit_time=row['submit_time'],elapsed_seconds=0.,Q50_total_seconds=1500.,compatible_sites=['s'])]
        self.raw['electrical_certificate']=dict(path='current',sha256='current')
        self.raw['route_table']['path']='currentroute'
        self.raw['reference']={'another_arm':'never imported'}

    def test_full_schema_stays_while_explicit_current_physical_fields_merge(self):
        result,audit=assemble_native_bundle(self.old,self.raw,self.template)
        self.assertEqual(result['known_population'],self.old['known_population'])
        self.assertEqual(result['reference'],self.old['reference'])
        self.assertEqual(result['electrical_certificate']['path'],'current')
        self.assertTrue(audit['full_job_schema_retained'])
        self.assertTrue(audit['raw_projection_reference_not_imported'])

    def test_raw_projection_cannot_replace_full_job_packet(self):
        with self.assertRaisesRegex(ValueError,'SAVED_FULL_NATIVE_JOB_DESCRIPTOR_SCHEMA_REQUIRED'):
            assemble_native_bundle(self.raw,self.raw,self.raw)

    def test_no_gpu_or_nominal_service_drift(self):
        for field,value in (('GPU_gang',1),('Q50_total_seconds',1501.)):
            raw=deepcopy(self.raw);raw['known_population'][0][field]=value
            with self.assertRaisesRegex(ValueError,'ISSUE_JOB_NOMINAL_SERVICE_DRIFT'):
                assemble_native_bundle(self.old,raw,self.template)

    def test_cc4_reconstruction_bits_do_not_replace_saved_quantities(self):
        self.raw['unknown_nominal_GPU'][0]+=1e-12
        result,audit=assemble_native_bundle(self.old,self.raw,self.template)
        self.assertEqual(result['unknown_nominal_GPU'],self.old['unknown_nominal_GPU'])
        self.assertFalse(audit['CC4']['unknown_nominal_GPU']['projection_exact_equal'])

    def test_known_uid_loss_and_route_bytes_rejected(self):
        raw=deepcopy(self.raw);raw['known_population']=[]
        with self.assertRaisesRegex(ValueError,'KNOWN_UID_ROSTER_DRIFT'):
            assemble_native_bundle(self.old,raw,self.template)
        raw=deepcopy(self.raw);raw['route_table']['sha256']='different'
        with self.assertRaisesRegex(ValueError,'EXACT_SAME_DAY_ROUTE_DRIFT'):
            assemble_native_bundle(self.old,raw,self.template)


if __name__=='__main__':
    unittest.main()
