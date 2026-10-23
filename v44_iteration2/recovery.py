"""One explicit repair permit may requeue a diagnosed failed A stage once."""
from copy import deepcopy
from pathlib import Path
from . import config as c
from .io import read,verify,now

def requeue(state):
 auth=read(c.OPS/'AUTHORIZATION.json');reference=auth.get('repair_permit')
 if not reference:return
 verify([reference]);permit=read(reference['path'])
 for repair in permit['resumable_A_stages']:
  job=next(j for j in state['jobs'] if j['day']==repair['day']);stage=repair['stage'];item=job.get('stages',{}).get(stage)
  if not item or Path(item['root'])!=Path(repair['parent_core']).parent:continue
  if any(h.get('parent_core')==repair['parent_core'] for h in job.get('repair_history',[])):continue
  if item['status'] not in ('FAILED','ENTRY_FAILED') or job['status']!='PLANNING_FAILED':raise ValueError('REPAIR_REQUEUE_REQUIRES_EXACT_TERMINAL_FAILURE')
  from .resume import repair_source_bridge
  old=read(Path(repair['parent_core'])/'request.json');repair_source_bridge(repair['parent_core'],old,old)
  job.setdefault('repair_history',[]).append(dict(UTC=now(),parent_core=repair['parent_core'],stage=stage,
   original_failure=deepcopy(item),original_job_error=job.get('error'),repair_permit=reference,Native_budget_reset=False))
  item.update(status='REPAIR_PENDING',PASS=False,diagnosed_repair=True)
  job.update(status='REPAIR_QUEUED');job.pop('error',None)
