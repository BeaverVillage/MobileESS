"""Read-only isolated timing of the official independent Forecast probes."""
from pathlib import Path
import sys,time,json,cProfile,pstats,io
import numpy as np
from exact_fastpath import forecast_setter_schedule,apply_schedule,terminal_layout,terminal_values
SOURCE=Path(r'D:\v42_svr11_epoch12_20261011')
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,atomic,record
from v42_svr11.authority import scope
from v42_svr11.model import _forecast_native_totals,_apply_forecast_native
from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes
from v42_svr11.resources import snapshot
ROOT=Path(r'D:\v42_svr11_may_20261011_12')
OUT=Path(__file__).resolve().parent
def run():
    assert snapshot()['RAM_available']>3*1024**3
    with scope(ROOT/'CAMPAIGN_MANIFEST.json') as m:
        from v42_voltage_control.bindings import original_bindings
        from v42_voltage_control.svr import install
        from v42_voltage_control.timecontrol import CommonClock
        from v42_regcontrol.runner import background
        authority,*_=original_bindings()
        from dayahead import run_v16_3_voltage_candidate as original
        from dayahead.v28r2.opendss_backend import _voltage_vector
        day='2025-05-01';scenario=read(m['scenario']['path'])
        folder=ROOT/'inputs/B2'/day
        forecast=read(read(folder/'SOURCE_PROVENANCE.json')['daily_sources']['aemo_forecast.json']['path'])
        bg=background(forecast['timestamps_96'],forecast['demand_mw_96'],forecast['pv_mw_96'])
        with np.load(ROOT/'models'/day/'FORECAST_ANCHOR/PLANNING_PHYSICAL.npz') as z:p=z['PCC_P_kw'].copy()
        e,ad,_=authority.compile_verified()
        try:
            install(e,scenario['svr']);branches,_=authority.source()['oriented_branches'](e)
            nodes=tuple(sorted(n.lower() for n in e.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')))
            native=authority.source()['NativeAllocation'].from_adapter(ad)
            load_names=tuple(e.Loads.AllNames());generator_names=tuple(e.Generators.AllNames());layout=terminal_layout(e,branches)
        finally:retire_completed_probe(e)
        del e;flush_completed_probes();totals=_forecast_native_totals(native,bg)
        rows=[]
        class Unprofiled:
            def enable(self):pass
            def disable(self):pass
        prof=Unprofiled()
        schedules=forecast_setter_schedule(native,totals,bg,p,ad,load_names,generator_names,original.PF_TAN)
        for target,fast in [(95,flag) for r in range(16) for flag in ((False,True) if r%2==0 else (True,False))]:
            elapsed={};began=time.perf_counter();cpu_started=time.process_time();tick=time.perf_counter();prof.enable()
            e,ad,_=authority.compile_verified();elapsed['compile_inventory']=time.perf_counter()-tick
            try:
                tick=time.perf_counter();clock=CommonClock('DAYAHEAD',day);clock.bind(e);install(e,scenario['svr']);elapsed['bind_install']=time.perf_counter()-tick
                elapsed['apply']=elapsed['settle']=0
                for t in range(target+1):
                    tick=time.perf_counter()
                    if fast:apply_schedule(e,schedules[t])
                    else:_apply_forecast_native(e,native,totals,t);original._set_slot(e,{**ad,'loads':[]},bg,p,t)
                    elapsed['apply']+=time.perf_counter()-tick
                    tick=time.perf_counter();clock.settle_slot(e,t,capture_events=False);elapsed['settle']+=time.perf_counter()-tick
                tick=time.perf_counter();v=_voltage_vector(e,nodes)**2;pq=terminal_values(e,layout,len(branches)) if fast else np.asarray([original._terminal_phase(e,b.branch_id,b.parent_bus,b.phase) for b in branches]);elapsed['measurement']=time.perf_counter()-tick
                elapsed['wall_total']=time.perf_counter()-began;elapsed['CPU_total']=time.process_time()-cpu_started
                rows.append(dict(target=target,fast=fast,seconds=elapsed,physical_solves=clock.total_physical_solve_count))
            finally:retire_completed_probe(e);prof.disable()
            del e;flush_completed_probes()
            print(json.dumps(rows[-1]),flush=True)
        import statistics
        summary={str(fast):{k:statistics.median(r['seconds'][k] for r in rows if r['fast']==fast) for k in rows[0]['seconds']} for fast in (False,True)}
        atomic(OUT/'INTERLEAVED_BENCHMARK.json',dict(rows=rows,medians=summary,source_SHA=m['execution_SHA'],candidate=record(OUT/'exact_fastpath.py'),Note='Alternating paired native prefixes under concurrently running official Workers; no whole-month speed claim'))
        print(json.dumps(summary),flush=True)
if __name__=='__main__':run()
