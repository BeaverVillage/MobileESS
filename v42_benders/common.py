from pathlib import Path
import csv, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_mess_exact_benders'
LOCAL = ROOT.parent / 'BENDERS_LOCAL'
BASE = '964b2c65964ff38089dab53c4e2fa03149d729f7'
THRESHOLD = .5732125039436496
ORIGINAL_UB = .5912812634331275
ORIGINAL_LB = .5722125039436496

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

def read(name):
    return json.loads((OUT/name).read_text(encoding='utf8'))

def table(name, rows, fields):
    with (OUT/name).open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
