"""Physical admission depends on causal source fields, never results or flexibility."""
import math
from v42_april_port.builder import timestamp
from v42_final.common import MODEL

def classify(row, raw, capacities, racks, available):
    fields = {}
    gpu = raw.get('gpus_requested') if raw else None
    missing_gpu = gpu is None or (isinstance(gpu, float) and not math.isfinite(gpu))
    fields['requested_GPU'] = 'ABSENT' if missing_gpu else 'PRESENT'
    reasons = []
    if not raw or not row.get('job_uid'):
        reasons.append('STABLE_EXACT_SOURCE_IDENTITY_ABSENT')
    else:
        try:
            if timestamp(raw['submit_time']) != timestamp(row['submit_time']):
                reasons.append('SUBMISSION_IDENTITY_CONFLICT')
            event = timestamp(row['runtime_inference_event_time'])
            if timestamp(row['submit_time']) > event or timestamp(available) > event:
                reasons.append('CAUSAL_RUNTIME_INPUT_UNAVAILABLE')
        except (ValueError, KeyError, TypeError):
            reasons.append('CAUSAL_TIMESTAMP_ABSENT')
    positive = (not isinstance(gpu, bool) and isinstance(gpu, (int, float)) and
                math.isfinite(gpu) and gpu > 0 and int(gpu) == gpu)
    if not positive:
        reasons.append('MISSING_GPU_REQUEST' if missing_gpu else 'INVALID_GPU_REQUEST')
    elif row['GPU_gang'] != int(gpu):
        raise ValueError('IMMUTABLE_RAW_GPU_CONFLICT')
    compatible = [s for s in sorted(capacities) if positive and int(gpu) <= capacities[s]
                  and any(int(gpu) <= r for r in racks[s])]
    if positive and not compatible:
        reasons.append('NO_COMPATIBLE_CURRENT_WHOLE_GANG_RACK_SITE')
    if raw and 'h100' not in str(raw.get('partition', '')).lower():
        reasons.append('GPU_TYPE_AUTHORITY_UNAVAILABLE')
    q = row.get('Q50_total_seconds'); n = row.get('service_slots')
    if row.get('runtime_authority') != MODEL or not isinstance(q, (int,float)) or not math.isfinite(q) or q < 0 or type(n) is not int or n < 0:
        reasons.append('CURRENT_RUNTIME_SERVICE_AUTHORITY_UNAVAILABLE')
    if row.get('source_site') and row['source_site'] not in compatible:
        reasons.append('SOURCE_SITE_RESOURCE_INCOMPATIBLE')
    return dict(modelable=not reasons, classification='J_PHYSICAL' if not reasons else
                'UNMODELABLE_MISSING_GPU_REQUEST' if missing_gpu else 'UNMODELABLE_SOURCE_RECORD',
                reasons=reasons, source_field_status=fields, compatible_sites=compatible)

def common_arm_population(rows, flex_ids):
    ids = {r['job_uid'] for r in rows}
    if not set(flex_ids) <= ids:
        raise ValueError('FLEX_NOT_SUBSET_OF_PHYSICAL')
    return {arm: [dict(r, flexibility_enabled=arm in ('B1','B3') and r['job_uid'] in flex_ids)
                  for r in rows] for arm in ('B0','B1','B2','B3')}
