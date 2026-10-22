"""Read archived originals without restoring anything into an old campaign."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import builtins,io,os,zipfile,json,hashlib,shutil,threading
from . import config as c
from .io import read,record,atomic,extended

def key(path):
 value=str(Path(path))
 if value.startswith('\\\\?\\'):value=value[4:]
 return os.path.normcase(value)

class Store:
 def __init__(self):
  self.archives=[];self.zips={};self.entries={};self._lock=threading.RLock()
  indexes=[c.OLD/n/'ARCHIVED_RESULTS_20250501_14.json' for n in ('campaign004','campaign005_may08_14')]
  for p in indexes:
   if not p.exists():continue
   for row in read(p)['days']:
    if row['day'] in self.zips:continue
    if not Path(row['archive']).is_file():raise FileNotFoundError(row['archive'])
    z=zipfile.ZipFile(row['archive']);manifest=json.loads(z.read('_ARCHIVE_MANIFEST.json'))
    if manifest['day']!=row['day'] or manifest['source']!=row['source']:raise ValueError('ARCHIVE_DATE_ROOT_DRIFT')
    self.archives.append(row);self.zips[row['day']]=z
    camp=Path(manifest['campaign'])
    for item in manifest['files']:
     if item['path'].startswith(row['day']+'/'):
      logical=camp/Path(item['path']);self.entries[key(logical)]=(row,z,item)
 def close(self):
  for z in self.zips.values():z.close()
 def paths(self,day,suffix):
  prefix=str(c.campaign(day)/day/'B3')
  values=[Path(k) for k in self.entries if k.startswith(os.path.normcase(prefix)) and k.endswith(os.path.normcase(suffix))]
  values+=list((c.campaign(day)/day/'B3').glob('attempt*/'+suffix.lstrip('/')))
  return sorted(set(values))
 def bytes(self,path):
  p=Path(path);entry=self.entries.get(key(p))
  if entry:
   row,z,item=entry;raw=z.read(item['path'])
   if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ARCHIVED_FILE_SHA_DRIFT:'+str(p))
   return raw
  return extended(p).read_bytes()
 def read(self,path):return json.loads(self.bytes(path).decode('utf-8-sig'))
 def record(self,path):
  raw=self.bytes(path);return dict(path=str(Path(path)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 def exists(self,path):return key(path) in self.entries or Path(path).exists()
 def materialize(self,path):
  entry=self.entries.get(key(path))
  if not entry:return Path(path)
  row,z,item=entry;target=c.ROOT/'BASELINE_READONLY'/Path(row['source']).parent.name/Path(item['path'])
  if not target.resolve().is_relative_to((c.ROOT/'BASELINE_READONLY').resolve()):raise ValueError('ARCHIVE_PATH_ESCAPE')
  with self._lock:
   if not extended(target).is_file():
    if shutil.disk_usage(c.ROOT).free<item['bytes']+2*2**30:raise OSError('INSUFFICIENT_ARCHIVE_VIEW_DISK')
    extended(target).parent.mkdir(parents=True,exist_ok=True)
    tmp=extended(target).with_name(target.name+'.extracting')
    h=hashlib.sha256();size=0
    try:
     with z.open(item['path']) as source,tmp.open('wb') as output:
      for chunk in iter(lambda:source.read(8*2**20),b''):
       output.write(chunk);h.update(chunk);size+=len(chunk)
     if size!=item['bytes'] or h.hexdigest()!=item['sha256']:raise ValueError('ARCHIVED_FILE_SHA_DRIFT:'+str(path))
     os.replace(tmp,extended(target))
    finally:tmp.unlink(missing_ok=True)
   actual=record(target)
   if (actual['bytes'],actual['sha256'])!=(item['bytes'],item['sha256']):raise ValueError('OWNED_ARCHIVE_VIEW_DRIFT')
  return extended(target)

 @contextmanager
 def read_scope(self):
  """Original receipt paths retain their identity; only missing read IO moves.

  Never redirects writes and never supplies a file with different bytes.
  In production, materialization occurs only after the B2 release gate.
  """
  original_open=builtins.open;original_io=io.open;original_stat=os.stat
  roots=tuple(str(c.campaign(d)).casefold() for d in c.DAYS)
  def mapped(path,mode='r'):
   if isinstance(path,int):return path
   p=Path(path)
   normalized=key(p)
   if any(normalized.startswith(r+os.sep) for r in roots) and any(x in str(mode) for x in ('w','a','x','+')):raise PermissionError('ORIGINAL_CAMPAIGN_WRITE_FORBIDDEN:'+str(p))
   if normalized in self.entries:return self.materialize(p)
   return path
  def opened(path,mode='r',*a,**kw):return original_open(mapped(path,mode),mode,*a,**kw)
  def io_opened(path,mode='r',*a,**kw):return original_io(mapped(path,mode),mode,*a,**kw)
  def stat(path,*a,**kw):
   if not isinstance(path,int) and key(path) in self.entries:
    return original_stat(self.materialize(path),*a,**kw)
   return original_stat(path,*a,**kw)
  # materialize uses saved raw IO, avoiding recursive alias callbacks.
  saved=self.materialize
  def materialize(path):
   with patch.object(builtins,'open',original_open),patch.object(io,'open',original_io),patch.object(os,'stat',original_stat):return saved(path)
  with patch.object(self,'materialize',materialize),patch.object(builtins,'open',opened),patch.object(io,'open',io_opened),patch.object(os,'stat',stat):yield
