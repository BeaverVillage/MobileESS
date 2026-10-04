"""Observe other lanes; native imports alone are not an optimize proof."""
from .common import *
import psutil,ast,re,time

def nonheavy_binding(p):
 try:
  command=' '.join(p.parent().cmdline());match=re.search(r"@'\s*\n(.*?)\n'@",command,re.S)
  if not match:return None
  source=match.group(1);tree=ast.parse(source)
  forbidden={'optimize','Solve','solve','run_a1','build','prepare','run_day'}
  if any(isinstance(n,ast.Call) and ((isinstance(n.func,ast.Attribute) and n.func.attr in forbidden) or (isinstance(n.func,ast.Name) and n.func.id in forbidden)) for n in ast.walk(tree)):return None
  if 'from v42_b1_production.native import bind' not in source or 'optimization_calls=0' not in source or '.load_native()' not in source:return None
  witness=read(OUT/'DW_CONTINUATION_PREREGISTRATION.json')['nonheavy_binding_source_SHA']
  if not all(sha(Path(n))==h for n,h in witness.items()):return None
  return dict(reason='Source-bound B1 cached input binding; no optimizer/OpenDSS solve',parent_command_SHA=hashlib.sha256(source.encode()).hexdigest(),source_SHA=witness)
 except (psutil.NoSuchProcess,psutil.AccessDenied,SyntaxError,FileNotFoundError):return None

def inspect_native(excluded=()):
 rows=[];blocked=[];skip={os.getpid(),*excluded}
 for p in psutil.process_iter(['pid','ppid','name']):
  if p.pid in skip or not any(s in (p.info['name'] or '').lower() for s in ('python','gurobi','opendss','pytest')):continue
  try:
   cmd=p.cmdline();maps=[x.path for x in p.memory_maps(grouped=True) if any(s in x.path.lower() for s in ('gurobi','opendss','dss_capi'))];proof=nonheavy_binding(p) if maps else None
   own_verify=('-m' in cmd and cmd[cmd.index('-m')+1] in ['v42_dw_continuation.base','v42_dw_continuation.finalize'])
   classification='SOURCE_PROVEN_NONHEAVY_BINDING' if proof else 'OWN_READONLY_VERIFICATION' if own_verify else 'NO_NATIVE_ENGINE_MAPPED' if not maps else 'NATIVE_HEAVY_OR_UNOBSERVABLE_RESERVATION'
   r=dict(p.info,cmd=cmd,cwd=p.cwd(),RSS=p.memory_info().rss,native_maps=maps,classification=classification,nonheavy_proof=proof);rows.append(r)
   if maps and not proof and not own_verify:blocked.append(r)
  except psutil.NoSuchProcess:continue
  except psutil.AccessDenied:blocked.append(dict(pid=p.pid,classification='UNOBSERVABLE_NATIVE_CANDIDATE'))
 return rows,blocked

def wait_admission(exp,phase):
 start=time.perf_counter();waited=False;events=getattr(exp,'wait_events',[])
 while True:
  sample=exp.monitor.sample();processes,blocked=inspect_native(exp.pids)
  from .resources import resource_failures
  observed_native=list(blocked);authorized=[]
  permit=OUT/'USER_RESOURCE_ADMISSION_OVERRIDE.json'
  if permit.exists() and read(permit)['B1_concurrency_authorized']:
   for row in observed_native:
    cmd=row.get('cmd',[])
    if '-m' in cmd and cmd[cmd.index('-m')+1]=='v42_b1_production.worker':authorized.append(row)
   blocked=[row for row in blocked if row not in authorized]
  failures=resource_failures(sample,exp.monitor.rows)
  if not blocked and not failures:break
  if STOP.exists():raise InterruptedError('USER_STOP_AT_WAIT_RESOURCE')
  if not waited:
   waited=True
   if getattr(exp,'master',None) is not None and hasattr(exp,'persistent_adapter'):
    exp.suspend_models()
  event=dict(phase=phase,UTC=sample['UTC'],elapsed_wait=time.perf_counter()-start,blocked=blocked,guards=failures,new_budget_consumed=exp.spent(),pool_count=START_COLUMNS+len(exp.columns),alpha=exp.smooth_weight,other_lane_kill_calls=0,other_lane_terminate_calls=0)
  if not events or time.perf_counter()-getattr(exp,'last_wait_heartbeat',0)>=30:
   events.append(event);exp.last_wait_heartbeat=time.perf_counter();write('DW_CONTINUATION_WAIT_RESOURCE.json',dict(status='WAIT_RESOURCE',events=events,optimization_budget_consumed_by_wait=0));print('WAIT_RESOURCE',phase,exp.spent(),len(blocked),failures,flush=True)
  exp.active_start=None;exp.cancel.clear();exp.monitor.failed.clear();time.sleep(2)
 exp.cancel.clear();exp.monitor.failed.clear();exp.wait_events=events
 write('DW_CONTINUATION_WAIT_RESOURCE.json',dict(status='ADMITTED',events=events,latest_processes=processes,authorized_B1_native_reservations=authorized,B1_concurrency_authorized=bool(authorized),wait_seconds=time.perf_counter()-start if waited else 0.,optimization_budget_consumed_by_wait=0,other_lane_kill_calls=0,other_lane_terminate_calls=0))
 if getattr(exp,'runtime_suspended',False):
  exp.restore_models()
  if phase!='PRICING_MODEL_BUILD':exp.start_workers(4)
 return sample
