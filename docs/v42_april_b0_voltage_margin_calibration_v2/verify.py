"""Verify unchanged PR118 bytes, test results and this task's evidence hashes."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE='86d77673a5f1cc04729cc742090bba1fb72a09fa'


def sha(data):return hashlib.sha256(data).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')


def main(record=False):
    tree=subprocess.check_output(['git','ls-tree','-rz','--full-tree',BASE],cwd=ROOT)
    blobs=[]
    for item in tree.split(b'\0'):
        if not item:continue
        metadata,name=item.split(b'\t',1)
        mode,kind,oid=metadata.split()
        if kind==b'blob':blobs.append((oid.decode(),name.decode()))
    p=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    baseline=[]
    for oid,name in blobs:
        p.stdin.write((oid+'\n').encode());p.stdin.flush()
        size=int(p.stdout.readline().split()[2]);data=p.stdout.read(size);p.stdout.read(1)
        current=(ROOT/name).read_bytes()
        if name=='.gitignore' and current!=data:
            receipt=json.loads((OUT/'CHECKOUT_EOL_RECEIPT.json').read_text(encoding='utf8'))
            assert sha(data)==receipt['Git_blob_SHA256']
            assert sha(current)==receipt['checkout_SHA256']=='606c741cb4bea8b7d58535d30053f3310d1d009e769d8995692053bfd39536a8'
            assert current==data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
        else:
            assert current==data,'PR118_BYTE_DRIFT:'+name
        baseline.append(dict(path=name,sha256=sha(data)))
    p.stdin.close();p.wait()
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
    suites=ET.parse(OUT/'TEST_RESULTS.xml').getroot().findall('testsuite')
    totals={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert totals['tests']>=983 and not any(totals[k] for k in ('failures','errors','skipped'))
    files=[]
    for folder in (OUT,ROOT/'v42_april_b0_v2',ROOT/'tests/v42_april_b0_v2'):
        for f in sorted(folder.rglob('*')):
            if not f.is_file() or '__pycache__' in f.parts or f.name in ('VERIFICATION.json','EVIDENCE_SHA256.json'):continue
            files.append(dict(path=f.relative_to(ROOT).as_posix(),sha256=sha(f.read_bytes())))
    if record:
        write('EVIDENCE_SHA256.json',dict(algorithm='SHA256_RAW_BYTES',files=files,PR118_files=baseline))
        write('VERIFICATION.json',dict(PASS=True,base=BASE,PR118_files_preserved=len(baseline),
              tests=totals,command='python -m pytest tests contract_tests -q --junitxml=docs/v42_april_b0_voltage_margin_calibration_v2/TEST_RESULTS.xml',
              git_diff_check='PASS',evidence_files_verified=len(files),production_changes=0,
              checkout_EOL_exception='Tests temporarily used inherited .gitignore CRLF receipt; final file restored to exact BASE Git blob',
              physical_execution_verified=False,scientific_calibration_complete=False))
    else:
        expected=json.loads((OUT/'EVIDENCE_SHA256.json').read_text(encoding='utf8'))
        assert expected['files']==files and expected['PR118_files']==baseline,'EVIDENCE_SHA_DRIFT'
    print(json.dumps(dict(PASS=True,PR118_files_preserved=len(baseline),tests=totals,evidence_files=len(files))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true')
    main(parser.parse_args().record)
