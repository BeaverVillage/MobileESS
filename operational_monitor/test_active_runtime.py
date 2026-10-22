import unittest,tempfile,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import monitor_service
import active_runtime as runtime

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf8')

class RuntimeTests(unittest.TestCase):
 def test_history_cached_but_active_overlay_runs_each_refresh(self):
  from unittest.mock import patch
  import active_equipment_overlay
  s=monitor_service;before=(s._history_key,s._history_view);s._history_key=s._history_view=None
  try:
   with patch.object(s.binding,'atomic'),patch.object(s.binding,'optional',return_value=dict(B3_fixed_recovery_PASS=True,original_batch=dict(sha256='fixed'))),patch.object(s.binding,'view',return_value=dict(immutable='history')) as view,patch.object(active_equipment_overlay,'apply',side_effect=lambda value,alive:dict(value,current=True)) as overlay:
    self.assertTrue(s.snapshot()['current']);self.assertTrue(s.snapshot()['current'])
    self.assertEqual(view.call_count,1);self.assertEqual(overlay.call_count,2)
  finally:s._history_key,s._history_view=before
 def fixture(self,root):
  case=root/'2025-05-22/B2/attempt003';ctx=dict(arm='B2',stage='M1',source_sha='exact',stage_case_sha='same825')
  write(case/'START.json',dict(pid=3,process_created=30))
  write(case/'progress.json',dict(stage='M1'))
  write(case/'M1/progress.json',dict(UTC=datetime.now(timezone.utc).isoformat(),budget_kind='PLANNING_NATIVE',stage_context=ctx,Native_Runtime=150.))
  write(case/'M1/K48_NATIVE_LEDGER.json',dict(measured_Native_Runtime=300.09,stage_context=dict(ctx,stage='K48_M1'),authorization=dict(old_native_clocks_reused=True)))
  write(case/'M1/JOINT_NATIVE_LEDGER.json',dict(measured_Native_Runtime=100.,stage_context=ctx,inflight=dict(UTC='now'),authorization=dict(old_native_clocks_reused=True)))
  write(case/'M1/LOWER_STAGE_RESULT.json',dict(Global_LB_valid=True,Global_LB=.5))
  trace=case/'M1/GLOBAL_CONTROL/GLOBAL_GAP_TRACE.jsonl';write(trace,dict(FULL_feasible=True,bound_consistency=True,Global_LB=.5,Global_UB=.625))
  job=dict(day='2025-05-22',arm='B2',status='BASELINE_RUNNING',pid=3,case_root=str(case),equipment_version='825')
  ledger=dict(jobs=[job],B2_root=str(root),B2_state=dict(lease=dict(pid=2,process_created=20),phase='B2_IO_FIXED_SERIAL_FULL_CASES',UTC=datetime.now(timezone.utc).isoformat(),commit_sha='current'))
  value=dict(status='実行',state='RUNNING',cases=[dict(day=job['day'],arm='B2',status='RUNNING')],solver_note='verified B3 retained',
   used=0,remaining=0,metrics_visible=False,stage_bounds=[dict(stage='OLD')],actual_tick_details=dict(rows=[]),case_line_loading=dict(rows=[dict(day=job['day'],scope='current',cells=[dict(arm='B2')])]))
  return case,ctx,ledger,value
 def test_all_panels_use_live_M1(self):
  with tempfile.TemporaryDirectory() as d:
   case,ctx,ledger,value=self.fixture(Path(d));before=deepcopy(ledger)
   out=runtime.connect(value,ledger,lambda v:v.get('pid') in (2,3))
   self.assertEqual(out['worker_PID'],3);self.assertEqual(out['stage'],'M1');self.assertTrue(out['metrics_visible'])
   self.assertAlmostEqual(out['used'],450.09);self.assertEqual(out['Native_completed_seconds'],400.09)
   self.assertAlmostEqual(out['remaining'],750.);self.assertEqual(out['bound_details']['relative_gap'],.2)
   self.assertEqual(out['stage_bounds'][0]['stage'],'M1');self.assertEqual(out['actual_tick_details']['rows'][0]['pid'],3)
   self.assertIn('Joint 150.0',out['used_text']);self.assertEqual(ledger,before);self.assertEqual(value['used'],0)
 def test_cross_case_callback_is_not_charged(self):
  self.assertEqual(runtime.native(dict(measured_Native_Runtime=4,stage_context=dict(source='a')),dict(Native_Runtime=999,budget_kind='PLANNING_NATIVE',stage_context=dict(source='b')),'PLANNING_NATIVE'),(4,4))
 def test_dead_worker_not_shown_live(self):
  with tempfile.TemporaryDirectory() as d:
   case,ctx,ledger,value=self.fixture(Path(d));out=runtime.connect(value,ledger,lambda v:v.get('pid')==2)
   self.assertFalse(out['worker_alive']);self.assertEqual(out['workers'],[]);self.assertFalse(out['metrics_visible'])
   self.assertEqual(out['stage_bounds'],[]);self.assertEqual(out['cases'][0]['status'],'DISCONNECTED')
 def test_dead_coordinator_is_not_automatic_ready(self):
  with tempfile.TemporaryDirectory() as d:
   case,ctx,ledger,value=self.fixture(Path(d));out=runtime.connect(value,ledger,lambda v:False)
   self.assertEqual(out['state'],'DISCONNECTED');self.assertFalse(out['Actual_auto_start_armed'])
 def test_diagnosed_retry_is_pending_not_Fresh_fail(self):
  with tempfile.TemporaryDirectory() as d:
   case,ctx,ledger,value=self.fixture(Path(d));failed=Path(d)/'2025-05-23/B2/attempt001'
   write(failed/'RESULT.json',dict(error='IMPLEMENTATION_FAILURE_BEST_FULL_PRESERVED'))
   write(failed/'M1/RESULT.json',dict(implementation_errors=["FileNotFoundError(2, 'No such file or directory')"]))
   ledger['jobs'].append(dict(day='2025-05-23',arm='B2',status='ACTUAL_FAILED',case_root=str(failed),equipment_version='825'))
   value['cases'].append(dict(day='2025-05-23',arm='B2',status='FAILED'))
   value['case_line_loading']['rows'].append(dict(day='2025-05-23',scope='current',cells=[dict(arm='B2',state='Fresh FAIL')]))
   out=runtime.connect(value,ledger,lambda v:v.get('pid') in (2,3))
   self.assertEqual(out['retry_queued'],1);self.assertEqual(out['failed'],0);self.assertTrue(out['cases'][1]['retry_queued'])
   self.assertEqual(ledger['jobs'][1]['status'],'ACTUAL_FAILED')
   cell=out['case_line_loading']['rows'][1]['cells'][0];self.assertEqual(cell['state'],'M1 저장 오류 · 복구 대기');self.assertFalse(cell['physical_pass'])
 def test_validated_B3_detail_no_old_error(self):
  with tempfile.TemporaryDirectory() as d:
   case,ctx,ledger,value=self.fixture(Path(d));b3=Path(d)/'2025-05-29/B3/attempt001';write(b3/'RESULT.json',dict(PASS=True))
   ledger['jobs'].append(dict(day='2025-05-29',arm='B3',status='PASS',case_root=str(b3)))
   value['actual_tick_details']['rows']=[dict(day='2025-05-29',arm='B3',reason='OLD FAIL')]
   out=runtime.connect(value,ledger,lambda v:v.get('pid') in (2,3));row=out['actual_tick_details']['rows'][1]
   self.assertEqual(row['reason'],'');self.assertEqual(row['case_root'],str(b3));self.assertEqual(row['preparation_status'],'PASS')
   self.assertEqual(row['control_tick_text'],'고정궤적 AC 검증')

if __name__=='__main__':unittest.main()
