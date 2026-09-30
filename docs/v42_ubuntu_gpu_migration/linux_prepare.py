"""Install canonical Linux files from already sealed Windows evidence."""
import csv,json,hashlib,shutil,subprocess,os
from pathlib import Path
HOME=Path.home();WIN=Path('/mnt/d/ChatGPT/Mobile ESS 2');SRC=WIN/'v42_root_lp_compression_pr';DOC=SRC/'docs/v42_ubuntu_gpu_migration'
def run(args,cwd=None):subprocess.run(args,cwd=cwd,check=True)
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def winpath(p):
    p=p.replace('\\','/')
    if p.startswith('//wsl.localhost/Ubuntu-MobileESS-D/'):return Path('/'+p.split('/',4)[4])
    if p.startswith('C:/codex_mobileess_workspace/'):p=p.replace('C:/codex_mobileess_workspace/','D:/codex_mobileess_workspace/',1)
    if p.startswith('C:/Users/kjw39/OneDrive/문서/ChatGPT/'):p=p.replace('C:/Users/kjw39/OneDrive/문서/ChatGPT/','D:/ChatGPT/',1)
    return Path('/mnt/'+p[0].lower()+p[2:])
repo=HOME/'codex_mobileess_workspace/MobileESS';work=HOME/'mobileess_worktrees';work.mkdir(exist_ok=True)
repo.parent.mkdir(exist_ok=True)
if not repo.exists():run(['git','clone',str(WIN/'V42_MIGRATION_GIT_ALL.bundle'),str(repo)])
else:
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():raise RuntimeError('EXISTING_CANONICAL_REPO_DIRTY')
run(['git','remote','set-url','origin','https://github.com/BeaverVillage/MobileESS.git'],repo)
# The verified complete-history bundle also preserves local branches and tags.
run(['git','fetch',str(WIN/'V42_MIGRATION_GIT_ALL.bundle'),'+refs/heads/*:refs/remotes/windows-preserved/*','+refs/tags/*:refs/tags/*'],repo)
if not (work/'pr102').exists():run(['git','worktree','add','--detach',str(work/'pr102'),'cd7e40762097b6c20303bd2238edf7ffeba87aa4'],repo)
if not (work/'root_lp_compression').exists():run(['git','worktree','add',str(work/'root_lp_compression'),'codex/v42-root-lp-compression-a1'],repo)
out=work/'root_lp_compression/docs/v42_ubuntu_gpu_migration';shutil.copytree(DOC,out,dirs_exist_ok=True)
rows=list(csv.DictReader((DOC/'V42_DATA_MIGRATION_MANIFEST.csv').open(encoding='utf8')));mapping={}
for row in rows:
    src=winpath(row['source']);dst=Path(row['destination']);dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():shutil.copy2(src,dst)
    row['ubuntu_sha256']=sha(dst);row['hash_pass']=row['ubuntu_sha256']==row['sha256']
    if not row['hash_pass']:raise RuntimeError('MIGRATION_HASH_DRIFT:'+str(src))
    mapping[row['logical_source']]=str(dst);mapping[row['source'].replace('\\','/')]=str(dst)
    print('input',dst,row['bytes'],flush=True)
with (out/'V42_DATA_MIGRATION_MANIFEST.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
# One explicit path table; no guessed substitute or changed scientific bytes.
cfg=HOME/'mobileess_data/path_map.json';cfg.parent.mkdir(exist_ok=True);cfg.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
local=[]
for row in csv.DictReader((DOC/'WIP_LOCAL_EVIDENCE_MANIFEST.csv').open(encoding='utf-8-sig')):
    src=winpath(row['source']);relative=src.relative_to(WIN);dst=work/relative;dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():shutil.copy2(src,dst)
    actual=sha(dst);assert actual==row['sha256'];local.append(dict(**row,destination=str(dst),ubuntu_sha256=actual,hash_pass=True))
(out/'WIP_LOCAL_EVIDENCE_LINUX.json').write_text(json.dumps(local,ensure_ascii=False,indent=2)+'\n')
(out/'UBUNTU_GIT_STATE.json').write_text(json.dumps(dict(repository=str(repo),PR102=str(work/'pr102'),WIP=str(work/'root_lp_compression'),checkpoint='a88879fdb4e6c51dae35656feee90f68ed19ad8f',bundle_sha256=sha(WIN/'V42_MIGRATION_GIT_ALL.bundle'),worktrees=subprocess.check_output(['git','worktree','list','--porcelain'],cwd=repo,text=True)),indent=2)+'\n')
print('CANONICAL_PREPARED',repo,flush=True)
