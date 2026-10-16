"""Post-Strict, locked independent Signed-versus-AC candidate diagnosis."""
from contextlib import ExitStack
from pathlib import Path
from collections import Counter
import math
import os

import numpy as np
import psutil

from v43.common import ROOT,RUNS,DOC,read,record,atomic,now
from v43_actual.vendor.qos import CausalReferenceScheduler
from v43_actual.observations import load_observations
from v43_actual.vendor.policy import digest
from v43_mess.budget import heavy_peers
from .binding import CorrectiveBinding
from .current_ac import FullPrefixReferenceAC


def run(output,*,strict='D:/MobileESS_V43/runtime/gate_b_c0_c1_actual96_attempt001',samples=3):
    if heavy_peers():raise RuntimeError('WAIT_FOR_ACTIVE_HEAVY_WORKER_OFFICIAL_TERMINATION')
    output=Path(output);strict=Path(strict)
    if output.exists():raise ValueError('FRESH_DIAGNOSTIC_ATTEMPT_REQUIRED')
    output.mkdir(parents=True)
    atomic(output/'START.json',dict(UTC=now(),pid=os.getpid(),creation=psutil.Process().create_time(),
        Native_calls=0,Source=[record(p) for p in sorted((ROOT/'v43_corrective').glob('*.py'))]))
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
    locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
    locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
    comparisons=[]
    with ExitStack() as stack:
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        binding=CorrectiveBinding('B1');args,case=binding.prepare(output/'CASE',private_service=False)
        reference,packet,bindings,_=binding.build(args,case,output/'REFERENCE')
        source=read(strict/'C0/ACTUAL_EVENT_LEDGERS.json')
        if source['migration_receipts']:raise ValueError('DIAGNOSIS_REQUIRES_EXPLICIT_MIGRATION_REPLAY')
        jobs={r['job_uid']:r for r in source['queue_ledger']}
        requests={r.uid:r for r in args['requests'] if r.metadata.get('origin_unknown') is True}
        old=CausalReferenceScheduler.from_dict(read(output/'CASE/UNCORRECTED_REFERENCE_SEED.json'))
        for r in sorted(requests.values(),key=lambda r:(r.submit,r.uid)):old.submit(r,event_seconds=r.submit)
        candidates=[];seen=set()
        for e in source['job_event_ledger']:
            if e['uid'] in requests and e.get('reason')=='CURRENT_OBSERVED_ORIGINAL_PLANNING_VOLTAGE':
                key=(e['time_seconds'],old.assigned[e['uid']]['reference_site'])
                if key not in seen:
                    candidates.append(e);seen.add(key)
        observations=load_observations(begin=args['begin'],end=args['end'])
        with np.load(strict/'C0/ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
            history_arrays={k:z[k].copy() for k in ('GPU','PCC_P_kw','PCC_Q_kvar')}
        for index,e in enumerate(candidates[:samples]):
            when=e['time_seconds'];uid=e['uid'];request=requests[uid]
            site=old.assigned[uid]['reference_site'];slot=int((when-reference.begin)//900)
            if not 0<=slot<96:continue
            released={x['uid'] for x in source['job_event_ledger'] if x['event']=='GPU_RELEASE_CONTROL' and x['time_seconds']<=when}
            gpu=np.zeros(len(reference.sites))
            for other,row in jobs.items():
                if row['admitted_time'] is not None and row['admitted_time']<=when and other not in released:
                    gpu[reference.sites.index(row['site'])]+=row['GPU_gang']
            baseline_gpu=gpu.copy();gpu[reference.sites.index(site)]+=request.gpu
            obs=observations.at(when,observed_now=when)
            physical=args['power_model'].recompute(gpu[None,:],reference.sites,[obs['weather']['values']])
            cols=[packet.control_names.index('aidc_load_kw['+s+']') for s in reference.sites]
            delta=(physical['PCC_P_kw'][0]-packet.controls[slot,cols])/packet.p_slope[slot]
            peak,violations=packet._at_slot(slot,delta)
            control=packet.controls[slot].copy();control[cols]=physical['PCC_P_kw'][0]
            c=packet.coefficients[slot];v2=c.voltage_constant+c.voltage_matrix.T@control
            prefix=int((when-args['begin'])//900);history=[]
            for t in range(prefix):
                begin=args['begin']+t*900
                history.append(dict(slot=t,start_seconds=begin,end_seconds=begin+900,
                    GPU=history_arrays['GPU'][t].tolist(),P=history_arrays['PCC_P_kw'][t].tolist(),
                    Q=history_arrays['PCC_Q_kvar'][t].tolist(),observations=observations.at(begin,observed_now=when)))
            oracle=FullPrefixReferenceAC(mess_plan=None,day_start_seconds=reference.begin,issue_seconds=args['begin'],detailed=True,
                sites=reference.sites,power_model=args['power_model'],observations=observations)
            oracle.observe(when,history);ac=oracle.evaluate(when,gpu,uid=uid)
            receipt=output/f'CANDIDATE_{index+1:03d}_CURRENT_AC.json';atomic(receipt,ac)
            baseline_ac=oracle.evaluate(when,baseline_gpu,uid='OBSERVED_BASELINE')
            baseline_receipt=output/f'BASELINE_{index+1:03d}_CURRENT_AC.json';atomic(baseline_receipt,baseline_ac)
            nodes=ac['current']['voltage_node_names']
            if len(nodes)!=len(v2):raise ValueError('SIGNED_CURRENT_AC_VOLTAGE_AXIS_SIZE_MISMATCH')
            bad=np.flatnonzero((v2<packet.voltage_lower)|(v2>packet.voltage_upper))
            comparisons.append(dict(uid=uid,time_seconds=when,site=site,gpu=request.gpu,
                Signed_violations=violations,Signed_peak=peak,Signed_voltage_squared_min=float(v2.min()),
                Signed_voltage_squared_max=float(v2.max()),Signed_voltage_min_index=int(np.argmin(v2)),
                Signed_voltage_max_index=int(np.argmax(v2)),Current_AC=record(receipt),
                Current_AC_PASS=ac['PASS'],Current_AC_current=ac['current'],
                baseline_Current_AC=record(baseline_receipt),baseline_Current_AC_PASS=baseline_ac['PASS'],
                rejected_voltage_nodes=[dict(node=nodes[int(j)],phase='ABC'[int(nodes[int(j)].rsplit('.',1)[-1])-1],
                    Signed_v_squared=float(v2[j]),Signed_v_pu=math.sqrt(v2[j]) if v2[j]>=0 else None,
                    Current_AC_v_pu=ac['current']['voltage_vector_pu'][j],
                    lower_pu=.95,upper_pu=1.05) for j in bad],
                physical_current_background='OBSERVED_AEMO_ASOF_NATIVE_LOAD_ALLOCATION',
                Signed_background='IMMUTABLE_D1_FORECAST_COEFFICIENT_INTERCEPT_AND_ANCHOR',
                candidate_GPU_by_site=dict(zip(reference.sites,gpu.tolist())),
                Source_coefficient_sha=c.coefficient_sha256,Source_actual_weather=obs['weather'],
                input_history_contains_only_past_slots=True))
        if denied:raise ValueError('DIAGNOSTIC_NATIVE0_VIOLATION')
    disagreements=[c for c in comparisons if c['Signed_violations'] and c['Current_AC_PASS']]
    # A mismatch is evidence, not yet a causal attribution. Root-cause review
    # must establish the forecast/observed background and regulator contract
    # before issuing a usable policy correction proof.
    result=dict(UTC=now(),arm='B1',anchors={k:bindings[k] for k in ('case_sha','response_sha','aidc_anchor','mess_anchor')},
        evidence_scope='REAL_V43_R1_FLEX30_CORRECTIVE',comparisons=comparisons,
        independent_current_AC_mismatch_count=len(disagreements),root_cause_verified=False,
        physical_bands_unchanged=True,correction_authorized=False,Native_calls=0,Native_seconds=0.,inflight=None,
        Strict_source_raw_modified=False,Known_commands_changed=False)
    atomic(output/'RESULT.json',result);atomic(output/'RECONCILIATION.json',dict(Native_calls=0,Native_seconds=0.,inflight=None))
    atomic(DOC/'V43_R1_SIGNED_CURRENT_AC_DIAGNOSIS_POINTER.json',dict(result=record(output/'RESULT.json'),
        status='MISMATCH_EVIDENCE_REQUIRES_ROOT_CAUSE_REVIEW',policy_hard_gate_disabled=False))
    return result


if __name__=='__main__':
    import sys
    run(sys.argv[1])
