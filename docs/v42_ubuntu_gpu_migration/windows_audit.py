"""Read-only targeted inventory. Never follows reparse points or deletes files."""
import os,re,json,csv,hashlib,subprocess,stat
from pathlib import Path
HERE=Path(__file__).absolute().parent
ROOT=HERE.parents[1]
def git(p,*args):
    r=subprocess.run(['git','-C',str(p),*args],capture_output=True,text=True,encoding='utf8',errors='replace')
    return r.stdout.strip() if r.returncode==0 else ''
def dump(n,v): (HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def table(n,rows,fields=None):
    with (HERE/n).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
rx=re.compile(r'ieee[_-]?8500|8500[-_ ]?node',re.I)
match=re.compile(r'mobile.?ess|codex_mobileess|gurobi|ieee123|ieee[_-]?8500|8500[-_ ]?node|_v(?:35|36|40|41|42)|frozen_artifacts',re.I)
bases=[Path('C:/'),Path('D:/'),Path('D:/ChatGPT'),Path('C:/Users/kjw39'),Path('C:/Users/kjw39/OneDrive/문서/ChatGPT')]
candidates=set()
for base in bases:
    if base.exists():
        for p in base.iterdir():
            if p.is_dir() and match.search(p.name):candidates.add(str(p))
for base in [Path('D:/ChatGPT/Mobile ESS 2'),Path('D:/codex_mobileess_workspace')]:
    for p in base.iterdir():
        if p.is_dir():candidates.add(str(p))
        if p.is_dir() and p.name in ('pr_workspaces','independent_screening'):
            candidates.update(str(x) for x in p.iterdir() if x.is_dir())
rows=list(csv.DictReader((HERE/'WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv').open(encoding='utf8'))) if (HERE/'WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv').exists() else []
done={r['path'] for r in rows};ieee=[];links=[];errors=[]
if (HERE/'WINDOWS_PATH_LINKS.json').exists():
    previous=json.loads((HERE/'WINDOWS_PATH_LINKS.json').read_text());links=previous['links'];errors=previous['errors']
for s in sorted(candidates):
    if s in done:continue
    p=Path(s);reparse=bool(p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    total=0;count=0;found=False
    if reparse:
        try:target=os.readlink(s)
        except ValueError:target='NON_LINK_REPARSE_METADATA_DO_NOT_DELETE'
        links.append(dict(path=s,target=target));kind='REPARSE_POINT';role='UNKNOWN_DO_NOT_DELETE'
    else:
        kind='DIRECTORY'
        for folder,dirs,files in os.walk(s,followlinks=False):
            kept=[]
            for d in dirs:
                dp=os.path.join(folder,d)
                try:
                    if os.lstat(dp).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        try:target=os.readlink(dp)
                        except ValueError:target='NON_LINK_REPARSE_METADATA_DO_NOT_DELETE'
                        links.append(dict(path=dp,target=target))
                    else:kept.append(d)
                except OSError as e:errors.append(dict(path=dp,error=str(e)))
            dirs[:]=kept
            for name in files:
                fp=os.path.join(folder,name)
                try:
                    size=os.stat(fp).st_size;total+=size;count+=1
                    if rx.search(fp):found=True
                except OSError as e:errors.append(dict(path=fp,error=str(e)))
        role='KEEP_IEEE8500' if found else ('KEEP_CURRENT_WIP' if s==str(ROOT) or 'V42_ROOT' in s else ('KEEP_RAW_AUTHORITY' if 'frozen' in s.lower() else 'UNKNOWN_DO_NOT_DELETE'))
    repo=(p/'.git').exists();head=git(p,'rev-parse','HEAD') if repo else '';branch=git(p,'branch','--show-current') if repo else ''
    status=git(p,'status','--porcelain=v1') if repo else ''
    tracked=git(p,'ls-files').splitlines() if repo else []
    rows.append(dict(path=s,type=kind,total_bytes=total,file_count=count,git_repository=repo,worktree=repo and (p/'.git').is_file(),branch=branch,HEAD=head,clean_dirty=('DIRTY' if status else 'CLEAN') if repo else 'NOT_GIT',tracked_estimate=len(tracked),untracked_estimate=sum(x.startswith('??') for x in status.splitlines()),candidate_role=role,classification=role,byte_scope='non-following recursive; overlapping parents are not additive'))
    print('inventory',s,total,count,role,flush=True)
    table('WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv',rows)
dump('WINDOWS_PATH_LINKS.json',dict(links=links,errors=errors))
dump('WINDOWS_IEEE8500_REFS.json',dict(branches=git(ROOT,'branch','-a'),tags=git(ROOT,'tag'),worktrees=git(ROOT,'worktree','list','--porcelain'),file_manifest='Dedicated once-per-path streaming scan'))
dump('CURRENT_WIP_CHECKPOINT.json',dict(branch=git(ROOT,'branch','--show-current'),checkpoint='a88879fdb4e6c51dae35656feee90f68ed19ad8f',remote_verified=True,source_worktree=str(ROOT),scientific_work_paused=True,unfinished='No selected full formulation; no fully validated MIP start; no A1',local_evidence='WIP_LOCAL_EVIDENCE_MANIFEST.csv'))
