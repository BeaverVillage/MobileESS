import hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'D:/MobileESS_v42_autonomous')
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,read,atomic,now

repo=Path('D:/MobileESS_v42_autonomous').resolve()
root=Path('D:/v42_may_restart_20261010_02').resolve()
target=Path('D:/v42run33').resolve()
assert str(target)==r'D:\v42run33' and not target.exists()
commit=subprocess.check_output(['git','rev-parse',sys.argv[1]],cwd=repo,text=True).strip()
registry=read(root/'AUTONOMOUS_MANIFEST.json')
manifest=read(registry['B2_deployment_manifest'])
execution=sources()
paths=set(execution)
original=manifest['builder_original_sources']
paths.update(original)
assets=['docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json',
 'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json',
 'docs/v42_april_b0_capacity_queue_voltage_calibration/ELECTRICAL_SOURCE_AUTHORITY.json',
 'docs/v42_may_b0_zero_margin_holdout/PREREGISTRATION.json','.gitattributes']
paths.update(assets)
assert len(execution)==98 and len(original)==1007 and len(paths)==1110
assert all((repo/p).is_file() and not any(c in p for c in ('*','?','[',']','\n','\r')) for p in paths)
subprocess.run(['git','worktree','add','--detach','--no-checkout',str(target),commit],cwd=repo,check=True)
subprocess.run(['git','sparse-checkout','init','--no-cone'],cwd=target,check=True)
subprocess.run(['git','sparse-checkout','set','--no-cone','--stdin'],cwd=target,
 input='\n'.join('/'+p for p in sorted(paths))+'\n',text=True,check=True)
subprocess.run(['git','read-tree','-m','-u','HEAD'],cwd=target,check=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=target,text=True).strip()==commit
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=target,text=True).strip()
bound=[]
for p in sorted(paths):
 expected=record(repo/p);actual=record(target/p)
 assert (expected['sha256'],expected['bytes'])==(actual['sha256'],actual['bytes']),p
 if p in execution:assert actual['sha256']==execution[p]
 if p in original:assert actual['sha256']==original[p]
 bound.append(actual)
doc=dict(PASS=True,UTC=now(),schema='V42_SPARSE_IMMUTABLE_SOURCE_FREEZE_V33',commit=commit,
 code_root=str(target),execution_source_count=len(execution),builder_original_source_count=len(original),
 unique_file_count=len(bound),source_files=bound,Native_optimize_calls=0,model_constructions=0,
 future_worker_admission_smoke_required=True,active_workers_untouched=True)
atomic(root/'autonomous/V33_SPARSE_IMMUTABLE_FREEZE.json',doc)
print(json.dumps(dict(PASS=True,receipt=record(root/'autonomous/V33_SPARSE_IMMUTABLE_FREEZE.json'),commit=commit,files=len(bound))))
