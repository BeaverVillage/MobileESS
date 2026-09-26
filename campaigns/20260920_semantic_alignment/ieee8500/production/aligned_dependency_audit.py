"""Dependency-scoped reuse gate; historical Actual-only drift is explicit."""
from pathlib import Path
import json,hashlib,time
P=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify():
 checks=[];excluded=[]
 for name in ('ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json','RECONSTRUCTION_FREEZE_MANIFEST.json'):
  for r in read(P/name)['files']:
   h=sha(r['path']);ok=h==r['sha256']
   if not ok:
    assert Path(r['path']).name=='actual_binding.py' and h=='5a4cb9d504191900898e126550183dfe383664b9975ac95a90e5d1a45ace47f5',('UNEXPLAINED_HISTORICAL_DRIFT',r['path'])
    excluded.append(dict(**r,current_sha256=h,classification='Actual-only historical audit correction; not a B0 DA/Fresh dependency',incident=read(P/'ACTUAL_AUDIT_SCALE_INCIDENT.json')))
   else:checks.append(r)
 copies=read(P.parent/'SOURCE_COPY_MANIFEST.json')['files']
 names={'electrical_engine.py','numerical_coefficients.py','full_electrical_rows.py','PCC_OVERLAY.dss','PCC_OVERLAY_INVENTORY.json','SCREENING_RULE.json','D1_AEMO_VIC1_FORECAST.json','MAY01_B0_AIDC_POWER.npz','AXES.json','LAYOUT.json'}
 electrical=[]
 for r in copies:
  f=Path(r['copy'])
  if f.name in names or 'coefficients' in f.parts or 'B0_REPLAY' in f.parts:
   assert sha(f)==r['original_sha256'],('B0_DEPENDENCY_DRIFT',str(f))
   electrical.append(dict(path=str(f),sha256=sha(f)))
 assert names<={Path(r['path']).name for r in electrical}
 report=dict(status='PASS',scope='B0_DA_FRESH_REUSE_ONLY',verified_historical_files=len(checks),explicit_historical_exclusions=excluded,unchanged_B0_electrical_dependencies=electrical,Actual_authorization_implied=False,updated_unix=time.time())
 (P/'B0_DEPENDENCY_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report
