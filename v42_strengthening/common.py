import csv
import hashlib
import json
import os
from pathlib import Path

ENV = dict.fromkeys(('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'), '1')
os.environ.update(ENV)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_exact_formulation_strengthening'
LOCAL = ROOT.parent / 'STRENGTHENING_LOCAL'
SOURCE = Path('C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
REF = ROOT / 'docs/v42_m1_cutpass_loop_campaign'
SCIENCE = ROOT / 'docs/v42_single_worker_single_thread_a1_m1'
BASE = '37ffd404e7d0d598ddb84fec084e3ac332ed99c0'
BASE_LB = 0.5687116103498322
UB_REF = 0.6715884801665905

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf8')
    tmp.replace(p)

def table(name, rows, fields=None):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def material(lb):
    delta = lb - BASE_LB
    relative = delta / (UB_REF - BASE_LB)
    return dict(delta_LB=delta, root_gap=(UB_REF-lb)/UB_REF,
                baseline_diagnostic_root_gap=(UB_REF-BASE_LB)/UB_REF,
                root_gap_relative_reduction=relative,
                material=bool(delta >= .001 or relative >= .01),
                UB_reference_is_diagnostic_only=True, UB_certificate=None)

def once(label):
    LOCAL.mkdir(parents=True, exist_ok=True)
    with (LOCAL / (label + '_STARTED.json')).open('x', encoding='utf8') as f:
        json.dump(dict(label=label, retries_allowed=0), f)
