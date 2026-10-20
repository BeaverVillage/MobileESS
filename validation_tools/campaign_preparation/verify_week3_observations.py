"""Read-only causal source lookup checks; never build or step a controller."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_week3 import preparation as op
from v44.common import atomic,record,now


def main():
    from v44.config import axis
    from v44.inputs import BUNDLE_ROOT
    from v44_recovery_r029.weather import loader
    rows=[]
    with op.bindings(),op.no_execution():
        for day in op.DAYS:
            print('CAUSAL_SOURCE_LOOKUPS '+day,flush=True)
            a=axis(day);bundle=BUNDLE_ROOT/('DAY_'+day.replace('-',''))
            weather_receipt=op.DOC/'observation_preflight'/day/'WEATHER_ADMISSION.json'
            weather_receipt.parent.mkdir(parents=True,exist_ok=True)
            observations=loader(weather_receipt)(begin=a['issue_seconds'],end=a['end_seconds'],bundle=bundle)
            ages={k:0. for k in ('demand','pv','weather')}
            for t in range(121):
                stamp=a['issue_seconds']+t*900
                current=observations.at(stamp,observed_now=stamp)
                for k in ages:ages[k]=max(ages[k],current[k]['observation_age_seconds'])
            rows.append(dict(day=day,lookup_boundaries=121,issue_seconds=a['issue_seconds'],end_seconds=a['end_seconds'],
                max_observation_age_seconds=ages,observation_bundle_sha=observations.sha,
                sources=observations.sources,weather_admission=record(weather_receipt),controller_created=False,control_ticks=0,Native_calls=0))
        atomic(op.OPS/'OBSERVATION_INPUT_PREFLIGHT.json',dict(PASS=True,UTC=now(),days=rows,
            script=record(__file__),Native_calls=0,control_ticks=0,weather_values_imputed=False,
            policy='Unchanged r029 finite weather admission plus original 7200-second as-of lookup; 121 read-only boundary queries per day',
            forecast_causal_availability='NOT_CERTIFIED',historical_ingestion_times_certified=False))
    print(dict(PASS=True,days=len(rows),read_only_lookups=121*len(rows),Native_calls=0,control_ticks=0),flush=True)

if __name__=='__main__':main()
