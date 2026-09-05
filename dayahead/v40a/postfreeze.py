"""Fresh and inherited AC restoration run only after a complete joint freeze.

The restoration backend receives immutable AIDC and mobility decisions. Each
accepted electrical correction is sealed before its own Fresh verification.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import time

from .invariants import digest, joint_decision, route_sha, validate_joint


def verify_after_freeze(jobs, trajectory, authority, output, *, fresh_call,
                        restore_call, validate_trajectory, max_rounds, write):
    """Bounded post-freeze verification, with no AIDC or mobility search callback."""
    output = Path(output)
    jobs = deepcopy(jobs)
    aidc_sha = digest(jobs)
    mobility_sha = route_sha(trajectory.slots)
    current = deepcopy(trajectory)
    rows = []
    fresh_seconds = restoration_seconds = 0.0
    for iteration in range(max_rounds + 1):
        if digest(jobs) != aidc_sha or route_sha(current.slots) != mobility_sha:
            raise RuntimeError('POSTFREEZE_DISCRETE_MUTATION')
        validate_trajectory(jobs, current)
        joint = joint_decision(jobs, current.slots, authority)
        sha = validate_joint(joint)
        round_root = output / f'round_{iteration:02d}'
        write(round_root / 'FINAL_JOINT_DECISION.json', joint)
        write(round_root / 'JOINT_DECISION_PAYLOAD.json', {
            'joint_decision': joint, 'AIDC_decision': jobs,
            'MESS_trajectory': [r.to_dict() for r in current.slots]})
        input_sha = digest(current)
        started = time.perf_counter()
        fresh = fresh_call(jobs, current, sha, round_root / 'fresh')
        elapsed = time.perf_counter() - started
        fresh_seconds += elapsed
        if digest(current) != input_sha or digest(jobs) != aidc_sha:
            raise RuntimeError('FRESH_MUTATED_JOINT_DECISION')
        if fresh.schedule_sha256 != sha:
            raise RuntimeError('FRESH_JOINT_SHA_MISMATCH')
        row = {'round': iteration, 'joint_sha256': sha,
               'Fresh_seconds': elapsed, 'summary': fresh.summary}
        rows.append(row)
        write(round_root / 'FRESH_JOINT_BINDING.json', row)
        if not fresh.summary['physical_violation']:
            from dayahead.v39d.actual import validate_actual_fixed_replay
            from dayahead.v38.authority import canonical_sha256
            replay = {'joint_decision': joint, 'AIDC_decision': jobs,
                      'MESS_trajectory': [r.to_dict() for r in current.slots]}
            actual = validate_actual_fixed_replay({'decision': replay}, canonical_sha256(replay))
            actual.update(FINAL_JOINT_DECISION_SHA=sha,
                          Fresh_FINAL_JOINT_DECISION_SHA=fresh.schedule_sha256,
                          replay_scope='EXISTING_FIXED_DECISION_REPLAY_IDENTITY_GATE')
            write(output / 'ACTUAL_FIXED_REPLAY.json', actual)
            report = {'status': 'PASS', 'restoration_rounds': iteration,
                      'Fresh_calls': len(rows), 'Fresh_seconds': fresh_seconds,
                      'AC_restoration_seconds': restoration_seconds,
                      'AIDC_changes_from_Fresh': 0, 'mobility_changes_from_Fresh': 0,
                      'route_search_calls': 0, 'rounds': rows,
                      'FINAL_JOINT_DECISION_SHA': sha}
            write(output / 'POSTFREEZE_VERIFICATION.json', report)
            return {'joint': joint, 'trajectory': current, 'fresh': fresh,
                    'actual': actual, 'report': report}
        if iteration == max_rounds:
            write(output / 'POSTFREEZE_VERIFICATION.json', {
                'status': 'FAIL_CLOSED', 'reason': 'INHERITED_AC_RESTORATION_LIMIT',
                'restoration_rounds': iteration, 'Fresh_calls': len(rows),
                'Fresh_seconds': fresh_seconds, 'AC_restoration_seconds': restoration_seconds,
                'rounds': rows})
            raise RuntimeError('INHERITED_AC_RESTORATION_FAILED_CLOSED')
        started = time.perf_counter()
        candidate, details = restore_call(jobs, deepcopy(current), fresh, sha, iteration + 1)
        restoration_seconds += time.perf_counter() - started
        if digest(jobs) != aidc_sha or route_sha(candidate.slots) != mobility_sha:
            raise RuntimeError('AC_RESTORATION_DISCRETE_MUTATION')
        validate_trajectory(jobs, candidate)
        write(round_root / 'AC_RESTORATION.json', details)
        current = candidate
    raise AssertionError('UNREACHABLE')


def production_verification(repo, day, jobs, trajectory, authority, context, output, write, progress):
    """Use the accepted V17/V37R3 fixed-discrete restoration without tuning."""
    from dayahead.v17_ac_restoration_contract import K_MAX
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY, FROZEN_MESS_WORKTREE, PF_TAN
    from dayahead.v37r3.restoration import (
        extract_ac_violations, frozen_trajectory, local_fresh_ac_restoration_cuts,
        solve_fixed_discrete_recourse)
    from dataclasses import replace
    from .feedback import pcc_from_jobs
    from .grid import evaluate_grid, controls_from_trajectory
    from .recourse import validate_physics
    from . import observability

    repo = Path(repo)
    accumulated = []
    route_table = None

    def frozen(aidc_jobs, mess, sha):
        pcc, _ = pcc_from_jobs(aidc_jobs, context)
        aidc = SimpleNamespace(pcc_p_kw=pcc, pcc_q_kvar=pcc * PF_TAN)
        value = frozen_trajectory(day, 'B3', aidc, mess, round_index=0)
        return aidc, replace(value, source_schedule_sha256=sha)

    def fresh_call(aidc_jobs, mess, sha, destination):
        _, value = frozen(aidc_jobs, mess, sha)
        return run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,
                                context=context.electrical, voltage=context.electrical.voltage,
                                trajectory=value, output=destination, progress=progress)

    def restore_call(aidc_jobs, mess, fresh, sha, iteration):
        nonlocal route_table
        from dayahead.tools.run_v35r3e_r1_beam import _service_mapping
        from dayahead.v35.execution import daily_traffic_authority
        from dayahead.v35.contracts import PHASE_CALIBRATION
        from dayahead.v37.runner import ADMISSION
        aidc, value = frozen(aidc_jobs, mess, sha)
        violations = extract_ac_violations(fresh)
        if not violations:
            raise RuntimeError('FRESH_PHYSICAL_VIOLATION_NOT_EXTRACTED')
        margins_path = repo / 'dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json'
        margins = json.loads(margins_path.read_text(encoding='utf-8'))['margins']
        generated, derivative = local_fresh_ac_restoration_cuts(
            source_repo=SOURCE_DATA_REPOSITORY, electrical=context.electrical,
            voltage=context.electrical.voltage, frozen=value, fresh=fresh,
            violations=violations, iteration_index=iteration, margins=margins)
        if not generated:
            raise RuntimeError('FRESH_VIOLATION_GENERATED_ZERO_CUTS')
        accumulated.extend(generated)
        if route_table is None:
            _, _, route_table, _ = daily_traffic_authority(
                FROZEN_MESS_WORKTREE, FROZEN_MESS_WORKTREE / 'dayahead/cache/v35', PHASE_CALIBRATION, day, ADMISSION)
        observability.install(Path(output).parent / 'solver_events', 'AC_RESTORATION')
        result = solve_fixed_discrete_recourse(
            repo=repo, case='B3', aidc=aidc, electrical=context.electrical,
            route_table=route_table, service_to_pcc=_service_mapping(),
            selected_trajectory=mess, restoration_cuts=tuple(accumulated))
        return result.trajectory, {
            'iteration': iteration, 'new_cut_count': len(generated), 'total_cut_count': len(accumulated),
            'cuts': [c.payload() for c in accumulated], 'derivative_audit': derivative,
            'solver_status': result.solver_status, 'solver_seconds': result.solve_seconds,
            'cut_arithmetic': list(result.restoration_cut_arithmetic),
            'route_search_calls': 0, 'AIDC_optimization_calls': 0}

    def validate(aidc_jobs, mess):
        pcc, _ = pcc_from_jobs(aidc_jobs, context)
        grid = evaluate_grid(context.coefficients,
                             controls_from_trajectory(context.coefficients, pcc, mess.slots), context.nodes)
        if grid['status'] != 'PASS' or validate_physics(mess)['status'] != 'PASS':
            raise RuntimeError('POSTFREEZE_PLANNING_OR_PHYSICS_FAILURE')

    return verify_after_freeze(jobs, trajectory, authority, output,
                              fresh_call=fresh_call, restore_call=restore_call,
                              validate_trajectory=validate, max_rounds=K_MAX, write=write)
