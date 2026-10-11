"""Exercise the actual candidate generator in a bounded nonproduction context."""
from pathlib import Path
import sys,copy,json
import numpy as np
SOURCE=Path(r'D:\v42_svr11_epoch13_20261011');sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest
from v42_common_campaign.authority import source_files
from v42_svr11.authority import scope
from v42_svr11 import model
OUT=Path(__file__).resolve().parent/'GENERATOR_CONNECTION';OUT.mkdir(exist_ok=True)
old=read(r'D:\v42_svr11_may_20261011_12\CAMPAIGN_MANIFEST.json');sources=source_files();source_sha=digest(sources)
h=read(old['hardware']['path']);h.update(source_SHA=source_sha,diagnostic_only=True)
atomic(OUT/'HARDWARE.json',h)
m=copy.deepcopy(old);m.update(root=str(OUT),code_root=str(SOURCE),execution_sources=sources,execution_SHA=source_sha,source_commit='UNRELEASED_CANDIDATE',hardware=record(OUT/'HARDWARE.json'),development_diagnosis_only=True,production_campaign=False)
m.pop('scientific_model_validation',None)
atomic(OUT/'CAMPAIGN_MANIFEST.json',m)
class BoundedDiagnosticComplete(Exception):pass
seen=[]
def progress(v):
 seen.append(v)
 if v.get('model_slot')==1:raise BoundedDiagnosticComplete()
with scope(OUT/'CAMPAIGN_MANIFEST.json'):
 try:model.generate('2025-05-01',Path(old['root'])/'raw/2025-05-01',OUT/'model',progress)
 except BoundedDiagnosticComplete:pass
gold=Path(__file__).resolve().parent/'2025-05-01_SLOT_00_EXACT.npz';new=OUT/'model/SLOT_00.npz'
with np.load(gold) as a,np.load(new) as b:fields={f:a[f].tobytes()==b[f].tobytes() for f in model.FIELDS}
assert all(fields.values()) and seen[-1]['independent_compiles']==121
atomic(OUT/'GENERATOR_CONNECTION_VALIDATION.json',dict(PASS=True,candidate_source_SHA=source_sha,original_source_SHA=old['execution_SHA'],model_source=record(SOURCE/'v42_svr11/model.py'),independent_compiles=121,physical_solves=seen[-1]['physical_solves'],fields=fields,original_diagnostic=record(gold),generated_slot=record(new),production_campaign_started=False,previous_official_worker_changes=0))
print(json.dumps(read(OUT/'GENERATOR_CONNECTION_VALIDATION.json')),flush=True)
