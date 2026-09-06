from pathlib import Path
import hashlib, json, subprocess
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dayahead/artifacts/v40p_lightgbm_forecast_forensic'
BASE = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\processed데이터\데이터센터\NLR Kestrel Jobs Data')
TOOLS = Path(r'\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_tools')
K5A = BASE / 'stage_k5a_20260721_151429'
K5B2 = BASE / 'stage_k5b2_20260721_164621'
START = 'e24492aa2e3404548cd4efc9f23e8168c0839b3b'
LIMIT = pd.Timestamp('2025-05-01', tz='UTC')

def clean(x):
    if isinstance(x, dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [clean(v) for v in x]
    if isinstance(x,np.ndarray): return clean(x.tolist())
    if isinstance(x,(np.integer,)): return int(x)
    if isinstance(x,(np.bool_,)): return bool(x)
    if isinstance(x,(float,np.floating)): return float(x) if np.isfinite(x) else None
    if isinstance(x,(Path,pd.Timestamp)): return str(x)
    return x

def dump(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf-8').strip()

def record_access(path,kind,**extra):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'access_log.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(clean({'path':str(path),'kind':kind,**extra}),ensure_ascii=False)+'\n')

def read_pre_may(path,columns=None,end=LIMIT):
    """Read only physically segregated pre-May row groups; never scan-and-filter May."""
    path=Path(path)
    assert 'v40n' not in str(path).lower()
    pf=pq.ParquetFile(path)
    names=pf.schema_arrow.names
    ti=names.index('timestamp_utc')
    tables=[]; groups=[]; skipped=[]
    for i in range(pf.num_row_groups):
        stat=pf.metadata.row_group(i).column(ti).statistics
        if stat is None or not stat.has_min_max:
            skipped.append({'group':i,'reason':'NO_TIMESTAMP_STATS'});continue
        lo,hi=pd.Timestamp(stat.min),pd.Timestamp(stat.max)
        if lo.tzinfo is None: lo=lo.tz_localize('UTC');hi=hi.tz_localize('UTC')
        if hi+pd.Timedelta(hours=4,minutes=5)>=end:
            skipped.append({'group':i,'min':lo,'max':hi,'reason':'GROUP_NOT_PROVEN_PRE_MAY_WITH_MAX_LABEL_WINDOW'});continue
        tables.append(pf.read_row_group(i,columns=columns));groups.append(i)
    record_access(path,'PRE_MAY_PARQUET_ROW_GROUPS',read_groups=groups,skipped=skipped)
    if not tables: return pd.DataFrame(columns=columns or names)
    frame=pa.concat_tables(tables).to_pandas()
    frame['timestamp_utc']=pd.to_datetime(frame.timestamp_utc,utc=True)
    assert (frame.timestamp_utc+pd.Timedelta(hours=4,minutes=5)<end).all()
    return frame

def footer(path):
    pf=pq.ParquetFile(path);names=pf.schema_arrow.names
    ti=names.index('timestamp_utc') if 'timestamp_utc' in names else None
    rows=[]
    for i in range(pf.num_row_groups):
        rg=pf.metadata.row_group(i);st=rg.column(ti).statistics if ti is not None else None
        rows.append({'group':i,'rows':rg.num_rows,'min':str(st.min) if st and st.has_min_max else None,'max':str(st.max) if st and st.has_min_max else None})
    record_access(path,'PARQUET_FOOTER_ONLY')
    return {'path':str(path),'columns':names,'row_groups':rows}
