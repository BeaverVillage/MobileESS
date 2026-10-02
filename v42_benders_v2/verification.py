"""Seal all new evidence and verify preserved base bytes and execution sources."""
import json,xml.etree.ElementTree as ET
from .common import *

def run():
    base=read('PR115_BASE_RECEIPT.json');changed=[r['path'] for r in base['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not changed and len(base['files'])==1615
    for r in read('DERIVATION_FREEZE.json')['files']:assert sha(OUT/r['path'])==r['sha256']
    for r in read('EXECUTION_FREEZE_FINAL.json')['sources']:assert sha(ROOT/r['path'])==r['sha256']
    suite=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])==789 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    assert read('V2_FIXTURE_EXACTNESS.json')['agreement']==1536
    assert read('FINAL_VERDICT.json')['verdict']=='INCONCLUSIVE'
    assert read('REPORT_GENERATION_RECEIPT.json')['original_bytes_preserved']
    source=[]
    for folder in ['v42_benders_v2','tests/v42_benders_v2']:
        for p in sorted((ROOT/folder).glob('*.py')):source.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    dump('SOURCE_MANIFEST.json',source)
    evidence=[]
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and p.name not in ['SOURCE_MANIFEST.json','EVIDENCE_MANIFEST.json','VERIFICATION.json']:
            evidence.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    dump('EVIDENCE_MANIFEST.json',evidence)
    dump('VERIFICATION.json',dict(PASS=True,base=BASE,preserved_tracked_files=1615,changed_base_files=changed,
        inherited_tests=708,added_tests=81,total_tests=789,tests_failures=0,tests_errors=0,
        tests_seconds=float(suite.attrib['time']),warnings='One inherited log1p RuntimeWarning; no new test warning',
        inherited_bounded_checks=44,derivation_freeze_verified=True,executed_final_source_hashes_verified=True,
        source_files=len(source),evidence_files=len(evidence),source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json'),
        evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json'),
        same_x_NOT_RUN=True,full_scale_optimization_calls=0,B0_B1_executed=False,
        fixture_exactness='1536/1536',Q_and_A_count=60,final_verdict='INCONCLUSIVE'))
    print('BASE 1615 BYTES / 789 TESTS / DERIVATIONS / SOURCES / EVIDENCE PASS',flush=True)

if __name__=='__main__':run()
