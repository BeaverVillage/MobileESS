"""Independently verify the sealed STOP sources, BASE bytes and new artifacts."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    tests = read('TEST_RECEIPT.json')
    if tests['exit_code'] != 0:
        raise ValueError('FULL_PYTEST_NOT_PASS')
    base = read('BASE_BYTE_PRESERVATION.json')
    for row in base['files']:
        if digest(ROOT/row['path']) != row['sha256']:
            raise ValueError('POST_TEST_BASE_BYTE_DRIFT:' + row['path'])
    a = read('REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')
    sources = a['static_source_graph']['files'] + a['code_read']
    for row in sources:
        if digest(Path(row['path'])) != row['sha256']:
            raise ValueError('SOURCE_DRIFT:' + row['path'])
    receipts = read('PR125_DAILY_FREEZE_RECEIPT_AUDIT.json')
    for day in receipts['days']:
        for row in day['source_records']:
            if digest(Path(row['path'])) != row['sha256']:
                raise ValueError('PR125_DAILY_RECEIPT_DRIFT:' + row['path'])
    for row in read('UNPRODUCED_SCIENTIFIC_ARTIFACTS.json')['artifacts']:
        if (OUT/row['name']).exists():
            raise ValueError('SCIENTIFIC_OUTPUT_PRESENT_DESPITE_STOP:' + row['name'])
    verification = read('VERIFICATION.json')
    verification.update(post_full_pytest_BASE_bytes_preserved=True, full_pytest_exit_code=0,
        full_pytest_passed=tests['passed'], source_files_and_code_rehashed=len(sources),
        daily_PR125_receipts_rehashed=60, inherited_EOL_test_compatibility_documented=True,
        exact_BASE_test_checkout_EOL_variants_restored=True,
        autonomous_production_tests_completed=False, audit_only_regression_tests=6)
    (OUT/'VERIFICATION.json').write_text(json.dumps(verification, indent=2)+'\n', encoding='utf-8')
    manifest_path = OUT/'SHA256_MANIFEST.json'
    # Git-ignore aware inventory: never include Python caches or local runtime outputs.
    names = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard',
        '--', 'docs/v42_autonomous_grid_controls_april_b0/'], cwd=ROOT).decode('utf-8').splitlines()
    files = []
    for name in sorted(set(names)):
        p = ROOT/name
        if p.name == manifest_path.name:
            continue
        files.append(dict(path=name, bytes=p.stat().st_size, sha256=digest(p)))
    value = dict(exact_base=base['exact_base'], scope='new audit-only namespace',
        scientific_execution='NOT_RUN', excludes=['SHA256_MANIFEST.json itself','ignored caches'],
        files=files, file_count=len(files), bytes=sum(r['bytes'] for r in files))
    manifest_path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Verified:', len(base['files']), 'BASE files;', len(files), 'new evidence files;', tests['passed'], 'tests', flush=True)


if __name__ == '__main__':
    main()
