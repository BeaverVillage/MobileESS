"""Supervisor-owned byte-frozen V42 research interface and anchor checks."""
from pathlib import Path
import hashlib
import json
import math

REPORT = Path(__file__).resolve().parents[1] / 'docs/v42_unified_aidc_mess_research_20261014'
BINDING_FIELDS = ('science_sha', 'case_sha', 'physical_sha', 'time_axis_sha',
                  'qos_sha', 'cc4_sha', 'runtime_sha', 'response_sha',
                  'initial_state_sha', 'aidc_anchor', 'mess_anchor', 'interface_sha')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf8')).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_contracts(directory=REPORT):
    directory = Path(directory)
    manifest = json.loads((directory / 'SHARED_SOURCE_CASE_MANIFEST.json').read_text(encoding='utf8'))
    for name, expected in manifest['contract_file_shas'].items():
        if file_sha(directory / name) != expected:
            raise ValueError('UNIFIED_CONTRACT_BYTE_DRIFT:' + name)
    documents={name:json.loads((directory/name).read_text(encoding='utf8'))
               for name in manifest['contract_file_shas']}
    b=manifest['bindings']
    require_bindings(b,b)
    for key,name in (('physical_sha','UNIFIED_PHYSICAL_AUTHORITY.json'),
                     ('interface_sha','UNIFIED_INTERFACE_CONTRACT.json'),
                     ('time_axis_sha','SHARED_TIME_AXIS_CONTRACT.json'),
                     ('qos_sha','TIME_SHIFT_60MIN_QOS_CONTRACT.json')):
        if b[key]!=digest(documents[name]):
            raise ValueError('UNIFIED_MANIFEST_SEMANTIC_SHA_DRIFT:'+key)
    historical=manifest['historical_reference']
    science=digest(dict(base_science=historical['science_sha'],physical=b['physical_sha'],
                        interface=b['interface_sha'],qos=b['qos_sha']))
    case=digest(dict(base_case=historical['case_sha'],science_sha=science,axis=b['time_axis_sha'],delay=3600))
    if b['science_sha']!=science or b['case_sha']!=case:
        raise ValueError('UNIFIED_MANIFEST_SCIENCE_CASE_DERIVATION_DRIFT')
    source=manifest['historical_reference_file']
    if Path(source['path']).exists() and file_sha(source['path'])!=source['sha256']:
        raise ValueError('UNIFIED_HISTORICAL_REFERENCE_DRIFT')
    return manifest


def require_bindings(actual, expected):
    for key in BINDING_FIELDS:
        value = actual.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('UNIFIED_COMPLETE_SHA_REQUIRED:' + key)
        if value != expected.get(key):
            raise ValueError('UNIFIED_SHARED_ANCHOR_DRIFT:' + key)
    return dict(actual)


def combine_grid_pq(aidc_p, aidc_q, mess_p, mess_q):
    """Net load: C1 AIDC consumption minus signed MESS injection, once each."""
    import numpy as np
    arrays = [np.asarray(v, dtype=float) for v in (aidc_p, aidc_q, mess_p, mess_q)]
    if any(a.shape != arrays[0].shape or not np.isfinite(a).all() for a in arrays):
        raise ValueError('UNIFIED_GRID_PQ_AXIS_OR_FINITE_DRIFT')
    if arrays[0].ndim != 2 or arrays[0].shape[0] != 96:
        raise ValueError('UNIFIED_GRID_FULL96_REQUIRED')
    return arrays[0] - arrays[2], arrays[1] - arrays[3]


def require_global_bound(bound, case_sha, *, original_case=False):
    if not bound or bound.get('case_sha') != case_sha:
        raise ValueError('BOUND_EXACT_CASE_BINDING_REQUIRED')
    if bound.get('scope') != ('ORIGINAL_GLOBAL' if original_case else 'REDUCED_CASE_GLOBAL'):
        raise ValueError('RESTRICTED_BOUND_IS_NOT_GLOBAL')
    value = bound.get('value')
    if value is None or not math.isfinite(float(value)):
        raise ValueError('MEASURED_FINITE_BOUND_REQUIRED')
    return float(value)


def validate_handoffs(rows, bindings, initial_aidc, initial_mess):
    """Check actual producer/consumer lineage, including final A2 to M2."""
    if [r['stage'] for r in rows] != ['A1','M1','A2','M2']:
        raise ValueError('UNIFIED_A1_M1_A2_M2_ORDER_REQUIRED')
    a,m=initial_aidc,initial_mess
    for row in rows:
        before=row['producer_anchor_before']
        if before!={'AIDC_anchor':a,'MESS_anchor':m}:
            raise ValueError('UNIFIED_STAGE_PRODUCER_ANCHOR_DRIFT')
        expected=dict(bindings,aidc_anchor=a,mess_anchor=m)
        require_bindings(row['unified_input_bindings'],expected)
        if row['stage'].startswith('A'):
            if row['consumed'].get('fixed_mess_plan_sha')!=m:
                raise ValueError('UNIFIED_A_STAGE_MESS_CONSUMPTION_DRIFT')
            if row['result_MESS_anchor']!=m:
                raise ValueError('UNIFIED_A_STAGE_MUTATED_MESS')
        else:
            if row['consumed'].get('fixed_aidc_anchor')!=a:
                raise ValueError('UNIFIED_M_STAGE_AIDC_CONSUMPTION_DRIFT')
            if row['result_AIDC_anchor']!=a:
                raise ValueError('UNIFIED_M_STAGE_MUTATED_AIDC')
        a,m=row['result_AIDC_anchor'],row['result_MESS_anchor']
    return dict(status='PASS',final_aidc_anchor=a,final_mess_anchor=m,stages=4)
