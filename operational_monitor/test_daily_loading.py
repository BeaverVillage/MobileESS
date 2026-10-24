import copy,hashlib,json,tempfile,unittest
from pathlib import Path
import monitor_service
import active_equipment_overlay as overlay

class DailyLoadingTests(unittest.TestCase):
 def raw(self):
  rows=[]
  for slot in range(120):
   ratio=.99 if slot<24 else .6
   rows.append(dict(slot=slot,full_physical=dict(currents=[
    dict(element='line.l115',current_A=ratio*400,NormalAmps=400,loading_pu=ratio),
    dict(element='transformer.example',current_A=980,NormalAmps=1000,loading_pu=.98)])))
  return dict(prefix_slots=24,evaluation_slots=96,physical_steps=rows)
 def receipt(self,path,value):
  raw=json.dumps(value).encode();path.write_bytes(raw)
  return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 def test_daily_peak_excludes_prefix_and_transformers(self):
  with tempfile.TemporaryDirectory() as folder:
   r=self.receipt(Path(folder)/'fresh.json',self.raw())
   audit=dict(independent_Fresh120=dict(maximum_line_loading_pu=.99),raw=r)
   value=overlay.evaluation_loading('B2',audit)
   self.assertEqual(value['maximum_line_loading_pu'],.6)
   self.assertEqual(value['physical_slots'],96)
   self.assertEqual(value['peak_slot'],24)
   self.assertEqual(value['peak_element'],'line.l115')
 def test_invalid_axis_hash_and_current_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fresh.json';raw=self.raw()
   raw['physical_steps'][25]['slot']=24
   r=self.receipt(path,raw)
   with self.assertRaisesRegex(ValueError,'EXACT_AXIS'):overlay.evaluation_loading('B2',dict(raw=r))
   raw=self.raw();raw['physical_steps'][30]['full_physical']['currents'][0]['loading_pu']=.1
   r=self.receipt(path,raw)
   with self.assertRaisesRegex(ValueError,'RATIO_MISMATCH'):overlay.evaluation_loading('B2',dict(raw=r))
   r['sha256']='0'*64
   with self.assertRaisesRegex(ValueError,'RECEIPT_MISMATCH'):overlay.evaluation_loading('B2',dict(raw=r))
 def test_no_fallback_to_120_and_existing_B3_daily_preserved(self):
  self.assertEqual(overlay.evaluation_loading('B2',dict(independent_Fresh120=dict(maximum_line_loading_pu=.99))),{})
  self.assertEqual(overlay.evaluation_loading('B3',dict(evaluation96=dict(maximum_line_loading_pu=.67)))['maximum_line_loading_pu'],.67)
 def test_live_overlay_keeps_physical_gate_and_other_cells(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);fresh=self.receipt(root/'fresh.json',self.raw())
   audit=dict(PASS=True,independent_Fresh120=dict(PASS=True,maximum_line_loading_pu=.99),
              MESS_SOC_PCS_routes=dict(PASS=True),original_M1_FULL_replay=True,raw=fresh)
   a=self.receipt(root/'audit.json',audit)
   result=self.receipt(root/'result.json',dict(PASS=True,independent_audit=a))
   job=dict(day='2025-05-22',arm='B2',status='PASS',case_root=str(root),result=result,equipment_version='825')
   registry=root/'registry.json'
   self.receipt(registry,dict(B3_fixed_recovery_PASS=True,jobs=[job],phase='COMPLETE',B2_root=str(root),
                            B2_state=dict(phase='COMPLETE'),superseded_failures={}))
   value=dict(cases=[],case_line_loading=dict(rows=[dict(day='2025-05-22',scope='current',cells=[
    dict(arm='B0',percent=88),dict(arm='B2',percent=99)])]))
   original=copy.deepcopy(value)
   from unittest.mock import patch
   with patch('active_runtime.connect',side_effect=lambda value,*args:value):
    out=overlay.apply(value,lambda _:False,registry)
   cells=out['case_line_loading']['rows'][0]['cells']
   self.assertEqual(cells[1]['percent'],60.)
   self.assertTrue(cells[1]['physical_pass'])
   self.assertEqual(cells[0],original['case_line_loading']['rows'][0]['cells'][0])
   self.assertEqual(value,original)
   audit['independent_Fresh120']['PASS']=False
   job['audit']=self.receipt(root/'audit.json',audit)
   self.receipt(registry,dict(B3_fixed_recovery_PASS=True,jobs=[job]))
   with self.assertRaisesRegex(ValueError,'FULL_PHYSICAL_GATES'):overlay.apply(value,lambda _:False,registry)

if __name__=='__main__':unittest.main()
