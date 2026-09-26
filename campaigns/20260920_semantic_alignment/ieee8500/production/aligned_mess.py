"""IEEE123 bounded_mess incumbent semantics, authorized unlimited MESS compute.

Numerical grid/PCC/fleet adapters are unchanged IEEE8500 ports. Original v40h
mobility/beam and v40h recourse own the scientific search and fixed-route model.
"""
from common8500 import *
import inspect,difflib,subprocess
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import gurobipy as gp
from mess_execution_performance import evaluate_grid, install_short_candidate_paths

class UnlimitedBudget:
 total=1e100
 def __init__(self):self.used=0.;self.events=[]
 @property
 def remaining(self):return 1e100
 def charge(self,seconds,label):self.used+=seconds;self.events.append(dict(seconds=seconds,label=label))

class RankingInversionStop(RuntimeError):pass

def install_compute():
 original=gp.Model.optimize
 def optimize(model,*args,**kwargs):
  model.Params.Threads=4;model.Params.TimeLimit=gp.GRB.INFINITY;model.Params.WorkLimit=gp.GRB.INFINITY
  model.Params.SoftMemLimit=gp.GRB.INFINITY;model.Params.NodefileStart=.5
  node=P/'nodefiles'/str(os.getpid());node.mkdir(parents=True,exist_ok=True);model.Params.NodefileDir=str(node)
  assert model.Params.Threads==4 and model.Params.TimeLimit>=1e90 and model.Params.WorkLimit>=1e90
  state(stage='MESS:OPTIMIZING',solver_name=model.ModelName,Threads=4,TimeLimit='NONE',WorkLimit='NONE')
  answer=original(model,*args,**kwargs)
  with (P/'MESS_SOLVER_TERMINATIONS.jsonl').open('a',encoding='utf-8') as f:
   f.write(json.dumps(dict(model=model.ModelName,status=int(model.Status),runtime=model.Runtime,work=model.Work,threads=model.Params.Threads,TimeLimit='NONE',WorkLimit='NONE',at=time.time()))+'\n')
  if model.Status in (gp.GRB.TIME_LIMIT,gp.GRB.WORK_LIMIT):raise RuntimeError('FORBIDDEN_MESS_COMPUTE_CUTOFF')
  return answer
 gp.Model.optimize=optimize

def install_grid():
 proof=read(P/'performance_verification/RESULT.json');assert proof['status']=='PASS'
 for source in proof['sources']:assert sha(source['path'])==source['sha256'],'MESS_PERFORMANCE_ADAPTER_DRIFT'
 import dayahead.v40a.grid as grid
 import mess_grid8500
 grid.evaluate_grid=evaluate_grid;grid.add_grid=mess_grid8500.add
 from dayahead.v41r1 import bounded_mess
 bounded_mess.ROOT=P

def load_worker_context(day):
 assert day=='2025-05-01'
 ctx=new_context(load_options=False);ctx.v41_bounded_compute=None
 # M1 consumes fixed jobs; AIDC neighborhood options have no role here.
 ctx.options.clear();ctx.references.clear()
 from mess_runtime import Authority
 ctx.electrical=SimpleNamespace(legacy_context=None,voltage=Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes'])),current=Authority())
 return ctx

def observe_candidate(ctx,jobs,trajectory,folder,label):
 from dayahead.v40g_segments.canonical import planning_power
 from dayahead.v40a.grid import controls_from_trajectory
 pcc=planning_power(jobs,ctx)['pcc'];approx=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,trajectory.slots),ctx.nodes)
 ac=exact(pcc,trajectory.slots,folder/'exact_observation')
 rho=ac['metrics']['max_phase_line_loading_pu'];w=max(ac['slots'],key=lambda r:r['max_phase_line_loading_pu'])
 baseline=exact(pcc,(),folder/'MESS_OFF_exact')
 br=baseline['metrics']['max_phase_line_loading_pu']
 ba=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,()),ctx.nodes)['rho_max']
 proof=dict(label=label,approximate_rho=approx['rho_max'],exact_AC_rho=rho,exact_critical_line=w['line_witness'],exact_critical_slot=w['slot'],Vmin=ac['metrics']['Vmin_pu'],Vmax=ac['metrics']['Vmax_pu'],surrogate_exact_error=rho-approx['rho_max'],AC_PASS=ac['status']=='PASS',MESS_off_approximate_rho=ba,MESS_off_exact_rho=br,
  diagnostic_only=True,physical_closure_applied_before_A2=False)
 # Operational stop gate, frozen before rerun. It is not a feasible-set cut.
 inversion=(rho-approx['rho_max']>=.05 and approx['rho_max']<ba-1e-4 and rho>br+1e-4)
 proof['large_ranking_inversion']=bool(inversion)
 save(folder/'APPROX_EXACT_COMPARISON.json',proof)
 if inversion:
  save(P/'SEMANTIC_ALIGNMENT_STOP.json',dict(status='STOP_SURROGATE_EXACT_RANKING_INVERSION',candidate=str(folder),evidence=proof,rule='error >= 0.05, surrogate improvement > 0.0001 and exact deterioration > 0.0001 against the identical fixed-AIDC MESS-off reference',Actual_forbidden=True))
  raise RankingInversionStop('STOP_SURROGATE_EXACT_RANKING_INVERSION')
 return proof

def inherited_search(day,jobs,ctx,output):
 install_short_candidate_paths(P,save,read)
 from dayahead.v40h import mobility,beam_driver as beam
 from dayahead.v40h.cache import execution_identity
 from dayahead.v40a.invariants import digest
 from dayahead.v40g_segments.canonical import planning_power
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from mess_runtime import traffic,integrated_adapter,coefficients
 from dayahead.v40a import observability
 from dayahead.v40h import authorities
 from dayahead.v40b.windows_paths import install_beam_paths
 from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
 _install_windows_safe_k_archive();install_beam_paths(beam)
 ctx.coefficients=coefficients()
 cache_proof=read(P/'performance_verification/ANCHOR_CACHE.json');assert cache_proof['status']=='PASS'
 for source in cache_proof['sources']:assert sha(source['path'])==source['sha256'],'ANCHOR_CACHE_SOURCE_DRIFT'
 import psutil
 from mess_anchor_cache import install as install_anchor_cache
 cache_limit=max(0,min(int(1.5*2**30),int(psutil.virtual_memory().available-6*2**30)))
 anchor_cache_stats=install_anchor_cache(ctx.coefficients,cache_limit)
 save(Path(output)/'ANCHOR_CACHE_ACTIVATION.json',dict(validation=record(P/'performance_verification/ANCHOR_CACHE.json'),limit_bytes=cache_limit,scope='PURE_FIXED_COEFFICIENT_CONSTANTS_ONLY',scientific_candidate_changes=0))
 pcc=planning_power(jobs,ctx)['pcc'];tr=traffic()
 from dayahead.v41.execution import SOURCE_REPO
 inv=read(SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json');ta=inv['traffic'][day]
 from dayahead import mess_physics
 from dayahead.v33m import contracts as mobility_contracts,mobility_15min_adapter
 runtime_mobility={m.__name__:record(inspect.getsourcefile(m)) for m in (mess_physics,mobility_contracts,mobility_15min_adapter)}
 assert sha(inspect.getsourcefile(mobility_contracts))==inv['MESS_mobility']['dayahead/v33m/contracts.py']['sha256']
 assert sha(inspect.getsourcefile(mobility_15min_adapter))==inv['MESS_mobility']['dayahead/v33m/mobility_15min_adapter.py']['sha256']
 overlay=next(r for r in read(P/'CODE_DIFF.json') if r['module']=='dayahead.mess_physics')
 assert sha(inspect.getsourcefile(mess_physics))==overlay['override_sha256']
 save(Path(output)/'MOBILITY_SOURCE_BINDING.json',dict(status='PASS',actual_runtime_sources=runtime_mobility,existing_IEEE8500_overlay=overlay,old_inventory=record(SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json'),reason='New cache identity binds the already authorized active IEEE8500 source revision, not missing pre-v41 source files; traffic and travel-energy code unchanged'))
 values=dict(campaign_SHA=sha(P/'PRODUCTION_AUTHORIZATION.json'),A0_decision_SHA=digest(jobs),A0_segment_SHA=digest(jobs),A0_GPU_SHA=digest(planning_power(jobs,ctx)['gpu']),A0_PCC_SHA=digest(pcc),electrical_coefficients=[c.coefficient_sha256 for c in ctx.coefficients],traffic_forecast=ta['forecast'],road_graph={'files':inv['road_graph'],'canonical_SHA':ta['forecast']['graph_SHA']},route_table=ta['route_table'],service_road_mapping=inv['road_graph']['service_nodes'],mobility_physics=inv['MESS_mobility'],MESS_electrical=record(P/'FINAL_MESS_RATING_AUTHORITY.json'),connection_delay={'source':inv['MESS_mobility']},route_energy={'source':inv['MESS_mobility']},MESS_PCC_mapping=record(P/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json'),K=200,beam_width=2,fallback_widths=[4],seed=2,WorkLimit_tiers='UNLIMITED_USER_AUTHORIZED',solver_settings={'Threads':4,'route_search_workers':1,'TimeLimit':None,'WorkLimit':None},source_manifest={'aligned_source':record(P/'aligned_mess.py'),'inherited_mobility':record(inspect.getsourcefile(mobility)),'inherited_beam':record(inspect.getsourcefile(beam))})
 values.update(mobility_physics=runtime_mobility,connection_delay={'source':runtime_mobility},route_energy={'source':runtime_mobility})
 values['source_manifest'].update(anchor_cache=record(P/'mess_anchor_cache.py'),execution_performance_adapter=record(P/'mess_execution_performance.py'),electrical_row_projection=record(P/'mess_grid8500.py'))
 identity=execution_identity(values);save(Path(output)/'M1_IDENTITY.json',identity)
 class Pool(ThreadPoolExecutor):
  def __init__(self,max_workers=None,initializer=None,initargs=(),**kw):super().__init__(max_workers=1,initializer=initializer,initargs=initargs)
 observability.ObservedProductionPool=Pool
 authorities.load_bound_traffic=lambda *args,**kwargs:tr
 beam.solve_integrated_mess=integrated_adapter()
 mapping={r['service']:r['PCC'] for r in read(P/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
 beam._service_mapping=lambda:mapping
 def progress(value):
  save(Path(output)/'M1_PROGRESS.json',dict(at=time.time(),detail=value,anchor_cache=anchor_cache_stats));state(status='RUNNING',stage='M1:INHERITED_V40H_SEARCH',MESS_progress=value)
 result=mobility.search_once(ROOT,day,pcc,ctx,output,progress,identity)
 trajectory=MessTrajectory(tuple(beam._restore_slots(result['trajectory_slots'])))
 return trajectory,result

def bounded_run(ctx,jobs,output,policy):
 from dayahead.v41r1 import bounded_mess as original
 install_grid();install_compute();ctx.v41_policy=policy;ctx.v41_policy_budget=UnlimitedBudget()
 source=inspect.getsource(original.run)
 replacements={"search_output=Path('D:/MobileESS_FO_M1')/uuid.uuid4().hex[:12]":"search_output=P/'m1'/uuid.uuid4().hex[:12]",
  "allowance=max(0.,min(budget.remaining,min(900.,budget.total*.5) if policy=='B3' else budget.remaining)-5.)":"allowance=float('inf')",
  "[sys.executable,'-u','-m','dayahead.v41r1.bounded_mess',str(request)]":"[sys.executable,'-B','-u',str(P/'bounded_child.py'),str(request)]",
  "classification='BOUNDED_COMPUTE_FEASIBLE'":"classification='VERIFIED_INCUMBENT_UNLIMITED_COMPUTE'",
  "algorithm='INHERITED_MESS_SEARCH_WITH_SHARED_POLICY_DAY_DEADLINE'":"algorithm='IEEE123_BOUNDED_MESS_INCUMBENT_SEMANTICS_NO_DEADLINE'"}
 for old,new in replacements.items():assert source.count(old)==1,old;source=source.replace(old,new)
 ns={**vars(original),'P':P,'ROOT':P};exec(compile(source,str(P/'aligned_mess.py')+'::bounded_run','exec'),ns)
 save(Path(output)/'BOUNDED_ADAPTATION.json',dict(source=record(inspect.getsourcefile(original)),changes=replacements,feasible_set_changed=False,original_incumbent_and_checkpoint_semantics=True))
 save(Path(output)/'EXECUTION_PERFORMANCE_BINDING.json',dict(validation=record(P/'performance_verification/RESULT.json'),adapter=record(P/'mess_execution_performance.py'),electrical_row_projection=record(P/'mess_grid8500.py'),coefficient_values_and_scientific_rows_unchanged=True))
 return ns['run'](ctx.day,jobs,ctx,output)

def bounded_child(request):
 from dayahead.v41r1 import bounded_mess as original
 install_grid();install_compute()
 source=inspect.getsource(original.worker)
 replacements={'from dayahead.v41.electrical import load':'from aligned_mess import load_worker_context as load',
  'from dayahead.v41.execution import run_m1':'from aligned_mess import inherited_search as run_m1',
  "write_json(output/'BOUNDED_FLEET_INCUMBENT.json',with_ledger)":"write_json(output/'BOUNDED_FLEET_INCUMBENT.json',with_ledger)\n            observe_candidate(ctx,data['jobs'],trajectory,path.with_suffix(''),source)"}
 for old,new in replacements.items():assert source.count(old)==1,old;source=source.replace(old,new)
 ns={**vars(original),'observe_candidate':observe_candidate};exec(compile(source,str(P/'aligned_mess.py')+'::bounded_child','exec'),ns)
 ns['worker'](request)

def recourse(ctx,jobs,pcc,m1,output):
 from dayahead.v40h import recourse as original
 import mess_grid8500
 install_grid();install_compute()
 original.add_grid=mess_grid8500.add;original.evaluate_grid=evaluate_grid
 ctx.v41_policy_budget=UnlimitedBudget();ctx.v41_current_jobs=jobs;ctx.v41_mf_output=Path(output)
 result=original.solve_fixed_route(pcc,m1,ctx)
 assert result['status']=='PASS';assert result['solver']['status_code'] not in (9,16)
 selected=result['trajectory'];proof=observe_candidate(ctx,jobs,selected,Path(output),'M2_ACCEPTED')
 save(Path(output)/'RESULT.json',result);return selected,result,proof
