from pathlib import Path
import sys,time,subprocess,psutil,json
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT));H=Path(__file__).parent
from v2_add_preflight.stage_common import RUN,SOURCE,record,read
from v2_add_preflight.stage_campaign import source_files
from v2_add_preflight.stage_pause import verify as verify_pause
from v2_add_preflight.prestart_execution import atomic
from v42_native.contracts import digest
python=RUN.parent/'.venv/Scripts/python.exe'
while True:
    state=read(H/'SEQUENTIAL_REPLAY_STATE.json')
    if state.get('PASS'):break
    if any(r['status']=='FAIL' for r in state['steps']):raise RuntimeError('UPSTREAM_REPLAY_FAILED')
    time.sleep(5)
pause=Path('D:/MobileESS_V44/runtime/V44_iteration2_fresh_20261023/OPERATIONS/PAUSE_FOR_V2_ADD_20261023/PAUSED_FOR_V2_ADD.json')
instruction=Path('C:/Users/kjw39/.codex/attachments/42e1403c-7a34-449d-ba61-1052c7847700/붙여넣은 텍스트.txt')
verify_pause(record(pause))
permit=H/'ISOLATED_CANARY_AUTHORIZATION_OFFICIAL_IO_REPAIR.json'
atomic(permit,dict(role='ISOLATED_NUMERICAL_CANARY',explicit_human_canary_authorization=True,
    official_campaign_result=False,source_sha=digest(SOURCE),Native_seconds_per_account=30.,
    human_instruction=record(instruction),iteration2_pause=record(pause),source_files=source_files(),
    authority='October23 human directive section5.2 authorizes isolated short numerical diagnostics'))
previous=read(H/'OFFICIAL_IO_REPAIR_20261023/POST_REPLAY_STATE.json')
state=dict(PASS=False,steps=[r for r in previous['steps'] if r['status']=='PASS' and r['name']=='K48_all_actual_Native0'],official_campaign_executed=False,
    previous_completed_checks=record(H/'OFFICIAL_IO_REPAIR_20261023/POST_REPLAY_STATE.json'),
    source_IO_compatibility=record(H/'OFFICIAL_IO_REPAIR_20261023/SOURCE_COMPATIBILITY.json'))
jobs=[
 ('K48_all_actual_Native0',['-m','v2_add_preflight.stage_m_binding','k48_native0']),
 ('M1_numerical',['-m','v2_add_preflight.stage_numerical_canary',str(RUN/'isolated_numerical_canary/Oct23_M1_03_official_io_repair'),str(permit)]),
 ('A1_numerical',['-m','v2_add_preflight.stage_a_numerical_canary',str(RUN/'isolated_numerical_canary/Oct23_A1_02_official_io_repair'),str(permit)]),
 ('final_A1_receipt',['-m','v2_add_preflight.stage_a_receipt','A1']),
 ('final_A2_receipt',['-m','v2_add_preflight.stage_a_receipt','A2']),
 ('final_A_entry',['-m','v2_add_preflight.stage_a_entry_fixture'])]
for name,args in jobs:
    if any(r['name']==name and r['status']=='PASS' for r in state['steps']):continue
    row=dict(name=name,status='RUNNING');state['steps'].append(row);atomic(H/'POST_REPLAY_STATE.json',state)
    start=time.perf_counter();print('START',name,flush=True)
    with (H/('POST_'+name+'.log')).open('w',encoding='utf8') as log:
        run=subprocess.run([str(python),'-X','utf8','-B','-u',*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    row.update(status='PASS' if run.returncode==0 else 'FAIL',returncode=run.returncode,wall_seconds=time.perf_counter()-start)
    atomic(H/'POST_REPLAY_STATE.json',state);print(row['status'],name,row['wall_seconds'],flush=True)
    if run.returncode:raise RuntimeError('POST_REPLAY_FAILED:'+name)
state['PASS']=True;atomic(H/'POST_REPLAY_STATE.json',state)
print('POST_REPLAY_ALL_PASS',flush=True)
