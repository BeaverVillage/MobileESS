"""Validate preserved Linux roots, original hashes and licensed CPU solver after compaction."""
import json,hashlib,subprocess,os,csv
from pathlib import Path
O=Path('/mnt/d/ChatGPT/Mobile ESS 2/v42_root_lp_compression_pr/docs/v42_ubuntu_migration_rollback');H=Path.home()
def read(n):return json.loads((O/n).read_text(encoding='utf-8-sig'))
def run(a):
    r=subprocess.run(a,capture_output=True,text=True);return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
b=read('PREEXISTING_UBUNTU_BASELINE.json');verified=[]
for row in b['representative_hashes']:
    p=Path(row['path']);assert p.is_file() and p.stat().st_size==row['bytes']
    with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256'],p
    verified.append(row)
assert all(Path(p).is_dir() for p in b['keep_roots'])
deleted=read('UBUNTU_MIGRATION_DELETION_RECEIPT.json')['deleted']
assert all(not os.path.lexists(r['path']) for r in deleted)
cpu=run([str(H/'miniconda3/envs/power_v61/bin/python'),'-c','import gurobipy as g;m=g.Model();m.Params.OutputFlag=0;x=m.addVar(vtype=g.GRB.BINARY);m.addConstr(x==1);m.setObjective(x);m.optimize();assert m.Status==2 and m.ObjVal==1;print(g.gurobi.version(),m.ObjVal)'])
gpu=run([str(H/'miniconda3/envs/power_v61_gpu/bin/python'),'-c','import gurobipy,importlib.metadata as m;print(m.version("gurobipy"))'])
git=run(['git','--version']);nvidia=run(['nvidia-smi']);df=run(['df','-B1','/'])
assert cpu['returncode']==gpu['returncode']==git['returncode']==0
receipt=dict(PASS=True,shell_started=True,home_readable=H.is_dir(),keep_roots=b['keep_roots'],representative_hashes_unchanged=verified,all_known_migration_paths_absent=True,CPU=cpu,GPU_import=gpu,git=git,nvidia_smi=nvidia,df=df,canonical_V42_runtime='WINDOWS',scope='Representative pre-existing hashes and roots checked; unrelated large Linux research was neither scanned fully nor modified')
(O/'POST_ROLLBACK_UBUNTU_HEALTHCHECK.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print('POST_COMPACTION_UBUNTU_HEALTH_PASS',flush=True)
