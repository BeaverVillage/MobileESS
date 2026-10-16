"""One frozen new Actual case, independent C0/Strict C1, original-grid Fresh."""
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

from v43.common import ROOT,DOC,RUNS,atomic,read,record,verify_records,git,now
from .case import prepare
from .current_ac import OriginalCurrentAC
from .controller import IssueContinuityPolicy,V43EventController
from .observations import load_observations
from .planning_reference import build
from .vendor.actual import run_actual
from .io import write


def physical_rows(actual,args,observations):
    physical=actual['physical']
    return [dict(slot=t,start_seconds=args['begin']+t*900,end_seconds=args['begin']+(t+1)*900,
        GPU=actual['occupancy_GPU'][t].tolist(),P=physical['PCC_P_kw'][t].tolist(),
        Q=physical['PCC_Q_kvar'][t].tolist(),
        observations=observations.at(args['begin']+t*900,observed_now=args['begin']+t*900))
        for t in range(len(actual['occupancy_GPU']))]


def run(output, *, control_slots=120):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    from v43.golden import no_heavy_peer
    output=Path(output)
    if output.exists() or control_slots not in (1,25,120):
        raise ValueError('FRESH_V43_COMPARE_ATTEMPT_AND_SUPPORTED_HORIZON_REQUIRED')
    no_heavy_peer()
    for peer in psutil.process_iter(['pid','name','cmdline']):
        if peer.pid != os.getpid() and (peer.info['name'] or '').lower() in ('python.exe','pythonw.exe','python'):
            if 'v43_actual' in ' '.join(peer.info['cmdline'] or []):raise RuntimeError('DUPLICATE_V43_ACTUAL')
    output.mkdir(parents=True)
    sources=[record(p) for p in sorted((ROOT/'v43_actual').rglob('*.py'))]
    sources += [record(ROOT/'v43/common.py'),record(DOC/'GATE_B_SELECTIVE_PORT_MANIFEST.json')]
    start=dict(UTC=now(),pid=os.getpid(),process_created=psutil.Process().create_time(),
        source_commit=git('rev-parse','HEAD').decode().strip(),sources=sources,
        Worker=1,Threads=1,Native_calls=0,control_slots=control_slots)
    atomic(output/'START.json',start)
    latest=dict(phase='PREPARE_SAME_GOLDEN003_CASE_NATIVE0')
    began=time.perf_counter();done=threading.Event()
    def progress(value):
        latest.update(value)
        atomic(output/'progress.json',dict(latest,UTC=now()))
        if (output/'STOP_REQUESTED.json').exists():
            raise RuntimeError('V43_ACTUAL_OFFICIAL_STOP_REQUESTED')
    def heartbeat():
        while not done.wait(10):
            p=psutil.Process()
            atomic(output/'HEARTBEAT.json',dict(UTC=now(),pid=os.getpid(),latest=dict(latest),
                CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=p.memory_info().rss,wall_seconds=time.perf_counter()-began))
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    result=dict(PASS=False,Gate_B_PASS=False,Actual96_PASS=False,Fresh96_PASS=False)
    attempts=[]
    try:
        with ExitStack() as stack:
            locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
            locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
            locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
            for path in locks:stack.enter_context(exclusive_lock(path))
            attempts=stack.enter_context(native_zero())
            verify_records(sources)
            args,identity=prepare(output/'CASE',private_service=True)
            reference,packet,bindings,proof=build(args,identity,output/'GOLDEN_REFERENCE')
            observations=load_observations(begin=args['begin'],end=args['end'])
            shared_commands=deepcopy(args['known_schedule'])
            variants={}
            for variant in ('C0','C1'):
                progress(dict(phase='EVENT_ACTUAL_CURRENT_AC',variant=variant,completed_control_ticks=0))
                current=deepcopy(args)
                current['end']=current['begin']+control_slots*900
                current['requests']=[r for r in current['requests'] if r.submit < current['end']]
                current['weather']=[observations.at(t,observed_now=t)['weather']['values']
                    for t in np.arange(current['begin'],current['end'],900.)]
                oracle=OriginalCurrentAC(issue_seconds=current['begin'],sites=reference.sites,
                    power_model=current['power_model'],observations=observations)
                policy=IssueContinuityPolicy(reference,packet,variant=variant,oracle=oracle,
                    bindings=bindings,expected_bindings=bindings,evidence_scope='REAL_V43_STRICT_SOURCE')
                policy.bind_observed_c1(current['power_model'],current_weather_provider=
                    lambda when:observations.at(when,observed_now=oracle.now)['weather']['values'])
                ticks=[]
                def on_tick(when,wall,starts):
                    ticks.append(dict(time_seconds=when,wall_seconds=wall,starts=starts))
                    progress(dict(completed_control_ticks=len(ticks),control_time_seconds=when,
                        last_tick_wall_seconds=wall,current_AC_calls=oracle.calls))
                policy.on_tick=on_tick
                started=time.perf_counter()
                actual=run_actual(**current,frozen_policy=policy,controller_class=V43EventController,expected_bindings=bindings)
                if current['known_schedule'] != shared_commands or reference.commands != shared_commands:
                    raise ValueError('GOLDEN_KNOWN_COMMANDS_MODIFIED')
                target=output/variant;target.mkdir()
                rows=physical_rows(actual,current,observations)
                carry=actual.pop('carryout')
                write(target/'SIMULATOR_PRIVATE_CARRYOUT.json',carry)
                np.savez_compressed(target/'ACTUAL_PHYSICAL.npz',GPU=actual['occupancy_GPU'],
                    compute_GPU=actual['compute_occupancy_GPU'],**actual['physical'],sites=np.array(actual['sites']))
                for key in ('occupancy_GPU','compute_occupancy_GPU','physical'):actual.pop(key)
                write(target/'ACTUAL_EVENT_LEDGERS.json',actual)
                write(target/'CURRENT_AC_RECEIPTS.json',oracle.audit)
                write(target/'SIGNED_PENDING_POLICY_AUDIT.json',dict(audit=policy.audit,diagnostics=policy.diagnostics))
                progress(dict(phase='INDEPENDENT_FRESH_ORIGINAL7_REPLAY',variant=variant))
                fresh=oracle._probe(rows)
                write(target/'FRESH_ORIGINAL7_AC.json',fresh)
                evaluated=fresh['physical_steps'][24:]
                fresh96=(control_slots==120 and len(evaluated)==96 and all(r['PASS'] for r in evaluated))
                actual96=(control_slots==120 and actual['receipt']['capacity_violations']==0
                    and actual['receipt']['dropped_jobs']==0 and actual['receipt']['optimizer_calls']==0)
                elapsed=[r['wall_seconds'] for r in ticks]
                variants[variant]=dict(Actual96_execution_PASS=actual96,Fresh96_physical_PASS=fresh96,
                    elapsed_wall_seconds=time.perf_counter()-started,Native_calls=0,Native_seconds=0.,
                    Current_AC_calls=oracle.calls,Known_commands_unchanged=True,
                    Source_presite_executed=sum(r['decision'].get('action')=='PREPLACE' for r in policy.audit),
                    tick_P50_seconds=float(np.percentile(elapsed,50)),tick_P95_seconds=float(np.percentile(elapsed,95)),
                    tick_Max_seconds=max(elapsed),latency_within_900_seconds=max(elapsed)<900,
                    observed_Unknown=sum(r['origin_unknown'] for r in actual['queue_ledger']),
                    receipt=actual['receipt'],current_AC=record(target/'CURRENT_AC_RECEIPTS.json'),
                    Fresh=record(target/'FRESH_ORIGINAL7_AC.json'))
                write(target/'RESULT.json',variants[variant])
            verify_records(sources)
            gate=control_slots==120 and all(v['Actual96_execution_PASS'] and v['Fresh96_physical_PASS']
                and v['latency_within_900_seconds'] for v in variants.values())
            result=dict(PASS=gate if control_slots==120 else not attempts,Gate_B_PASS=gate,
                Actual96_PASS=all(v['Actual96_execution_PASS'] for v in variants.values()),
                Fresh96_PASS=all(v['Fresh96_physical_PASS'] for v in variants.values()),variants=variants,
                case=record(output/'CASE/CASE_BINDINGS.json'),planning_reference=record(output/'GOLDEN_REFERENCE/REFERENCE_PROOF.json'),
                Source_initial_sites_certified=False,initial_sites_assumption='44_MODEL_ASSUMED',
                Strict_Source_scope='UNKNOWN_PRE_SITE_PERMISSION_ONLY',R1='NOT_EXECUTED_ASSUMED_SEPARATE',R2='HOLD',
                original_control_contract='PR189_SNAPSHOT_STATIC_7REG_NO_ADDED_SVR',
                delayed_TIME_actuation_certificate='NOT_CERTIFIED',Golden_reexecution=False,
                FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        done.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),Native_calls=0,Native_seconds=0.,inflight=None,
            wall_seconds=time.perf_counter()-began,denied_Native_attempts=attempts,raw_preserved=True)
        write(output/'RESULT.json',result)
        write(output/'RECONCILIATION.json',dict(UTC=now(),Native_calls=0,Native_seconds=0.,inflight=None))
    print(result)
    return result


if __name__=='__main__':
    run(sys.argv[1],control_slots=int(sys.argv[2]) if len(sys.argv)>2 else 120)
