"""Read-only current Table V Full96 ancestry and settled-physics evidence.

JSON metadata and numeric NPZ packets use separate readers. Nothing here
constructs a solver/model, executes Actual/AC, or opens retrospective job truth.
Missing new ancestry/policy fields are rejected; old evidence is never upgraded.
"""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .a_engine import digest
from .m_engine import file_record, vector_sha
from .release_ac_contract import CONTRACT, validate_settled_fresh
from .table_v_dates import require_day


REFERENCE_POLICY = 'ORIGINAL_REFERENCE_FIFO_GRID_BLIND_NO_ADDED_FLEX'
ARMS = ('B0', 'B1', 'B2', 'B3')


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _checked_bytes(record):
    _require(isinstance(record, dict) and set(record) == {'path', 'sha256', 'bytes'},
             'TABLE_V_EVIDENCE_EXACT_FILE_DESCRIPTOR_REQUIRED')
    path = Path(record['path'])
    _require(file_record(path) == record, 'TABLE_V_EVIDENCE_RAW_BYTES_DRIFT')
    return path


def _json(path, *, record=None):
    path = _checked_bytes(record) if record is not None else Path(path)
    _require(path.suffix.lower() == '.json', 'TABLE_V_EVIDENCE_JSON_READER_REJECTS_BINARY')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _point(record):
    path = _checked_bytes(record)
    _require(path.suffix.lower() == '.npz', 'TABLE_V_EVIDENCE_NUMERIC_NPZ_REQUIRED')
    with np.load(path, allow_pickle=False) as packet:
        _require(packet.files == ['point'], 'TABLE_V_EVIDENCE_LITERAL_POINT_AXIS_REQUIRED')
        point = packet['point']
        _require(point.dtype == np.dtype('float64') and point.ndim == 1 and np.isfinite(point).all(),
                 'TABLE_V_EVIDENCE_LITERAL_POINT_FINITE_REQUIRED')
        return vector_sha(point)


def _root(folder):
    for candidate in (folder, *folder.parents):
        if (candidate / 'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').is_file():
            return candidate
    raise ValueError('TABLE_V_EVIDENCE_CANONICAL_EXECUTION_ROOT_REQUIRED')


def _source(expected, manifest):
    require_day(expected['day'])
    identity = expected['source_identity']
    _require(all(identity.get(k) for k in ('science_sha', 'case_sha', 'initial_state_sha'))
             and expected.get('source_sha') and manifest.get('day') == expected['day']
             and manifest.get('source_sha') == expected['source_sha'] and manifest.get('identity') == identity,
             'TABLE_V_EVIDENCE_CURRENT_SCIENCE_CASE_SOURCE_REQUIRED')
    freeze = manifest.get('source_freeze') or {}
    _require(bool(freeze.get('files')) and freeze.get('source_sha') == expected['source_sha'] == digest(freeze['files'])
             and digest(manifest.get('science_derivation')) == identity['science_sha']
             and digest(manifest.get('case_derivation')) == identity['case_sha'],
             'TABLE_V_EVIDENCE_CURRENT_SCIENCE_CASE_DERIVATION_REQUIRED')
    for record in freeze['files']:
        _checked_bytes(record)
    parent = manifest.get('parent_basic_manifest') or {}
    _require(parent.get('case_payload', {}).get('native_source') == parent.get('source_native_record')
             == manifest.get('source_native_record') and bool(manifest.get('source_native_record'))
             and digest(parent.get('case_payload')) == parent.get('identity', {}).get('case_sha')
             and manifest['case_derivation'].get('parent_case') == parent['identity']['case_sha'],
             'TABLE_V_EVIDENCE_ORIGINAL_NATIVE_SOURCE_CASE_DERIVATION_REQUIRED')


def _reference(root, expected, manifest):
    from .table_v_reference import require_reference_acceptance
    result = _json(root / 'REFERENCE_RESULT.json')
    receipt = _json(root / 'REFERENCE_ACCEPTANCE.json')
    require_reference_acceptance(receipt, identity=expected['source_identity'], result=result)
    module_root = Path(__file__).resolve().parents[1]
    required_sources = [file_record(module_root / name) for name in
        ('v42_integration/table_v_reference.py', 'v42_integration/production_case.py',
         'v42_integration/qos.py', 'v42_native/service.py')]+manifest['source_freeze']['files']
    _require(all(record in result.get('reference_sources', []) for record in required_sources)
             and result.get('initial_record') == manifest.get('initial_record'),
             'TABLE_V_EVIDENCE_ORIGINAL_REFERENCE_SOURCE_AUTHORITY_REQUIRED')
    _require(receipt['source_sha'] == expected['source_sha'], 'TABLE_V_EVIDENCE_REFERENCE_SOURCE_DRIFT')
    from .table_v_mess import require_aidc_anchor
    require_aidc_anchor(result, sorted(result['capacities']))
    return result, receipt


def _stage(folder, stages, stage, *, kind):
    entry = stages.get(stage) or {}
    result, receipt = entry.get('result'), entry.get('acceptance')
    _require(isinstance(result, dict) and isinstance(receipt, dict), 'TABLE_V_EVIDENCE_FULL_STAGE_ANCESTOR_REQUIRED')
    result_name, receipt_name = (('P1_ONLY_RESULT.json', 'P1_ONLY_ACCEPTANCE.json') if kind == 'A'
                                 else ('TABLE_V_M_RESULT.json', 'TABLE_V_M_ACCEPTANCE.json'))
    _require(_json(folder / stage / result_name) == result and _json(folder / stage / receipt_name) == receipt,
             'TABLE_V_EVIDENCE_CANONICAL_STAGE_BODY_DRIFT')
    return result, receipt


def _a_stage(folder, stages, stage, expected, arm, audit, fixed_mess_anchor):
    from .release_p1_acceptance import require_acceptance, prohibit_p2
    from .tablev_fullflex_actual import require_full_a_parent
    from .table_v_mess import require_aidc_anchor
    from .coordinator import _full_a
    result, receipt = _stage(folder, stages, stage, kind='A')
    require_acceptance(receipt, stage=stage, source_identity=expected['source_identity'], result=result)
    prohibit_p2(result); _full_a(result)
    require_full_a_parent({'input_audit': audit}, arm, result, receipt)
    require_aidc_anchor(result, sorted(result['AIDC_P_by_site']))
    case_sha = digest(dict(parent=expected['source_identity']['case_sha'], stage=stage,
                           input_MESS_anchor=fixed_mess_anchor, backlog_contract=audit['backlog_contract_sha']))
    _require(result.get('arm') == arm and result.get('stage') == stage and result.get('case_sha') == case_sha
             and receipt.get('source_sha') == expected['source_sha'] and receipt.get('P1_only') is True
             and receipt.get('fixture') is False and receipt.get('evidence_scope') == 'REAL_PRODUCTION'
             and result.get('input_MESS_anchor') == fixed_mess_anchor,
             'TABLE_V_EVIDENCE_CURRENT_ORIGINAL_P1_ANCESTOR_REQUIRED')
    point = folder / stage / 'P1_ONLY_POINT.npz'
    _require(_point(file_record(point)) == receipt.get('point_sha256'), 'TABLE_V_EVIDENCE_A_POINT_SHA_DRIFT')
    return result, receipt


def _m_stage(folder, stages, stage, expected, arm, aidc, parent, off):
    from .table_v_mess import require_m_acceptance, require_full_plan_axes
    result, receipt = _stage(folder, stages, stage, kind='M')
    require_m_acceptance(receipt, result=result, identity=expected['source_identity'], arm=arm, stage=stage)
    identity = _json(folder / stage / 'SCIENTIFIC_CASE_IDENTITY.json')
    case_sha = identity.get('case_sha')
    _require(case_sha == result.get('case_sha') == digest({k: v for k, v in identity.items() if k != 'case_sha'})
             and identity.get('day') == expected['day'] and identity.get('arm') == arm and identity.get('stage') == stage
             and identity.get('science_sha') == expected['source_identity']['science_sha']
             and identity.get('D0_source_sha') == expected['source_sha']
             and identity.get('D0_parent_case_sha') == expected['source_identity']['case_sha']
             and identity.get('aidc_anchor') == aidc['aidc_anchor']
             and receipt.get('source_sha') == expected['source_sha']
             and receipt.get('AIDC_anchor') == aidc['aidc_anchor']
             and receipt.get('parent_acceptance_sha') == parent['acceptance_sha']
             and receipt.get('P1_only') is True and receipt.get('fixture') is False,
             'TABLE_V_EVIDENCE_CURRENT_M_PARENT_AND_SCIENCE_REQUIRED')
    _require(all(identity.get(key) and identity[key] == result['binding'].get(key) for key in
             ('original_matrix_sha', 'original_domain_sha', 'selected_matrix_sha', 'selected_domain_sha')),
             'TABLE_V_EVIDENCE_M_MATRIX_DOMAIN_BINDING_DRIFT')
    require_full_plan_axes(SimpleNamespace(graph=(tuple(off['P_by_site']), off['initial_sites'])), result['mess'])
    return result, receipt


def _trace(record, expected, capacities, slots):
    path = _checked_bytes(record)
    _require(path.suffix.lower() == '.npz', 'TABLE_V_EVIDENCE_TRACE_NPZ_REQUIRED')
    begin = datetime.fromisoformat(expected['day']).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
    with np.load(path, allow_pickle=False) as packet:
        _require({'sites', 'timestamps_start_epoch_seconds', 'GPU', 'compute_GPU', 'PCC_P_kw', 'PCC_Q_kvar'} <= set(packet.files),
                 'TABLE_V_EVIDENCE_COMPLETE_ACTUAL_TRACE_REQUIRED')
        sites = tuple(map(str, packet['sites']))
        _require(len(sites) == 12 and len(set(sites)) == 12 and set(sites) == set(capacities)
                 and np.array_equal(packet['timestamps_start_epoch_seconds'], begin + np.arange(slots)*900),
                 'TABLE_V_EVIDENCE_CURRENT_96_TRACE_AXIS_REQUIRED')
        for field in ('GPU', 'compute_GPU', 'IT_kw', 'PCC_P_kw', 'PCC_Q_kvar'):
            _require(field in packet.files, 'TABLE_V_EVIDENCE_COMPLETE_ACTUAL_TRACE_REQUIRED')
            values = packet[field]
            _require(values.shape == (slots, 12) and np.issubdtype(values.dtype, np.number) and np.isfinite(values).all(),
                     'TABLE_V_EVIDENCE_FINITE_96_TRACE_POWER_REQUIRED')
        gpu, compute = packet['GPU'], packet['compute_GPU']
        _require(np.all(gpu >= -1e-9) and np.all(compute >= -1e-9) and np.all(compute <= gpu+1e-8)
                 and np.all(gpu <= np.asarray([capacities[s] for s in sites])[None, :]+1e-8),
                 'TABLE_V_EVIDENCE_TRACE_CAPACITY_OR_COMPUTE_DRIFT')
        return packet['PCC_P_kw'].copy(), packet['PCC_Q_kvar'].copy()


def _validate_arm(record, expected, arm, *, expected_policy_sha, slots):
    """Replay the exact requested scope without promoting a prefix to Full96."""
    _require(slots in (16, 96), 'TABLE_V_EVIDENCE_EXACT_16_OR_96_SCOPE_REQUIRED')
    _require(arm in ARMS and isinstance(expected_policy_sha, str) and bool(expected_policy_sha),
             'TABLE_V_EVIDENCE_EXPLICIT_ARM_AND_POLICY_REQUIRED')
    outcome = _json(None, record=record); folder = Path(record['path']).resolve().parent
    root = _root(folder)
    manifest = _json(root / 'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json'); _source(expected, manifest)
    reference, ref_receipt = _reference(root, expected, manifest)
    from .production_case import initial_mess
    native = _json(None, record=manifest['source_native_record'])
    _require(native.get('day') == expected['day'] and native.get('capacities') == reference['capacities'],
             'TABLE_V_EVIDENCE_CURRENT_OFF_NATIVE_DAY_REQUIRED')
    off = initial_mess(native)
    stages = _json(folder / 'PLANNING_STAGE_RESULTS.json')
    aidc, aa, m_result, ma, mess = reference, ref_receipt, None, None, off
    if arm in ('B1', 'B3'):
        audit = _json(root / 'INPUTS/FULL_FLEX/TABLE_V_FLEX_INPUT_AUDIT.json')
        _require(audit.get('a_input_sha') == manifest.get('full_flex_input_sha'), 'TABLE_V_EVIDENCE_PUBLIC_INPUT_SHA_DRIFT')
        aidc, aa = _a_stage(folder, stages, 'A1', expected, arm, audit, off['plan_sha'])
    if arm in ('B2', 'B3'):
        m_result, ma = _m_stage(folder, stages, 'M1', expected, arm, aidc, aa, off)
        mess = m_result['mess']
    if arm == 'B3':
        aidc, aa = _a_stage(folder, stages, 'A2', expected, arm, audit, mess['plan_sha'])
        _require(aa.get('parent_acceptance_sha') == ma['acceptance_sha'], 'TABLE_V_EVIDENCE_A2_M1_PARENT_SHA_DRIFT')
        m_result, ma = _m_stage(folder, stages, 'M2', expected, arm, aidc, aa, off)
        mess = m_result['mess']
    a_stage = 'REFERENCE' if arm in ('B0', 'B2') else 'A1' if arm == 'B1' else 'A2'
    m_stage = 'OFF' if arm in ('B0', 'B1') else 'M1' if arm == 'B2' else 'M2'
    actual_wrapper = _json(folder / 'ACTUAL_RESULT.json'); fresh_wrapper = _json(folder / 'FRESH_AC_RESULT.json')
    actual, fresh = actual_wrapper.get('result'), fresh_wrapper.get('result')
    _require(isinstance(actual, dict) and isinstance(fresh, dict), 'TABLE_V_EVIDENCE_TYPED_ACTUAL_FRESH_REQUIRED')
    payload = actual.get('evaluation_case_payload') or {}
    policy = payload.get('policy'); policy_sha = digest(policy)
    _require(policy is not None and payload.get('policy_sha') == policy_sha == expected_policy_sha,
             'TABLE_V_EVIDENCE_CURRENT_ACTUAL_POLICY_SHA_REQUIRED')
    if arm in ('B0', 'B2'):
        _require(policy == REFERENCE_POLICY, 'TABLE_V_EVIDENCE_ORIGINAL_REFERENCE_POLICY_REQUIRED')
    else:
        _require(isinstance(policy, dict) and payload.get('actual_policy') == policy
                 and payload.get('actual_policy_sha') == policy_sha and policy.get('arm') == arm
                 and policy.get('R2') == 'HOLD' and policy.get('MESS_plan_sha') == mess['plan_sha']
                 and policy.get('policy') == manifest.get('science_derivation', {}).get('policy')
                 and bool(policy.get('policy')),
                 'TABLE_V_EVIDENCE_CURRENT_FULL_FLEX_POLICY_REQUIRED')
    required = dict(day=expected['day'], arm=arm, source_identity=expected['source_identity'],
        source_sha=expected['source_sha'], initial_state_sha=expected['source_identity']['initial_state_sha'],
        A_result_sha=digest(aidc), A_acceptance_sha=aa['acceptance_sha'],
        M_result_sha=None if m_result is None else digest(m_result), M_acceptance_sha=None if ma is None else ma['acceptance_sha'],
        reference_result_sha=digest(reference), reference_acceptance_sha=digest(ref_receipt),
        AIDC_anchor=aidc['aidc_anchor'], MESS_plan_sha=mess['plan_sha'], final_AIDC_stage=a_stage,
        final_MESS_stage=m_stage, slots=slots, clock_contract=CONTRACT)
    _require(all(key in payload and payload[key] == value for key, value in required.items()),
             'TABLE_V_EVIDENCE_ACTUAL_FINAL_ANCESTOR_HASH_OR_ANCHOR_DRIFT')
    schema = 'TABLE_V_ACTUAL_EVALUATION_CASE_V1' if arm in ('B0', 'B2') else 'TABLE_V_FULL_FLEX_ACTUAL_EVALUATION_CASE_V1'
    _require(payload.get('schema') == schema and actual.get('evaluation_case_sha') == digest(payload)
             and outcome.get('day') == expected['day'] and outcome.get('arm') == arm and outcome.get('status') == 'FULL_PASS'
             and outcome.get('actual') == actual_wrapper and outcome.get('fresh') == fresh_wrapper
             and outcome.get('executed_actual_slots') == outcome.get('executed_fresh_slots') == slots
             and actual_wrapper.get('status') == fresh_wrapper.get('status') == 'FULL_PASS'
             and actual.get('schema') == 'TABLE_V_ACTUAL_EXECUTION_V1' and actual.get('fixture') is False
             and actual.get('Actual_stage_PASS') is True and actual.get('status') == fresh.get('status') == 'FULL_PASS'
             and actual.get('day') == expected['day'] and actual.get('arm') == fresh.get('arm') == arm
             and actual.get('source_identity') == expected['source_identity'] and actual.get('source_sha') == expected['source_sha']
             and actual.get('AIDC_anchor') == aidc['aidc_anchor'] and actual.get('MESS_plan_sha') == mess['plan_sha']
             and actual.get('policy_sha') == policy_sha and actual.get('initial_state_sha') == required['initial_state_sha']
             and actual.get('executed_actual_slots') == fresh.get('executed_slots') == slots
             and actual.get('Gate_contract') == fresh.get('official_contract') == CONTRACT,
             'TABLE_V_EVIDENCE_CURRENT_FULL96_OUTCOME_CHAIN_REQUIRED')
    for wrapper in (actual_wrapper, fresh_wrapper):
        _require(bool(wrapper.get('raw_records')), 'TABLE_V_EVIDENCE_IMMUTABLE_RAW_RECORDS_REQUIRED')
        for raw in wrapper['raw_records']:
            _checked_bytes(raw)
    _require(fresh.get('actual_record') in actual_wrapper['raw_records']
             and _json(None, record=fresh['actual_record']) == actual,
             'TABLE_V_EVIDENCE_ACTUAL_RAW_BODY_DRIFT')
    saved_fresh = [r for r in fresh_wrapper['raw_records'] if Path(r['path']).name == 'TABLE_V_SETTLED_FRESH.json']
    _require(len(saved_fresh) == 1 and _json(None, record=saved_fresh[0]) == fresh,
             'TABLE_V_EVIDENCE_FRESH_RAW_BODY_DRIFT')
    _require(actual.get('actual_trace') in actual_wrapper['raw_records'], 'TABLE_V_EVIDENCE_TRACE_RECORD_MISSING')
    p, q = _trace(actual['actual_trace'], expected, reference['capacities'], slots)
    rows = _json(None, record=fresh['raw_slot_rows'])
    _require(len(rows) == slots and all(np.array_equal(row.get('PCC_P_kw'), p[t])
             and np.array_equal(row.get('PCC_Q_kvar'), q[t]) for t, row in enumerate(rows)),
             'TABLE_V_EVIDENCE_FRESH_APPLIED_PQ_DIFFERS_FROM_ACTUAL_TRACE')
    certificate = validate_settled_fresh(_json(None, record=fresh['raw_receipt']), rows,
        day=expected['day'], case_sha=actual['evaluation_case_sha'], initial_state_sha=required['initial_state_sha'],
        mess_plan_sha=mess['plan_sha'], trace_record=actual['actual_trace'], slots=slots)
    _require(certificate == fresh.get('official_certificate') and certificate['status'] == 'PASS',
             'TABLE_V_EVIDENCE_CURRENT_SETTLED_FULL96_RAW_REPLAY_REQUIRED')
    return certificate


def validate_arm_full96(record, expected, arm, *, expected_policy_sha):
    """Public Full96 authority: a 16-slot canary can never pass this API."""
    return _validate_arm(record, expected, arm, expected_policy_sha=expected_policy_sha, slots=96)


def validate_arm_canary16(record, expected, arm, *, expected_policy_sha):
    """Read an already completed current canary; never authorize its launch."""
    return _validate_arm(record, expected, arm, expected_policy_sha=expected_policy_sha, slots=16)
