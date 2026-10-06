from pathlib import Path
import json,hashlib,csv
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_one_tree_bc_20261006'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,v):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/n
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def table(n,rows,fields=None):
    with (OUT/n).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),extrasaction='ignore')
        w.writeheader();w.writerows(rows)
