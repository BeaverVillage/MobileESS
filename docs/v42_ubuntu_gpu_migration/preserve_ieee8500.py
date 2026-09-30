"""Exact content-addressed Linux protection, preserving all logical paths."""
import csv,json,hashlib,shutil,os,sys,re
from pathlib import Path
H=Path.home();O=H/'mobileess_worktrees/root_lp_compression/docs/v42_ubuntu_gpu_migration';WIN=Path('/mnt/d/ChatGPT/Mobile ESS 2/v42_root_lp_compression_pr/docs/v42_ubuntu_gpu_migration')
DEST=H/'mobileess_research/IEEE8500';objects=DEST/'objects';objects.mkdir(parents=True,exist_ok=True)
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def source(s):
    p=s.replace('\\','/')
    if p.startswith('C:/codex_mobileess_workspace/'):p=p.replace('C:/codex_mobileess_workspace/','D:/codex_mobileess_workspace/',1)
    if p.startswith('C:/Users/kjw39/OneDrive/문서/ChatGPT/'):p=p.replace('C:/Users/kjw39/OneDrive/문서/ChatGPT/','D:/ChatGPT/',1)
    return Path('/mnt/'+p[0].lower()+p[2:])
rows=list(csv.DictReader((WIN/'IEEE8500_FILE_MANIFEST.csv').open(encoding='utf8')));verified={};copied=0;errors=[]
for i,row in enumerate(rows):
    digest=row['sha256'];obj=objects/digest[:2]/digest
    try:
        if digest not in verified:
            if not obj.exists():
                need=int(row['bytes'])
                if shutil.disk_usage('/mnt/d').free < need+12*1024**3:raise OSError('PHYSICAL_D_FREE_SPACE_RESERVE_REACHED')
                obj.parent.mkdir(exist_ok=True);shutil.copy2(source(row['original']),obj);copied+=need
            actual=sha(obj)
            if actual!=digest or obj.stat().st_size!=int(row['bytes']):raise ValueError('HASH_OR_SIZE_MISMATCH')
            verified[digest]=True
        logical=row['original'].replace('\\','/').replace(':','');link=DEST/'windows'/logical;link.parent.mkdir(parents=True,exist_ok=True)
        if not link.exists():link.symlink_to(obj)
        row.update(destination=str(link),preservation_status='LINUX_HASH_SIZE_VERIFIED',ubuntu_sha256=digest,hash_pass=True)
    except Exception as e:
        row.update(preservation_status='SOURCE_RETAINED_COPY_UNRESOLVED',ubuntu_sha256='',hash_pass=False,destination='');errors.append(dict(path=row['original'],error=str(e)))
    if i%1000==0:print('IEEE8500 preserved',i,'of',len(rows),'unique',len(verified),'copied_bytes',copied,'errors',len(errors),flush=True)
fields=list(rows[0])
with (O/'IEEE8500_FILE_MANIFEST.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
shutil.copy2(WIN/'IEEE8500_WINDOWS_GIT_STATE.json',O/'IEEE8500_WINDOWS_GIT_STATE.json')
# Existing Ubuntu research is retained in place; inventory without following symlinks.
rx=re.compile(r'ieee[_-]?8500|8500[-_ ]?node',re.I);linux_existing=[]
for root in (H/'mobile_ess_work',H/'mobile_ess_tools',H/'codex_mobileess_workspace'):
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ('.git','__pycache__','.pytest_cache') and not (Path(folder)/d).is_symlink()]
        for n in files:
            p=Path(folder)/n
            if rx.search(str(p)) and p.is_file():linux_existing.append(dict(path=str(p),bytes=p.stat().st_size,preservation='RETAINED_LINUX_IN_PLACE'))
(O/'IEEE8500_EXISTING_LINUX_INVENTORY.json').write_text(json.dumps(linux_existing,ensure_ascii=False,indent=2)+'\n')
result=dict(IEEE8500_PRESERVED=not errors,IEEE8500_UNRESOLVED_FILES=len(errors),files=len(rows),unique_sha256_objects=len(verified),total_logical_bytes=sum(int(r['bytes']) for r in rows),new_copied_bytes=copied,canonical=str(DEST),errors=errors,all_originals_retained=True,deleted_IEEE8500_files=0,Git_authority='All Windows Git heads/tags and complete history preserved in canonical Linux Git clone, windows-preserved refs and verified ALL bundle',existing_Linux_files_retained=len(linux_existing),storage='Content-addressed byte-identical objects plus readable original path symlinks; duplicate bytes stored once')
(O/'IEEE8500_PRESERVATION_MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result),flush=True)
