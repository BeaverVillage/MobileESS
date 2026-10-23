from pathlib import Path
import sys,time,json,subprocess,psutil,os
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT));H=Path(__file__).parent
from v2_add_preflight.stage_common import OUT,read,record,put
from v2_add_preflight.prestart_execution import atomic
python=Path('D:/ChatGPT/Mobile ESS 2/V2_add_runtime/.venv/Scripts/python.exe')
owner=json.loads((H/'A1_AFTER_PROCESS_IDENTITY.json').read_text(encoding='utf8'))
state=dict(role='SEQUENTIAL_POST_PAUSE_VALIDATION',PASS=False,steps=[],never_official_campaign_launcher=True)
def save():atomic(H/'SEQUENTIAL_REPLAY_STATE.json',state)
save()
while True:
    try:
        p=psutil.Process(owner['pid']);live=abs(p.create_time()-owner['process_created'])<.001 and p.is_running()
    except psutil.NoSuchProcess:live=False
    if not live:break
    time.sleep(5)
assert read(OUT/'A1_ORIGINAL_P1_FULL_PREPARATION.json')['PASS'],'A1_NATIVE0_AFTER_NOT_COMPLETE'
jobs=[
 ('A1_receipt',['-m','v2_add_preflight.stage_a_receipt','A1']),
 ('RAM_policy',['-m','v2_add_preflight.stage_resources']),
 ('M1_handler',['-m','v2_add_preflight.stage_factory_fixture']),
 ('M1_FULL',['-c',"from v2_add_preflight.stage_m_validator_fixture import certify;certify('M1',r'"+str(H/'FULL_REPLAY')+"')"]),
 ('M2_FULL',['-c',"from v2_add_preflight.stage_m_validator_fixture import certify;certify('M2',r'"+str(H/'FULL_REPLAY')+"')"]),
 ('Joint_Native0_after',[str(H/'replay_native0.py'),'JOINT']),
 ('M1_static_Native0_after',[str(H/'replay_native0.py'),'M1']),
 ('M2_static_Native0_after',[str(H/'replay_native0.py'),'M2']),
 ('A2_Native0_after',['-m','v2_add_preflight.stage_a_canary','A2']),
 ('A2_receipt',['-m','v2_add_preflight.stage_a_receipt','A2']),
 ('A1_grid_FULL',['-m','v2_add_preflight.stage_a_verify','A1']),
 ('A2_grid_FULL',['-m','v2_add_preflight.stage_a_verify','A2']),
 ('A_handler',['-m','v2_add_preflight.stage_a_entry_fixture']),
 ('Actual_prepare',['-m','v2_add_preflight.stage_actual_prepare_fixture']),
 ('Actual_migration',['-m','v2_add_preflight.stage_work_migration_fixture']),
 ('Actual_full120',['-m','v2_add_preflight.stage_handler_fixture']),
 ('Independent_Fresh120',['-m','v2_add_preflight.stage_fresh_fixture']),
 ('Final_guards',['-m','v2_add_preflight.stage_guard_fixture']),
 ('Gurobi_IO',['-m','v2_add_preflight.stage_gurobi_io_fixture'])]
for name,args in jobs:
    log=H/('REPLAY_'+name+'.log');start=time.perf_counter();row=dict(name=name,status='RUNNING',argv=args,log=str(log));state['steps'].append(row);save()
    print('START',name,flush=True)
    with log.open('w',encoding='utf8') as stream:
        result=subprocess.run([str(python),'-X','utf8','-B','-u',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    row.update(status='PASS' if result.returncode==0 else 'FAIL',exit_code=result.returncode,wall_seconds=time.perf_counter()-start);save()
    print(row['status'],name,round(row['wall_seconds'],3),flush=True)
    if result.returncode:raise RuntimeError('SEQUENTIAL_REPLAY_FAILED:'+name)
state['PASS']=True;save();print('SEQUENTIAL_REPLAY_COMPLETE',flush=True)
