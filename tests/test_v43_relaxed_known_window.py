"""Small controller method tests only; no run_actual, solver, AC or Heavy Lock."""
from copy import deepcopy
import inspect

import pytest

from test_v43_corrective import policy,request,stats
from v43_actual.windows import OriginalKnownWindows
from v43_actual.vendor.policy import digest
from v43_corrective.controller import CorrectiveController,CorrectiveReservations,admission_core
from v43_corrective.known_window import RelaxedKnownController,POLICY_ID,select_controller
from v43_corrective.reference import CorrectedReferenceScheduler


def make(*,cls=RelaxedKnownController,start=1800.,reference=0.,latest=None,deadline=None,submit=0.,migration=False):
    p,_,_,_=policy('C1')
    q=OriginalKnownWindows(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'),
        windows=[dict(job_id='8632559',reference_start=int(reference/900),
            latest_start=int(reference/900),allowed_starts=[int(reference/900)])],issue_seconds=0.)
    ref=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF')
    ref.assigned['8632559']=dict(uid='8632559',reference_site='A',reference_start_seconds=reference,
        nominal_release_seconds=reference+900.,reference_sha=ref.reference_sha)
    command=dict(site='A',start_seconds=start,protected_segments=[
        dict(resource='gpu:A',begin=start,end=start+900.,quantity=1)])
    if migration:command.update(migration_destination='B',physical_checkpoint_seconds=start+450.,
        checkpoint_control_seconds=start+900.)
    c=cls({'A':1,'B':1},arm='B1',qos_window_provider=q,frozen_policy=p,reference=ref,
        known_schedule={'8632559':command})
    job=request('8632559',submit,site='A',origin_unknown=False,reference_start_seconds=reference,
        hard_latest_start_seconds=latest,completion_deadline_seconds=deadline)
    return c,job


def submit(c,r,now=None):c.submit(r,r.submit if now is None else now)


def measurements(c,phase):
    return [e for e in c.events if e['event']=='KNOWN_RESEARCH_QOS_MEASUREMENT' and e['phase']==phase]


def test_uid8632559_original_1800_only_plan1830_can_attempt_and_preserves_receipt():
    c,r=make(start=18.5*3600,reference=18*3600);submit(c,r)
    before=deepcopy(c.qos.export_ledger());commands=deepcopy(c.known_schedule)
    assert c.admit(18*3600)==[] and c.metadata[r.uid]['state']=='PENDING'
    assert c.admit(18.5*3600)==[r.uid]
    assert c.audit[r.uid]['site']=='A' and c.audit[r.uid]['plan_start_seconds']==18.5*3600
    assert c.qos.export_ledger()==before and c.known_schedule==commands
    assert measurements(c,'START')[0]['actual_start_in_original_allowed_starts'] is False
    strict,s=make(cls=CorrectiveController,start=18.5*3600,reference=18*3600);submit(strict,s)
    assert strict.admit(18.5*3600)==[]
    assert strict.decisions[s.uid]['status']=='PLAN_OUTSIDE_AUTHORIZED_WINDOW'


def test_running_overrun_queue_release_retry_no_eviction():
    c,r=make(start=0.);submit(c,r)
    other=request('RUNNING',site='A',origin_unknown=True);submit(c,other)
    c.ledger.start('RUNNING','A',0.,'TEST');c.pending.remove((0.,'RUNNING'))
    c.metadata['RUNNING'].update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800.)
    c.reservations.retain_running('RUNNING','A',0.,2700.,1)
    assert c.admit(1800.)==[] and c.metadata[r.uid]['state']=='PENDING'
    assert c.ledger.physical(1800.)['A']==1
    c.completion('RUNNING',1800.);c.reservations.release('RUNNING',1800.)
    assert c.admit(2700.)==[r.uid]
    assert c.ledger.physical(2700.)['A']==1


def test_hard_latest_and_completion_deadline_are_measured_not_blocked():
    c,r=make(start=1800.,latest=0.,deadline=900.);submit(c,r)
    assert c.admit(1800.)==[r.uid]
    row=measurements(c,'START')[0]
    assert row['hard_latest_start_excess_seconds']==1800.
    assert row['start_after_completion_deadline_seconds']==900.
    assert row['actual_completion_deadline_excess_seconds'] is None
    c.completion(r.uid,3600.)
    row=measurements(c,'COMPLETION')[0]
    assert row['actual_completion_deadline_excess_seconds']==2700.
    assert row['QoS_PASS']=='NOT_CLAIMED'
    assert c.metadata[r.uid]['completion_deadline_seconds']==900.


def test_no_start_before_submit_observation_release_or_frozen_start():
    c,r=make(start=0.,submit=1800.,reference=1800.)
    with pytest.raises(ValueError,match='FUTURE_SUBMISSION'):c.submit(r,0.)
    assert c.admit(0.)==[]
    submit(c,r,2700.)
    assert c._known_decision(r.uid,1800.)['start_seconds']==2700.
    assert c.admit(2700.)==[r.uid]
    c,r=make(start=3600.);submit(c,r)
    assert c.admit(2700.)==[] and c.metadata[r.uid]['state']=='PENDING'
    assert c.admit(3600.)==[r.uid]


def test_peer_committed_reservation_cannot_be_displaced():
    c,r=make(start=0.);submit(c,r)
    assert c.reservations.reserve('PEER',[dict(resource='gpu:A',begin=900.,end=2700.,quantity=1)])[0]
    before=deepcopy(c.reservations.reservations['PEER'])
    assert c.admit(1800.)==[] and c.reservations.reservations['PEER']==before
    assert c.admit(2700.)==[r.uid]


@pytest.mark.parametrize('reason',['RACK_GANG_INCOMPATIBLE','CURRENT_AC_VOLTAGE','LINE_RATING','TRANSFORMER_RATING'])
def test_physical_guard_still_blocks(reason):
    c,r=make(start=0.);submit(c,r)
    c.policy.current_guard=lambda *a:reason
    assert c.admit(0.)==[] and c.metadata[r.uid]['state']=='PENDING'
    assert any(e.get('reason')==reason for e in c.events)


def test_incompatible_site_and_frozen_command_mutation_rejected():
    c,r=make(start=0.);submit(c,r)
    c.requests[r.uid]=type(r)(r.uid,r.submit,r.gpu,('B',),r.q50,r.source_site,r.metadata)
    assert c.admit(0.)==[] and c.decisions[r.uid]['status']=='PLAN_SITE_NO_AUTHORITY'
    c.known_schedule[r.uid]['site']='B'
    with pytest.raises(ValueError,match='KNOWN_FROZEN_COMMANDS_MODIFIED'):c.admit(900.)


def test_delayed_known_does_not_force_old_migration_checkpoint():
    c,r=make(start=0.,migration=True);submit(c,r)
    assert c.admit(1800.)==[r.uid]
    commands=deepcopy(c.known_schedule)
    assert c.migration(r.uid,2700.,2250.) is None
    assert c.events[-1]['reason']=='KNOWN_DELAYED_START_INVALIDATES_PLANNED_CHECKPOINT'
    assert not c.migrations and c.known_schedule==commands


def test_unknown_deadline_and_participation_identical_in_both_controllers():
    outputs=[]
    for cls in (CorrectiveController,RelaxedKnownController):
        c,_=make(cls=cls)
        u=request('UNKNOWN',site='A',completion_deadline_seconds=1.)
        submit(c,u);assert c.admit(0.)==[];assert c.admit(900.)==[]
        assert not c._relaxed_known(u.uid) if cls is RelaxedKnownController else True
        def stable(v):
            if isinstance(v,dict):return {k:stable(x) for k,x in v.items() if k!='decision_seconds'}
            if isinstance(v,(list,tuple)):return [stable(x) for x in v]
            return v
        outputs.append(stable((c.qos.export_ledger(),c.participation.receipts,c.decisions,c.events,c.policy.funnel)))
    assert outputs[0]==outputs[1]


def test_only_deadline_ast_guard_diff_unknown_branch_exact(monkeypatch):
    import ast
    import builtins
    trees=[];original=builtins.compile
    def capture(source,*args,**kwargs):
        if isinstance(source,ast.Module):trees.append(deepcopy(source))
        return original(source,*args,**kwargs)
    monkeypatch.setattr(builtins,'compile',capture)
    admission_core();admission_core(relaxed_known=True)
    strict,relaxed=trees
    gates=[n for n in ast.walk(relaxed) if isinstance(n,ast.If)
        and isinstance(n.test,ast.BoolOp) and ast.unparse(n.test).startswith('not self._relaxed_known(uid)')]
    assert len(gates)==1
    gates[0].test=gates[0].test.values[1]
    assert ast.dump(strict,include_attributes=False)==ast.dump(relaxed,include_attributes=False)
    # Fresh generated functions carry no changed global/vendor implementation.
    assert RelaxedKnownController._admit_tick is CorrectiveController._admit_tick
    assert RelaxedKnownController._state_key is CorrectiveController._state_key
    assert RelaxedKnownController._policy_resource_guard is CorrectiveController._policy_resource_guard
    assert RelaxedKnownController.__mro__[1] is CorrectiveController
    assert 'relaxed_known=False' in inspect.getsource(admission_core)


def test_b0_b2_and_default_strict_selector_unchanged(monkeypatch):
    from v43_corrective.binding import CorrectiveBinding
    import v43_corrective.binding as binding
    monkeypatch.setattr(binding,'ArmBinding',lambda *a:object())
    for arm in ('B0','B1','B2','B3'):
        assert select_controller(arm) is CorrectiveController
        assert CorrectiveBinding(arm).known_window_policy is None
    assert CorrectiveBinding('B1',known_window_policy=POLICY_ID).controller_class is RelaxedKnownController
    for arm in ('B0','B2','B3'):
        with pytest.raises(ValueError,match='EXPLICIT_B1'):CorrectiveBinding(arm,known_window_policy=POLICY_ID)


def test_snapshot_marks_research_and_strict_carry_cannot_enter():
    c,r=make(start=0.);submit(c,r)
    assert c.snapshot(0.)['Known_research_assumption']['status']=='IMPLEMENTED_NOT_EXECUTED'
    snap=c.snapshot(0.);snap.pop('Known_research_assumption')
    with pytest.raises(ValueError,match='CARRYOUT_POLICY_MISMATCH'):c.restore(snap)


def test_known_migration_adapter_preserves_original_metadata_and_physical_guard(monkeypatch):
    import v43_corrective.known_window as module
    observed=[]
    def guard(m,*a,**kw):
        observed.append(deepcopy(m));return None,'WAN_CAPACITY_TEST_REJECT'
    monkeypatch.setattr(module,'migration_guard',guard)
    c,r=make(start=0.,deadline=1.,migration=True);submit(c,r)
    assert c.admit(0.)==[r.uid]
    commands=deepcopy(c.known_schedule)
    c.metadata[r.uid]['accumulated_compute_seconds']=1800.
    assert c.migration(r.uid,900.,450.) is None
    assert len(observed)==1 and observed[0]['completion_deadline_seconds'] is None
    assert c.metadata[r.uid]['completion_deadline_seconds']==1.
    assert c.events[-1]['reason']=='WAN_CAPACITY_TEST_REJECT'
    assert c.known_schedule==commands and not c.migrations


def test_actual_gpu_double_start_prevented_in_same_tick():
    c,r=make(start=0.);submit(c,r)
    u=request('ZZ_UNKNOWN',site='A',compatible=('A',));submit(c,u)
    assert c.admit(0.)==[r.uid]
    assert c.ledger.physical(0.)['A']==1
    assert c.metadata[u.uid]['state']=='PENDING'


def test_research_receipt_digest_matches_original_export():
    c,r=make();submit(c,r)
    row=next(e for e in c.events if e['event']=='KNOWN_RESEARCH_WINDOW_ASSUMPTION')
    assert row['original_receipt_sha']==c.qos.export_ledger()[r.uid]['receipt_sha']


def test_c1_unknown_presite_start_and_hash_identical_in_both_controllers():
    from test_v43_corrective import participant_uid
    results=[]
    for cls in (CorrectiveController,RelaxedKnownController):
        c,_=make(cls=cls)
        uid=participant_uid();u=request(uid,site='A');submit(c,u)
        assert c.reservations.reserve('PEER',[dict(resource='gpu:A',begin=0.,end=900.,quantity=1)])[0]
        assert c.admit(0.)==[uid]
        assert c.audit[uid]['site']=='B' and c.audit[uid]['policy_action']=='PREPLACE'
        results.append((c.audit[uid],c.participation.receipts,c.qos.export_ledger(),c.events))
    assert results[0]==results[1]


def test_strict_deadline_guard_remains_blocking_with_original_member_start():
    c,r=make(cls=CorrectiveController,start=0.,latest=0.,deadline=1.);submit(c,r)
    assert c.admit(0.)==[] and c.metadata[r.uid]['state']=='PENDING'
    assert any(e.get('reason')=='EMPTY_AUTHORIZED_HARD_WINDOW' for e in c.events)


def test_late_observed_known_command_not_permanently_rejected_before_dday():
    from dataclasses import replace
    c,r=make(start=0.)
    r=replace(r,metadata=dict(r.metadata,dday_initialization_seconds=900.));submit(c,r,900.)
    assert c.admit(900.)==[r.uid]
    assert c.audit[r.uid]['plan_start_seconds']==0.


@pytest.mark.parametrize('field',['release_seconds','hard_earliest_start_seconds'])
def test_existing_lower_bound_constraints_remain(field):
    from dataclasses import replace
    c,r=make(start=0.)
    r=replace(r,metadata=dict(r.metadata,**{field:1800.}));submit(c,r)
    assert c.admit(0.)==[] and c.admit(900.)==[]
    assert c.admit(1800.)==[r.uid]
