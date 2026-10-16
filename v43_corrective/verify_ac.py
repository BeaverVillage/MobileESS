"""Locked real observed-prefix equivalence; never reruns a whole Actual case."""
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
import os

import numpy as np
import psutil

from v43.common import ROOT,RUNS,DOC,read,record,atomic,now
from v43_actual.observations import load_observations
from v43_mess.budget import heavy_peers
from .binding import CorrectiveBinding
from .current_ac import ShadowCertifiedPrefixAC


def run(output,*,source_attempt='D:/MobileESS_V43/runtime/may01_B0_C0_C1_actual96_attempt002'):
    if heavy_peers():raise RuntimeError('WAIT_FOR_HEAVY_WORKER_OFFICIAL_EXIT_AND_LOCK_RELEASE')
    output=Path(output);source_attempt=Path(source_attempt)
    if output.exists():raise ValueError('NEW_AC_EQUIVALENCE_ATTEMPT_REQUIRED')
    start=read(source_attempt/'START.json')
    try:
        process=psutil.Process(start['pid'])
        if process.create_time()==start['process_created']:raise RuntimeError('SOURCE_ACTUAL_WORKER_STILL_ALIVE')
    except psutil.NoSuchProcess:pass
    if not read(source_attempt/'RESULT.json')['PASS']:raise ValueError('SOURCE_ACTUAL_NOT_SUCCESSFULLY_RECONCILED')
    rec=read(source_attempt/'RECONCILIATION.json')
    if rec['inflight'] is not None or rec['Native_calls']!=0:raise ValueError('SOURCE_LEDGER_NOT_SETTLED')
    output.mkdir(parents=True);began=perf_counter()
    atomic(output/'START.json',dict(UTC=now(),pid=os.getpid(),creation=psutil.Process().create_time(),
        source_attempt=record(source_attempt/'RESULT.json'),optimized_source=record(ROOT/'v43_corrective/current_ac.py')))
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
    locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
    locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
    with ExitStack() as stack:
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        args,identity=CorrectiveBinding('B1').prepare(output/'CASE',private_service=False)
        observations=load_observations(begin=args['begin'],end=args['end'])
        oracle=ShadowCertifiedPrefixAC(mess_plan=None,day_start_seconds=args['begin']+21600,
            issue_seconds=args['begin'],sites=tuple(sorted(args['capacities'])),power_model=args['power_model'],observations=observations)
        event=read(source_attempt/'C0/ACTUAL_EVENT_LEDGERS.json');jobs=event['queue_ledger']
        requests={r.uid:r for r in args['requests'] if r.metadata.get('origin_unknown') is True}
        actual_by={r['job_uid']:r for r in jobs}
        with np.load(source_attempt/'C0/ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
            physical={k:z[k].copy() for k in ('GPU','PCC_P_kw','PCC_Q_kvar')}
        def history(count,observed_now):
            rows=[]
            for t in range(count):
                begin=args['begin']+t*900
                rows.append(dict(slot=t,start_seconds=begin,end_seconds=begin+900,GPU=physical['GPU'][t].tolist(),
                    P=physical['PCC_P_kw'][t].tolist(),Q=physical['PCC_Q_kvar'][t].tolist(),
                    observations=observations.at(begin,observed_now=observed_now),authority='OBSERVED_PHYSICAL_HOLD_INTERVAL_INTEGRAL'))
            return rows
        candidates=[]
        for prefix in (24,48,72,96,119):
            when=args['begin']+prefix*900;oracle.observe(when,history(prefix,when))
            released={e['uid'] for e in event['job_event_ledger'] if e['event']=='GPU_RELEASE_CONTROL' and e['time_seconds']<=when}
            current=np.zeros(len(oracle.sites))
            for row in jobs:
                if row['admitted_time'] is not None and row['admitted_time']<=when and row['job_uid'] not in released:
                    current[oracle.sites.index(row['site'])]+=row['GPU_gang']
            pending=next((r for r in sorted(requests.values(),key=lambda r:(r.submit,r.uid))
                if r.submit<=when and (actual_by[r.uid]['admitted_time'] is None or actual_by[r.uid]['admitted_time']>when)),None)
            if pending is None:continue
            for site in sorted(pending.compatible)[:3]:
                offered=current.copy();offered[oracle.sites.index(site)]+=pending.gpu
                result=oracle.evaluate(when,offered,uid=pending.uid)
                candidates.append(dict(uid=pending.uid,time_seconds=when,site=site,
                    offered_GPU=offered.tolist(),PASS=result['PASS'],input_sha=result['input_sha']))
                atomic(output/'progress.json',dict(UTC=now(),completed_candidates=len(candidates),prefix=prefix))
        # Whole-source trajectory Fresh is a single independent sequential
        # replay; its outputs are never substituted for the event occupancy.
        fresh=oracle.full_fresh_probe(history(120,args['end']))
        atomic(output/'FRESH_ORIGINAL7_AC.json',fresh)
        if denied:raise ValueError('AC_EQUIVALENCE_NATIVE0_VIOLATION')
        exact=all(p['PASS'] for p in oracle.equivalence) and len(oracle.equivalence)==len(candidates)
        sums=lambda key:{name:sum(p[key][name] for p in oracle.equivalence) for name in oracle.performance}
        result=dict(UTC=now(),PASS=exact,Native_calls=0,Native_seconds=0.,inflight=None,
            optimized_source=record(ROOT/'v43_corrective/current_ac.py'),source_Actual=record(source_attempt/'C0/ACTUAL_PHYSICAL.npz'),
            candidates=candidates,equivalence=oracle.equivalence,optimized_counts=sums('optimized_counts'),
            reference_counts=sums('reference_counts'),optimized_candidate_wall_seconds=sum(p['optimized_wall_seconds'] for p in oracle.equivalence),
            reference_candidate_wall_seconds=sum(p['reference_wall_seconds'] for p in oracle.equivalence),
            Source_actual_Fresh96_PASS=len(fresh['physical_steps'][24:])==96 and all(s['PASS'] for s in fresh['physical_steps'][24:]),
            wall_seconds=perf_counter()-began,state_clone_claimed=False,all_current_candidates_fully_measured=True,
            actual_execution_UID_site_time_GPU_equivalence='PENDING_PAIRED_SHORT_EVENT_CANARY',
            new_full_Actual_wall_seconds=None,new_max_controller_latency_seconds=None,
            scope='EXACT_DECLARED_OBSERVED_PREFIX_CANDIDATE_SET_NOT_ALL_MAY01_CANDIDATES_OR_NEW_ACTUAL_SERVICE')
    atomic(output/'RESULT.json',result);atomic(output/'RECONCILIATION.json',dict(Native_calls=0,Native_seconds=0.,inflight=None))
    atomic(DOC/'V43_CURRENT_AC_REAL_PREFIX_EQUIVALENCE_POINTER.json',dict(result=record(output/'RESULT.json'),
        paired_event_canary='NOT_RUN',production_fast_path_authorized=False))
    return result


if __name__=='__main__':
    import sys
    run(sys.argv[1])
