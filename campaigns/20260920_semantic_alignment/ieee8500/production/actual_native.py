"""IEEE8500 exact evaluator, with restorable causal slot state and clean-prefix fallback."""
from common8500 import *
SETTERS=('Hour','Seconds','Year','Frequency','LoadMult','GenMult','MaxIterations','MinIterations','MaxControlIterations','Convergence','Algorithm','LoadModel','StepSize','Number')
class Native:
 def __init__(self,folder,data):
  self.e=Engine(folder);self.data=data;self.e.md=data['md'];self.e.mpv=data['mpv'];self.e.ap=data['PCC_P'];self.e.aq=data['PCC_Q']
 def inputs(self,t,p,q):
  e=self.e;data=self.data;x=np.r_[data['PCC_P'][t],np.zeros(48)]
  for j,loc in enumerate(data['locations'][t]):
   if data['connected'][t,j]:
    k=e.services.index(loc);x[12+k]+=p[j];x[36+k]+=q[j]
   else:assert p[j]==0 and q[j]==0
  e.inputs(t,x)
 def solve(self,t):
  e=self.e;e.d.Solution.SolveSnap();err=e.d.Error.Number();assert err==0,('DSS_API_ERROR',err)
  vv,ll,tt,ss=e.arrays();st=e.state(t);line=abs(ll);tx=abs(tt)
  return dict(v=np.sqrt(vv),line=line,tx=tx,ipu=np.r_[line,tx],kva=abs(ss)/e.ax['kva_rating'],taps=[r['tap_number'] for r in st['regulators']],caps=[r['step_states'] for r in st['capacitors']],converged=bool(e.d.Solution.Converged() and e.d.Solution.ControlActionsDone()),settled=bool(e.d.Solution.ControlActionsDone()),controls_settled=bool(e.d.Solution.ControlActionsDone()),state=st)
 def apply(self,t,p,q):self.inputs(t,p,q);return self.solve(t)
 def close(self):self.e.close()

class ExperimentalSnapshotEvaluator:
 def __init__(self,folder,data):
  self.folder=Path(folder);self.data=data;self.native=Native(self.folder/'cached_runtime',data);self.slot=-1;self.snapshot=None;self.accepted=[];self.commands=[];self.fallback=None;self.trials=0;self.solves=0;self.engines=1;self.trace=[]
 def capture(self,t):
  d=self.native.e.d;st=self.native.e.state(t)
  reversible=[]
  for name in d.RegControls.AllNames():d.RegControls.Name(name);reversible.append(d.RegControls.IsReversible())
  s=dict(state=st,solution={k:getattr(d.Solution,k)() for k in SETTERS},control_mode=d.Solution.ControlMode(),solution_mode=d.Solution.Mode(),node_order=d.Circuit.YNodeOrder(),V=d.YMatrix.getV(),I=d.YMatrix.getI(),initialized=d.YMatrix.SolutionInitialized(),updating=d.YMatrix.LoadsNeedUpdating(),iteration=d.YMatrix.Iteration(),actions_done=d.Solution.ControlActionsDone(),control_iterations=d.Solution.ControlIterations())
  if d.CtrlQueue.QueueSize() or d.CtrlQueue.NumActions() or s['solution_mode']!=0 or any(reversible):raise RuntimeError('UNSUPPORTED_NATIVE_DYNAMIC_STATE_USE_CLEAN_PREFIX')
  return s
 def restore(self,t,p,q):
  d=self.native.e.d;s=self.snapshot;d.CtrlQueue.ClearQueue();d.CtrlQueue.ClearActions()
  for r in s['state']['regulators']:
   d.RegControls.Name(r['name']);d.RegControls.Reset();w=d.RegControls.TapWinding()
   d.Transformers.Name(r['transformer']);d.Transformers.Wdg(w);d.Transformers.Tap(r['tap_pu'])
  for r in s['state']['capcontrols']:d.CapControls.Name(r['name']);d.CapControls.Reset()
  for r in s['state']['capacitors']:d.Capacitors.Name(r['name']);d.Capacitors.States(r['step_states'])
  for k,v in s['solution'].items():getattr(d.Solution,k)(v)
  d.Solution.ControlMode(s['control_mode']);self.native.inputs(t,p,q);d.Solution.BuildYMatrix(2,True)
  assert d.Circuit.YNodeOrder()==s['node_order'],'CACHED_NODE_ORDER_DRIFT'
  vp=d.YMatrix.VVector();ip=d.YMatrix.IVector()
  for i,v in enumerate(s['V']):vp[i]=v
  for i,v in enumerate(s['I']):ip[i]=v
  d.YMatrix.SolutionInitialized(s['initialized']);d.YMatrix.LoadsNeedUpdating(s['updating']);d.YMatrix.Iteration(s['iteration']);d.Solution.ControlActionsDone(s['actions_done']);d.Solution.ControlIterations(s['control_iterations'])
  r=self.native.solve(t);self.solves+=1;return r
 def prefix(self,t,p,q):
  native=Native(self.folder/'clean_prefix_runtime',self.data);self.engines+=1
  try:
   for s in range(t+1):
    pp,qq=(p,q) if s==t else self.commands[s];r=native.apply(s,pp,qq);self.solves+=1
    if s<t:
     old=self.accepted[s];assert r['taps']==old['taps'] and max(np.max(abs(r[k]-old[k])) for k in ('v','line','tx','kva'))<1e-9,'ACCEPTED_PREFIX_DRIFT'
   return r
  finally:native.close()
 def evaluate(self,t,p,q):
  assert t==len(self.accepted),'FUTURE_OR_NONCAUSAL_SLOT';self.trials+=1
  if self.fallback:r=self.prefix(t,p,q)
  else:
   try:
    if t!=self.slot:
     assert t==self.slot+1;self.native.inputs(t,p,q);self.snapshot=self.capture(t);self.slot=t
    r=self.restore(t,p,q)
   except Exception as e:
    self.fallback=repr(e);save(self.folder/'PERFORMANCE_FALLBACK.json',dict(slot=t,reason=self.fallback,original_clean_prefix_used=True));r=self.prefix(t,p,q)
  if self.trials%50==0:save(self.folder/'TRIAL_PROGRESS.json',dict(slot=t,max_Actual_slot_applied=t,trials=self.trials,native_solves=self.solves,fallback=self.fallback,updated_at=time.time()))
  return r
 def accept(self,p,q,r):self.commands.append((np.asarray(p).copy(),np.asarray(q).copy()));self.accepted.append(r)
 def close(self):
  self.native.close();save(self.folder/'NATIVE_PERFORMANCE_AUDIT.json',dict(trials=self.trials,native_solves=self.solves,compiled_engines=self.engines,fallback=self.fallback,future_Actual_slots_applied=0,independent_continuous_verification_required=True))

class Evaluator:
 """Continuous accepted state; isolated exact prefixes for alternative commands.

 IEEE8500 regulator/capacitor hidden state did not pass snapshot equivalence.
 Repeated identical commands reuse their exact result, never a restored state.
 """
 def __init__(self,folder,data):
  self.folder=Path(folder);self.data=data;self.native=Native(self.folder/'accepted_runtime',data)
  self.accepted=[];self.commands=[];self.slot=-1;self.results={};self.base_key=None
  self.trial_native=None;self.trial_key=None;self.trials=0;self.solves=0;self.engines=1
  self.fallback='SNAPSHOT_REJECTED_BY_FORECAST_EQUIVALENCE; EXACT_PREFIX_ALTERNATIVES'
 @staticmethod
 def key(p,q):return (np.asarray(p,dtype=float).tobytes(),np.asarray(q,dtype=float).tobytes())
 def dispose_trial(self):
  if self.trial_native is not None:self.trial_native.close();self.trial_native=None;self.trial_key=None
 def prefix(self,t,p,q):
  self.dispose_trial();native=Native(self.folder/'trial_runtime',self.data);self.engines+=1
  try:
   for s in range(t+1):
    pp,qq=(p,q) if s==t else self.commands[s];r=native.apply(s,pp,qq);self.solves+=1
    if s<t:
     old=self.accepted[s]
     assert r['taps']==old['taps'] and r['caps']==old['caps'] and max(np.max(abs(r[k]-old[k])) for k in ('v','line','tx','kva'))<1e-9,'ACCEPTED_PREFIX_DRIFT'
   self.trial_native=native;self.trial_key=self.key(p,q);return r
  except BaseException:native.close();raise
 def evaluate(self,t,p,q):
  assert t==len(self.accepted),'FUTURE_OR_NONCAUSAL_SLOT';self.trials+=1;key=self.key(p,q)
  if self.slot!=t:
   assert t==self.slot+1;self.slot=t;self.results={};self.base_key=key
   r=self.native.apply(t,p,q);self.solves+=1;self.results[key]=r
  elif key in self.results:r=self.results[key]
  else:r=self.prefix(t,p,q);self.results[key]=r
  if self.trials%50==0:save(self.folder/'TRIAL_PROGRESS.json',dict(slot=t,max_Actual_slot_applied=t,trials=self.trials,native_solves=self.solves,execution='CONTINUOUS_BASELINE_EXACT_PREFIX_TRIALS',updated_at=time.time()))
  return r
 def accept(self,p,q,r):
  key=self.key(p,q)
  if key!=self.base_key:
   if key!=self.trial_key:
    verified=self.prefix(self.slot,p,q)
    assert verified['taps']==r['taps'] and verified['caps']==r['caps'] and max(np.max(abs(verified[k]-r[k])) for k in ('v','line','tx','kva'))<1e-9
   self.native.close();self.native=self.trial_native;self.trial_native=None;self.trial_key=None
  else:self.dispose_trial()
  self.commands.append((np.asarray(p).copy(),np.asarray(q).copy()));self.accepted.append(r)
 def close(self):
  self.dispose_trial();self.native.close()
  save(self.folder/'NATIVE_PERFORMANCE_AUDIT.json',dict(trials=self.trials,native_solves=self.solves,compiled_engines=self.engines,execution='CONTINUOUS_BASELINE_EXACT_PREFIX_TRIALS',snapshot_optimization_enabled=False,future_Actual_slots_applied=0,independent_continuous_verification_required=True))
