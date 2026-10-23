"""Same-stage continuation. No live tree reconstruction or Native clock reset."""
from pathlib import Path
from contextlib import contextmanager
from . import config as c
from .io import read,record,verify,atomic

def repair_source_bridge(parent,old,request):
 auth=read(c.OPS/'AUTHORIZATION.json');permit=auth.get('repair_permit')
 if not permit:raise PermissionError('SAME_STAGE_SOURCE_CHANGE_NEEDS_DIAGNOSED_REPAIR')
 verify([permit]);policy=read(permit['path'])
 row=next((r for r in policy['resumable_A_stages'] if r['day']==request['day'] and r['stage']==request['iteration_stage'] and Path(r['parent_core'])==Path(parent)),None)
 if row is None or row['old_source_sha']!=old['source_sha']:raise PermissionError('UNAPPROVED_REPAIR_STAGE_OR_SOURCE')
 verify([row[k] for k in ('old_request','ledger','reconciliation','phase_budget')])
 if record(Path(parent)/'request.json')!=row['old_request']:raise PermissionError('REPAIR_PARENT_REQUEST_DRIFT')
 failure=read(Path(parent)/'RESULT.json')
 diagnosed=row.get('diagnosed_error',"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')")
 allowed=("ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')","ValueError('R029_NUMERICAL_OPTIMALITY_OR_PRIOR_POINT_DOMINANCE_NOT_VERIFIED')")
 if diagnosed not in allowed or failure.get('error')!=diagnosed:raise PermissionError('REPAIR_REQUIRES_EXACT_DIAGNOSED_P1_FAILURE')
 if row.get('core_failure'):
  verify([row['core_failure']])
  if record(Path(parent)/'RESULT.json')!=row['core_failure']:raise PermissionError('REPAIR_FAILURE_RECEIPT_DRIFT')
 if not policy.get('scientific_equations_domain_and_acceptance_unchanged') or policy.get('Native_budget_reset') is not False:raise PermissionError('REPAIR_MUST_KEEP_DOMAIN_AND_NATIVE_ACCOUNT')
 return row

def phase_account(parent):
 parent=Path(parent);ledger=read(parent/'NATIVE_RUNTIME_LEDGER.json');saved=read(parent/'OUTPUT/PHASE_I_NATIVE_BUDGET.json')
 calls=[];cursor=0
 # A continued account contains old P1 calls BEFORE its new Phase I. Read
 # the exact persisted Phase-I subaccount, then prove it against the full
 # ledger in order, rather than stopping at the first historical P1 call.
 for row in saved['calls']:
  component=row['label']
  while component.startswith('INHERITED_'):component=component[len('INHERITED_'):]
  if component not in ('PHASE_I','LOCAL_PRICING'):raise ValueError('PHASE_I_COMPONENT_DRIFT')
  if row.get('source'):verify([row['source']])
  for index in range(cursor,len(ledger['calls'])):
   native=ledger['calls'][index]
   if native['component']==component and abs(native['Native_Runtime']-row['Native_seconds'])<1e-7:
    cursor=index+1;break
  else:raise ValueError('PHASE_I_CALL_NOT_IN_NATIVE_ACCOUNT')
  calls.append(dict(label='INHERITED_'+component,Native_seconds=row['Native_seconds'],source=record(parent/'NATIVE_RUNTIME_LEDGER.json')))
 used=sum(r['Native_seconds'] for r in calls)
 if abs(used-saved['Native_seconds'])>1e-6:raise ValueError('PHASE_I_AND_LOCAL_PRICING_ACCOUNT_DRIFT')
 if abs(sum(r['Native_Runtime'] for r in ledger['calls'] if r['component']=='PHASE_I')-sum(r['Native_seconds'] for r in calls if r['label']=='INHERITED_PHASE_I'))>1e-6:raise ValueError('PHASE_I_SOLVE_OMITTED_FROM_ACCOUNT')
 return dict(used=used,calls=calls)

def budget_parent(parent):
 """An exact failed-model regression is paid from the same A account."""
 parent=Path(parent);auth=read(c.OPS/'AUTHORIZATION.json');reference=auth.get('repair_permit')
 if not reference:return parent
 verify([reference]);row=next((r for r in read(reference['path'])['resumable_A_stages'] if Path(r['parent_core'])==parent),None)
 if not row or not row.get('repaired_native_account'):return parent
 from v44.checkpoints import ledger_state
 verify([row['repaired_native_account'],row['diagnostic_result']]);proof=read(row['diagnostic_result']['path'])
 path=Path(row['repaired_native_account']['path']);account=read(path);old=read(parent/'NATIVE_RUNTIME_LEDGER.json')
 if account.get('parent_ledger')!=record(parent/'NATIVE_RUNTIME_LEDGER.json') or account['calls'][:len(old['calls'])]!=old['calls']:raise ValueError('REPAIR_DIAGNOSTIC_NATIVE_PREFIX_DRIFT')
 extra=account['calls'][len(old['calls']):]
 if not extra or any(r['component']!='ORIGINAL_P1' or r['label']!='SAME_MATRIX_DOMINANCE_REPAIR_REGRESSION' for r in extra):raise ValueError('REPAIR_DIAGNOSTIC_CALL_DRIFT')
 if not proof.get('PASS') or not proof.get('matrix_bounds_objective_unchanged') or proof.get('acceptance_relaxed') is not False:raise ValueError('FAILED_OR_RELAXED_NUMERICAL_REGRESSION')
 ledger_state(path,ceiling=5400.);return path.parent

def admit(parent,request):
 from v44.checkpoints import assert_dead,crash_admission,ledger_state
 parent=Path(parent);assert_dead(parent);old=read(parent/'request.json')
 if not parent.resolve().is_relative_to((c.ROOT/request['day']/'B3').resolve()):raise PermissionError('OLD_CAMPAIGN_RESUME_FORBIDDEN')
 for k in ('iteration_stage','day','arm','equipment_version','fixed_parent_stage','fixed_parent_receipt'):
  if old.get(k)!=request.get(k):raise PermissionError('SAME_PUBLIC_STAGE_SOURCE_PARENT_EQUIPMENT_REQUIRED:'+k)
 if old['source_sha']!=request['source_sha']:
  if not request['iteration_stage'].startswith('A'):raise PermissionError('M_SOURCE_CHANGE_CANNOT_RESTORE_OLD_BINARY')
  repair_source_bridge(parent,old,request)
 from .history import verify_historical
 verify_historical(old['sources']);request['scientific_case_root']=old.get('scientific_case_root',old['case_root'])
 if request['iteration_stage'].startswith('M'):
  identity=read(parent/'SCIENTIFIC_CASE_IDENTITY.json')
  if identity.get('iteration_stage')!=request['iteration_stage'] or identity.get('voltage_band')!=list(c.band(request['iteration_stage'])) or identity.get('equipment_version')!=c.EQUIPMENT:raise PermissionError('SAME_M_DOMAIN_REQUIRED')
  receipt=crash_admission(parent,request);request['resume_parent']=str(parent)
 else:
  receipt=ledger_state(budget_parent(parent)/'NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
  if receipt['remaining']<=0:raise PermissionError('A_SAME_STAGE_NATIVE_BUDGET_EXHAUSTED')
 return receipt

@contextmanager
def a_scope(parent,request):
 from v44_recovery_r046.planning import a1_scope
 from v44_recovery_r029 import phase_limit
 from unittest.mock import patch
 receipt=admit(parent,request)
 # Existing generic adapter retains both total A5400 and spent Phase-I1500.
 # It rebuilds the exact same model under remaining measured budgets; no
 # previous point/LB/certificate is promoted to another A Case.
 account=phase_account(parent);previous=phase_limit.phase_scope
 @contextmanager
 def exact_phase_scope(native,output):
  with previous(native,output) as limited:
   limited.context.update(used=account['used'],calls=account['calls'].copy())
   phase_limit.persist(limited.context);yield limited
 with a1_scope(budget_parent(parent)),patch.object(phase_limit,'phase_scope',exact_phase_scope):yield dict(receipt,inherited_Phase_I_Native_seconds=account['used'])

def m_request(parent,request):
 receipt=admit(parent,request)
 return receipt
