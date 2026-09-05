"""Solver-free check of accepted A0 materialization across all May days."""
from pathlib import Path
import sys,traceback,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from concurrent.futures import ProcessPoolExecutor,as_completed

def check(day):
    from dayahead.v40a.context import load_planning_context
    from dayahead.v40b.may_adapter import accepted_a0,admit_day,traffic_authority
    from dayahead.v40a.outcome_guard import prohibit_fresh_calls
    from dayahead.v40a import firewall
    context=None
    try:
        with prohibit_fresh_calls(),admit_day(day):
            firewall.activate(day)
            context=load_planning_context(REPO,day);a0=accepted_a0(day,context)
            traffic=traffic_authority(day)
            return {'day':day,'status':'PASS','jobs':len(a0['jobs']),'A0_SHA':a0['A0_SHA'],
                'A0_migrations':a0['RUNNING_migrations_selected_in_A0'],'terminal_audit':a0['terminal_audit'],
                'traffic_forecast_SHA':traffic['forecast_SHA'],'solver_calls':0,'Fresh_calls':0}
    except Exception as e:return {'day':day,'status':'FAIL','error':repr(e),'traceback':traceback.format_exc()}
    finally:
        firewall.deactivate()
        if context is not None:context.electrical.voltage.close();context.electrical.current.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--retry-failed',action='store_true');args=parser.parse_args()
    target=ROOT/'V40B_MAY_A0_ADMISSION_TEST.json'
    previous=read(target) if args.retry_failed else None
    rows=[r for r in previous['rows'] if r['status']=='PASS'] if previous else []
    days=[d for d in DAYS if d not in {r['day'] for r in rows}]
    if previous:write(ROOT/'V40B_MAY_A0_ADMISSION_BEFORE_TRAFFIC_COMPLETION.json',previous)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(check,d) for d in days]):
            value=future.result();rows.append(value);print(value['day'],value['status'],value.get('error',''),flush=True)
            write(ROOT/'V40B_MAY_A0_ADMISSION_TEST.json',{'status':'PASS' if len(rows)==31 and all(r['status']=='PASS' for r in rows) else 'RUNNING',
                 'rows':sorted(rows,key=lambda r:r['day']),'solver_calls':0,'May_result_tuning':0})
    write(ROOT/'V40B_MAY_A0_ADMISSION_TEST.json',{'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',
       'rows':sorted(rows,key=lambda r:r['day']),'solver_calls':0,'Fresh_calls':0,'May_result_tuning':0})

if __name__=='__main__':main()
