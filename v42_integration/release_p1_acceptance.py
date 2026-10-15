"""Explicit P1-only acceptance; no fabricated lexicographic/P2 certificate.

The saved A1 is a current D0 basic-domain point, never a certificate for the
original unpriced migration domain or the joint AIDC/MESS optimum.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np

from .a_engine import digest
from .coordinator import _full_a, _full_m
from .m_engine import file_record, vector_sha

ROOT = Path(__file__).resolve().parents[1]
RC01 = ROOT / 'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/A1_P1_120'
SCHEMA = 'RELEASE_P1_ONLY_STAGE_ACCEPTANCE_V1'
SAVED_A1_PINS = {
    'A1_P1_RESULT.json': 'ce34aa06bfb6b53a1b214e9562e0cb296b48e33421b5a70c872939338981aec6',
    'PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json': '410ba0ea740e6528b0758b6e729809349664d79c970c06d280caa21cbac353cb',
    'EXECUTED_ADAPTER_SOURCE.json': '46a1bbbd0b1045a1a5c085823b07e92c7201e670181a15ddb9fb58620241a960',
    'SOLVE/POINT.npz': '966f5064ccbeea0180acb8b3e2d142e6ab69c7930354a9d54ab5a82c5255d938',
    'SOLVE/F2-CRA_MODEL_COMPLETE.json': '1354bbae49d3ab133ae74995b2f904b83ff2ec847ac32b2d80894601116ae31d',
    'CASE/D0_CASE_MANIFEST.json': 'f09d1aff680b2584f25c8be9d6b888bed421f0e935007ee7971bad7d2d972143',
    'CASE/D0_PLANNING_INPUT_AUDIT.json': '8f564edcea774230525da772f562f473a87e16f5c4af5a902128fd1eed8a6773',
    'SEPARATE_NATIVE_LEDGER_180.json': '1f26c7f0a0f5e20f93b758cc94d319bb5eb749ad6c55a6ffdf224e3368a555f7',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def prohibit_p2(result):
    if (result.get('P2_calls', 0) != 0 or result.get('P2') not in (None, 'NOT_RUN')
            or result.get('P2_certified', False) or result.get('P2_contract_certified', False)):
        raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')
    for row in result.get('lexicographic_trace', []):
        if row.get('group') == 'P2' and row.get('Native_call'):
            raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')


def _finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def require_acceptance(receipt, *, stage=None, source_identity=None, result=None):
    if (receipt.get('schema') != SCHEMA or receipt.get('status') != 'FULL_PASS'
            or receipt.get('P2_calls') != 0 or receipt.get('P2_optimized') is not False
            or receipt.get('acceptance_sha') != digest({k: v for k, v in receipt.items() if k != 'acceptance_sha'})
            or stage is not None and receipt.get('stage') != stage
            or source_identity is not None and receipt.get('source_identity') != source_identity
            or result is not None and receipt.get('result_sha') != digest(result)):
        raise ValueError('RELEASE_EXACT_P1_ONLY_FULL_STAGE_ACCEPTANCE_REQUIRED')
    return receipt


def accept_a(result, *, stage, stage_case_sha, source_identity, source_sha,
        input_sha, input_mess_anchor, native_binding, point_sha, original_full,
        parent_acceptance=None, evidence_scope='REAL_PRODUCTION'):
    prohibit_p2(result)
    if stage not in ('A1', 'A2'):
        raise ValueError('RELEASE_A_STAGE_REQUIRED')
    if stage == 'A2':
        require_acceptance(parent_acceptance or {}, stage='M1', source_identity=source_identity)
        if parent_acceptance['MESS_anchor'] != input_mess_anchor:
            raise ValueError('RELEASE_A2_FIXED_M1_ANCHOR_DRIFT')
    full = result.get('FULL_point_replay', {})
    if (result.get('FULL_feasible') is not True or full.get('PASS') is not True
            or original_full.get('PASS') is not True
            or not _finite(original_full.get('FULL_max_residual'))
            or not 0 <= original_full['FULL_max_residual'] <= 1e-5
            or original_full.get('point_sha256') != point_sha or full.get('point_sha256') != point_sha
            or result.get('stage') != stage or result.get('case_sha') != stage_case_sha
            or result.get('source_identity') != source_identity or result.get('D0_input_sha') != input_sha
            or result.get('input_MESS_anchor') != input_mess_anchor
            or native_binding.get('objective_sense') != 1
            or native_binding.get('rows') != original_full.get('rows')
            or native_binding.get('columns') != original_full.get('columns')):
        raise ValueError('RELEASE_CURRENT_ORIGINAL_FULL_P1_SOURCE_POINT_DOMAIN_REQUIRED')
    _full_a(result)
    objective = result.get('objective', result.get('rho'))
    bound = result.get('bound', result.get('local_bound'))
    gap = result.get('gap')
    # This target is a current numeric A-matrix closure only. FULL feasibility
    # is sufficient for a physical handoff; missed optimality stays explicit.
    numeric_closed = (_finite(objective) and _finite(bound) and _finite(gap) and 0 <= gap <= .005)
    receipt = dict(schema=SCHEMA, status='FULL_PASS', stage=stage,
        stage_case_sha=stage_case_sha, source_identity=deepcopy(source_identity), source_sha=source_sha,
        D0_input_sha=input_sha, AIDC_anchor=result['aidc_anchor'], MESS_anchor=input_mess_anchor,
        result_sha=digest(result), native_binding=deepcopy(native_binding), point_sha256=point_sha,
        Original_FULL=deepcopy(original_full), P1_only=True, P2_calls=0, P2_optimized=False,
        original_P1_objective='MIN_MAXIMUM_PHASE_LINE_LOADING',
        native_matrix_objective=objective, native_matrix_bound=bound, native_matrix_gap=gap,
        native_matrix_target_met=numeric_closed,
        optimality_status='CURRENT_MATRIX_TARGET_MET' if numeric_closed else 'OPTIMALITY_TARGET_UNMET',
        whole_original_unpriced_domain_global_optimality=False,
        original_unrestricted_migration_pricing_certificate=False,
        AIDC_MESS_joint_Global_LB=None, K48_Global_LB=None,
        minimum_control_timeshift_migration_cost_claimed=False,
        parent_acceptance_sha=None if parent_acceptance is None else parent_acceptance['acceptance_sha'],
        evidence_scope=evidence_scope, fixture=evidence_scope == 'NAMED_FIXTURE')
    receipt['acceptance_sha'] = digest(receipt)
    return receipt


def accept_m(result, *, stage, source_identity, source_sha, parent_a, parent_result,
        stage_case_sha, full_certificate):
    prohibit_p2(result)
    require_acceptance(parent_a, stage='A1' if stage == 'M1' else 'A2',
        source_identity=source_identity, result=parent_result)
    plan = _full_m(result)
    if (stage not in ('M1', 'M2') or result.get('stage') != stage
            or result.get('case_sha') != stage_case_sha or plan.get('case_sha') != stage_case_sha
            or result.get('D0_source_identity') != source_identity
            or result.get('D0_fixed_AIDC_anchor') != parent_a['AIDC_anchor']
            or result.get('binding', {}).get('aidc_anchor') != parent_a['AIDC_anchor']
            or full_certificate.get('PASS') is not True
            or full_certificate.get('original_matrix_and_96_slot_physical_replay', {}).get('case_sha') != stage_case_sha
            or full_certificate.get('original_matrix_and_96_slot_physical_replay', {}).get('PASS') is not True
            or full_certificate.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True):
        raise ValueError('RELEASE_M_STAGE_ORIGINAL_FULL_SOURCE_ANCHOR_REQUIRED')
    receipt = dict(schema=SCHEMA, status='FULL_PASS', stage=stage, stage_case_sha=stage_case_sha,
        source_identity=deepcopy(source_identity), source_sha=source_sha,
        AIDC_anchor=parent_a['AIDC_anchor'], MESS_anchor=plan['plan_sha'], result_sha=digest(result),
        Original_FULL=deepcopy(full_certificate), P1_only=True, P2_calls=0, P2_optimized=False,
        parent_acceptance_sha=parent_a['acceptance_sha'],
        UB_algorithm='ADAPTIVE_BEAM_4_JOINT_ORIGINAL_FULL_INCUMBENT_REGISTRY',
        restricted_pool_ObjBound_is_Global_LB=False, K48_Global_LB=None,
        evidence_scope=parent_a['evidence_scope'], fixture=parent_a['fixture'])
    receipt['acceptance_sha'] = digest(receipt)
    return receipt


def saved_a1(directory=RC01):
    """Authenticate the already executed result and normalize metadata in RAM.

    No old JSON is rewritten. This adds the explicit stage metadata expected
    by the preserved D0 M factory, without inventing a P2 result.
    """
    directory = Path(directory)
    records = []
    for name, wanted in SAVED_A1_PINS.items():
        actual = file_record(directory / name)
        if actual['sha256'] != wanted:
            raise ValueError('RELEASE_SAVED_A1_BYTE_DRIFT:' + name)
        records.append(actual)
    result = read(directory / 'A1_P1_RESULT.json')
    cert = read(directory / 'PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json')
    sources = read(directory / 'EXECUTED_ADAPTER_SOURCE.json')
    manifest = read(directory / 'CASE/D0_CASE_MANIFEST.json')
    audit = read(directory / 'CASE/D0_PLANNING_INPUT_AUDIT.json')
    for item in sources['files'] + sources['frozen_planning_Source13']:
        if file_record(item['path']) != item:
            raise ValueError('RELEASE_ORIGINAL_SUCCESSFUL_SOURCE_DRIFT')
    if (result['source_identity'] != cert['identity'] or result['native_binding'] != cert['native_binding']
            or manifest['identity'] != cert['identity'] or result['stage_case_sha'] != cert['stage_case_sha']
            or result['source_identity'] != audit['identity'] or result['Native_calls'] != 1):
        raise ValueError('RELEASE_SAVED_A1_SOURCE_CASE_MATRIX_DOMAIN_DRIFT')
    with np.load(directory / 'SOLVE/POINT.npz', allow_pickle=False) as z:
        point = z['point'].copy()
    if vector_sha(point) != result['FULL_point_replay']['point_sha256']:
        raise ValueError('RELEASE_SAVED_A1_RAW_POINT_DRIFT')
    result.update(stage='A1', case_sha=result['stage_case_sha'], P2_calls=0,
        D0_input_sha=audit['a_input_sha'], input_MESS_anchor=manifest['science_payload'].get('input_MESS_anchor'))
    # The immutable A1 stage-case digest contains the initial zero-MESS anchor.
    # Read it from its original explicit source contract, never an old M2 plan.
    from .production_case import initial_mess
    native = read(manifest['source_native_record']['path'])
    for merge in audit['exact_original_production_current_physical_merge']:
        record = merge['source_record']
        if file_record(record['path']) != record:
            raise ValueError('RELEASE_SAVED_A1_PHYSICAL_PROJECTION_SOURCE_DRIFT')
        native[merge['field']] = read(record['path'])[merge['field']]
    result['input_MESS_anchor'] = initial_mess(native)['plan_sha']
    if result['case_sha'] != digest(dict(parent=manifest['identity']['case_sha'], stage='A1',
            input_MESS_anchor=result['input_MESS_anchor'], backlog_contract=manifest['backlog_contract']['contract_sha'])):
        raise ValueError('RELEASE_SAVED_A1_INITIAL_ANCHOR_DERIVATION_DRIFT')
    receipt = accept_a(result, stage='A1', stage_case_sha=result['case_sha'],
        source_identity=manifest['identity'], source_sha=manifest['source_sha'], input_sha=audit['a_input_sha'],
        input_mess_anchor=result['input_MESS_anchor'], native_binding=cert['native_binding'],
        point_sha=vector_sha(point), original_full=result['FULL_point_replay'])
    return dict(result=result, acceptance=receipt, point=point, manifest=manifest,
        input_audit=audit, certificate=cert, immutable_records=records)
