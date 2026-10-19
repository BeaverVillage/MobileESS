"""Isolated real-hardware replay comparing exact bank cache predicates."""
from pathlib import Path
import argparse
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from statistics import median
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch
import psutil

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r029
from v44_recovery_r029 import current_ac_performance as performance
from v44_actual_bank_gate import build
from v44.svr12 import scope,HARDWARE
from v44.common import read,now


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def one(factory,slots):
    with scope():
        from v42_regcontrol import authority
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        import v42_voltage_control.svr as svr
        engine,adapter,initial=authority.compile_verified()
        clock=CommonClock('ACTUAL','2025-05-02');clock.bind(engine)
        bank=svr.install(engine,read(HARDWARE/'SCENARIO.json')['svr'])
        counts=dict(state_reads=0)
        def state(e):
            counts['state_reads']+=1
            inv=performance.state_inventory(e)
            return dict(taps=[r['initial_tap'] for r in inv['regulators']],
                caps=[r['states'] for r in inv['capacitors']],queue=queue(e),physical_seconds=seconds(e))
        oracle=SimpleNamespace(arm='B3',_bank=bank,_scenario_audit=SimpleNamespace(rows=[]),
            _independent_fresh=False,_state=state)
        measurements=[];timings=[];traces=[]
        with patch.object(performance,'bank_reader',factory),performance.live_read_scope(oracle=oracle):
            for slot in range(slots):
                traces.append(clock.settle_slot(engine,slot))
                began=perf_counter();first=bank.measure();oracle._scenario_audit.rows.append({})
                second=bank.measure();timings.append(perf_counter()-began)
                assert first==second
                measurements.append(first)
        result=dict(measurement_SHA=hashlib.sha256(encoded(measurements)).hexdigest(),
            native_trace_SHA=hashlib.sha256(encoded(traces)).hexdigest(),
            final_voltages=engine.Circuit.AllBusVolts(),final_queue=queue(engine),
            median_bank_pair_seconds=median(timings[1:]),timings=timings,
            counters=counts,duplicate_reuses=oracle._r029_duplicate_bank_reuses,
            gate_counts=getattr(oracle,'_r034_bank_gate_counts',{}))
        engine.Basic.ClearAll()
        return result


def run(output):
    psutil.Process().cpu_affinity([2])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    factory=build();old=one(performance.bank_reader,12);new=one(factory,12)
    for field in ('measurement_SHA','native_trace_SHA','final_voltages','final_queue','duplicate_reuses'):
        assert old[field]==new[field],field
    result=dict(UTC=now(),PASS=True,scope='ISOLATED_REAL_SVR12_43_REGCONTROL_12_SLOT_REPLAY_BANK_COMPONENT',
        all_measurements_and_native_events_byte_identical=True,original=old,optimized=new,
        component_speedup=old['median_bank_pair_seconds']/new['median_bank_pair_seconds'],
        native_solves_removed=0,physical_checks_removed=0,production_worker_modified=False)
    (output/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('original','optimized')},ensure_ascii=False))
    print(json.dumps({'original':{k:v for k,v in old.items() if k not in ('timings','final_voltages','final_queue')},
                     'optimized':{k:v for k,v in new.items() if k not in ('timings','final_voltages','final_queue')}},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);run(p.parse_args().output)
