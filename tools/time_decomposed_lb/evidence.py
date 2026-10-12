"""Verify new-study frozen execution bytes against staged or committed Git blobs."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_time_decomposed_global_lb'
INDEX=DOCS/'EVIDENCE_INDEX.json'
BASES=(DOCS,ROOT/'tools/time_decomposed_lb')

def digest(data):return hashlib.sha256(data).hexdigest()

def index():
    files={}
    for base in BASES:
        for p in sorted(base.rglob('*')):
            if not p.is_file() or p==INDEX or '__pycache__' in p.parts:continue
            b=p.read_bytes();files[p.relative_to(ROOT).as_posix()]={'bytes':len(b),'sha256':digest(b)}
    INDEX.write_text(json.dumps(dict(PASS=True,schema='V42_TIME_DECOMPOSED_EVIDENCE_V1',self_excluded=True,files=files),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(PASS=True,indexed_files=len(files))))

def verify(ref):
    expected=json.loads(INDEX.read_text(encoding='utf-8'));failures=[]
    for n,s in expected['files'].items():
        current=(ROOT/n).read_bytes();blob=subprocess.check_output(['git','show',ref+':'+n],cwd=ROOT)
        if current!=blob or len(blob)!=s['bytes'] or digest(blob)!=s['sha256']:failures.append(n)
    print(json.dumps(dict(PASS=not failures,indexed_files=len(expected['files']),ref=ref,failures=failures)))
    if failures:raise ValueError('Git blob differs from indexed execution evidence')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['index','verify'],required=True);p.add_argument('--ref',default='HEAD');a=p.parse_args()
    index() if a.mode=='index' else verify(a.ref)
