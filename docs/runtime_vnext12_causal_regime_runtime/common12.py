"""V12 research namespace; older scientific artifacts are read-only inputs."""
from pathlib import Path
import datetime, hashlib, json, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
LOCAL = ROOT / '.local'
BASE = 'dcc15226263998a90c5aa3fdc5ec53b4cd2afd17'
V9 = REPO / 'docs/runtime_vnext9_distributional_runtime'
V10 = REPO / 'docs/runtime_vnext10_tail_calibrated_hazard'
V11 = REPO / 'docs/runtime_vnext11_total_remaining'
V8 = REPO / 'docs/runtime_vnext8_trace_feature_total'
for p in [V8, V9, V10]:
    sys.path.append(str(p))

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def record(p): return dict(path=str(p), bytes=Path(p).stat().st_size, sha256=sha(p))
def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, np.ndarray): return clean(x.tolist())
    if hasattr(x, 'item'): return clean(x.item())
    if isinstance(x, float) and not np.isfinite(x): return None
    return x
def write(name, x):
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean(x), indent=2, ensure_ascii=False, allow_nan=False, default=str)+'\n', encoding='utf-8')
def data(i, role): return pd.read_parquet(V9 / '.local' / f'fold{i}' / (role+'.parquet'))
def prep(i): return read(V9 / f'FOLD_{i}_PREPROCESSING.json')
def ids(f): return hashlib.sha256(('\n'.join(sorted(f.job_id.astype(str)))+'\n').encode()).hexdigest()
