import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.update(dict.fromkeys(('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'), '1'))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_accel_vnext'
OLD = ROOT / 'docs/v42_m1_dw_root_continuation_v2'
BASE = '63e81dc3b6d236549f566e65e07dcd05ac0a160c'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    tmp.replace(path)

def table(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf8', newline='') as f:
        fields = list(dict.fromkeys(k for r in rows for k in r)) or ['event']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
