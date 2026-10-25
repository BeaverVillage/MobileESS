import unittest,tempfile,zipfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
from archive_reads import ArchivedReads,key

class ArchivedEvidence(unittest.TestCase):
 def test_missing_reads_are_verified_without_restoring_or_redirecting_writes(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);logical=root/'old/RESULT.json';raw=b'{"PASS":true}';archive=root/'daily.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('result',raw)
   reader=ArchivedReads();z=zipfile.ZipFile(archive);reader.zips[str(archive)]=z;reader.entries[key(logical)]=(z,dict(path='result',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()));reader.directories.add(key(logical.parent))
   try:
    with reader.scope():
     self.assertTrue(logical.exists());self.assertTrue(logical.is_file());self.assertTrue(logical.parent.is_dir());self.assertEqual(json.loads(logical.read_text()),dict(PASS=True));self.assertEqual(logical.read_bytes(),raw)
    self.assertFalse(logical.exists());self.assertFalse(logical.parent.exists())
    reader.entries[key(logical)][1]['sha256']='incorrect'
    with reader.scope():
     with self.assertRaisesRegex(ValueError,'SHA_DRIFT'):logical.read_bytes()
   finally:reader.close()
