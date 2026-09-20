"""Fresh chronological 96-slot B0 gate. No proxy schedules or control states reused."""
import os,sys,json,time,hashlib,traceback
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent;ROOT=H.parent.parent
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
(H/'tmp').mkdir(exist_ok=True)
os.environ['TMP']=os.environ['TEMP']=str(H/'tmp')
OLD=ROOT/'RESITING_SCREEN/IEEE8500_MAY01_20260916'
sys.path.insert(0,str(OLD))
from engine import ResiteEngine,BASE_P,BASE_Q,save,table,read,s,np
def main():
 import psutil
 layout=read(OLD/'placements/legal_mixed_M1/LAYOUT.json')
 save(H/'LAYOUT.json',layout)
 save(H/'RUN_CONTRACT.json',dict(date='2025-05-01',candidate='legal_mixed_M1',workers=1,Gurobi_Threads=4,s_DC=1.,s_MESS=1.,background_alpha=.574,PV_alpha=.50,policies=['B0','B1','B2','B3'],Fresh=True,Actual=False,placement_reselection=False,proxy_reuse=False,transport_changes=False,spatial_audit='SUPERSEDED_NONBLOCKING_DIAGNOSTIC',spatial_correlation_required=False))
 save(H/'RESOURCE_PREFLIGHT.json',dict(cpu_logical=psutil.cpu_count(),cpu_percent=psutil.cpu_percent(1),memory=psutil.virtual_memory()._asdict(),existing_processes=[p.info for p in psutil.process_iter(['pid','ppid','name','cmdline']) if 'python' in (p.info['name'] or '').lower()],Gurobi_concurrent_4_thread_probe='PASS under licensed user kjw39'))
 for stage in ['B0_DA','B0_FRESH']:
  out=H/stage;start=time.perf_counter();e=ResiteEngine(layout,out/'runtime');rows=[];states=[]
  save(H/'STATUS.json',dict(status='RUNNING',stage=stage,pid=os.getpid(),slots=0))
  try:
   for t in range(96):
    e.inputs(t,BASE_P,BASE_Q);r,a=e.measure(t);rows.append(r)
    states.append(s.control_state(e.d,t,e.rule['source_pu'],e.rule['Vreg_V']))
    if t%12==11:save(H/'STATUS.json',dict(status='RUNNING',stage=stage,pid=os.getpid(),slots=t+1));print(stage,t+1,flush=True)
  finally:e.close()
  keys=['max_phase_line_loading_pu','Vmin_pu','Vmax_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu']
  result={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in keys}
  result.update(status='PASS' if all(r['physical_pass'] for r in rows) else 'FAIL',slots=96,converged_slots=sum(bool(r['converged']) for r in rows),runtime_seconds=time.perf_counter()-start,critical_slot=max(rows,key=lambda r:r[keys[0]])['slot'],critical_witness=max(rows,key=lambda r:r[keys[0]])['line_witness'])
  table(out/'SLOTS.csv',rows);save(out/'CONTROL_STATES.json',states);save(out/'SUMMARY.json',result);print(stage,json.dumps(result),flush=True)
 save(H/'STATUS.json',dict(status='B0_COMPLETE',pid=os.getpid(),next_stage='PRODUCTION_ADAPTER_PREFLIGHT'))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'STATUS.json',dict(status='FAILED',error=repr(e),traceback=traceback.format_exc()));raise
