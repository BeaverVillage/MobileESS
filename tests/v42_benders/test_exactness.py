import copy,itertools
import numpy as np
import pytest
import gurobipy as gp
from v42_benders.common import ROOT,read,ORIGINAL_UB,ORIGINAL_LB,THRESHOLD
from v42_benders.canonical import from_model,matrix_audit,lp_audit
from v42_benders.certificates import create,verify,Uncertifiable,weighted,support
from v42_benders.engine import Recourse,solve,relative_gap
from v42_benders.fixtures import build,CASES,near_zero_test

@pytest.fixture
def env():
    e=gp.Env(empty=True);e.setParam('OutputFlag',0);e.start()
    yield e
    e.dispose()

@pytest.mark.parametrize('case',list(CASES))
def test_all_assignment_census_matches_native_and_preserves_feasible_points(case,env):
    rows=[c for c in read('FIXTURE_CUT_PAYLOADS.json') if c['case']==case]
    evidence=next(c for c in read('FIXTURE_EXACTNESS.json')['cases'] if c['case']==case)
    assert evidence['assignments']==128 and evidence['native_canonical_match']
    m=build(env,case);can=from_model(m)
    known=[(np.asarray(c['source_x']),c['record']['recourse_optimum']) for c in rows if c['record']['type']=='optimality']
    feasible={tuple(x) for x,v in known};survivors=set()
    for bits in itertools.product([0.,1.],repeat=7):
        if all(c['record']['type']!='feasibility' or c['record']['intercept']+np.asarray(c['coefficients'])@bits>=-1e-8 for c in rows):survivors.add(bits)
    assert survivors==feasible
    for c in rows:
        cut=dict(record=c['record'],coefficients=np.asarray(c['coefficients']),multipliers=np.asarray(c['multipliers']),source_x=np.asarray(c['source_x']))
        assert verify(can,cut,known)['PASS']
    assert evidence['optimum_match'] and evidence['selected_optimum_equivalence']
    m.dispose()

def test_partition_full_and_B3_are_distinct_complete_axes():
    audit=read('VARIABLE_PARTITION_AUDIT.json')
    assert (audit['full_master'],audit['full_recourse'])==(208312,108431)
    assert (audit['B3_master'],audit['B3_recourse'])==(85744,230999)
    with np.load(ROOT/'docs/v42_mess_exact_benders/PARTITION_AXIS.npz') as z:
        assert np.all(~z['B3_master']|z['full_master'])
        assert len(set(z['names']))==316743
        assert np.count_nonzero(z['full_master']&~z['B3_master'])==122568

def test_fixed_x_recourse_is_LP_and_all_finite_bounds_are_rows(env):
    m=build(env);can=from_model(m);lp=Recourse(can,env)
    assert lp_audit(m,can)['PASS'] and lp.model.NumIntVars==0
    assert lp.model.NumQConstrs==lp.model.NumSOS==lp.model.NumGenConstrs==0
    assert len(can.bound_columns)==np.isfinite(can.lower).sum()+np.isfinite(can.upper).sum()
    assert np.all(np.asarray(lp.model.getAttr('LB'))<=-gp.GRB.INFINITY)
    assert np.all(np.asarray(lp.model.getAttr('UB'))>=gp.GRB.INFINITY)
    lp.close();m.dispose()

def test_signed_equalities_mixed_senses_and_fixed_rhs(env):
    m=build(env);can=from_model(m)
    assert matrix_audit(m,can)['PASS']
    eq=np.asarray(m.getAttr('Sense'))=='='
    assert len(can.source_rows)==m.NumConstrs+eq.sum()
    for j in np.flatnonzero(eq):
        positions=np.flatnonzero(can.source_rows==j)
        assert sorted(can.signs[positions])==[-1.,1.]
    for bits in itertools.product([0.,1.],repeat=7):
        assert np.array_equal(can.rhs(bits),can.b-can.B@bits)
    m.dispose()

@pytest.mark.parametrize('status',[9,12,11,4,17])
def test_nonterminal_or_ambiguous_LP_never_yields_cut(status,env):
    m=build(env);can=from_model(m)
    with pytest.raises(Uncertifiable,match='NO_CUT'):create(can,np.zeros(len(can.b)),np.zeros(7),'feasibility',status)
    m.dispose()

@pytest.mark.parametrize('mutation',['ray_sign','bound_term','B_coefficient','RHS'])
def test_perturbed_certificate_is_rejected_independently(mutation,env):
    c=next(c for c in read('FIXTURE_CUT_PAYLOADS.json') if c['case']=='J' and c['record']['type']=='feasibility')
    cut=copy.deepcopy(dict(record=c['record'],coefficients=np.array(c['coefficients']),multipliers=np.array(c['multipliers']),source_x=np.array(c['source_x'])))
    if mutation=='ray_sign':cut['multipliers']*=-1
    elif mutation=='bound_term':cut['record']['exact_bound_correction']='42'
    elif mutation=='B_coefficient':cut['coefficients'][0]+=1
    else:cut['record']['intercept']+=1
    m=build(env,'J');can=from_model(m)
    with pytest.raises(Uncertifiable):verify(can,cut)
    m.dispose()

def test_finite_bound_essential_and_near_zero_margin(env):
    j=next(c for c in read('FIXTURE_EXACTNESS.json')['cases'] if c['case']=='J')
    assert j['finite_bound_ray_present'] and near_zero_test(env)

def test_removing_required_finite_bound_changes_feasibility(env):
    m=build(env,'J');can=from_model(m);m.setAttr('VType',['C']*m.NumVars)
    for i,value in zip(can.xi,[0.,0.,1.,1.,0.,0.,1.]):
        v=m.getVars()[i];v.LB=value;v.UB=value
    m.optimize();assert m.Status==3
    m.getVarByName('bounded_transformer_aux').UB=gp.GRB.INFINITY
    m.optimize();assert m.Status==2
    m.dispose()

def test_degenerate_dual_alternatives_give_same_valid_lower_cut(env):
    m=build(env,'H');can=from_model(m)
    rows=[c for c in read('FIXTURE_CUT_PAYLOADS.json') if c['case']=='H']
    source=next(c for c in rows if c['record']['type']=='optimality')
    w=np.array(source['multipliers']);changed=w.copy();names=m.getAttr('ConstrName')
    found=False
    for i,name in enumerate(names):
        if name!='line_threshold':continue
        for j,other in enumerate(names):
            if other=='degenerate_duplicate' and (can.A[i]-can.A[j]).nnz==0 and (can.B[i]-can.B[j]).nnz==0 and can.b[i]==can.b[j] and w[i]!=w[j]:
                changed[i],changed[j]=w[j],w[i];found=True;break
        if found:break
    assert found
    x=np.array(source['source_x']);value=source['record']['recourse_optimum']
    c1=create(can,w,x,'optimality',2,recourse_value=value)
    c2=create(can,changed,x,'optimality',2,recourse_value=value)
    known=[(np.array(c['source_x']),c['record']['recourse_optimum']) for c in rows if c['record']['type']=='optimality']
    assert verify(can,c1,known)['PASS'] and verify(can,c2,known)['PASS']
    assert np.array_equal(c1['coefficients'],c2['coefficients'])
    assert c1['record']['dual_ray_hash']!=c2['record']['dual_ray_hash']
    m.dispose()

@pytest.mark.parametrize('failure',['maximization','mask_shape'])
def test_partition_rejects_unsupported_objective_or_axis_shape(failure,env):
    m=build(env)
    if failure=='maximization':
        m.ModelSense=gp.GRB.MAXIMIZE
        with pytest.raises(ValueError,match='MINIMIZATION'):from_model(m)
    else:
        with pytest.raises(ValueError,match='PARTITION'):from_model(m,np.zeros((m.NumVars,1),dtype=bool))
    m.dispose()

def test_exact_executed_source_bytes_survive_post_experiment_interface_changes():
    import gzip,hashlib
    audit=read('EXECUTED_SOURCE_ARCHIVE.json')
    assert audit['PASS'] and len(audit['files'])==4
    for row in audit['files']:
        path=ROOT/'docs/v42_mess_exact_benders/EXECUTED_SOURCE'/(row['source'].replace('/','__')+'.gz')
        assert hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()==row['executed_sha256']

def test_stationarity_residual_or_unbounded_support_rejected(env):
    m=build(env);can=from_model(m)
    with pytest.raises(Uncertifiable,match='STATIONARITY'):create(can,np.ones(len(can.b)),np.zeros(7),'feasibility',3)
    from fractions import Fraction
    with pytest.raises(Uncertifiable,match='UNBOUNDED'):support({0:Fraction(-1)},np.array([0.]),np.array([np.inf]))
    m.dispose()

def test_adversarial_physical_features_survive_partition(env):
    m=build(env);can=from_model(m);names=m.getAttr('ConstrName')
    assert names.count('PCS16')==48
    assert 'terminal_SOC' in names and 'initial_SOC' in names and 'travel_SOC0' in names
    assert names.count('voltage_upper')==names.count('voltage_lower')==2
    assert names.count('transformer_current')==names.count('transformer_kVA')==2
    assert sum('travel' in str(can.names[i]) for i in can.xi)==2
    assert all(str(can.names[i]).startswith(('SOC','Pch','Pdis','Q','rho')) for i in can.yi)
    assert matrix_audit(m,can)['PASS'];m.dispose()

def test_full96_scientific_rows_remain_exact():
    c=read('CANONICAL_MATRIX_VALIDATION.json')
    assert c['PASS'] and c['all96_grid_SOC_rows'] and c['terminal_equalities'] and c['PCS16']
    assert c['robust_voltage']==[.955,1.045]
    assert c['full']['original_rows']==954560 and c['full']['coefficient_difference']==0
    assert c['B3']['original_rows']==954561 and c['B3']['coefficient_difference']==0

def test_actual_solver_matrix_not_only_preconversion_arrays():
    a=read('ACTUAL_SOLVER_RECOURSE_MATRIX_AUDIT.json')
    assert a['PASS'] and a['optimize_calls']==0
    for c in a['checks']:
        assert c['actual_solver_nonzeros']==c['expected_nonzeros']
        assert c['coefficient_difference']==0 and c['RHS_after_fixed_x_exact'] and c['actual_solver_LP']

def test_optimality_dual_sign_and_source_tightness_are_required(env):
    payload=next(c for c in read('FIXTURE_CUT_PAYLOADS.json') if c['case']=='A' and c['record']['type']=='optimality')
    m=build(env);can=from_model(m);w=np.array(payload['multipliers']);x=np.array(payload['source_x'])
    with pytest.raises(Uncertifiable,match='SIGN'):create(can,-w,x,'optimality',2,recourse_value=payload['record']['recourse_optimum'])
    with pytest.raises(Uncertifiable,match='NOT_TIGHT'):create(can,w,x,'optimality',2,recourse_value=payload['record']['recourse_optimum']+1)
    m.dispose()

def test_inherited_643_tests_and_44_check_receipt_remain_bytes():
    c=read('LEGACY_PRESERVATION_AUDIT.json')
    assert c['PASS'] and c['files']==1533 and not c['modified_files']
    assert read('VERIFICATION.json')['inherited_bounded_checks']==44

def test_complete_warm_start_mapping_and_original_validation():
    c=read('WARM_START_MAPPING.json')
    assert c['PASS'] and c['names_bitwise_equal'] and c['columns']==316743
    assert c['independent_validation']['valid_new_UB'] and c['Start_only'] and not c['route_fixing']
    assert c['original_UB']==ORIGINAL_UB

def test_global_gap_not_partial_zero_objective_bound():
    assert abs(relative_gap(ORIGINAL_UB,ORIGINAL_LB)-.03224989640084286)<1e-15
    with pytest.raises(Uncertifiable,match='CONTRADICTION'):relative_gap(.5,.6)
    assert relative_gap(None,.5) is None
    assert read('B3_CERTIFICATE.json')['zero_objective_bound_is_not_rho_LB']

def test_B3_classification_and_canary_gate_are_evidence_based():
    c=read('B3_CERTIFICATE.json');gate=read('FULL_M1_CANARY_AUTHORIZATION.json')
    assert c['master_binaries']==85744 and c['full_domain_binaries']==208312
    if c['classification']=='B3_NEGATIVE_CERTIFIED':assert c['result_status']=='VALIDATED_WITNESS'
    elif c['classification']=='B3_POSITIVE_CERTIFIED':assert c['result_status']=='MASTER_INFEASIBLE'
    else:assert not c['certificate_valid']
    if gate['authorized']:assert c['performance_gate'] and c['progress_beyond_root_bottleneck']

def test_production_P2_lock_and_movement_lex_recourses(env):
    m=build(env);can=from_model(m)
    p1,point,cuts=solve(can,env=env,seconds=30,target_gap=0)
    assert point is not None
    value=float(can.c@point[can.yi]);m.addConstr(m.getVarByName('rho_max')<=value+1e-7,name='P1_lock')
    locked=from_model(m);energy=np.array([0.,0.,0.,.2,4.,0.,0.]);count=np.array([0.,0.,0.,1.,1.,0.,0.])
    p2,z,cuts=solve(locked,env=env,seconds=30,movement=energy,count=count,accepted_p1=value)
    assert p2['P2_complete'] and [l['level'] for l in p2['levels']]==['movement_energy','movement_count']
    assert z is not None and z[list(locked.names).index('rho_max')]<=value+1e-7+1e-7
    m.dispose()

def test_no_new_route_restriction_actual_repair_or_downstream():
    p=read('PREREGISTRATION.json');f=read('FINAL_FLAGS.json')
    assert 'Top-K' in p['forbidden'] and 'Hamming restriction' in p['forbidden'] and 'cut deletion' in p['forbidden']
    assert not p['actual_PQ_repair'] and not f['A2_RUN'] and not f['M2_RUN']
    assert not f['PROBLEM13_FINAL_VALIDATED'] and not f['B0_B1_WORK_TOUCHED']
    assert not f['EXCLUDED_PROBLEMS_NEW_WORK']

def test_no_cut_deletion_and_numeric_status_provenance():
    r=read('B3_DECOMPOSITION_RESULT.json')
    assert r['no_cut_deletion'] and r['sequential']
    for row in r['cut_records']:assert row['recourse_status'] in [2,3] and row['independent_validation']['PASS']
    for row in r['recourse_log']:
        assert 'warnings' in row and row['feasibility_tolerance']==1e-7 and row['optimality_tolerance']==1e-7
