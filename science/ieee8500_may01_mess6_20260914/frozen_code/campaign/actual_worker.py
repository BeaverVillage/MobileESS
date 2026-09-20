"""Original Actual/QSAFE robust V2, six vehicles and current May01 authority."""
import os,sys
from pathlib import Path
sys.dont_write_bytecode=True
POLICY=sys.argv[1];assert POLICY in ('B2','B3')
BASE=Path(__file__).absolute().parent
import fleet_binding
fleet_binding.install();sys.path.insert(0,str(BASE))
from headroom_authority import install_power_binding
install_power_binding()
source_adapter=BASE.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913/validate_actual.py'
text=source_adapter.read_text(encoding='utf-8').split('\ndef selected():',1)[0]
text=text.replace("H=BASE/'actual'","H=BASE/('actual_'+POLICY)")
exec(compile(text,str(source_adapter)+'::six_MESS','exec'),globals())
import actual_binding as binding
binding.install_actual()
def selected():
 final=read(BASE/POLICY/'FINAL_AUTHORITY.json');assert final['status']=='PASS'
 jobs=read(BASE/'REFERENCE_JOBS.json') if POLICY=='B2' else final['jobs']
 commands=final['trajectory_slots'];assert len(commands)==576
 return {POLICY:(jobs,commands)}
def verify():
 for r in read(H/'RULE_FREEZE.json')['source_files']:assert sha(r['path'])==r['sha256'],r['path']
def main():
 assert not H.exists();H.mkdir()
 (H/'BATTERY_EFFICIENCY_AUTHORITY.json').write_bytes((METHOD/'BATTERY_EFFICIENCY_AUTHORITY.json').read_bytes())
 files=[Path(__file__),BASE/'actual_binding.py',BASE/'availability_gating.py',BASE/'fleet_binding.py',BASE/'FLEET_AUTHORITY.json',BASE/'HEADROOM_AUTHORITY.json',BASE/'AIDC_2X_AUTHORITY.json',BASE/'MAPPING_FREEZE.json',BASE/'electrical_engine.py',BASE/'PCC_Master.dss',BASE/'D1_AEMO_VIC1_FORECAST.json',BASE/POLICY/'FINAL_AUTHORITY.json',source_adapter,METHOD/'robust_search.py',METHOD/'frozen_code/qsafe.py']
 save(H/'RULE_FREEZE.json',dict(status='FROZEN_BEFORE_ACTUAL',date=DAY,policy=POLICY,fleet=6,initial=fleet_binding.INITIAL,source_files=[rec(p) for p in files],mobility='final arrival-based departure; connection-ready electrical P/Q; unchanged DA clock; missed commands; physical-connection QSAFE',QSAFE='unchanged robust V2',production_optimizer_calls=0))
 ns=kernel();ns['independent_audit']=binding.independent_audit
 import gurobipy as gp
 gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DA_OPTIMIZATION_FORBIDDEN_IN_ACTUAL'))
 verify();protect();authority=inputs(ns)
 assert(H/POLICY/'INPUT_READY.json').exists()
 run_policy(POLICY,ns,authority);verify()
 # Physical AIDC audit remains the uniform image of the normalized dispatcher.
 events=pd.read_parquet(H/POLICY/'aidc/RESOURCE_CHANGE_EVENTS.parquet');physical=events.copy()
 for col in ['GPU_delta','GPU_occupancy_before','GPU_occupancy_after','GPU_capacity','rack_single_gang_capacity']:physical[col]=2*physical[col]
 assert ((physical.GPU_occupancy_after>=0)&(physical.GPU_occupancy_after<=physical.GPU_capacity)).all()
 physical.to_parquet(H/POLICY/'aidc/PHYSICAL_2X_RESOURCE_CHANGE_EVENTS.parquet',index=False)
 save(H/'COMPLETE.json',dict(status='COMPLETE',date=DAY,policy=POLICY,source_preservation='PASS',result=rec(H/POLICY/'COMPLETE.json'),new_scheduling_optimizer_calls=0))
if __name__=='__main__':
 try:main()
 except BaseException as e:
  H.mkdir(exist_ok=True);save(H/'FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
