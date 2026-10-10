"""Real Native row readback and original transport, without a campaign solve."""
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from scipy import sparse

from v42_common_mess.planning_policy import POLICY, scope, current, specification, build_case, compare_baseline


def _save(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def _tiny_builder(stage):
    def builder(payload,request,progress):
        import gurobipy as gp
        from v42_native.grid import GridAuthority
        from v42_native.voltage import Stage,voltage_for
        from v42_integrated.matrix import arrays
        from v42_supercompact.formulation import Compact
        from v42_supercompact.presolve import Presolve
        from v42_may_campaign.m_model import _domain_sha,verify_transport
        from v42_m1_hybrid.blocks import matrix_sha
        from v42_pr134_b1.common import digest
        out=Path(request['output']);out.mkdir(parents=True,exist_ok=True)
        selected=Stage.M1 if stage=='B2_M' else Stage(stage)
        band=voltage_for(selected)
        ga=GridAuthority(*['a'*64]*4,band.lower_squared,band.upper_squared,True,stage=selected)
        ga.validate()
        m=gp.Model('VMAX1048_SYNTHETIC_NATIVE_ROWS')
        m.Params.OutputFlag=0
        p=m.addVar(lb=-200,ub=200,name='injection_P[A,0]')
        q=m.addVar(lb=-200,ub=200,name='injection_Q[A,0]')
        mode=m.addVar(vtype='B',name='charge_mode[U,0]')
        soc=m.addVar(lb=0,ub=100,name='SOC[U,0]')
        rho=m.addVar(lb=0,ub=1,obj=1,name='rho_max')
        coeff=SimpleNamespace(slot=0, control_names=['aidc_load_kw[AIDC01]','mess_p_kw[A]','mess_q_kvar[A]'],
            voltage_constant=np.array([1.,1.]),voltage_matrix=np.array([[.001,.001],[.0002,.0003],[.001,.0008]]))
        for n,b in enumerate(coeff.voltage_constant):
            expression=float(b)+.001*10+float(coeff.voltage_matrix[1,n])*p+float(coeff.voltage_matrix[2,n])*q
            m.addConstr(expression>=band.lower_squared,name=f'voltage_lower[0,{n}]')
            m.addConstr(expression<=band.upper_squared,name=f'voltage_upper[0,{n}]')
        m.addConstr(rho>=.2+.0001*p,name='line_thermal_face[0,0,0]')
        m.addConstr(q<=200,name='PCS16[U,A,0,0]')
        m.addConstr(soc>=20,name='SOC_terminal[U]')
        m.addConstr(mode>=0,name='mode_domain[U]')
        m.update();A,d=arrays(m);native_rhs=np.array(m.getAttr('RHS'));m.dispose()
        compact=Compact(A,d,[],{},1)
        presolve=Presolve(compact.A,compact.d);B,e=presolve.run()
        proof=verify_transport(compact,presolve)
        identity=dict(original_matrix_sha=matrix_sha(A),original_domain_sha=_domain_sha(d),
            selected_matrix_sha=matrix_sha(B),selected_domain_sha=_domain_sha(e),transport=proof,
            arm='B2',input_identity={'stage':stage})
        case=SimpleNamespace(A=B,d=e,original_A=A,original_d=d,point=None,compact=compact,presolve=presolve,
            case_sha=digest(identity),identity=identity,coefficients=(coeff,),output=out,
            anchor={'controls':[[10.,0.,0.]]},graph=([],{},[],SimpleNamespace(),{}),
            planning={},bundle={'day':'2025-05-01'},native_FULL_RHS=native_rhs,
            lift=lambda x:compact.inverse(presolve.inverse(x)))
        sparse.save_npz(out/'FULL_A.npz',A);np.savez_compressed(out/'FULL_DATA.npz',**d)
        np.savez_compressed(out/'CURRENT_C2_AXES.npz',columns=presolve.col_ids,rows=presolve.row_ids)
        _save(out/'CURRENT_C2_ALIASES.json',presolve.steps)
        _save(out/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**identity))
        _save(out/'INPUT_AND_SOURCE_IDENTITY.json',dict(case_sha=case.case_sha))
        return case
    return builder


def _strict(case,path,evidence):
    from v42_m1_research.check_ub import vector_sha
    from v42_common_mess.storage import record
    from v42_integrated.matrix import audit
    with np.load(path,allow_pickle=False) as data:
        point=data['point']
    raw=case.lift(point)
    for d,x in ((case.d,point),(case.original_d,raw)):
        assert np.array_equal(x[d['types']!='C'],np.rint(x[d['types']!='C']))
    if not audit(case.original_A,case.original_d,raw,integral=True,tolerance=1e-8)['PASS']:
        raise ValueError('SYNTHETIC_INDEPENDENT_ORIGINAL_FULL_PHYSICAL_REJECTED')
    return dict(PASS=True,exact_Global_UB=str(Fraction(float(raw[-1]))),Global_UB=float(raw[-1]),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        point_file_sha256=record(path)['sha256'],point_vector_sha256=vector_sha(point),
        original_matrix_and_96_slot_physical_replay={'PASS':True,'case_sha':case.case_sha})


def _baseline(root):
    old=_tiny_builder('B2_M')({},dict(output=str(root)),None)
    raw=np.array([0.,(1.1025-1.01)/.001,0.,20.,.2])
    point=old.presolve.forward(old.compact.forward(raw))
    path=root/'BEST_STRICT_UB_POINT.npz';np.savez_compressed(path,point=point)
    _save(root/'BEST_STRICT_UB_CERTIFICATE.json',_strict(old,path,{}))
    return old,point


def test_exact_user_square_and_restored_scope():
    assert specification()['Planning_upper_squared']==1.098304
    assert specification()['Planning_upper_squared']!=1.048**2
    assert current() is None
    with scope(POLICY):
        assert current()['version']==POLICY
    assert current() is None
    with pytest.raises(ValueError,match='UNKNOWN'):
        with scope('unapproved_1047'):
            pass


@pytest.mark.parametrize('stage',['B2_M','M1','M2'])
def test_shared_native_FULL_Compact_C3A_policy_and_baseline_identity(tmp_path,stage):
    from v42_common_mess.model import build
    from v42_may_campaign.m_model import _domain_sha
    old,point=_baseline(tmp_path/'baseline')
    with scope(POLICY,baseline_output=old.output):
        case=build_case(_tiny_builder(stage),{},dict(output=str(tmp_path/'candidate')),stage=stage,strict_validator=_strict)
    policy=case.identity['planning_voltage_policy']
    assert policy['Planning_upper_squared']==1.098304 and policy['Planning_lower_squared']==.9025
    assert old.identity['original_matrix_sha']==case.identity['original_matrix_sha']
    assert old.identity['original_domain_sha']!=case.identity['original_domain_sha']
    assert old.case_sha!=case.case_sha
    assert case.identity['original_domain_sha']==_domain_sha(case.original_d)
    receipt=json.loads((case.output/'VMAX1048_MODEL_POLICY_AUDIT.json').read_text())
    comparison=receipt['audit']['baseline_comparison']
    assert receipt['audit']['upper_rows']==receipt['audit']['lower_rows']==2
    assert comparison['all_non_voltage_upper_RHS_byte_equal']
    assert comparison['MESS_integer_and_continuous_decision_domain_byte_equal']
    assert comparison['old_strict_point_rejected_under_new_FULL']
    assert comparison['independent_new_case_strict_replay']['PASS'] is False
    assert comparison['old_strict_point_under_new_FULL_max_voltage_upper_violation_squared_pu']==pytest.approx(.004196)
    assert np.array_equal(case.original_d['rhs'],case.native_FULL_RHS)
    output=tmp_path/'NativeReadback';output.mkdir()
    model,variables,identity=build(case,output)
    try:
        assert identity['checks']['original_RHS_exact']
        assert identity['checks']['original_source_rows_exact']
        assert np.array_equal(np.array(model.getAttr('RHS')),case.d['rhs'])
        assert all(identity['checks'].values())
    finally:
        model.dispose()
    # The old vector still exists unchanged and is independently rejected by
    # the same common engine admission gate; it never becomes a MIP start.
    from v42_common_mess.engine import _validate
    from v42_common_mess.budget import StageBudget
    budget=SimpleNamespace(used=lambda:0.,cost=lambda *a,**k:nullcontext(),calls=[])
    assert _validate(case,point,case.output/'OLD_POINT_ENGINE_ADMISSION.npz',_strict,StageBudget(budget),'new_case') is None


@pytest.mark.parametrize('stage',['B2_M','M1','M2'])
def test_A1_A2_and_Actual_stay_original_even_during_M_scope(stage):
    from v42_native.voltage import Stage,voltage_for
    from v42_common_mess.planning_policy import _construction_scope
    with scope(POLICY),_construction_scope(stage):
        import v42_native.voltage as voltage
        assert voltage.voltage_for(Stage.A1).upper_squared==1.1025
        assert voltage.voltage_for(Stage.A2).upper_squared==1.1025
        assert voltage.voltage_for(Stage.ACTUAL).upper_squared==1.1025
        assert voltage.voltage_for(Stage.M1 if stage=='B2_M' else Stage(stage)).upper_squared==1.098304
    assert voltage_for(Stage.M1).upper_squared==1.1025


def test_A_and_Actual_builder_calls_cannot_activate_policy(tmp_path):
    for stage in ('A1','A2','Actual'):
        with scope(POLICY),pytest.raises(ValueError,match='CANNOT_CHANGE_A_OR_ACTUAL'):
            build_case(lambda *a:pytest.fail('builder should not execute'),{},dict(output=str(tmp_path)),stage=stage)


def test_default_build_is_identical_and_does_not_tag_new_policy(tmp_path):
    case=build_case(_tiny_builder('B2_M'),{},dict(output=str(tmp_path)),stage='B2_M')
    assert 'planning_voltage_policy' not in case.identity
    assert not (tmp_path/'VMAX1048_MODEL_POLICY_AUDIT.json').exists()


def test_baseline_difference_guard_rejects_non_voltage_scientific_change(tmp_path):
    old,_=_baseline(tmp_path/'baseline')
    with scope(POLICY):
        case=build_case(_tiny_builder('B2_M'),{},dict(output=str(tmp_path/'candidate')),stage='B2_M')
    index=list(case.original_d['row_names']).index('SOC_terminal[U]')
    case.original_d['rhs'][index]+=.1
    with pytest.raises(ValueError,match='ONLY_UPPER_RHS'):
        compare_baseline(case,old.output,strict_validator=_strict)


def test_policy_readback_rejects_pu_limit_used_as_squared_rhs(tmp_path):
    builder=_tiny_builder('B2_M')
    def broken(*args):
        case=builder(*args)
        mask=np.array([str(n).startswith('voltage_upper[') for n in case.original_d['row_names']])
        case.original_d['rhs'][mask] += 1.048-1.098304
        return case
    with scope(POLICY),pytest.raises(ValueError,match='READBACK_DRIFT'):
        build_case(broken,{},dict(output=str(tmp_path)),stage='B2_M')


def _diagnostic():
    version='V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1'
    request=dict(algorithm_version=version,planning_policy=POLICY,planning_voltage_max_pu=1.048,actual_voltage_max_pu=1.05)
    manifest=dict(schema='V42_VMAX1048_DIAGNOSTIC_MANIFEST_V1',algorithm_version=version,
        planning_policy=POLICY,planning_voltage_min_pu=.95,planning_voltage_max_pu=1.048,
        planning_voltage_max_squared_pu=1.098304,actual_voltage_min_pu=.95,actual_voltage_max_pu=1.05,
        native_M_limit_seconds=1800,Threads=1,P2_calls=0,diagnostic_only=True,
        all31_policy_conversion_approved=False,A1_A2_policy_changed=False)
    return request,manifest


def test_explicit_diagnostic_build_budget_with_normal_and_legacy_preserved():
    from v42_b2_build_authority_v13.builder import admitted_native_limit
    request,manifest=_diagnostic()
    assert admitted_native_limit(request,manifest)==1800
    assert admitted_native_limit(request,dict(schema='V42_COMMON_U4_QUALIFICATION_V1',
        algorithm_version=request['algorithm_version'],native_M_limit_seconds=1800))==1800
    assert admitted_native_limit({})==5400


@pytest.mark.parametrize('key,value',[
    ('planning_policy','other'),('planning_voltage_min_pu',.94),('planning_voltage_max_pu',1.05),
    ('planning_voltage_max_squared_pu',1.048),('planning_voltage_max_squared_pu',1.048**2),
    ('actual_voltage_max_pu',1.048),('actual_voltage_min_pu',.94),('native_M_limit_seconds',1801),
    ('Threads',True),('P2_calls',False),('diagnostic_only',False),
    ('all31_policy_conversion_approved',True),('A1_A2_policy_changed',True)])
def test_diagnostic_admission_rejects_contract_drift(key,value):
    from v42_b2_build_authority_v13.builder import admitted_native_limit
    request,manifest=_diagnostic();manifest[key]=value
    with pytest.raises(ValueError,match='EXPLICIT_DIAGNOSTIC'):
        admitted_native_limit(request,manifest)
