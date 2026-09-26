from bootstrap import *
from aligned_mess import bounded_child
import traceback
if __name__=='__main__':
 protect()
 try:bounded_child(sys.argv[1])
 except BaseException as e:
  save(P/'BOUNDED_CHILD_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
  raise
