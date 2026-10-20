"""Read-only observation joins for all ten May22-31 dates."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_week4 import preparation as op
from v44.common import atomic,record,now

def main():
    from v44.config import axis
    from v44.inputs import BUNDLE_ROOT
    from v44_recovery_r029.weather import loader
    rows=[]
    with op.bindings(),op.no_execution():
        for day in op.DAYS:
            a=axis(day);receipt=op.DOC/'observation_preflight'/day/'WEATHER_ADMISSION.json'
            receipt.parent.mkdir(parents=True,exist_ok=True);failures=[]
            obs=loader(receipt)(begin=a['issue_seconds'],end=a['end_seconds'],bundle=BUNDLE_ROOT/('DAY_'+day.replace('-','')))
            for t in range(121):
                stamp=a['issue_seconds']+900*t
                try:obs.at(stamp,observed_now=stamp)
                except ValueError as e:failures.append(dict(slot=t,seconds=stamp,error=str(e)))
            rows.append(dict(day=day,PASS=not failures,lookup_boundaries=121,failures=failures,sources=obs.sources,
                weather_admission=record(receipt),Native_calls=0,control_ticks=0))
            print(dict(day=day,PASS=not failures,failed_lookups=len(failures)),flush=True)
        atomic(op.OPS/'OBSERVATION_INPUT_PREFLIGHT.json',dict(PASS=all(r['PASS'] for r in rows),UTC=now(),days=rows,
            script=record(__file__),Native_calls=0,control_ticks=0,weather_values_imputed=False,
            max_staleness_seconds=7200,invalid_dates_excluded_from_B0_admission=True))

if __name__=='__main__':
    main()
