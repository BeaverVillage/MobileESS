import json
import numpy as np
import gurobipy as gp
import pytest
from dayahead.v41r1.early_stop import FamilySweep,FAMILIES,material_improvement,objective_floor
from dayahead.v41r1.bounded_solver import BoundedLex,PolicyBudget


def complete_sweep(state, used):
    seen=[]
    for _ in FAMILIES:
        seen.append(state.family);used+=state.family_seconds+1e-6
        state.observe(used,False)
    assert tuple(seen)==state.order and set(seen)==set(FAMILIES)
    return used


@pytest.mark.parametrize('priority',range(4))
def test_one_stagnant_normal_then_exactly_one_diversification(priority):
    s=FamilySweep(priority,0)
    used=complete_sweep(s,0)
    assert s.mode=='DIVERSIFICATION' and s.normal_completed==1 and not s.reason
    complete_sweep(s,used)
    assert s.reason=='FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT'
    assert s.diversification_started==s.diversification_completed==1
    assert s.metrics()['stage_family_coverage_fraction']==1
    assert not s.metrics()['raw_candidate_coverage_required_for_stopping']


def test_p5_stays_inside_optimization_but_never_repeats_proof_sweeps():
    s=FamilySweep(4,0);complete_sweep(s,0)
    assert s.reason=='NORMAL_FAMILY_SWEEP_NO_IMPROVEMENT' and s.diversification_started==0


@pytest.mark.parametrize('during_diversification',[False,True])
def test_material_improvement_restarts_structure_and_normal_sweep(during_diversification):
    s=FamilySweep(0,0);used=complete_sweep(s,0) if during_diversification else 0
    assert s.observe(used+1,True)
    assert s.mode=='NORMAL' and s.family==FAMILIES[0] and s.material_improvements==1
    assert not s.reason and not s.families
    used=complete_sweep(s,used+1);complete_sweep(s,used)
    assert s.reason=='FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT'


@pytest.mark.parametrize('noise',[0.,1e-12,1e-10])
def test_numerical_noise_and_lower_priority_improvements_do_not_reset_p1(noise):
    before=[.5383475197373216,1604.,0.,0.,100.]
    after=[before[0]-noise,1600.,0.,0.,90.]
    assert not material_improvement(before,after,0,True)
    assert material_improvement(before,after,1,True)
    assert not material_improvement(before,after,1,False)


@pytest.mark.parametrize('priority',[1,2,3])
def test_floor_is_conditional_and_requires_exact_zero_of_verified_original_objective(priority):
    v=[.5,0.,0.,0.,10.]
    proof=objective_floor(priority,v,production_verified=True)
    assert proof['bound']==0 and not proof['joint_lexicographic_global_certificate']
    assert objective_floor(priority,v,production_verified=False) is None
    v[priority]=1e-10
    assert objective_floor(priority,v,production_verified=True) is None


def test_no_assumed_global_p1_bound_or_p5_floor():
    for p in (0,4):assert objective_floor(p,[0.]*5,production_verified=True) is None


def test_early_stop_before_raw_coverage_and_complete_domain_overlap(tmp_path):
    # Thousands of options cannot fit in ten small neighborhoods. This is
    # nevertheless two genuine five-family sweeps; unseen options persist.
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4
    for g in range(1000):
        vs=[m.addVar(vtype=gp.GRB.BINARY,name=f'choice[{g},{i}]') for i in range(2)]
        m.addConstr(sum(vs)==1)
    m.setObjective(0.);m.update();seed=np.tile([1.,0.],1000)
    engine=BoundedLex(m,seed,tmp_path,PolicyBudget(5),allocation=[1],
        metadata={g:dict(candidate_count=2,members=[str(g)],can_migrate=True,can_relocate=True) for g in range(1000)})
    engine.target_free=4
    # Keep size fixed to observe overlap and partial raw coverage; the actual
    # model optimizer, seed starts, audits and checkpoints all run normally.
    original=engine._solve
    def fixed_size(seconds,label):
        candidate,data=original(seconds,label);data['runtime_seconds']=data['solver_runtime_seconds']=11.
        return candidate,data
    engine._solve=fixed_size
    result=engine.optimize('P1')
    assert result['termination_reason']=='FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT'
    assert result['stage_family_coverage_fraction']==1
    assert result['STAGE_COVERAGE_FRACTION']<1
    assert result['diversification_sweeps_completed']==1
    assert engine.budget.remaining>0 and result['material_improvements']==0
    coverage=engine.coverage()
    assert coverage['scientific_candidate_pruning']==0 and coverage['unvisited_reason']=='NOT_VISITED_WITHIN_COMPUTE_BUDGET'
    proofs=[json.loads(p.read_text()) for p in (tmp_path/'bounded_checkpoints').glob('ITERATION_*.json')]
    overlap=[p for p in proofs if p['sweep_mode']=='DIVERSIFICATION']
    assert overlap and all(p['neighborhood']['overlap_groups'] for p in overlap)
    assert all(p['free_discrete_variable_count']==2*len(p['free_cohorts']) for p in proofs)
    assert all(v.LB==0 and v.UB==1 for v in m.getVars())
    m.dispose()


def test_guard_is_distinct_from_sweep_convergence():
    s=FamilySweep(0,0);s.observe(1.,False);s.finish(2.,'STAGE_SOFT_GUARD_REACHED')
    assert s.normal_completed==s.diversification_started==0
    assert s.reason=='STAGE_SOFT_GUARD_REACHED'


@pytest.mark.parametrize('family_remaining',[0.,.1,1.,3.,10.])
def test_family_deadline_never_preempts_verified_full_model_seed_processing(family_remaining):
    from dayahead.v41r1.early_stop import neighborhood_time_limit
    assert neighborhood_time_limit(100.,family_remaining,10.,5.)>=5.
    assert neighborhood_time_limit(14.9,family_remaining,10.,5.)==0.
    assert neighborhood_time_limit(15.,family_remaining,10.,5.)==5.


def test_migration_and_relocation_priorities_start_with_relevant_family():
    assert FamilySweep(2,0).family=='RUNNING_MIGRATION_BLOCK'
    assert FamilySweep(3,0).family=='PENDING_RELOCATION_BLOCK'



def test_family_overrun_is_absorbed_by_next_slice_not_repeated_five_times():
    state=FamilySweep(0,0)
    state.observe(90.,False)
    assert state.family_index==1 and state.family_deadline==168.
    state.observe(175.,False)
    assert state.family_index==2 and state.family_deadline==252.


def test_monitor_lock_retry_preserves_original_canonical_bytes(tmp_path,monkeypatch):
    import dayahead.v41r1.early_stop as control
    from dayahead.paper_analysis.storage import canonical
    original=control._canonical_write_json;calls=[]
    def transient(path,value):
        calls.append(1)
        if len(calls)<3:raise PermissionError('reader sharing lock')
        original(path,value)
    monkeypatch.setattr(control,'_canonical_write_json',transient)
    monkeypatch.setattr(control.time,'sleep',lambda seconds:None)
    value={'objective':.5383475197373216,'hard_feasibility':True}
    path=tmp_path/'F_AND_O_LIVE.json'
    assert control.write_compute_json(path,value) and len(calls)==3
    assert path.read_bytes()==canonical(value)


def test_ui_lock_cannot_discard_incumbent_but_required_receipt_fails_closed(tmp_path,monkeypatch):
    import dayahead.v41r1.early_stop as control
    def locked(*args):raise PermissionError('persistent lock')
    monkeypatch.setattr(control,'_canonical_write_json',locked)
    monkeypatch.setattr(control.time,'sleep',lambda seconds:None)
    assert control.write_compute_json(tmp_path/'F_AND_O_LIVE.json',{'incumbent':'retained'}) is False
    with pytest.raises(PermissionError):control.write_compute_json(tmp_path/'STAGE_ACCEPTED.json',{'status':'PASS'})
