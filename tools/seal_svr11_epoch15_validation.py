"""Bind the small current-matrix release packet after measured native smoke."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
from prepare_svr11_epoch15 import preserved_science,OLD,DEV


def checked_record(item):
    if record(item['path'])!=item:
        raise PermissionError('MINIMAL_VALIDATION_PACKET_BYTES_DRIFT:'+item['path'])
    return read(item['path'])


def crosslinks(smoke,equivalent,equivalent_data,proof_receipt,proof,sources,source_sha):
    from v42_ultracompact.current import SOURCES
    if (equivalent_data['source_SHA']!=source_sha
            or smoke['native_execution_source_SHA']!=source_sha
            or smoke['construction_source_SHA']!=equivalent_data['construction_source_SHA']
            or smoke['final_source_equivalence']!=record(equivalent)
            or equivalent_data['exact_reduction_proof']!=proof_receipt
            or proof['scientific_source_SHAs']!={name:sources[name] for name in SOURCES}):
        raise PermissionError('MINIMAL_VALIDATION_SOURCE_OR_PROOF_CROSSLINK_DRIFT')
    ledger=checked_record(smoke['native_ledger'])
    if ledger['source_SHA']!=source_sha or ledger['inflight'] is not None:
        raise PermissionError('MINIMAL_VALIDATION_NATIVE_LEDGER_SOURCE_DRIFT')
    equality=checked_record(equivalent_data['memory_Delete_only_equality'])
    flags=('selected_matrix_bitwise_equal','selected_domain_bitwise_equal',
        'all_removed_row_certificates_identical','all_bound_certificates_identical')
    transition=equality['mathematical_source_transition']
    if (equality.get('PASS') is not True or equality['source_SHA']!=source_sha
            or equality['construction_source_SHA']!=equivalent_data['construction_source_SHA']
            or equality['refreshed_case_SHA']!=equivalent_data['refreshed_case_SHA']
            or equality['refreshed_exact_reduction_proof']!=proof_receipt
            or not all(equality.get(name) is True for name in flags)
            or not all(transition.get(name) is True for name in
                ('PASS','AST_identical_after_removing_single_unused_temporary_Delete','other_mathematical_sources_unchanged'))):
        raise PermissionError('MINIMAL_VALIDATION_MEMORY_EQUALITY_CROSSLINK_DRIFT')
    identity=checked_record(smoke['original_model_identity'])
    original=identity['original_model_identity']
    if (identity.get('PASS') is not True or identity['case_sha']!=equality['refreshed_case_SHA']
            or original['selected_matrix_sha']!=equivalent_data['selected_matrix_SHA']
            or original['selected_domain_sha']!=equivalent_data['selected_domain_SHA']
            or original['c3_authority']['certificate']!=proof_receipt):
        raise PermissionError('MINIMAL_VALIDATION_NATIVE_CASE_CROSSLINK_DRIFT')
    if equality['old_native0_ledger']!=smoke['prior_native0_ledger']:
        raise PermissionError('MINIMAL_VALIDATION_PRIOR_NATIVE0_CROSSLINK_DRIFT')
    prior=checked_record(smoke['prior_native0_ledger'])
    if (prior['source_SHA']!=smoke['construction_source_SHA'] or prior['calls']
            or prior['inflight'] is not None or prior['measured_Native_Runtime']!=0):
        raise PermissionError('MINIMAL_VALIDATION_PRIOR_NATIVE0_REQUIRED')
    return dict(PASS=True,source_SHA=source_sha,refreshed_case_SHA=equality['refreshed_case_SHA'],
        final_source_proof_case_native_and_memory_equality_bound=True,prior_construction_Native_zero=True)


def seal():
    sources=source_files();source_sha=digest(sources)
    smoke=read(DEV/'RUNTIME_SMOKE.json')
    gap=SOURCE/'docs/v42_epoch15_integration_20261011/GAP_VALIDATION.json'
    if not smoke.get('PASS') or smoke['source_SHA']!=source_sha:
        raise PermissionError('CURRENT_NATIVE_SMOKE_REQUIRED')
    if not read(gap).get('PASS') or read(gap)['source_SHA']!=source_sha:
        raise PermissionError('CURRENT_GAP_VALIDATION_REQUIRED')
    preserved=preserved_science(read(OLD/'CAMPAIGN_MANIFEST.json'),sources)
    output=DEV/'dates/B2/2025-05-01/attempts/representative01/output'
    equivalent=DEV/'ORIGINAL_EQUIVALENCE_VALIDATION_FINAL_SOURCE.json'
    equivalent_data=read(equivalent)
    proof_receipt=equivalent_data.get('exact_reduction_proof',record(output/'CURRENT_EXACT_C3A_PROOF.json'))
    if record(proof_receipt['path'])!=proof_receipt:
        raise PermissionError('FINAL_CURRENT_EXACT_PROOF_BYTES_DRIFT')
    proof=read(proof_receipt['path'])
    if not proof['PASS'] or not read(equivalent)['PASS']:
        raise PermissionError('CURRENT_EXACT_REDUCTION_AND_ORIGINAL_EQUIVALENCE_REQUIRED')
    links=crosslinks(smoke,equivalent,equivalent_data,proof_receipt,proof,sources,source_sha)
    receipt=dict(schema='SVR11_EPOCH15_MINIMAL_VALIDATION_V1',PASS=True,
        source_SHA=source_sha,Native_M_limit_seconds=1800,
        A1_A2_algorithms_changed=False,physical_and_forecast_science_bitwise_unchanged=True,
        production_results_promoted=0,exact_reduction_proof=proof_receipt,
        original_equivalence_validation=record(equivalent),runtime_smoke=record(DEV/'RUNTIME_SMOKE.json'),
        gap_validation=record(gap),unchanged_science=preserved,
        source_proof_case_native_crosslinks=links,
        construction_source_SHA=read(equivalent).get('construction_source_SHA',read(equivalent)['source_SHA']),
        selected_current_matrix=proof['selected'],UTC=now())
    path=DEV/'EPOCH15_MINIMAL_VALIDATION.json';atomic(path,receipt)
    summary=SOURCE/'docs/v42_epoch15_integration_20261011/MINIMAL_VALIDATION_SUMMARY.json'
    atomic(summary,dict(receipt,full_packet=record(path),
        skipped=['1536_assignment_replay','duplicate_full_forensic_audit',
            'all31_repeated_full_model_comparison','solver_tournament','extra_LP_or_CG_research',
            'repeated_immutable_raw_input_numerical_validation']))
    print('CURRENT_EXACT_C3A_MINIMAL_VALIDATION_SEALED',source_sha)


if __name__=='__main__':seal()
