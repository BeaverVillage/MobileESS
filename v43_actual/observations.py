"""Bind the existing as-of observer to PR189's raw exogenous receipts."""
import pandas as pd

from .case import BUNDLE
from .io import read, record, checked
from .vendor.current_ac_admission import CausalObservations, CausalSeries, _archive_series


def load_observations(*, begin, end, bundle=BUNDLE):
    provenance=read(bundle/'SOURCE_PROVENANCE.json')
    # PR189 daily weather is a retrospective interpolated 96-row derivative.
    # An online as-of observer must read the original hourly observations,
    # including the six-hour issue prefix, from the preserved raw receipt.
    raw=provenance['raw_realized_sources']
    series={};sources=[]
    for kind in ('demand','pv'):
        current=checked(raw[kind])
        prior=current.with_name(current.name.replace('202505010000','202504010000'))
        if prior==current or not prior.is_file():
            raise ValueError('ORIGINAL_PREVIOUS_MONTH_OBSERVATION_ARCHIVE_MISSING:'+kind)
        series[kind],receipts=_archive_series((prior,current),kind,begin,end)
        sources.extend(receipts)
    path=checked(raw['weather']);receipt=record(path)
    frame=pd.read_parquet(path,columns=['ts','t_wb_c','rh_pct'])
    if 'ts' not in frame:
        raise ValueError('RAW_HOURLY_OBSERVATION_CLOCK_REQUIRED')
    rows=[]
    for ordinal,row in enumerate(frame.to_dict('records')):
        stamp=pd.Timestamp(row['ts']).timestamp()
        if begin-7200 <= stamp <= end:
            rows.append(dict(observed_seconds=stamp,available_seconds=stamp,
                values={key:float(row[key]) for key in ('t_wb_c','rh_pct')},
                source=receipt,source_row=ordinal,
                availability_scope='OBSERVATION_TIME_MODEL_NOT_HISTORICAL_INGESTION_CERTIFICATE'))
    sources.append(receipt)
    return CausalObservations(series['demand'],series['pv'],CausalSeries(rows,name='weather'),sources=sources)
