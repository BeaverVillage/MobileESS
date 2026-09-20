import os,sys,importlib.util
from pathlib import Path
H=Path(__file__).absolute().parent
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
os.environ['TMP']=os.environ['TEMP']=str(H/'tmp')
os.environ['V41_FO_ACCEPTANCE']='1'
import fleet_binding
fleet_binding.install();sys.path.insert(0,str(H))
from headroom_authority import install_power_binding
install_power_binding()
from common8500 import *
install_output_paths()
assert read(H/'PRODUCTION_AUTHORIZATION.json')['authorized']
def protect():
 def canonical(p):
  s=os.fsdecode(p)
  if s.startswith('\\\\?\\'):s=s[4:]
  s=os.path.realpath(os.path.abspath(s))
  if s.startswith('\\\\?\\'):s=s[4:]
  return os.path.normcase(s)
 root=canonical(H)
 def guard(event,args):
  if event=='open':
   p,mode,flags=args
   if isinstance(p,(str,bytes,os.PathLike)) and os.fsdecode(p).lower() in ('nul',r'\\.\nul'):return
   if isinstance(p,(str,bytes,os.PathLike)) and ((mode and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
    target=canonical(p)
    if os.path.commonpath([target,root])!=root:raise PermissionError('FROZEN_SOURCE_WRITE_FORBIDDEN:'+str(p))
 sys.addaudithook(guard)
def clock_binding():
 for name in ['v41r4_search_budget','v41r4_loop_budget']:
  spec=importlib.util.spec_from_file_location(name,H/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
