"""Offline boundary/contract tests; these fixtures never run a solver."""
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path
from fractions import Fraction
import numpy as np
import pytest
from v44_recovery_r025a import bounded_a_stage as policy


class Budget:
    def __init__(self,path=None,native_limit=5400.,**kw):self.native_limit=native_limit;self.native_used=0.
    def used(self):return self.native_used
    def remaining(self,reserve=None):return max(0.,self.native_limit-self.native_used)
    def persist(self):pass
    def cost(self,*a,**kw):return nullcontext()
    def wall(self):return 12.


def test_phase_window_counts_all_native_and_opens_original_total_after_cutoff(monkeypatch,tmp_path):
    from v44 import common
    monkeypatch.setattr(common,'read',lambda _:{});monkeypatch.setattr(common,'atomic',lambda *a:None)
    b=policy.budget_type(Budget,{})(tmp_path/'ledger');c=policy.Controller(b,tmp_path)
    assert b.native_limit==3600
    b.native_used=399.;assert b.remaining()==1.
    b.native_used=400.;assert b.remaining()==0.
    with pytest.raises(policy.PhaseDeadline):c.checkpoint({'physical':'unchanged'})
    assert c.state=={'physical':'unchanged'}
    c.start_p1(c.state);assert b.remaining()==3200.
    b.native_used=3600.;assert b.remaining()==0.


def test_timed_nonoptimal_phase_result_is_not_misclassified_as_numerical_failure(tmp_path):
    b=Budget();c=policy.Controller(b,tmp_path)
    class Native:
        def remaining(self):return 1.
        def solve(self,*a):b.native_used=400.;return {'status':9},{'X':[1.]}
    n=policy.BoundedNative(Native(),c)
    with pytest.raises(policy.PhaseDeadline,match='DURING_NATIVE'):n.solve(None,tmp_path,'LOCAL_PRICING')
    c.phase=False
    assert n.solve(None,tmp_path,'INTEGER_CONTROL')[0]['status']==9


@pytest.mark.parametrize('physical_valid',[True,False])
def test_phase_cutoff_runs_original_integer_model_and_only_freezes_verified_ub(monkeypatch,tmp_path,physical_valid):
    from v44.common import atomic,read
    import v42_a_stage_practical.integer_model as integer
    import v42_a_stage_phase1.core as core
    import v42_a_stage_lexfull.runner as objective
    import v42_a_stage_acceptance.schedule_audit as audit
    output=tmp_path/'OUTPUT';output.mkdir();(output/'STATIC').mkdir()
    source=output/'SOURCE.json';atomic(source,{'fixture':True})
    typed=SimpleNamespace(vtypes=np.array(['I']),objectives=[SimpleNamespace(name='rho')])
    state={'_campaign':{'input_receipts':{}},'data':(None,{'job':object()},None,None,None,None,None,{'classes':{'c':['job']}}),'global_types':None}
    budget=Budget();budget.native_used=400.;calls=[]
    verification={'PASS':physical_valid,'selected_jobs':{},'controls':[],'globals':{},'physical':{'P1_rho':2.}}
    class Physical:
        def __init__(self,*a):pass
        def verify(self,point):return dict(verification)
    class Native:
        def __init__(self):self.calls=[];self.freeze_path=source;self.live_model=None
        def remaining(self):return 3200.
        def solve(self,snapshot,folder,component):
            assert component=='INTEGER_CONTROL' and snapshot is typed
            calls.append(component);self.incumbent_callback(np.array([1.]),2.)
            budget.native_used=3600.;return {'status':9,'objective':2.},{'X':np.array([1.])}
    monkeypatch.setattr(integer,'restore_types',lambda *a:(typed,{'PASS':True}))
    monkeypatch.setattr(core,'primal_replay',lambda *a:{'PASS':True})
    monkeypatch.setattr(objective,'objective_value',lambda *a:Fraction(2))
    monkeypatch.setattr(audit,'original_schedule_metrics',lambda *a:({},{}))
    planning=output/'PLAN.npz'
    def materialize(*a):np.savez(planning,fixture=[1]);from v44.common import record;return record(planning)
    ns={'_paths':lambda r:('2025-05-03',tmp_path,output),'prepare':lambda *a:state,
        '_native':lambda *a:Native(),'rebound':lambda f,ns:f,'group':lambda *a,**k:{'targeted':None,'run':None},
        'DayDirectory':lambda *a:None,'_physical':lambda *a:(Physical,{}),'_planning':materialize,
        'dated_acceptance':lambda *a:None,'_notify':lambda *a,**kw:None}
    result=policy.run({'arm':'B1','stage':'A1'},budget,None,ns)
    assert calls==['INTEGER_CONTROL']
    assert result['Phase_I_skipped'] and result['P1_skipped']
    assert result['native_seconds']==3600
    if physical_valid:assert result['LB'] is None
    else:assert result['PASS'] is False
    if physical_valid:
        assert result['PASS'] and result['FULL_feasible'] and result['allow_downstream']
        assert result['UB']==2 and result['certified_gap'] is None and not result['independent_Global_LB_validated']
        assert not result['global_gap_certified']
        freeze=read(result['freeze']['path']);assert freeze['UB_feasible_only'] and not freeze['A1_P1_ONLY_ACCEPTED']
        from v44_recovery_r025a.ub_downstream import verify_ub
        assert verify_ub(dict(result,day='2025-05-03'))['PASS']
    else:
        assert not result['allow_downstream'] and not (output/'B1_UB_FREEZE.json').exists()
    assert not (output/'PHASE_I_ZERO_CERTIFICATE.json').exists()
    assert not (output/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json').exists()


def test_export_and_worker_compilers_preserve_null_lb_and_gap():
    from v44 import worker,daily
    from v44_recovery_r025a.ub_downstream import worker_function,export_a
    import inspect
    assert inspect.unwrap(worker_function(worker.a_stage)).__globals__ is inspect.unwrap(worker.a_stage).__globals__
    assert callable(export_a(daily.export_a))


def test_scoped_a2_binding_uses_same_fixed_m1_physical_functions(monkeypatch):
    from v44.frozen.v43_a2 import adapter
    from v42_may_campaign_native90 import a_stage
    # Compilation only: no model construction and no Native calls.
    ns=dict(a_stage.__dict__)
    with policy.install():
        fn,changes=adapter.routed_function(a_stage,'run',ns,{})
        assert fn is ns['run'] and changes['labels']>0
        assert fn.__closure__ is not None


def test_ub_export_reaches_a2_parent_gate_without_gap_or_mutable_result_hash(tmp_path):
    from v44.common import atomic,record,read
    from v44.daily import export_a
    from v44.stages import require_a2
    from v44_recovery_r025a.ub_downstream import export_a as adapt_export,require_a2 as adapt_require
    root=tmp_path/'A2';root.mkdir();out=root/'OUTPUT';out.mkdir()
    point=out/'POINT.npz';np.savez(point,X=[1.])
    physical=out/'PHYSICAL.json';atomic(physical,dict(PASS=True,original_integer_types_restored=True,
        original_job_population_verified=True,scientific_primal_replay={'PASS':True},integral_max_residual=0.))
    inputs=tmp_path/'INPUTS';inputs.mkdir();atomic(inputs/'NATIVE_INPUT.json',{'reference':{'fixture':True}});atomic(inputs/'WINDOWS.json',[])
    plan=out/'PLAN.npz';np.savez(plan,sites=['AIDC01'],known_GPU=np.zeros((96,1)),GPU=np.ones((96,1)),
        PCC_P_kw=np.ones((96,1)),PCC_Q_kvar=np.ones((96,1)))
    freeze=out/'FREEZE.json';atomic(freeze,dict(PASS=True,accepted=True,policy='R025A_NATIVE60_PHASE400_UB',
        UB_feasible_only=True,global_gap_certified=False,arm='B3',stage='A2',day='2025-05-03',
        selected_jobs={},globals={},physical=record(physical),validated_original_integer_point=record(point),
        planning=record(plan),fixed_M1_plan_sha='fixed_plan',scientific_input={
            'NATIVE_INPUT.json':record(inputs/'NATIVE_INPUT.json'),'WINDOWS.json':record(inputs/'WINDOWS.json')}))
    result=dict(PASS=True,FULL_feasible=True,allow_downstream=True,UB_feasible_only=True,policy='R025A_NATIVE60_PHASE400_UB',
        arm='B3',stage='A2',day='2025-05-03',P2_calls=0,finished_UTC='fixture',freeze=record(freeze),planning=record(plan),
        independent_Global_LB_validated=False,certified_gap=None,UB=2.,LB=None,fixed_M1_plan_sha='fixed_plan')
    request=dict(root=str(root),day='2025-05-03',sources=[],source_sha='fixture',input_folder=str(inputs),M1_result={'fixture':True})
    folder=adapt_export(export_a)(result,request,root/'AIDC_FROZEN','A2')
    identity=read(folder/'AIDC_REFERENCE.json')['identity']
    atomic(root/'RESULT.json',dict(result,AIDC_reference=record(folder/'AIDC_REFERENCE.json')))
    assert adapt_require(require_a2)(identity,'2025-05-03') is identity
    assert identity['certified_gap'] is None and identity['global_gap'] is None
    assert not identity['independent_Global_LB_validated']
    identity['fixed_M1_plan_sha']='wrong'
    with pytest.raises(ValueError,match='M1_BINDING'):adapt_require(require_a2)(identity,'2025-05-03')
