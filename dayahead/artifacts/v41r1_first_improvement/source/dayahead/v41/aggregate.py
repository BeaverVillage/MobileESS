"""Rebuild campaign tables from sealed unit data, without loading a solver."""
import argparse
from pathlib import Path
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, atomic
from .data import RUNTIME
from .preflight import record
from .scientific_archive import verify_manifest
from .persistence import table


def aggregate(root=RUNTIME):
    rows=[]; sources=[]
    for manifest in sorted(Path(root).glob('2025-05-*/B*/UNIT_SCIENTIFIC_MANIFEST.json')):
        verify_manifest(manifest); unit=manifest.parent
        frame=pd.read_parquet(unit/'actual/comparison/DAYAHEAD_VS_ACTUAL.parquet')
        frame.insert(0,'policy',unit.name); frame.insert(0,'target_day',unit.parent.name)
        rows.append(frame); sources.append(record(manifest))
    output=Path(root)/'aggregation'
    if not rows:
        write_json(output/'AGGREGATION_STATUS.json',dict(status='NO_COMPLETED_UNITS',optimizer_calls=0)); return
    daily=pd.concat(rows,ignore_index=True)
    # Output replacement is deliberate: every completed unit remains immutable;
    # the summary is regenerated from its current complete input manifest set.
    from dayahead.paper_analysis.storage import write_parquet
    write_parquet(output/'DAILY_POLICY_COMPARISON.parquet',daily)
    monthly=daily.groupby(['policy','metric','unit'],dropna=False)[['dayahead','actual','delta']].agg(['count','mean','min','max'])
    monthly.columns=['_'.join(c) for c in monthly.columns]; monthly=monthly.reset_index()
    write_parquet(output/'MONTHLY_POLICY_STATISTICS.parquet',monthly)
    with atomic(output/'DAILY_POLICY_COMPARISON.csv') as f: f.write(daily.to_csv(index=False).encode('utf-8'))
    write_json(output/'AGGREGATION_STATUS.json',dict(status='PASS',completed_policy_days=len(sources),sources=sources,
        optimizer_calls=0,partial_month=len(sources)<124,aggregation='count/mean/min/max across completed days; no artificial sum of maxima',
        daily=record(output/'DAILY_POLICY_COMPARISON.parquet'),monthly=record(output/'MONTHLY_POLICY_STATISTICS.parquet')))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=RUNTIME); args=p.parse_args(); aggregate(args.root)
