"""Inventory only known migration destinations; preserve pre-existing home/research/envs."""
import os,json,csv,stat,hashlib,subprocess
from pathlib import Path
H=Path.home();O=Path('/mnt/d/ChatGPT/Mobile ESS 2/v42_root_lp_compression_pr/docs/v42_ubuntu_migration_rollback')
M=H/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration'
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def command(a,cwd=None):
    r=subprocess.run(a,cwd=cwd,capture_output=True,text=True);return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
states=[]
for p in (H/'codex_mobileess_workspace/MobileESS',H/'mobileess_worktrees/pr102',H/'mobileess_worktrees/root_lp_compression'):
    states.append(dict(path=str(p),commands={k:command(['git',*a],p) for k,a in {'status':['status','--porcelain'],'branch':['branch','--show-current'],'HEAD':['rev-parse','HEAD'],'log':['log','-5','--oneline'],'remote':['remote','-v']}.items()}))
    assert not command(['git','diff','a88879fdb4e6c51dae35656feee90f68ed19ad8f','--','v42_root','tests'],p)['stdout'] if p.name!='pr102' else True
dump('UBUNTU_GIT_BEFORE_ROLLBACK.json',states)
paths=[('mobileess_research/IEEE8500','Content-addressed store and logical symlinks created by preserve_ieee8500.py; all original Windows/native sources retained'),('mobileess_data','65 explicit copies/path_map and exact version artifact seal created by migration'),('mobileess_research/V42_PR102_evidence','PR102 logs copied by sync_tools.py; originals Windows'),('mobileess_worktrees/pr102','Worktree created by linux_prepare.py at exact PR102 SHA'),('mobileess_worktrees/root_lp_compression','Migration-created WIP worktree; source pushed and Windows restored before deletion'),('codex_mobileess_workspace/MobileESS','Fresh migration clone from complete Windows bundle; original Windows Git/refs preserved'),('mobileess_envs/v42_cpu','Separate migration-only --system-site-packages venv; base power_v61 kept'),('mobileess_envs/v42_gpu','Separate migration-only venv; pre-existing power_v61_gpu kept'),('mobileess_tools/gurobi_cli','Official CPU CLI added solely by migration; pre-existing gurobipy/license kept')]
for p in (H/'mobileess_worktrees').iterdir():
    if p.name.startswith(('V42_ROOT_LP','PR102_GPU_ROOT','V42_EXACT_')):paths.append((str(p.relative_to(H)),'Copied checkpoint evidence/cache or diagnostic staging; exact originals on Windows'))
for n in ('.local/bin/mobileess-v42','.local/bin/gurobi_cl'):
    p=H/n
    if p.exists():
        text=p.read_text();assert 'mobileess_worktrees/root_lp_compression' in text or 'mobileess_tools/gurobi_cli' in text
        paths.append((n,'Migration-only launcher wrapper; contents verified'))
rows=[]
for relative,reason in paths:
    p=H/relative
    if not p.exists():continue
    assert str(p.resolve()).startswith(str(H)+'/') and not p.is_symlink(),p
    total=0;files=0;links=0
    items=[p] if p.is_file() else (Path(folder)/n for folder,dirs,names in os.walk(p,followlinks=False) for n in names)
    for q in items:
        s=q.lstat()
        if stat.S_ISREG(s.st_mode):total+=s.st_size;files+=1
        elif stat.S_ISLNK(s.st_mode):links+=1
    rows.append(dict(path=str(p),classification='MIGRATION_CREATED_DELETE',logical_regular_file_bytes=total,regular_files=files,symlinks=links,reason=reason,delete_approved=False))
    print('MIGRATION_CREATED',p,total,files,flush=True)
keep=[H/'mobile_ess_work',H/'mobile_ess_tools',H/'miniconda3',H/'miniconda3/envs/power_v61',H/'miniconda3/envs/power_v61_gpu']
representatives=[]
for env in ('power_v61','power_v61_gpu'):
    root=H/'miniconda3/envs'/env
    for p in [root/'bin/python3.12',*list((root/'lib/python3.12/site-packages/gurobipy').glob('_core*.so'))]:
        if p.exists():representatives.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
for p in H.glob('*.lic'):
    representatives.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
inputs=list(csv.DictReader((M/'V42_DATA_MIGRATION_MANIFEST.csv').open()))
for row in inputs:
    if row['source'].replace('\\','/').startswith('//wsl.localhost/Ubuntu-MobileESS-D/'):
        p=Path('/'+row['source'].replace('\\','/').split('/',4)[4]);assert sha(p)==row['sha256']
        representatives.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),reason='Pre-existing Linux authority used by original Windows paths; KEEP'))
dump('PREEXISTING_UBUNTU_BASELINE.json',dict(keep_roots=[str(p) for p in keep],representative_hashes=representatives,preexisting_sources_not_migration_destinations=True,CPU=command([str(H/'miniconda3/envs/power_v61/bin/python'),'-c','import gurobipy as g; m=g.Model(); x=m.addVar(vtype=g.GRB.BINARY);m.addConstr(x==1);m.setObjective(x);m.optimize();assert m.Status==2;print(g.gurobi.version(),m.ObjVal)']),GPU_import=command([str(H/'miniconda3/envs/power_v61_gpu/bin/python'),'-c','import gurobipy,importlib.metadata as m;print(m.version("gurobipy"))']),nvidia_smi=command(['nvidia-smi']),df=command(['df','-B1','/'])))
inventory=rows+[dict(path=str(p),classification='PREEXISTING_UBUNTU_KEEP',logical_regular_file_bytes='',regular_files='',symlinks='',reason='Pre-existing Linux research/runtime root; not a deletion target',delete_approved=False) for p in keep]
for name,data in [('UBUNTU_MIGRATION_CREATED_INVENTORY.csv',inventory),('UBUNTU_MIGRATION_DELETE_MANIFEST.csv',rows)]:
    with (O/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(data)
dump('WSL_FREE_SPACE_BEFORE_AFTER.json',dict(before=command(['df','-B1','/']),before_statvfs=dict(block_size=os.statvfs('/').f_frsize,total_blocks=os.statvfs('/').f_blocks,free_blocks=os.statvfs('/').f_bfree,available_blocks=os.statvfs('/').f_bavail),logical_planned_delete_bytes=sum(r['logical_regular_file_bytes'] for r in rows)))
print('LINUX_ROLLBACK_INVENTORY_COMPLETE',sum(r['logical_regular_file_bytes'] for r in rows),flush=True)
