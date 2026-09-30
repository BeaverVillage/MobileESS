"""Once-per-path resumable SHA scan of located research roots, no blind disk scan."""
import os,csv,stat,json,re,hashlib
from pathlib import Path
O=Path(__file__).absolute().parent;rx=re.compile(r'ieee[_-]?8500|8500[-_ ]?node',re.I)
rows=list(csv.DictReader((O/'WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv').open(encoding='utf8')))
roots=[]
for r in sorted(rows,key=lambda r:len(r['path'])):
    p=r['path']
    if r['type']=='REPARSE_POINT':continue
    if not any(p.lower().startswith(x.lower().rstrip('\\')+'\\') for x in roots):roots.append(p)
out=O/'IEEE8500_FILE_MANIFEST.csv';done=set()
if out.exists():done={r['original'] for r in csv.DictReader(out.open(encoding='utf8'))}
errors=[];n=len(done);total=0
with out.open('a',encoding='utf8',newline='') as stream:
    fields=['original','bytes','sha256','git_tracked','destination','preservation_status'];writer=csv.DictWriter(stream,fieldnames=fields)
    if not done:writer.writeheader()
    for root in roots:
        for folder,dirs,files in os.walk(root,followlinks=False):
            keep=[]
            for d in dirs:
                p=os.path.join(folder,d)
                if d in ('.git','__pycache__','.pytest_cache'):continue
                try:
                    if os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        try:target=os.readlink(p)
                        except ValueError:target=None # Cloud metadata is not a directory link.
                        if target is not None:continue
                    keep.append(d)
                except OSError as e:errors.append(dict(path=p,error=str(e)))
            dirs[:]=keep
            for name in files:
                fp=os.path.join(folder,name)
                if not rx.search(fp) or fp in done or name=='.git':continue
                try:
                    size=os.stat(fp).st_size
                    with open(fp,'rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
                    writer.writerow(dict(original=fp,bytes=size,sha256=digest,git_tracked='PENDING_GIT_AUTHORITY_AUDIT',destination='',preservation_status='SOURCE_RETAINED_PENDING_LINUX_COPY'));done.add(fp);n+=1;total+=size
                    if n%500==0:stream.flush();print('IEEE_SHA_PROGRESS',n,total,fp,flush=True)
                except OSError as e:errors.append(dict(path=fp,error=str(e)))
        stream.flush();print('IEEE_ROOT_COMPLETE',root,n,total,flush=True)
(O/'IEEE8500_WINDOWS_SCAN_RECEIPT.json').write_text(json.dumps(dict(roots=roots,files=n,hashed_bytes_this_run=total,errors=errors,source_mutations=0),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('IEEE_WINDOWS_SHA_COMPLETE',n,total,'errors',len(errors),flush=True)
