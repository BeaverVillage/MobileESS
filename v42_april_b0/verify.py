"""Verify source citations, inherited Git identities and new evidence hashes."""
from pathlib import Path
import json
import re
import subprocess
import xml.etree.ElementTree as ET

from v42_native.contracts import require
from .audit import ROOT, OUT, dump, git, sha
from .contracts import BASE, authority_gate

NAMESPACES = ('v42_april_b0/', 'tests/v42_april_b0/', 'docs/v42_april_b0_voltage_margin_calibration/')


def main():
    audit = json.loads((OUT/'B0_AUTHORITY_AUDIT.json').read_text(encoding='utf-8'))
    require(not authority_gate(audit)['B0_APRIL_EXECUTION_AUTHORIZED'], 'AUDIT_STOP_REQUIRED')
    citation_count = 0
    for finding in audit['findings']:
        for e in finding['evidence']:
            require(sha(ROOT/e['path']) == e['sha256'], 'SOURCE_EVIDENCE_SHA_DRIFT')
            require(git('rev-parse', BASE+':'+e['path']).strip() == e['base_git_blob'], 'BASE_BLOB_DRIFT')
            lines = (ROOT/e['path']).read_text(encoding='utf-8').splitlines()
            require(lines[e['line']-1] == e['excerpt'], 'CITATION_LINE_DRIFT')
            citation_count += 1
    base = json.loads((OUT/'PR117_BASE_RECEIPT.json').read_text(encoding='utf-8'))
    require(sha(OUT/'PR117_TRACKED_OBJECTS.csv') == base['inventory_sha256'], 'BASE_INVENTORY_SHA')
    require(git('rev-parse', BASE+'^{tree}').strip() == base['base_tree'], 'BASE_TREE_DRIFT')
    # Covers committed, staged and unstaged original paths; untracked additions are sealed below.
    changes = [row for row in git('diff', '--name-status', BASE).splitlines() if row]
    for row in changes:
        status, path = row.split('\t', 1)
        require(status == 'A' and path.startswith(NAMESPACES), 'INHERITED_TRACKED_BYTES_CHANGED:'+path)
    require(git('merge-base', BASE, 'HEAD').strip() == BASE, 'EXACT_BASE_NOT_ANCESTOR')
    subprocess.check_call(['git','diff','--check',BASE], cwd=ROOT)
    require(len(re.findall(r'\*\*Q\d+\.', (OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8'))) >= 50, 'REVIEW_50_QA')
    root = ET.parse(OUT/'TEST_RESULTS.xml').getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
    tests = sum(int(s.attrib.get('tests',0)) for s in suites)
    failures = sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
    skipped = sum(int(s.attrib.get('skipped',0)) for s in suites)
    new_tests = sum(1 for case in root.iter('testcase') if 'v42_april_b0' in case.attrib.get('classname',''))
    require(new_tests >= 47 and tests > new_tests and failures == 0 and skipped == 0, 'COMPLETE_REGRESSION_CHECKS_REQUIRED')
    files = []
    for namespace in NAMESPACES:
        for path in sorted((ROOT/namespace).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.name in ('EVIDENCE_MANIFEST.json','VERIFICATION.json'):
                continue
            files.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
    dump('EVIDENCE_MANIFEST.json',dict(base_head=BASE, files=files,
         excludes=['EVIDENCE_MANIFEST.json','VERIFICATION.json','__pycache__'],
         note='Manifest is sealed by VERIFICATION.json; verification is sealed by its Git commit. No circular/self hash.'))
    manifest = json.loads((OUT/'EVIDENCE_MANIFEST.json').read_text(encoding='utf-8'))
    require(all(sha(ROOT/r['path']) == r['sha256'] for r in manifest['files']), 'EVIDENCE_SHA')
    dump('VERIFICATION.json',dict(PASS=True, base_head=BASE, inherited_tracked_files=base['tracked_files'],
         inherited_Git_blobs_preserved=True, evidence_citations_verified=citation_count,
         new_evidence_files_sha256_verified=len(files), evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json'),
         tests=tests, passed=tests, failures=failures, skipped=skipped, new_tests=new_tests,
         git_diff_check=True, review_QA=50, B0_gate_failed_as_required=True,
         April_scientific_execution=False, May_used_for_calibration=False, FINAL_MARGIN_ACCEPTED=False,
         interpretation='Unit and inherited regression PASS does not establish B0 authority, April voltages, or margin acceptance.'))
    print(json.dumps(dict(PASS=True,tests=tests,new_tests=new_tests,sha_files=len(files),citations=citation_count)))


if __name__ == '__main__':
    main()
