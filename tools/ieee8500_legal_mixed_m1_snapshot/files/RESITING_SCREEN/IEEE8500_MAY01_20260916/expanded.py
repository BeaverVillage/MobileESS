import optimize as op
from optimize import *
import inspect
op.SLOTS=list(range(68,86))
base_replay=op.replay
def replay_exp(layout,p,folder,mess=None,slots=None):
 return base_replay(layout,p,folder,mess,slots=op.SLOTS if slots is None else slots)
op.replay=replay_exp
src=inspect.getsource(op.capability).replace("/'capability'","/'capability_expanded'")
exec(src,op.__dict__)
if __name__=='__main__':
 rows=[]
 for name in sys.argv[1:]:
  rows.append(op.capability(name));save(H/f'EXPANDED_BATCH_{sys.argv[1]}.json',rows)
