"""Read-only reuse of completed CC4-v2.7; new evidence writes only here."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parent
PREV=ROOT.parent/'cc4_v27_target_feature_sharpness'
sys.path.insert(0,str(PREV))
import core as c
import experiment as old
import report as previous_report
import numpy as np,pandas as pd
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(name,data):
    with (ROOT/name).open('x',encoding='utf-8',newline='\n') as f:json.dump(c.clean(data),f,indent=2,ensure_ascii=False,allow_nan=False)
def csv(name,rows):
    p=ROOT/name;assert not p.exists();pd.DataFrame(rows).to_csv(p,index=False,lineterminator='\n')
def verify_previous():
    assert read(PREV/'CURRENT_RUN_COMPLETION.json')['CURRENT_V27_RUN_COMPLETED_UNCHANGED']
    for r in read(PREV/'DELIVERY_MANIFEST.json')['files']:assert sha(PREV/r['path'])==r['sha256'],r['path']
    old.guard()

