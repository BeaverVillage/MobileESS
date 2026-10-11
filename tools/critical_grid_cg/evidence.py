"""Index only the new study tree; verify exact execution bytes in Git blobs."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/v42_critical_grid_cg'
INDEX = DOCS/'EVIDENCE_INDEX.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def index():
    files = {}
    for base in (DOCS, ROOT/'tools/critical_grid_cg'):
        for path in sorted(base.rglob('*')):
            if not path.is_file() or path == INDEX or '__pycache__' in path.parts:
                continue
            data = path.read_bytes()
            files[path.relative_to(ROOT).as_posix()] = dict(bytes=len(data), sha256=digest(data))
    value = dict(PASS=True, schema='V42_CRITICAL_GRID_CG_EVIDENCE_V1', self_excluded=True, files=files)
    INDEX.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(PASS=True, indexed_files=len(files))))


def verify(ref):
    value = json.loads(INDEX.read_text(encoding='utf-8'))
    failures = []
    for name, expected in value['files'].items():
        work = (ROOT/name).read_bytes()
        blob = subprocess.check_output(['git','show',ref+':'+name], cwd=ROOT)
        if work != blob or len(blob) != expected['bytes'] or digest(blob) != expected['sha256']:
            failures.append(name)
    print(json.dumps(dict(PASS=not failures, indexed_files=len(value['files']), ref=ref, failures=failures)))
    if failures:
        raise ValueError('Git artifact differs from frozen execution evidence')


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['index','verify'], required=True)
    ap.add_argument('--ref', default='HEAD')
    args=ap.parse_args()
    index() if args.mode == 'index' else verify(args.ref)
