"""Segment-certified B1 -> A0 -> M1 -> A1 -> MF construction.

The production entry point is blocked by the execution authorization gate.
The state machine can be verified with synthetic callbacks without B3 science.
"""
from dataclasses import dataclass
from pathlib import Path
from copy import deepcopy
import numpy as np
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40a.invariants import digest
from dayahead.v40g.reuse import accepted_b1_as_a0, persist_reuse
from .canonical import import_frozen, identities, planning_power, terminal_audit, require


@dataclass(frozen=True)
class SegmentB1AsA0:
    source: object
    canonical_path: Path
    canonical_file_SHA: str
    identity: dict

    def load(self, context):
        self.source.verify()
        require(sha(self.canonical_path) == self.canonical_file_SHA, 'CANONICAL_B1_FILE_DRIFT')
        jobs = read(self.canonical_path)
        require(jobs == import_frozen(read(self.source.accepted_b1_path)['jobs']), 'B1_A0_NORMALIZATION_DRIFT')
        require(identities(jobs) == self.identity, 'B1_A0_SEGMENT_IDENTITY')
        power = planning_power(jobs, context)
        with np.load(self.source.b1_trajectory_path) as z:
            for key in ('gpu', 'it', 'pcc', 'qcc'):
                require(np.array_equal(power[key], z[key]), 'B1_SEGMENT_TRAJECTORY_IDENTITY:' + key)
        return jobs, power


def bind_b1(accepted, trajectory, context, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    source = accepted_b1_as_a0(accepted, trajectory)
    alias = persist_reuse(source, output)
    jobs = import_frozen(read(accepted)['jobs']); identity = identities(jobs)
    path = output / 'CANONICAL_B1_FINAL_AS_A0.json'
    if path.exists(): require(read(path) == jobs, 'CANONICAL_A0_ALIAS_DRIFT')
    else: write_json(path, jobs)
    handle = SegmentB1AsA0(source, path, sha(path), identity)
    reused, power = handle.load(context)
    gate = {**alias, 'B1_B3_A0_SEGMENT_IDENTITY': 'PASS', 'B1_segment_identity': identity,
        'B3_A0_segment_identity': identities(reused), 'common_normalization_is_optimization': False,
        'GPU_SHA': digest(power['gpu']), 'IT_SHA': digest(power['it']),
        'PCC_P_SHA': digest(power['pcc']), 'PCC_Q_SHA': digest(power['qcc']),
        'complete_migration_events_in_identity': True, 'B3_A0_optimize_calls': 0}
    write_json(output / 'SEGMENT_A0_REUSE_GATE.json', gate)
    return handle


def coordinate_segments(jobs, context, search_numeric, feedback, recourse_numeric, authority, *, tolerance=1e-6):
    """One search and one recourse, both receiving only certified numeric PCC.

    Used by the gated production entry and bounded synthetic contract tests.
    No optimizer/A0 constructor is reachable before M1.
    """
    from . import coordination
    from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
    original = identities(jobs); m1_binding = {}

    def evaluate(current, mess):
        power = planning_power(current, context)
        return evaluate_grid(context.coefficients,
            controls_from_trajectory(context.coefficients, power['pcc'], () if mess is None else mess.slots), context.nodes)

    def full_search(current):
        require(identities(current) == original, 'M1_REQUIRES_EXACT_B1_SEGMENTS')
        power = planning_power(current, context)
        certificate = {**original, 'PCC_SHA': digest(power['pcc']), 'GPU_SHA': digest(power['gpu']),
            'conditioning_authority': deepcopy(authority), 'B2_result_reused': False}
        frozen_power = digest(power['pcc'])
        result = search_numeric(power['pcc'], certificate)
        require(digest(power['pcc']) == frozen_power and identities(current) == original, 'M1_MUTATED_AIDC')
        m1_binding.update(certificate)
        return result

    def guarded_feedback(current, m1):
        before = deepcopy(current); before_sha = identities(current)
        result = feedback(current, m1)
        require(identities(current) == before_sha, 'A1_MUTATED_INPUT')
        old = {r['job_uid']: r for r in before}
        from dayahead.v40h.feedback import candidates
        for row in result['jobs']:
            previous = old[row['job_uid']]
            allowed = candidates(previous, context.capacity)
            require(any(row == x for x in allowed), 'A1_UNAUTHORIZED_SEGMENTS')
            if previous['state_at_issue'] == 'RUNNING':
                require(identities([row]) == identities([previous]), 'A1_RUNNING_SEGMENT_EVENT_DRIFT')
        terminal_audit(before, result['jobs'])
        return result

    def recourse(current, m1):
        frozen = identities(current); power = planning_power(current, context)
        frozen_power = digest(power['pcc'])
        certificate = {**frozen, 'PCC_SHA': frozen_power, 'GPU_SHA': digest(power['gpu'])}
        result = recourse_numeric(power['pcc'], m1, certificate)
        require(identities(current) == frozen and digest(power['pcc']) == frozen_power, 'MF_CHANGED_FROZEN_AIDC')
        result['frozen_AIDC_segment_certificate'] = certificate
        return result

    result = coordination.coordinate(jobs, full_search, guarded_feedback, recourse, evaluate, authority, tolerance)
    result.update(B3_A0_optimize_calls=0, M1_segment_conditioning=m1_binding,
                  A0_segment_identity=original, A1_segment_identity=identities(result['a1']))
    return result


def run(repo, handle, context, output, progress):
    """Future production route; current correction never authorizes this call."""
    from .authority import REL
    gate = read(Path(repo) / REL / 'EXECUTION_AUTHORIZATION.json')
    require(gate.get('B2_B3_AUTHORIZED') == 'YES', 'B2_B3_EXECUTION_NOT_AUTHORIZED')
    from dayahead.v40e.smoke import search
    from dayahead.v40a.recourse import solve_fixed_route
    from .feedback import solve_feedback
    jobs, _ = handle.load(context)
    authority = {'B1_decision_SHA': handle.source.decision_sha,
        'B1_trajectory_SHA': handle.source.trajectory_file_sha,
        'corrected_input_SHAs': context.input_shas, **handle.identity}

    def m1(pcc, certificate):
        write_json(Path(output) / 'M1_SEGMENT_CONDITIONING.json', certificate)
        return search(Path(repo), '2025-05-01', 'B3', pcc, context, Path(output) / 'M1', progress)

    return coordinate_segments(jobs, context, m1,
        lambda j, m: solve_feedback(j, m, context),
        lambda p, m, cert: solve_fixed_route(p, m, context), authority)
