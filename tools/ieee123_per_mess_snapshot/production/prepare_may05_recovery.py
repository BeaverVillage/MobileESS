"""Prepare one attested in-campaign technical resume without resetting its budget."""
import os,sys,time,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W))
from v41r4_windows_paths import install_long_file_operations
install_long_file_operations()
from dayahead.paper_analysis.storage import read,write_json
from fast_prepare import record
from v41r4_900_namespace import RUN,OUT,LOGS
import v41r4_per_mess_budget as m
from dayahead.v35r3e_r1.beam import BeamState
E=R/'manifests/per_mess_900s/may05_physics_fix'
S=RUN/'2025-05-05/B3/search'
assert read(E/'REAL_REJECTION_REGRESSION.json')['status']=='PASS'
failed=OUT/'2025-05-05/PHASE_B3_DA.json'
assert read(failed)['status']=='FAIL_CLOSED'
live=read(S/'PER_MESS_LIVE.json');assert live['mess_index']==2 and live['stop_reason']=='PHYSICAL_FAIL'
stage=next((S/'search_cache').rglob('STAGE_1.json'))
value=read(stage)
assert value['payload']['runtime_budget_contract_SHA']==m.CONTRACT_SHA
complete=read(S/'PER_MESS_01_COMPLETE.json')
assert complete['stop_reason'] in ('SEARCH_COMPLETED','SOFT_BUDGET_EXHAUSTED')
assert complete['retained_child_signatures']==[x['state_sha256'] for x in value['payload']['retained_states']]
proof=dict(day='2025-05-05',policy='B3',search_root=str(S),runtime_budget_contract_SHA=m.CONTRACT_SHA,
    reason='USER_REQUESTED_TECHNICAL_RECOVERY_RESTRICTED_TRANSFORMER_POLYGON_GATE',
    completed_stages={'1':record(stage)},resume_depth=2,elapsed_consumed_seconds=live['elapsed_at_stop'],
    original_failure=record(failed),at=time.time(),old_campaign_results_reused=False)
write_json(S/'TECHNICAL_RECOVERY.json',proof)
os.environ.update(IEEE123_MESS_SEARCH_ROOT=str(S),IEEE123_MESS_POLICY='B3')
parents=[BeamState.from_dict(x['state']) for x in value['parents']]
assert m.recover_stage(stage,value['execution'],parents,1)==value['payload']
assert m.recover_stage(stage,value['execution'],parents,2) is None
m.NODES=[];m.NEUTRAL=[]
m.begin_depth('2025-05-05','B3',1,'MESS02',[],None,None,None,None,S)
assert live['elapsed_at_stop']<=m.ACTIVE.elapsed<live['elapsed_at_stop']+10
write_json(E/'RECOVERY_REGRESSION.json',dict(status='PASS',stage_restored_without_recompute=True,
    original_depth2_seconds=live['elapsed_at_stop'],resume_elapsed=m.ACTIVE.elapsed,
    remaining_seconds=900-m.ACTIVE.elapsed,optimizer_calls=0,stage1_unchanged=record(stage)==proof['completed_stages']['1']))
# Preserve the failed attempt and its terminal snapshot before opening a retry.
write_json(E/'FAILED_MESS02_LIVE.json',live)
shutil.copy2(S/'PER_MESS_02_COMPLETE.json',E/'FAILED_MESS02_COMPLETE.json')
shutil.move(str(failed),str(E/'FAILED_PHASE_B3_DA.json'))
shutil.move(str(LOGS/'2025-05-05/B3_DA.log'),str(E/'FAILED_B3_DA.log'))
print('RECOVERY_PREPARED_STAGE1_REUSE_DEPTH2_DEBIT',live['elapsed_at_stop'])
