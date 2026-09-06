"""Authorized future wiring: attested loaders, segment jobs, hardened caches."""
from pathlib import Path
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40g_segments.b3 import coordinate_segments
from .identity import CAMPAIGN, require
from .b1 import load_b1_as_a0
from .electrical import load as load_electrical
from .feedback import solve_feedback
from .recourse import solve_fixed_route
from .mobility import search_once


def certified_context(certificate, expected_builder, construct_context):
    """Only validated output paths are handed to a numerical context loader."""
    outputs = load_electrical(certificate, expected_builder)
    return construct_context(outputs, expected_builder())


def b3(repo, day, accepted_b1, b1_expected_builder, trajectory, context,
       electrical_certificate, electrical_expected_builder, m1_identity_builder, output, progress):
    gate = read(Path(repo) / CAMPAIGN / 'EXECUTION_AUTHORIZATION.json')
    require(gate.get('B2_B3_AUTHORIZED') == 'YES', 'B2_B3_NOT_AUTHORIZED')
    from .numerical_context import require_attested_context
    require_attested_context(context, electrical_certificate, electrical_expected_builder)
    handle = load_b1_as_a0(accepted_b1, b1_expected_builder, trajectory, context)
    from .freeze import verify_scientific_freeze
    verify_scientific_freeze(repo)
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from .beam_driver import _restore_slots
    def m1(pcc, cert):
        identity = m1_identity_builder(handle, context)
        value = search_once(repo, day, pcc, context, Path(output) / 'M1', progress, identity)
        write_json(Path(output) / 'M1_GENERATION_IDENTITY.json', identity)
        # The inherited search returns a result dictionary, not a trajectory.
        return MessTrajectory(tuple(_restore_slots(value['trajectory_slots']))), value
    return coordinate_segments(handle['jobs'], context, m1,
        lambda jobs, mess: solve_feedback(jobs, mess, context),
        lambda pcc, mess, cert: solve_fixed_route(pcc, mess, context),
        {'B1_generation_SHA': handle['B1_GENERATION_IDENTITY_SHA'], 'electrical': electrical_expected_builder()})


def fresh(electrical_certificate, expected_builder, jobs, context, execute):
    from .numerical_context import require_attested_context
    require_attested_context(context, electrical_certificate, expected_builder)
    from dayahead.v40g_segments.canonical import planning_power, identities
    return execute(planning_power(jobs, context), identities(jobs), expected_builder())


def actual(electrical_certificate, expected_builder, jobs, observations, **kwargs):
    load_electrical(electrical_certificate, expected_builder)
    from .actual import replay_jobs
    return replay_jobs(jobs, observations, **kwargs)
