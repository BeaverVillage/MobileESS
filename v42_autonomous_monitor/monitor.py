"""Observe persistent evidence without importing dispatch or calling a solver.

HTTP requests serve a cached snapshot. Only the observer thread reads journals;
it never acquires a campaign/solver lock and never writes scientific artifacts.
"""
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import time

import psutil

from v42_b2_monitor_v15.actual import metric, measured
from v42_b2_monitor_v16.certificates import bounds

DAYS = tuple(f'2025-05-{i:02d}' for i in range(1, 32))
ACTIVE = {'PENDING', 'RUNNING', 'RETRY_READY', 'START_REQUESTED'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def rounded_bound(value, upper):
    shown = float(value)
    if not math.isfinite(shown):
        raise ValueError('MONITOR_FINITE_BOUND_REQUIRED')
    if (upper and Fraction(shown) < value) or (not upper and Fraction(shown) > value):
        shown = math.nextafter(shown, math.inf if upper else -math.inf)
    return shown


def read(path, default=None):
    if not path:
        return default if default is not None else {}
    try:
        with Path(path).open(encoding='utf-8-sig') as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return default if default is not None else {}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stamp(path):
    info = Path(path).stat()
    return info.st_mtime_ns, info.st_size


@lru_cache(maxsize=160)
def sealed(path, expected, file_stamp):
    if not expected or sha(path) != expected:
        raise ValueError('MONITOR_RESULT_SHA_MISMATCH')
    return read(path)


def alive(identity):
    try:
        proc = psutil.Process(identity['PID'])
        return (proc.is_running() and proc.create_time() == identity['created']
                and proc.cmdline() == identity['command'])
    except (KeyError, TypeError, psutil.Error):
        return False


def age(timestamp, epoch):
    try:
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return max(0., epoch - parsed.timestamp())
    except (ValueError, TypeError, AttributeError):
        return None


def terminal(status):
    return bool(status) and status not in ACTIVE and not status.startswith('HELD')


def result_for(row):
    if not row.get('result') or not row.get('result_SHA'):
        return {}, None
    try:
        document = sealed(row['result'], row['result_SHA'], stamp(row['result']))
        identity = document.get('identity', {})
        if identity.get('arm') != row['arm'] or identity.get('day') != row['day']:
            raise ValueError('MONITOR_RESULT_DAY_ARM_MISMATCH')
        if document.get('benchmark_initialization_only'):
            raise ValueError('MONITOR_BENCHMARK_NOT_PRODUCTION')
        return document, None
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {}, str(error)


def request_for(row):
    path = row.get('request')
    if not path and row.get('result'):
        path = str(Path(row['result']).parent / 'request.json')
    return read(path)


def actual_for(row, document):
    if document.get('files'):
        return metric(row)
    # B3 seals its Fresh pair inside evaluation; the enclosing RESULT SHA has
    # already been checked. Reuse the same strict Actual/array verifier.
    try:
        fresh = document.get('evaluation', {}).get('Fresh', {})
        if not fresh.get('folder'):
            return dict(available=False)
        folder = Path(fresh['folder'])
        paths = (folder / 'FRESH_RESULT.json', folder / 'fresh' / 'OPENDSS_PHASE_ARRAYS.npz')
        receipts = []
        for path in paths:
            matches = [r for r in fresh.get('files', []) if Path(r['path']).resolve() == path.resolve()]
            if len(matches) != 1:
                raise ValueError('MONITOR_B3_SEALED_FRESH_PAIR_REQUIRED')
            receipts.append(matches[0])
        return measured(row['result'], row['result_SHA'], stamp(row['result']),
                        str(paths[0]), receipts[0]['sha256'], stamp(paths[0]),
                        str(paths[1]), receipts[1]['sha256'], stamp(paths[1]), row['arm'], row['day'])
    except (OSError, ValueError, TypeError, KeyError) as error:
        return dict(available=False, reason='Actual 근거 확인 필요', error=str(error))


def verified_reuse(a1, receipt_path, day):
    reuse = a1.source_packet.get('b1_reuse')
    receipt = read(receipt_path)
    ledger = json.loads(a1.ledger_receipt)
    if (not reuse or receipt != reuse or reuse.get('day') != day
            or reuse.get('verified_reuse') is not True
            or reuse.get('new_native_optimize_calls') != 0
            or reuse.get('new_native_runtime_seconds') != 0
            or reuse.get('historical_runtime_charged_to_B3') is not False
            or reuse.get('equivalence', {}).get('PASS') is not True
            or ledger.get('native_call_count') != 0 or ledger.get('measured_native_runtime') != 0):
        raise ValueError('MONITOR_B1_A1_VERIFIED_REUSE_REQUIRED')
    for record in reuse.get('origin_receipts', []) + [reuse['equivalence_receipt'], reuse['producer_source_receipt'], reuse['source_result']]:
        if sha(record['path']) != record['sha256']:
            raise ValueError('MONITOR_B1_A1_REUSE_ORIGIN_SHA_MISMATCH')
    equivalence = read(reuse['equivalence_receipt']['path'])
    if equivalence != reuse['equivalence'] or reuse['source_result']['sha256'] != reuse['source_result_sha']:
        raise ValueError('MONITOR_B1_A1_REUSE_EQUIVALENCE_DRIFT')
    return True


def b2_bound(output, day):
    try:
        found = bounds(output, day) if output else {}
        return dict(UB=found.get('UB', {}).get('value'),
                    LB=found.get('LB', {}).get('value'), gap=found.get('Gap'),
                    target=.03, scope='ORIGINAL_FULL_GLOBAL',
                    status='CERTIFIED' if 'Gap' in found else 'UNKNOWN', evidence=found)
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError) as error:
        return dict(UB=None, LB=None, gap=None, target=.03, status='UNKNOWN', error=str(error))


@lru_cache(maxsize=128)
def b3_output(path, expected, file_stamp):
    # This parser validates typed identities and the content digest; it does
    # not construct a model, re-run validation, or enter a source registry.
    from v42_b3_joint.source_coordinator import output_from_document
    output = output_from_document(read(path))
    if output.sha != expected or output.evidence_kind != 'SOURCE':
        raise ValueError('MONITOR_B3_STAGE_CONTENT_SHA_MISMATCH')
    return output


def b3_observation(output, day, stage=None):
    pipeline = Path(output) / 'PIPELINE' if output else None
    state = read(pipeline / 'B3_SOURCE_CHECKPOINT.json') if pipeline else {}
    if state.get('identity', {}).get('day') not in (None, day):
        return dict(stage=stage, status='UNKNOWN', error='MONITOR_B3_CHECKPOINT_DAY_MISMATCH')
    stage = stage or state.get('inflight') or next(iter(reversed(state.get('completed', []))), None)
    result = dict(stage=stage, UB=None, LB=None, gap=None,
                  target=.005 if str(stage).startswith('A') else .03,
                  scope='STAGE_FIXED_INPUT_GLOBAL', status='UNKNOWN', A1_reused=None)
    try:
        a1_path = pipeline / 'A1' / 'B3_SOURCE_STAGE_OUTPUT.json' if pipeline else None
        expected_a1 = state.get('result_shas', {}).get('A1')
        if a1_path and expected_a1 and a1_path.is_file():
            a1 = b3_output(str(a1_path), expected_a1, stamp(a1_path))
            receipt_path = pipeline / 'A1' / 'B1_A1_VERIFIED_REUSE.json'
            if a1.source_packet.get('b1_reuse') and verified_reuse(a1, receipt_path, day):
                result['A1_reused'] = True
                result['A1_reuse_evidence'] = dict(path=str(receipt_path), sha256=sha(receipt_path),
                                                   stage_content_SHA=expected_a1)
        expected = state.get('result_shas', {}).get(stage)
        path = pipeline / str(stage) / 'B3_SOURCE_STAGE_OUTPUT.json' if pipeline else None
        if not expected or not path or not path.is_file():
            return result
        accepted = b3_output(str(path), expected, stamp(path))
        if accepted.request.authority.day != day or accepted.request.stage != stage:
            raise ValueError('MONITOR_B3_STAGE_DAY_MISMATCH')
        physical, cert = accepted.physical_evidence, accepted.global_evidence
        if (physical.get('PASS') is not True or cert.get('PASS') is not True
                or physical.get('original_integer_physical_verified') is not True
                or cert.get('original_global_bound_verified') is not True
                or cert.get('bound_scope') != 'STAGE_FIXED_INPUT_GLOBAL'
                or cert.get('joint_global_optimality_claim') is not False):
            raise ValueError('MONITOR_B3_INDEPENDENT_EVIDENCE_REQUIRED')
        lb, ub = Fraction(cert['exact_LB']), Fraction(cert['exact_UB'])
        if lb < 0 or ub < lb:
            raise ValueError('MONITOR_B3_EXACT_BRACKET_INVALID')
        gap = Fraction(0) if ub == 0 else (ub - lb) / ub
        if gap > (Fraction(1, 200) if str(stage).startswith('A') else Fraction(3, 100)):
            raise ValueError('MONITOR_B3_STAGE_GAP_NOT_ACCEPTED')
        result.update(UB=rounded_bound(ub, True), LB=rounded_bound(lb, False), gap=float(gap), status='CERTIFIED',
                      exact_LB=str(lb), exact_UB=str(ub), exact_gap=str(gap),
                      stage_content_SHA=expected, path=str(path))
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        result.update(UB=None, LB=None, gap=None, status='UNKNOWN', error=str(error))
    return result


def runtime(ledger, progress, cap=5400.):
    completed = ledger.get('measured_Native_Runtime')
    reported = progress.get('Native_Runtime')
    unknown = (ledger.get('budget_basis') == 'CONSERVATIVE_LOST_CALL_WINDOW'
               or any(c.get('runtime_unavailable') for c in ledger.get('calls', []))
               or ledger.get('actual_cumulative_Native_Runtime') == 'UNKNOWN')
    eligible = (not unknown and bool(ledger.get('inflight')) and finite(completed)
                and progress.get('Native_Runtime_completed') == completed
                and finite(reported) and reported >= completed)
    used = reported if eligible else completed
    if unknown or not finite(used):
        used = None
    return dict(Native_Runtime=used, remaining_Native= max(0., cap-used) if used is not None else None,
                Native_limit=cap, native_inflight=bool(ledger.get('inflight')),
                basis='UNKNOWN' if used is None else ('CALLBACK_INCLUDES_INFLIGHT' if eligible else 'COMPLETED_LEDGER'),
                measured_completed=completed if finite(completed) else None,
                conservative_accounted_upper_bound=ledger.get('Native_budget_accounted_upper_bound'),
                calls=len(ledger.get('calls', [])), ledger_present=bool(ledger))


def initial_solution(output, day, bound, ledger, phase=None):
    """Distinguish a raw feasibility witness from a FULL-validated solution.

    Native solution counts/objectives are observations only. They never supply
    an independent UB, LB or Global Gap, even when the native gap is zero.
    """
    candidates = []
    for call in ledger.get('calls', []):
        count = call.get('Native_SolCount', call.get('SolCount'))
        if ((call.get('track') == 'M_START' or call.get('component') in ('FEASIBILITY_LP', 'FEASIBILITY'))
                and call.get('entered_native') is True and finite(count) and count > 0):
            objective = call.get('Native_incumbent')
            candidates.append(dict(track=call.get('track'), component=call.get('component'),
                SolCount=count, observation_UTC=call.get('Native_observation_UTC'),
                raw_native_objective=objective if finite(objective) and call.get('Native_objective_basis') == 'ORIGINAL_OBJECTIVE' else None,
                diagnostic_only=True))
    result = dict(status='SEARCHING', label='초기해 탐색 중',
                  candidate_observed=bool(candidates), scientifically_validated=False,
                  native_candidate_evidence=candidates, proof_reason=None)
    if (phase in ('M_ORIGINAL_MODEL_BUILD', 'M_EXISTING_COMPACT_STATIC_PRESOLVE', 'MODEL_PREPARATION')
            and not ledger.get('calls') and not ledger.get('inflight')):
        result.update(status='MODEL_PREPARATION', label='원본 모델·정적 검증 중')
    if finite(bound.get('UB')):
        result.update(status='FULL_VALIDATED', label='FULL 검증 완료', scientifically_validated=True)
        return result
    if candidates:
        result.update(status='CANDIDATE_UNVALIDATED', label='FULL 검증 중')
    if not output:
        return result
    path = Path(output) / 'STATIONARY_DISPATCH_REPLAY.json'
    proof = read(path)
    identity = read(Path(output) / 'SCIENTIFIC_CASE_IDENTITY.json')
    if proof and (identity.get('day') != day or identity.get('arm') != 'B2'
                  or proof.get('case_sha') != identity.get('case_sha')):
        result['observation_error'] = 'INITIAL_SOLUTION_PROOF_CASE_MISMATCH'
        return result
    if proof.get('PASS') is False and proof.get('invalid_start_not_supplied') is True:
        result.update(status='VALIDATION_FAILURE', label='후보 생성 · FULL 검증 오류',
                      proof_reason=proof.get('reason', 'FULL_VALIDATION_FAILED'),
                      validation_evidence=dict(path=str(path), sha256=sha(path), case_sha=proof.get('case_sha')))
    return result


def worker_view(key, worker, epoch):
    arm, day = key.split('/', 1)
    request = request_for(worker)
    progress = read(request.get('progress'))
    attempt = Path(request['result']).parent if request.get('result') else None
    heartbeat = read(attempt / 'HEARTBEAT.json') if attempt else {}
    identity = worker if worker.get('PID') else progress.get('worker', {})
    live = alive(identity)
    output = request.get('output')
    if arm == 'B3' and output:
        heartbeat = read(Path(output) / 'HEARTBEAT.json') or heartbeat
        progress = heartbeat if not progress else progress
    stage = progress.get('stage') or heartbeat.get('stage') or ('M' if arm == 'B2' else None)
    if arm == 'B3':
        bound = b3_observation(output, day, stage)
        stage = bound.get('stage')
        ledger_path = Path(output) / 'PIPELINE' / str(stage) / 'NATIVE_RUNTIME_LEDGER.json' if output and stage else None
    else:
        bound = b2_bound(output, day)
        ledger_path = attempt / 'NATIVE_RUNTIME_LEDGER.json' if attempt else None
    ledger = read(ledger_path)
    phase = progress.get('phase') or heartbeat.get('phase') or ('START_REQUESTED' if worker.get('launch_intent') else 'UNKNOWN')
    resource = {}
    if live:
        try:
            proc = psutil.Process(identity['PID'])
            resource = dict(RSS_bytes=proc.memory_info().rss,
                            CPU_seconds=sum(proc.cpu_times()[:2]))
        except psutil.Error:
            pass
    timestamp = heartbeat.get('timestamp_UTC') or progress.get('timestamp_UTC')
    return dict(slot=request.get('worker_slot', worker.get('worker_slot')), arm=arm, day=day,
                PID=identity.get('PID'), alive=live, status='RUNNING' if live else 'PROCESS_ENDED',
                stage=stage, phase=phase, initial_solution_verified=bound.get('UB') is not None,
                initial_solution=initial_solution(output, day, bound, ledger, phase),
                heartbeat_UTC=timestamp, heartbeat_age_seconds=age(timestamp, epoch),
                bounds=bound, runtime=runtime(ledger, progress), resource=resource,
                attempt_id=request.get('attempt_id'), source_SHA=request.get('implementation_SHA', request.get('source_SHA')),
                request=worker.get('request'), ledger_path=str(ledger_path) if ledger_path else None,
                source_admission=(read(Path(output) / 'B3_SOURCE_ADMISSION.json') if arm == 'B3' and output else
                                  read(attempt / 'NATIVE_WORKER_ADMISSION.json') if attempt else {}))


def view(root, epoch=None):
    root = Path(root)
    epoch = time.time() if epoch is None else epoch
    manifest = read(root / 'AUTONOMOUS_MANIFEST.json')
    cp = read(root / 'SUPERVISOR_STATE.json')
    if not manifest or cp.get('run_id') != manifest.get('run_id'):
        raise ValueError('EXPLICIT_PRODUCTION_SUPERVISOR_REQUIRED')
    if manifest.get('B2_workers') != 3 or manifest.get('B3_workers') != 1:
        raise ValueError('MONITOR_PRODUCTION_WORKER_CONTRACT_DRIFT')
    workers = [worker_view(k, w, epoch) for k, w in cp.get('workers', {}).items()]
    recovery = read(root / 'RECOVERY_QUEUE.json').get('entries', [])
    recovery = sorted(recovery, key=lambda r: (-r.get('retry_priority', 0), r.get('date', '')))
    pending_recovery = [r for r in recovery if r.get('verification_status') in
                        {'READY_VERIFIED_REPAIR', 'DISPATCH_INTENT', 'WORKER_ENTERED', 'NATIVE_PROGRESS_VERIFIED'}]
    rows, totals = [], {a: dict(total=31, processed=0, PASS=0, FAIL=0, pending=0) for a in ('B1', 'B2', 'B3')}
    for day in DAYS:
        row = dict(day=day)
        for arm in ('B1', 'B2', 'B3'):
            original = cp.get('dates', {}).get(arm + '/' + day, dict(arm=arm, day=day, status='PENDING'))
            status = original.get('status', 'PENDING')
            document, error = result_for(original)
            if arm == 'B1' and status == 'PASS':
                origin = manifest.get('B1_results', {}).get(arm + '/' + day, {})
                if (not origin or original.get('result_SHA') != origin.get('sha256')
                        or not original.get('result')
                        or Path(original['result']).resolve() != Path(origin.get('path', '')).resolve()):
                    document, error = {}, 'MONITOR_B1_SEALED_ORIGIN_MISMATCH'
            verified_pass = status == 'PASS' and document.get('PASS') is True and not error
            display_status = 'EVIDENCE_INVALID' if status == 'PASS' and not verified_pass else status
            is_terminal = terminal(status)
            totals[arm]['processed'] += is_terminal
            totals[arm]['PASS'] += verified_pass
            totals[arm]['FAIL'] += is_terminal and not verified_pass
            totals[arm]['pending'] += not is_terminal
            request = request_for(original)
            live = next((w for w in workers if w['arm'] == arm and w['day'] == day), None)
            bound = live['bounds'] if live else (b2_bound(request.get('output'), day) if arm == 'B2'
                     else b3_observation(request.get('output'), day) if arm == 'B3' else {})
            native = (live['runtime']['Native_Runtime'] if live else
                      document.get('Native_Runtime', document.get('native_seconds', original.get('Native_Runtime'))))
            if not finite(native):
                native = None
            actual = actual_for(original, document) if arm in ('B2', 'B3') and document else dict(available=False)
            row[arm] = dict(status=display_status, recorded_status=status, result_verified=bool(document) and not error, PASS=verified_pass,
                            Native_Runtime=native, bounds=bound, actual=actual,
                            stage=live.get('stage') if live else bound.get('stage'),
                            A1_reused=bound.get('A1_reused'), result=original.get('result'),
                            result_SHA=original.get('result_SHA'), error=error or document.get('error'),
                            source_SHA=(live.get('source_SHA') if live else document.get('source_SHA',
                                        document.get('source_sha', original.get('source_SHA')))),
                            attempts=original.get('attempt_count'), current_attempt=original.get('current_attempt'))
            if live:
                row[arm]['initial_solution'] = live['initial_solution']
        row['recovery'] = [r for r in recovery if r.get('date') == day]
        b2, b3 = row['B2']['actual'], row['B3']['actual']
        row['rho_difference_pp'] = b3['percent'] - b2['percent'] if b2.get('available') and b3.get('available') else None
        rows.append(row)
    heartbeat = read(root / 'SUPERVISOR_HEARTBEAT.json')
    supervisor_identity = heartbeat.get('process') or read(root / 'SUPERVISOR_PROCESS.json')
    state = cp.get('state', 'UNKNOWN')
    return dict(schema='V42_AUTONOMOUS_MONITOR_V1', read_only=True, runtime_root=str(root),
                run_id=cp['run_id'], snapshot_UTC=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                campaign='B2' if state.startswith('B2') else 'B3' if state.startswith('B3') else 'COMPLETE',
                state=state, totals=totals, workers=workers, live_worker_count=sum(w['alive'] for w in workers),
                configured_workers=dict(B2=3, B3=1), supervisor_alive=alive(supervisor_identity),
                heartbeat_UTC=heartbeat.get('timestamp_UTC'), heartbeat_age_seconds=age(heartbeat.get('timestamp_UTC'), epoch),
                recovery_queue=pending_recovery, recovery_queue_count=len(pending_recovery),
                last_Codex_inspection=read(root / 'LAST_CODEX_INSPECTION.json'), rows=rows,
                chart=dict(unit='percent', definition='96 Actual AC slots, line phases, current / Line NormalAmps',
                           rows=[dict(day=r['day'], B2=r['B2']['actual'].get('percent') if r['B2']['actual'].get('available') else None,
                                      B3=r['B3']['actual'].get('percent') if r['B3']['actual'].get('available') else None) for r in rows]),
                transition_history=cp.get('transition_history', []), last_error=read(root / 'SUPERVISOR_ERROR.json'))
