"""One ordered A/M/Actual pipeline, with independent acceptance at each edge.

Backends receive one frozen authority and one cumulative native budget per
stage. A production backend must provide its original independent verifiers;
the default committed-evidence backend never starts an optimization.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Protocol
import json
from v42_native.contracts import digest, require, write_once, lex_not_worse
from .audit import ROOT, REPORTS, A_HEAD, M_HEAD, C3_HEAD, write
from .policy import Policy, NativeBudget, STAGES
from .interface import validate_handoff


def configuration(path=None):
    c = json.loads(Path(path or ROOT/'V42_CONFIG.json').read_text(encoding='utf8'))
    require(c['schema'] == 'V42_SINGLE_ENVIRONMENT_V1' and c['branch'] == 'v42', 'V42_CONFIG_SCHEMA')
    require(Path(c['workspace']).resolve() == ROOT.resolve() and ROOT.drive.upper() == 'D:', 'V42_D_WORKSPACE')
    require((c['A_source_head'], c['M_completed_source_head'], c['M_scientific_authority_head']) ==
            (A_HEAD, M_HEAD, C3_HEAD), 'V42_SOURCE_AUTHORITY_DRIFT')
    require(tuple(c['stages']) == STAGES and not c['memory_limits'] and not c['memory_automatic_stop'], 'V42_POLICY_DRIFT')
    Policy(**c['policy'])
    return c


class PipelineBackend(Protocol):
    def execute(self, stage, request, budget): ...
    def verify(self, stage, result, request): ...
    def combine(self, aidc, mess, authority): ...
    # actual delegates to v42_native.actual.run_dday_actual, which owns the
    # sole backend.fresh_ac call. The next stage exposes its checked receipt.
    def actual(self, frozen_plan, output): ...
    def fresh_ac_receipt(self, frozen_plan, actual, output): ...
    def validate_actual(self, frozen_plan, actual, fresh): ...


def require_stage(stage, result, request, independent, policy):
    require(independent.get('PASS') is True and independent.get('original_integer_physical_PASS') is True,
            'ORIGINAL_STAGE_INTEGER_PHYSICAL_REPLAY_REQUIRED')
    require(independent.get('input_identity') == request['input_identity'], 'STAGE_INPUT_IDENTITY_DRIFT')
    require(independent.get('upstream_sha256') == request['upstream_sha256'], 'STAGE_UPSTREAM_DRIFT')
    require(result.get('stage') == stage and result.get('input_identity') == request['input_identity'], 'STAGE_RESULT_IDENTITY')
    require(result['decision_sha256'] == digest(result['decisions']) and independent.get('decision_sha256') == result['decision_sha256'],
            'INDEPENDENT_DECISION_HASH_REQUIRED')
    scope = result.get('acceptance_scope')
    if stage == 'A1' and scope == 'P1_ONLY':
        validate_handoff(result['handoff'])
        require(result.get('A1_ACCEPTED') is False and result.get('P2_certificate') is None, 'P1_ONLY_P2_FABRICATION')
    else:
        require(scope == 'P1_AND_P2' and independent.get('original_P2_certificate_PASS') is True,
                'ORIGINAL_P2_CERTIFICATE_REQUIRED_FOR_STAGE')
    require(independent.get('global_domain_certificate_PASS') is True, 'GLOBAL_DOMAIN_CERTIFICATE_REQUIRED')
    L, U = Fraction(independent['exact_LB']), Fraction(independent['exact_UB'])
    require(U >= L and U >= 0 and (U == L == 0 or U > 0 and (U-L)/U <= Fraction(str(policy.global_gap))),
            'GLOBAL_STAGE_GAP_NOT_ACCEPTED')
    if stage.startswith('M'):
        require(independent.get('AIDC_anchor_unchanged') is True and independent.get('AIDC_decision_variables') == 0,
                'MESS_STAGE_CHANGED_AIDC_ANCHOR')
    if stage == 'A2':
        require(independent.get('MESS_anchor_unchanged') is True, 'A2_CHANGED_FIXED_M1')
    if stage == 'M2':
        require(independent.get('fixed_A2_no_regret_PASS') is True, 'M2_FIXED_A2_NO_REGRET_CERTIFICATE_REQUIRED')
    return True


def run_pipeline(backend: PipelineBackend, authority, output, *, config=None):
    c = config or configuration()
    policy = Policy(**c['policy'])
    require(authority.get('day') and authority.get('input_authority_hashes') and authority.get('grid_array_identities'),
            'SINGLE_FROZEN_AUTHORITY_REQUIRED')
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT.resolve()), 'OUTPUT_MUST_BE_IN_D_V42')
    output.mkdir(parents=True, exist_ok=False)
    # Canonical detached state prevents backend writes from altering upstream.
    original_authority = deepcopy(authority)
    authority_sha = digest(authority)
    states = {}; receipts = {}
    for stage in STAGES[:4]:
        upstream = dict(AIDC=states.get('A1' if stage in ('M1','A2') else 'A2'),
                        MESS=states.get('M1'))
        request = dict(stage=stage, day=authority['day'], authority=deepcopy(original_authority),
                       input_identity=authority_sha, upstream=deepcopy(upstream), upstream_sha256=digest(upstream),
                       warm_start=deepcopy(states.get('A1' if stage=='A2' else 'M1' if stage=='M2' else '_none')),
                       policy=c['policy'])
        budget = NativeBudget(stage, policy, native_allowed=c['integration_native_optimize_allowed'])
        if c['integration_native_optimize_allowed']:
            result = backend.execute(stage, deepcopy(request), budget)
        else:
            from contextlib import ExitStack
            from .replay import forbid_native
            with ExitStack() as guard:
                forbid_native(guard)
                result = backend.execute(stage, deepcopy(request), budget)
        if result.get('status') in ('NOT_RUN', 'NOT_CERTIFIED', 'PENDING'):
            stopped = dict(status='INTEGRATION_READY_SCIENCE_PENDING', stopped_at=stage,
                           reason=result.get('reason'), stages=receipts, result=result,
                           completed_pipeline=False, M1_ACCEPTED=False, native_optimize_calls=sum(
                               r['runtime']['native_calls'] for r in receipts.values()))
            write_once(output/'PIPELINE_RESULT.json', stopped)
            return stopped
        begin = perf_counter()
        independent = backend.verify(stage, deepcopy(result), deepcopy(request))
        budget.validation_seconds += perf_counter()-begin
        require_stage(stage, result, request, independent, policy)
        require(digest(authority) == authority_sha, 'PIPELINE_AUTHORITY_MUTATED')
        runtime = budget.receipt()
        require(runtime['native_Runtime'] <= policy.native_seconds, 'CUMULATIVE_NATIVE_LIMIT_EXCEEDED')
        receipts[stage] = dict(result=result, independent=independent, runtime=runtime)
        states[stage] = deepcopy(result)
        write_once(output/stage/'STAGE_RESULT.json', receipts[stage])
    # Every edge was independently accepted before the final operational freeze.
    from v42_native.planning import freeze_day_ahead_plan
    final = backend.combine(states['A2'], states['M2'], deepcopy(original_authority))
    require(final['input_authority_hashes'] == authority['input_authority_hashes'], 'FINAL_AUTHORITY_DRIFT')
    from .execution import operational_scope
    with operational_scope(original_authority, receipts):
        frozen = freeze_day_ahead_plan(final, output/'PLANNING_FREEZE', grid_sha=final['grid_anchor']['grid_sha'])
        actual = backend.actual(frozen, output/'ACTUAL')
    require(actual.get('global_MILP_calls') == 0 and actual.get('local_PQ_repair', 0) == 0,
            'ACTUAL_REOPTIMIZATION_FORBIDDEN')
    require(actual['plan_sha256'] == frozen.plan_sha, 'ACTUAL_FROZEN_PLAN_DRIFT')
    with operational_scope(original_authority, receipts):
        fresh = backend.fresh_ac_receipt(frozen, deepcopy(actual), output/'FRESH_AC')
    from v42_native.actual import require_fresh_ac
    require_fresh_ac(fresh, frozen.plan_sha, frozen.grid_sha)
    validation = backend.validate_actual(frozen, deepcopy(actual), deepcopy(fresh))
    require(validation.get('PASS') is True and validation.get('frozen_input_identity_PASS') is True,
            'FINAL_VALIDATION_REQUIRED')
    write_once(output/'ACTUAL'/'RESULT.json', actual)
    write_once(output/'FRESH_AC'/'RESULT.json', fresh)
    write_once(output/'VALIDATION'/'RESULT.json', validation)
    result = dict(status='V42_VALIDATED', completed_pipeline=True, M1_ACCEPTED=True,
                  stages=receipts, plan_sha256=frozen.plan_sha, validation=validation,
                  practical_runtime_PASS=all(r['runtime']['practical_wall_PASS'] for r in receipts.values()))
    write_once(output/'PIPELINE_RESULT.json', result)
    return result


def saved_pipeline_status():
    """Default entry: materialized A1 edge and blocked M1, zero solver calls."""
    c = configuration()
    handoff = json.loads((REPORTS/'A1_P1_ONLY_TO_M1_HANDOFF.json').read_text(encoding='utf8'))
    validate_handoff(handoff)
    from .replay import pinned
    status = pinned(ROOT/'docs/v42_m1_group_branching_20261008/FINAL_DECISION.json', M_HEAD)
    result = dict(schema='V42_PIPELINE_RESULT_V1', status='INTEGRATION_READY_SCIENCE_PENDING',
                  stages=list(STAGES), A1_P1_ONLY_ACCEPTED=True, A1_ACCEPTED=False,
                  A1_day=handoff['anchor']['day'], A1_to_M1_handoff_sha256=digest(handoff),
                  stopped_at='M1', reason='NEW_P1_ONLY_INPUT_HAS_NO_ACCEPTED_M1_RESULT',
                  M1_ACCEPTED=False, historical_M1_global_gap_percent=status['new_global_gap_percent'],
                  historical_M1_result_applies_to_new_input=False,
                  A2='NOT_RUN', M2='NOT_RUN', Planning_Freeze='NOT_RUN', Actual='NOT_RUN', Fresh_AC='NOT_RUN',
                  Validation='NOT_RUN', native_optimize_calls=0, complete_pipeline=False,
                  policy=c['policy'], pending_M_research_polled=False)
    write(REPORTS/'V42_PIPELINE_STATUS.json', result)
    return result
