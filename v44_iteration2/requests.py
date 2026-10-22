"""Independent dated requests over the unchanged r043 scientific authority."""
from pathlib import Path
from . import config as c
from .io import read,record,verify,digest
from .authority import sources,validate

def canonical(rows):
 verify(rows);values={};aliases=[]
 for row in rows:
  actual=record(Path(row['path']).resolve())
  if any(actual[k]!=row[k] for k in ('bytes','sha256')):raise PermissionError('CANONICAL_SOURCE_BYTES_CHANGED')
  values[actual['path']]=actual
  if actual['path']!=row['path']:aliases.append(dict(original=row,canonical=actual))
 return list(values.values()),aliases

def make(day,stage,lease,*,parent=None,freeze=None,slot=None,resume=None):
 from .bootstrap import base
 from v44.config import axis
 # Inherit live, byte-pinned scientific policies. Never execute the B2 chain.
 r=read(c.B2_ROOT/'requests/2025-05-23_B2.json')
 for key in tuple(r):
  if key in ('resume_of','resume_parent','scientific_case_root','a2_checkpoint_parent','fresh_a2_parent','wall_resume_parent','actual_resume_parent','io_resume_M1_parent','sequence_mode','sequence_authorization','sequence825_authorization','io_recovery_authority'):r.pop(key)
 attempts=sorted((c.ROOT/day/'B3').glob('attempt[0-9][0-9][0-9]'))
 reserved=sorted((c.OPS/'attempt_reservations'/day).glob('attempt[0-9][0-9][0-9].json'))
 numbers=[int(p.name[7:10]) for p in attempts+reserved]
 number=max(numbers,default=0)+1
 dated=next(x for x in read(c.DOC/'SEVEN_DAY_INPUT_MANIFEST.json')['days'] if x['day']==day)
 r.update(day=day,arm='B3',worker_slot=1,lane='MAIN',campaign_root=str(c.ROOT),case_root=str(c.ROOT/day/'B3'/f'attempt{number:03d}'),
  lease=lease,axis=axis(day),iteration_stage=stage,experiment='V44_iteration2',MESS_units=list(c.FLEET),equipment_version=c.EQUIPMENT,
  iteration2_authorization=record(c.OPS/'AUTHORIZATION.json'),r038_phase='ACTUAL_PARALLEL' if stage=='ACTUAL' else 'PREPARE_SERIAL')
 rows=r['sources']+list(dated['files'].values())+sources()+[record(c.OPS/'AUTHORIZATION.json')]+base.sources()
 r['sources'],r['canonical_source_aliases']=canonical(rows);r['source_sha']=digest(r['sources'])
 if stage=='ACTUAL':
  r.update(M4_freeze=freeze,parallel_actual_slot=slot)
 else:
  r.update(fixed_parent_stage=c.PARENT[stage],fixed_parent_core=parent['path'],fixed_parent_receipt=parent)
 if resume:r['stage_resume_parent']=str(resume)
 validate(r);return r
