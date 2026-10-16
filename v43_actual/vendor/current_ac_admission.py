from copy import deepcopy
from datetime import datetime,timezone,timedelta
import csv
import io
import math
from pathlib import Path
import zipfile
import pandas as pd
from .policy import digest
from v43_actual.io import read,record,checked


AEST=timezone(timedelta(hours=10))


def epoch(value):
    if isinstance(value,(int,float)):return float(value)
    t=datetime.fromisoformat(str(value).replace('/','-').replace('Z','+00:00'))
    return t.replace(tzinfo=AEST).timestamp() if t.tzinfo is None else t.timestamp()


class CausalSeries:
    """Observation and source-update times both bind a read-only as-of view."""
    def __init__(self,rows,*,name,max_staleness_seconds=7200):
        self.name=name;self.max_staleness_seconds=max_staleness_seconds
        clean=[];seen={}
        for raw in rows:
            row=deepcopy(raw)
            if not all(math.isfinite(float(row[k])) for k in ('observed_seconds','available_seconds')):
                raise ValueError('CAUSAL_NONFINITE_OBSERVATION_CLOCK')
            if row['available_seconds']<row['observed_seconds']:raise ValueError('CAUSAL_AVAILABLE_BEFORE_OBSERVATION')
            if not all(math.isfinite(float(v)) for v in row['values'].values()):raise ValueError('CAUSAL_NONFINITE_VALUE')
            key=(row['observed_seconds'],row['available_seconds'])
            if key in seen and seen[key]!=row['values']:raise ValueError('CAUSAL_CONFLICTING_SOURCE_DUPLICATE')
            seen[key]=row['values'];row['row_sha']=digest(row);clean.append(row)
        self.__rows=tuple(sorted(clean,key=lambda r:(r['observed_seconds'],r['available_seconds'],r['row_sha'])))
        self.receipt_sha=digest(list(self.__rows))

    def at(self,when,*,observed_now):
        if not math.isfinite(when) or not math.isfinite(observed_now) or when>observed_now:raise ValueError('FUTURE_OBSERVATION_QUERY_FORBIDDEN')
        row=next((r for r in reversed(self.__rows) if r['observed_seconds']<=when and r['available_seconds']<=when),None)
        if row is None:raise ValueError('CAUSAL_OBSERVATION_NOT_AVAILABLE:'+self.name)
        if when-row['observed_seconds']>self.max_staleness_seconds:raise ValueError('CAUSAL_OBSERVATION_TOO_STALE:'+self.name)
        return dict(deepcopy(row),decision_seconds=when,observation_age_seconds=when-row['observed_seconds'],
            source_availability_checked=True,interpolation='NONE_ASOF_FORWARD_HOLD')


def _archive_series(paths,kind,begin,end):
    time_key,column=('SETTLEMENTDATE','TOTALDEMAND') if kind=='demand' else ('INTERVAL_DATETIME','POWER')
    rows=[];sources=[]
    lower=datetime.fromtimestamp(begin-7200,AEST).strftime('%Y/%m/%d %H:%M:%S')
    upper=datetime.fromtimestamp(end,AEST).strftime('%Y/%m/%d %H:%M:%S')
    for path in paths:
        source=record(path);sources.append(source)
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith('.csv'):continue
                with archive.open(member) as stream:
                    headers={}
                    for ordinal,line in enumerate(csv.reader(io.TextIOWrapper(stream,encoding='utf-8-sig'))):
                        key=tuple(line[1:4])
                        if line and line[0]=='I':headers[key]=line[4:]
                        elif line and line[0]=='D' and key in headers:
                            item=dict(zip(headers[key],line[4:]));stamp=item.get(time_key,'')
                            if (item.get('REGIONID')!='VIC1' or not lower<=stamp<=upper
                                    or kind=='pv' and item.get('TYPE')!='MEASUREMENT'
                                    or kind=='demand' and item.get('INTERVENTION','0')!='0'):continue
                            observed=epoch(stamp)
                            if not item.get('LASTCHANGED'):raise ValueError('AEMO_SOURCE_UPDATE_TIME_MISSING')
                            available=max(observed,epoch(item['LASTCHANGED']))
                            rows.append(dict(observed_seconds=observed,available_seconds=available,
                                values={kind+'_mw':float(item[column])},source=source,member=member,
                                source_row=ordinal,record_type=key,source_fields=item))
    return CausalSeries(rows,name=kind),sources


class CausalObservations:
    def __init__(self,demand,pv,weather,*,sources=()):
        self.demand,self.pv,self.weather=demand,pv,weather;self.sources=list(sources)
        self.sha=digest(dict(demand=demand.receipt_sha,pv=pv.receipt_sha,weather=weather.receipt_sha,sources=self.sources))

    def at(self,when,*,observed_now):
        return dict(demand=self.demand.at(when,observed_now=observed_now),
            pv=self.pv.at(when,observed_now=observed_now),weather=self.weather.at(when,observed_now=observed_now),
            observation_bundle_sha=self.sha)

    @classmethod
    def load(cls,raw,*,begin,end):
        raw=Path(raw);actual=read(raw/'ACTUAL_INPUT_BUNDLE.json');provenance=read(raw/'SOURCE_PROVENANCE.json')
        series={};sources=[]
        for kind in ('demand','pv'):
            current=checked(actual['realized_inputs']['authority'][kind])
            prior=current.with_name(current.name.replace('202505010000','202504010000'))
            if prior==current or not prior.is_file():raise ValueError('PREVIOUS_MONTH_CAUSAL_ARCHIVE_MISSING:'+kind)
            series[kind],receipts=_archive_series((prior,current),kind,begin,end);sources.extend(receipts)
        weather_path=checked(provenance['daily_sources']['noaa_actual_weather.parquet']);receipt=record(weather_path)
        frame=pd.read_parquet(weather_path);rows=[]
        for ordinal,row in enumerate(frame.to_dict('records')):
            stamp=pd.Timestamp(row['ts']).timestamp()
            if begin-7200<=stamp<=end:
                rows.append(dict(observed_seconds=stamp,available_seconds=stamp,
                    values={key:float(row[key]) for key in ('t_wb_c','rh_pct')},source=receipt,source_row=ordinal,
                    availability_scope='OBSERVATION_TIME_MODEL_NOT_HISTORICAL_INGESTION_CERTIFICATE'))
        sources.append(receipt)
        return cls(series['demand'],series['pv'],CausalSeries(rows,name='weather'),sources=sources)
