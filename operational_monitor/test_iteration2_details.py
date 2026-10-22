import unittest,tempfile,json,hashlib
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import patch
import iteration2_details as view
import monitor_service

def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf8')

def receipt(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

class ExistingMonitorDetails(unittest.TestCase):
 def state(self,root,phase='WAIT_B2'):
  state=dict(phase=phase,jobs=[dict(day=f'2025-05-{i:02d}',status='QUEUED',stages={}) for i in range(1,32)],workers=[],
   supervisor=dict(pid=1,process_created=1),lease=dict(pid=3,process_created=3),UTC=datetime.now(timezone.utc).isoformat(),commit_sha='sealed')
  write(root/'STATE.json',state);return state

 def test_B2_remains_primary_with_31_followup_rows(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   self.state(Path(d));old=dict(day='2025-05-25 B2',stage='M1',worker_PID=100,workers=[dict(pid=100)],worker_alive=True,coordinator_alive=True,active_state_source='B2/state',used_text='K48 300s',cases=[dict(arm='B3',status='PASS')]);before=deepcopy(old)
   out=view.apply(old,lambda who:True)
   for k in old:self.assertEqual(out[k],old[k])
   self.assertEqual(old,before);self.assertEqual(len(out['iteration2_details']['rows']),31);self.assertEqual(out['iteration2_details']['planning_pass'],0);self.assertEqual(len(out['iteration2_details']['slots']),7)

 def test_user_stop_is_explicit_and_has_no_live_workers(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   self.state(Path(d),'USER_STOPPED')
   out=view.apply(dict(worker_alive=False,coordinator_alive=False),lambda who:False)
   self.assertEqual(out['state'],'USER_STOPPED');self.assertIn('사용자 요청',out['status'])
   self.assertFalse(out['worker_alive']);self.assertEqual(out['workers'],[])

 def test_stage_PASS_needs_SHA_bound_FULL_and_new_A_solver(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   root=Path(d);core=root/'A2/RESULT.json';public=root/'RESULT.json'
   value=dict(FULL_feasible=True,Native_seconds=12.,independent_Global_LB_validated=True,certified_gap=.001);write(core,value)
   p=dict(PASS=True,original_FULL_PASS=True,stage='A3',day='2025-05-01',core_result=receipt(core),new_AIDC_FULL_optimization=True,Native_seconds=12.,UB=.6,LB=.599,Gap=.001);write(public,p)
   item=dict(status='PASS',result=receipt(public));self.assertEqual(view.stage('2025-05-01','A3',item)['status'],'PASS')
   value['Native_seconds']=0;write(core,value);p['core_result']=receipt(core);write(public,p);item['result']=receipt(public)
   self.assertEqual(view.stage('2025-05-01','A3',item)['status'],'VERIFY_ERROR')
   public.write_text('{}');self.assertEqual(view.stage('2025-05-01','A3',item)['status'],'VERIFY_ERROR')

 def test_no_Fresh_PASS_from_status_flag_or_absent_audit(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   p=Path(d)/'RESULT.json';write(p,dict(day='2025-05-01',PASS=True))
   row=view.actual('2025-05-01',dict(status='PASS',result=receipt(p)))
   self.assertIsNone(row['Fresh_PASS']);self.assertEqual(row['status'],'VERIFY_ERROR')

 def test_Fresh_and_overall_fail_are_separate(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   root=Path(d);a=root/'AUDIT.json';p=root/'RESULT.json';write(a,dict(PASS=False,independent_Fresh120=dict(PASS=True)))
   write(p,dict(day='2025-05-01',PASS=False,independent_audit=receipt(a)))
   row=view.actual('2025-05-01',dict(status='FAILED',result=receipt(p)))
   self.assertTrue(row['Fresh_PASS']);self.assertFalse(row['overall_PASS']);self.assertEqual(row['label'],'Fresh PASS · 종합 미통과')

 def test_same_main_cards_follow_real_public_M3_after_B2(self):
  with tempfile.TemporaryDirectory() as d,patch.object(view,'ROOT',Path(d)):
   root=Path(d);s=self.state(root,'PLANNING_SERIAL');case=root/'2025-05-01/B3/attempt003';who=dict(pid=2,process_created=2)
   write(case/'START.json',who);ctx=dict(day='2025-05-01',stage='M2',case_sha='M3-new')
   write(case/'M2/progress.json',dict(budget_kind='PLANNING_NATIVE',stage_context=ctx,Native_Runtime=90.,UTC=s['UTC']))
   write(case/'M2/JOINT_NATIVE_LEDGER.json',dict(stage_context=ctx,measured_Native_Runtime=50.,inflight={}))
   write(case/'M2/K48_NATIVE_LEDGER.json',dict(measured_Native_Runtime=300.));write(case/'M2/LOWER_STAGE_RESULT.json',dict(Global_LB_valid=True,Global_LB=.5))
   s['workers']=[dict(who,day='2025-05-01',stage='M3',root=str(case))];s['jobs'][0]['stages']['M3']=dict(status='RUNNING',root=str(case));write(root/'STATE.json',s)
   old=dict(worker_alive=False,coordinator_alive=False,cases=[dict(arm='B0',status='COMPLETE')],case_line_loading=dict(rows=[dict(day='old',cells=[])]))
   out=view.apply(old,lambda w:w.get('pid') in (1,2,3))
   self.assertEqual(out['stage'],'M3');self.assertEqual(out['arm'],'B3');self.assertEqual(out['worker_PID'],2);self.assertIn('Joint 90.0',out['used_text']);self.assertEqual(out['case_line_loading'],old['case_line_loading']);self.assertEqual(out['cases'],old['cases'])
   self.assertEqual(out['actual_tick_details']['total'],31);self.assertEqual(out['actual_tick_details']['rows'][0]['active_stage'],'M3');self.assertEqual(out['actual_tick_details']['rows'][0]['pid'],2)
   write(case/'START.json',dict(pid=999,process_created=2));out=view.apply(old,lambda w:w.get('pid') in (1,2,3));self.assertFalse(out['worker_alive']);self.assertIsNone(out['worker_PID'])

 def test_original_DOM_fetch_and_r043_identity_extended_in_place(self):
  page=monitor_service.index().decode('utf8')
  for name in ('case-loading-body','actual-ticks-body','bounds-history-body','iteration2-days','iteration2-workers'):
   self.assertEqual(page.count('id="'+name+'"'),1)
  self.assertIn('<h1>V44 r043 · 5월 캠페인</h1>',page);self.assertEqual(page.count("fetch('/api/status'"),1)
  self.assertEqual(page.count('renderIteration2(s.iteration2_details);'),1);self.assertNotIn('8796',page);self.assertNotIn('<iframe',page)

if __name__=='__main__':unittest.main()
