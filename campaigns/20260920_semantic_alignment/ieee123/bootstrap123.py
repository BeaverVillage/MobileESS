import os,sys,json,hashlib
from pathlib import Path
from types import FunctionType
OUT=Path(__file__).absolute().parent
EXT=OUT.parent/'B3_2ROUND_EXTENSION'
SOURCE=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
sys.dont_write_bytecode=True
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='4'
sys.path[:0]=[str(OUT),str(EXT),str(SOURCE)]
import runtime_environment as env
env.seed_aliases()
from authority_recovery import install_validator
install_validator()
# Keep the original read-only source resolver; relocate all writable state.
f=env.SourceFinder.find_spec
env.SourceFinder.find_spec=FunctionType(f.__code__,dict(f.__globals__,ROOT=EXT),f.__name__,f.__defaults__,f.__closure__)
env.ROOT=OUT
env.WRITE_ROOTS=tuple(env.norm(p) for p in (OUT,OUT.resolve()))
env.seed_aliases=lambda:None
env.install('ACTUAL')
from native_runtime_paths import install
install(OUT/'native'/str(os.getpid()))
sys.path.insert(0,str(OUT/'inherited'))
import common
common.OUT=OUT;common.ROOT=SOURCE
common.protect=lambda:None # env write router plus below strict output guard
from common import read,save,sha,arrays,digest
import qsafe
import robust_search
import cached_engine
def protect():
 root=os.path.normcase(os.path.realpath(OUT))
 def hook(event,args):
  if event!='open':return
  p,mode,flags=args
  if not isinstance(p,(str,bytes,os.PathLike)):return
  if not ((mode and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):return
  actual=os.path.normcase(os.path.realpath(os.fsdecode(p)))
  if actual!=os.path.normcase(os.path.realpath('NUL')) and os.path.commonpath([root,actual])!=root:raise PermissionError('NEW_ACTUAL_NAMESPACE_ONLY:'+str(p))
 sys.addaudithook(hook)
protect()
