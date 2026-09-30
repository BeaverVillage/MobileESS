from v42_boundary.common import ROOT,OLD,PR97,read,sha,rec,clean,require,MODEL
from pathlib import Path
import json
import pandas as pd
OUT=ROOT/'docs/v42_compact_aidc_state_flow'
PR98=ROOT/'docs/v42_ts_boundary_a1_acceleration'
LOCAL=ROOT.parent/'V42_COMPACT_STATE_LOCAL'
BASE='e9f9387769bd2500e48654d0aa1752ad7f7d6aa4'
def dump(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def csv(name,rows):pd.DataFrame(rows).to_csv(OUT/name,index=False,lineterminator='\n')
