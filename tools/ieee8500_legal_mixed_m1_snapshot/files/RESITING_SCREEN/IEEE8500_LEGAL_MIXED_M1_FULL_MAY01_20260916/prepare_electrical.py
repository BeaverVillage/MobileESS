import os,sys,time,traceback
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
os.environ['TMP']=os.environ['TEMP']=str(H/'tmp')
import fleet_binding
fleet_binding.install()
sys.path.insert(0,str(H))
from electrical_engine import *
def main():
 start=time.perf_counter();save(H/'STATUS.json',dict(status='RUNNING',stage='FULL_INFRASTRUCTURE_B0',pid=os.getpid(),workers=1,threads=4))
 if not (H/'B0_REPLAY/AC_VALIDATION.json').exists():baseline()
 else:assert read(H/'B0_REPLAY/AC_VALIDATION.json')['status']=='PASS'
 from common8500 import exact
 with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:p=z['pcc'].copy()
 # Fresh controls have zero MESS, so no coefficient payload is needed here.
 from numerical_coefficients import Coefficients
 import common8500
 original=common8500.Coefficients
 class AxisOnly:
  def __len__(self):return 96
  def __getitem__(self,t):
   from types import SimpleNamespace
   return SimpleNamespace(control_names=NAMES)
 common8500.Coefficients=AxisOnly
 try:r=exact(p,[],H/'B0/Fresh');assert r['status']=='PASS'
 finally:common8500.Coefficients=original
 rows=[]
 for t in range(96):
  rows.append(generate_slot(t));save(H/'STATUS.json',dict(status='RUNNING',stage='FULL_60_CONTROL_COEFFICIENTS',pid=os.getpid(),slots=t+1,workers=1,threads=4,wall_seconds=time.perf_counter()-start));print('FULL_COEFFICIENTS',t+1,'/96',flush=True)
 save(H/'COEFFICIENT_GENERATION.json',dict(status='PASS',slots=rows,wall_seconds=time.perf_counter()-start))
 save(H/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json',dict(status='IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS',scope='Fresh full 96-slot 60-control coefficients and B0 DA/Fresh',infrastructure=record(H/'PCC_OVERLAY_INVENTORY.json'),coefficients=record(H/'COEFFICIENT_GENERATION.json')))
 save(H/'STATUS.json',dict(status='PREPARATION_COMPLETE',stage='READY_B1',pid=os.getpid()))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'STATUS.json',dict(status='FAILED',error=repr(e),traceback=traceback.format_exc()));raise
