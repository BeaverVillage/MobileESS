"""Forecast physical admission rejects private/future exogenous substitutes."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json
import tempfile
import unittest

from v42_dstatcom.forecast import forecast_inputs,accepted_arrays
from v42_pr134_b1.common import record


class ForecastAuthority(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'forecast.json'
        target=datetime(2025,5,1,tzinfo=timezone(timedelta(hours=10)))
        self.value=dict(demand_issue='2025-04-30T17:32:39+10:00',pv_issue='2025-04-30T18:00:00+10:00',
            timestamps_96=[(target+timedelta(minutes=15*(i+1))).isoformat() for i in range(96)],
            demand_mw_96=[4800.]*96,pv_mw_96=[0.]*96)

    def tearDown(self):self.temp.cleanup()

    def receipt(self):
        self.path.write_text(json.dumps(self.value),encoding='utf8')
        return record(self.path)

    def test_d1_forecast_with_original_end_of_slot_axis_admitted(self):
        self.assertEqual(forecast_inputs('2025-05-01',self.receipt()),self.value)

    def test_day_actual_vintage_cannot_be_planning_exogenous(self):
        self.value['demand_issue']='2025-05-01T00:15:00+10:00'
        with self.assertRaisesRegex(ValueError,'D1_VINTAGE_REQUIRED'):
            forecast_inputs('2025-05-01',self.receipt())

    def test_naive_issue_or_shifted_slot_axis_rejected(self):
        self.value['pv_issue']='2025-04-30T18:00:00'
        with self.assertRaisesRegex(ValueError,'D1_VINTAGE_REQUIRED'):
            forecast_inputs('2025-05-01',self.receipt())
        self.value['pv_issue']='2025-04-30T18:00:00+10:00'
        self.value['timestamps_96'][0]='2025-05-01T00:00:00+10:00'
        with self.assertRaisesRegex(ValueError,'EXACT_SLOT_AXIS_REQUIRED'):
            forecast_inputs('2025-05-01',self.receipt())

    def test_nonfinite_forecast_and_changed_receipt_rejected(self):
        self.value['pv_mw_96'][42]=float('nan')
        with self.assertRaisesRegex(ValueError,'FINITE_96_EXOGENOUS'):
            forecast_inputs('2025-05-01',self.receipt())
        receipt=self.receipt();self.path.write_text('{}',encoding='utf8')
        with self.assertRaisesRegex(PermissionError,'RECEIPT_DRIFT'):
            forecast_inputs('2025-05-01',receipt)

    def test_real_original_aidc_axis_admitted_without_physical_or_optimizer_call(self):
        source=Path('D:/v42_common_mess_campaign_20261010_01/dates/B2/2025-05-01/attempts/common_u4_v1_01/output/OPERATIONS/SOURCE')
        if not source.exists():self.skipTest('Preserved original physical source unavailable')
        import numpy as np
        physical,mess=accepted_arrays(record(source/'PLANNING_PHYSICAL.npz'),record(source/'PLANNING_MESS.npz'))
        self.assertEqual(list(physical['sites']),[f'AIDC{i:02d}' for i in range(1,13)])
        self.assertEqual(mess['locations'].shape,(96,4))
        self.assertTrue(np.isfinite(mess['P_kw']).all())


if __name__=='__main__':unittest.main()
