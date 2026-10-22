"""Same-stage continuation. No live tree reconstruction or Native clock reset."""
from pathlib import Path
from contextlib import contextmanager
from . import config as c
from .io import read,record,verify,atomic

def admit(parent,request):
 from v44.checkpoints import assert_dead,crash_admission,ledger_state
 parent=Path(parent);assert_dead(parent);old=read(parent/'request.json')
 for k in ('iteration_stage','day','arm','source_sha','equipment_version','fixed_parent_stage','fixed_parent_receipt'):
  if old.get(k)!=request.get(k):raise PermissionError('SAME_PUBLIC_STAGE_SOURCE_PARENT_EQUIPMENT_REQUIRED:'+k)
 verify(old['sources']);request['scientific_case_root']=old.get('scientific_case_root',old['case_root'])
 if request['iteration_stage'].startswith('M'):
  identity=read(parent/'SCIENTIFIC_CASE_IDENTITY.json')
  if identity.get('iteration_stage')!=request['iteration_stage'] or identity.get('voltage_band')!=list(c.band(request['iteration_stage'])) or identity.get('equipment_version')!=c.EQUIPMENT:raise PermissionError('SAME_M_DOMAIN_REQUIRED')
  receipt=crash_admission(parent,request);request['resume_parent']=str(parent)
 else:
  receipt=ledger_state(parent/'NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
  if receipt['remaining']<=0:raise PermissionError('A_SAME_STAGE_NATIVE_BUDGET_EXHAUSTED')
 return receipt

@contextmanager
def a_scope(parent,request):
 from v44_recovery_r046.planning import a1_scope
 receipt=admit(parent,request)
 # Existing generic adapter retains both total A5400 and spent Phase-I1500.
 # It rebuilds the exact same model under remaining measured budgets; no
 # previous point/LB/certificate is promoted to another A Case.
 with a1_scope(parent):yield receipt

def m_request(parent,request):
 receipt=admit(parent,request)
 return receipt
