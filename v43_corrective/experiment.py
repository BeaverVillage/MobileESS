"""May01 B1 C1 only: audit frozen Planning, one event canary, one Actual96."""
from contextlib import ExitStack
from collections import Counter
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys

import numpy as np

from v43.common import ROOT,DOC,RUNS,read,record,atomic,verify_records,now
from v43_actual.case import accepted,BUNDLE
from v43_actual.vendor.aidc_sensitivity_runtime import grid_numeric_fingerprint
from .binding import CorrectiveBinding

PREFLIGHT=RUNS/'may01_B1_R1_FLEX30_C1_preflight_attempt002'
CANARY=RUNS/'may01_B1_R1_FLEX30_C1_canary_attempt001'
ACTUAL=RUNS/'may01_B1_R1_FLEX30_C1_actual96_attempt001'
PARENT=RUNS/'may01_B1_C0_corrective_actual96_attempt001'


def prepare():
    if PREFLIGHT.exists():raise ValueError('IMMUTABLE_NEW_PREFLIGHT_REQUIRED')
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    from .safety import no_heavy_peer
    no_heavy_peer();began=perf_counter()
    with ExitStack() as stack:
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        certificate,freeze,native,windows,arrays=accepted()
        assert certificate['UB']==0.6718471055537026 and certificate['independent_Global_LB']==0.6715871456570585
        args,case=CorrectiveBinding('B1').prepare(PREFLIGHT/'CASE',private_service=False)
        reference,packet,bindings,_=CorrectiveBinding('B1').build(args,case,PREFLIGHT/'REFERENCE')
        oldcase=read(PARENT/'CASE/CASE_BINDINGS.json');oldref=read(PARENT/'GOLDEN_REFERENCE/REFERENCE_PROOF.json')
        for k,v in oldref['bindings'].items():
            if k!='case_sha':assert bindings[k]==v,k
        assert oldcase['strict_parent_case_sha']==case['strict_parent_case_sha']
        assert oldcase['Known_commands_sha']==case['Known_commands_sha']
        assert oldcase['source_receipts']==case['source_receipts']
        with np.load(PARENT/'GOLDEN_REFERENCE/REFERENCE.npz',allow_pickle=False) as old, np.load(PREFLIGHT/'REFERENCE/REFERENCE.npz',allow_pickle=False) as new:
            exact=[k for k in old.files if k!='target_sha']
            for k in exact:assert np.array_equal(old[k],new[k]),k
        prior=read(read(DOC/'V43_B1_CURRENT_CASE_CORRECTION_PROOF_POINTER.json')['proof']['path'])
        fingerprint=grid_numeric_fingerprint(packet)
        assert fingerprint==prior['unchanged_response_numeric_sha']
        verify_records([prior['reused_real_AC_evidence'],prior['contract_review']])
        proof=dict(prior,anchors={k:bindings[k] for k in ('case_sha','response_sha','aidc_anchor','mess_anchor')},
            UTC=now(),scope='C1_ATTEMPT_EXACT_SCIENTIFIC_INPUT_REFERENCE_COMMAND_AND_RESPONSE_EQUALITY',
            parent_proof=record(read(DOC/'V43_B1_CURRENT_CASE_CORRECTION_PROOF_POINTER.json')['proof']['path']),
            exact_reference_arrays_and_commands=exact,unchanged_response_numeric_sha=fingerprint,
            new_controller_source=[record(p) for p in sorted((ROOT/'v43_corrective').glob('*.py'))],
            verified_unchanged_core_sources=[])  # old controller identities are not this attempt's source proof
        atomic(PREFLIGHT/'CURRENT_AFFINE_PROOF.json',proof)
        by={r['job_id']:r for r in windows};raw={r['job_uid']:r for r in native['known_population']}
        source={r['job_uid']:r for r in read(BUNDLE/'PLANNING_INPUT_BUNDLE.json')['known_population']}
        issue=args['begin'];mismatches=[];checked=[]
        # Original FULL loader explicitly binds native boundaries to precisely
        # WINDOWS.allowed_starts; no FULL model or Native solve is constructed.
        loader=ROOT/'v42_pr134_b1/native.py'
        assert "allowed_starts=tuple(windows[uid]['allowed_starts'])" in loader.read_text(encoding='utf8')
        for uid,command in args['known_schedule'].items():
            w=by[uid];slot=freeze['selected_jobs'][uid]['start'];allowed=[issue+900*t for t in w['allowed_starts']]
            assert command['start_seconds']==issue+900*slot
            row=dict(uid=uid,Golden_start_slot=slot,Golden_start_seconds=command['start_seconds'],
                PR189_FULL_allowed_slots=w['allowed_starts'],WINDOWS=w,
                OriginalKnownWindows_allowed_seconds=allowed,
                Actual_known_decision_status='KNOWN_EXECUTION_COMMAND' if command['start_seconds'] in allowed else 'PLAN_OUTSIDE_AUTHORIZED_WINDOW',
                source_can_timeshift=raw[uid]['can_timeshift'],source_delay_budget_slots=raw[uid]['delay_budget_slots'],
                source_request={k:source[uid].get(k) for k in ('qos','protected','submit_time','release_seconds',
                    'hard_earliest_start_seconds','hard_latest_start_seconds','completion_deadline_seconds','request_version_history')},
                axis='D-1_18AEST_08UTC_PLUS_900_SECONDS_PER_SLOT',window_widened=False)
            checked.append(row)
            if command['start_seconds'] not in allowed:mismatches.append(row)
        old=read(PARENT/'C0/ACTUAL_EVENT_LEDGERS.json');unstarted={r['job_uid'] for r in old['queue_ledger']
            if not r['origin_unknown'] and r['admitted_time'] is None}
        mismatch_uids={r['uid'] for r in mismatches};remaining=unstarted-mismatch_uids
        events={u:[] for u in remaining}
        for e in old['job_event_ledger']:
            if e['uid'] in events and e.get('reason'):events[e['uid']].append(e)
        remainder=[dict(uid=u,last_reason=events[u][-1]['reason'] if events[u] else None,
            reason_counts=dict(Counter(e['reason'] for e in events[u])),events=events[u]) for u in sorted(remaining)]
        audit=dict(UTC=now(),planning_contract_status='FAIL' if mismatches else 'PASS',
            service_equivalence='NOT_CERTIFIED',adapter_axis_bug=False,adapter_windows_modified=False,
            checked_UID_count=len(checked),mismatch_UID_count=len(mismatches),mismatch_UIDs=mismatches,all_UIDs=checked,
            prior_unstarted_Known=len(unstarted),prior_other_unstarted_Known_count=len(remaining),
            prior_other_unstarted_Known=remainder,original_FULL_loader=record(loader),
            original_WINDOW=freeze['scientific_input']['WINDOWS.json'],Golden003=certificate,
            execution_authority_not_inferred_from_Golden_numerical_certificate=True,Native_calls=0)
        atomic(PREFLIGHT/'KNOWN_WINDOW_AUDIT.json',audit)
        assert not denied
        result=dict(PASS=True,Known_contract_PASS=not mismatches,service_equivalence='NOT_CERTIFIED',
            Golden003_reoptimized=False,Native_calls=0,Native_seconds=0.,wall_seconds=perf_counter()-began,
            exact_scientific_case_PASS=True,proof=record(PREFLIGHT/'CURRENT_AFFINE_PROOF.json'),
            Known_window_audit=record(PREFLIGHT/'KNOWN_WINDOW_AUDIT.json'))
        atomic(PREFLIGHT/'RESULT.json',result);return result


def run_canary():
    from .compare import run
    pre=read(PREFLIGHT/'RESULT.json');verify_records([pre['proof'],pre['Known_window_audit']])
    # One short real event run including the issue prefix and D00 candidate tick.
    result=run('B1',CANARY,variants=('C1',),control_slots=25,ac_mode='FAST',
        ac_certification=read(DOC/'V43_CURRENT_AC_PRODUCTION_CERTIFICATION_POINTER.json')['certificate']['path'],
        correction_proof=pre['proof']['path'])
    if not result['PASS']:raise RuntimeError('REAL_C1_CANARY_FAILED')
    receipts=read(CANARY/'CORRECTIVE_POLICY_RECEIPTS.json');p=receipts['policies'][0]
    assert p['variant']=='C1'
    assert not any(r.get('reason')=='C0_BASIC_SITE_ONLY' for r in p['candidate_funnel'])
    evaluated=[r for r in p['candidate_funnel'] if r.get('participant') and r.get('sensitivity_evaluated')
        and r['site']!=r['basic_site'] and r['time_seconds']>=1746021600.]
    assert evaluated,'NO_REAL_DDAY_PARTICIPANT_ALTERNATIVE_SENSITIVITY_EVALUATION'
    sys.path.insert(0,str(ROOT/'tests'))
    from test_v43_c1_performance import pending_overrun_canary
    fixture=pending_overrun_canary()
    atomic(CANARY/'PENDING_OVERRUN_EVENT_FIXTURE.json',fixture)
    evidence=dict(PASS=True,actual_canary=record(CANARY/'RESULT.json'),
        real_alternative_sensitivity_candidates=len(evaluated),candidate_evidence=evaluated,
        named_overrun_pending_retry=record(CANARY/'PENDING_OVERRUN_EVENT_FIXTURE.json'),
        Native_calls=0,full_Actual_authorized_by_user=True)
    atomic(CANARY/'CANARY_GATE.json',evidence);return evidence


def run_actual():
    gate=read(CANARY/'CANARY_GATE.json');assert gate['PASS']
    verify_records([gate['actual_canary'],gate['named_overrun_pending_retry']])
    from v43.may01 import actual
    return actual('B1',ACTUAL,correction_proof=PREFLIGHT/'CURRENT_AFFINE_PROOF.json')


def complete_canary_evidence():
    """Continue the one canary's evidence; no second event trajectory is run.

    Reconstruct its public D00 pre-admission state using only observations
    at/before D00, and expose all scored alternatives hidden by old logging.
    """
    from copy import deepcopy
    from types import SimpleNamespace
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    from v43_actual.observations import load_observations
    from v43_actual.compare import physical_rows
    from .current_ac import CertifiedPrefixAC
    from .policy import CorrectivePolicy
    from .controller import CorrectiveReservations
    folder=CANARY/'CANDIDATE_EVIDENCE_CONTINUATION002'
    if folder.exists():raise ValueError('IMMUTABLE_CANARY_EVIDENCE_REQUIRED')
    with ExitStack() as stack:
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        args,case=CorrectiveBinding('B1').prepare(folder/'CASE',private_service=False)
        ref,packet,bindings,_=CorrectiveBinding('B1').build(args,case,folder/'REFERENCE')
        when=ref.begin;event=read(CANARY/'C1/ACTUAL_EVENT_LEDGERS.json')
        saved=read(CANARY/'C1/SIMULATOR_PRIVATE_CARRYOUT.json')['controller']
        metadata=deepcopy(saved['metadata']);jobs={r['job_uid']:r for r in event['queue_ledger']}
        completed={r['uid'] for r in event['job_event_ledger'] if r['event']=='COMPLETION_OBSERVED' and r['time_seconds']<=when}
        released={r['uid'] for r in event['job_event_ledger'] if r['event']=='GPU_RELEASE_CONTROL' and r['time_seconds']<=when}
        owner=SimpleNamespace(known_schedule=args['known_schedule'],metadata=metadata,
            requests={uid:SimpleNamespace(q50=r['q50']) for uid,r in saved['requests'].items()})
        ledger=CorrectiveReservations(owner,capacities=args['capacities'])
        current={s:0. for s in ref.sites}
        for uid,m in metadata.items():
            assert m['submit_seconds']<=when
            row=jobs[uid];a=row['admitted_time'];m['accumulated_compute_seconds']=0.
            m['state']='COMPLETED' if uid in completed else 'RUNNING' if a is not None and a<when else 'PENDING'
            if uid in completed:ledger.known_plans.pop(uid,None)
            if m['state']=='RUNNING':
                m['current_site']=row['site'];m['accumulated_compute_seconds']=when-a
                ledger.retain_running(uid,row['site'],when,when+900,m['gpu'])
            if a is not None and a<when and uid not in released:current[row['site']]+=m['gpu']
        obs=load_observations(begin=args['begin'],end=args['end'])
        oracle=CertifiedPrefixAC(issue_seconds=args['begin'],sites=ref.sites,power_model=args['power_model'],
            observations=obs,mess_plan=None,day_start_seconds=when)
        with np.load(CANARY/'C1/ACTUAL_PHYSICAL.npz',allow_pickle=False) as z:
            history=[dict(slot=t,start_seconds=args['begin']+900*t,end_seconds=args['begin']+900*(t+1),
                GPU=z['GPU'][t].tolist(),P=z['PCC_P_kw'][t].tolist(),Q=z['PCC_Q_kvar'][t].tolist(),
                observations=obs.at(args['begin']+900*t,observed_now=when),
                authority='OBSERVED_PHYSICAL_HOLD_INTERVAL_INTEGRAL') for t in range(24)]
        oracle.observe(when,history)
        proof=read(PREFLIGHT/'CURRENT_AFFINE_PROOF.json')
        p=CorrectivePolicy(ref,packet,variant='C1',oracle=oracle,bindings=bindings,expected_bindings=bindings,
            correction_proof=proof,evidence_scope='REAL_V43_R1_FLEX30_CORRECTIVE')
        p.bind_observed_c1(args['power_model'],current_weather_provider=lambda t:obs.at(t,observed_now=oracle.now)['weather']['values'])
        p.observe(when,current,metadata)
        candidates=[m for m in metadata.values() if m['state']=='PENDING' and m.get('r1_flex30',{}).get('participant')]
        assert candidates
        decision=p.select(sorted(candidates,key=lambda m:(m['submit_seconds'],m['uid']))[0],None,when,ledger)
        alternatives=[r for r in p.funnel if r.get('sensitivity_evaluated') and r['site']!=r['basic_site']]
        assert alternatives and not denied
        evidence=dict(PASS=True,Native_calls=0,public_clock_seconds=when,decision=decision,
            all_scored_candidates=p.funnel,real_alternative_sensitivity_candidates=len(alternatives),
            public_state_reconstruction='ONLY_ARRIVALS_STARTS_COMPLETIONS_RELEASES_OBSERVED_AT_OR_BEFORE_D00',
            private_future_runtime_reads=0,Current_AC=oracle.audit,
            source=[record(p) for p in sorted((ROOT/'v43_corrective').glob('*.py'))],
            original_canary=record(CANARY/'RESULT.json'),event_trajectory_reruns=0)
        atomic(folder/'RESULT.json',evidence)
        sys.path.insert(0,str(ROOT/'tests'))
        from test_v43_c1_performance import pending_overrun_canary
        atomic(folder/'PENDING_OVERRUN_EVENT_FIXTURE.json',pending_overrun_canary())
        gate=dict(PASS=True,actual_canary=record(CANARY/'RESULT.json'),
            named_overrun_pending_retry=record(folder/'PENDING_OVERRUN_EVENT_FIXTURE.json'),
            real_candidate_evidence=record(folder/'RESULT.json'),real_alternative_sensitivity_candidates=len(alternatives),
            event_trajectory_reruns=0,Native_calls=0)
        atomic(CANARY/'CANARY_GATE.json',gate);return gate


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','canary','canary-evidence','actual'])
    action=p.parse_args().action
    print(json.dumps({'prepare':prepare,'canary':run_canary,'canary-evidence':complete_canary_evidence,'actual':run_actual}[action](),default=str))
