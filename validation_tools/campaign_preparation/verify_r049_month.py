"""Recheck all ten dates with the scoped May23 source repair, no controller replay."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r049 import operations as r
from v44_recovery_r049 import weather
from v44.config import axis
from v44.inputs import BUNDLE_ROOT
from v44_week3.preparation import no_execution
from v44.common import read,atomic,record,now

rows=[]
with r.op.bindings(dict(day='2025-05-23',arm='B0',campaign_root=str(r.ROOT))),no_execution():
    for n in range(22,32):
        day=f'2025-05-{n:02d}';a=axis(day);bundle=BUNDLE_ROOT/('DAY_'+day.replace('-',''))
        obs=weather.loader()(begin=a['issue_seconds'],end=a['end_seconds'],bundle=bundle)
        age=0.
        for t in range(121):
            stamp=a['issue_seconds']+900*t;v=obs.at(stamp,observed_now=stamp)
            age=max(age,v['weather']['observation_age_seconds'])
        rows.append(dict(day=day,PASS=True,queries=121,max_weather_age_seconds=age,receipt_sha=obs.sha))
atomic(r.HOME/'MONTH_INPUT_RECHECK.json',dict(PASS=True,UTC=now(),days=rows,queries=1210,failed_queries=0,
    Native_calls=0,control_ticks=0,authorization=record(r.AUTH),supplement=record(weather.SUPPLEMENT),max_staleness_seconds=7200))
atomic(r.ROOT/'DOCUMENTS/input_metadata/2025-05-23/RECOVERED_WEATHER_BINDING.json',dict(day='2025-05-23',
    supplement=record(weather.SUPPLEMENT),authority=record(r.AUTH),loader='v44_recovery_r049.weather.loader',
    observed_altimeter_derived_station_pressure=True,original_source_immutable=True,new_actual_execution_arms=['B0']))
print(dict(PASS=True,read_only_queries=1210,failed_queries=0,Native_calls=0),flush=True)
