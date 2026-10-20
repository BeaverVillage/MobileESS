"""Isolated differential test of native TIME prefix checkpoint round trips.

This never patches or imports a campaign worker. A genuine RegControl event
is carried across a 15-minute boundary after a 47-slot prefix. The reference
replays that prefix independently for every candidate. Export/import branches
also restore the visible clock, so the test does not fail on clock alone.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
import opendssdirect as odd
from dss.enums import DSSJSONFlags, DSSSaveFlags


COMMANDS = (
    'new circuit.snapshot_test basekv=12.47 pu=1 phases=3 bus1=src',
    'new transformer.reg phases=3 windings=2 buses=[src reg] conns=[wye wye] '
    'kvs=[12.47 12.47] kvas=[10000 10000] xhl=1 %loadloss=0.2',
    'new line.feed phases=3 bus1=reg bus2=load r1=0.4 x1=0.2 length=1 units=km normamps=2000',
    'new load.ld bus1=load phases=3 conn=wye kv=12.47 kw=100 kvar=20 model=1',
    'new regcontrol.ctl transformer=reg winding=2 bus=load.1 vreg=120 band=2 '
    'ptratio=60 delay=1000 tapdelay=1000 maxtapchange=1',
    'set voltagebases=[12.47]',
    'calcvoltagebases',
    'set mode=snapshot controlmode=time maxcontroliter=100 maxiterations=15',
)


def new_engine():
    engine = odd.NewContext()
    engine.Text.Commands(list(COMMANDS))
    return engine


def clock(engine, value):
    engine.Solution.Hour(int(value // 3600))
    engine.Solution.Seconds(value % 3600)


def queue(engine):
    if engine.CtrlQueue.QueueSize() == 0:
        return []
    return [dict(handle=int(r[0]), seconds=int(r[1])*3600+float(r[2]),
                 code=int(r[3]), proxy=int(r[4]), device=r[5].strip())
            for r in list(csv.reader(engine.CtrlQueue.Queue(), skipinitialspace=True))[1:]]


def settle(engine, slot, kw):
    engine.Loads.Name('ld')
    engine.Loads.kW(kw)
    engine.Loads.kvar(0.3*kw if kw > 100 else 20)
    start, end = slot*900, (slot+1)*900
    clock(engine, start)
    trace = []
    for _ in range(101):
        engine.Solution.SolveSnap()
        if not engine.Solution.Converged():
            raise RuntimeError('ISOLATED_TEST_NATIVE_NONCONVERGENCE')
        pending = queue(engine)
        engine.Transformers.Name('reg')
        engine.Transformers.Wdg(2)
        trace.append(dict(time=engine.Solution.DblHour()*3600,
                          tap=engine.Transformers.Tap(), queue=pending))
        due = min((r['seconds'] for r in pending), default=end)
        if due >= end:
            break
        if due < engine.Solution.DblHour()*3600-1e-7:
            raise RuntimeError('ISOLATED_TEST_OVERDUE_NATIVE_EVENT')
        clock(engine, due)
    else:
        raise RuntimeError('ISOLATED_TEST_EVENT_LOOP_LIMIT')
    clock(engine, end)
    return trace


def prefix():
    engine = new_engine()
    for slot in range(47):
        settle(engine, slot, 5000 if slot == 46 else 100)
    assert queue(engine), 'The adversarial fixture must contain a real pending RegControl event'
    assert queue(engine)[0]['device'].lower() == 'ctl'
    return engine


def state(engine):
    engine.Transformers.Name('reg')
    engine.Transformers.Wdg(2)
    currents = {}
    for name in engine.Circuit.AllElementNames():
        engine.Circuit.SetActiveElement(name)
        currents[name] = list(engine.CktElement.Currents())
    volts = list(engine.Circuit.AllBusMagPu())
    return dict(clock_seconds=engine.Solution.DblHour()*3600, queue=queue(engine),
                tap=engine.Transformers.Tap(), node_names=engine.Circuit.AllNodeNames(),
                complex_volts=list(engine.Circuit.AllBusVolts()), voltage_pu=volts,
                currents=currents, converged=bool(engine.Solution.Converged()),
                voltage_only_PASS=bool(volts) and all(0.95 <= v <= 1.05 for v in volts))


def exports(engine):
    # Full emits the write-only Line.Like default, which this pinned backend
    # cannot import. Use its normal public round-trip format for the trial.
    json_flags = DSSJSONFlags.SkipRedundant | DSSJSONFlags.SkipTimestamp
    save_flags = (DSSSaveFlags.IncludeOptions | DSSSaveFlags.IncludeDisabled |
                  DSSSaveFlags.SetVoltageBases | DSSSaveFlags.SingleFile |
                  DSSSaveFlags.KeepOrder | DSSSaveFlags.ToString)
    return dict(json=engine.to_dss_python().ActiveCircuit.ToJSON(json_flags),
                dss=engine.Circuit.Save('', save_flags))


def restore(kind, payload):
    engine = odd.NewContext()
    if kind == 'json':
        engine.to_dss_python().ActiveCircuit.FromJSON(payload)
    else:
        engine.Text.Commands(payload)
    clock(engine, 47*900)
    assert engine.Solution.ControlMode() == 2
    return engine


def compare(reference, candidate):
    aligned = reference['node_names'] == candidate['node_names']
    error = float(np.max(np.abs(np.asarray(reference['voltage_pu'])-
                               np.asarray(candidate['voltage_pu'])))) if aligned else None
    current_error = max(float(np.max(np.abs(np.asarray(value)-
                         np.asarray(candidate['currents'][name]))))
                        for name, value in reference['currents'].items())
    return dict(node_axis_equal=aligned, max_voltage_error_pu=error,
                max_current_component_error_amp=current_error,
                tap_equal=reference['tap'] == candidate['tap'],
                queue_equal=reference['queue'] == candidate['queue'],
                voltage_PASS_equal=reference['voltage_only_PASS'] == candidate['voltage_only_PASS'],
                physical_match=aligned and error <= 1e-6 and current_error <= 1e-6 and
                               reference['tap'] == candidate['tap'] and
                               reference['queue'] == candidate['queue'])


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # Keep this short experiment away from the live worker's reserved CPU 0.
    import psutil
    process = psutil.Process()
    allowed = [i for i in process.cpu_affinity() if i not in (0, 1)]
    if allowed:
        process.cpu_affinity([allowed[0]])
    source = prefix()
    original = state(source)
    saved = exports(source)
    unchanged = state(source) == original
    branches = {}
    for kind, payload in saved.items():
        branch = restore(kind, payload)
        branches[kind] = dict(clock_seconds=branch.Solution.DblHour()*3600,
                              queue=queue(branch), source_queue=original['queue'])
        branch.Basic.ClearAll()
    rows = []
    timings = dict(full_replay=[], json=[], dss=[])
    for kw in (1000, 5000, 8000, 10000, 11000, 12000, 12500, 13000, 14000):
        began = perf_counter()
        reference = prefix()
        reference_trace = settle(reference, 47, kw)
        timings['full_replay'].append(perf_counter()-began)
        reference_state = state(reference)
        row = dict(candidate_kw=kw, reference=reference_state, reference_trace=reference_trace)
        for kind, payload in saved.items():
            began = perf_counter()
            branch = restore(kind, payload)
            trace = settle(branch, 47, kw)
            timings[kind].append(perf_counter()-began)
            measured = state(branch)
            row[kind] = dict(comparison=compare(reference_state, measured), result=measured, trace=trace)
            branch.Basic.ClearAll()
        reference.Basic.ClearAll()
        rows.append(row)
    source_unchanged_after_candidates = state(source) == original
    source.Basic.ClearAll()
    result = dict(schema='V44_PREFIX_CHECKPOINT_DIFFERENTIAL_V1',
        UTC=datetime.now(timezone.utc).isoformat(), backend=odd.Basic.Version(),
        scope='ISOLATED_SMALL_CIRCUIT_REAL_NATIVE_REGCONTROL_NOT_PRODUCTION_GRID',
        prefix_slots=47, candidate_count=len(rows), snapshot_restores_visible_clock=True,
        snapshot_boundaries=branches, prefix_source_unchanged=unchanged and source_unchanged_after_candidates,
        all_candidates_equal={kind: all(r[kind]['comparison']['physical_match'] for r in rows) for kind in saved},
        voltage_verdict_mismatches={kind: sum(not r[kind]['comparison']['voltage_PASS_equal'] for r in rows) for kind in saved},
        median_candidate_seconds={k: median(v) for k, v in timings.items()},
        apparent_speedup={kind: median(timings['full_replay'])/median(timings[kind]) for kind in saved},
        production_fast_path_authorized=False, production_worker_or_sources_modified=False,
        Native_optimizer_calls=0, decision='REJECT_EXPORT_IMPORT_CHECKPOINT_FAST_PATH', cases=rows)
    (output/'RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases', 'backend')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    run(parser.parse_args().output)
