from pathlib import Path
import json, pickle, collections, math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.production_case import STATIC, ARCHIVE
from v42_integration.unified_contract import REPORT, load_contracts
from v42_integration.policy import digest
with STATIC.open('rb') as f:
    data=pickle.load(f)
jobs=data[1]
source=json.loads((ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json').read_text(encoding='utf-8'))
rows={r['job_uid']:r for r in source['known_population']}
records=[]
for uid,j in jobs.items():
    r=rows[uid]
    records.append(dict(uid=uid,state=j.state,gpu=j.gpu,service_slots=j.service_slots,
        native_service_seconds=j.service_slots*900,V10_Q50_total_seconds=r['V10_Q50_total_seconds'],
        nominal_remaining_seconds=r['nominal_remaining_seconds'],elapsed_seconds=r['elapsed_seconds'],
        source_service_slots=r['service_slots'],duration_authority=j.duration_authority,
        t50_minus_native_seconds=r['V10_Q50_total_seconds']-j.service_slots*900,
        nominal_remaining_minus_native_seconds=r['nominal_remaining_seconds']-j.service_slots*900))
summary={}
for state in ('PENDING','RUNNING'):
    x=[r for r in records if r['state']==state]
    summary[state]=dict(UIDs=len(x),GPU=sum(r['gpu'] for r in x),
        native_GPUh=sum(r['native_service_seconds']*r['gpu']/3600 for r in x),
        public_Q50_GPUh=sum(r['V10_Q50_total_seconds']*r['gpu']/3600 for r in x),
        nominal_remaining_GPUh=sum(r['nominal_remaining_seconds']*r['gpu']/3600 for r in x),
        native_smaller_than_public=sum(r['native_service_seconds']<r['V10_Q50_total_seconds'] for r in x),
        native_larger_than_public=sum(r['native_service_seconds']>r['V10_Q50_total_seconds'] for r in x),
        exact_native_public=sum(r['native_service_seconds']==r['V10_Q50_total_seconds'] for r in x),
        native_raw_slot_mismatch=sum(r['service_slots']!=r['source_service_slots'] for r in x),
        max_native_minus_nominal_seconds=max(r['native_service_seconds']-r['nominal_remaining_seconds'] for r in x),
        native_service_slot_histogram=dict(collections.Counter(r['service_slots'] for r in x)),
        public_Q50_histogram=dict(collections.Counter(r['V10_Q50_total_seconds'] for r in x)))
out=dict(bindings=load_contracts()['bindings'],source_descriptor_path=str(STATIC),
    issue_source_template=str(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json'),
    summary=summary,rows=records,Native_calls=0,models_built=0,Actual_bank_read=False)
(REPORT/'KNOWN_SERVICE_AUTHORITY_ALIGNMENT_AUDIT.json').write_text(json.dumps(out,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(summary))
