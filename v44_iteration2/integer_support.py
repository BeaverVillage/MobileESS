"""Continue an uncertified integer search over exact physical graph supersets."""
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
from dataclasses import replace
import gzip,pickle,inspect,textwrap,linecache,os
import ast
import gc
from contextlib import contextmanager
from unittest.mock import patch
import numpy as np
from . import config as c
from .io import read,record,verify,atomic,now

BATCH_COLUMNS=20000


def continuation_row(parent):
 permit=read(read(c.OPS/'AUTHORIZATION.json')['repair_permit']['path'])
 row=next((r for r in permit['resumable_A_stages'] if Path(r['parent_core'])==Path(parent)),None)
 if not row or not row.get('integer_gap_continuation'):raise PermissionError('EXPLICIT_INTEGER_GAP_CONTINUATION_REQUIRED')
 return row


def load_closed(request,budget):
 parent=Path(request['_iteration2_integer_resume_parent']);row=continuation_row(parent)
 if row.get('integer_conflict_repair') or row.get('integer_physical_callback_repair'):request['_iteration2_retry_same_support']=True
 verify([row['closed_state'],row['core_failure'],row['ledger'],row['old_request']]+list(row['certificates'].values()))
 old=read(parent/'request.json');account=read(row['ledger']['path'])
 for name in ('day','arm','iteration_stage','fixed_parent_receipt','equipment_version'):
  if old.get(name)!=request.get(name):raise PermissionError('INTEGER_CONTINUATION_CASE_DRIFT:'+name)
 for name in ('NATIVE_INPUT.json','WINDOWS.json'):
  a=record(Path(old['input_folder'])/name);b=record(Path(request['input_folder'])/name)
  if (a['bytes'],a['sha256'])!=(b['bytes'],b['sha256']):raise PermissionError('INTEGER_CONTINUATION_INPUT_DRIFT')
 if budget.native_used!=account['measured_Native_Runtime'] or budget.calls!=account['calls']:
  raise PermissionError('INTEGER_CONTINUATION_ACCOUNT_NOT_INHERITED')
 checkpoint=row.get('integer_search_checkpoint')
 if checkpoint:
  verify([checkpoint,row['integer_model_identity'],row['integer_typeproof']])
  with gzip.open(checkpoint['path'],'rb') as stream:saved=pickle.load(stream)
  state=saved.pop('state');request['_iteration2_integer_search']=saved
  saved['_source_checkpoint']=checkpoint
  request['_iteration2_integer_model_identity']=row['integer_model_identity']
  request['_iteration2_integer_typeproof']=row['integer_typeproof']
 else:
  with gzip.open(row['closed_state']['path'],'rb') as stream:state=pickle.load(stream)
 output=Path(request['output']);output.mkdir(parents=True,exist_ok=True)
 for name in ('PHASE_I_ZERO_CERTIFICATE.json','PHASE_I_TRACE.json','PHASE_I_NATIVE_BUDGET.json','P1_RESULT.json','P1_TRACE.json','BLOCK_PRICING_ORACLE_VERIFICATION.json','A2_MODEL_VOLTAGE_POLICY.json'):
  atomic(output/name,read(parent/'OUTPUT'/name))
 cert=read(output/'P1_RESULT.json');verify([cert['full_pricing']]);priced=read(cert['full_pricing']['path'])
 if not (cert.get('PASS') and cert.get('P1_LP_closure') and priced.get('no_negative_omitted_block_certified')):
  raise PermissionError('INTEGER_CONTINUATION_REQUIRES_VALID_FULL_P1_CLOSURE')
 from v44_recovery_r029.voltage_policy import ACTIVE
 from v44_recovery_r029.model_difference import verify_state_policy
 controller=ACTIVE.get()
 voltage=row.get('voltage_progress')
 if voltage:verify([voltage])
 if controller is None or read(voltage['path'] if voltage else parent/'OUTPUT/R029_CONDITIONAL_VOLTAGE_PROGRESS.json')['approved_rows']:
  raise PermissionError('INTEGER_CONTINUATION_REQUIRES_SAME_STRICT_VOLTAGE_MODEL')
 controller.bind(state);verify_state_policy(state,output,controller=controller)
 policy=read(output/'A2_MODEL_VOLTAGE_POLICY.json')
 atomic(output/'A2_MODEL_VOLTAGE_POLICY.json',dict(policy,initial_state_built_fresh=False,same_case_P1_checkpoint_resumed=True))
 atomic(output/'ITERATION2_INTEGER_CONTINUATION.json',dict(PASS=True,UTC=now(),parent_core=str(parent),
  closed_state=row['closed_state'],certificates=row['certificates'],ledger=row['ledger'],
  same_fixed_parent_and_input_bytes=True,new_PhaseI_or_P1_search=False,Native_budget_reset=False,
  inherited_Native_seconds=budget.native_used,full_physical_and_gap_revalidation_required=True))
 return state,priced


def prepare(request,budget,original,progress):
 if request.get('_iteration2_integer_resume_parent'):return load_closed(request,budget)
 return original(dict(request,_budget=budget),progress),None


def persist_closed(path,state,request,original):
 if not request.get('_iteration2_integer_resume_parent'):return original(path,state)
 source=Path(continuation_row(request['_iteration2_integer_resume_parent'])['closed_state']['path'])
 target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
 try:os.link(source,target)
 except OSError:
  import shutil
  shutil.copyfile(source,target)
 if (record(source)['bytes'],record(source)['sha256'])!=(record(target)['bytes'],record(target)['sha256']):
  raise ValueError('CLOSED_STATE_LOSSLESS_LINK_FAILED')


def verify_typed(typed,request):
 if not request.get('_iteration2_integer_resume_parent'):return
 parent=Path(request['_iteration2_integer_resume_parent'])
 identity=request.get('_iteration2_integer_model_identity')
 if identity:verify([identity])
 expected=read(identity['path'] if identity else parent/'OUTPUT/P1/INTEGER_CONTROL/MODEL_IDENTITY.json')['original_snapshot_sha256']
 if typed.fingerprint()!=expected:raise ValueError('INTEGER_CONTINUATION_TYPED_SNAPSHOT_DRIFT')


def restore_typed(state,request,original):
 if not request.get('_iteration2_integer_resume_parent'):return original(state,state['global_types'])
 parent=Path(request['_iteration2_integer_resume_parent'])/'OUTPUT'
 identity=read(request.get('_iteration2_integer_model_identity',{}).get('path',parent/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json'));verify([identity['attributes'],identity['matrix']])
 with np.load(identity['attributes']['path'],allow_pickle=False) as arrays:
  typed=replace(state['reference'],vtypes=arrays['vtypes'].copy()).require()
 verify_typed(typed,request)
 proof=read(request.get('_iteration2_integer_typeproof',{}).get('path',parent/'ORIGINAL_INTEGER_TYPE_RESTORATION.json'))
 if proof.get('PASS') is not True:raise PermissionError('VERIFIED_PARENT_INTEGER_RESTORATION_REQUIRED')
 return typed,dict(proof,same_case_type_proof_reused=True,exact_typed_snapshot_sha256=typed.fingerprint())


def resume_point(request):
 if not request.get('_iteration2_integer_resume_parent'):return None
 parent=Path(request['_iteration2_integer_resume_parent']);saved=read(parent/'RESULT.json')['incumbent']['point'];verify([saved])
 with np.load(saved['path'],allow_pickle=False) as arrays:return arrays['X'].copy()


def unique_incumbent(output):
 folder=Path(output)/'I'
 used=[int(p.stem[1:]) for p in folder.glob('V[0-9]*.npz') if p.stem[1:].isdigit()]
 return folder/('V'+str(max(used,default=0)+1))


def verify_candidate(physical,point,output):
 """An original physical rejection rejects this candidate, not the MIP run."""
 try:return physical.verify(point)
 except ValueError as error:
  # Only the diagnosed original factorized-state validator uses this prefix.
  # Unexpected implementation errors must still propagate and fail visibly.
  if not str(error).startswith('NONPHYSICAL_FACTORIZED_STATE:'):raise
  folder=Path(output)/'I';folder.mkdir(parents=True,exist_ok=True)
  stem=folder/('F'+str(len(list(folder.glob('F*.npz')))+1))
  np.savez_compressed(str(stem)+'.npz',X=point)
  proof=dict(PASS=False,UTC=now(),reason='ORIGINAL_PHYSICAL_CANDIDATE_REJECTED',error=str(error),
   point=record(str(stem)+'.npz'),original_snapshot_sha256=physical.snapshot.fingerprint(),
   candidate_accepted=False,original_raw_unchanged=True,tolerance_relaxed=False,
   action='CONTINUE_SOLVER_WITH_EXISTING_VERIFIED_INCUMBENT')
  atomic(str(stem)+'.json',proof)
  return proof


def defer_bound_conflict(native,snapshot,point,upper,lower,output):
 """Quarantine a tolerance-scale candidate; it is never an accepted UB."""
 if upper>=lower:return False
 if lower-upper>Fraction(1,1000000) or getattr(native,'_iteration2_conflict_polished',False):
  raise ValueError('A_CERTIFIED_LB_UB_CONFLICT')
 folder=Path(output)/'I';folder.mkdir(parents=True,exist_ok=True)
 stem=folder/('C'+str(len(list(folder.glob('C*.npz')))+1))
 np.savez_compressed(str(stem)+'.npz',X=point)
 proof=dict(UTC=now(),exact_candidate_value=str(upper),exact_full_domain_LB=str(lower),
  original_snapshot_sha256=snapshot.fingerprint(),point=record(str(stem)+'.npz'),
  candidate_accepted=False,lower_bound_modified=False,gap_target_relaxed=False,
  action='POST_NATIVE_EXACT_FIXED_INTEGER_NUMERICAL_POLISH')
 atomic(str(stem)+'.json',proof);native._iteration2_bound_conflict=proof
 if native.live_model is not None:native.live_model.terminate()
 return True


def repair_conflict(native,snapshot,point,folder,original):
 if not getattr(native,'_iteration2_bound_conflict',None):return original(native,snapshot,point,folder)
 from v44_recovery_r029.integer_repair import fixed_snapshot
 from v42_a_stage_phase1.core import primal_replay
 from .integer_native import POLISH
 fixed,integer,residual=fixed_snapshot(snapshot,point)
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
 callback=getattr(native,'incumbent_callback',None);warm=getattr(native,'warm_point',None)
 basis=getattr(native,'warm_basis',None)
 native.incumbent_callback=None;native.warm_point=None;native.warm_basis=None
 token=POLISH.set(True)
 try:rec,raw=native.solve(fixed,folder/'CONTINUOUS','INTEGER_CONTROL')
 finally:
  POLISH.reset(token);native.incumbent_callback=callback;native.warm_point=warm;native.warm_basis=basis
 if 'X' not in raw:raise ValueError('FIXED_INTEGER_CONFLICT_POLISH_NO_POINT')
 replay=primal_replay(snapshot,raw['X']);exact=np.array_equal(raw['X'][integer],np.rint(point[integer]))
 proof=dict(PASS=bool(replay['PASS'] and exact),UTC=now(),original_snapshot_sha256=snapshot.fingerprint(),
  fixed_snapshot_sha256=fixed.fingerprint(),original_rows=replay,integer_decisions_exact=bool(exact),
  previous_integer_residual=residual,original_conflict=native._iteration2_bound_conflict,
  shared_original_A5400_budget=True,lower_bound_modified=False,acceptance_relaxed=False,
  physical_and_gap_revalidation_required=True,native_result=record(folder/'CONTINUOUS/NATIVE_RESULT.json'))
 atomic(folder/'REPAIR_CERTIFICATE.json',proof)
 if not proof['PASS']:raise ValueError('FIXED_INTEGER_CONFLICT_POLISH_ORIGINAL_REPLAY_FAILED')
 native._iteration2_conflict_polished=True;native._iteration2_bound_conflict=None
 return rec,raw


def detach_lp_state(state):
 """All original data/physics stay live; dormant LP state stays on disk."""
 keep=dict(data=state['data'],atlas=dict(node_names=state['atlas']['node_names']),
  _campaign=state['_campaign'],_iteration2_offloaded=True)
 released=sorted(set(state)-set(keep));state.clear();state.update(keep)
 return released


def choose(required,state,scores,promoted,limit=BATCH_COLUMNS):
 chosen=[];columns=0
 for key in sorted(required,key=lambda k:(-scores.get(k,0.),k)):
  if key in promoted:continue
  row=required[key];uid=state['data'][7]['classes'][key][0]
  if state['data'][5][uid].sha==row['complete_graph_sha256']:continue
  size=row['complete_native_primitive_columns']
  # The batch cap never removes a scientific class, including an oversized one.
  if chosen and columns+size>limit:continue
  chosen.append(key);columns+=size
  if columns>=limit:break
 return chosen


class Support:
 def __init__(self,request,state,output,exact_lb):
  self.request=request;self.output=Path(output);self.exact_lb=exact_lb
  self.round=0;self.promoted=set();self.history=[]
  self.checkpoint=None;self.checkpoint_round=None;self.checkpoint_payload=True;self.typed_sha=None
  self.required={r['class_id']:r for r in read(self.output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
  saved=request.pop('_iteration2_integer_search',None)
  if saved:
   from v42_a_stage_phase1.core import primal_replay
   self.round=saved['round'];self.promoted=set(saved['promoted']);self.history=saved['history'];self.lp_point=saved['lp_point']
   self.checkpoint=saved.get('_source_checkpoint');self.checkpoint_round=self.round
   if (not primal_replay(state['reference'],self.lp_point)['PASS'] or
       self.promoted!={key for row in self.history for key in row['classes']} or
       self.round!=self.history[-1]['round']):raise ValueError('INTEGER_SEARCH_CHECKPOINT_STATE_DRIFT')
   self.resumed_support=True
   return
  self.resumed_support=False
  from v42_a_stage_compact_rowgen.lift import expanded_point
  step=Path(read(self.output/'P1_RESULT.json')['full_pricing']['path']).parent.parent
  model=read(step/'MODEL_IDENTITY.json')
  if model['original_snapshot_sha256']!=state['compact'].fingerprint():raise ValueError('INTEGER_SUPPORT_P1_POINT_MODEL_DRIFT')
  raw=read(step/'NATIVE_RESULT.json')['raw_attributes'];verify([raw])
  with np.load(raw['path'],allow_pickle=False) as saved:self.lp_point=expanded_point(state,saved['X'])

 def persist(self,state,typed):
  """Keep only the latest exact search state, distinct from the P1 checkpoint."""
  target=self.output/'STATIC/INTEGER_SEARCH_STATE.pkl.gz';target.parent.mkdir(parents=True,exist_ok=True)
  expected=None
  if self.checkpoint and self.checkpoint_round==self.round:
   source=Path(self.checkpoint['path']);expected=self.checkpoint
   if source!=target:
    try:os.link(source,target)
    except OSError:
     import shutil
     shutil.copyfile(source,target)
  else:
   temporary=target.with_suffix('.tmp')
   with gzip.open(temporary,'wb',compresslevel=1) as stream:
    pickle.dump(dict(state=state,lp_point=self.lp_point,round=self.round,history=self.history,promoted=self.promoted),stream,protocol=5)
   os.replace(temporary,target)
  current=record(target)
  if expected and (current['bytes'],current['sha256'])!=(expected['bytes'],expected['sha256']):raise ValueError('INTEGER_CHECKPOINT_LOSSLESS_LINK_FAILED')
  self.checkpoint=current;self.checkpoint_round=self.round;self.checkpoint_payload=True;self.typed_sha=typed.fingerprint()
  atomic(self.output/'INTEGER_SEARCH_CHECKPOINT.json',dict(PASS=True,UTC=now(),state=self.checkpoint,
   typed_snapshot_sha256=self.typed_sha,round=self.round,Native_budget_reset=False,
   complete_graphs_retained=True,P1_certificate_recomputed=False))
  atomic(self.output/'ITERATION2_INTEGER_SUPPORT.json',dict(PASS=True,UTC=now(),rounds=self.history,
   original_gap_target=.005,Native_ceiling=5400,Native_budget_reset=False,all_native_calls_in_same_account=True))

 def offload(self,state,typed,physical):
  if self.round==0:
   self.checkpoint=record(self.output/'STATIC/P1_CLOSED_STATE.pkl.gz');self.checkpoint_round=0;self.checkpoint_payload=False
   self.typed_sha=typed.fingerprint()
  if not self.checkpoint or self.checkpoint_round!=self.round:raise ValueError('COMPLETE_INTEGER_STATE_BACKUP_REQUIRED')
  if physical.state is not state:raise ValueError('INTEGER_PHYSICAL_STATE_IDENTITY_DRIFT')
  released=detach_lp_state(state);gc.collect()
  atomic(self.output/'INTEGER_WORKING_STATE.json',dict(PASS=True,UTC=now(),round=self.round,checkpoint=self.checkpoint,
   released_LP_only_keys=released,original_physical_data_retained=True,original_typed_snapshot_sha256=self.typed_sha,
   scientific_option_deletion=False,complete_state_rehydrated_before_any_expansion=True))

 def restore(self,state,typed):
  if not state.get('_iteration2_offloaded'):return state
  if typed.fingerprint()!=self.typed_sha:raise ValueError('CURRENT_INTEGER_SNAPSHOT_DRIFT')
  verify([self.checkpoint])
  with gzip.open(self.checkpoint['path'],'rb') as stream:saved=pickle.load(stream)
  full=saved.pop('state') if self.checkpoint_payload else saved
  restored=replace(full['reference'],vtypes=typed.vtypes).require()
  if restored.fingerprint()!=self.typed_sha:raise ValueError('REHYDRATED_INTEGER_SNAPSHOT_DRIFT')
  full['_campaign']=state['_campaign'];state.clear();state.update(full)
  return state

 def folder(self):
  return self.output/'P1/INTEGER_CONTROL' if self.round==0 else self.output/'P1/INTEGER_SUPPORT'/('R'+str(self.round))

 def need_more(self,candidates,record,native):
  if not candidates or candidates[-1]['acceptance']['PASS']:return False
  if record.get('status') not in (2,9,11):return False
  return native.remaining()>0

 def expand(self,state,typed,point):
  from v42_a_stage_phase1.runner import load_cache
  from v42_a_stage_domain_v2.domain import graph_content_hash
  from v44_recovery_r031.p1_expansion import contains
  from v42_a_stage_compact_rowgen.assembly import compact_inverse
  from v42_a_stage_early.progress import artificial_free_inclusion
  from v42_a_stage_practical.integer_model import restore_types
  from v42_a_stage_phase1.core import primal_replay
  from v42_a_stage_canary.phase import activate
  scores={}
  for key,meta in state['metas'].items():
   ids=np.asarray(meta['reference_columns'],dtype=np.int64);ids=ids[typed.vtypes[ids]!='C']
   scores[key]=float(np.abs(self.lp_point[ids]-np.rint(self.lp_point[ids])).sum())
  keys=choose(self.required,state,scores,self.promoted)
  if not keys:return None
  selected=[]
  for key in keys:
   row=self.required[key];cache=load_cache(row);graph=cache['graph']
   if graph_content_hash(graph)!=row['complete_graph_sha256'] or graph.sha!=row['complete_graph_sha256'] or cache['snapshot'].matrix.shape[1]!=row['complete_native_primitive_columns']:
    raise ValueError('INTEGER_COMPLETE_GRAPH_CACHE_IDENTITY_DRIFT')
   for uid in state['data'][7]['classes'][key]:contains(graph,state['data'][5][uid])
   selected.append(dict(class_id=key,graph=graph,support_sha256=graph.sha,price=Fraction(0)))
  self.round+=1;folder=self.folder();folder.mkdir(parents=True,exist_ok=False)
  new,_=activate(state,selected,compact_inverse(state,point),folder,max_batch=len(selected))
  witness,mapped=artificial_free_inclusion(state['reference'],state['reference_descriptor'],point,new['reference'],new['reference_descriptor'],state['n'])
  if not witness['PASS']:raise ValueError('INTEGER_SUPPORT_PRIOR_POINT_NOT_INCLUDED')
  lp_witness,lp_mapped=artificial_free_inclusion(state['reference'],state['reference_descriptor'],self.lp_point,new['reference'],new['reference_descriptor'],state['n'])
  if not lp_witness['PASS']:raise ValueError('INTEGER_SUPPORT_P1_POINT_NOT_INCLUDED')
  self.lp_point=lp_mapped
  new['_campaign']=state['_campaign']
  newtyped,proof=restore_types(new,new['global_types'])
  if not primal_replay(newtyped,mapped)['PASS']:raise ValueError('INTEGER_SUPPORT_MAPPED_POINT_REPLAY_FAILED')
  atomic(self.output/'ORIGINAL_INTEGER_TYPE_RESTORATION.json',proof)
  atomic(folder/'PRIOR_INTEGER_INCLUSION.json',witness)
  self.promoted.update(keys)
  self.history.append(dict(round=self.round,classes=keys,complete_native_columns=sum(self.required[k]['complete_native_primitive_columns'] for k in keys),
   prior_inclusion=record(folder/'PRIOR_INTEGER_INCLUSION.json'),same_full_domain_LB=str(self.exact_lb),
   active_MIP_bound_used_as_global=False,candidate_deletion=False,scientific_domain_changed=False))
  atomic(self.output/'ITERATION2_INTEGER_SUPPORT.json',dict(PASS=True,UTC=now(),rounds=self.history,
   original_gap_target=.005,Native_ceiling=5400,Native_budget_reset=False,all_native_calls_in_same_account=True))
  return new,newtyped,mapped


def compiler(original):
 def compile_(function):
  compiled=original(function);source=textwrap.dedent(inspect.getsource(compiled))
  edits={
   '            state = prepare(dict(request, _budget=budget), progress)':
    '            state,_iteration2_priced = _iteration2_integer_support.prepare(request,budget,prepare,progress)',
   "        state, _, expanded, priced = phase_group['run'](native, state, day)":
    "        if _iteration2_priced is None:\n            state, _, expanded, priced = phase_group['run'](native, state, day)\n        else:priced=_iteration2_priced",
   "        _dump_state(output / 'STATIC/P1_CLOSED_STATE.pkl.gz', state)":
    "        _iteration2_integer_support.persist_closed(output / 'STATIC/P1_CLOSED_STATE.pkl.gz',state,request,_dump_state)",
   "        atomic(output / 'ORIGINAL_INTEGER_TYPE_RESTORATION.json', typeproof)":
    "        atomic(output / 'ORIGINAL_INTEGER_TYPE_RESTORATION.json', typeproof)\n        _iteration2_integer_support.verify_typed(typed,request)",
   "        typed, typeproof = restore_types(state, state['global_types'])":
    "        typed,typeproof = _iteration2_integer_support.restore_typed(state,request,restore_types)",
   "        def validate(point, objective):":
    "        _iteration2_search=_iteration2_integer_support.Support(request,state,output,exact_lb)\n        native._iteration2_target=exact_lb/(1-Fraction(1,200)) if exact_lb>0 else None\n        def validate(point, objective):",
   "            verification = physical.verify(point)":
    "            verification = _iteration2_integer_support.verify_candidate(physical,point,output)",
   "            if upper < exact_lb:\n                raise ValueError('A_CERTIFIED_LB_UB_CONFLICT')":
    "            if _iteration2_integer_support.defer_bound_conflict(native,typed,point,upper,exact_lb,output):return",
   "            incarnation = output / 'I' / ('V' + str(len(candidates) + 1))":
    "            incarnation = _iteration2_integer_support.unique_incumbent(output)",
  }
  for old,new in edits.items():
   if source.count(old)!=1:raise ValueError('INTEGER_SUPPORT_COMPILER_BOUNDARY_DRIFT:'+old)
   source=source.replace(old,new)
  begin=source.index('        native.incumbent_callback = validate\n');end=source.index('        if candidates:\n            best = candidates[-1]',begin)
  source=source[:begin]+'''        _iteration2_initial=_iteration2_integer_support.resume_point(request)
        if _iteration2_initial is not None:
            validate(_iteration2_initial,float(objective_value(typed,_iteration2_initial,'rho')))
            if _iteration2_search.resumed_support or request.get('_iteration2_retry_same_support'):_warm=_iteration2_initial
            else:
                _next=_iteration2_search.expand(state,typed,_iteration2_initial)
                if _next is None:raise ValueError('INTEGER_CONTINUATION_HAS_NO_NEW_PHYSICAL_SUPPORT')
                state,typed,_warm=_next
            physical=Physical(state,typed)
            native.live_model=None;native.warm_basis=None;native.warm_point=_warm
            candidates.clear()
            validate(_warm,float(objective_value(typed,_warm,'rho')))
        while True:
            if candidates and candidates[-1]['acceptance']['PASS']:break
            if _iteration2_search.round:_iteration2_search.persist(state,typed)
            _next=None
            _iteration2_search.offload(state,typed,physical)
            native.incumbent_callback = validate
            rec, raw = native.solve(typed, _iteration2_search.folder(), 'INTEGER_CONTROL')
            if 'X' in raw:
                _repair=_iteration2_integer_support.repair_conflict(native,typed,raw['X'],_iteration2_search.folder()/'EXACT_INTEGER_REPAIR',_r029_restore)
                if _repair is not None:
                    rec,raw=_repair;candidates.clear()
                validate(raw['X'], rec['objective'])
            if not _iteration2_search.need_more(candidates,rec,native):break
            with np.load(candidates[-1]['point']['path'],allow_pickle=False) as _saved:
                _point=_saved['X'].copy()
            state=_iteration2_search.restore(state,typed)
            _next=_iteration2_search.expand(state,typed,_point)
            if _next is None:break
            state,typed,_warm=_next
            physical=Physical(state,typed)
            native.live_model=None;native.warm_basis=None;native.warm_point=_warm
            candidates.clear()
            validate(_warm,float(objective_value(typed,_warm,'rho')))
''' +source[end:]
  filename=__file__+'.run.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
  namespace=dict(compiled.__globals__);exec(compile(source,filename,'exec'),namespace)
  return namespace[compiled.__name__]
 return compile_


@contextmanager
def selective_scope(request):
 """Bind the actual A2 AST compiler to the complete adapted integer body."""
 from v44.frozen.v43_a2 import adapter
 original=adapter.source_tree
 def source_tree(module,name):
  if module.__name__=='v42_may_campaign_native90.a_stage' and name=='_native':
   from .integer_native import receipt_tree
   return receipt_tree(original(module,name))
  if module.__name__!='v42_may_campaign_native90.a_stage' or name!='run':return original(module,name)
  function=inspect.unwrap(module.run);source=textwrap.dedent(inspect.getsource(function))
  if '_iteration2_search.expand(state,typed,_point)' not in source:raise ValueError('INTEGER_SUPPORT_ACTUAL_SELECTIVE_COMPILER_NOT_BOUND')
  tree=ast.parse(source).body[0]
  atomic(Path(request.get('root',request['output']))/'ITERATION2_INTEGER_SUPPORT_BINDING.json',dict(PASS=True,UTC=now(),
   binding='ACTUAL_A2_SELECTIVE_AST_COMPILER',source=record(__file__),day=request['day'],iteration_stage=request['iteration_stage'],
   original_integer_repair_retained=True,full_physical_and_gap_acceptance_retained=True))
  return tree
 with patch.object(adapter,'source_tree',source_tree):yield
