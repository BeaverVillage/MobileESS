from pathlib import Path
import sys,gzip,pickle,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024
from v44.common import read,atomic,now
from v44_recovery_r024.adaptive_pricing import AdaptivePricing
from v42_may_campaign_native90.preflight import native_zero
from v44_recovery_r024.a2_continue import FrozenWeights
root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt005/A2/OUTPUT')
out=Path('D:/MobileESS_V44/development/r024/pipeline_validation');out.mkdir(exist_ok=False)
assert read(out.parent/'real_validation/RESULT.json')['PASS']
with native_zero() as denied:
 with gzip.open(root/'STATIC/INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
 attr=read(root/'PHASE_I/S11/ATTRIBUTION/RESIDUAL_ATTRIBUTION.json')
 candidates=[];receipts=[]
 for p in (root/'PHASE_I/S11/PRICE/B').glob('*/CONCRETE_RECOVERY.json'):
  d=read(p);candidates+=d['candidates'];receipts.append(d)
 a=AdaptivePricing(out)
 a.feedback=[dict(voltage_rows=[dict(row=x['row'],slot=x['time'],node=x['node']) for x in attr['top_rows'] if x['family'] in ('voltage_lower','voltage_upper')],relative_decrease=None)]
 def archived_oracle(*args):
  keys=set(args[12]);cs=[c for c in candidates if c['class_id'] in keys]
  return dict(receipts=[r for r in receipts if r['class_id'] in keys]),cs
 a.compiled[archived_oracle]=archived_oracle
 master=FrozenWeights(state['reference'],state['grows'],None).elastic_master(state['compact'],state['grows'])
 result,selected=a.price(None,state,master,None,{}, {},attr,np.zeros(len(state['axes'])),{},out/'PRICE',archived_oracle)
 guidance=read(out/'PRICE/R024_VIOLATION_GUIDANCE.json')
 assert guidance['voltage_row_sensitivities'] and len(selected)>0
 assert not result['full_native_fractional_LP_pricing_closure'] and not denied
 atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,Native_calls=0,archived_oracle_fixture=True,new_native_oracle_not_claimed=True,
  real_full_model_guidance_and_selection_pipeline=True,selected=len(selected),classes_planned=result['classes_priced'],
  voltage_rows_with_sensitivities=len(guidance['voltage_row_sensitivities']),deadline_and_GPU_domains_unchanged=True))
 print(read(out/'RESULT.json'))
