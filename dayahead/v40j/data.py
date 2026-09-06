"""Projected pre-May rows. April payload remains sealed until selection freeze."""
from io import BytesIO
import json
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .contracts import OUT, LEGACY_CACHE, ARCHIVE, SPLIT, FEATURES9
from .firewall import ReadFirewall, write, sha
from .timestamp_firewall import premay_mask

def utc(t): return pd.Timestamp(t,tz='UTC')

def read_frame(path):
    return pq.read_table(BytesIO(path.read_bytes())).to_pandas()

def train_mask(frame,when):
    t=utc(when)
    return premay_mask(frame)&(frame.end_time<t)&(frame.end_time>=t-pd.Timedelta(days=120))&(frame.submit_time<t)&frame.runtime_seconds.notna()&(frame.runtime_seconds>=0)

def block_mask(frame,interval,deadline):
    return premay_mask(frame)&(frame.submit_time>=utc(interval[0]))&(frame.submit_time<utc(interval[1]))&(frame.end_time<utc(deadline))&frame.runtime_seconds.notna()&(frame.runtime_seconds>=0)

def extract():
    path=LEGACY_CACHE/'kestrel_preissue_normalized.parquet'
    fw=ReadFirewall('development_extract',[path]).install()
    try:
        f=read_frame(path)
        if (f.submit_time>=utc('2025-05-01')).any() or (f.end_time>=utc('2025-04-01')).any():
            raise ValueError('NON_PREMAY_CACHE')
        census={'source_sha256':sha(path),'all_rows':len(f),'GPU_rows':int((f.num_gpus_req>0).sum()),
          'submit_range':[str(f.submit_time.min()),str(f.submit_time.max())],
          'end_range':[str(f.end_time.min()),str(f.end_time.max())],
          'all_columns':{c:str(t) for c,t in f.dtypes.items()},
          'request_missing_count':{c:int(f[c].isna().sum()) for c in FEATURES9},
          'label_status_counts':{str(k):int(v) for k,v in f.job_state.value_counts(dropna=False).items()},
          'cache_selection_bias':'Legacy normalization is end-known before March31 issue and lower-end-time bounded; census of this training input is not a full unfiltered source census.',
          'source_inventory':'V40J_PREMAY_RUNTIME_DATA_CENSUS.json',
          'raw_archive_payload_reads':0,'April_payload_reads':0}
        g=f.loc[f.num_gpus_req>0].copy()
        del f
        g=g.sort_values(['submit_time','job_id'],kind='stable').reset_index(drop=True)
        census['GPU_status_counts']={str(k):int(v) for k,v in g.job_state.value_counts(dropna=False).items()}
        census['GPU_partition_qos_counts']=g.groupby(['partition','qos'],dropna=False).size().rename('N').reset_index().to_dict('records')
        census['GPU_daily_counts']={str(k):int(v) for k,v in g.groupby(g.submit_time.dt.strftime('%Y-%m-%d')).size().items()}
        census['split_counts']={fold['id']:{'train':int(train_mask(g,fold['fit_before']).sum()),
           'calibration':int(block_mask(g,fold['calibration'],fold['validation'][0]).sum()),
           'validation':int(block_mask(g,fold['validation'],SPLIT['validation_label_deadline']).sum())} for fold in SPLIT['folds']}
        g.to_parquet(OUT/'DEVELOPMENT_GPU_ROWS.parquet',index=False)
        write('V40J_PREMAY_RUNTIME_ROW_CENSUS.json',census)
        print(json.dumps({'GPU_rows':len(g),'split_counts':census['split_counts']}),flush=True)
    finally: fw.close()

if __name__=='__main__': extract()
