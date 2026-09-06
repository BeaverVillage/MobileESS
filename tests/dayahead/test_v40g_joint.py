from types import SimpleNamespace
from dataclasses import replace
import numpy as np
import pytest
from tests.dayahead.test_v40f_min_rho import setup
from dayahead.v40g.optimizer import solve
from dayahead.v40g.domain import options, deviation, materialize, audit


class Wan:
    historical=SimpleNamespace(maximum_active_transfers=1)
    def payload_bytes(self,gpu):return gpu*10
    def path_capacity_bytes(self,s,d,t):return 100
    def path(self,s,d):return ('fixed',)
    def path_id(self,s,d):return s+'_'+d
    def capacity_bytes(self,link,t):return 100


def test_spatial_primary_not_temporal_fallback(tmp_path):
    ctx,row=setup();r=solve([row],np.array([[1.,0.]]),ctx,tmp_path)
    assert r['jobs'][0]['AIDC_site']=='AIDC02'
    assert r['secondary_migration_optimum']==0
    assert r['tertiary_reference_deviation_optimum']==2
    assert r['grid']['rho_max']<=r['primary_optimum']+1.1e-8


def test_equivalent_primary_selects_exact_reference(tmp_path):
    ctx,row=setup(True);r=solve([row],np.array([[1.,0.]]),ctx,tmp_path)
    assert r['jobs']==[row] and r['tertiary_reference_deviation_optimum']==0


def test_migration_primary_beats_feasible_temporal_only(tmp_path):
    ctx,row=setup();row={**row,'state_at_issue':'RUNNING','start_slot':0,'end_slot':29,'safe_duration_slots':29,'safe_duration_seconds':26100.}
    c=ctx.coefficients[0]
    # A late stress peak rewards moving the residual; source service before
    # the checkpoint remains physically present and exactly conserved.
    ctx.coefficients=tuple(replace(c,slot=t,current_constant=np.array([.1 if t==4 else .01,.01])) for t in range(6))
    ctx.tables={s:np.tile([[0.,1.,2.]],(6,1)) for s in ctx.capacity.aidc_ids}
    ctx.wan=Wan();ctx.elapsed={'one':900.}
    p=np.array([[1.,0.]]*5+[[0.,0.]])
    joint=solve([row],p,ctx,tmp_path/'joint')
    temporal=solve([row],p,ctx,tmp_path/'temporal',temporal_only=True)
    assert joint['secondary_migration_optimum']==1
    assert joint['primary_optimum']<temporal['primary_optimum']
    assert joint['terminal_audit']['common_service_compute_GPU_slots_preserved']
    assert joint['jobs'][0]['compute_segments'][0]['site']=='AIDC01'


def test_tail_running_cannot_break_terminal_state():
    ctx,row=setup();row={**row,'state_at_issue':'RUNNING','start_slot':0,'end_slot':125,'safe_duration_slots':125,'safe_duration_seconds':112500.}
    assert len(options(row,ctx.capacity,Wan(),{'one':0.}))==1


def test_segmented_metric_is_full_service_symmetric_difference():
    ctx,row=setup();row={**row,'state_at_issue':'RUNNING','start_slot':0,'end_slot':29,'safe_duration_slots':29,'safe_duration_seconds':26100.}
    opts=options(row,ctx.capacity,Wan(),{'one':900.});opt=next(o for o in opts if o.migrated)
    selected=materialize(row,opt,ctx.capacity,Wan())
    assert deviation(row,opt)==2*(29-opt.checkpoint)
    assert audit([row],[selected],ctx.capacity,Wan())['status']=='PASS'


def test_no_primary_sacrifice_smaller_than_old_tolerance(tmp_path):
    ctx,row=setup();c=ctx.coefficients[0]
    m=c.current_matrix.copy();m[1]=m[0]-5e-8
    ctx.coefficients=(replace(c,current_matrix=m),)
    r=solve([row],np.array([[1.,0.]]),ctx,tmp_path)
    assert r['jobs'][0]['AIDC_site']=='AIDC02'
    assert r['tertiary_reference_deviation_optimum']==2


def test_exact_b1_reuse_without_any_solver_call(tmp_path,monkeypatch):
    from dayahead.paper_analysis.storage import write_json
    from dayahead.v40g.reuse import accepted_b1_as_a0,persist_reuse,validate_m1_conditioning
    import gurobipy as gp
    ctx,row=setup();result=solve([row],np.array([[1.,0.]]),ctx,tmp_path/'b1')
    trajectory=tmp_path/'B1.npz';np.savez_compressed(trajectory,gpu=result['GPU'],pcc=result['PCC'])
    def forbidden(*a,**k):raise AssertionError('DUPLICATE_A0_OPTIMIZATION')
    monkeypatch.setattr(gp.Model,'optimize',forbidden)
    h=accepted_b1_as_a0(tmp_path/'b1/ACCEPTED_AIDC.json',trajectory)
    r=persist_reuse(h,tmp_path/'A0')
    assert r['B3_A0_AIDC_OPTIMIZE_CALLS']==0
    assert (tmp_path/'A0/B1_FINAL_AS_A0.json').read_bytes()==h.accepted_b1_path.read_bytes()
    with pytest.raises(ValueError,match='M1_MUST_BE_CONDITIONED'):
        validate_m1_conditioning(h,{'AIDC_decision_SHA':'B2'})
    data=dict(AIDC_decision_SHA=h.decision_sha,AIDC_trajectory_file_SHA=h.trajectory_file_sha,
              corrected_Planning_electrical_authority_SHA='grid',common_T_DA_SHA='duration',
              causal_traffic_authority_SHA='traffic',MESS_mobility_energy_authority_SHA='energy')
    assert validate_m1_conditioning(h,data)
    with pytest.raises(ValueError,match='B2_CANNOT_BYPASS'):
        validate_m1_conditioning(h,{**data,'B2_result_accepted_without_M1_reoptimization':True})


@pytest.mark.parametrize('residual_slots',[29,4])
def test_frozen_migration_actual_preserves_full_service(residual_slots):
    from datetime import datetime,timedelta,timezone
    from dayahead.v40g.actual import replay_jobs
    from dayahead.v40d_actual.rack_dispatch import Rack
    ctx,row=setup();issue=datetime(2025,4,30,18,tzinfo=timezone(timedelta(hours=10)))
    row={**row,'state_at_issue':'RUNNING','start_slot':0,'end_slot':29,'safe_duration_slots':29,'safe_duration_seconds':26100.,
         'submit_time':(issue-timedelta(days=1)).isoformat(),'requested_walltime_seconds':100000.}
    option=next(o for o in options(row,ctx.capacity,Wan(),{'one':900.}) if o.migrated)
    candidate=materialize(row,option,ctx.capacity,Wan())
    obs={'one':{'start_time':issue-timedelta(hours=1),'end_time':issue+timedelta(seconds=residual_slots*900),'gpus_requested':1}}
    result=replay_jobs([candidate],obs,issue_time=issue,site_capacity=ctx.capacity.site_capacity,
                       racks=[Rack(s,s+'_LP01',2) for s in ctx.capacity.aidc_ids])
    final=result['job_ledger'][0]
    assert len(result['job_ledger'])==1 and final['job_uid']=='one'
    assert sum(s['end']-s['start'] for s in final['actual_compute_segments'])==residual_slots
    assert final['migration_executed']==(residual_slots>option.checkpoint)
    assert result['frozen_migration_actual_audit']['status']=='PASS'
