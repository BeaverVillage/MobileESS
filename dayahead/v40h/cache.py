"""A shared provenance family for stage, restricted and full-child caches."""
from pathlib import Path
from copy import deepcopy
import shutil
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40a.invariants import digest
from .identity import bind, validate_identity, require, file_record, verify_file, IntegrityError

ROLES = ('campaign_SHA', 'A0_decision_SHA', 'A0_segment_SHA', 'A0_GPU_SHA', 'A0_PCC_SHA',
    'electrical_coefficients', 'traffic_forecast', 'road_graph', 'route_table', 'service_road_mapping',
    'mobility_physics', 'MESS_electrical', 'connection_delay', 'route_energy', 'MESS_PCC_mapping',
    'K', 'beam_width', 'fallback_widths', 'seed', 'WorkLimit_tiers', 'solver_settings', 'source_manifest')


def execution_identity(inputs): return bind('V40H_M1_EXECUTION_V1', inputs, ROLES)


def cache_identity(execution, *, kind, candidate, parent_SHA, fixed_trajectory_SHA, step):
    require(kind in ('STAGE', 'RESTRICTED', 'FULL_CHILD', 'MIPSTART'), 'UNKNOWN_CACHE_KIND')
    return bind('V40H_' + kind + '_CACHE_V1', {'execution': execution, 'candidate': candidate,
        'parent_state_SHA': parent_SHA, 'fixed_previous_MESS_trajectory_SHA': fixed_trajectory_SHA, 'step': step},
        ('execution', 'candidate', 'parent_state_SHA', 'fixed_previous_MESS_trajectory_SHA', 'step'))


def state_record(state):
    raw = state.to_dict() if hasattr(state, 'to_dict') else deepcopy(state)
    if 'trajectory_equivalence_sha256' in raw:
        from dayahead.v35r3e_r1.beam import trajectory_equivalence_sha, canonical_sha256
        require(raw['trajectory_equivalence_sha256'] == trajectory_equivalence_sha(raw['trajectory_slots']), 'RETAINED_INTERNAL_TRAJECTORY_IDENTITY')
        key = {'case': raw['case_id'], 'root': True} if raw['parent_state_id'] is None else {
            'case': raw['case_id'], 'completed_vehicles': list(raw['completed_vehicles']),
            'trajectory_equivalence_sha256': raw['trajectory_equivalence_sha256']}
        require(raw['state_sha256'] == canonical_sha256(key), 'RETAINED_INTERNAL_STATE_IDENTITY')
    return {'state': raw, 'content_SHA': digest(raw), 'trajectory_SHA': digest(raw.get('trajectory_slots', []))}


def _parents(parents): return [state_record(p) for p in parents]


def stage_envelope(payload, execution, parents, step):
    records = [state_record(x) for x in payload['retained_states']]
    return {'schema': 'V40H_STAGE_CACHE_V1', 'execution': execution,
        'execution_fingerprint_sha256': execution['identity_SHA'], 'step': step,
        'parents': _parents(parents), 'retained': records, 'payload': deepcopy(payload), 'payload_SHA': digest(payload)}


def validate_stage(value, execution, parents, step):
    require(value.get('schema') == 'V40H_STAGE_CACHE_V1', 'STALE_STAGE_SCHEMA')
    validate_identity(value['execution'], execution)
    require(value['execution_fingerprint_sha256'] == execution['identity_SHA'], 'STALE_STAGE_FINGERPRINT')
    require(value['step'] == step and value['parents'] == _parents(parents), 'STAGE_PARENT_IDENTITY')
    payload = value['payload']; require(value['payload_SHA'] == digest(payload), 'STAGE_PAYLOAD_SHA')
    require(value['retained'] == [state_record(x) for x in payload['retained_states']], 'RETAINED_STATE_TRAJECTORY_IDENTITY')
    parent_ids = {x['state']['beam_state_id'] for x in value['parents']}
    require(all(x['state']['parent_state_id'] in parent_ids for x in value['retained']), 'RETAINED_PARENT_NOT_CURRENT')
    require(len({x['state']['beam_state_id'] for x in value['retained']}) == len(value['retained']), 'DUPLICATE_RETAINED_STATE')
    return deepcopy(payload)


def mark_non_reusable(path, reason):
    path = Path(path); status = path.with_name(path.name + '.NON_REUSABLE.json')
    write_json(status, {'status': 'STALE_DIFFERENT_IDENTITY', 'STALE_STAGE_RESTORE_ALLOWED': 'NO',
                       'source': file_record(path), 'reason': reason, 'historical_bytes_deleted': False})


def archive_stale(path, reason):
    path = Path(path); mark_non_reusable(path, reason)
    archive = path.parent / 'non_reusable' / (path.stem + '_' + sha(path) + path.suffix)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists(): shutil.copyfile(path, archive)
    return archive


def restore_stage(path, execution, parents, step):
    path = Path(path)
    if not path.exists(): return None
    try: return validate_stage(read(path), execution, parents, step)
    except (ValueError, KeyError, TypeError, OSError) as error:
        mark_non_reusable(path, str(error)); return None


def write_stage(path, payload, execution, parents, step):
    path = Path(path); value = stage_envelope(payload, execution, parents, step)
    validate_stage(value, execution, parents, step)
    if path.exists():
        previous = read(path)
        if previous == value: return
        mark_non_reusable(path, 'RECOMPUTE_UNDER_CURRENT_EXECUTION_IDENTITY')
        archive = path.parent / 'non_reusable' / (path.stem + '_' + sha(path) + path.suffix)
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists(): shutil.copyfile(path, archive)
    write_json(path, value)


def store_candidate(path, identity, payload, leaves=()):
    value = {'schema': 'V40H_CANDIDATE_RESULT_V1', 'identity': identity, 'payload': deepcopy(payload),
        'payload_SHA': digest(payload), 'leaves': [file_record(p) for p in leaves],
        'reuse_mode': 'HINT_ONLY_NO_FIXING' if identity['identity']['schema'] == 'V40H_MIPSTART_CACHE_V1' else 'EXACT_CURRENT_RESULT'}
    path = Path(path)
    if path.exists():
        require(read(path) == value, 'CANDIDATE_CACHE_OVERWRITE_FORBIDDEN_USE_IDENTITY_NAMESPACE')
    else: write_json(path, value)
    return value


def restore_candidate(path, expected):
    path = Path(path)
    if not path.exists(): return None
    try:
        value = read(path); require(value.get('schema') == 'V40H_CANDIDATE_RESULT_V1', 'CANDIDATE_CACHE_SCHEMA')
        validate_identity(value['identity'], expected)
        require(value['payload_SHA'] == digest(value['payload']), 'CANDIDATE_PAYLOAD_SHA')
        for leaf in value['leaves']: verify_file(leaf)
        return value
    except (ValueError, KeyError, TypeError, OSError) as error:
        mark_non_reusable(path, str(error)); return None
