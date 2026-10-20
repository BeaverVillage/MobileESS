from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import v44_recovery_r026f1
from v44_recovery_r026f1.voltage_policy import a2_voltage_scope,audit,install,strict_authority_required,require_conditional


def test_only_selected_rows_change_and_global_authority_remains_strict(tmp_path):
    from v42_native import voltage
    from v42_boundary import model
    from v42_exact import validation
    from v42_integrated.contract import physical_authority
    old=dict(voltage._MAPPING)
    with a2_voltage_scope(dict(arm='B3',stage='A2',output=str(tmp_path))) as controller:
        for f in (voltage.voltage_for,model.voltage_for,validation.voltage_for):
            assert (f(voltage.Stage.A2).lower_pu,f(voltage.Stage.A2).upper_pu)==(.95,1.05)
            for stage in (voltage.Stage.A1,voltage.Stage.M1,voltage.Stage.M2,voltage.Stage.ACTUAL):
                assert (f(stage).lower_pu,f(stage).upper_pu)==(.95,1.05)
        with physical_authority():assert voltage.voltage_for(voltage.Stage.A2).lower_pu==.95
        assert controller.bounds(0,1)[0][0]==.9025
        with pytest.raises(PermissionError):strict_authority_required()
    assert voltage._MAPPING==old
    strict_authority_required()


def test_voltage_scope_rejects_any_other_stage():
    with pytest.raises(PermissionError):
        with a2_voltage_scope(dict(arm='B3',stage='M2')):pass


def test_original_grid_validator_uses_only_approved_physical_slot(tmp_path):
    from v42_integrated import contract
    coeff=[]
    for t in range(96):
        coeff.append(SimpleNamespace(voltage_constant=np.array([(.945 if t==0 else 1.)**2]),voltage_matrix=np.zeros((1,1)),
            flow_p_constant=np.empty(0),flow_q_constant=np.empty(0),flow_p_matrix=np.empty((0,1)),flow_q_matrix=np.empty((0,1)),
            branch_limits=np.empty(0),anchor=np.zeros(1),current_matrix=np.empty((1,0)),current_constant=np.empty(0),
            branch_names=[],transformer_ratings=[]))
    original=contract.grid_audit
    assert not original(coeff,[[0.]]*96,1.)['PASS']
    with a2_voltage_scope(dict(arm='B3',stage='A2',output=str(tmp_path))) as c:
        c.nodes=('n.1',);c.mask['voltage_lower',0,'n.1']={}
        assert contract.grid_audit(coeff,[[0.]]*96,1.)['PASS']
        c.mask.clear();c.mask['voltage_lower',1,'n.1']={}
        assert not contract.grid_audit(coeff,[[0.]]*96,1.)['PASS']
    assert contract.grid_audit is original


def make_coeff(values):
    return [SimpleNamespace(voltage_constant=np.square(values),voltage_matrix=np.zeros((1,len(values)))) for _ in range(96)]


def test_report_all_nodes_phases_slots_and_exact_relaxation_cap(tmp_path):
    from v44_recovery_r026f1.conditional_voltage import ConditionalVoltage
    c=ConditionalVoltage(dict(output=str(tmp_path)));c.nodes=('n.1','n.2','n.3')
    for t in range(96):c.mask['voltage_lower',t,'n.1']={};c.mask['voltage_upper',t,'n.2']={}
    report=audit(make_coeff([.94,1.06,1.0]),[[0.]]*96,['n.1','n.2','n.3'],controller=c)
    assert report['PASS'] and not report['strict_PASS']
    assert report['violation_node_phase_slot_count']==192
    assert report['evaluated_node_phase_slots']==288
    assert report['maximum_strict_deviation_pu']==pytest.approx(.01)
    assert report['violations'][0]['phase']=='1' and report['violations'][-1]['slot']==95
    assert not audit(make_coeff([.939]),[[0.]]*96,['n.1'])['PASS']


def test_relaxed_candidate_is_rejected_by_strict_recovery(tmp_path):
    from v44_recovery_r026f1.conditional_voltage import ConditionalVoltage
    c=ConditionalVoltage(dict(output=str(tmp_path)));c.nodes=('n.1',)
    for t in range(96):c.mask['voltage_lower',t,'n.1']={}
    assert audit(make_coeff([.945]),[[0.]]*96,['n.1'],controller=c)['PASS']
    from v44_recovery_r026f1.voltage_policy import STRICT
    assert not audit(make_coeff([.945]),[[0.]]*96,['n.1'],band=STRICT)['PASS']


def test_no_unsigned_conditional_handoff_or_changed_original_strict_gate():
    from v44.stages import require_a2
    old=require_a2
    bad=dict(PASS=False,FULL_feasible=False,day='2025-05-02',arm='B3',stage='A2',finished_UTC='now',
        status='A2_VOLTAGE_RECOVERY_PENDING',A2_STRICT_PASS=False,relaxed_model_PASS=True)
    with pytest.raises(Exception):require_conditional(bad,'2025-05-02')
    with pytest.raises(ValueError):old(bad,'2025-05-02')
    with install():
        from v44.stages import require_a2 as current
        assert current is old


def test_phase_I_native_cap_counts_pricing_but_excludes_P1(tmp_path,monkeypatch):
    from v44_recovery_r026f1.phase_limit import phase_scope,PhaseINativeLimit
    from v42_may_campaign_native90.budget import DateBudget
    calls=[]
    def optimize(self,model,*args,**kwargs):
        calls.append(kwargs['requested_seconds']);self.native_used+=min(1000.,kwargs['requested_seconds'])
    monkeypatch.setattr(DateBudget,'native_optimize',optimize)
    budget=SimpleNamespace(native_used=0.)
    class Native:
        def remaining(self):return 5400.-budget.native_used
        def solve(self,snapshot,folder,component):
            DateBudget.native_optimize(budget,None,component=component,requested_seconds=self.remaining())
            return {},{}
    with phase_scope(Native(),tmp_path) as native:
        native.solve(None,tmp_path,'PHASE_I')
        with pytest.raises(PhaseINativeLimit):native.solve(None,tmp_path,'LOCAL_PRICING')
    assert calls==[1500.,500.] and budget.native_used==1500.
    calls.clear();budget.native_used=0.
    with phase_scope(Native(),tmp_path) as native:
        native.solve(None,tmp_path,'PHASE_I')
        native.solve(None,tmp_path,'ORIGINAL_P1')
    assert calls==[1500.,4400.]


def test_failure_quarantine_is_one_date_arm(tmp_path):
    from v44.common import atomic
    from v44_recovery_r026f1.failure_continue import deferred_dates
    atomic(tmp_path/'R026F1_REPAIR_QUEUE/a.json',dict(day='2025-05-02',arm='B1'))
    assert deferred_dates(tmp_path)=={('2025-05-02','B1')}
