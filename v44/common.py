from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import uuid

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/v44'
RUNTIME=Path('D:/MobileESS_V44/runtime')
V43_ROOT=Path('D:/v43_pr189_fast_planning_20261016')
V43_COMMIT='5fed802db447a1f4b4e7fd556e4f5009b6bcee0d'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def now():return datetime.now(timezone.utc).isoformat()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def record(path):
    p=Path(path).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def verify(rows):
    for r in rows:
        actual=record(r['path'])
        if any(actual[k]!=r[k] for k in ('bytes','sha256')):raise ValueError('SOURCE_SHA_DRIFT:'+r['path'])
def atomic(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    try:tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');os.replace(tmp,p)
    finally:tmp.unlink(missing_ok=True)


class NotReady(RuntimeError):pass
