"""Full original-row adapters, deterministic batches and conservative restart."""
from .common import *
from .resources import resource_failures
from v42_dw_runtime.contracts import RuntimeFlags,DiscoverySnapshot,Candidate,canonical
from v42_dw_runtime.validation import OriginalBlockValidator,validate_batches
from v42_dw_runtime.audit import AuditCache,AuditReceipt,make_authority,audit_plan
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
from v42_dw_root.run import exact_rc
from v42_degen.identity import digest
from dataclasses import asdict,replace
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import numpy as np,psutil

FLAGS=RuntimeFlags(True,True,True,False)
class Integration:
 METHODS=('suspend_models','restore_models','continuation_receipts','setup_audits','audit_one','tier_audit','parallel_validation','resource_gate','restore_run','resume_dual','debit_done','full_pool_final','runtime_receipts','authority_rmp','last_completed_dual')
 def resource_gate(self,phase):
  from .admission import wait_admission
  wait_admission(self,phase)
 def setup_audits(self):
  start=time.perf_counter();rr=[[] for _ in UNITS]
  for i in range(self.A.shape[0]):
   deps=set(map(int,self.owner[self.A.indices[self.A.indptr[i]:self.A.indptr[i+1]]]))
   if len(deps)==1 and -1 not in deps:rr[next(iter(deps))].append(i)
  self.validators={}
  for m,b in enumerate(self.blocks):
   rows=np.asarray(rr[m]);cols=b.columns;matrix=self.A[rows][:,cols];attrs=dict(self.d,rhs=self.d['rhs'][rows],sense=self.d['sense'][rows],lower=self.d['lower'][cols],upper=self.d['upper'][cols],types=self.d['types'][cols],objective=self.d['objective'][cols],constant=np.array(0.))
   self.validators[m]=OriginalBlockValidator(m,b,matrix,attrs,pure_binary_equalities(matrix,attrs))
  paths=['v42_dw_runtime/validation.py','v42_dw_resume/audit.py','v42_dw_root/run.py','v42_native/mess.py','v42_bootstrap/attribution.py','v42_dw_root/models.py','v42_dw_root/partition.py']
  self.audit_authority=make_authority(SCIENTIFIC_HEAD,[(self.A,self.d),(self.B,self.e)],self.d['names'],self.d['row_names'],b''.join((ROOT/p).read_bytes() for p in paths),dict(source_dependencies={p:sha(ROOT/p) for p in paths},A1=read(ARC/'ARC_LP_BASE_IDENTITY.json')['A1_freeze'],entire_PR147_freeze_SHA=sha(OUT/'PR147_BYTE_FREEZE.json')),dict(FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,affine=1e-6,true_RC=-1e-7))
  self.cache=AuditCache.load(OUT/'PHYSICAL_AUDIT_CACHE.json') if (OUT/'PHYSICAL_AUDIT_CACHE.json').exists() else AuditCache()
  self.audit_rows=[];self.validation_rows=[];self.current_RC_rows=[]
  with np.load(SCI/read(SCI/'DW_CHECKPOINT_LATEST.json')['RMP']['point_file']) as z:pi=z['pi'];alpha=z['alpha']
  missing=[c for c in self.master.column_data if self.cache.lookup(c['key'],self.audit_authority) is None]
  with ThreadPoolExecutor(max_workers=4,thread_name_prefix='DW_INITIAL_AUDIT') as ex:
   receipts=list(ex.map(lambda c:self.audit_one(c,pi,alpha,'RESTORED1433'),missing))
  for r in receipts:self.cache.add(r)
  self.cache.save(OUT/'PHYSICAL_AUDIT_CACHE.json');write('DW_AUDIT_CACHE_RESTORE.json' if (OUT/'DW_INITIAL_POOL_AUDIT.json').exists() else 'DW_INITIAL_POOL_AUDIT.json',dict(PASS=True,columns=START_COLUMNS,initial_full_audits=len(missing),authority=asdict(self.audit_authority),authority_key=self.audit_authority.key,wall=time.perf_counter()-start,old_receipt_key_incomplete=True,no_pricing_replayed=True))
 def audit_one(self,c,pi,alpha,label):
  v=self.validators[c['unit']];r=v.audit(c['x']);assert r['local_PASS'] and r['physical_PASS'] and r['integral'];assert v.trajectory_sha(c['x'])==c['key']
  rc=float(exact_rc(self.blocks[c['unit']],c['x'],pi,alpha[c['unit']]))
  return AuditReceipt(c['key'],self.audit_authority,r['max_residual'],rc,hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest(),self.current_round,datetime.now(timezone.utc).isoformat(),label,canonical(r))
 def tier_audit(self,kind,pi,alpha,key):
  begin=time.perf_counter();data={c['key']:c for c in self.master.column_data};newly=list(getattr(self,'pending_new',[]))+[c['SHA256'] for c in self.columns if c['round']==self.current_round-1];self.pending_new=[];plan=audit_plan(kind,data,newly,self.audit_authority,self.cache,FLAGS)
  required=plan['columns_to_full_audit']
  with ThreadPoolExecutor(max_workers=4,thread_name_prefix='DW_POOL_AUDIT') as ex:
   receipts=list(ex.map(lambda k:self.audit_one(data[k],pi,alpha,kind),required))
  for r in receipts:
   if self.cache.lookup(r.trajectory_SHA,self.audit_authority) is None:self.cache.add(r)
  # Every retained column receives CURRENT true-dual RC. Native manual RC identity
  # has independently been audited in solve_master; historical receipt RC is unused.
  current=[dict(SHA=c['key'],true_RC=c['c']-float(pi@c['a'])-alpha[c['unit']]) for c in self.master.column_data]
  assert all(np.isfinite(r['true_RC']) for r in current)
  self.current_RC_rows=current;self.cache.save(OUT/'PHYSICAL_AUDIT_CACHE.json')
  row=dict(kind=kind,round=self.current_round,retained=len(data),full_audited=len(required),reused=len(plan['reused_physical_receipts']),current_true_RC_recomputed=len(current),dual_SHA=key,authority_key=self.audit_authority.key,PASS=True,wall=time.perf_counter()-begin)
  self.audit_rows.append(row);write('DW_INCREMENTAL_AUDIT_FULLSCALE.json',dict(PASS=True,authority=asdict(self.audit_authority),rounds=self.audit_rows,historical_RC_never_authority=True,current_RMP_full_original_required=True,initial_audit=read(OUT/'DW_INITIAL_POOL_AUDIT.json')))
  return row
 def parallel_validation(self,prices,dual):
  begin=time.perf_counter();pi,alpha,key,file=dual
  with np.load(OUT/prices[0]['dual_file']) as z:sp=z['pi'];sa=z['alpha']
  snap=DiscoverySnapshot.create(self.current_round,pi,sp,alpha,sa,self.smoothing_rows[-1]['alpha_used'],self.authority_rmp()['objective'])
  batches={p['unit']:[] for p in prices}
  for p in prices:
   for c in p['candidates']:
    with np.load(OUT/c['point_file']) as z:x=z['x']
    batches[p['unit']].append(Candidate(p['unit'],x,self.current_round,key))
  start=time.perf_counter();seq=validate_batches(batches,snap,self.validators,RuntimeFlags());seqwall=time.perf_counter()-start
  start=time.perf_counter();par=validate_batches(batches,snap,self.validators,FLAGS);parwall=time.perf_counter()-start
  assert [asdict(r) for r in seq]==[asdict(r) for r in par]
  results={(r.unit,r.trajectory_SHA):r for r in par}
  for p in prices:
   chosen=set()
   for c in p['candidates']:
    r=results[p['unit'],c['column_SHA']];assert r.accepted==c['valid_negative'];assert abs(r.true_RC-c['rc_inc'])<=EPS
    c['selected']=bool(r.accepted and c['column_SHA'] not in self.seen[p['unit']] and c['column_SHA'] not in chosen and len(chosen)<4)
    if c['selected']:chosen.add(c['column_SHA'])
    if r.accepted and self.cache.lookup(r.trajectory_SHA,self.audit_authority) is None:self.cache.add(AuditReceipt.issue(r,self.audit_authority,datetime.now(timezone.utc).isoformat(),'DISCOVERY'))
  self.cache.save(OUT/'PHYSICAL_AUDIT_CACHE.json')
  self.validation_rows.append(dict(round=self.current_round,PASS=True,canonical_equivalence=True,sequential_wall=seqwall,parallel_wall=parwall,total_wall=time.perf_counter()-begin,results=[asdict(r) for r in par]))
  write('DW_PARALLEL_VALIDATION_FULLSCALE.json',dict(PASS=True,max_Python_validation_workers=4,additional_Gurobi_processes=0,rounds=self.validation_rows))
 def debit_done(self):
  write('DW_BUDGET_JOURNAL.json',dict(elapsed_budget=self.spent(),elapsed_wall=self.elapsed(),call=self.call,round=self.current_round))
 def restore_run(self):
  self.resume_phase=None
  if not self.resume_checkpoint:return
  cp=self.resume_checkpoint;assert cp['authority_key']==self.audit_authority.key and cp['feature_selection_SHA']==sha(OUT/'DW_RUNTIME_FEATURE_SELECTION.json')
  self.budget_carried=cp['elapsed_budget'];self.wall_carried=cp['elapsed_wall']
  if (OUT/'DW_BUDGET_JOURNAL.json').exists():self.budget_carried=max(self.budget_carried,read(OUT/'DW_BUDGET_JOURNAL.json')['elapsed_budget'])
  if (OUT/'DW_INFLIGHT.json').exists():
   flight=read(OUT/'DW_INFLIGHT.json');self.budget_carried=max(self.budget_carried,flight['spent_before']+flight['reserved_optimize_seconds'])
  assert self.budget_carried<=BUDGET
  state=cp['restart_state']
  for k in ['rmps','prices','rounds','columns','certs','canaries','capture_ledger','smoothing_rows','accepted','uppers']:setattr(self,k,state[k])
  self.audit_rows=state.get('audit_rows',[]);self.validation_rows=state.get('validation_rows',[]);self.checkpoint_timings=state.get('checkpoint_timings',[])
  self.current_round=cp['RMP']['round'];self.call=max([p['call'] for p in self.prices],default=0);self.column_id=len(self.columns)
  self.bestL,self.bestU=cp['best_interval'];self.best_corr=cp['best_corrected_LB'];self.smooth_weight=cp['alpha_next']
  for c in self.columns:
   assert sha(OUT/c['file'])==c['file_SHA'];m=UNITS.index(c['MESS'])
   with np.load(OUT/c['file']) as z:self.master.add(m,z['x'],z['a'],float(z['c']),c['SHA256'])
   self.seen[m].add(c['SHA256'])
  if cp['smooth_file']:
   with np.load(OUT/cp['smooth_file']) as z:self.smooth_pi=z['pi'];self.smooth_conv=z['alpha']
   self.smooth_file=cp['smooth_file'];self.smooth_key=cp['smooth_key'];assert hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest()==self.smooth_key
  if (OUT/'DW_PHASE_STATE.json').exists():
   phase=read(OUT/'DW_PHASE_STATE.json')
   if not phase['committed']:
    assert phase['true_dual_SHA']==cp['RMP']['dual_SHA'];self.resume_phase=phase
    with np.load(OUT/phase['search_file']) as z:self.smooth_pi=z['pi'];self.smooth_conv=z['alpha']
    self.smooth_weight=phase['alpha_next'];self.smoothing_rows=phase['smoothing_rows'];self.smooth_file=phase['search_file'];self.smooth_key=phase['search_key']
  write('DW_RESUME_RECEIPT.json',dict(PASS=True,conservative_budget_debit=self.budget_carried,checkpoint_type=cp['type'],recover_uncommitted_phase=bool(self.resume_phase),no_second_budget_grant=True))
 def authority_rmp(self):
  return next(r for r in reversed(self.rmps) if r['status']==2)
 def last_completed_dual(self):
  row=self.authority_rmp();assert sha(OUT/row['point_file'])==row['point_SHA']
  with np.load(OUT/row['point_file']) as z:pi=z['pi'];alpha=z['alpha']
  self.previous_pi=pi.copy()
  prior=[r for r in self.rmps if r['status']==2]
  file=OUT/prior[-2]['point_file'] if len(prior)>=2 else SCI/read(SCI/'DW_CHECKPOINT_LATEST.json')['RMP']['point_file']
  with np.load(file) as z:self.last_true_pi=z['pi'].copy()
  return pi,alpha,row['dual_SHA'],row['point_file']
 def resume_dual(self):
  cp=self.resume_checkpoint
  # Successful points/calls are NEVER optimized again. Only the LP whose native
  # terminal TIME_LIMIT provided no authoritative point is completed on its
  # exact preserved append-only pool; the previous60s debit remains charged.
  if cp['RMP']['status']!=2 or cp['type']=='DISCOVERY_ADDED':
   failed=cp['RMP'];self.pending_new=[c['SHA256'] for c in self.columns if c['round']==failed['round']-1]
   self.uppers=[read(SCI/'DW_THRESHOLD_FINAL_RESULT.json')['smallest_RMP_upper']]+[r['objective'] for r in self.rmps if r['status']==2 and r['type']!='INITIAL_TRUE_RMP']
   self.last_completed_dual();dual=self.solve_master('RESUME_INCOMPLETE_RMP')
   if dual is not None:
    self.uppers.append(self.bestU)
    if self.rounds:
     self.rounds[-1].update(recovered_post_RMP_round=self.current_round,U_after=self.bestU,D_U=self.bestU-self.authority['T_cert'],incomplete_native_call_retained=failed['round'],early_certification_trigger=early_trigger(self.accepted,self.uppers,self.authority['T_cert']))
   else:
    self.stop=None;self.force_final_after_incomplete=True;dual=self.last_completed_dual()
   self.checkpoint('RECOVER_POST_DISCOVERY');return dual
  return self.last_completed_dual()
 def full_pool_final(self):
  if not any(r['status']==2 for r in self.rmps):
   write('DW_FULL_POOL_FINAL_AUDIT.json',dict(PASS=False,reason='NO_OPTIMAL_RMP_AUTHORITY'));return
  row=self.authority_rmp()
  with np.load(OUT/row['point_file']) as z:pi=z['pi'];alpha=z['alpha']
  audit=self.tier_audit('FINAL_CHECKPOINT',pi,alpha,row['dual_SHA']);write('DW_FULL_POOL_FINAL_AUDIT.json',dict(PASS=True,columns=len(self.master.column_data),audit=audit,current_true_RC=self.current_RC_rows,no_column_deletion=True,true_dual_origin_RMP=row['round'],latest_RMP_optimal=self.rmps[-1]['status']==2,point_extension='new column lambdas zero on last completed primal point'))
 def runtime_receipts(self):
  rows=[]
  for p in self.prices:
   rows.append(dict(call=p['call'],round=p['round'],MESS=p['MESS'],type=p['type'],native_status=p['native_status'],accepted=p.get('early_stop',{}).get('accepted_count',0),stop_reason=p.get('early_stop',{}).get('STOP_REASON'),pricing_start=p['timing']['start'],first_raw_incumbent=p['timing']['first_raw_incumbent'],accepted_times=json.dumps(p['timing']['accepted_candidate_timestamps']),quota_fill=p['timing']['quota_fill_time'],terminate_request=p['timing']['terminate_request_time'],native_terminal=p['timing']['native_terminal'],actual_seconds=p['wall_seconds'],cap=p['settings']['TimeLimit'],saved_wall_diagnostic=p['pricing_saved_wall_estimate'],valid_bound=p['valid_bound'],true_dual_SHA=p['true_dual_SHA']))
  table('DW_EARLY_STOP_FULLSCALE_LEDGER.csv',rows)

 def authority_rmp(self):
  return next((r for r in reversed(self.rmps) if r['status']==2),self.initial_rmp)
 def last_completed_dual(self):
  row=self.authority_rmp();assert sha(OUT/row['point_file'])==row['point_SHA']
  with np.load(OUT/row['point_file']) as z:pi=z['pi'];alpha=z['alpha']
  self.previous_pi=pi.copy()
  completed=[r for r in self.rmps if r['status']==2]
  prior=OUT/completed[-2]['point_file'] if len(completed)>=2 else SCI/self.initial_rmp['point_file'].split('/')[-1] if completed else SCI/'RMP_POINT_0013.npz'
  with np.load(prior) as z:self.last_true_pi=z['pi'].copy()
  return pi,alpha,row['dual_SHA'],row['point_file']
 def restore_run(self):
  self.resume_phase=None
  if not self.resume_checkpoint:return
  cp=self.resume_checkpoint;assert cp['authority_key']==self.audit_authority.key and cp['feature_selection_SHA']==sha(OUT/'DW_RUNTIME_FEATURE_SELECTION.json')
  self.budget_carried=cp['elapsed_budget'];self.wall_carried=cp['elapsed_wall']
  if (OUT/'DW_BUDGET_JOURNAL.json').exists():self.budget_carried=max(self.budget_carried,read(OUT/'DW_BUDGET_JOURNAL.json')['elapsed_budget'])
  if (OUT/'DW_INFLIGHT.json').exists():
   flight=read(OUT/'DW_INFLIGHT.json');self.budget_carried=max(self.budget_carried,flight['spent_before']+flight['reserved_optimize_seconds'])
  assert self.budget_carried<=BUDGET
  state=cp['restart_state']
  for k in ['rmps','prices','rounds','columns','certs','canaries','capture_ledger','smoothing_rows','accepted','uppers']:setattr(self,k,state[k])
  self.audit_rows=state.get('audit_rows',[]);self.validation_rows=state.get('validation_rows',[]);self.checkpoint_timings=state.get('checkpoint_timings',[])
  self.current_round=cp['RMP']['round'];self.call=max([52]+[p['call'] for p in self.prices]);self.column_id=189+len(self.columns);self.bestL,self.bestU=cp['best_interval'];self.best_corr=cp['best_corrected_LB'];self.smooth_weight=cp['alpha_next']
  for c in self.columns:
   assert sha(OUT/c['file'])==c['file_SHA'];m=UNITS.index(c['MESS'])
   with np.load(OUT/c['file']) as z:self.master.add(m,z['x'],z['a'],float(z['c']),c['SHA256'])
   self.seen[m].add(c['SHA256'])
  with np.load(OUT/cp['smooth_file']) as z:self.smooth_pi=z['pi'];self.smooth_conv=z['alpha']
  self.smooth_file=cp['smooth_file'];self.smooth_key=cp['smooth_key'];assert hashlib.sha256(self.smooth_pi.tobytes()+self.smooth_conv.tobytes()).hexdigest()==self.smooth_key
  if (OUT/'DW_PHASE_STATE.json').exists():
   phase=read(OUT/'DW_PHASE_STATE.json')
   if not phase['committed']:
    assert phase['true_dual_SHA']==cp['RMP']['dual_SHA'];self.resume_phase=phase
    with np.load(OUT/phase['search_file']) as z:self.smooth_pi=z['pi'];self.smooth_conv=z['alpha']
    self.smooth_weight=phase['alpha_next'];self.smoothing_rows=phase['smoothing_rows'];self.smooth_file=phase['search_file'];self.smooth_key=phase['search_key']
  self.last_completed_dual()
  write('DW_RESUME_RECEIPT.json',dict(PASS=True,new_budget_conservative_debit=self.budget_carried,historical_PR149=self.historical_optimize,no_second_new_grant=True,completed_pricing_replayed=False))
 def resume_dual(self):
  cp=self.resume_checkpoint
  if cp['type']=='DISCOVERY_ADDED' or cp['RMP']['status']!=2:
   self.pending_new=[c['SHA256'] for c in self.columns if c['round']==max(x['round'] for x in self.columns)]
   file=OUT/f'RMP_RECEIPT_{self.current_round+1:04d}.json'
   if file.exists() and read(file)['status']==2:
    row=read(file);assert sha(OUT/row['point_file'])==row['point_SHA'];self.rmps.append(row);self.current_round=row['round'];self.bestU=min(self.bestU,row['objective']);self.uppers.append(self.bestU);return self.last_completed_dual()
   dual=self.solve_master('RESUME_INCOMPLETE_RMP')
   if dual is not None:self.uppers.append(self.bestU)
   return dual or self.last_completed_dual()
  return self.last_completed_dual()
 def suspend_models(self):
  import gc
  self.close_workers();self.master.model.dispose();del self.persistent_adapter;del self.master;gc.collect();self.runtime_suspended=True
 def restore_models(self):
  from v42_dw_resume.audit import Master
  from v42_dw_accelerated.persistent import FullScalePersistentRMP
  self.master=Master(self.B,self.e,self.owner,self.row_owner,self.native)
  for directory,h in old_columns():
   m=UNITS.index(h['MESS'])
   with np.load(directory/h['file']) as z:self.master.add(m,z['x'] if 'x' in z else z['local_values'],z['a'] if 'a' in z else z['master_coefficients'],float(z['c'] if 'c' in z else z['objective']),h['SHA256'])
  for c in self.columns:
   with np.load(OUT/c['file']) as z:self.master.add(UNITS.index(c['MESS']),z['x'],z['a'],float(z['c']),c['SHA256'])
  self.persistent_adapter=FullScalePersistentRMP(self.master);self.runtime_suspended=False
 def full_pool_final(self):
  row=self.authority_rmp()
  with np.load(OUT/row['point_file']) as z:pi=z['pi'];alpha=z['alpha']
  audit=self.tier_audit('FINAL_CHECKPOINT',pi,alpha,row['dual_SHA']);write('DW_FULL_POOL_FINAL_AUDIT.json',dict(PASS=True,columns=len(self.master.column_data),audit=audit,current_true_RC=self.current_RC_rows,no_column_deletion=True,true_dual_origin_RMP=row['round']))
 def continuation_receipts(self):
  result=read(OUT/'DW_ACCELERATED_FINAL_RESULT.json');result.update(historical_PR149_optimize=self.historical_optimize,new_authorized_optimize=1800,new_consumed_optimize=self.spent(),cumulative_optimize=self.historical_optimize+self.spent(),B1_untouched=True,B2_B3_calls=[0,0],new_negative_RC=[dict(MESS=p['MESS'],optimum=p['rc_inc'] if p['native_status']==2 else None,BestBd=p['ObjBound']) for p in self.prices if p['type']=='FINAL_CERTIFICATION'])
  write('DW_CONTINUATION_FINAL_RESULT.json',result);write('DW_CONTINUATION_FINAL_CERTIFICATION.json',read(OUT/'DW_ACCELERATED_FINAL_CERTIFICATION.json'));write('DW_CONTINUATION_FULL_POOL_AUDIT.json',read(OUT/'DW_FULL_POOL_FINAL_AUDIT.json'));write('DW_CONTINUATION_BUDGET_ACCOUNTING.json',dict(historical_PR149=self.historical_optimize,new_authorized=1800,new_consumed=self.spent(),new_remaining=self.remaining(),cumulative=self.historical_optimize+self.spent(),new_segments=read(OUT/'DW_OPTIMIZE_INTERVALS.json'),wait_budget=0,build_audit_elapsed=self.elapsed(),automatic_extension=False))
  table('DW_CONTINUATION_ITERATION_LEDGER.csv',self.rounds);table('DW_CONTINUATION_THRESHOLD_DISTANCE.csv',ledger('DW_ACCELERATED_CG_THRESHOLD_DISTANCE.csv'));table('DW_CONTINUATION_PRICING_LEDGER.csv',[dict(call=p['call'],round=p['round'],MESS=p['MESS'],type=p['type'],status=p['native_status'],BestBd=p['ObjBound'],feasible_RC=p['rc_inc'],valid_bound=p['valid_bound'],true_dual_SHA=p['true_dual_SHA'],wall=p['wall_seconds']) for p in self.prices])
