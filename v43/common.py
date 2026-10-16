"""Small, independent V43 provenance helpers."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/v43'
BASE = '625bbcb8b9a54a00c1660c26d96f7737c2f75457'
HIST = Path('D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01/dates/B1/2025-05-01')
PR231 = Path('D:/v42_trajectory_tracking_may01_20261014')
RUNS = Path('D:/MobileESS_V43/runtime')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def record(path):
    path = Path(path).resolve()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))

def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    os.replace(tmp, path)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def now():
    return datetime.now(timezone.utc).isoformat()

def export_support(rel):
    """Export one original input/policy blob, never a result tree."""
    if not rel.startswith('docs/') or Path(rel).suffix not in ('.json', '.csv', '.py'):
        raise ValueError('ONLY_EXPLICIT_SMALL_SUPPORT_BLOBS')
    raw = git('show', BASE + ':' + rel)
    if len(raw) > 10_000_000:
        raise ValueError('SUPPORT_EXPORT_TOO_LARGE')
    path = ROOT / rel
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('EXISTING_SUPPORT_DRIFT:' + rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return record(path)

def source_records():
    paths = [ROOT / p.decode('utf8') for p in git('ls-tree', '-r', '--name-only', '-z', BASE).split(b'\0') if p]
    paths = [p for p in paths if p.suffix in ('.py', '.json', '.csv', '.html') and not p.relative_to(ROOT).as_posix().startswith('docs/')]
    paths += sorted((ROOT / 'v43').glob('*.py'))
    return [record(p) for p in paths if p.is_file()]

def verify_records(rows):
    for row in rows:
        actual = record(row['path'])
        if any(actual[k] != row[k] for k in ('bytes','sha256')):
            raise ValueError('FROZEN_BYTES_DRIFT:' + row['path'])
