import json, time, shutil, hashlib
from pathlib import Path
import psutil
H=Path(r'D:\ChatGPT\Mobile ESS 2\IEEE8500_PAPER_SCALE_ONLY_20260920\full_production_paper_BG055200_AIDC240_MESS200')
out=H/'diagnostic_attempts'/('BEFORE_PAPER_TERMINATION_'+time.strftime('%Y%m%d_%H%M%S'))
out.mkdir(parents=True,exist_ok=False)
targets=[(86024,'campaign_resume_after_sparse_b2.py'),(87296,'mess_worker.py')]
processes=[]
for pid,script in targets:
    if not psutil.pid_exists(pid): continue
    p=psutil.Process(pid); command=p.cmdline()
    assert script in ' '.join(command),(pid,command)
    assert Path(p.cwd()).resolve() in (H.resolve(),(H/'B2').resolve()),(pid,p.cwd())
    processes.append(dict(pid=pid,cmdline=command,cwd=p.cwd(),created=p.create_time(),cpu=p.cpu_times()._asdict()))
for name in ['STATUS.json','CAMPAIGN_STATUS.json','ACTIVE_CAMPAIGN_CONTINUATION_STATUS.json','mess_runtime.py','mess_grid8500_active.py','mess_worker.py','campaign_resume_after_sparse_b2.py','FINAL_CANDIDATE_FREEZE.json','MESS_NO_CUTOFF_AUDIT.json']:
    if (H/name).is_file():shutil.copy2(H/name,out/name)
for name in ['B2/solver_trace/call_00008','B2/beam','B2_PREFERRED_BOUND_REPAIR_RUN_20260921']:
    if (H/name).is_dir():shutil.copytree(H/name,out/name)
manifest=[]
for name in ['B2/beam','B2/candidate_cache']:
    for f in (H/name).rglob('*'):
        if f.is_file():
            with f.open('rb') as s: h=hashlib.file_digest(s,'sha256').hexdigest()
            manifest.append(dict(path=str(f),bytes=f.stat().st_size,sha256=h))
(out/'SNAPSHOT.json').write_text(json.dumps(dict(unix=time.time(),processes=processes,files=manifest,
    reason='User requests restoring paper solver termination',inflight_model_not_serialized=True,
    completed_checkpoints_preserved=True),indent=2),encoding='utf-8')
# Stop supervisor first so an intentional solver stop cannot launch another stage.
for row in processes:
    p=psutil.Process(row['pid'])
    assert p.create_time()==row['created']
    p.terminate();p.wait(timeout=20)
    print('STOPPED',row['pid'],flush=True)
(out/'STOPPED.json').write_text(json.dumps(dict(unix=time.time(),stopped=processes),indent=2),encoding='utf-8')
(H/'PAPER_TERMINATION_TRANSITION.json').write_text(json.dumps(dict(status='PRESERVED_AND_STOPPED',diagnostic=str(out),unix=time.time()),indent=2),encoding='utf-8')
print('PRESERVED',out,flush=True)
