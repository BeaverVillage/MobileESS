from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,os,uuid,time

def now():return datetime.now(timezone.utc).isoformat()
def extended(path):
 p=str(Path(path).absolute())
 return Path(p if os.name!='nt' or p.startswith('\\\\?\\') else '\\\\?\\'+p)
def read(path):return json.loads(extended(path).read_text(encoding='utf-8-sig'))
def optional(path):
 try:return read(path)
 except (OSError,ValueError):return {}
def sha(path):
 with extended(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(path):
 p=Path(path).absolute();return dict(path=str(p),bytes=extended(p).stat().st_size,sha256=sha(p))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def verify(rows):
 for r in rows:
  actual=record(r['path'])
  if (actual['bytes'],actual['sha256'])!=(r['bytes'],r['sha256']):raise ValueError('RECEIPT_DRIFT:'+r['path'])
def atomic(path,value):
 p=extended(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
  for n in range(101):
   try:os.replace(tmp,p);break
   except PermissionError:
    if n==100:raise
    time.sleep(.01)
 finally:tmp.unlink(missing_ok=True)
