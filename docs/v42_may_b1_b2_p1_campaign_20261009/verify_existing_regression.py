"""Run the completed common regression profile with Native optimize/presolve=0.

This diagnostic never installs or starts a campaign. All outputs go to the new
D-drive preflight directory; historical sources and ledgers are read-only.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime/v42_may_b1_b2_p1_campaign/scheduler_preflight_20261009'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    if ROOT.drive.upper() != 'D:':
        raise ValueError('D_DRIVE_REQUIRED')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    protected = {name: sha(ROOT / name) for name in names if name and (
        name.endswith('.py') or name.endswith('FREEZE.json') or 'NATIVE_RUNTIME_LEDGER' in name)}
    ledgers = {str(p.resolve()): sha(p) for p in (ROOT / 'runtime').rglob('*LEDGER*.json')}
    source = ROOT / 'docs/v42_m1_anytime_gap_frontier/ZERO_NATIVE_REGRESSION.json'
    prior = json.loads(source.read_text(encoding='utf-8-sig'))
    tests = sorted({name.split('::')[0] for name in prior['passed'] + prior['skipped']})
    env = os.environ.copy()
    temp = RUNTIME / 'tmp'
    temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp), TMP=str(temp), PYTHONDONTWRITEBYTECODE='1',
               V42_ANYTIME_TEST_REPORT=str(OUT / 'ZERO_NATIVE_REGRESSION.json'))
    with (RUNTIME / 'EXISTING_REGRESSION.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p',
            'v42_m1_anytime.pytest_plugin', '-o', 'cache_dir=' + str(RUNTIME / 'pytest_cache'),
            '--basetemp=' + str(temp / 'pytest'), *tests], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT)
    current = json.loads((OUT / 'ZERO_NATIVE_REGRESSION.json').read_text(encoding='utf-8'))
    differences = [name for name, before in protected.items() if sha(ROOT / name) != before]
    ledger_differences = [path for path, before in ledgers.items() if sha(Path(path)) != before]
    missing = sorted(set(prior['passed']) - set(current['passed']))
    write('REGRESSION_SUMMARY.json', dict(
        PASS=result.returncode == 0 and not missing and not differences and not ledger_differences,
        UTC=datetime.now(timezone.utc).isoformat(), exit_code=result.returncode,
        passed=len(current['passed']), skipped=len(current['skipped']), failed=len(current['failed']),
        Native_optimize_calls=0, SKIP_not_PASS=True, historical_passes_missing=missing,
        protected_existing_files=len(protected), changed_existing_files=differences,
        protected_existing_ledgers=len(ledgers), changed_existing_ledgers=ledger_differences,
        historical_profile_source=str(source), historical_profile_SHA256=sha(source),
        log=str(RUNTIME / 'EXISTING_REGRESSION.log'),
        campaign_preflight_PASS=False, campaign_date_adapters_implemented=False))
    write('SOURCE_LEDGER_PRESERVATION.json', dict(PASS=not differences and not ledger_differences,
        protected_existing_files=protected, protected_existing_ledgers=ledgers,
        changed_existing_files=differences, changed_existing_ledgers=ledger_differences,
        optimization_algorithms_changed=False, historical_Runtime_reassigned=False))
    print(json.dumps(json.loads((OUT / 'REGRESSION_SUMMARY.json').read_text()), ensure_ascii=False))
    return result.returncode or bool(missing or differences or ledger_differences)


if __name__ == '__main__':
    raise SystemExit(main())
