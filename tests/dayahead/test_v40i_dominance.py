from copy import deepcopy
import pytest
from dayahead.v40h.identity import IntegrityError
from dayahead.v40i.dominance import *


def pair():
    identities={k:k for k in IDENTITIES};identities['workload_uids']=['u1']
    b0=dict(date='2025-05-01',identities=identities,stage='Planning',Actual_informed_policy=False,
        reference_candidate_identity='B0-reference',fresh_execution=True,old_reuse_count=0,cache_hit_count=0,
        objective=1.,objective_components={'primary':1.},incumbent_by_semantic={'load':1.})
    b1={**deepcopy(b0),'solver_incumbent':1.,'solver_best_bound':.9,'solver_gap':.1,'termination_reason':'WORK_LIMIT',
        'A1_primary_objective':1.,'MF_primary_objective':1.,'lower_level_objective_degradation':0.,
        'primary_certificate':dict(status='PASS',bound=.9,incumbent=1.),'authorized_candidate_identities':['B0-reference']}
    space={'complete_export':True,'variables':[dict(name='b1_load',semantic='load',lb=0.,ub=2.,type='C')],
        'constraints':[dict(name='capacity',linear=[['b1_load',1]],quadratic=[],sense='<',rhs=2.)],
        'objective':dict(linear=[['b1_load',1]],quadratic=[],constant=0.,sense=1),
        'counts':dict(variables=1,linear=1,quadratic=0,general=0,sos=0)}
    return b0,b1,space


def evaluate_pair(values): return evaluate(*values,objective_tolerance=1e-8,feasibility_tolerance=1e-9)


def test_feasible_b0_and_worse_b1_is_dominance_fail():
    b0,b1,space=pair();b1.update(objective=1.1,objective_components={'primary':1.1},A1_primary_objective=1.1,MF_primary_objective=1.1,
        primary_certificate=dict(status='PASS',bound=.9,incumbent=1.1))
    result=evaluate_pair((b0,b1,space))
    assert result['B0_incumbent_feasible_in_B1']=='YES' and result['status']=='B0_B1_PLANNING_STRUCTURAL_DOMINANCE_FAIL'
    assert not result['production_valid_scientific_result']


def test_dominance_pass_at_tolerance():
    b0,b1,space=pair();b1.update(objective=1+1e-9,objective_components={'primary':1+1e-9})
    assert evaluate_pair((b0,b1,space))['status']=='PASS'


@pytest.mark.parametrize('field',IDENTITIES)
def test_identity_comparison_before_objective(field):
    b0,b1,space=pair();b1['identities'][field]=['different'] if field=='workload_uids' else 'different'
    assert evaluate_pair((b0,b1,space))['status']=='B0_B1_PLANNING_IDENTITY_FAIL'


def test_infeasible_incumbent_reports_direct_constraint_violation():
    b0,b1,space=pair();space['constraints'][0]['rhs']=.5
    result=evaluate_pair((b0,b1,space))
    assert result['status']=='B0_REFERENCE_B1_PLANNING_FEASIBILITY_FAIL'
    assert result['violated_B1_constraints'][0]['constraint']=='capacity'


def test_no_mapping_default_and_no_unexported_constraint():
    b0,b1,space=pair();b0['incumbent_by_semantic']={}
    with pytest.raises(ValueError,match='MAPPING_MISSING'):evaluate_pair((b0,b1,space))
    space['complete_export']=False
    with pytest.raises(IntegrityError,match='COMPLETE_CONSTRAINT'):map_b0_incumbent({},space)


@pytest.mark.parametrize('fault',['old','cache','actual','not_fresh'])
def test_contamination_or_reuse_is_not_valid_planning(fault):
    b0,b1,space=pair()
    if fault=='old':b1['old_reuse_count']=1
    elif fault=='cache':b1['cache_hit_count']=1
    elif fault=='actual':b1['stage']='Actual'
    else:b1['fresh_execution']=False
    assert not evaluate_pair((b0,b1,space))['production_valid_scientific_result']


def test_future_gate_does_not_bypass_current_authorization():
    with pytest.raises(IntegrityError,match='NOT_AUTHORIZED'):
        authorized_future_validation({'B2_B3_AUTHORIZED':'NO'},*pair(),objective_tolerance=1e-8,feasibility_tolerance=1e-9)


def test_real_b1_model_constraint_export_without_optimization():
    import gurobipy as gp
    with gp.Model() as model:
        model.Params.OutputFlag=0
        x=model.addVar(lb=0,ub=2,name='x');b=model.addVar(vtype='B',name='b')
        model.addConstr(x<=1.5,name='linear');model.addQConstr(x*x<=2,name='quadratic')
        model.addGenConstrIndicator(b,True,x<=1,name='indicator');model.update()
        space=export_b1_constraints(model,{'x':'load','b':'flag'})
        mapped=map_b0_incumbent({'load':1.2,'flag':1},space)
        result=direct_feasibility(space,mapped,1e-9)
        assert not result['feasible'] and result['violated_B1_constraints'][0]['constraint']=='indicator'
        assert model.SolCount==0


def test_b0_mapped_objective_must_equal_b0_reported_objective():
    b0,b1,space=pair();space['objective']['constant']=1.
    with pytest.raises(IntegrityError,match='MAPPED_OBJECTIVE_MISMATCH'):evaluate_pair((b0,b1,space))


def actual_pair():
    row={'date':'2025-05-01','identities':{k:k for k in ACTUAL_IDENTITIES},'stage':'Actual','fresh_execution':True,
        'Actual_reoptimization':False,'Actual_informed_policy_selection':False,'Actual_informed_parameter_tuning':False,
        'old_reuse_count':0,'cache_hit_count':0,'GPU_service_conservation_error':0.,'runtime_service_conservation_error':0.}
    row['identities']['workload_uids']=['u1']
    return deepcopy(row),deepcopy(row)


def test_approved_actual_degradation_is_scientific_outcome_not_failure():
    b0,b1=actual_pair();b0['rho']=0.5892357967005808;b1['rho']=0.5895856572902464
    assert actual_replay_identity(b0,b1)['status']=='PASS'
    outcome=actual_outcome(b0,b1)
    assert outcome['delta_B0_minus_B1']==pytest.approx(-0.0003498605896656)
    assert outcome['classification']=='ACTUAL_GENERALIZATION_DEGRADATION_OBSERVED'
    assert not outcome['is_hard_gate'] and not outcome['integrity_failure_due_to_outcome_sign']


@pytest.mark.parametrize('field',ACTUAL_IDENTITIES)
def test_actual_replay_identity_difference_is_hard_failure(field):
    b0,b1=actual_pair();b1['identities'][field]='different'
    assert actual_replay_identity(b0,b1)['status']=='FAIL'


@pytest.mark.parametrize('field',['Actual_reoptimization','Actual_informed_policy_selection','Actual_informed_parameter_tuning'])
def test_actual_holdout_leakage_rejected(field):
    b0,b1=actual_pair();b1[field]=True
    assert actual_replay_identity(b0,b1)['status']=='FAIL'


def test_planning_primary_degradation_and_missing_reference_rejected():
    b0,b1,space=pair();b1['lower_level_objective_degradation']=.01
    with pytest.raises(IntegrityError,match='PRIMARY_DEGRADATION'):evaluate_pair((b0,b1,space))
    b1['lower_level_objective_degradation']=0;b1['authorized_candidate_identities']=[]
    with pytest.raises(IntegrityError,match='REFERENCE_NOT_INCLUDED'):evaluate_pair((b0,b1,space))


def test_current_b1_gpu_pcc_piecewise_constraint_direct_check():
    import gurobipy as gp
    with gp.Model() as model:
        model.Params.OutputFlag=0
        gpu=model.addVar(lb=0,ub=4,vtype='I',name='GPU');pcc=model.addVar(lb=0,ub=40,name='PCC')
        model.addGenConstrPWL(gpu,pcc,[0,2,4],[0,12,32],name='GPU_to_PCC');model.update()
        space=export_b1_constraints(model,{'GPU':'GPU','PCC':'PCC'})
        assert direct_feasibility(space,{'GPU':3,'PCC':22},1e-9)['feasible']
        assert not direct_feasibility(space,{'GPU':3,'PCC':20},1e-9)['feasible']
        with pytest.raises(IntegrityError,match='INCUMBENT_NOT_AVAILABLE'):
            extract_b0_incumbent(model,{'GPU':'GPU','PCC':'PCC'})
        assert model.SolCount==0
