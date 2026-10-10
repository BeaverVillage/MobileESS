"""Display the existing SHA-bound wrapper; reject partial/foreign proof packets."""
from fractions import Fraction
from pathlib import Path
import hashlib
import json

import pytest

from v42_autonomous_monitor import current_certificates as adapter, monitor
from v42_b2_monitor_v16 import certificates as original


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')
    return str(path)


@pytest.fixture
def packet(tmp_path):
    attempt = tmp_path / 'dates/B2/2025-05-01/attempts/current'
    output = attempt / 'output'
    code = tmp_path / 'frozen'
    code.mkdir()
    (code / 'builder.py').write_text('# original builder\n')
    (code / 'worker.py').write_text('# current worker\n')
    execution = {'worker.py': original.sha(code / 'worker.py')}
    manifest = dict(execution_sources=execution, execution_SHA=canonical(execution),
                    builder_original_sources={'builder.py': original.sha(code / 'builder.py')})
    manifest_path = write(tmp_path / 'MANIFEST.json', manifest)
    request = dict(root=str(tmp_path), arm='B2', day='2025-05-01', attempt_id='current',
                   output=str(output), result=str(attempt / 'RESULT.json'), manifest=manifest_path,
                   manifest_SHA=original.sha(manifest_path), implementation_SHA=manifest['execution_SHA'],
                   deployment_SHA=manifest['execution_SHA'])
    transport = dict(PASS=True, integer_and_full_LP_domains_identical=True, retained_rows=2, retained_columns=3)
    transport_path = write(output / 'TRANSPORT.json', transport)
    identity = dict(arm='B2', day='2025-05-01', case_sha='case', transport=transport,
        transport_authority=dict(sources={'builder.py': dict(path=str(code / 'builder.py'),
            sha256=original.sha(code / 'builder.py'))},
            certificate=dict(path=transport_path, sha256=original.sha(transport_path))))
    write(output / 'SCIENTIFIC_CASE_IDENTITY.json', identity)
    point = output / 'point.npz'
    point.write_bytes(b'unchanged raw integer point')
    ub = dict(PASS=True, case_sha='case', exact_Global_UB='4/5', point_path=str(point),
              point_file_sha256=original.sha(point), strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
              original_matrix_and_96_slot_physical_replay=dict(PASS=True, case_sha='case'))
    ub_path = write(output / 'UB.json', ub)
    replay = dict(PASS=True, all_original_feasible_points_contained=True, checked_original_equality_implications=1)
    proof = dict(PASS=True, independent_replay=replay, original_model_bounds_mutated=False,
                 original_checker_modified=False, source_matrix_domain_SHA='matrix-domain')
    proof_path = write(output / 'PROOF.json', proof)
    dual = {'0': '3/5'}
    dual_path = write(output / 'DUAL.json', dual)
    dual_sha = hashlib.sha256(b'0:3/5').hexdigest()
    nested = dict(PASS=True, case_sha='case', status='EXACT_STORED_RATIONAL_BOUND_CERTIFIED',
                  certified_domain='CHECKED_ROW_DOMAIN_WITH_FINITE_BOX', exact_bound='3/5',
                  native_objective_used=False, native_BestBd_used=False, optimality_claimed=False,
                  original_checker_byte_preserved=True, arbitrary_finite_bounds_used=False, dual_SHA256=dual_sha,
                  finite_box_original_row_implication=dict(proof_SHA=canonical(proof),
                    independent_replay=replay, original_model_bounds_mutated=False,
                    proof_file=dict(path=proof_path, sha256=original.sha(proof_path))))
    inclusion = dict(PASS=True, case_sha='case', original_rows=2, original_columns=3,
                     all_original_rows_exactly_once=True, all_original_columns_exactly_once=True,
                     every_original_96_slot_integer_plan_is_in_decomposed_domain=True,
                     original_coupling_rows_are_relaxed_only_via_signed_multipliers=True)
    lb = dict(PASS=True, case_sha='case', scope='FULL_ORIGINAL_C3A_SIGNED_LAGRANGIAN_LP_DUAL',
              exact_Global_LB='3/5', independent_decomposition=inclusion, independent_exact_certificate=nested,
              assembled_original_dual_sha256=dual_sha, dual_path=dual_path, dual_sha256=original.sha(dual_path),
              Native_optimize_calls=0, native_rounded_price_objectives_used_as_proof=False,
              restricted_master_objective_used_as_Global_LB=False, Native_MIP_ObjBound_used_as_exact_Global_LB=False)
    lb_path = write(output / 'LB.json', lb)
    frontier = dict(case_sha='case', exact_UB='4/5', exact_LB='3/5', exact_gap='1/4',
                    UB_certificate_path=ub_path, UB_certificate_sha256=original.sha(ub_path),
                    LB_certificate_path=lb_path, LB_certificate_sha256=original.sha(lb_path))
    frontier_path = write(output / 'frontier/CURRENT_CERTIFIED_STATE.json', frontier)
    return dict(output=output, request=request, lb=lb, lb_path=lb_path, frontier=frontier,
                frontier_path=frontier_path, proof_path=proof_path, dual_path=dual_path, code=code)


def observed(packet):
    return monitor.b2_bound(packet['output'], '2025-05-01', packet['request'])


def reseal(packet):
    write(Path(packet['lb_path']), packet['lb'])
    packet['frontier']['LB_certificate_sha256'] = original.sha(packet['lb_path'])
    write(Path(packet['frontier_path']), packet['frontier'])


def test_actual_producer_schema_read_only_and_exact_gap(packet):
    before = {p: p.read_bytes() for p in packet['output'].rglob('*') if p.is_file()}
    value = observed(packet)
    assert value['status'] == 'CERTIFIED' and value['gap'] == .25
    assert Fraction(value['UB']) >= Fraction(4, 5) and Fraction(value['LB']) <= Fraction(3, 5)
    assert value['evidence']['LB']['schema'] == 'CURRENT_ASSEMBLED_ORIGINAL_EXACT_LB'
    assert before == {p: p.read_bytes() for p in packet['output'].rglob('*') if p.is_file()}


@pytest.mark.parametrize('path,value', [
    (('PASS',), False), (('scope',), 'RESTRICTED_MASTER'), (('case_sha',), 'other'),
    (('independent_decomposition','PASS'), False),
    (('independent_decomposition','all_original_rows_exactly_once'), False),
    (('independent_decomposition','all_original_columns_exactly_once'), False),
    (('independent_decomposition','every_original_96_slot_integer_plan_is_in_decomposed_domain'), False),
    (('independent_decomposition','original_coupling_rows_are_relaxed_only_via_signed_multipliers'), False),
    (('independent_decomposition','original_rows'), 3), (('independent_decomposition','original_columns'), 4),
    (('independent_exact_certificate','PASS'), False),
    (('independent_exact_certificate','status'), 'TIME_LIMIT'),
    (('independent_exact_certificate','case_sha'), 'other'),
    (('independent_exact_certificate','native_objective_used'), True),
    (('independent_exact_certificate','native_BestBd_used'), True),
    (('independent_exact_certificate','optimality_claimed'), True),
    (('independent_exact_certificate','original_checker_byte_preserved'), False),
    (('independent_exact_certificate','arbitrary_finite_bounds_used'), True),
    (('independent_exact_certificate','exact_bound'), '7/10'),
    (('independent_exact_certificate','dual_SHA256'), '0'*64),
    (('native_rounded_price_objectives_used_as_proof',), True),
    (('restricted_master_objective_used_as_Global_LB',), True),
    (('Native_MIP_ObjBound_used_as_exact_Global_LB',), True), (('Native_optimize_calls',), True),
    (('independent_exact_certificate','finite_box_original_row_implication','proof_SHA'), '0'*64),
    (('independent_exact_certificate','finite_box_original_row_implication','original_model_bounds_mutated'), True),
    (('independent_exact_certificate','finite_box_original_row_implication','independent_replay','PASS'), False),
    (('independent_exact_certificate','finite_box_original_row_implication','independent_replay','all_original_feasible_points_contained'), False),
])
def test_partial_or_untrusted_wrapper_never_falls_back(packet, path, value):
    target = packet['lb']
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    reseal(packet)
    result = observed(packet)
    assert result['status'] == 'UNKNOWN' and result['UB'] is None and result['LB'] is None
    assert result['error']


@pytest.mark.parametrize('field,value', [
    ('implementation_SHA', '0'*64), ('deployment_SHA', '0'*64), ('manifest_SHA', '0'*64),
    ('attempt_id', 'previous'), ('arm', 'B3'), ('day', '2025-05-02'), ('attempt_id','../../escape')])
def test_current_request_and_source_binding_required(packet, field, value):
    packet['request'][field] = value
    assert observed(packet)['status'] == 'UNKNOWN'


def test_no_request_is_not_authority_for_nested_receipt(packet):
    assert monitor.b2_bound(packet['output'], '2025-05-01')['status'] == 'UNKNOWN'


@pytest.mark.parametrize('kwargs', [{'source': '0'*64}, {'attempt': 'previous'}])
def test_checkpoint_current_identity_is_required(packet, kwargs):
    assert monitor.b2_bound(packet['output'], '2025-05-01', packet['request'], **kwargs)['status'] == 'UNKNOWN'


@pytest.mark.parametrize('target', ['lb_path','proof_path','dual_path','builder'])
def test_mutation_after_cached_success_rejected(packet, target):
    assert observed(packet)['status'] == 'CERTIFIED'
    path = packet['code'] / 'builder.py' if target == 'builder' else Path(packet[target])
    path.write_bytes(b'mutated receipt')
    assert observed(packet)['status'] == 'UNKNOWN'


@pytest.mark.parametrize('target', ['dual','proof','UB','LB'])
def test_foreign_attempt_paths_rejected_even_with_valid_sha(packet, tmp_path, target):
    foreign = tmp_path / 'other-attempt.json'
    if target == 'dual':
        foreign.write_bytes(Path(packet['dual_path']).read_bytes())
        packet['lb']['dual_path'] = str(foreign)
        reseal(packet)
    elif target == 'proof':
        foreign.write_bytes(Path(packet['proof_path']).read_bytes())
        packet['lb']['independent_exact_certificate']['finite_box_original_row_implication']['proof_file']['path'] = str(foreign)
        reseal(packet)
    else:
        field = target + '_certificate_path'
        foreign.write_bytes(Path(packet['frontier'][field]).read_bytes())
        packet['frontier'][field] = str(foreign)
        write(Path(packet['frontier_path']), packet['frontier'])
    assert observed(packet)['status'] == 'UNKNOWN'


def test_exact_frontier_and_gap_not_clamped(packet):
    packet['frontier']['exact_gap'] = '1/100'
    write(Path(packet['frontier_path']), packet['frontier'])
    assert observed(packet)['status'] == 'UNKNOWN'


def test_flat_original_reader_unchanged(packet):
    packet['lb'] = dict(PASS=True, case_sha='case', status='EXACT_STORED_RATIONAL_BOUND_CERTIFIED',
                       native_objective_used=False, native_BestBd_used=False, exact_bound='3/5')
    reseal(packet)
    assert adapter.bounds(packet['output'], '2025-05-01') == original.bounds(packet['output'], '2025-05-01')
