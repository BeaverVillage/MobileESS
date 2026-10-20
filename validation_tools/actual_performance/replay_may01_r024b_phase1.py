"""Isolated real May01 A2 Phase I replay; no campaign result is replaced."""
from pathlib import Path
import sys, gzip, pickle, shutil, traceback, inspect
from contextlib import ExitStack
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024b
from v44.common import read, record, atomic, now, verify, digest
from v44.locks import coordinator, worker_slot, process_identity
from v44.execution import case_scope, native_stage
from v44 import a2, q250_m4_v2 as q
from v44_recovery_r024b import operations as ops
from v44_recovery_r024b.phase_rebuild import stage_scope
from v44_recovery_r024b.finite_bound import install as finite_install
from v44_recovery_r024b.snapshot_checks import install as snapshot_install
from v44_recovery_r024b.exact_clean import install as clean_install
from v44_recovery_r024b.native_cpu import install as cpu_install, _stage
from v44_recovery_r024b.thread_policy import numerical_threads
from v44_recovery_r024b.adaptive_pricing import AdaptivePricing
from v42_may_campaign_native90 import a_stage
from v42_may_campaign_native90.a_routing import DayDirectory, rebound
from v42_may_campaign_native90.budget import DateBudget
from v42_a_stage_canary import phase, pricing, targeted
from validation_tools.actual_performance.phase1_fresh_init_fix import fixed_fresh_initializer


class PhaseIComplete(BaseException):
    pass


def run(destination):
    destination.mkdir(parents=True, exist_ok=False)
    old = ops.CAMPAIGN / '2025-05-01/B3/attempt002'
    original_output = old / 'A2/OUTPUT'
    initial = original_output / 'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'
    preserved = [record(old / name) for name in ('RESULT.json', 'A2/RESULT.json', 'M1/RESULT.json')]
    preserved += [record(initial), record(original_output / 'PHASE_I_ZERO_CERTIFICATE.json')]
    permit = ops.validate()
    assert read(ops.OPS / 'STOP_AUTONOMY.json')['user_stop']
    assert not ops.workers(), 'PRODUCTION_WORKER_MUST_BE_STOPPED'
    request = read(old / 'A2/request.json')
    case_root = destination / '2025-05-01/B3/attempt001'
    stage = case_root / 'A2'
    output = stage / 'OUTPUT'
    output.mkdir(parents=True)
    (output / 'STATIC').mkdir()
    request.update(case_root=str(case_root), root=str(stage), output=str(output),
                   campaign_root=str(destination), execution_permit=record(ops.PERMIT))
    for key in ('fresh_a2_parent', 'r024b_continuation', 'r024b_adaptive_parent', 'a2_checkpoint_parent'):
        request.pop(key, None)
    request['sources'] += [record(__file__), record(initial), record(old / 'M1/RESULT.json'),
                          record(inspect.getfile(fixed_fresh_initializer))]
    request = ops.decorate(request, permit)
    verify(request['sources'])
    m1 = read(old / 'M1/RESULT.json')
    roster = original_output / 'BLOCK_PRICING_ORACLE_VERIFICATION.json'
    verify([record(roster)])
    manifest = read(roster)
    verify([r['external_full_block_cache'] for r in manifest['records']])
    shutil.copyfile(roster, output / roster.name)
    atomic(destination / 'PHASE.json', dict(lane='MAIN', UTC=now()))
    atomic(destination / 'ADMISSION.json', dict(UTC=now(), PASS=True,
        algorithm_revision='v44_recovery_r024b', algorithm_sources=ops.sources(),
        initial_state=record(initial), fixed_M1=record(old / 'M1/RESULT.json'),
        fixed_M1_plan_sha=m1['MESS_plan']['plan_sha'], original_results_preserved=preserved,
        replay_kind='REAL_OPTIMIZATION_FROM_ORIGINAL_PRE_NATIVE_INITIAL_SUPPORT',
        accepted_point_or_final_support_imported=False, old_Native_clock_imported=False,
        stop_after='ORIGINAL_PHASE_I_ZERO_AND_FULL_ORIGINAL_REPLAY_BEFORE_FIRST_P1',
        Native_limit=5400, constraints_relaxed=False, campaign_stays_stopped=True))
    print('LOAD_ORIGINAL_PRE_NATIVE_STATE', flush=True)
    with gzip.open(initial, 'rb') as f:
        state = pickle.load(f)
    assert state['_campaign']['Native_calls'] == 0
    assert state['data'][0]['day'] == request['day']
    state['_campaign']['output'] = str(output)
    atomic(destination / 'INITIAL_MODEL.json', dict(UTC=now(),
        compact_sha=state['compact'].fingerprint(), reference_sha=state['reference'].fingerprint(),
        rows=state['compact'].matrix.shape[0], columns=state['compact'].matrix.shape[1],
        initial_candidate_columns=sum(len(v['candidates']) for v in state['metas'].values()),
        adaptive_history_empty=True, initial_support_not_completed_support=True))
    print('INITIAL_MODEL_LOADED', state['compact'].matrix.shape, flush=True)
    budget = DateBudget(stage / 'NATIVE_RUNTIME_LEDGER.json', native_limit=5400.)
    with coordinator(destination) as lease:
        request['lease'] = lease
        atomic(stage / 'request.json', request)
        who = dict(**process_identity(), day=request['day'], arm='B3', worker_slot=1)
        with worker_slot(request['day'], 'B3', 1, root=destination, lease=lease), case_scope(request, lease, who):
            with ExitStack() as stack:
                stack.enter_context(q.install(ops.PERMIT))
                stack.enter_context(native_stage(request))
                stack.enter_context(finite_install())
                stack.enter_context(clean_install())
                stack.enter_context(snapshot_install())
                stack.enter_context(numerical_threads(4))
                stack.enter_context(cpu_install())
                stack.enter_context(fixed_fresh_initializer(destination))
                token = _stage.set(dict(stage='A2', calls=[]))
                stack.callback(_stage.reset, token)
                stack.enter_context(stage_scope(request))
                original_run = stack.enter_context(a2.scope(request, m1))
                native = original_run.__globals__['_native'](request, state, budget, None)
                original_solve = native.solve
                def solve(snapshot, folder, component):
                    if component == 'ORIGINAL_P1':
                        assert read(output / 'PHASE_I_ZERO_CERTIFICATE.json')['PASS']
                        raise PhaseIComplete()
                    return original_solve(snapshot, folder, component)
                native.solve = solve
                full_pricing = rebound(pricing.full_pricing, dict(pricing.full_pricing.__globals__, HISTORY=output))
                target = a_stage.group(targeted, ('worker', 'targeted'), HISTORY=output)
                routed = a_stage.group(phase, ('activate', 'run'), OUT=DayDirectory(request['day'], output),
                                       full_pricing=full_pricing, targeted=target['targeted'])
                try:
                    routed['run'](native, state, request['day'])
                    raise AssertionError('PHASEI_DIAGNOSTIC_MUST_STOP_BEFORE_P1')
                except PhaseIComplete:
                    zero = read(output / 'PHASE_I_ZERO_CERTIFICATE.json')
                    trajectory = read(output / 'PHASE_I_TRACE.json')
                    progress = read(output / 'R024B_ADAPTIVE_PROGRESS.json')
                    explorations = [read(p) for p in (output / 'PHASE_I').glob('S*/PRICE/R024B_CLASS_EXPLORATION.json')]
                    verify(preserved)
                    atomic(destination / 'RESULT.json', dict(UTC=now(), PASS=True,
                        scope='MAY01_B3_A2_CURRENT_PHASE_I_ONLY_REAL_NATIVE_REPLAY',
                        zero_certificate=record(output / 'PHASE_I_ZERO_CERTIFICATE.json'),
                        Native_seconds=budget.used(), Native_calls=len(budget.calls),
                        original_campaign_P1_integer_Actual_not_rerun=True,
                        initial_support_from_original_pre_native_state=True,
                        old_accepted_point_bound_clock_loaded=False,
                        activation_rounds=trajectory['activation_rounds'], trajectory=trajectory['trajectory'],
                        adaptive_feedback=progress['feedback'], class_exploration=explorations,
                        original_results_byte_preserved=True, campaign_remains_stopped=True))
                    print('REAL_PHASE_I_PASS', budget.used(), 'activation_rounds', trajectory['activation_rounds'], flush=True)
    verify(preserved)


if __name__ == '__main__':
    destination = Path(sys.argv[1])
    try:
        run(destination)
    except BaseException as error:
        atomic(destination / 'ERROR.json', dict(UTC=now(), error=repr(error), traceback=traceback.format_exc()))
        raise
