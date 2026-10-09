"""Evidence and lifecycle honesty checks; these tests never enter a solver."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import numpy as np

from v42_autonomous_monitor import monitor
from v42_autonomous_monitor.host import Snapshot


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')
    return str(path)


def production(tmp_path):
    write(tmp_path / 'AUTONOMOUS_MANIFEST.json', dict(run_id='production', B2_workers=3, B3_workers=1))
    dates = {f'{arm}/{day}': dict(arm=arm, day=day, status='PENDING')
             for arm in ('B1', 'B2', 'B3') for day in monitor.DAYS}
    cp = dict(run_id='production', state='B2_RUNNING', dates=dates, workers={})
    write(tmp_path / 'SUPERVISOR_STATE.json', cp)
    return cp


def test_unknown_native_never_becomes_zero_or_full_budget():
    assert monitor.runtime({}, {})['Native_Runtime'] is None
    assert monitor.runtime({}, {})['remaining_Native'] is None
    lost = dict(measured_Native_Runtime=18, budget_basis='CONSERVATIVE_LOST_CALL_WINDOW',
                Native_budget_accounted_upper_bound=300)
    observed = monitor.runtime(lost, dict(Native_Runtime=18))
    assert observed['Native_Runtime'] is None
    assert observed['remaining_Native'] is None
    assert observed['conservative_accounted_upper_bound'] == 300
    assert monitor.runtime(dict(measured_Native_Runtime=18, calls=[dict(runtime_unavailable=True)]), {})['Native_Runtime'] is None


def test_inflight_native_requires_matching_completed_ledger():
    ledger = dict(measured_Native_Runtime=10, inflight=dict(track='M'))
    accepted = monitor.runtime(ledger, dict(Native_Runtime=12, Native_Runtime_completed=10))
    assert accepted['Native_Runtime'] == 12
    assert accepted['remaining_Native'] == 5388
    stale = monitor.runtime(ledger, dict(Native_Runtime=6000, Native_Runtime_completed=9))
    assert stale['Native_Runtime'] == 10
    assert stale['remaining_Native'] == 5390


def test_recycled_pid_is_not_live(monkeypatch):
    proc = SimpleNamespace(is_running=lambda: True, create_time=lambda: 20,
                           cmdline=lambda: ['python', 'worker'])
    monkeypatch.setattr(monitor.psutil, 'Process', lambda pid: proc)
    assert not monitor.alive(dict(PID=4, created=19, command=['python', 'worker']))
    assert not monitor.alive(dict(PID=4, created=20, command=['python', 'another']))
    assert monitor.alive(dict(PID=4, created=20, command=['python', 'worker']))


def test_result_sha_identity_and_benchmark_are_enforced(tmp_path):
    path = tmp_path / 'RESULT.json'
    document = dict(identity=dict(arm='B2', day='2025-05-01'), PASS=True)
    write(path, document)
    row = dict(arm='B2', day='2025-05-01', result=str(path), result_SHA=monitor.sha(path))
    assert monitor.result_for(row)[0]['PASS'] is True
    assert monitor.result_for({**row, 'day': '2025-05-02'})[1] == 'MONITOR_RESULT_DAY_ARM_MISMATCH'
    assert monitor.result_for({**row, 'result_SHA': '0'*64})[1] == 'MONITOR_RESULT_SHA_MISMATCH'
    write(path, {**document, 'benchmark_initialization_only': True})
    row['result_SHA'] = monitor.sha(path)
    assert monitor.result_for(row)[1] == 'MONITOR_BENCHMARK_NOT_PRODUCTION'


def test_monitor_uses_explicit_production_and_keeps_31_unknown_days(tmp_path):
    production(tmp_path)
    write(tmp_path / 'initialization_benchmark_v19_99' / 'CHECKPOINT_V19.json', dict(state='COMPLETE'))
    snapshot = monitor.view(tmp_path)
    assert snapshot['state'] == 'B2_RUNNING'
    assert snapshot['read_only'] is True
    assert len(snapshot['rows']) == 31
    assert len(snapshot['chart']['rows']) == 31
    assert all(row['B2'] is None and row['B3'] is None for row in snapshot['chart']['rows'])
    assert snapshot['last_Codex_inspection'] == {}
    assert snapshot['live_worker_count'] == 0
    assert not snapshot['supervisor_alive']
    assert all(snapshot['totals'][arm]['PASS'] == 0 for arm in ('B1', 'B2', 'B3'))


def test_unverified_pass_is_visible_as_evidence_invalid(tmp_path):
    cp = production(tmp_path)
    cp['dates']['B2/2025-05-01'].update(status='PASS', result=str(tmp_path/'missing'), result_SHA='a'*64)
    write(tmp_path / 'SUPERVISOR_STATE.json', cp)
    result = monitor.view(tmp_path)
    assert result['rows'][0]['B2']['status'] == 'EVIDENCE_INVALID'
    assert result['totals']['B2']['PASS'] == 0
    assert result['totals']['B2']['FAIL'] == 1


def test_b1_complete_result_must_match_sealed_origin_outside_new_root(tmp_path):
    root = tmp_path/'new'
    cp = production(root)
    origin = tmp_path/'origin'/'B1_RESULT.json'
    write(origin, dict(identity=dict(arm='B1', day='2025-05-01'), PASS=True))
    record = dict(path=str(origin), sha256=monitor.sha(origin))
    manifest = monitor.read(root/'AUTONOMOUS_MANIFEST.json')
    manifest['B1_results'] = {'B1/2025-05-01': record}
    write(root/'AUTONOMOUS_MANIFEST.json', manifest)
    cp['dates']['B1/2025-05-01'].update(status='PASS', result=str(origin), result_SHA=record['sha256'])
    write(root/'SUPERVISOR_STATE.json', cp)
    assert monitor.view(root)['totals']['B1']['PASS'] == 1
    replacement = root/'replacement.json'
    write(replacement, dict(identity=dict(arm='B1', day='2025-05-01'), PASS=True, edited=True))
    cp['dates']['B1/2025-05-01'].update(result=str(replacement), result_SHA=monitor.sha(replacement))
    write(root/'SUPERVISOR_STATE.json', cp)
    invalid = monitor.view(root)
    assert invalid['totals']['B1']['PASS'] == 0
    assert invalid['rows'][0]['B1']['error'] == 'MONITOR_B1_SEALED_ORIGIN_MISMATCH'


def test_dead_worker_receipt_is_not_a_live_worker(tmp_path):
    cp = production(tmp_path)
    request = write(tmp_path/'attempt'/'request.json', dict(result=str(tmp_path/'attempt'/'RESULT.json'),
                    output=str(tmp_path/'attempt'/'output'), worker_slot=1, attempt_id='test'))
    cp['workers']['B2/2025-05-01'] = dict(request=request, PID=99999999, created=1, command=[])
    write(tmp_path/'SUPERVISOR_STATE.json', cp)
    snapshot = monitor.view(tmp_path)
    assert snapshot['live_worker_count'] == 0
    assert snapshot['workers'][0]['status'] == 'PROCESS_ENDED'
    assert snapshot['workers'][0]['runtime']['Native_Runtime'] is None
    assert snapshot['workers'][0]['bounds']['gap'] is None


def test_fresh_unallocated_native_is_unknown_but_measured_pre_native_zero_is_zero(tmp_path, monkeypatch):
    cp = production(tmp_path)
    attempt = tmp_path/'attempt'
    request = write(attempt/'request.json', dict(result=str(attempt/'RESULT.json'),
                    progress=str(attempt/'progress.json'), output=str(attempt/'output'),
                    worker_slot=1, attempt_id='fresh', implementation_SHA='a'*64))
    write(attempt/'NATIVE_RUNTIME_LEDGER.json', dict(measured_Native_Runtime=0., calls=[], inflight=None))
    write(attempt/'progress.json', dict(phase='M_ORIGINAL_MODEL_BUILD', Native_Runtime=0.))
    cp['workers']['B2/2025-05-01'] = dict(request=request, PID=10, created=1, command=['worker'])
    cp['dates']['B2/2025-05-01'].update(status='RUNNING', request=request)
    write(tmp_path/'SUPERVISOR_STATE.json', cp)
    monkeypatch.setattr(monitor, 'alive', lambda owner: owner.get('PID') == 10)
    monkeypatch.setattr(monitor.psutil, 'Process', lambda pid: SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=1), cpu_times=lambda: (1, 0)))
    snapshot = monitor.view(tmp_path)
    assert snapshot['totals']['B2']['processed'] == 0
    assert snapshot['live_worker_count'] == 1
    assert snapshot['workers'][0]['phase'] == 'M_ORIGINAL_MODEL_BUILD'
    assert snapshot['workers'][0]['source_SHA'] == 'a'*64
    assert snapshot['rows'][0]['B2']['source_SHA'] == 'a'*64
    assert snapshot['rows'][0]['B2']['Native_Runtime'] == 0.
    assert snapshot['workers'][0]['runtime']['remaining_Native'] == 5400.
    assert snapshot['rows'][1]['B2']['Native_Runtime'] is None
    assert snapshot['rows'][0]['B3']['Native_Runtime'] is None


def test_snapshot_http_reads_do_not_recompute_or_touch_scientific_files(tmp_path, monkeypatch):
    production(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    cache = Snapshot(tmp_path)
    cache.refresh()
    monkeypatch.setattr('v42_autonomous_monitor.host.view', lambda root: pytest.fail('HTTP must use cached snapshot'))
    code, data = cache.get()
    assert code == 200 and json.loads(data)['schema'] == 'V42_AUTONOMOUS_MONITOR_V1'
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_missing_production_contract_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='EXPLICIT_PRODUCTION'):
        monitor.view(tmp_path)


def test_b3_actual_requires_sha_verified_fresh_and_exact_line_arrays(tmp_path):
    folder = tmp_path / 'Fresh'
    folder.mkdir()
    arrays = folder / 'fresh' / 'OPENDSS_PHASE_ARRAYS.npz'
    arrays.parent.mkdir()
    np.savez(arrays, branch_kinds=np.array(['line', 'transformer']),
             branch_names=np.array(['line.l1.a', 'transformer.t1.a']),
             phase_current_loading_pu=np.array([[.82, 9.]]*96), convergence=np.ones(96, dtype=bool))
    fresh_path = folder/'FRESH_RESULT.json'
    write(fresh_path, dict(NormalAmps_current=True, converged=True,
          summary=dict(case='B3', day='2025-05-01', namespace='ACTUAL',
                       convergence_count=96, OpenDSS_solve_count=96, rho_max_AC=.82)))
    document = dict(identity=dict(arm='B3', day='2025-05-01'), PASS=True,
                    evaluation=dict(Fresh=dict(folder=str(folder), files=[
                        dict(path=str(p), sha256=monitor.sha(p)) for p in (fresh_path, arrays)])))
    path = tmp_path/'RESULT.json'
    write(path, document)
    row = dict(arm='B3', day='2025-05-01', result=str(path), result_SHA=monitor.sha(path))
    actual = monitor.actual_for(row, document)
    assert actual['available'] and actual['percent'] == pytest.approx(82)
    assert actual['transformer_excluded'] is True
    # Editing a sealed array invalidates the visible measurement.
    with arrays.open('ab') as stream:
        stream.write(b'tampered')
    changed = monitor.actual_for(row, document)
    assert not changed['available'] and 'SHA' in changed['error']


def test_a1_reuse_is_bound_to_equivalence_and_origin_bytes(tmp_path):
    equivalence = dict(PASS=True, complete_domain_sha='same')
    eq = tmp_path/'eq.json'
    origin = tmp_path/'origin.json'
    write(eq, equivalence)
    write(origin, dict(PASS=True))
    rec = lambda p: dict(path=str(p), sha256=monitor.sha(p))
    reuse = dict(day='2025-05-01', verified_reuse=True, new_native_optimize_calls=0,
                 new_native_runtime_seconds=0, historical_runtime_charged_to_B3=False,
                 equivalence=equivalence, equivalence_receipt=rec(eq), origin_receipts=[rec(origin)],
                 producer_source_receipt=rec(origin), source_result=rec(origin), source_result_sha=monitor.sha(origin))
    path = tmp_path/'reuse.json'
    write(path, reuse)
    a1 = SimpleNamespace(source_packet=dict(b1_reuse=reuse),
                         ledger_receipt=json.dumps(dict(native_call_count=0, measured_native_runtime=0)))
    assert monitor.verified_reuse(a1, path, '2025-05-01')
    write(origin, dict(PASS=False))
    with pytest.raises(ValueError, match='ORIGIN_SHA'):
        monitor.verified_reuse(a1, path, '2025-05-01')


def test_initial_candidate_never_becomes_certified_bound(tmp_path):
    bound = dict(UB=None, LB=None, gap=None)
    raw = dict(component='FEASIBILITY_LP', track='M_START', entered_native=True,
               Native_SolCount=1., Native_incumbent=.54, Native_Gap=0.,
               Native_objective_basis='ORIGINAL_OBJECTIVE')
    assert monitor.initial_solution(str(tmp_path), '2025-05-01', bound, {})['status'] == 'SEARCHING'
    candidate = monitor.initial_solution(str(tmp_path), '2025-05-01', bound, dict(calls=[raw]))
    assert candidate['status'] == 'CANDIDATE_UNVALIDATED'
    assert candidate['label'] == 'FULL 검증 중'
    assert candidate['candidate_observed'] and not candidate['scientifically_validated']
    assert candidate['native_candidate_evidence'][0]['raw_native_objective'] == .54
    assert bound == dict(UB=None, LB=None, gap=None)
    auxiliary = {**raw, 'component': 'P1', 'track': 'F2_ALL_96_MODES',
                 'Native_objective_basis': 'AUXILIARY_FEASIBILITY_ZERO', 'Native_incumbent': 0.}
    assert monitor.initial_solution(str(tmp_path), '2025-05-01', bound, dict(calls=[auxiliary]))['status'] == 'SEARCHING'
    validated = monitor.initial_solution(str(tmp_path), '2025-05-01', dict(UB=.54, LB=None, gap=None), dict(calls=[raw]))
    assert validated['status'] == 'FULL_VALIDATED' and validated['scientifically_validated']


def test_actual_three_date_replay_failure_bytes_survive_cached_api(tmp_path, monkeypatch):
    fixture = Path(__file__).parent/'fixtures'/'v42_monitor_initial_solution'/'saved_may01_02_03_validation_failure.json'
    saved = json.loads(fixture.read_text(encoding='utf8'))
    cp = production(tmp_path)
    for slot, case in enumerate(saved, 1):
        day = case['day']
        attempt = tmp_path/'dates'/'B2'/day/'attempt'
        output = attempt/'output'
        output.mkdir(parents=True)
        proof = output/'STATIONARY_DISPATCH_REPLAY.json'
        proof.write_bytes(case['proof_bytes'].encode('utf8'))
        assert monitor.sha(proof) == case['original_proof_SHA']
        write(output/'SCIENTIFIC_CASE_IDENTITY.json', dict(arm='B2', day=day, case_sha=case['case_sha']))
        write(attempt/'NATIVE_RUNTIME_LEDGER.json', dict(calls=[case['native_call']]))
        request = write(attempt/'request.json', dict(result=str(attempt/'RESULT.json'),
            output=str(output), progress=str(attempt/'progress.json'), worker_slot=slot, attempt_id='saved'))
        cp['workers']['B2/'+day] = dict(request=request, PID=100+slot, created=1, command=['worker'])
        cp['dates']['B2/'+day].update(status='RUNNING', request=request)
    write(tmp_path/'SUPERVISOR_STATE.json', cp)
    # Persisted PID receipts are intentionally dead in the fixture; candidate
    # evidence remains visible without falsely reporting a live worker.
    monkeypatch.setattr(monitor, 'alive', lambda owner: False)
    cache = Snapshot(tmp_path)
    cache.refresh()
    code, payload = cache.get()
    assert code == 200
    api = json.loads(payload)
    assert len(api['workers']) == 3 and api['live_worker_count'] == 0
    for worker, case in zip(api['workers'], saved):
        state = worker['initial_solution']
        assert state['status'] == 'VALIDATION_FAILURE'
        assert state['label'] == '후보 생성 · FULL 검증 오류'
        assert state['candidate_observed'] and not state['scientifically_validated']
        assert state['proof_reason'] == 'HYBRID_FINAL_D_PATH_REQUIRED:EVIDENCE'
        assert state['validation_evidence']['sha256'] == case['original_proof_SHA']
        assert worker['bounds']['UB'] is None and worker['bounds']['LB'] is None and worker['bounds']['gap'] is None
        row = next(row for row in api['rows'] if row['day'] == worker['day'])
        assert row['B2']['initial_solution'] == state


def test_failure_receipt_from_different_case_cannot_override_current_candidate(tmp_path):
    write(tmp_path/'SCIENTIFIC_CASE_IDENTITY.json', dict(day='2025-05-01', arm='B2', case_sha='current'))
    write(tmp_path/'STATIONARY_DISPATCH_REPLAY.json', dict(PASS=False, invalid_start_not_supplied=True,
          case_sha='another', reason='wrong'))
    observed = monitor.initial_solution(str(tmp_path), '2025-05-01', {}, dict(calls=[dict(
        component='FEASIBILITY_LP', entered_native=True, Native_SolCount=1)]))
    assert observed['status'] == 'CANDIDATE_UNVALIDATED'
    assert observed['observation_error'] == 'INITIAL_SOLUTION_PROOF_CASE_MISMATCH'
    assert observed['proof_reason'] is None
