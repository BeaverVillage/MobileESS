from __future__ import annotations
from pathlib import Path
from typing import Any
from datetime import date, datetime
import hashlib, json, logging, math, shutil, zipfile
import numpy as np
import pandas as pd

class JsonEncoder(json.JSONEncoder):
    def default(self, obj: Any):
        if isinstance(obj, Path): return str(obj)
        if isinstance(obj, (pd.Timestamp, datetime, date)): return obj.isoformat()
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating):
            v=float(obj); return v if math.isfinite(v) else None
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, cls=JsonEncoder), encoding='utf-8')

def sha256_file(path: Path, chunk_size: int=1024*1024) -> str:
    d=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b=f.read(chunk_size)
            if not b: break
            d.update(b)
    return d.hexdigest()

def setup_logger(path: Path) -> logging.Logger:
    logger=logging.getLogger(f'k5b2_{path.parent.parent.name}')
    logger.setLevel(logging.INFO); logger.handlers.clear()
    fmt=logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    fh=logging.FileHandler(path, encoding='utf-8'); fh.setFormatter(fmt)
    sh=logging.StreamHandler(); sh.setFormatter(fmt)
    logger.addHandler(fh); logger.addHandler(sh); return logger

def copy_file(source: Path, target_dir: Path) -> Path:
    target=target_dir/source.name
    if source.resolve()!=target.resolve(): shutil.copy2(source,target)
    return target

def dataframe_to_markdown(frame: pd.DataFrame, max_rows: int=30) -> str:
    if frame.empty: return '(empty)'
    f=frame.head(max_rows); cols=[str(c) for c in f.columns]
    lines=['| '+' | '.join(cols)+' |','|'+'|'.join(['---']*len(cols))+'|']
    for _,r in f.iterrows():
        vals=[]
        for v in r.tolist():
            if pd.isna(v): vals.append('')
            elif isinstance(v,float): vals.append(f'{v:.6g}')
            else: vals.append(str(v).replace('|','\\|'))
        lines.append('| '+' | '.join(vals)+' |')
    if len(frame)>max_rows: lines.append(f'\n_First {max_rows} of {len(frame)} rows._')
    return '\n'.join(lines)

def zip_review(publish_dir: Path, review_zip: Path) -> None:
    roots={'metrics','reports','logs'}; tops={'manifest.json','pipeline_used.yaml'}
    with zipfile.ZipFile(review_zip,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(publish_dir.rglob('*')):
            if not p.is_file(): continue
            rel=p.relative_to(publish_dir)
            if len(rel.parts)==1 and rel.name in tops: z.write(p,rel)
            elif rel.parts[0] in roots: z.write(p,rel)
            elif rel.parts[0]=='outputs' and p.suffix.lower() in {'.csv','.json','.yaml','.md'}: z.write(p,rel)
