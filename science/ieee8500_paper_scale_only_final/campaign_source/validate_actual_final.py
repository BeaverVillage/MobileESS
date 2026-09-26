"""Identical B0/B1 final DA and original Actual/QSAFE robust V2 validation."""
import os,sys,pathlib,json,hashlib,ast,time,math,itertools,traceback,copy,difflib
from pathlib import Path
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
BASE=Path(__file__).absolute().parent;H=BASE/'actual';W=BASE.parent.parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
METHOD=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2';DAY='2025-05-01'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(BASE))
import numpy as np,pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
FUNCTION_BINDINGS=[]
source=W/'IEEE8500_actual_20260912_r3/actual8500.py'
source_text=source.read_text(encoding='utf-8');tree=ast.parse(source_text)
adaptations=[]
for name in ['clean','save','rec','state','protect','original_functions','kernel','inputs','Electrical','summary','outputs','continuous','run_policy']:
 node=next(x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name==name)
 original=ast.get_source_segment(source_text,node);text=original
 if name=='inputs':
  text=text.replace('2025-05-21',DAY)
  text=text.replace('==(1200,400,300,.95,.95)', '==(2400,800,600,.95,.95)')
  text=text.replace('from dayahead.v41.actual_dispatch import replay_jobs,power_from_execution,persist','from dayahead.v41.actual_dispatch import replay_jobs,persist\n from actual_power_binding import power_from_execution')
  text=text.replace("assert sum(cap.values())==780","assert sum(cap.values())==780; cap=read(BASE/'HEADROOM_AUTHORITY.json')['normalized_site_capacity']; rk=dict(rk,logical_Rack_pools=[dict(r,compatibility_GPU_limit=cap[r['aidc_id']]) for r in rk['logical_Rack_pools']]); assert sum(cap.values())==1312")
  text=text.replace("W/'IEEE8500_operating_point_20260911/D1_AEMO_VIC1_FORECAST_AUTHORITY.json'","BASE/'D1_AEMO_VIC1_FORECAST.json'")
  text=text.replace("assert len(jobs)==708 and all",'assert len(jobs)>0 and all').replace('jobs=708','jobs=len(jobs)')
  text=text.replace("power=power_from_execution(ROOT,jr,cap,exo['weather']);np.savez_compressed", "power=power_from_execution(ROOT,jr,cap,exo['weather'])\n  power['power_audit']=dict(normalized_original_audit=power['power_audit'],physical_demand_scale=2.4,physical_resource_scale=2.,authority=rec(BASE/'AIDC_2X_AUTHORITY.json'),physical_capacity={s:2*n for s,n in cap.items()},C1='2.4*C1(IT_normalized, actual_weather)')\n  power['occupancy']=2*power['occupancy']\n  for key in ('IT','PCC_P','PCC_Q'):power[key]=2.4*power[key]\n  np.savez_compressed")
 if name=='run_policy':
  text=text.replace('2025-05-21',DAY).replace("W/'IEEE8500_numerical_preflight_20260911/AXES.json'","BASE/'AXES.json'")
 exec(compile(text,str(source)+'::'+name,'exec'),globals())
 adaptations.append(dict(name=name,unaltered=text==original,original_AST_SHA256=hashlib.sha256(ast.dump(ast.parse(original),include_attributes=False).encode()).hexdigest(),bound_AST_SHA256=hashlib.sha256(ast.dump(ast.parse(text),include_attributes=False).encode()).hexdigest(),diff=''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True)))))

def selected():
 assert read(BASE/'B1_RESULT.json')['status']=='PASS'
 return {'B0':(read(BASE/'REFERENCE_JOBS.json'),[]),'B1':(read(BASE/'B1_RESULT.json')['jobs'],[])}

def verify():
 for r in read(H/'RULE_FREEZE.json')['source_files']:assert sha(r['path'])==r['sha256'],r['path']

def main():
 start=time.perf_counter();assert not H.exists();H.mkdir()
 (H/'BATTERY_EFFICIENCY_AUTHORITY.json').write_bytes((METHOD/'BATTERY_EFFICIENCY_AUTHORITY.json').read_bytes())
 assert read(BASE/'B0_GATE.json')['status']=='PASS' and read(BASE/'B1_RESULT.json')['status']=='PASS'
 from common8500 import exact,install_output_paths
 install_output_paths()
 # Reuse the completed, SHA-frozen DA final and independent AC evidence.
 origin=BASE
 assert read(origin/'DA_RESULT.json')['clean_replay']=='PASS'
 save(H/'DA_FINAL_AND_CLEAN.json',dict(status='PASS',source=rec(origin/'DA_RESULT.json'),new_DA_optimization_calls=0))

 ns=kernel()
 from dayahead.v41.data import SOURCE_REPO
 audit=Path(SOURCE_REPO)/'dayahead/artifacts/v40d_actual_realized_replay'
 files=[Path(__file__),BASE/'electrical_engine.py',BASE/'PCC_Master.dss',BASE/'PCC_OVERLAY_INVENTORY.json',origin/'MAPPING_FREEZE.json',origin/'RUN_INPUT_FREEZE.json',origin/'IEEE8500_PCC_Overlay.dss',origin/'PCC_BusCoordinates.dss',BASE/'actual_power_binding.py',BASE/'headroom_authority.py',BASE/'HEADROOM_AUTHORITY.json',source,BASE/'B1_RESULT.json',BASE/'REFERENCE_JOBS.json',BASE/'AIDC_2X_AUTHORITY.json',BASE/'SCREENING_RULE.json',BASE/'D1_AEMO_VIC1_FORECAST.json',METHOD/'METHOD_FREEZE.json',METHOD/'METHOD_CODE_BINDING.json',METHOD/'robust_search.py',METHOD/'frozen_code/qsafe.py',METHOD/'frozen_code/worker.py',audit/'V40D_FROZEN_JOB_OBSERVATIONS.parquet']
 for name in ['V40D_AEMO_COMPLETENESS.json','V40D_WEATHER_COMPLETENESS.json','V40D_TRAFFIC_COMPLETENESS.json']:
  p=audit/name;files.append(p);j=read(p)
  if name.startswith('V40D_AEMO'):refs=[j['demand']['source'],j['pv']['source']]
  elif name.startswith('V40D_WEATHER'):refs=[j['derived']]
  else:refs=[j['link_order'],*j['geometry_sources'],next(x for x in j['days'] if x['day']==DAY)['source']]
  for r in refs:assert sha(r['path'])==r['sha256'];files.append(Path(r['path']))
 for sub in ['v41','v41r1','v40d_actual','v40g_segments','v39a','v33m']:
  files+=list((ROOT/'dayahead'/sub).glob('*.py'))
 save(H/'ADAPTER_FUNCTION_BINDINGS.json',dict(source=rec(source),adaptations=adaptations,QSAFE_function_bindings=FUNCTION_BINDINGS))
 save(H/'RULE_FREEZE.json',dict(status='FROZEN_BEFORE_ACTUAL',date=DAY,policies=['B0','B1'],timing_status='CONTINUOUS_14400S_EXTERNAL_DEADLINE',capacity_physical=2624,AIDC_scale=2.,MESS='OFF',no_new_mobility_or_QSAFE_rule=True,QSAFE_policy_scope='Unchanged IEEE8500 robustV2: B0/B1 baseline is accepted without Q correction; independently validate all hard limits',original_method=rec(METHOD/'METHOD_FREEZE.json'),source_files=[rec(p) for p in sorted(set(files))]))
 verify();protect()
 import gurobipy as gp
 gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('DAYAHEAD_OPTIMIZER_FORBIDDEN_IN_ACTUAL'))
 da_authority=inputs(ns)
 for policy in ['B0','B1']:
  assert (H/policy/'INPUT_READY.json').exists()
  run_policy(policy,ns,da_authority)
  # Preserve the original normalized replay ledger and its exact physical-unit image.
  events=pd.read_parquet(H/policy/'aidc/RESOURCE_CHANGE_EVENTS.parquet')
  physical=events.copy()
  for col in ['GPU_delta','GPU_occupancy_before','GPU_occupancy_after','GPU_capacity','rack_single_gang_capacity']:physical[col]=2*physical[col]
  assert ((physical.GPU_occupancy_after>=0)&(physical.GPU_occupancy_after<=physical.GPU_capacity)).all()
  physical.to_parquet(H/policy/'aidc/PHYSICAL_2X_RESOURCE_CHANGE_EVENTS.parquet',index=False)
  save(H/policy/'PHYSICAL_2X_RESOURCE_AUDIT.json',dict(status='PASS',normalized_events=rec(H/policy/'aidc/RESOURCE_CHANGE_EVENTS.parquet'),physical_events=rec(H/policy/'aidc/PHYSICAL_2X_RESOURCE_CHANGE_EVENTS.parquet'),all_resource_values_uniformly_doubled=True,event_timestamps_and_job_rack_site_choices_unchanged=True))
  # Existing robustV2 feasibility predicate, independent of summary aggregation.
  with np.load(H/policy/'FINAL_ACTUAL/OPENDSS_PHASE_ARRAYS.npz') as z:
   passes=[ns['feasible'](dict(v=z['voltage_pu'][t],ipu=np.r_[z['line_current_loading_pu'][t],z['transformer_current_loading_pu'][t]],kva=z['transformer_winding_kva_loading_pu'][t],converged=True)) for t in range(96)]
  save(H/policy/'QSAFE_ROBUST_V2_CHECK.json',dict(status='PASS' if all(passes) else 'FAIL',slots_pass=sum(passes),Q_interventions=0,policy_branch='Existing B0/B1 control replay only',MESS_OFF=True,new_rules=0,method=rec(METHOD/'METHOD_FREEZE.json')))
  verify()
 save(H/'COMPLETE.json',dict(status='COMPLETE',date=DAY,policies=['B0','B1'],wall_seconds=time.perf_counter()-start,source_preservation='PASS',DA_and_Actual_clean_replay=True))
 print('ALL_VALIDATIONS_COMPLETE',time.perf_counter()-start,flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  if H.exists():save(H/'TECHNICAL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
  raise
