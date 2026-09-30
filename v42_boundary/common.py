from v42_temporal.common import ROOT, OLD, read, sha, rec, clean, require, MODEL
from pathlib import Path
import json
import pandas as pd

OUT=ROOT/'docs/v42_ts_boundary_a1_acceleration'
PR97=ROOT/'docs/v42_ts_cc4_temporal_refinement'
LOCAL=ROOT.parent/'V42_TS_BOUNDARY_A1_LOCAL'
GEN=LOCAL/'generation_zero_rate_repair'
BASE='cde230b1be83cfe8fa4114a372b92ed564c98574'

def dump(name,value):
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/name).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def csv(name,rows,columns=None):
    pd.DataFrame(rows,columns=columns).to_csv(OUT/name,index=False,lineterminator='\n')
