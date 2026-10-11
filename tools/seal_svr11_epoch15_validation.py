"""Bind the small current-matrix release packet after measured native smoke."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
from prepare_svr11_epoch15 import preserved_science,OLD,DEV


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
    receipt=dict(schema='SVR11_EPOCH15_MINIMAL_VALIDATION_V1',PASS=True,
        source_SHA=source_sha,Native_M_limit_seconds=1800,
        A1_A2_algorithms_changed=False,physical_and_forecast_science_bitwise_unchanged=True,
        production_results_promoted=0,exact_reduction_proof=proof_receipt,
        original_equivalence_validation=record(equivalent),runtime_smoke=record(DEV/'RUNTIME_SMOKE.json'),
        gap_validation=record(gap),unchanged_science=preserved,
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
