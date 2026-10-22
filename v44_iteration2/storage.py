from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import sys
from .io import atomic

@contextmanager
def install():
 import v44.common as c,v43.common as c43
 originals=(c.atomic,c43.atomic)
 with ExitStack() as stack:
  for module in list(sys.modules.values()):
   if module is None:continue
   for name,value in list(vars(module).items()):
    if any(value is original for original in originals):stack.enter_context(patch.object(module,name,atomic))
  yield
