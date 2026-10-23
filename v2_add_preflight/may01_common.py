"""May01-only preparation on PR236; immutable prior evidence is an authority."""
from pathlib import Path
import csv, hashlib, json, time
from .audit import ROOT, DOC, read, sha
from .prestart import SOURCE, INITIAL, resources
from .physical import RUNTIME

BASE = '759dd5f87edd7340c703507e42dc36ccd32afcdc'
OLD = DOC / 'integration'
PRIOR = RUNTIME / 'integration'
OUT = DOC / 'may01'
RUN = RUNTIME / 'may01'
PACK = PRIOR / 'FULL96_MATRIX_PORT_PACK'

def relocated(p):
    """Resolve the workspace move, without modifying any sealed receipt."""
    p = Path(p)
    prefix = 'C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/'
    s = p.as_posix()
    if s.lower().startswith(prefix.lower()):
        candidate = ROOT.parent / s[len(prefix):]
        if candidate.exists():
            return candidate
    return p

def record(p):
    p = Path(p)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return dict(path=str(p.resolve()), sha256=h.hexdigest(), bytes=p.stat().st_size)

def put(name, x):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(x, ensure_ascii=False, indent=2,
        allow_nan=False) + '\n', encoding='utf-8')
    return x

def table(name, rows):
    rows = list(rows)
    assert rows
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader(); w.writerows(rows)

def guard(start, wall=3600):
    import psutil
    if psutil.Process().memory_info().rss > 4 * 1024**3 or psutil.virtual_memory().available < 5 * 1024**3:
        raise MemoryError('PROTECTED_WORKER_RESOURCE_RESERVE')
    if time.perf_counter() - start > wall:
        raise TimeoutError('MAY01_PREPARATION_WALL_GUARD')

def init():
    OUT.mkdir(exist_ok=True); RUN.mkdir(exist_ok=True)
    p = OUT / 'TASK_DIRECTIVE_KO.md'
    if not p.exists():
        p.write_bytes(Path('C:/Users/kjw39/.codex/attachments/d823ad55-7254-49c9-be43-dfa2ccc53df0/붙여넣은 텍스트.txt').read_bytes())
    return resources()
