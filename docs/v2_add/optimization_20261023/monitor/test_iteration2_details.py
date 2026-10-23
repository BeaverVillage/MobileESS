"""Regression checks for V2_add journals in the existing monitor."""
import unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
import iteration2_details as view
import monitor_service

def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf8')

class V2MonitorTests(unittest.TestCase):
 def test_same_existing_page_has_no_old_campaign_and_one_refresh(self):
  page=monitor_service.index().decode('utf8')
  self.assertIn('<h1>V2_add · May01 캠페인</h1>',page)
  for old in ('r043','V44_iteration2','31일','825 kVA','M2 → A3'):self.assertNotIn(old,page)
  self.assertEqual(page.count("fetch('/api/status'"),1)
  self.assertEqual(page.count('id="v2-preparation"'),1)
  self.assertEqual(page.count('id="iteration2-days"'),1)
  self.assertIn('renderIteration2(s.v2_add_details)',page)

 def test_B3_uses_B1_A1_with_zero_new_solver_budget(self):
  self.assertEqual(view.CHAINS['B3'][0],'A1_REUSE')
  self.assertNotIn('A1',view.CHAINS['B3'])
  self.assertEqual(set(view.CHAINS),{'B0','B1','B2','B3'})
  with tempfile.TemporaryDirectory() as d:
   b=view.native(Path(d),'A1_REUSE',False)
   self.assertEqual(b['ceiling'],0);self.assertEqual(b['measured'],0)

 def test_diagnostic_calls_and_native_do_not_become_official_results(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);h=root/'prep';out=root/'docs';h.mkdir()
   for script in ('replay_sequence.py','post_replay_canaries.py'):
    (h/script).write_text("jobs=[('one',[])]",encoding='utf8')
   write(h/'SEQUENTIAL_REPLAY_STATE.json',dict(steps=[dict(name='one',status='PASS')]))
   write(out/'ISOLATED_NUMERICAL_CANARY_20261023.json',dict(PASS=True,diagnostic_Native_optimize_calls=3,Native_seconds=90))
   with patch.object(view,'H',h),patch.object(view,'OUT',out),patch.object(view,'RUN',root),patch.object(view,'processes',lambda:[]):
    data=view.apply({},lambda i:False)
   self.assertFalse(data['v2_add_details']['official_campaign_started'])
   self.assertEqual(data['v2_add_details']['official_measured_Native_seconds'],0)
   self.assertEqual(data['v2_add_details']['diagnostic_Native_optimize_calls'],3)
   self.assertFalse(data['metrics_visible'])
   self.assertEqual(data['active_experiment'],'V2_add')

 def test_tampered_checkpoint_is_not_complete(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'2025-05-01/B3/A1_REUSE/CHECKPOINT.json'
   value=dict(status='COMPLETE',identity={},result=dict(PASS=True,reused_exact_A1=True),files=[])
   value['checkpoint_sha']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
   write(p,value)
   self.assertEqual(view.stage(root,'B3','A1_REUSE',lambda i:False)['status'],'COMPLETE')
   value['result']['reused_exact_A1']=False;write(p,value)
   self.assertEqual(view.stage(root,'B3','A1_REUSE',lambda i:False)['status'],'BLOCKED')

 def test_active_attempt_cannot_escape_current_runtime(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'official'
   write(root/'CONTROL/B2/M1_ACTIVE_ATTEMPT.json',dict(path=str(Path(d)/'other')))
   with self.assertRaisesRegex(ValueError,'ONLY_CURRENT_V2_RUNTIME_ALLOWED'):
    view.stage(root,'B2','M1',lambda i:False)

if __name__=='__main__':unittest.main()