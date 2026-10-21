"""Valid-observation ingestion for the unchanged bounded as-of observer.

A missing wet-bulb measurement is retained in source/defect evidence and is
not an observation value. The original observer holds the latest complete
published pair for at most its existing7200s limit; no interpolation/future
observation, filled source row, or weather coefficient change is introduced.
"""
import types,math
import numpy as np
from .full_common import *

def observations(day,begin,end):
    from v43_actual.observations import load_observations,CausalSeries
    rejected=[]
    def complete(rows,*,name,**kw):
        valid=[]
        for r in rows:
            if all(math.isfinite(float(v)) for v in r['values'].values()):valid.append(r)
            else:rejected.append(dict(observed_seconds=r['observed_seconds'],source_row=r['source_row'],reason='MISSING_MEASUREMENT_NOT_A_FINITE_OBSERVATION'))
        return CausalSeries(valid,name=name,**kw)
    fn=types.FunctionType(load_observations.__code__,dict(load_observations.__globals__,CausalSeries=complete),argdefs=load_observations.__defaults__)
    fn.__kwdefaults__=load_observations.__kwdefaults__
    obs=fn(begin=begin,end=end,bundle=Path(day['files']['actual_input']['path']).parent)
    trace=[]
    for t in range(120):
        now=begin+t*900;row=obs.at(now,observed_now=now)['weather']
        assert row['observed_seconds']<=now and row['available_seconds']<=now and row['observation_age_seconds']<=7200
        trace.append(dict(slot=t,decision_seconds=now,observed_seconds=row['observed_seconds'],available_seconds=row['available_seconds'],age_seconds=row['observation_age_seconds'],**row['values']))
    table('WEATHER_ASOF_'+day['day']+'.csv',trace)
    put('WEATHER_VALID_OBSERVATIONS_'+day['day']+'.json',dict(PASS=True,missing_measurements=rejected,
        source_rows_changed=0,interpolation='NONE',asof_forward_hold=True,original_max_staleness_seconds=7200,
        maximum_age_seconds=max(r['age_seconds'] for r in trace),future_reads=0,sources=obs.sources,
        source_observer=record(ROOT/'v43_actual/vendor/current_ac_admission.py')))
    return obs

def actual_power(gpu,sites,day):
    from .aidc_candidate import actual_c1
    import pandas as pd
    # Route only the read of the original hourly frame to its complete observed
    # pairs. The original pure C1 implementation and as-of search are unchanged.
    class Pandas:
        def __getattr__(self,name):return getattr(pd,name)
        def read_parquet(self,*a,**kw):return pd.read_parquet(*a,**kw).dropna(subset=['t_wb_c','rh_pct'])
    fn=types.FunctionType(actual_c1.__code__,dict(actual_c1.__globals__,pd=Pandas()),argdefs=actual_c1.__defaults__)
    return fn(gpu,sites,day)
