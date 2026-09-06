"""Generation attestation precedes B1 solve; A0 reuse has no solve operation."""
from pathlib import Path
import numpy as np
from dayahead.paper_analysis.storage import read
from dayahead.v40a.invariants import digest
from dayahead.v40g_segments.canonical import import_frozen, identities, planning_power
from .identity import bind, validate_identity, require, file_record, verify_file, immutable_write, verify_bound_files

ROLES = ('V40G_method_SHA', 'V40G_source_SHA', 'V40G_config_SHA', 'common_T_DA_SHA', 'job_universe_SHA',
    'initial_state_SHA', 'electrical_authority_SHA', 'capacity_SHA', 'Rack_SHA', 'WAN_SHA', 'migration_authority_SHA',
    'solver_settings', 'objective_hierarchy', 'day')


def generation_identity(inputs): return bind('V40H_B1_GENERATION_V1', inputs, ROLES)


def generate(path, expected_builder, producer):
    expected = expected_builder()
    verify_bound_files(expected)
    require(expected['identity']['schema'] == 'V40H_B1_GENERATION_V1', 'B1_GENERATION_SCHEMA')
    result = producer(expected)
    current = expected_builder(); verify_bound_files(current); validate_identity(current, expected)
    require(result.get('status') == 'PASS' and result.get('diagnostic_only') is False, 'ACCEPTED_B1_ONLY')
    jobs = import_frozen(result['jobs'])
    require(result['final_decision_SHA'] == digest(sorted(result['jobs'], key=lambda r: r['job_uid'])), 'B1_CONTENT_IDENTITY')
    result = {**result, 'B1_GENERATION_IDENTITY': expected['identity'], 'B1_GENERATION_IDENTITY_SHA': expected['identity_SHA'],
        'B1_segment_identity': identities(jobs), 'generation_attestation': 'CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER',
        'post_hoc_generation_adoption': False}
    immutable_write(path, result)
    return result


def produce_joint_b1(path, expected_builder, reference_jobs, reference_pcc, context, solve_output):
    """Production entry: capture inputs before the frozen joint solver runs."""
    from dayahead.v40g.optimizer import solve
    def producer(expected):
        inputs = expected['identity']['inputs']
        from .numerical_context import require_attested_context
        from .freeze import expected_electrical
        certificate = inputs['input_files']['electrical']['path']
        require_attested_context(context, certificate, lambda: expected_electrical(Path(context.V40H_repository), inputs['day']))
        require(inputs['job_universe_SHA'] == digest(sorted(str(r['job_uid']) for r in reference_jobs)), 'B1_JOB_UNIVERSE')
        require(inputs['initial_state_SHA'] == digest(reference_jobs), 'B1_INITIAL_STATE')
        require(np.array_equal(planning_power(import_frozen(reference_jobs), context)['pcc'], reference_pcc), 'B1_REFERENCE_PCC_INPUT')
        return solve(reference_jobs, reference_pcc, context, Path(solve_output))
    return generate(path, expected_builder, producer)


def load_b1_as_a0(path, expected_builder, trajectory_path, context):
    """Expected identity is built from external frozen inputs, never the file."""
    expected = expected_builder(); verify_bound_files(expected); value = read(path)
    require(value.get('generation_attestation') == 'CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER' and
            value.get('post_hoc_generation_adoption') is False, 'B1_GENERATION_IDENTITY_REQUIRED_NO_POST_HOC_ADOPTION')
    validate_identity({'identity': value['B1_GENERATION_IDENTITY'], 'identity_SHA': value['B1_GENERATION_IDENTITY_SHA']}, expected)
    require(value.get('status') == 'PASS' and value.get('diagnostic_only') is False, 'ACCEPTED_B1_ONLY')
    require(value['final_decision_SHA'] == digest(sorted(value['jobs'], key=lambda r: r['job_uid'])), 'B1_DECISION_CONTENT_DRIFT')
    jobs = import_frozen(value['jobs']); segments = identities(jobs)
    require(segments == value['B1_segment_identity'], 'B1_SEGMENT_CONTENT_DRIFT')
    power = planning_power(jobs, context)
    with np.load(trajectory_path, allow_pickle=False) as z:
        for k in ('gpu', 'it', 'pcc', 'qcc'): require(np.array_equal(power[k], z[k]), 'B1_TRAJECTORY_BINDING:' + k)
    return {'jobs': jobs, 'power': power, 'source': file_record(path), 'trajectory': file_record(trajectory_path),
        'B1_FINAL_DECISION_SHA': value['final_decision_SHA'], 'B3_A0_DECISION_SHA': value['final_decision_SHA'],
        'B1_FINAL_SEGMENT_SHA': segments['segment_and_event_SHA'], 'B3_A0_SEGMENT_SHA': segments['segment_and_event_SHA'],
        'B1_GENERATION_IDENTITY_SHA': expected['identity_SHA'], 'B3_A0_GENERATION_IDENTITY_SHA': expected['identity_SHA'],
        'B3_A0_AIDC_OPTIMIZE_CALLS': 0}
