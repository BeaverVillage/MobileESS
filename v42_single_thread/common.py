import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_single_worker_single_thread_a1_m1'
LOCAL = ROOT.parent / 'SINGLE_THREAD_LOCAL'
BASE = 'c26c656265cc90dec39eb2937b76fbea1f2ed500'
NORMALAMPS = '0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
ENV = dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'), '1')

def configure():
    os.environ.update(ENV)
    os.environ['V42_ROOT_OUTPUT'] = 'docs/v42_single_worker_single_thread_a1_m1/A1_BUILD'
    os.environ['V42_ROOT_LOCAL'] = 'SINGLE_THREAD_LOCAL'
    OUT.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
    tmp.replace(p)
