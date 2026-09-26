import unittest
import numpy as np
import pandas as pd
from study import choose, stats, paired, MODELS, ROLES

class Contract(unittest.TestCase):
    def table(self):
        return pd.DataFrame([dict(state=s,arm=a,role=r,coverage=.91,GPU_coverage=.92,long_under=.1,
            overreserved_GPUh=5.,requested_overreserved_GPUh=10.) for s in ['PENDING','RUNNING'] for a in MODELS for r in ROLES])

    def test_lower_quantile_and_no_candidate_fallback(self):
        table=self.table();self.assertEqual(choose(table)[0],{'PENDING':'R1','RUNNING':'R1'})
        table.loc[table.state.eq('RUNNING'),'coverage']=.89
        self.assertEqual(choose(table)[0]['RUNNING'],'R0')

    def test_both_roles_required_and_preferred_safety(self):
        table=self.table();table.loc[table.arm.eq('R1')&table.role.eq('CALIBRATION'),'coverage']=.89
        self.assertEqual(choose(table)[0]['PENDING'],'R2')
        table=self.table();table.loc[table.arm.eq('R1'),'GPU_coverage']=.89
        self.assertEqual(choose(table)[0]['PENDING'],'R2')

    def test_nan_fails_closed_and_overreserve_strict(self):
        table=self.table();table.loc[table.arm.eq('R2'),'coverage']=np.nan
        table.loc[table.arm.eq('R1'),'overreserved_GPUh']=10.
        self.assertEqual(choose(table)[0]['PENDING'],'R0')

    def sample(self):
        return pd.DataFrame(dict(job_issue_id=['a','b'],issue_time=pd.to_datetime(['2025-01-01','2025-01-02'],utc=True),
            actual_seconds=[1800.,18000.],runtime_seconds=[1800.,36000.],bound_seconds=[900.,21600.],
            num_gpus_req=[4.,1.],requested_seconds=[3600.,43200.],elapsed_seconds=[0.,18000.]))

    def test_runtime_slots_reserve_and_named_pinballs(self):
        s=stats(self.sample());self.assertEqual(s['coverage'],.5);self.assertEqual(s['GPU_coverage'],.2)
        self.assertEqual(s['missed_GPU_slots'],4);self.assertEqual(s['long_under'],0.)
        self.assertEqual(s['overreserved_GPUh'],1.);self.assertEqual(s['reserved_GPUh'],7.)
        self.assertAlmostEqual(s['pinball_Q90'],585.);self.assertAlmostEqual(s['pinball_Q95'],517.5)

    def test_paired_identical_bounds_zero_interval(self):
        f=self.sample()
        for r in paired(f,f,1):
            self.assertEqual(r['delta'],0.)
            if r['metric']!='long_under':
                self.assertEqual(r['CI95_low'],0.);self.assertEqual(r['CI95_high'],0.)

if __name__=='__main__':unittest.main()
