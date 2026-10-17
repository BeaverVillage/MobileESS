from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import inspect
import numpy as np
import scipy.sparse as sp
import pytest
from v44_recovery_r024a.row_generation import ActiveRows,exact_phi,compile_phase,row_identities
from v44_recovery_r024a.phase_speed import compile_attribution
from v44_recovery_r024a.phase_stability import StableNative
from v42_a_stage_phase1.core import elastic_master,phase_objective,verify_zero,primal_replay
from v42_a_stage_phase1.backend import artificial_point
from v42_a_stage_compact_rowgen.rowgen import restricted,certified_separate
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective


def state(rows=100,local=0,residual=0.):
    rhs=np.full(rows,-residual)
    s=LinearSnapshot(sp.csr_matrix(np.zeros((rows+local,1))),np.zeros(1),np.ones(1),np.full(rows+local,'<'),
        np.r_[rhs,np.ones(local)],np.array(['C']),(Objective('rho',((0,Fraction(1)),),0),)).require()
    return dict(compact=s,reference=s,grows=tuple(range(rows)),n=1,axes={},
        atlas=dict(rf=np.zeros(rows,dtype=int),rf_names=np.array(['test_family'])),prior_compact=np.zeros(1))


def evaluate(manager,active,point=None):
    s=manager.state['compact'];rows=tuple(sorted(active));r=restricted(s,rows);master=elastic_master(r,[j for j,i in enumerate(rows) if i<len(manager.state['grows'])])
    raw=artificial_point(master,np.zeros(s.matrix.shape[1]))[0] if point is None else point
    return manager.evaluate(master,rows,dict(X=raw),lambda m,x:artificial_point(m,x)[0]),master


def test_restricted_zero_does_not_hide_many_sub_tolerance_omitted_residuals(tmp_path):
    st=state(100,residual=5e-7);full=elastic_master(st['compact'],st['grows']);manager=ActiveRows(st,set(),full)
    ev,master=evaluate(manager,set());sep=certified_separate(st['compact'],[0.],set())
    assert sep['PASS'] and ev['restricted_Phi']==0 and ev['Phi']>Fraction(1,100000000)
    assert not ev['zero']['PASS'] and manager.add_rows(sep,ev,tmp_path)
    assert manager.included==set(range(100))


def test_raw_included_artificial_is_never_recomputed_or_clipped():
    st=state(2);full=elastic_master(st['compact'],st['grows']);manager=ActiveRows(st,{0},full)
    ev,_=evaluate(manager,{0},np.array([0.,.125]))
    assert ev['point'].tolist()==[0.,.125,0.] and ev['Phi']==Fraction(1,8)
    assert not ev['zero']['PASS']


def test_adaptive_batches_never_promote_unviolated_rows_at_round_19(tmp_path):
    st=state(1000);manager=ActiveRows(st,set(),elastic_master(st['compact'],st['grows']))
    manager.row_rounds=19
    ev=dict(Phi=Fraction(1),restricted_Phi=Fraction(0),contributions={7:Fraction(1)})
    assert manager.add_rows(dict(violated_rows=[7]),ev,tmp_path)
    assert manager.included=={7}
    assert not manager.add_rows(dict(violated_rows=[7]),ev,tmp_path)


def test_batches_prioritize_scientific_violations_and_positive_contributions(tmp_path):
    st=state(1000);manager=ActiveRows(st,set(),elastic_master(st['compact'],st['grows']));manager.batch=1
    ev=dict(Phi=Fraction(4),restricted_Phi=Fraction(0),contributions={8:Fraction(3),9:Fraction(1)})
    manager.add_rows(dict(violated_rows=[9]),ev,tmp_path)
    assert manager.included=={9}


def test_column_activation_keeps_semantic_global_rows_and_all_new_local_rows(tmp_path):
    old=state(1000,2);full=elastic_master(old['compact'],old['grows']);manager=ActiveRows(old,{7},full)
    new=state(1000,9);new['compact']=replace(new['compact'],matrix=sp.hstack([new['compact'].matrix,sp.csr_matrix((1009,1))],format='csr'),
        lower=np.zeros(2),upper=np.ones(2),vtypes=np.full(2,'C'))
    nf=elastic_master(new['compact'],new['grows']);point=artificial_point(nf,np.zeros(2))[0]
    manager.rebind(new,nf,point,tmp_path)
    assert manager.included=={7}|set(range(1000,1009))
    assert len(manager.included)<new['compact'].matrix.shape[0]


def test_resource_identity_remaps_when_global_rows_reorder(tmp_path):
    old=state(2);old['axes']={('GPU','IDC01',24):0,('GPU','IDC02',24):1}
    manager=ActiveRows(old,{0},elastic_master(old['compact'],old['grows']))
    new=state(2);new['axes']={('GPU','IDC02',24):0,('GPU','IDC01',24):1}
    nf=elastic_master(new['compact'],new['grows'])
    manager.rebind(new,nf,np.zeros(3),tmp_path)
    assert manager.identities[1]==('RESOURCE',('GPU','IDC01',24))


@pytest.mark.parametrize('kind',['rhs','sense','coefficient','family'])
def test_mapping_rejects_changed_original_global_physics(tmp_path,kind):
    old=state(2);manager=ActiveRows(old,{0},elastic_master(old['compact'],old['grows']));new=state(2)
    if kind=='rhs':new['compact']=replace(new['compact'],rhs=np.array([1.,0.]))
    if kind=='sense':new['compact']=replace(new['compact'],senses=np.array(['>','<']))
    if kind=='coefficient':new['compact']=replace(new['compact'],matrix=sp.csr_matrix([[1.],[0.]]))
    if kind=='family':new['atlas']['rf_names']=np.array(['changed'])
    with pytest.raises(ValueError,match='PHYSICS_DRIFT'):manager.rebind(new,elastic_master(new['compact'],new['grows']),np.zeros(3),tmp_path)


def test_prior_seed_reprojects_when_restricted_rows_change():
    st=state(3,residual=.25);full=elastic_master(st['compact'],st['grows']);manager=ActiveRows(st,{0},full)
    evaluate(manager,{0});rows=(0,2);master=elastic_master(restricted(st['compact'],rows),(0,1));native=StableNative(None)
    manager.prepare_native(native,master,rows)
    assert native.seed['X'].tolist()==[0.,.25,.25] and native.seed['Phi']==Fraction(1,2)
    assert primal_replay(master.snapshot,native.seed['X'])['PASS']


def test_sparse_exact_phi_identical_including_negative_zero_and_negative_small_values():
    st=state(100);full=elastic_master(st['compact'],st['grows']);point=np.zeros(101)
    point[2]=.1;point[3]=-.00000000001;point[4]=-0.
    assert exact_phi(full,point)==phase_objective(full,point)


def test_both_full_promotion_branches_removed_and_certified_p1_body_unchanged():
    from v42_a_stage_canary import phase
    fn=compile_phase(phase.run,dict(vars(phase)));original=inspect.getsource(phase.run);changed=inspect.getsource(fn)
    anchor='    # Original P1:'
    assert original[original.index(anchor):]==changed[changed.index(anchor):]
    phase1=changed[:changed.index(anchor)]
    assert 'row_promotion_after' not in phase1
    assert "included=set(range(new['compact'].matrix.shape[0]))" not in phase1
    assert 'certified_separate(s,x,included)' in phase1 and 'inclusion_witness' in phase1
    assert 'PREVIOUS_PHI_INCLUSION_NOT_PRESERVED' in phase1


def test_optimized_attribution_retains_exact_results_and_ranking(tmp_path):
    from v42_a_stage_practical.attribution import analyze
    A=sp.csr_matrix([[2.,0.,-1.],[0.,3.,-1.],[1.,4.,0.]])
    s=LinearSnapshot(A,np.zeros(3),np.full(3,10.),np.array(['=','=','<']),np.array([0.,0.,-1.]),np.full(3,'C'),(Objective('rho',(),0),)).require()
    master=elastic_master(s,(0,1,2));point=artificial_point(master,np.zeros(3))[0]
    keys={('GPU','IDC01',0):0,('RUNTIME','',0):1}
    atlas=dict(rf=np.zeros(3,dtype=int),rf_names=np.array(['test']),resource_variables=np.array([0,1]),domains={'u':SimpleNamespace(stays=[(0,'IDC01')],blocks=[])})
    data=({}, {'u':SimpleNamespace(reference_start=0,reference_site='IDC01',gpu=1,service_slots=1)}, {},SimpleNamespace(capacities={'IDC01':1}),{}, {'u':SimpleNamespace(fixed=None)},None,{'classes':{'class':('u',)}})
    original=analyze(master,dict(X=point),data,keys,{2:'class'},atlas,tmp_path/'old')
    optimized=compile_attribution(analyze)(master,dict(X=point),data,keys,{2:'class'},atlas,tmp_path/'new')
    assert original[0]==optimized[0] and np.array_equal(original[1],optimized[1]) and original[2]==optimized[2]
    assert (tmp_path/'old/RESIDUAL_ROWS.csv').read_bytes()==(tmp_path/'new/RESIDUAL_ROWS.csv').read_bytes()


def test_user_restart_only_exact_interrupted_case_can_exceed_default_attempt_limit():
    from v44_recovery_r024a.operations import needs_retry
    assert needs_retry(Path('D:/c/2025-05-02/B3/attempt004'),dict(error='R024A_MAY02_B3_FRESH_A2_ROWGEN_RESTART'))
    assert not needs_retry(Path('D:/c/2025-05-03/B3/attempt004'),dict(error='R024A_MAY02_B3_FRESH_A2_ROWGEN_RESTART'))


@pytest.mark.parametrize('arm,stage',[('B1','A1'),('B3','A2'),('B1','A2')])
@pytest.mark.parametrize('prior_a2',['missing','RUNNING','FAILED','PASS'])
def test_runtime_routing_never_reads_prior_a2_result(tmp_path,monkeypatch,arm,stage,prior_a2):
    from v44_recovery_r024a import phase_rebuild,row_generation
    from v42_may_campaign_native90 import a_stage
    from v42_a_stage_canary import phase
    from v44 import common
    calls=[]
    original_read=common.read;original_exists=Path.exists
    def exists(path):
        if 'attempt005' in str(path):pytest.fail('pilot status must not be inspected: '+prior_a2)
        return original_exists(path)
    def read(path):
        if 'attempt005' in str(path):pytest.fail('pilot result must not be read: '+prior_a2)
        return original_read(path)
    monkeypatch.setattr(Path,'exists',exists)
    monkeypatch.setattr(common,'read',read)
    from v44_recovery_r024a import adaptive_pricing
    monkeypatch.setattr(adaptive_pricing,'compile_adaptive',lambda function,namespace,controller:function)
    monkeypatch.setattr(row_generation,'compile_phase',lambda function,namespace:calls.append('rowgen_compiled') or (lambda *args:True))
    st=state(3);st['prior_compact']=np.zeros(1)
    with phase_rebuild.stage_scope(dict(root=str(tmp_path),day='2025-05-03',arm=arm,stage=stage)):
        namespace=a_stage.group(phase,('activate','run'))
        assert namespace['run'](None,st,'2025-05-03')
    assert calls==['rowgen_compiled']
