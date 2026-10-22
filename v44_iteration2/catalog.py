"""Resolve the precise preserved A1/M1/A2 behind each original Actual trace."""
from pathlib import Path
from . import config as c
from .archives import Store
from .io import atomic,read,record,digest,now
from .contracts import full_m

def build(store):
 rows=[]
 for day in c.DAYS:
  paths=[p for p in store.paths(day,'RESULT.json') if p.parent.parent.name.casefold()=='b3']
  pairs=[(p,store.read(p)) for p in paths]
  good=[(p,r) for p,r in pairs if r.get('PASS') is True]
  candidates=good or [(p,r) for p,r in pairs if store.exists(p.parent/'ACTUAL/CASE/CASE_BINDINGS.json')]
  if not candidates:raise ValueError('ORIGINAL_B3_ACTUAL_EVIDENCE_MISSING:'+day)
  result,value=max(candidates,key=lambda x:int(x[0].parent.name[-3:]))
  case=result.parent;bindings=store.read(case/'ACTUAL/CASE/CASE_BINDINGS.json')
  a2ref=bindings['Final_AIDC_reference'];a2=Path(a2ref['path']).parent.parent
  ar=store.read(a2/'RESULT.json');request=store.read(a2/'request.json')
  if ar.get('day')!=day or ar.get('stage')!='A2' or ar.get('arm')!='B3':raise ValueError('A2_SOURCE_DATE_STAGE_DRIFT')
  mref=request.get('M1_result');m1=Path(mref['path']).parent if isinstance(mref,dict) else a2.parent/'M1'
  mr=store.read(m1/'RESULT.json');plan=full_m(mr,day)
  if ar['fixed_M1_plan_sha']!=plan['plan_sha']:raise ValueError('REUSED_M1_A2_BINDING_DRIFT')
  domain=request['physical_domain_request'];proofref=request['physical_cache_case_proof'];proof=store.read(proofref['path'])
  a1=Path(proof['result']['path']).parent;a1r=store.read(a1/'RESULT.json')
  if not (a1r.get('PASS') and a1r.get('FULL_feasible') and a1r.get('independent_Global_LB_validated') and a1r.get('certified_gap',1)<=.005):raise ValueError('ORIGINAL_A1_NOT_CERTIFIED:'+day)
  evidence=[store.record(p) for p in (result,case/'ACTUAL/CASE/CASE_BINDINGS.json',a1/'RESULT.json',m1/'RESULT.json',a2/'RESULT.json',a2/'request.json',Path(a2ref['path']),Path(proofref['path']))]
  if (store.record(a2ref['path'])['sha256'],store.record(a2ref['path'])['bytes'])!=(a2ref['sha256'],a2ref['bytes']):raise ValueError('FROZEN_A2_BYTES_DRIFT')
  if (store.record(proofref['path'])['sha256'],store.record(proofref['path'])['bytes'])!=(proofref['sha256'],proofref['bytes']):raise ValueError('DOMAIN_PROOF_BYTES_DRIFT')
  comparison=case;hardware='V44_ORIGINAL_MESS_TX750'
  if day in ('2025-05-29','2025-05-30'):
   comparison=Path('D:/MobileESS_V44/runtime/equipment_versions')/c.EQUIPMENT/'campaign007_fixed750_B3_revalidation'/day/'B3/attempt001'
   v=read(comparison/'RESULT.json')
   if v.get('PASS') is not True:raise ValueError('VERIFIED_825_COMPARISON_REQUIRED:'+day)
   hardware=c.EQUIPMENT;evidence.append(record(comparison/'RESULT.json'))
  rows.append(dict(day=day,original_case=str(case),A1=str(a1),M1=str(m1),A2=str(a2),
   physical_domain_request=domain,physical_cache_case_proof=proofref,AIDC_reference=a2ref,
   M1_plan_sha=plan['plan_sha'],reused_stages=['A1','M1','A2'],new_reuse_Native_calls=0,
   comparison_case=str(comparison),comparison_equipment=hardware,new_equipment=c.EQUIPMENT,
   equipment_equal=hardware==c.EQUIPMENT,evidence=evidence))
 return dict(schema='V44_ITERATION2_PRESERVED_SOURCE_CATALOG_V1',UTC=now(),days=rows,
  MESS_units=list(c.FLEET),B1_new_execution_allowed=False,archived_originals_modified=False)

def prepare():
 c.DOC.mkdir(parents=True,exist_ok=True);c.OPS.mkdir(parents=True,exist_ok=True)
 store=Store()
 try:
  catalogue=build(store);atomic(c.DOC/'BASELINE_CATALOG.json',catalogue)
  manifests=[Path('D:/v44_may01_07_prepare_20261016/docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')]+[c.OLD/n/'DOCUMENTS/SEVEN_DAY_INPUT_MANIFEST.json' for n in ('campaign005_may08_14','campaign006_may15_21','campaign007_may22_31')]
  rows={r['day']:r for p in manifests for r in read(p)['days']}
  if set(rows)!=set(c.DAYS):raise ValueError('EXACT_31_DAILY_INPUTS_REQUIRED')
  atomic(c.DOC/'SEVEN_DAY_INPUT_MANIFEST.json',dict(schema='V44_ITERATION2_31_DAY_MANIFEST',days=[rows[d] for d in c.DAYS],source_manifests=[record(p) for p in manifests]))
  olddoc=Path('D:/v44_may01_07_prepare_20261016/docs/v44')
  (c.DOC/'SCIENTIFIC_FREEZE_MANIFEST.json').write_bytes((olddoc/'SCIENTIFIC_FREEZE_MANIFEST.json').read_bytes())
  atomic(c.DOC/'PREPARATION.json',dict(PASS=True,UTC=now(),Native_calls=0,Actual_or_Fresh_calls=0,dates=31,
   catalog=record(c.DOC/'BASELINE_CATALOG.json'),input_manifest=record(c.DOC/'SEVEN_DAY_INPUT_MANIFEST.json'),archive_extraction_during_B2=False))
  return catalogue
 finally:store.close()
