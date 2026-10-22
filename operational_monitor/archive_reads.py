"""Read missing archived monitor evidence in memory; never restore old folders."""
from pathlib import Path
from contextlib import contextmanager
import os,json,zipfile,hashlib,threading

BASE=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1')
EQUIPMENT=Path('D:/MobileESS_V44/runtime/equipment_versions')
def key(path):return os.path.normcase(os.path.abspath(path))

class ArchivedReads:
 def __init__(self):self.entries={};self.directories=set();self.zips={};self.lock=threading.RLock();self.installed=False
 def refresh(self):
  # Existing 1--14 indexes remain available, too. Load each immutable ZIP once.
  for index in BASE.glob('campaign*/ARCHIVED_RESULTS_*.json'):
   for row in json.loads(index.read_text(encoding='utf-8-sig')).get('days',[]):
    path=row['archive']
    if path in self.zips:continue
    z=zipfile.ZipFile(path);manifest=json.loads(z.read('_ARCHIVE_MANIFEST.json'))
    if (manifest['day'],manifest['source'])!=(row['day'],row['source']):z.close();raise ValueError('MONITOR_ARCHIVE_IDENTITY_DRIFT')
    roots=[Path(os.path.abspath(r)) for r in manifest.get('source_roots',[manifest['source']])]
    if any(r.name!=row['day'] or not (r.is_relative_to(BASE) or r.is_relative_to(EQUIPMENT)) for r in roots):z.close();raise ValueError('MONITOR_ARCHIVE_ROOT_ESCAPE')
    for item in manifest['files']:
     logical=item.get('logical_path')
     if not logical and item['path'].startswith(row['day']+'/'):logical=str(Path(manifest['campaign'])/item['path'])
     if not logical:continue
     p=Path(os.path.abspath(logical))
     if not any(p.is_relative_to(r) for r in roots):z.close();raise ValueError('MONITOR_ARCHIVE_MEMBER_ESCAPE')
     self.entries[key(p)]=(z,item)
     # Thousands of files share each directory; expand its parents only once.
     if key(p.parent) not in self.directories:
      for parent in p.parents:
       if parent in (BASE,EQUIPMENT):break
       self.directories.add(key(parent))
    self.zips[path]=z
 def bytes(self,path):
  z,item=self.entries[key(path)]
  with self.lock:raw=z.read(item['path'])
  if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('MONITOR_ARCHIVE_FILE_SHA_DRIFT:'+str(path))
  return raw
 @contextmanager
 def scope(self):
  from unittest.mock import patch
  read_bytes,read_text,exists,is_file,is_dir=Path.read_bytes,Path.read_text,Path.exists,Path.is_file,Path.is_dir
  def rb(p):
   try:return read_bytes(p)
   except FileNotFoundError:
    if key(p) in self.entries:return self.bytes(p)
    raise
  def rt(p,encoding=None,errors=None):
   try:return read_text(p,encoding=encoding,errors=errors)
   except FileNotFoundError:
    if key(p) in self.entries:return self.bytes(p).decode(encoding or 'utf8',errors or 'strict')
    raise
  with patch.object(Path,'read_bytes',rb),patch.object(Path,'read_text',rt),patch.object(Path,'exists',lambda p:exists(p) or key(p) in self.entries or key(p) in self.directories),patch.object(Path,'is_file',lambda p:is_file(p) or key(p) in self.entries),patch.object(Path,'is_dir',lambda p:is_dir(p) or key(p) in self.directories):yield
 def close(self):
  for z in self.zips.values():z.close()

reader=ArchivedReads()
