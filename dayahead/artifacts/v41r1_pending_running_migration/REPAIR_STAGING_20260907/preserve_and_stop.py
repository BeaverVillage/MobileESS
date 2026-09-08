from pathlib import Path
import json, shutil, time
import psutil
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.data import RUNTIME

archive=RUNTIME/'revision_history/20260907_gap_001_and_guard_repair'
archive.resolve().relative_to(RUNTIME.resolve())
archive.mkdir(parents=True,exist_ok=False)
state=read(RUNTIME/'campaign_state.json')
assert state['scientific_commit']=='e7fc82cce415d36f524cf5db80e31d244c8e7698'
processes=[]
supervisor=psutil.Process(state['pid'])
assert 'dayahead.v41r1.campaign_run' in supervisor.cmdline()
processes.append(supervisor)
for row in state['units'].values():
    if row['status'] not in ('DAYAHEAD_RUNNING','ACTUAL_RUNNING'):continue
    proc=psutil.Process(row['worker_pid'])
    cmd=proc.cmdline()
    assert all(x in cmd for x in ('dayahead.v41.execution',row['day'],row['policy'],state['scientific_commit']))
    processes.append(proc)
proof=[dict(pid=p.pid,command=p.cmdline(),memory=p.memory_info()._asdict(),created=p.create_time()) for p in processes]
write_json(archive/'BEFORE_STOP.json',dict(state=state,processes=proof,
    reason='USER_AUTHORIZED_P1_P2_MIPGAP_0.001_REVISION',
    termination_is_scientific_failure=False,B1_solution_available=False,
    authorization='User selected 0.1% P1/P2; P3-P5 and physical tolerances unchanged'))
for p in processes:p.terminate()
gone,alive=psutil.wait_procs(processes,timeout=15)
assert not alive
for name in ('campaign_state.json','campaign_progress.json','campaign_heartbeat.json','campaign_memory.json',
             'FULL_MAY_FROZEN_RELEASE.json','FULL_MAY_LAUNCH.json','DETACHED_FULL_MAY_PROOF.json'):
    shutil.copyfile(RUNTIME/name,archive/name)
gate_names=['EXACT_COMPRESSION_GATE.json','V41_TEST_RESULTS.xml','FULL_MAY_PREPARATION.json',
    'FIXED_FOUR_WORKER_MEMORY_STRESS_GATE.json','FIXED_FOUR_WORKER_SOLVER_CONFIGURATION.json',
    'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json']
for name in gate_names:shutil.copyfile(OUT/name,archive/name)
folder=RUNTIME/'2025-05-01/B1/dayahead'
folder.resolve().relative_to(RUNTIME.resolve())
assert not (folder/'DAYAHEAD_RECEIPT.json').exists()
files=[dict(relative=str(p.relative_to(folder)),original=record(p)) for p in folder.rglob('*') if p.is_file()]
destination=archive/'May01_B1_zero_gap_attempt'
destination.resolve().relative_to(RUNTIME.resolve())
folder.rename(destination)
for item in files:
    target=destination/item['relative'];item['preserved']=record(target)
    assert item['original']['sha256']==item['preserved']['sha256']
log=ROOT/'logs/v41r1_migration/full_may/2025-05-01/B1/dayahead.log'
shutil.copyfile(log,archive/'May01_B1_zero_gap.log')
write_json(archive/'PRESERVATION.json',dict(status='PASS',files=files,
    classification='INTERRUPTED_FOR_USER_AUTHORIZED_GAP_REVISION',completed_B0_modified=False,
    B1_incumbent_not_accepted=True,source_commit=state['scientific_commit']))
state['status']='PAUSED_FOR_AUTHORIZED_REVISION'
state['units']['2025-05-01/B1'].update(status='PENDING',worker_pid=None,phase=None,
    prior_attempt=record(archive/'PRESERVATION.json'))
write_json(RUNTIME/'campaign_state.json',state)
progress=read(RUNTIME/'campaign_progress.json');progress.update(status=state['status'],current=[])
write_json(RUNTIME/'campaign_progress.json',progress)
write_json(RUNTIME/'campaign_heartbeat.json',progress)
write_json(OUT/'USER_APPROVED_P1_P2_GAP.json',dict(P1_relative_gap=.001,P2_relative_gap=.001,
    P3_P5_relative_gap=0.,absolute_gap=0.,physical_tolerances='UNCHANGED',
    user_answer='0.1% 허용 (권장)',preservation=record(archive/'PRESERVATION.json')))
print(json.dumps(dict(status='PRESERVED_AND_STOPPED',archive=str(archive),processes=proof),ensure_ascii=True))
