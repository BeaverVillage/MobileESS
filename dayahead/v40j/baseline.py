"""Run in the pinned existing V35R3D environment, without changing it."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .contracts import LEGACY, LEGACY_CACHE, OUT, FEATURES9, Q
from .firewall import ReadFirewall, sha, write

def main():
    import dayahead
    dayahead.__path__.append(str(LEGACY/'dayahead'))
    source = LEGACY/'dayahead'
    reference = LEGACY_CACHE/'window_predictions/1742652000.parquet'
    normalized = LEGACY_CACHE/'kestrel_preissue_normalized.parquet'
    fw=ReadFirewall('baseline', [reference, normalized], [source]).install()
    try:
        from dayahead.v35r3d.runtime import run_windows, metric_summary, safe_runtime
        from dayahead.v35r3d.contracts import QUERY_FEATURE_FIELDS, RECIPE_CONTRACT
        assert list(QUERY_FEATURE_FIELDS) == FEATURES9
        print('Reading only the legacy pre-issue normalized table',flush=True)
        rows=pq.read_table(BytesIO(normalized.read_bytes())).to_pylist()
        expected=pq.read_table(BytesIO(reference.read_bytes())).to_pandas()
        assert all(r['end_time'] < datetime(2025,4,1,tzinfo=timezone.utc) for r in rows)
        print('Exact baseline reproduction, historical rows='+str(len(rows)),flush=True)
        reproduced, entries, equivalence=run_windows(rows,[datetime.fromtimestamp(1742652000,timezone.utc)],OUT/'baseline_reproduction',label='V40J_C0_REPRO')
        columns=['job_id','actual_runtime_seconds','point_runtime_seconds','requested_seconds']
        keys_equal=expected['job_id'].tolist()==reproduced['job_id'].tolist()
        p=expected['point_runtime_seconds'].to_numpy(dtype='<f8')
        r=reproduced['point_runtime_seconds'].to_numpy(dtype='<f8')
        exact=keys_equal and p.tobytes()==r.tobytes()
        diff=float(np.max(np.abs(p-r))) if keys_equal else None
        safe=np.array([safe_runtime(a,Q,b) for a,b in zip(r,reproduced.requested_seconds)])
        ceil=np.maximum(1,np.ceil(safe/900)).astype(np.int64)
        report={'status':'PASS' if exact and equivalence['PASS'] else 'FAIL',
          'prediction_bytes_identical':exact,'prediction_max_abs_difference':diff,'query_adapter_equivalence':equivalence,
          'reference_prediction_sha256':hashlib.sha256(p.tobytes()).hexdigest(),
          'reproduced_prediction_sha256':hashlib.sha256(r.tobytes()).hexdigest(),
          'reference_file_sha256':sha(reference),'training_input_sha256':sha(normalized),
          'features':FEATURES9,'recipe':RECIPE_CONTRACT,'q_seconds':Q,
          'safe_formula':'min(requested_seconds,max(point+q,900)); then max(1,ceil(safe/900))',
          'fallback':'sparse MoE route uses fitted pooled fallback; missing mandatory request input uses requested-walltime scheduler fallback',
          'support':'current MoE min_expert_rows=100; no V40J support guard retrofitted',
          'reference_metrics':metric_summary(expected),'reproduced_metrics':metric_summary(reproduced),
          'safe_coverage':float(np.mean(reproduced.actual_runtime_seconds<=safe)),
          'ceil_coverage':float(np.mean(reproduced.actual_runtime_seconds<=ceil*900)),
          'window':'2025-03-22T14:00:00Z/2025-03-22T20:00:00Z',
          'scope':'exact current algorithm and archived pre-May window; no frozen May prediction consulted',
          'candidate_comparison_authorized':bool(exact and equivalence['PASS'])}
        write('V40J_CURRENT_RUNTIME_BASELINE.json',report)
        print(json.dumps({k:report[k] for k in ['status','prediction_bytes_identical','prediction_max_abs_difference']}),flush=True)
    finally:
        fw.close()

if __name__=='__main__':
    main()
