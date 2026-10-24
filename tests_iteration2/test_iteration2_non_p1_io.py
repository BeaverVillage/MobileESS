import unittest,tempfile,json,zipfile,hashlib,threading,time
from pathlib import Path
from unittest.mock import patch
from v44_iteration2 import config as c,archives,performance
from v44_iteration2.io import atomic

class NonP1IO(unittest.TestCase):
 def fixture(self,folder):
  root=Path(folder);old=root/'old';camp=old/'campaign004';camp.mkdir(parents=True)
  rows=[]
  for day in ('2025-05-01','2025-05-02'):
   (camp/day).mkdir()
   raw=b'{"PASS":true}\n';member=day+'/B3/attempt001/RESULT.json';zpath=root/(day+'.zip')
   manifest=dict(day=day,source=str(camp/day),campaign=str(camp),files=[dict(path=member,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())])
   with zipfile.ZipFile(zpath,'w') as z:
    z.writestr(member,raw);z.writestr('_ARCHIVE_MANIFEST.json',json.dumps(manifest))
   rows.append(dict(day=day,source=str(camp/day),archive=str(zpath)))
  atomic(camp/'ARCHIVED_RESULTS_FIXTURE.json',dict(days=rows));(root/'new').mkdir()
  return root,old,camp
 def test_single_date_index_keeps_all_original_campaign_write_guards(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root,old,camp=self.fixture(d)
   with patch.object(c,'OLD',old),patch.object(c,'ROOT',root/'new'),patch.object(c,'campaign',lambda day:camp):
    store=archives.Store(days=('2025-05-01',))
    try:
     self.assertEqual(list(store.zips),['2025-05-01'])
     with store.read_scope():
      self.assertEqual(store.read(camp/'2025-05-01/B3/attempt001/RESULT.json'),dict(PASS=True))
      with self.assertRaises(PermissionError):(camp/'2025-05-02/forbidden.json').write_text('x')
    finally:store.close()
 def test_metadata_does_not_rehash_but_every_read_still_rejects_changed_bytes(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root,old,camp=self.fixture(d)
   with patch.object(c,'OLD',old),patch.object(c,'ROOT',root/'new'),patch.object(c,'campaign',lambda day:camp):
    store=archives.Store(days=('2025-05-01',));logical=camp/'2025-05-01/B3/attempt001/RESULT.json'
    try:
     target=store.materialize(logical);calls=[];original=archives.record
     def counted(path):calls.append(path);return original(path)
     with patch.object(archives,'record',counted),store.read_scope():
      for _ in range(4):self.assertTrue(logical.is_file());logical.stat()
      self.assertEqual(calls,[])
      self.assertEqual(json.loads(logical.read_text()),dict(PASS=True));self.assertTrue(calls)
      target.write_bytes(b'{"PASS":false}')
      with self.assertRaisesRegex(ValueError,'VIEW_DRIFT'):logical.read_text()
    finally:store.close()
 def test_materialization_never_temporarily_disables_guards_for_other_threads(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as d:
   root,old,camp=self.fixture(d);entered=threading.Event();release=threading.Event();errors=[]
   with patch.object(c,'OLD',old),patch.object(c,'ROOT',root/'new'),patch.object(c,'campaign',lambda day:camp):
    store=archives.Store(days=('2025-05-01',));logical=camp/'2025-05-01/B3/attempt001/RESULT.json';original=store.materialize
    def paused(path):entered.set();release.wait(5);return original(path)
    def reader():
     try:logical.read_text()
     except BaseException as e:errors.append(e)
    try:
     with patch.object(store,'materialize',paused),store.read_scope():
      t=threading.Thread(target=reader);t.start()
      try:
       self.assertTrue(entered.wait(3))
       with self.assertRaises(PermissionError):(camp/'2025-05-02/forbidden.json').write_text('x')
      finally:release.set();t.join(5)
      self.assertFalse(t.is_alive());self.assertEqual(errors,[])
    finally:store.close()
 def test_full_domain_dict_and_tuple_use_bounded_C_chunks_with_original_SHA(self):
  values=[{'blocks':tuple((i,[i,-0.,'한글']) for i in range(10001)),'stays':[(1,2)],'job':{'a':1}},
   {1:[1,2],2:[]},(),{'é':'a','a':0}]
  for value in values:
   expected=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()).hexdigest()
   original=json.JSONEncoder.iterencode
   def only_C(encoder,obj,_one_shot=False):
    self.assertTrue(_one_shot,'PYTHON_SCALAR_WALK_FORBIDDEN');return original(encoder,obj,_one_shot)
   with patch.object(json.JSONEncoder,'iterencode',only_C):
    self.assertEqual(performance.streaming_domain_digest(value),expected)
  with self.assertRaises(ValueError):performance.streaming_domain_digest({'blocks':[float('nan')]})

if __name__=='__main__':unittest.main()
