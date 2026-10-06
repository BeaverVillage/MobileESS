from pathlib import Path
import csv,json,hashlib,os
os.environ.update(dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1'))
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_exact_redundancy_audit_20261006'
LOCAL=ROOT/'REDUNDANCY_LOCAL'
BASE='07c9ae892335b34a32faf82cff6266ab5cf80aac'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,data):
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def table(name,rows,fields):
 OUT.mkdir(parents=True,exist_ok=True)
 with (OUT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
