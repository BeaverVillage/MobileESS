"""Read-only archive validation. Does not launch optimizers or AC replay."""
import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    manifest = read(HERE / 'SOURCE_COPY_MANIFEST.json')
    records = manifest['files']
    assert len({r['path'] for r in records}) == len(records)
    for row in records:
        path = HERE / row['path']
        assert path.resolve().is_relative_to(HERE)
        raw = path.read_bytes()
        assert len(raw) == row['bytes'], path
        assert hashlib.sha256(raw).hexdigest() == row['sha256'], path
        if '--git-index' in sys.argv:
            repo = HERE.parents[1]
            staged = subprocess.check_output(['git', 'show', ':' + path.relative_to(repo).as_posix()], cwd=repo)
            assert hashlib.sha256(staged).hexdigest() == row['sha256'], path
        if path.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=str(path))
    e = HERE / 'evidence'
    result = read(e / 'campaign/RESULT_WITH_ENERGY_EXCEPTION.json')
    assert result['status'] == 'PASS_WITH_USER_ACCEPTED_E_MIN_EXCEPTION'
    accepted = read(e / 'actual_B3/USER_ACCEPTED_COMPLETE.json')
    assert accepted['AC_feasible'] and accepted['independent_replay_PASS']
    assert not accepted['operating_440kWh_floor_feasible']
    events = accepted['energy_floor_exceptions']
    assert {r['slot'] for r in events} == set(range(32, 41))
    assert all(r['mess_id'] == 'MESS06' and 0 < r['energy_min_kWh'] < 440 for r in events)
    for policy, row in result['policies'].items():
        src = {'B0': 'baseline/actual/B0/COMPLETE.json',
               'B1': 'baseline/actual/B1/COMPLETE.json',
               'B2': 'qsafe/B2/COMPLETE.json',
               'B3': 'actual_B3/B3/COMPLETE.json'}[policy]
        complete = read(e / src)
        assert hashlib.sha256((e / src).read_bytes()).hexdigest() == row['Actual_source']['sha256']
        assert complete['summary'] == row['Actual']
        assert complete['AC_feasible'] and complete['independent_replay_PASS']
        assert complete['summary']['converged_slots'] == 96
        assert complete['summary']['controls_settled_slots'] == 96
        assert complete['ROBUST_Q_ONLY_UNRESOLVED_slots'] == 0
    clock = read(e / 'campaign/SEARCH_CLOCK.json')
    assert clock['total_seconds'] == 14400 and not clock['clock_pause_allowed']
    assert clock['cumulative_stage_deadlines'] == [7200, 11040, 12480, 13440, 14400]
    fleet = read(e / 'campaign/FLEET_AUTHORITY.json')
    assert len(set(fleet['fleet_ids'])) == 6 and fleet['initial_total_energy_kwh'] == 4560
    assert fleet['B2_initial_locations'] == fleet['B3_initial_locations'] == fleet['initial_locations']
    core = HERE / 'frozen_code/qsafe/shared/qsafe_shell.py'
    assert core.read_bytes() == (HERE / 'ieee123_port/qsafe_shell.py').read_bytes()
    assert hashlib.sha256(core.read_bytes()).hexdigest() == '04448962bf46b33a15c6350aecd7ac3bd6efe763d1e910e924c5f682a0f39865'
    monitor_proof = read(e / 'campaign/b3_energy_continue_preflight_20260914/MONITOR_VERIFICATION.json')
    for proof in monitor_proof['files']:
        name = proof['path'].replace('\\', '/').split('/')[-1]
        assert hashlib.sha256((HERE / 'frozen_code/monitor' / name).read_bytes()).hexdigest() == proof['sha256']

    # Exercise the real monitor against copied evidence, including stale failure.
    spec = importlib.util.spec_from_file_location('snapshot_monitor', HERE / 'frozen_code/monitor/server.py')
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    original_read = monitor.read
    def archived_read(path):
        for prefix, target in [(monitor.RUN / 'actual_B3_energy_exception_20260914', e / 'actual_B3'),
                               (monitor.RUN, e / 'campaign'), (monitor.BASE, e / 'baseline'),
                               (monitor.SHELL, e / 'qsafe')]:
            if path.is_relative_to(prefix):
                return original_read(target / path.relative_to(prefix))
        return None
    with patch.object(monitor, 'read', side_effect=archived_read):
        state = monitor.status()
    assert state['complete'] and state['current'] == 6 and state['failure'] is None
    assert state['actual_slots'] == 96 and state['energy_exception_authorized']
    assert state['results'][3]['Actual'] == result['policies']['B3']['Actual']['max_phase_line_loading_pu']
    print(json.dumps(dict(status='PASS',sha_verified_files=len(records),policies=4,
                         slots_per_policy=96,shared_qsafe_sha_match=True,
                         completed_monitor_ignores_historical_failure=True,
                         optimization_calls=0,AC_replays=0)))


if __name__ == '__main__':
    main()
