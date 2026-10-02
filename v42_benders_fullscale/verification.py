"""Validate candidate lineage, immutable sources, tests, and evidence hashes."""
import gzip,hashlib,json,subprocess,xml.etree.ElementTree as ET
import numpy as np
from v42_benders.canonical import digest_arrays
from .common import *

def run():
    verify_inherited();require_scope();base=read('PR116_BASE_RECEIPT.json')
    base_paths={r['path'] for r in base['files']}
    assert not (set(git('diff',BASE,'--name-only').splitlines()) & base_paths)
    for r in read('EXECUTION_FREEZE.json')['sources']:assert sha(ROOT/r['path'])==r['sha256']
    suite=ET.parse(OUT/'FINAL_TEST_RESULTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])==825 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    candidate_rows=[]
    for p in sorted(OUT.rglob('MASTER_X_*_RECEIPT.json')):
        r=json.loads(p.read_text());prefix=p.name.replace('_RECEIPT.json','');directory=p.parent
        assert sha(directory/(prefix+'.npz'))==r['npz_sha256'] and sha(directory/(prefix+'_AXIS.json'))==r['axis_json_sha256']
        with np.load(directory/(prefix+'.npz')) as z:
            values=z['values'];names=z['names'];indices=z['original_column_indices'];bits=z['bits']
        assert digest_arrays(values)==r['vector_sha256'] and digest_arrays(names,indices)==r['axis_hash'] and digest_arrays(bits)==r['bits_sha256']
        assert np.isin(values,[0,1]).all() and np.array_equal(values,bits)
        assert r['vector_length']==(85744 if r['stage'] in ['PILOT','FULL_B3'] else 208312)
        assert r['persisted_before_recourse'] and not r['historical_PR115_x'] and r['master_settings']['Threads']==1
        candidate_rows.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),vector_sha256=r['vector_sha256'],axis_hash=r['axis_hash']))
    raw=[]
    for p in sorted(OUT.rglob('RECOURSE_*_RAW_RECEIPT.json')):
        r=json.loads(p.read_text());receipt=r['persistence'];journal=Path(receipt['journal'])
        with gzip.open(journal,'rb') as f:
            lines=[l.rstrip(b'\n') for l in f]
        payload=lines[receipt['record']-1];assert hashlib.sha256(payload).hexdigest()==receipt['payload_sha256']
        source=json.loads(payload);index=int(p.name.split('_')[1]);candidate=read(f'MASTER_X_{index:03d}_RECEIPT.json',p.parent)
        assert digest_arrays(np.array(source['source_x'],dtype=float))==candidate['vector_sha256']
        assert sha(source['axis_npz'])==source['axis_npz_sha256']
        assert source['Method']==1 and source['Seed']==20260929 and source['InfUnbdInfo']==1
        raw.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),raw_payload_sha256=receipt['payload_sha256']))
    assert read('REPORT_RECEIPT.json')['questions']==60
    flags=read('FINAL_FLAGS.json');assert flags['uncertified_cuts_inserted']==0
    assert all(flags[k] is False for k in ['P2_RUN','A2_RUN','M2_RUN','M1_ACCEPTED','PROBLEM13_FINAL_VALIDATED'])
    source_rows=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for folder in ['v42_benders_fullscale','tests/v42_benders_fullscale'] for p in sorted((ROOT/folder).glob('*.py'))]
    dump('SOURCE_MANIFEST.json',source_rows)
    evidence=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*'))
        if p.is_file() and p.name not in ['SOURCE_MANIFEST.json','EVIDENCE_MANIFEST.json','VERIFICATION.json']]
    dump('EVIDENCE_MANIFEST.json',evidence)
    dump('VERIFICATION.json',dict(PASS=True,base=BASE,preserved_tracked_files=2054,changed_inherited_files=0,
        inherited_tests=789,added_tests=36,total_tests=825,tests_seconds=float(suite.attrib['time']),inherited_bounded_checks=44,
        scope_committed_before_optimization=True,source_freeze_PASS=True,candidates=candidate_rows,raw_receipts=raw,
        raw_persisted_before_validation=True,source_x_persisted_before_recourse=True,historical_PR115_x='NOT_AVAILABLE',
        causal_speedup_claim=False,uncertified_cuts_inserted=0,questions=60,
        source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json'),evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json'),
        final_verdict=read('FINAL_VERDICT.json')['verdict']))
    print('2054 inherited bytes / 825 tests / source freeze / candidate lineage / raw journals / hashes PASS',flush=True)

if __name__=='__main__':run()
