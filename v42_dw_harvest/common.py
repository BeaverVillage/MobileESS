import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_dw_multicolumn_microbenchmark'
if os.environ.get('V42_DW_CLEAN_REVALIDATION') == '1':
    OUT = OUT / 'clean_revalidation'
OLD = ROOT / 'docs/v42_m1_dw_root_continuation_v2'
BASE = '63e81dc3b6d236549f566e65e07dcd05ac0a160c'
ENV = dict.fromkeys(('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'), '1')
os.environ.update(ENV)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    temp.replace(path)


def table(path, rows):
    with Path(path).open('w', encoding='utf8', newline='') as f:
        fields = list(dict.fromkeys(k for r in rows for k in r)) or ['event']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
