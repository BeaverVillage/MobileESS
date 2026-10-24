"""Continue an uncertified integer search over exact physical graph supersets."""
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
from dataclasses import replace
import gzip,pickle,inspect,textwrap,linecache,os
import ast
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
 verify([row['closed_state'],row['core_failure'],row['ledger'],row['old_request']]+list(row['certificates'].values()))
 old=read(parent/'request.json');account=read(row['ledger']['path'])
 for name in ('day','arm','iteration_stage','fixed_parent_receipt','equipment_version'):
  if old.get(name)!=request.get(name):raise PermissionError('INTEGER_CONTINUATION_CASE_DRIFT:'+name)
 for name in ('NATIVE_INPUT.json','WINDOWS.json'):
  a=record(Path(old['input_folder'])/name);b=record(Path(request['input_folder'])/name)
  if (a['bytes'],a['sha256'])!=(b['bytes'],b['sha256']):raise PermissionError('INTEGER_CONTINUATION_INPUT_DRIFT')
 if budget.native_used!=account['measured_Native_Runtime'] or budget.calls!=account['calls']:
  raise PermissionError('INTEGER_CONTINUATION_ACCOUNT_NOT_INHERITED')
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
 if controller is None or read(parent/'OUTPUT/R029_CONDITIONAL_VOLTAGE_PROGRESS.json')['approved_rows']:
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
 expected=read(parent/'OUTPUT/P1/INTEGER_CONTROL/MODEL_IDENTITY.json')['original_snapshot_sha256']
 if typed.fingerprint()!=expected:raise ValueError('INTEGER_CONTINUATION_TYPED_SNAPSHOT_DRIFT')


def restore_typed(state,request,original):
 if not request.get('_iteration2_integer_resume_parent'):return original(state,state['global_types'])
 parent=Path(request['_iteration2_integer_resume_parent'])/'OUTPUT'
 identity=read(parent/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json');verify([identity['attributes'],identity['matrix']])
 with np.load(identity['attributes']['path'],allow_pickle=False) as arrays:
  typed=replace(state['reference'],vtypes=arrays['vtypes'].copy()).require()
 verify_typed(typed,request)
 proof=read(parent/'ORIGINAL_INTEGER_TYPE_RESTORATION.json')
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
  self.required={r['class_id']:r for r in read(self.output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
  from v42_a_stage_compact_rowgen.lift import expanded_point
  step=Path(read(self.output/'P1_RESULT.json')['full_pricing']['path']).parent.parent
  model=read(step/'MODEL_IDENTITY.json')
  if model['original_snapshot_sha256']!=state['compact'].fingerprint():raise ValueError('INTEGER_SUPPORT_P1_POINT_MODEL_DRIFT')
  raw=read(step/'NATIVE_RESULT.json')['raw_attributes'];verify([raw])
  with np.load(raw['path'],allow_pickle=False) as saved:self.lp_point=expanded_point(state,saved['X'])

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
    "        _iteration2_search=_iteration2_integer_support.Support(request,state,output,exact_lb)\n        def validate(point, objective):",
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
            _next=_iteration2_search.expand(state,typed,_iteration2_initial)
            if _next is None:raise ValueError('INTEGER_CONTINUATION_HAS_NO_NEW_PHYSICAL_SUPPORT')
            state,typed,_warm=_next
            physical=Physical(state,typed)
            native.live_model=None;native.warm_basis=None;native.warm_point=_warm
            candidates.clear()
            validate(_warm,float(objective_value(typed,_warm,'rho')))
        while True:
            native.incumbent_callback = validate
            rec, raw = native.solve(typed, _iteration2_search.folder(), 'INTEGER_CONTROL')
            if 'X' in raw:
                _repair=_r029_restore(native,typed,raw['X'],_iteration2_search.folder()/'EXACT_INTEGER_REPAIR')
                if _repair is not None:
                    rec,raw=_repair;candidates.clear()
                validate(raw['X'], rec['objective'])
            if not _iteration2_search.need_more(candidates,rec,native):break
            with np.load(candidates[-1]['point']['path'],allow_pickle=False) as _saved:
                _point=_saved['X'].copy()
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
  if module.__name__!='v42_may_campaign_native90.a_stage' or name!='run':return original(module,name)
  function=inspect.unwrap(module.run);source=textwrap.dedent(inspect.getsource(function))
  if '_iteration2_search.expand(state,typed,_point)' not in source:raise ValueError('INTEGER_SUPPORT_ACTUAL_SELECTIVE_COMPILER_NOT_BOUND')
  tree=ast.parse(source).body[0]
  atomic(Path(request.get('root',request['output']))/'ITERATION2_INTEGER_SUPPORT_BINDING.json',dict(PASS=True,UTC=now(),
   binding='ACTUAL_A2_SELECTIVE_AST_COMPILER',source=record(__file__),day=request['day'],iteration_stage=request['iteration_stage'],
   original_integer_repair_retained=True,full_physical_and_gap_acceptance_retained=True))
  return tree
 with patch.object(adapter,'source_tree',source_tree):yield
