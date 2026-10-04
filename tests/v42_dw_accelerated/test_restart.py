"""Crash/restart budget and append-only registry exercised without any optimizer."""
import json,hashlib
from types import SimpleNamespace
import numpy as np
from v42_dw_accelerated.integration import Integration

def test_inflight_restart_debits_full_reservation_and_restores_column_once(tmp_path,monkeypatch):
 import v42_dw_accelerated.integration as module
 def write(n,d):(tmp_path/n).write_text(json.dumps(d))
 monkeypatch.setattr(module,'OUT',tmp_path);monkeypatch.setattr(module,'write',write)
 (tmp_path/'DW_RUNTIME_FEATURE_SELECTION.json').write_text('{}')
 np.savez(tmp_path/'saved.npz',x=[1.],a=[2.],c=3.)
 column=dict(file='saved.npz',file_SHA=module.sha(tmp_path/'saved.npz'),MESS='MESS01',SHA256='a'*64)
 state={k:[] for k in ['rmps','prices','rounds','certs','canaries','capture_ledger','smoothing_rows','accepted','uppers']};state['columns']=[column]
 cp=dict(authority_key='b'*64,feature_selection_SHA=module.sha(tmp_path/'DW_RUNTIME_FEATURE_SELECTION.json'),elapsed_budget=100.,elapsed_wall=20.,restart_state=state,RMP=dict(round=2),best_interval=[.5,.6],best_corrected_LB=.4,alpha_next=.1,smooth_file=None,type='DISCOVERY_ADDED')
 write('DW_BUDGET_JOURNAL.json',dict(elapsed_budget=180.));write('DW_INFLIGHT.json',dict(spent_before=170.,reserved_optimize_seconds=24.))
 added=[];fake=SimpleNamespace(resume_checkpoint=cp,audit_authority=SimpleNamespace(key='b'*64),master=SimpleNamespace(add=lambda *args:added.append(args)),seen=[set() for _ in range(4)])
 Integration.restore_run(fake)
 assert fake.budget_carried==194. and len(added)==1 and fake.column_id==1 and fake.seen[0]=={'a'*64}
 assert fake.columns==[column] and fake.current_round==2
 assert json.loads((tmp_path/'DW_RESUME_RECEIPT.json').read_text())['no_second_budget_grant']

def test_completed_pricing_receipts_are_restored_without_new_dispatch(tmp_path,monkeypatch):
 from v42_dw_accelerated.cg_reuse import Mechanics
 import v42_dw_accelerated.cg_reuse as module
 from v42_dw_accelerated.common import union_seconds
 def write(n,d):
  p=tmp_path/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
 monkeypatch.setattr(module,'OUT',tmp_path);monkeypatch.setattr(module,'write',write)
 jobs=[];prices=[]
 for m in range(4):
  receipt=f'p{m}.json';jobs.append(dict(call=m+1,receipt=receipt))
  price=dict(call=m+1,round=1,unit=m,dual_SHA='s',true_dual_SHA='t',native_status=11,capture_errors=[],ObjVal=-1.,valid_point=True,early_stop=dict(STOP_REASON='DISCOVERY_QUOTA_FILLED',accepted_count=4),interval=[1.,5.]);write(receipt,price);prices.append(price)
 row=dict(perf=3.,available_RAM=4*1024**3,commit_percent=70.)
 stats=dict(min_available_RAM=row['available_RAM'],max_commit_percent=70.)
 monitor=SimpleNamespace(phase='',rows=[],failed=[],sample=lambda:monitor.rows.append(row),summary=lambda rows:dict(stats))
 class Pipe:
  def send(self,job):raise AssertionError('COMPLETED NATIVE CALL REPLAYED')
 fake=SimpleNamespace(resource_gate=lambda kind:None,workers=4,remaining=lambda:1000.,spent=lambda:100.,current_round=1,monitor=monitor,resume_phase=dict(kind='DISCOVERY',true_dual_SHA='t',search_file='smooth.npz',search_key='s',jobs=jobs),smooth_weight=.1,smoothing_rows=[],pipes=[Pipe()]*4,prices=[],call=0,canaries=[],debit_done=lambda:None)
 actual,safe=Mechanics.pricing_round(fake,'DISCOVERY',(None,None,'t','true.npz'),20)
 assert safe and [r['call'] for r in actual]==[1,2,3,4] and len(fake.prices)==4
 assert fake.canaries[0]['actual_four_overlap_seconds']==4.
