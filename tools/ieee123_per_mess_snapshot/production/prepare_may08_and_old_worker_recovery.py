"""Recover failed May08 and safely drained last old-runtime May06 worker."""
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
E=R/'manifests/per_mess_900s/may08_physics_fix'
assert read(E/'REAL_REJECTION_REGRESSION.json')['status']=='PASS'
drain=read(E/'MAY06_DRAIN_PROOF.json');assert drain['active_atomic_call_completed']
audits=[]
for day,policy in [('2025-05-08','B2'),('2025-05-06','B3')]:
    S=RUN/day/policy/'search';live=read(S/'PER_MESS_LIVE.json')
    assert live['mess_index']==4
    spent=live['elapsed_at_stop'] if day.endswith('08') else drain['preserved_elapsed_seconds']
    assert 0<spent<900
    phase=OUT/day/f'PHASE_{policy}_DA.json'
    if day.endswith('08'):assert read(phase)['status']=='FAIL_CLOSED'
    else:assert not phase.exists()
    completed={}
    for step in (1,2,3):
        path=next((S/'search_cache').rglob(f'STAGE_{step}.json'));value=read(path)
        done=read(S/f'PER_MESS_{step:02}_COMPLETE.json')
        assert done['stop_reason'] in ('SEARCH_COMPLETED','SOFT_BUDGET_EXHAUSTED')
        assert done['retained_child_signatures']==[x['state_sha256'] for x in value['payload']['retained_states']]
        completed[str(step)]=record(path)
    proof=dict(day=day,policy=policy,search_root=str(S),runtime_budget_contract_SHA=m.CONTRACT_SHA,
        reason='REPLACE_PRE_FIX_IN_MEMORY_RUNTIME_WITH_POLYGON_RETENTION_FIX',completed_stages=completed,
        resume_depth=4,elapsed_consumed_seconds=spent,at=time.time(),old_campaign_results_reused=False)
    write_json(S/'TECHNICAL_RECOVERY.json',proof)
    os.environ.update(IEEE123_MESS_SEARCH_ROOT=str(S),IEEE123_MESS_POLICY=policy)
    for step,entry in completed.items():
        value=read(entry['path']);parents=[BeamState.from_dict(x['state']) for x in value['parents']]
        assert m.recover_stage(Path(entry['path']),value['execution'],parents,int(step))==value['payload']
    write_json(E/f'{day}_{policy}_PRESERVED_LIVE.json',live)
    if phase.exists():shutil.move(str(phase),str(E/f'{day}_{policy}_FAILED_PHASE.json'))
    shutil.move(str(LOGS/day/f'{policy}_DA.log'),str(E/f'{day}_{policy}_PRE_UPDATE.log'))
    audits.append(dict(day=day,policy=policy,restored_depths=[1,2,3],elapsed_consumed_seconds=spent,
        remaining_seconds=900-spent,stage_hashes_unchanged=all(record(x['path'])==x for x in completed.values())))
write_json(E/'RECOVERY_REGRESSION.json',dict(status='PASS',optimizer_calls=0,cases=audits))
print(audits)
