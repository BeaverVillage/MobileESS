from contextlib import nullcontext
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import inspect
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from v44_recovery_r027.integer_repair import fixed_snapshot,compile_run
from v44_recovery_r027.p1_acceleration import structural_key,compile_p1
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective


def snapshot():
    return LinearSnapshot(csr_matrix([[4.,1.]]),np.array([0.,0.]),np.array([2.,10.]),
        np.array(['=']),np.array([8.]),np.array(['I','C']),
        (Objective('rho',((1,Fraction(1)),)),))


def test_fractional_integer_is_fixed_but_continuous_value_is_not_rounded():
    s=snapshot();point=np.array([1.9999996,.0000016])
    fixed,integer,residual=fixed_snapshot(s,point)
    assert fixed.matrix is s.matrix and fixed.rhs is s.rhs
    assert fixed.objectives is s.objectives
    assert fixed.lower[0]==fixed.upper[0]==2
    assert fixed.lower[1]==s.lower[1] and fixed.upper[1]==s.upper[1]
    assert np.array_equal(s.vtypes,['I','C']) and all(fixed.vtypes=='C')
    assert residual>1e-7 and point[1]==.0000016


def test_repair_rejects_materially_fractional_or_out_of_bounds_decisions():
    with pytest.raises(ValueError,match='INTEGER_TOLERANCE'):fixed_snapshot(snapshot(),np.array([1.9,.4]))
    s=replace(snapshot(),upper=np.array([1.9999999,10.]))
    with pytest.raises(ValueError,match='OUTSIDE'):fixed_snapshot(s,np.array([1.9999998,.0000008]))


def test_basis_identity_ignores_only_objective_and_detects_rhs_bounds_and_matrix():
    s=snapshot();key=structural_key(s)
    assert structural_key(replace(s,objectives=(Objective('rho',((0,Fraction(3)),)),)))==key
    assert structural_key(replace(s,rhs=np.array([9.])))!=key
    assert structural_key(replace(s,lower=np.array([.1,0.])))!=key
    assert structural_key(replace(s,matrix=csr_matrix([[4.01,1.]])))!=key


def test_a1_keyword_default_survives_real_voltage_installer_and_restores():
    from v44 import worker
    from v44_recovery_r027.voltage_policy import install
    original=worker.a_stage
    with install():
        fn=inspect.unwrap(worker.a_stage)
        assert inspect.signature(fn).parameters['m1'].default is None
        with patch('v44.planning.scope',lambda day:nullcontext()),patch.dict(fn.__globals__,assert_current=lambda:None):
            # Passing only request must enter the function body, not TypeError.
            with pytest.raises(KeyError):worker.a_stage({'day':'2025-05-03'})
    assert worker.a_stage is original


def test_integer_adapter_retains_complete_a2_routable_source():
    from v42_may_campaign_native90 import a_stage
    from v44.frozen.v43_a2 import adapter
    from v44_recovery_r027.integer_repair import install
    with install():
        source=inspect.getsource(a_stage.run)
        assert '_r027_restore' in source
        ns=dict(a_stage.__dict__)
        fn,changes=adapter.routed_function(a_stage,'run',ns,{})
        assert callable(fn) and '_r027_restore' in fn.__globals__


def test_p1_compiler_preserves_all_original_pricing_and_certification():
    from v42_a_stage_canary import phase
    ns=dict(phase.__dict__);fn=compile_p1(phase.run,ns)
    source=inspect.getsource(fn)
    assert 'max_batch=len(negative)' in source and 'native.admit_p1(s,p1point)' in source
    for required in ('primal_replay','verify_sign_convention','full_pricing','no_negative_omitted_block_certified','P1_RESULT.json'):
        assert source.count(required)==inspect.getsource(phase.run).count(required)


def test_reused_planning_compiles_separate_postsolve_and_preserves_full_validation():
    from v42_may_campaign_native90 import a_stage
    from v44_recovery_r027.planning_reuse import run_reused
    fn=run_reused(compile_run(a_stage.run));source=inspect.getsource(fn)
    assert '_r027_load_state' in source and '_r027_load_point' in source
    assert 'physical.verify(point)' in source and 'acceptance = contract(' in source
    assert "new_Planning_search_Native_calls=0" in source


def test_fixed_integer_repair_solves_continuous_variables_and_replays_original(tmp_path):
    from v44_recovery_r027.integer_repair import restore
    from v44.common import atomic
    class Native:
        incumbent_callback=object();warm_point=object()
        def solve(self,fixed,folder,component):
            assert component=='INTEGER_CONTROL' and self.incumbent_callback is None
            assert fixed.lower[0]==fixed.upper[0]==2
            atomic(folder/'NATIVE_RESULT.json',{'status':2})
            return dict(native_seconds=.1),dict(X=np.array([2.,0.]))
    n=Native();callback=n.incumbent_callback;warm=n.warm_point
    rec,raw=restore(n,snapshot(),np.array([1.9999996,.0000016]),tmp_path/'repair')
    assert np.array_equal(raw['X'],[2.,0.]) and rec['native_seconds']==.1
    assert n.incumbent_callback is callback and n.warm_point is warm


def test_warm_p1_seed_is_independently_replayed_and_never_reused_across_snapshots():
    from v44_recovery_r027.phase_stability import StableNative
    n=StableNative(object());s=snapshot();n.admit_p1(s,np.array([2.,0.]))
    assert n.p1_seed['replay']['PASS'] and n.seed is None
    with pytest.raises(ValueError,match='NOT_ORIGINAL_FEASIBLE'):n.admit_p1(s,np.array([1.,0.]))


def test_handover_waits_for_worker_and_coordinator_and_natural_result(tmp_path):
    from v44_recovery_r027 import handover
    from v44.common import atomic
    guard=dict(protected_case_root=str(tmp_path),protected_worker={},protected_coordinator={})
    with patch.object(handover,'alive',lambda p:p.get('alive',False)):
        assert not handover.boundary(guard,lease={},workers=[])
        atomic(tmp_path/'RESULT.json',dict(status='COMPLETE'))
        assert not handover.boundary(guard,lease={'alive':True},workers=[])
        assert not handover.boundary(guard,lease={},workers=[{}])
        assert handover.boundary(guard,lease={},workers=[])


def test_user_half_voltage_band_applies_only_to_approved_directions(tmp_path):
    from types import SimpleNamespace
    from v44_recovery_r027.conditional_voltage import ConditionalVoltage,LOWER_DELTA,UPPER_DELTA
    from v44_recovery_r027.voltage_policy import audit,authority
    c=ConditionalVoltage(dict(output=str(tmp_path)));c.nodes=('n.1','n.2','n.3')
    for t in range(96):c.mask['voltage_lower',t,'n.1']={};c.mask['voltage_upper',t,'n.2']={}
    def check(values):
        coeff=[SimpleNamespace(voltage_constant=np.square(values),voltage_matrix=np.zeros((1,3))) for _ in range(96)]
        return audit(coeff,[[0.]]*96,c.nodes,controller=c)
    assert check([.945,1.055,1.])['PASS']
    assert not check([.9449,1.055,1.])['PASS']
    assert not check([.945,1.0551,1.])['PASS']
    assert not check([.945,1.055,.949])['PASS']
    assert authority()['maximum_relaxation_pu']==.005
    assert LOWER_DELTA==Fraction('0.945')**2-Fraction('0.95')**2
    assert UPPER_DELTA==Fraction('1.055')**2-Fraction('1.05')**2


def test_existing_failed_attempt_requires_validated_current_revision_release(tmp_path):
    from v44_recovery_r027 import operations as op
    from v44_recovery_r027.failure_continue import defer
    from v44.common import atomic,record
    case=tmp_path/'2025-05-03/B1/attempt001';ops=tmp_path/'ops';ops.mkdir()
    result=dict(PASS=False,status='FAILED',error="TypeError(\"a_stage() missing 1 required keyword-only argument: 'm1'\")")
    atomic(case/'RESULT.json',result);queue=defer(ops,case,result)
    permit=tmp_path/'permit.json';proof=tmp_path/'validation.json'
    atomic(permit,dict(revision='r027'));atomic(proof,dict(PASS=True))
    with patch.object(op,'OPS',ops),patch.object(op,'PERMIT',permit):
        assert not op.needs_retry(case,result)
        atomic(ops/'R026F1_REPAIR_RELEASES'/queue.name,dict(repair_validation=record(proof),
            failed_queue_receipt=record(queue),execution_permit=record(permit),
            diagnosed_cause_fixed=True,allow_new_attempt=True))
        assert op.needs_retry(case,result)


def test_real_p1_composes_with_rowgen_and_half_voltage_compilers():
    from v42_a_stage_canary import phase
    from v44_recovery_r027.row_generation import compile_phase
    from v44_recovery_r027.conditional_voltage import compile_conditional
    ns=dict(phase.__dict__)
    fn=compile_p1(compile_conditional(compile_phase(phase.run,ns),ns,None),ns)
    body=inspect.getsource(fn)
    assert 'max_batch=len(negative)' in body and 'native.admit_p1(s,p1point)' in body
    assert '_r027_conditional.observe' in body and 'rowgen.evaluate' in body


def test_new_revision_releases_cannot_reach_shared_queue_while_old_worker_runs(tmp_path):
    from v44_recovery_r027 import handover
    with patch.object(handover,'require_boundary',side_effect=PermissionError('running')):
        with pytest.raises(PermissionError):handover.release_repairs(tmp_path,tmp_path/'permit')
    assert not (tmp_path/'R026F1_REPAIR_RELEASES').exists()


def test_new_revision_release_publishes_only_after_all_evidence_is_verified(tmp_path):
    from v44_recovery_r027 import handover
    from v44.common import atomic,record,read
    refs={}
    for k in ('repair_validation','failed_queue_receipt','execution_permit','failed_result'):
        p=tmp_path/(k+'.json');atomic(p,dict(PASS=True));refs[k]=record(p)
    atomic(tmp_path/'R027_PENDING_REPAIR_RELEASES/case.json',refs)
    with patch.object(handover,'require_boundary',return_value=None):
        handover.release_repairs(tmp_path,Path(refs['execution_permit']['path']))
    assert read(tmp_path/'R026F1_REPAIR_RELEASES/case.json')==refs
