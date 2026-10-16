"""PR219–221 repeat/feedback controller over the existing Exact Direct core.

No restricted bound is a global bound. Every offered incumbent is replayed
against the current Original FULL model, including after an interrupted call.
"""
from pathlib import Path
import json
from time import perf_counter

from .m_engine import (_write, binding, file_record, vector_sha, matrix_sha, domain_sha,
                       pin_pools, direct_joint, _native_joint, _validate)

RETURN_RESERVE_SECONDS = 10.
JOINT_CAP_SECONDS = 140.


def pool_identity(pools):
    # Canonical route sets: a reordered lambda axis is the same mathematics.
    from .a_engine import digest
    return digest({u: sorted([list(p) for p in paths]) for u, paths in sorted(pools.items())})


def run(case, bank, budget, folder, validator):
    from .m_candidates import generate
    folder = Path(folder)
    state = dict(epoch=0, reservoir={}, used_paths={}, seen_pools=set(), feedback=[])
    case.mess_search_state = state
    generator = getattr(case, 'candidate_generator', None)
    supplied = getattr(case, 'candidate_pools', None)
    if generator is None and supplied is None:
        generator = generate
        case.candidate_generator = generator
    calls, seen_models, history = [], set(), []
    last, reason = None, 'NATIVE_BUDGET_RETURN_RESERVE'
    control=getattr(case,'global_gap_control',None)
    if control is not None:
        from .table_v_global_control import mess_upper
        mess_upper(control,case,bank,Native_remaining=budget.remaining())
        if getattr(case,'global_gap_seed_checkpoint',False):
            return None,dict(history=[],joint_calls=0,unique_pools=0,stop_reason='CERTIFIED_LOWER_BOUND_CHECKPOINT',
                stage_native_seconds=budget.used(),stage_budget_seconds=budget.limit)
    solver = getattr(case,'joint_solver',_native_joint)
    reserve = RETURN_RESERVE_SECONDS if solver is _native_joint or budget.remaining()>RETURN_RESERVE_SECONDS else 0.
    # Finite exhaustion guard; absence of improvement is never a stop rule.
    for epoch in range(1, 1101):
        if control is not None and control.target_met():
            reason='GLOBAL_GAP_TARGET_MET'
            break
        if budget.remaining() <= reserve:
            break
        state['epoch'] = epoch
        tick = perf_counter()
        iteration = folder / f'ITERATION_{epoch:04d}'
        iteration.mkdir()
        case.mess_iteration_output = iteration
        before = bank.fields()['BEST_GLOBAL_UB']
        try:
            center = None if bank.best is None else bank.best[0]
            candidates = generator(case, center, bank, budget) if generator else supplied
            if generator and candidates is None:
                reason = 'DIVERSE_CURRENT_DOMAIN_POOLS_EXHAUSTED'
                break
            pools = pin_pools(case, center, bank, candidates)
            signature = pool_identity(pools)
            if signature in state['seen_pools']:
                history.append(dict(epoch=epoch, status='DUPLICATE_POOL_SKIPPED', pool_sha=signature))
                if generator is None:
                    reason = 'CALLER_POOL_EXHAUSTED'
                    break
                continue
            state['seen_pools'].add(signature)
            _write(iteration/'POOL.json', dict(pools=pools, pool_sha=signature,
                STAY_preserved=True, complete_incumbent_paths_pinned=center is not None,
                seedless=center is None, no_MOVE_forcing=True))
            packet = direct_joint(case, center, pools)
            math_key = (matrix_sha(packet[0]), domain_sha(packet[1]))
            if math_key in seen_models:
                history.append(dict(epoch=epoch,status='DUPLICATE_MATH_MODEL_SKIPPED',pool_sha=signature))
                del packet
                continue
            seen_models.add(math_key)
            _write(iteration/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json', packet[-1])
            seconds = min(JOINT_CAP_SECONDS, budget.remaining()-reserve)
            if seconds <= 0:
                del packet
                break
            solver = getattr(case, 'joint_solver', _native_joint)
            native, captures = solver(case, budget, packet, iteration/'JOINT', seconds)
            del packet
            if solver is not _native_joint:
                native = dict(native, fixture_backend=True, production_execution=False)
            last = native
            calls.append(native)
            unique = set()
            for ordinal, capture in enumerate(captures):
                point = capture['point']
                sha = vector_sha(point)
                if sha in unique:
                    continue
                unique.add(sha)
                cert = _validate(case, point, iteration/f'CAPTURE_{ordinal:03d}.npz', validator)
                _write(iteration/f'CAPTURE_{ordinal:03d}_ROUTE_SELECTION.json',capture.get('route_selection'))
                if cert is not None:
                    bank.offer(point, cert)
                    case.mess_feedback_point=point.copy()
            after = bank.fields()['BEST_GLOBAL_UB']
            if control is not None:
                mess_upper(control,case,bank,Native_Runtime=native.get('Native_Runtime'),Native_remaining=budget.remaining(),pool_sha=signature)
            row = dict(epoch=epoch,pool_sha=signature,pool_counts={u:len(p) for u,p in pools.items()},
                status='REPLAYED',FULL_verified_UB_before=before,FULL_verified_UB_after=after,
                improvement=None if before is None or after is None else before-after,Native_Runtime=native.get('Native_Runtime'),
                wall_seconds=perf_counter()-tick,remaining_native_seconds=budget.remaining(),
                restricted_ObjBound_is_Global_LB=False)
            state['feedback'].append(row)
            history.append(row)
            # Persist every epoch in its own directory. Earlier Raw is immutable.
            bank.save(iteration/'INCUMBENT', binding(case))
            _write(folder/'ADAPTIVE_PROGRESS.json',dict(history=history,joint_calls=len(calls),
                best=bank.fields(),Native_remaining=budget.remaining()))
            if native.get('error'):
                reason = 'NATIVE_CALL_ERROR_BEST_FULL_PRESERVED'
                break
        except Exception as exc:
            record=iteration/'JOINT/NATIVE_CALL.json'
            if record.is_file():
                failed=json.loads(record.read_text(encoding='utf8'))
                calls.append(failed);last=failed
                for i,raw in enumerate(failed.get('recoverable_captures',[])):
                    if file_record(raw['path'])!=raw:continue
                    import numpy as np
                    with np.load(raw['path'],allow_pickle=False) as z:point=z['point'].copy()
                    cert=_validate(case,point,iteration/f'RECOVERED_{i:03d}.npz',validator)
                    if cert is not None:bank.offer(point,cert)
            reason = 'INTERRUPTED_OR_FAILED_BEST_FULL_PRESERVED'
            history.append(dict(epoch=epoch,status=reason,error=repr(exc)))
            _write(iteration/'FAILURE.json',history[-1])
            break
    else:
        reason = 'FINITE_CURRENT_DOMAIN_SEARCH_EXHAUSTED'
    report = dict(history=history,joint_calls=len(calls),unique_pools=len(state['seen_pools']),
        unique_math_models=len(seen_models),stop_reason=reason,
        joint_cap_seconds=JOINT_CAP_SECONDS,return_reserve_seconds=RETURN_RESERVE_SECONDS,
        stage_budget_seconds=budget.limit,stage_native_seconds=budget.used(),
        restricted_ObjBound_is_Global_LB=False,backend='EXACT_DIRECT_ONLY',
        PR219_PR221_repeat_and_feedback=True)
    if control is not None:
        canonical=('GLOBAL_GAP_TARGET_MET' if control.target_met() else
            'IMPLEMENTATION_OR_NUMERICAL_FAILURE' if 'FAILED' in reason or 'ERROR' in reason else
            'NO_FULL_FEASIBLE_SOLUTION' if bank.best is None else
            'NATIVE_BUDGET_EXHAUSTED' if budget.remaining()<=reserve else
            'NO_FURTHER_CERTIFIED_IMPROVEMENT')
        report.update(global_gap_control=control.bounds(),termination_reason=canonical,
            exhausted_scope='CURRENT_APPROVED_CANDIDATE_GENERATOR_NOT_ENTIRE_GLOBAL_ROUTE_DOMAIN')
    _write(folder/'ADAPTIVE_SEARCH.json',report)
    # Static products, path reservoirs and full model references die with stage.
    case.__dict__.pop('_direct_static_cache',None)
    case.__dict__.pop('mess_feedback_point',None)
    return last, report
