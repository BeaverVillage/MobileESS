from pathlib import Path
import csv, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_mess_benders_v2_native_recourse'
BASE = '089518b08d477777b154d9c75dc6ea72c14f254e'
PRIOR = Path('C:/Users/kjw39/Documents/Codex/2026-10-02/m1-exact-benders/worktree')

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

def read(name): return json.loads((OUT/name).read_text(encoding='utf8'))

def table(name, rows, fields):
    with (OUT/name).open('w', encoding='utf8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
