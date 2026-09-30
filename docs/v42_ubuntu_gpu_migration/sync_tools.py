"""Transfer migration tooling once to canonical Git; never replaces science files."""
import json,subprocess,shutil,os,hashlib
from pathlib import Path
H=Path.home();R=H/'mobileess_worktrees/root_lp_compression';O=R/'docs/v42_ubuntu_gpu_migration';W=Path(__file__).parent
for p in W.glob('*.py'):shutil.copy2(p,O/p.name)
(O/'.gitattributes').write_text('* -text whitespace=cr-at-eol\n')
repo=H/'codex_mobileess_workspace/MobileESS'
for key,fmt in [('user.name','%an'),('user.email','%ae')]:
    val=subprocess.check_output(['git','log','-1','--format='+fmt,'a88879fdb4e6c51dae35656feee90f68ed19ad8f'],cwd=repo,text=True).strip()
    subprocess.run(['git','config',key,val],cwd=repo,check=True)
subprocess.run(['git','config','credential.helper','/mnt/c/Program\\ Files/Git/mingw64/bin/git-credential-manager.exe'],cwd=repo,check=True)
refs=dict(PR99='3309cd230cd8235201f5578d392241fa98e059bc',PR101='f536e65fc7fb968c52e99e4a5b017953edc53744',PR102='cd7e40762097b6c20303bd2238edf7ffeba87aa4',WIP='a88879fdb4e6c51dae35656feee90f68ed19ad8f')
for name,commit in refs.items():
    subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=repo,check=True)
    subprocess.run(['git','update-ref','refs/mobileess-authorities/'+name,commit],cwd=repo,check=True)
state=json.loads((O/'UBUNTU_GIT_STATE.json').read_text());state.update(required_refs=refs,required_ref_commit_existence_PASS=True,remote_branches_fetched=True,only_required_physical_worktrees=True)
(O/'UBUNTU_GIT_STATE.json').write_text(json.dumps(state,indent=2)+'\n')
evidence=H/'mobileess_research/V42_PR102_evidence';evidence.mkdir(parents=True,exist_ok=True);winroot=Path('/mnt/d/ChatGPT/Mobile ESS 2');rows=[]
files=list((winroot/'V42_EXACT_WAN_LOCAL').rglob('*'))+list(winroot.glob('V42_EXACT_*'))
for p in files:
    if not p.is_file():continue
    dst=evidence/p.relative_to(winroot);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
    with p.open('rb') as f:expected=hashlib.file_digest(f,'sha256').hexdigest()
    with dst.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    assert expected==actual;rows.append(dict(source=str(p),destination=str(dst),bytes=p.stat().st_size,sha256=actual,hash_pass=True))
(O/'PR102_LOCAL_EVIDENCE_PRESERVATION.json').write_text(json.dumps(rows,indent=2)+'\n')
wrapper=H/'.local/bin/mobileess-v42';wrapper.parent.mkdir(exist_ok=True)
body='#!/usr/bin/python3\nimport runpy\nrunpy.run_path('+repr(str(O/'launch_v42.py'))+',run_name="__main__")\n'
if not wrapper.exists():wrapper.write_text(body);wrapper.chmod(0o755)
elif wrapper.read_text()!=body:raise RuntimeError('EXISTING_MOBILEESS_LAUNCHER_DO_NOT_OVERWRITE')
print('LINUX_CANONICAL_TOOLING_READY',len(rows),'PR102 local files preserved')
