"""Finish authorized checks and start May01 only after real gates pass."""
from pathlib import Path
import sys,time,subprocess,json,shutil,traceback,atexit
H=Path(__file__).parent
ROOT=Path('D:/ChatGPT/Mobile ESS 2/V2_add');sys.path.insert(0,str(ROOT))
from v2_add_preflight.stage_common import RUN,OUT,read,record
from v2_add_preflight.prestart_execution import atomic
from v2_add_preflight.stage_campaign import source_files
from v42_native.contracts import digest
python=RUN.parent/'.venv/Scripts/python.exe'
instruction=Path('C:/Users/kjw39/.codex/attachments/42e1403c-7a34-449d-ba61-1052c7847700/붙여넣은 텍스트.txt')
pause=Path('D:/MobileESS_V44/runtime/V44_iteration2_fresh_20261023/OPERATIONS/PAUSE_FOR_V2_ADD_20261023/PAUSED_FOR_V2_ADD.json')
status=dict(status='WAITING_REQUIRED_EXECUTION_CHECKS',official_campaign_executed=False,
            additional_RAM_optimization=False,additional_performance_benchmarks=False)
def save():atomic(H/'PREPARE_AND_LAUNCH_STATE.json',status)
def command(name,args):
    print('START',name,flush=True)
    with (H/(name+'.log')).open('w',encoding='utf8') as log:
        result=subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(name+':exit='+str(result.returncode))
    print('PASS',name,flush=True)
try:
    from original_root_source_guard import protect
    root_guard=protect();root_proof=root_guard.__enter__()
    atexit.register(root_guard.__exit__,None,None,None)
    save()
    while True:
        first=read(H/'SEQUENTIAL_REPLAY_STATE.json')
        if any(row['status']=='FAIL' for row in first['steps']):raise RuntimeError('REQUIRED_NATIVE0_OR_FULL_CHECK_FAILED')
        path=H/'POST_REPLAY_STATE.json'
        second=read(path) if path.exists() else {}
        if any(row['status']=='FAIL' for row in second.get('steps',[])):raise RuntimeError('REQUIRED_NUMERICAL_CHECK_FAILED')
        if first.get('PASS') and second.get('PASS'):break
        time.sleep(5)
    if source_files()!=read(H/'FROZEN_ADAPTER_SOURCE_SET.json')['source_files']:
        raise RuntimeError('FROZEN_SOURCE_SET_DRIFT')
    status['status']='RECONCILING_EXACT_EVIDENCE';save()
    command('RESTORE_HISTORICAL_READBACK',[str(python),'-X','utf8','-B',str(H/'restore_historical_readback.py')])
    from v2_add_preflight.stage_report import generate
    from v2_add_preflight.stage_optimization_gate import certify
    from v2_add_preflight.stage_seal import seal
    generate();proof=certify(H,instruction,pause);assert proof['PASS']
    proof['validated_evidence'].append(record(H/'ORIGINAL_ROOT_SOURCE_VERIFICATION.json'))
    proof['execution_identity']['additional_original_source_files']=root_proof['files']
    proof['execution_identity']['additional_original_source_guard']=record(H/'original_root_source_guard.py')
    from canonical_input_identity import canonical_inputs
    lineage=proof['execution_identity']['inputs']
    canonical=canonical_inputs(lineage,record)
    identity_audit=dict(PASS=True,manifest_lineage=lineage,canonical_inputs=canonical,
        all_bytes_and_sha256_preserved=True,producer=record(H/'canonical_input_identity.py'))
    atomic(H/'INPUT_ALIAS_REPAIR_20261023/CANONICAL_INPUT_VERIFICATION.json',identity_audit)
    proof['execution_identity']['inputs']=canonical
    proof['execution_identity']['input_manifest_lineage']=lineage
    proof['validated_evidence'].append(record(H/'INPUT_ALIAS_REPAIR_20261023/CANONICAL_INPUT_VERIFICATION.json'))
    atomic(OUT/'V2_ADD_OPTIMIZATION_VERIFICATION_20261023.json',proof)
    generate();seal()
    final=read(OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json')
    assert final['status']=='READY_FOR_MAY01_CAMPAIGN_APPROVAL'
    archive=ROOT/'docs/v2_add/optimization_20261023_official_io_repair';archive.mkdir(exist_ok=False)
    (archive/'.gitattributes').write_text('*.json -text\n*.txt -text\n*.log -text\n*.py -text\n',encoding='utf8')
    selected=['USER_INSTRUCTION.txt','USER_STEERING_STOP_RAM_20261023.txt','FROZEN_ADAPTER_SOURCE_SET.json',
              'SEQUENTIAL_REPLAY_STATE.json','POST_REPLAY_STATE.json','HISTORICAL_READBACK_RESTORATION.json',
              'FINAL_RELATED_TESTS.log','A1_PROFILE_AFTER.txt',
              'replay_sequence.py','post_replay_canaries.py','replay_native0.py',
              'restore_historical_readback.py','complete_preparation_and_launch.py',
              'original_root_source_guard.py','ORIGINAL_ROOT_SOURCE_VERIFICATION.json']
    selected+=['canonical_input_identity.py','test_canonical_input_identity.py']
    selected+=['carry_verified_B0.py']
    for name in selected:shutil.copyfile(H/name,archive/name)
    monitor=H/'V2_MONITOR_DELIVERY'
    if monitor.exists():shutil.copytree(monitor,archive/'monitor')
    repair=H/'BOUND_JSON_REPAIR_20261023'
    if repair.exists():shutil.copytree(repair,archive/'bound_json_repair')
    shutil.copytree(H/'INPUT_ALIAS_REPAIR_20261023',archive/'input_alias_repair')
    shutil.copytree(H/'OFFICIAL_IO_REPAIR_20261023',archive/'official_io_repair')
    atomic(archive/'EXACT_BYTE_MANIFEST.json',dict(files=[record(archive/name) for name in selected],
           no_untested_active_key_compression=True,additional_RAM_work_stopped=True,
           original_model_and_physics_preserved=True,formal_execution_requires_all_real_gates=True))
    command('GIT_DIFF_CHECK',['git','diff','--check'])
    command('GIT_STAGE_V2',['git','add','--','v2_add_preflight','tests/test_v2_add_campaign_optimization.py',
                          'docs/v2_add/static_complete','docs/v2_add/optimization_20261023_official_io_repair'])
    command('GIT_COMMIT_V2',['git','commit','-m','V2_add: fix May01 execution paths and validate expanded Native budgets'])
    # A transport failure does not invalidate passed local scientific gates.
    with (H/'GIT_PUSH_V2.log').open('w',encoding='utf8') as log:
        pushed=subprocess.run(['git','push','origin','HEAD'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    status['push_exit_code']=pushed.returncode
    approval=H/'MAY01_FORMAL_EXECUTION_AUTHORIZATION.json'
    atomic(approval,dict(explicit_human_campaign_approval=True,
        prestart_certificate_sha=record(OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json')['sha256'],
        experiment_id='V2_add',days=['2025-05-01'],execution_identity_sha=digest(final['execution_identity']),
        human_instruction=record(instruction),latest_human_steering=record(H/'USER_STEERING_STOP_RAM_20261023.txt'),
        authority='Original October23 human directive explicitly approves May01 after all gates pass'))
    from v2_add_preflight.stage_authority import require_approval
    require_approval(approval)
    root=RUN/'official_stage_campaign/May01_20261023_iofix'
    if root.exists():raise FileExistsError('OFFICIAL_NEW_ROOT_REQUIRED')
    from carry_verified_B0 import prepare as carry_B0
    carry_B0(root,RUN/'official_stage_campaign/May01_20261023_after_execution_checks',H)
    status.update(status='OFFICIAL_CAMPAIGN_STARTING',official_root=str(root),authorization=record(approval));save()
    from v2_add_preflight.stage_campaign import run
    results=run(root,approval,resume=True)
    status.update(status='OFFICIAL_CAMPAIGN_RETURNED',official_campaign_executed=True,results=results);save()
    print(json.dumps(status,ensure_ascii=False,indent=2),flush=True)
except BaseException as error:
    status.update(status='BLOCKED_WITH_PRESERVED_EVIDENCE',error=repr(error),traceback=traceback.format_exc());save()
    print(status['traceback'],flush=True);raise
