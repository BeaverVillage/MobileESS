import unittest,tempfile,marshal
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from v44_iteration2 import config as c,adapters,storage
from v44_iteration2.io import read,extended


class LiveFailures(unittest.TestCase):
 def test_restoration_accepts_exact_live_cap300_and_fresh900_wrappers(self):
  from v44_iteration2.bootstrap import CORE_RESTORE
  from v44 import m_restore,cap300,fresh900
  already=cap300.restore_adapter(CORE_RESTORE)
  self.assertIs(adapters.routed_restore(already),already)
  # Enter the same inherited wrapper scope as the original worker. Validation
  # is isolated to this fixture; the real cap300 transform remains unchanged.
  with patch.object(fresh900,'validate',return_value={'fresh_policy_sha':'fixture'}),patch.object(cap300,'validate',return_value={'operational_overlay':{},'execution_policy_sha':'fixture'}):
   with fresh900.install():
    wrapped=m_restore.restore
    self.assertIs(adapters.routed_restore(wrapped),wrapped)
  self.assertIs(m_restore.restore,CORE_RESTORE)

 def test_unknown_restore_wrapper_is_rejected_instead_of_disabling_guard(self):
  def restore(*args,**kwargs):return None
  with self.assertRaisesRegex(ValueError,'SOURCE_BOUNDARY_DRIFT'):adapters.routed_restore(restore)

 def test_lazy_legacy_atomic_keeps_cleaning_and_writes_long_temp_path(self):
  import v42_pr134_b1.common as legacy
  original=legacy.atomic
  with tempfile.TemporaryDirectory(dir=extended(c.ROOT)) as folder:
   output=Path(folder)
   while len(str(output))<240:output=output/'long_current_ac_reference'
   path=output/'SOURCE_INITIAL_CONTROL_REFERENCE.json'
   self.assertGreater(len(str(path))+50,300)
   with storage.install():
    # This import represents an alias captured by a lazily imported AC module.
    from v42_pr134_b1.common import atomic as lazy_atomic
    self.assertIsNot(lazy_atomic,original)
    lazy_atomic(path,dict(array=np.array([1,2]),nonfinite=float('inf')))
   self.assertIs(legacy.atomic,original)
   self.assertEqual(read(path),dict(array=[1,2],nonfinite='inf'))
   self.assertFalse(list(extended(output).glob('*.tmp')))

 def test_owned_long_numpy_files_use_same_scoped_io_with_original_archive_guards(self):
  from v44_iteration2.archives import Store
  with tempfile.TemporaryDirectory(dir=extended(c.ROOT)) as folder:
   output=Path(str(folder).removeprefix('\\\\?\\'))
   while len(str(output))<240:output=output/'current_ac_prefix_proof'
   extended(output).mkdir(parents=True)
   path=output/'COMPLETE_CURRENT_PHYSICAL_ARRAYS.npz';store=Store(days=())
   try:
    with store.read_scope():
     np.savez_compressed(path,X=np.arange(10))
     self.assertGreater(path.stat().st_size,0)
     with np.load(path,allow_pickle=False) as arrays:np.testing.assert_array_equal(arrays['X'],np.arange(10))
   finally:store.close()


if __name__=='__main__':unittest.main()
