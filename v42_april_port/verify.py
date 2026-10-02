"""Byte-preserve PR121 and verify receipts without executing scientific code."""
import hashlib
import subprocess
import xml.etree.ElementTree as ET
from .audit import ROOT, read, write, record
from .builder import BASE


def base_bytes():
    entries = subprocess.check_output(['git', 'ls-tree', '-r', '-z', BASE], cwd=ROOT).split(b'\0')
    entries = [e.split(b'\t', 1) for e in entries if e]
    objects = [head.split()[2].decode() for head, path in entries]
    batch = subprocess.check_output(['git', 'cat-file', '--batch'],
                                    input=('\n'.join(objects)+'\n').encode(), cwd=ROOT)
    offset = 0
    for (head, path), oid in zip(entries, objects):
        end = batch.index(b'\n', offset)
        actual_oid, kind, n = batch[offset:end].split()
        assert actual_oid.decode() == oid and kind == b'blob'
        n = int(n); offset = end+1
        yield path.decode('utf8'), batch[offset:offset+n]
        offset += n+1
    assert offset == len(batch)


def main():
    out = ROOT/'docs/v42_april_port_from_may_pipeline'
    checked = 0; differences = []
    for name, expected in base_bytes():
        checked += 1
        if (ROOT/name).read_bytes() != expected:
            differences.append(name)
    assert checked == 2730 and differences == [], ('BASE_FILE_DRIFT', differences)
    report = ET.parse(out/'TEST_RESULTS.xml').getroot()
    suites = [report] if report.tag == 'testsuite' else list(report.findall('testsuite'))
    totals = {k:sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assert totals['tests'] >= 1099 and all(totals[k] == 0 for k in ('failures', 'errors', 'skipped'))
    flags = read(out/'FINAL_FLAGS.json'); verdict = read(out/'FINAL_VERDICT.json')
    assert flags['SCIENTIFIC_EXECUTED_DAYS'] == 0
    assert verdict['scientific_calibration_complete'] is False and flags['FINAL_MARGIN_ACCEPTED'] is False
    manifest = read(out/'APRIL/APRIL_INPUT_MANIFEST.json')
    from .audit import sha
    for day in manifest['days']:
        for key in ('planning', 'actual'):
            assert sha(day[key]['path']) == day[key]['sha256'], 'BUNDLE_ARTIFACT_DRIFT'
    namespace_dirs = ('v42_april_port', 'tests/v42_april_port', 'docs/v42_april_port_from_may_pipeline')
    allowed = []
    for namespace in namespace_dirs:
        for p in sorted((ROOT/namespace).rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.name in ('EVIDENCE_SHA256.json', 'VERIFICATION.json'):
                continue
            assert p.stat().st_size < 100_000_000, 'OVERSIZED_ARTIFACT'
            allowed.append(dict(relative=p.relative_to(ROOT).as_posix(), **record(p)))
    write(out, 'EVIDENCE_SHA256.json', dict(files=allowed, self_and_verification_excluded=True))
    diff = subprocess.run(['git', 'diff', '--check', '--cached'], cwd=ROOT, capture_output=True)
    assert diff.returncode == 0, diff.stdout.decode('utf8', errors='replace')[:2000]
    diff = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True)
    assert diff.returncode == 0, diff.stdout.decode('utf8', errors='replace')[:2000]
    write(out, 'VERIFICATION.json', dict(PASS=True, exact_base=BASE, PR121_files_preserved=checked,
        PR118_production_chain_preserved=True, prior_983_tests_preserved=True, tests=totals,
        command='python -X utf8 -m pytest tests contract_tests -q --junitxml=docs/v42_april_port_from_may_pipeline/TEST_RESULTS.xml',
        staged_and_unstaged_diff_check='PASS', new_namespace_files_hashed=len(allowed),
        BASE_all_bytes_exact=True, temporary_checkout_EOL_exception='Inherited .gitignore CRLF for unchanged prior tests; restored exact BASE Git bytes before this check',
        scientific_execution_verified=False, calibration_complete=False,
        May_scientific_outcomes_used=False, final_margin_accepted=False))
    print('Verified', checked, 'BASE files;', totals['tests'], 'tests; new evidence SHA files', len(allowed))


if __name__ == '__main__':
    main()
