"""Bind the reviewed Actual/forecast authority correction to the B0 case.

Reuse only independently verified physical input receipts, never a solution
or objective bound. No new domain, forecast or electrical coefficient build.
"""
from contextlib import ExitStack
from pathlib import Path
import os
import numpy as np
import psutil

from v43.common import DOC,RUNS,ROOT,read,record,verify_records,atomic,now
from v43_actual.observations import load_observations
from v43_actual.vendor.policy import digest
from v43_corrective.binding import CorrectiveBinding
from v43_mess.budget import heavy_peers


def run(output):
    if heavy_peers():raise RuntimeError('WAIT_FOR_OFFICIAL_CANARY_EXIT')
    output=Path(output)
    if output.exists():raise ValueError('NEW_B0_AUTHORITY_ATTEMPT_REQUIRED')
    pointer=read(DOC/'V43_CURRENT_AC_REAL_PREFIX_EQUIVALENCE_POINTER.json')['result'];verify_records([pointer])
    evidence=read(pointer['path']);verify_records([evidence['source_Actual'],evidence['optimized_source']])
    if not evidence['PASS'] or not evidence['Source_actual_Fresh96_PASS']:
        raise ValueError('INDEPENDENT_REAL_B0_PREFIX_PROOF_REQUIRED')
    review=read(DOC/'V43_R1_AFFINE_CURRENT_CONTRACT_REVIEW.json')
    if review['root_cause_verified'] is not True:raise ValueError('CURRENT_AUTHORITY_CONTRACT_REVIEW_REQUIRED')
    output.mkdir(parents=True)
    atomic(output/'START.json',dict(UTC=now(),pid=os.getpid(),creation=psutil.Process().create_time(),
        source=record(__file__),Native_calls=0,independent_B0_AC_evidence=pointer))
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
    locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
    locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
    comparisons=[]
    with ExitStack() as stack:
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        binding=CorrectiveBinding('B0','D:/MobileESS_V43/inputs/V43_MAY01_B0_REFERENCE_003')
        args,case=binding.prepare(output/'CASE',private_service=False)
        reference,packet,bindings,_=binding.build(args,case,output/'REFERENCE')
        observations=load_observations(begin=args['begin'],end=args['end'])
        with np.load(evidence['source_Actual']['path'],allow_pickle=False) as z:
            arrays={k:z[k].copy() for k in ('GPU','PCC_P_kw','PCC_Q_kvar')}
        for candidate in evidence['candidates']:
            when=candidate['time_seconds'];prefix=int((when-args['begin'])/900);slot=prefix-24
            gpu=np.array(candidate['offered_GPU']);obs=observations.at(when,observed_now=when)
            physical=args['power_model'].recompute(gpu[None,:],reference.sites,[obs['weather']['values']])
            history=[]
            for t in range(prefix):
                begin=args['begin']+t*900
                history.append(dict(slot=t,start_seconds=begin,end_seconds=begin+900,
                    GPU=arrays['GPU'][t].tolist(),P=arrays['PCC_P_kw'][t].tolist(),Q=arrays['PCC_Q_kvar'][t].tolist(),
                    observations=observations.at(begin,observed_now=when),authority='OBSERVED_PHYSICAL_HOLD_INTERVAL_INTEGRAL'))
            current=dict(slot=prefix,start_seconds=when,end_seconds=when+900,GPU=gpu.tolist(),
                P=physical['PCC_P_kw'][0].tolist(),Q=physical['PCC_Q_kvar'][0].tolist(),observations=obs)
            key=digest(dict(history=history,current=current,source_power=args['power_model'].authority_sha,
                contract='PR189_ORIGINAL7_AUTO_SNAPSHOT_STATIC_NO_ADDED_SVR'))
            if key!=candidate['input_sha'] or candidate['PASS'] is not True:
                raise ValueError('B0_PREVIOUS_INDEPENDENT_AC_INPUT_NOT_IDENTICAL')
            cols=[packet.control_names.index('aidc_load_kw['+s+']') for s in reference.sites]
            delta=(physical['PCC_P_kw'][0]-packet.controls[slot,cols])/packet.p_slope[slot]
            _,violations=packet._at_slot(slot,delta)
            control=packet.controls[slot].copy();control[cols]+=delta*packet.p_slope[slot]
            if not np.allclose(control[cols],physical['PCC_P_kw'][0],rtol=0,atol=1e-12):
                raise ValueError('ORIGINAL_C1_CONTROL_UNITS_ROUNDTRIP')
            comparisons.append(dict(uid=candidate['uid'],site=candidate['site'],time_seconds=when,
                input_sha=key,independent_Current_AC_PASS=True,Signed_violations=violations,
                exact_physical_input_reuse=True,private_future_service_used=False))
        if denied:raise ValueError('B0_CURRENT_AUTHORITY_NATIVE0_VIOLATION')
    mismatches=sum(bool(c['Signed_violations']) for c in comparisons)
    proof=dict(UTC=now(),anchors={k:bindings[k] for k in ('case_sha','response_sha','aidc_anchor','mess_anchor')},
        evidence_scope='REAL_V43_R1_FLEX30_CORRECTIVE',independent_current_AC_mismatch_count=mismatches,
        root_cause_verified=mismatches>0,physical_bands_unchanged=True,correction_authorized=mismatches>0,
        contract_review=record(DOC/'V43_R1_AFFINE_CURRENT_CONTRACT_REVIEW.json'),independent_AC_evidence=pointer,
        comparisons=comparisons,Planning_model_changed=False,old_UB_LB_or_Native_clock_reused=False,
        Native_calls=0,Native_seconds=0.,inflight=None,scope='EXACT_B0_CORRECTIVE_CASE_ONLY')
    atomic(output/'RESULT.json',proof);atomic(output/'RECONCILIATION.json',dict(Native_calls=0,Native_seconds=0.,inflight=None))
    if mismatches>0:atomic(DOC/'V43_R1_B0_AFFINE_CURRENT_CORRECTION_PROOF.json',proof)
    return proof


if __name__=='__main__':
    import sys
    run(sys.argv[1])
