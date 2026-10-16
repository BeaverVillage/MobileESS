"""Reuse real AC evidence only after exact B1 mathematical-input equality."""
from contextlib import ExitStack
from pathlib import Path
import numpy as np

from v43.common import ROOT,DOC,RUNS,read,record,verify_records,atomic,now
from v43_corrective.binding import CorrectiveBinding
from v43_mess.budget import heavy_peers


def run(output):
    if heavy_peers():raise RuntimeError('NO_COMPETING_HEAVY_WORKER')
    output=Path(output)
    if output.exists():raise ValueError('FRESH_B1_MATH_EQUIVALENCE_ATTEMPT_REQUIRED')
    parent=Path('D:/MobileESS_V43/runtime/corrective_signed_ac_diagnosis_attempt001')
    old=read(DOC/'V43_R1_B1_AFFINE_CURRENT_CORRECTION_PROOF.json')
    verify_records([old['contract_review'],old['evidence']])
    oldstart=read(parent/'START.json')
    core=[r for r in oldstart['Source'] if Path(r['path']).name!='compare.py']
    verify_records(core)
    oldcase=read(parent/'CASE/CASE_BINDINGS.json');oldbindings=read(parent/'REFERENCE/REFERENCE_PROOF.json')['bindings']
    output.mkdir(parents=True)
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
    locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
    locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
    with ExitStack() as stack:
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        binding=CorrectiveBinding('B1');args,case=binding.prepare(output/'CASE',private_service=False)
        reference,packet,bindings,_=binding.build(args,case,output/'REFERENCE')
        for key in ('strict_parent_case_sha','Known_commands_sha','reference_sha','source_receipts'):
            if case[key]!=oldcase[key]:raise ValueError('B1_SCIENTIFIC_INPUT_DRIFT:'+key)
        if {k:v for k,v in bindings.items() if k!='case_sha'}!={k:v for k,v in oldbindings.items() if k!='case_sha'}:
            raise ValueError('B1_RESPONSE_OR_STAGE_AUTHORITY_DRIFT')
        checked=[]
        with np.load(parent/'REFERENCE/REFERENCE.npz',allow_pickle=False) as before,np.load(output/'REFERENCE/REFERENCE.npz',allow_pickle=False) as after:
            if set(before.files)!=set(after.files):raise ValueError('B1_REFERENCE_ARRAY_AXIS_DRIFT')
            for key in before.files:
                if before[key].dtype.kind in 'fciu' or key in ('sites','Known_UID_Schedule_JSON'):
                    if not np.array_equal(before[key],after[key]):raise ValueError('B1_REFERENCE_NUMERIC_OR_COMMAND_DRIFT:'+key)
                    checked.append(key)
        from v43_actual.vendor.aidc_sensitivity_runtime import grid_numeric_fingerprint
        oldspec=read('D:/MobileESS_V43/runtime/corrective_B1_full_prefix_canary_attempt001/CORRECTIVE_POLICY_RECEIPTS.json')['policies'][0]['spec']
        numeric=grid_numeric_fingerprint(packet)
        if numeric!=oldspec['response_numeric_sha']:raise ValueError('B1_FULL_GRID_NUMERIC_PACKET_DRIFT')
        if denied:raise ValueError('B1_EQUIVALENCE_NATIVE0_VIOLATION')
    proof=dict(old,UTC=now(),anchors={k:bindings[k] for k in old['anchors']},
        scope='EXACT_CURRENT_B1_CASE_AFTER_INDEPENDENT_INPUT_PACKET_AND_CORE_SOURCE_EQUALITY',
        reused_real_AC_evidence=record(parent/'RESULT.json'),verified_unchanged_core_sources=core,
        changed_dispatch_only_source=record(ROOT/'v43_corrective/compare.py'),
        unchanged_strict_parent_case_sha=case['strict_parent_case_sha'],unchanged_response_numeric_sha=numeric,
        exact_reference_arrays_and_commands=checked,new_DSS_execution=False,
        historical_UB_LB_or_Native_clock_reused=False,Native_calls=0,Native_seconds=0.,inflight=None)
    atomic(output/'RESULT.json',proof);atomic(output/'RECONCILIATION.json',dict(Native_calls=0,Native_seconds=0.,inflight=None))
    atomic(DOC/'V43_B1_CURRENT_CASE_CORRECTION_PROOF_POINTER.json',dict(proof=record(output/'RESULT.json')))
    return proof


if __name__=='__main__':
    import sys
    run(sys.argv[1])
