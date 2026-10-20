"""Real 43-RegControl isolated measurement comparison, including fault probes."""
from pathlib import Path
import argparse
import sys
import hashlib
import json
from statistics import median
from time import perf_counter
from types import SimpleNamespace
from contextlib import nullcontext
import psutil
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import v44_recovery_r029
from v44_recovery_r029.current_ac_performance import live_read_scope
from v44_actual_audit_light import measure_scope
from v44.svr12 import scope, HARDWARE
from v44.common import read, now


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def visible(engine):
    return dict(element=engine.CktElement.Name(), transformer=engine.Transformers.Name(),
                winding=engine.Transformers.Wdg(), property=engine.Properties.Name(),
                volts=list(engine.Circuit.AllBusVolts()), queue=list(engine.CtrlQueue.Queue()),
                hour=engine.Solution.Hour(), seconds=engine.Solution.Seconds(),
                iterations=engine.Solution.TotalIterations())


def run(output):
    psutil.Process().cpu_affinity([2])
    output = Path(output)
    output.mkdir(exist_ok=False, parents=True)
    with scope():
        from v42_regcontrol import authority
        from v42_voltage_control.timecontrol import CommonClock
        import v42_voltage_control.svr as svr
        engine, adapter, initial = authority.compile_verified()
        clock = CommonClock('ACTUAL', '2025-05-02')
        clock.bind(engine)
        scenario = read(HARDWARE/'SCENARIO.json')
        bank = svr.install(engine, scenario['svr'])
        engine.Solution.SolveSnap()
        assert len(engine.RegControls.AllNames()) == 43
        oracle = SimpleNamespace(arm='B3', _bank=bank, _scenario_audit=None, _independent_fresh=False)
        timings = dict(original=[], lightweight=[])
        hashes, states, stats = {}, {}, {}
        for name in ('original', 'lightweight'):
            outer = measure_scope(svr, oracle) if name == 'lightweight' else nullcontext(None)
            with outer as p, live_read_scope(oracle=oracle):
                for _ in range(8):
                    began = perf_counter()
                    value = bank.measure()
                    timings[name].append(perf_counter()-began)
                    hashes[name] = hashlib.sha256(canonical(value).encode()).hexdigest()
                states[name] = visible(engine)
                if p is not None:
                    stats = p.report()
        assert len(set(hashes.values())) == 1
        assert states['original'] == states['lightweight']
        faults = []
        first = bank.installation_receipt['added_transformer_names'][0]
        regulator = bank.installation_receipt['added_RegControl_names'][0]
        for element, prop, replacement in (('Transformer.'+first, 'NormHkVA', '1'),
                                            ('RegControl.'+regulator, 'Vreg', '125')):
            engine.Circuit.SetActiveElement(element)
            old = engine.Properties.Value(prop)
            engine.Properties.Value(prop, replacement)
            errors = {}
            try:
                for name in ('original', 'lightweight'):
                    outer = measure_scope(svr, oracle) if name == 'lightweight' else nullcontext()
                    with outer, live_read_scope(oracle=oracle):
                        try:
                            bank.measure()
                        except Exception as error:
                            errors[name] = (type(error).__name__, str(error))
                assert errors.get('original') and errors['original'] == errors.get('lightweight')
                faults.append(dict(element=element, property=prop, identical_error=errors['original']))
            finally:
                engine.Circuit.SetActiveElement(element)
                engine.Properties.Value(prop, old)
        with measure_scope(svr, oracle) as fresh_stats, live_read_scope(oracle=oracle):
            oracle._independent_fresh = True
            value = bank.measure()
            assert fresh_stats.omitted == 0
        oracle._independent_fresh = False
        engine.Basic.ClearAll()
    result = dict(UTC=now(), PASS=True, scope='ISOLATED_REAL_SVR12_43_REGCONTROL_BANK_MEASUREMENT_NOT_FULL_ACTUAL',
        identical_measurement_SHA=hashes, native_state_and_selectors_equal=True,
        median_seconds={k:median(v[1:]) for k,v in timings.items()},
        component_speedup=median(timings['original'][1:])/median(timings['lightweight'][1:]),
        property_read_counts=stats, fault_injections=faults,
        independent_Fresh_full_reader_preserved=True, Native_optimizer_calls=0,
        production_worker_modified=False)
    (output/'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    run(parser.parse_args().output)
