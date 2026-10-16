"""Original nonflexible events and one independent sequential Fresh replay."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import os
import inspect
import math
import threading
import textwrap
import traceback

import numpy as np
import psutil

from v43.common import ROOT,DOC,RUNS,read,record,verify_records,atomic,git,now
from v43_arms.actual import ArmBinding
from v43_actual.vendor.actual import JobEventController,run_actual
from v43_actual.vendor.policy import digest
from v43_actual.observations import load_observations
from v43_actual.compare import physical_rows
from v43_corrective.reference import CorrectedReferenceScheduler
from v43_corrective.current_ac import FullPrefixReferenceAC
from v43_mess.budget import heavy_peers
from v42_capacity.actual import Controller as OriginalFCFS


def original_fcfs_core():
    body=textwrap.dedent(inspect.getsource(OriginalFCFS.admit))
    original='eligible=sorted(s for s in r.compatible if s in use and (r.source_site is None or s==r.source_site))'
    if body.count(original)!=1:raise ValueError('ORIGINAL_FCFS_SOURCE_BOUNDARY_DRIFT')
    # The existing R0 Reference fixes each basic site; this is not an
    # alternative-site selector. All heap/head-of-line/capacity/start logic
    # remains the original PR189 code-base FCFS implementation.
    body=body.replace(original,'eligible=self._baseline_sites(uid,now,use)')
    namespace=dict(OriginalFCFS.admit.__globals__)
    exec(compile(body,inspect.getfile(OriginalFCFS),'exec'),namespace)
    return namespace['admit']


class BaselineController(JobEventController):
    _fcfs_admit=original_fcfs_core()
    def __init__(self,*args,rack_limits,on_tick=None,**kwargs):
        if kwargs.get('arm') not in ('B0','B2') or kwargs.get('frozen_policy') is not None:
            raise ValueError('GRID_BLIND_BASELINE_NO_CONTROL_POLICY_REQUIRED')
        super().__init__(*args,**kwargs)
        if self.flexible:raise ValueError('BASELINE_MUST_USE_ORIGINAL_NONFLEXIBLE_FCFS')
        self.rack_limits=rack_limits;self.on_tick=on_tick

    def _baseline_sites(self,uid,when,use):
        r=self.requests[uid];m=self.metadata[uid];site=m['reference_site']
        if site not in r.compatible or site not in use or r.gpu>max(self.rack_limits[site]):return []
        if r.source_site is not None and site!=r.source_site:return []
        if when<max(r.submit,m.get('release_seconds') or -math.inf,m.get('hard_earliest_start_seconds') or -math.inf):return []
        if any(m.get(k) is not None and value>m[k] for k,value in (
                ('hard_latest_start_seconds',when),('completion_deadline_seconds',when+r.q50))):return []
        return [site]

    def admit(self,when):
        if when%900:return []
        began=perf_counter();started=self._fcfs_admit(when)
        for uid in started:
            site=self.audit[uid]['site'];reference=self.reference.assigned[uid]
            self.metadata[uid].update(state='RUNNING',current_site=site,additional_start_delay_seconds=0.)
            self.reservations.retain_running(uid,site,when,when+900,self.requests[uid].gpu)
            self.audit[uid].update(policy_action='START',plan_start_seconds=reference['reference_start_seconds'],
                plan_actual_start_deviation_seconds=when-reference['reference_start_seconds'],
                intentional_delay_seconds=0.,unavoidable_queue_seconds=when-self.requests[uid].submit)
            self._event(uid,when,'RUNNING',site=site,action='START',mode='ORIGINAL_GRID_BLIND_FCFS')
        if self.on_tick:self.on_tick(when,perf_counter()-began,len(started))
        return started


def run(arm,output,*,reference_folder=None,mess_result=None):
    if arm not in ('B0','B2'):raise ValueError('BASELINE_B0_B2_ONLY')
    if heavy_peers():raise RuntimeError('ANOTHER_HEAVY_WORKER_IS_ACTIVE')
    output=Path(output);freeze=output.with_name(output.name+'.BASELINE_SOURCE_FREEZE.json')
    if output.exists() or freeze.exists():raise ValueError('NEW_BASELINE_ATTEMPT_REQUIRED')
    mess=None
    if arm=='B2':
        if mess_result is None:raise ValueError('B2_REQUIRES_FROZEN_FULL_FEASIBLE_MESS')
        r=read(mess_result)
        if r['arm']!='B2' or r.get('FULL_feasible') is not True:raise ValueError('EXACT_B2_FULL_MESS_REQUIRED')
        mess=r['MESS_plan']
    elif mess_result is not None:raise ValueError('B0_MESS_MUST_BE_ZERO')
    binding=ArmBinding(arm,reference_folder,mess)
    sources=[record(p) for folder in ('v43_baseline','v43_actual','v43_arms') for p in sorted((ROOT/folder).rglob('*.py'))]
    sources += [record(ROOT/p) for p in ('v43/common.py','v43/may01.py','v43_corrective/reference.py',
        'v43_corrective/current_ac.py','v42_capacity/actual.py','v43_mess/budget.py')]
    if mess_result:sources.append(record(mess_result))
    start=dict(UTC=now(),pid=os.getpid(),process_created=psutil.Process().create_time(),
        source_commit=git('rev-parse','HEAD').decode().strip(),sources=sources,arm=arm,
        control_variant=None,execution_mode='GRID_BLIND_EVENT_FCFS',Worker=1,Threads=1,
        candidate_Current_AC_calls=0,C0_policy=None,C1_policy=None)
    atomic(freeze,start);output.mkdir(parents=True);atomic(output/'START.json',start)
    began=perf_counter();latest={'phase':'REUSE_EXISTING_R0_Q50_INPUT'};done=threading.Event()
    def progress(**values):
        latest.update(values);atomic(output/'progress.json',dict(latest,UTC=now()))
        if (output/'STOP_REQUESTED.json').exists():raise RuntimeError('V43_BASELINE_OFFICIAL_STOP_REQUESTED')
    def heartbeat():
        while not done.wait(10):
            p=psutil.Process();atomic(output/'HEARTBEAT.json',dict(UTC=now(),pid=os.getpid(),latest=dict(latest),
                CPU_seconds=sum(p.cpu_times()[:2]),wall_seconds=perf_counter()-began,RSS_bytes=p.memory_info().rss))
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    result=dict(PASS=False,arm=arm,control_variant=None,execution_mode='GRID_BLIND_EVENT_FCFS',
        Actual96_execution_PASS=False,Fresh96_physical_PASS=False)
    denied=[]
    try:
        from v42_may_campaign.common import exclusive_lock
        from v42_may_campaign_native90.preflight import native_zero
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        with ExitStack() as stack:
            for path in locks:stack.enter_context(exclusive_lock(path))
            denied=stack.enter_context(native_zero());verify_records(sources)
            args,case=binding.prepare(output/'CASE',private_service=True)
            # Keep source Known R0/site/start and the causal grid-blind
            # scheduler. Remove only the diagnosed global future-Known barrier.
            args['reference']=CorrectedReferenceScheduler.from_dict(args['reference'].to_dict())
            case=dict(case,case_sha=digest(dict(parent=case['case_sha'],mode=start['execution_mode'],sources=sources)),
                comparator='NO_PRESITE_NO_TIMESHIFT_NO_MIGRATION',control_variant=None,
                grid_aware_admission=False,Known_R0_reference_unchanged=True,
                future_Known_global_Unknown_start_barrier=False)
            args['qos_window_provider'].case_sha=case['case_sha'];atomic(output/'CASE/CASE_BINDINGS.json',case)
            commands=deepcopy(args['known_schedule']);reference_before=deepcopy(args['reference'].assigned)
            observations=load_observations(begin=args['begin'],end=args['end'])
            args['weather']=[observations.at(args['begin']+t*900,observed_now=args['begin']+t*900)['weather']['values'] for t in range(120)]
            preparation_wall=perf_counter()-began;ticks=[]
            def on_tick(when,wall,starts):
                ticks.append(dict(time_seconds=when,wall_seconds=wall,starts=starts))
                progress(phase='GRID_BLIND_EVENT_FCFS',completed_control_ticks=len(ticks),
                    control_time_seconds=when,last_tick_wall_seconds=wall,candidate_Current_AC_calls=0)
            def controller(*a,**kw):
                return BaselineController(*a,rack_limits=binding.aidc['identity'].get('rack_compatibility',
                    read(case['source_receipts'][0]['path'])['rack_compatibility']),on_tick=on_tick,**kw)
            tick=perf_counter()
            actual=run_actual(**args,frozen_policy=None,controller_class=controller)
            actual_wall=perf_counter()-tick
            if args['known_schedule']!=commands or any(args['reference'].assigned[u]!=r for u,r in reference_before.items()):
                raise ValueError('BASELINE_SOURCE_R0_KNOWN_COMMAND_CHANGED')
            carry=actual.pop('carryout');atomic(output/'SIMULATOR_PRIVATE_CARRYOUT.json',carry)
            rows=physical_rows(actual,args,observations)
            np.savez_compressed(output/'ACTUAL_PHYSICAL.npz',GPU=actual['occupancy_GPU'],compute_GPU=actual['compute_occupancy_GPU'],
                **actual['physical'],sites=np.array(actual['sites']))
            for key in ('occupancy_GPU','compute_occupancy_GPU','physical'):actual.pop(key)
            atomic(output/'ACTUAL_EVENT_LEDGERS.json',actual)
            if actual['migration_receipts'] or any(r.get('policy_action') not in (None,'START') or
                    r.get('intentional_delay_seconds',0)!=0 or r['migration_count'] for r in actual['queue_ledger']):
                raise ValueError('BASELINE_CONTAINS_CONTROLLED_FLEXIBILITY')
            if any(r['admitted_time'] is not None and r['site']!=args['reference'].assigned[r['job_uid']]['reference_site']
                    for r in actual['queue_ledger']):raise ValueError('BASELINE_REFERENCE_SITE_CHANGED')
            progress(phase='ONE_INDEPENDENT_SEQUENTIAL_FRESH120_WITH_ACTUAL96')
            oracle=FullPrefixReferenceAC(issue_seconds=args['begin'],sites=actual['sites'],power_model=args['power_model'],
                observations=observations,mess_plan=mess,day_start_seconds=args['begin']+21600)
            tick=perf_counter();fresh=oracle.full_fresh_probe(rows);fresh_wall=perf_counter()-tick
            atomic(output/'FRESH_ORIGINAL7_AC.json',fresh)
            evaluated=fresh['physical_steps'][24:];fresh_pass=len(evaluated)==96 and all(r['PASS'] for r in evaluated)
            receipt=actual['receipt'];execution_pass=receipt['capacity_violations']==0 and receipt['dropped_jobs']==0
            if denied:raise ValueError('BASELINE_NATIVE0_VIOLATION')
            verify_records(sources)
            result.update(PASS=execution_pass and fresh_pass,Actual96_execution_PASS=execution_pass,Fresh96_physical_PASS=fresh_pass,
                preparation_wall_seconds=preparation_wall,Actual_wall_seconds=actual_wall,Fresh_wall_seconds=fresh_wall,
                Known_R0_unchanged=True,Pre_site_actions=0,Time_shift_actions=0,Migration_actions=0,
                candidate_Current_AC_calls=0,candidate_past_slot_replays=0,
                sequential_Fresh_counts=oracle.performance,Fresh_actual_slots=len(evaluated),
                Fresh_violations={k:sum(r['violations'][k] for r in evaluated) for k in evaluated[0]['violations']},
                peak_line_phase_loading=max(r['maximum_phase_line_loading'] for r in evaluated),
                controller_max_seconds=max(r['wall_seconds'] for r in ticks),receipt=receipt,
                Source_initial_sites_certified=False,initial_sites_assumption='44_MODEL_ASSUMED_210_RETAINED',
                FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False)
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        done.set();thread.join(timeout=12)
        result.update(finished_UTC=now(),wall_seconds=perf_counter()-began,Native_calls=0,Native_seconds=0.,
            inflight=None,denied_Native_attempts=denied,raw_preserved=True)
        atomic(output/'RESULT.json',result);atomic(output/'RECONCILIATION.json',dict(UTC=now(),Native_calls=0,Native_seconds=0.,inflight=None))
    return result
