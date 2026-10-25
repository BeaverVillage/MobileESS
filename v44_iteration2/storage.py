from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import sys
from .io import atomic,extended

@contextmanager
def install():
 import v44.common as c,v43.common as c43,v42_pr134_b1.common as c42
 originals=(c.atomic,c43.atomic)
 legacy=c42.atomic
 def legacy_atomic(path,value):
  # Lazy Current/Fresh modules import this writer after install(). Preserve
  # its NumPy/nonfinite cleaning and locking while extending temporary paths.
  return legacy(extended(path),value)
 with ExitStack() as stack:
  for module in list(sys.modules.values()):
   if module is None:continue
   for name,value in list(vars(module).items()):
    if value is legacy:stack.enter_context(patch.object(module,name,legacy_atomic))
    elif any(value is original for original in originals):stack.enter_context(patch.object(module,name,atomic))
  yield
