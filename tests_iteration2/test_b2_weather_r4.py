import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from b2_recovery_r4 import run as r

class WeatherRecovery(unittest.TestCase):
 def test_original_loader_reproduces_cause_and_same_time_scope_covers_all_boundaries(self):
  from v44_week4 import preparation as prep
  from v44_recovery_r029.weather import loader as original
  old_failure=False
  for day in r.DAYS:
   request=r.read(prep.OPS/'templates'/f'{day}_B0.json');begin=request['axis']['issue_seconds'];bundle=Path(request['actual_bundle'])
   if day=='2025-05-23':
    old=original()(begin=begin,end=begin+120*900,bundle=bundle)
    with self.assertRaisesRegex(ValueError,'CAUSAL_OBSERVATION_TOO_STALE:weather'):
     for t in range(121):old.at(begin+900*t,observed_now=begin+900*t)
    old_failure=True
   obs=r.recovered.loader()(begin=begin,end=begin+120*900,bundle=bundle)
   self.assertEqual(obs.weather.max_staleness_seconds,7200)
   for t in range(121):obs.at(begin+900*t,observed_now=begin+900*t)
  self.assertTrue(old_failure)

 def test_reuse_completed_m1_never_calls_solver_and_preserves_clocks(self):
  from v42_may_campaign_native90.preflight import native_zero
  m=r.read(r.PARENT/'RESULT.json');old=r.read(r.PARENT/'request.json')
  before=[r.record(r.PARENT/n) for n in ('RESULT.json','K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json','COMPLETED_STAGE_CHECKPOINT.json')]
  with tempfile.TemporaryDirectory(dir=r.HOME.parent) as folder,r.previous.old.followup.base.bindings(),r.previous.old.equipment.scope(),native_zero() as denied:
   request=dict(old,case_root=folder)
   result=r.reuse_m1(r.PARENT,request)
   receipt=r.read(Path(folder)/'REUSED_COMPLETED_M1.json')
   self.assertEqual(result,m);self.assertEqual(receipt['new_M1_Native_calls'],0);self.assertFalse(receipt['Native_clock_reset'])
   self.assertEqual(receipt['K48_Native_seconds'],m['K48_Native_seconds']);self.assertFalse(denied)
  r.verify(before)

 def test_fresh_date_request_uses_current_equipment_root_without_resume(self):
  # Exercise the real historical request factory and its unchanged validation;
  # substitute only this new controller's not-yet-issued authority.
  with patch.object(r,'authority',lambda request=None:None),patch.object(r,'record',side_effect=lambda p:r.previous.record(r.previous.AUTH) if Path(p)==r.AUTH else r.previous.record(p)):
   request=r.new_request('2025-05-24',dict(pid=1))
  self.assertEqual(request['campaign_root'],str(r.ROOT));self.assertEqual(request['arm'],'B2')
  self.assertTrue(Path(request['case_root']).is_relative_to(r.ROOT/'2025-05-24/B2'))
  self.assertNotIn('reuse_completed_M1',request);self.assertNotIn('io_resume_M1_parent',request)
  for row in request['sources']:self.assertEqual(Path(row['path']).resolve(),Path(row['path']))

 def test_complete_worker_entry_scopes_keep_canonical_source_lease_and_recovered_loader(self):
  from v44_recovery_r029 import source_io
  from v43_actual import observations
  with patch.object(r,'authority',lambda request=None:None),patch.object(r,'record',side_effect=lambda p:r.previous.record(r.previous.AUTH) if Path(p)==r.AUTH else r.previous.record(p)):
   request=r.new_request('2025-05-23',dict(pid=1))
  called=[]
  def probe(q):
   called.append(True)
   from v44.daily import day_inputs
   begin=q['axis']['issue_seconds'];bundle=Path(day_inputs(q['day'])['actual_bundle'])
   obs=observations.load_observations(begin=begin,end=begin+120*900,bundle=bundle)
   for t in range(121):obs.at(begin+900*t,observed_now=begin+900*t)
   return dict(PASS=True,Native_calls=0,Actual_calls=0)
  from v42_may_campaign_native90.preflight import native_zero
  with tempfile.TemporaryDirectory(dir=r.HOME.parent) as folder:
   request['case_root']=str(Path(folder)/'ENTRY_ONLY');path=Path(folder)/'request.json';r.atomic(path,request)
   with patch.object(r,'boundary',lambda request:dict(protected_case_root='D:/protected')),patch.object(r,'case',probe),native_zero() as denied:
    result=r.worker(path)
   self.assertTrue(result['PASS']);self.assertFalse(denied);self.assertEqual(called,[True])

if __name__=='__main__':unittest.main()
