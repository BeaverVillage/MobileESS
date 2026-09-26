"""Read-only archival validation; never imports or launches campaign code."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / 'snapshot'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    index = read(ROOT / 'SNAPSHOT_INDEX.json')
    indexed = {}
    for row in index['files']:
        relative = row['path']
        path = (SNAPSHOT / relative).resolve()
        require(path.is_relative_to(SNAPSHOT.resolve()), 'Path outside snapshot')
        require(relative not in indexed, 'Duplicate indexed path')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(len(raw) == row['bytes'] and digest == row['sha256'], relative)
        indexed[relative] = digest
        if path.suffix == '.py':
            ast.parse(raw, filename=relative)
    actual = {p.relative_to(SNAPSHOT).as_posix() for p in SNAPSHOT.rglob('*')
              if p.is_file()}
    require(actual == set(indexed), 'Unindexed or missing snapshot files')
    prefix = index['source_namespace'].replace('\\', '/').rstrip('/') + '/'
    pinned = read(SNAPSHOT / 'RUN_CODE_SHA.json')
    for source, digest in pinned.items():
        source = source.replace('\\', '/')
        require(source.startswith(prefix), 'Unexpected pin root')
        require(indexed.get(source[len(prefix):]) == digest, source)
    for relative, row in read(SNAPSHOT / 'PATCH_MANIFEST.json').items():
        require(indexed['original_source/' + relative] == row['ablation_sha256'],
                'Patched source mismatch: ' + relative)
    manifest = read(SNAPSHOT / 'EXPERIMENT_MANIFEST.json')
    expected = dict(WORKERS=4, THREADS_PER_WORKER=4, DATES=31,
                    AIDC_search_seconds=1320, stage_seconds=[900, 180, 120, 120],
                    TOTAL_AIDC_BUDGET_MATCHED=False, P1_BUDGET_UNCHANGED=True,
                    REMAINING_PRIORITY_BUDGETS_UNCHANGED=True,
                    P2_BUDGET_REDISTRIBUTED=False,
                    WITH_CC4_REUSED_FROZEN_AUTHORITY=True,
                    OLD_NO_CC4_RESULTS_REUSED=False,
                    ACTUAL_FROZEN_BITWISE_EXECUTION_UNCHANGED=False,
                    status='STOPPED_BY_USER')
    for key, value in expected.items():
        require(manifest[key] == value, 'Manifest: ' + key)
    authority = read(SNAPSHOT / 'AUTHORITY_VERIFIED.json')
    require(authority['status'] == 'PASS' and authority['dates'] == 31
            and len(authority['days']) == 31
            and len(authority['verified_leaves']) == 1280
            and authority['baseline_optimizer_calls'] == 0, 'Authority evidence')
    preflight = SNAPSHOT / 'preflight_wiring' / '2025-05-01'
    a1 = read(preflight / 'BUDGET_PREFLIGHT_A1.json')
    a2 = read(preflight / 'BUDGET_PREFLIGHT_A2.json')
    require(a1['GUARDS'] == [900, 0, 180, 120, 120]
            and a1['A1_total'] == 1320 and a1['per_family_scale'] == 1
            and a1['CC4_interface_disabled']
            and a1['MESS_default_unchanged'] == 1800, 'A1 budget evidence')
    require(a2['A2_actual_function_budget_constant'] == 1320
            and a2['MESS_outer_budget_unchanged'] == 1800, 'A2 budget evidence')
    require(a1['solver_optimize_calls'] == a2['solver_optimize_calls'] == 0,
            'Budget check unexpectedly optimized')
    state = read(SNAPSHOT / 'CAMPAIGN_STATUS.json')
    require(state['status'] == 'STOPPED_BY_USER' and not state['active']
            and not state['completed'], 'Campaign stop evidence')
    require(not read(SNAPSHOT / 'USER_STOP.json')['automatic_restart_allowed'],
            'User stop instruction')
    summary = read(SNAPSHOT / 'reports' / 'PAIRED_SUMMARY.json')
    require(summary['completed_pairs'] == 0 and summary['expected_pairs'] == 31,
            'Partial results incorrectly represented')
    for day in range(1, 5):
        status = SNAPSHOT / 'days' / f'2025-05-{day:02}' / 'status'
        require(read(status / 'A1.json')['status'] == 'COMPLETE', 'A1 receipt')
        require(read(status / 'B3.json')['status'] == 'STOPPED_BY_USER', 'B3 receipt')
    print(f'PASS: {len(indexed)} export hashes, {len(pinned)} runtime pins; '
          '1320-second contract; stopped campaign; 0/31 paired dates. No solves.')


if __name__ == '__main__':
    main()
