from v42_final.common import ROOT, OUT as OLD, V9, read, sha, rec, clean, require, MODEL
from pathlib import Path
import json
import pandas as pd

OUT = ROOT / 'docs/v42_ts_cc4_temporal_refinement'
LOCAL = ROOT.parent / 'V42_TS_CC4_TEMPORAL_LOCAL'
TRAIN = V9 / '.local/fold1/TRAIN.parquet'
BASE = 'd9787338fa5995a62628b9a2958bae60e7411ded'

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

def csv(name, rows):
    pd.DataFrame(rows).to_csv(OUT/name, index=False, lineterminator='\n')

def train_frame():
    spec = read(OUT/'PREREGISTRATION.json')
    f = pd.read_parquet(TRAIN)
    cutoff = pd.Timestamp(spec['TRAIN_cutoff'])
    require((f.submit_time < cutoff).all() and (f.start_time < cutoff).all(), 'TRAIN_CHRONOLOGY')
    require((f.observation_cutoff <= cutoff).all(), 'TRAIN_OBSERVATION_CUTOFF')
    return f, cutoff
