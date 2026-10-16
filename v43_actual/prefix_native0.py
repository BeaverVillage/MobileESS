"""Observed 18:00 prefix canary; explicitly not a grid/Actual96 certificate."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import os
import sys
import threading
import time
import traceback

import numpy as np
import psutil

from v43.common import ROOT, DOC, RUNS, atomic, now, record, read, verify_records, git
from .case import prepare, BUNDLE
from .io import write


def run(output):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    from v43.golden import no_heavy_peer
    from .vendor.actual import run_actual
    from .vendor.current_ac_admission import CausalObservations
    output=Path(output)
    if output.exists():
        raise FileExistsError('NEW_INDEPENDENT_PREFIX_ATTEMPT_REQUIRED')
    no_heavy_peer()
    for peer in psutil.process_iter(['pid','name','cmdline']):
        if peer.pid != os.getpid() and (peer.info['name'] or '').lower() in ('python.exe','pythonw.exe','python'):
            if 'v43_actual' in ' '.join(peer.info['cmdline'] or []):
                raise RuntimeError('V43_ACTUAL_DUPLICATE_WORKER')
    output.mkdir(parents=True)
    sources=[record(p) for p in sorted((ROOT/'v43_actual').rglob('*.py'))]
    sources += [record(ROOT/'v43/common.py'),record(DOC/'GATE_B_SELECTIVE_PORT_MANIFEST.json')]
    start=dict(schema='V43_NATIVE0_PREFIX_CANARY_V1',UTC=now(),pid=os.getpid(),
        process_created=psutil.Process().create_time(),source_commit=git('rev-parse','HEAD').decode().strip(),
        sources=sources,Worker=1,Threads=1,Native_calls=0,Actual96_PASS=False,Fresh96_PASS=False,
        scope='EVENT_BOUNDARY_ONLY_ELECTRICAL_GUARD_NOT_YET_CONNECTED')
    atomic(output/'START.json',start)
    stopped=threading.Event()
    began=time.perf_counter()
    def heartbeat():
        while not stopped.wait(10):
            p=psutil.Process()
            atomic(output/'HEARTBEAT.json',dict(UTC=now(),pid=os.getpid(),
                CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=p.memory_info().rss,
                wall_seconds=time.perf_counter()-began))
    thread=threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    result=dict(PASS=False,Actual96_PASS=False,Fresh96_PASS=False,Gate_B_PASS=False)
    attempts=[]
    try:
        with ExitStack() as stack:
            locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
            locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
            locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
            for path in locks:
                stack.enter_context(exclusive_lock(path))
            attempts=stack.enter_context(native_zero())
            verify_records(sources)
            args,identity=prepare(output/'CASE',private_service=True)
            midnight=args['begin']+21600
            observations=CausalObservations.load(BUNDLE,begin=args['begin'],end=midnight)
            # Every physical interval uses a causal as-of observation. No
            # interpolated future observation is exposed to a controller.
            weather=[observations.at(t,observed_now=t)['weather']['values']
                for t in np.arange(args['begin'],midnight,900.)]
            future_requests=[r for r in args['requests'] if r.submit >= midnight]
            args['requests']=[r for r in args['requests'] if r.submit < midnight]
            args.update(end=midnight,weather=weather)
            before=deepcopy(args['known_schedule'])
            actual=run_actual(**args)
            if args['known_schedule'] != before:
                raise ValueError('GOLDEN003_KNOWN_COMMAND_MUTATION')
            carry=actual.pop('carryout')
            write(output/'SIMULATOR_PRIVATE_CARRYOUT.json',carry)
            arrays={k:actual.pop(k) for k in ('occupancy_GPU','compute_occupancy_GPU')}
            physical=actual.pop('physical')
            np.savez_compressed(output/'PREFIX_PHYSICAL.npz',**arrays,**physical,sites=np.array(actual['sites']))
            write(output/'PREFIX_EVENT_LEDGERS.json',actual)
            write(output/'OBSERVATION_AUTHORITY.json',dict(sha=observations.sha,sources=observations.sources,
                NOAA_availability='OBSERVATION_TIME_MODEL_NOT_HISTORICAL_INGESTION_CERTIFICATE'))
            verify_records(sources)
            result=dict(PASS=not attempts,scope=start['scope'],
                event_engine_native0_PASS=not attempts,Gate_B_PASS=False,Actual96_PASS=False,Fresh96_PASS=False,
                slots=24,initial_Running=identity['initial_Running'],Known=identity['Known'],
                Unknown_total=identity['Unknown'],prefix_observed_unknown=sum(r['origin_unknown'] for r in actual['queue_ledger']),
                future_unsubmitted_requests_retained=len(future_requests),
                prefix_receipt=actual['receipt'],Known_commands_unchanged=True,
                midnight_Unknown_reclassification=0,initialization='44_MODEL_ASSUMED_FIXED210_UNCHANGED',
                physical_electrical_admission='NOT_CONNECTED_NOT_CERTIFIED',
                Original_Golden_case_unchanged=True,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        stopped.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),Native_calls=0,Native_seconds=0.,
            wall_seconds=time.perf_counter()-began,denied_Native_attempts=attempts,raw_preserved=True)
        write(output/'RESULT.json',result)
        write(output/'RECONCILIATION.json',dict(UTC=now(),Native_calls=0,Native_seconds=0.,inflight=None))
    print(result)
    return result


if __name__=='__main__':
    run(sys.argv[1])
