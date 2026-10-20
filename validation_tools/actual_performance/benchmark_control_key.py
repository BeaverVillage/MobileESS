"""Compare the first control-key pair against the complete native reader."""
from pathlib import Path
import json,sys
from statistics import median
from time import perf_counter
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r029
from v44_recovery_r029 import history,current_ac_performance as performance
from v44_actual_control_key import from_controls
from v44.svr12 import scope,HARDWARE
from v44.common import read,now


def run(output):
    import psutil
    psutil.Process().cpu_affinity([2])
    with scope():
        from v42_regcontrol import authority
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        import v42_voltage_control.svr as svr
        import v42_voltage_control.integration as integration
        e,_,_=authority.compile_verified()
        clock=CommonClock('ACTUAL','2025-05-02');clock.bind(e)
        scenario=read(HARDWARE/'SCENARIO.json')
        svr.install(e,scenario['svr'])
        def state(e):
            inv=performance.state_inventory(e)
            return dict(taps=[r['initial_tap'] for r in inv['regulators']],
                caps=[r['states'] for r in inv['capacitors']],queue=queue(e),physical_seconds=seconds(e))
        o=SimpleNamespace(_state=state)
        old=[];new=[]
        with performance.live_read_scope(oracle=o):
            for slot in range(12):
                clock.settle_slot(e,slot)
                for reverse in (False,True):
                    results={}
                    for kind in (('new','old') if reverse else ('old','new')):
                        began=perf_counter()
                        if kind=='old':
                            stamp=history.native_stamp(o,e)
                            controls=integration._controls(e,scenario)
                        else:
                            controls=integration._controls(e,scenario)
                            stamp=from_controls(o,e,controls)
                        (old if kind=='old' else new).append(perf_counter()-began)
                        results[kind]=(stamp,controls)
                    assert results['old']==results['new'],slot
        result=dict(UTC=now(),PASS=True,comparisons=24,exact_key_and_control_values_equal=True,
            old_seconds=median(old),new_seconds=median(new),component_speedup=median(old)/median(new),
            counts=o._r034_control_key_counts,production_worker_modified=False)
        assert result['counts']['fallbacks']==0
        Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        e.Basic.ClearAll()


if __name__=='__main__':run(sys.argv[1])
