"""Classify protected files and preserve each Windows worktree status/diff."""
import csv,json,subprocess,os
from pathlib import Path
O=Path(__file__).absolute().parent
def git(p,*args):
    r=subprocess.run(['git','-C',str(p),*args],capture_output=True,text=True,encoding='utf8',errors='replace')
    return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
rows=list(csv.DictReader((O/'IEEE8500_FILE_MANIFEST.csv').open(encoding='utf8')))
roots={};states={}
for row in rows:
    p=Path(row['original']);folder=p.parent;repo=None
    for ancestor in (folder,*folder.parents):
        if str(ancestor) in roots:repo=roots[str(ancestor)];break
        if (ancestor/'.git').exists():repo=ancestor;break
    roots[str(folder)]=repo
    if repo:
        key=str(repo)
        if key not in states:
            tracked=git(repo,'ls-files')['stdout'].splitlines()
            states[key]=dict(HEAD=git(repo,'rev-parse','HEAD')['stdout'].strip(),branch=git(repo,'branch','--show-current')['stdout'].strip(),status=git(repo,'status','--porcelain=v1')['stdout'],diff=git(repo,'diff')['stdout'],cached_diff=git(repo,'diff','--cached')['stdout'],tracked_files=tracked,unpushed_commits=git(repo,'rev-list','HEAD','--not','--remotes=origin')['stdout'].splitlines())
        relative=p.relative_to(repo).as_posix();row['git_tracked']=relative in states[key]['tracked_files']
    else:row['git_tracked']=False
    row['git_repository']=str(repo) if repo else '';row['git_HEAD']=states[str(repo)]['HEAD'] if repo else ''
with (O/'IEEE8500_FILE_MANIFEST.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(O/'IEEE8500_WINDOWS_GIT_STATE.json').write_text(json.dumps(states,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('IEEE8500 Git states',len(states),'files',len(rows),'local_only',sum(str(x['git_tracked'])=='False' for x in rows),flush=True)
