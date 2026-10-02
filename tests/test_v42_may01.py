from pathlib import Path
from itertools import combinations
from copy import deepcopy
import pytest
from v42_may01.state import physical_occupancy,observe,reservation,t2,cohort_key
from v42_may01.projection import capacity_lower_bounds,known_planning_gate,solve


@pytest.mark.parametrize('known',[True,False])
@pytest.mark.parametrize('state,expected',[('PENDING',0),('RUNNING',16)])
def test_causal_known_unknown_physical_occupancy(known,state,expected):
    assert physical_occupancy(state,16,known=known)==expected


def test_old_pending_plan_does_not_become_physical_occupancy():
    old=dict(uid='j',state='PENDING',site='A',gpu=4,known=True,observed_at=0,planning_segments=(('A',0,200),))
    current=dict(old,observed_at=900)
    result=observe(old,current)
    assert result['current_physical_occupancy']==0 and not result['prior_reservation_is_physical']
    assert result['previous_counterfactual_plan']==old['planning_segments']
    use=reservation(4,(('A',30,200),))
    assert ('A',29) not in use and use['A',30]==use['A',199]==4
    assert sum(use.values())==4*170  # tail retained; no service discarded


def test_running_site_remaining_and_history_preserved():
    old=dict(uid='r',state='RUNNING',site='A',gpu=4,known=True,observed_at=1,remaining_seconds=3600)
    current=dict(old,observed_at=2,remaining_seconds=3599)
    result=observe(old,current)
    assert result['site']=='A' and result['remaining_seconds']==3599 and result['current_physical_occupancy']==4
    with pytest.raises(ValueError):observe(old,dict(current,site='B'))
    with pytest.raises(ValueError):reservation(4,(('A',0,3),('B',2,5)))


def cohort(n=100,q=1800):
    return dict(N=n,Q25_seconds=q,cutoff='2025-01-01 00:00:00+00:00',max_observed_start='2024-12-20 01:00:00+00:00')


@pytest.mark.parametrize('n,q,yes,slots',[(99,1800,False,0),(100,899,False,0),(100,900,True,1),(101,2699,True,2)])
def test_exact_T2_thresholds_and_floor(n,q,yes,slots):
    result=t2('PENDING',False,cohort(n,q))
    assert result[:2]==(yes,slots)


@pytest.mark.parametrize('state,protected,known',[('RUNNING',False,True),('PENDING',True,True),('PENDING',False,False)])
def test_T2_authority_firewalls(state,protected,known):
    assert not t2(state,protected,cohort(),known=known)[0]


def test_T2_no_standby_shortcut_and_no_May_outcome_feature():
    c=cohort(8482,272)
    assert not t2('PENDING',False,c)[0]
    result=t2('PENDING',False,cohort())
    assert t2('PENDING',False,dict(cohort(),May_realized_wait=999999))==result
    with pytest.raises(ValueError):t2('PENDING',False,dict(cohort(),max_observed_start='2025-05-01'))
    assert cohort_key('standby','gpu-h100-stdby',1,43200,1)=='standby|gpu-h100-stdby|STANDBY_QUEUE_CONTROLLED|False|1|4-24h|1'


def test_known_gate_does_not_require_unknown_runtime_or_response_kernel():
    bundle=dict(day='2025-05-01',network='IEEE123',unknown_arrival_actions=False,
        unresolved_transitive_physical_inputs=[],known_population=[dict(exact_service_seconds=900,planning_eligible=True)],
        RUNTIME_PROVIDER_READY=False,response_kernel_ready=False)
    assert known_planning_gate(bundle)
    with pytest.raises(ValueError):known_planning_gate(dict(bundle,network='IEEE8500'))


def jobs_for_bound(gpus):
    return [dict(job_uid=str(i),GPU_gang=g,reference_start_if_authorized=24,reference_end=30,can_timeshift=False) for i,g in enumerate(gpus)]


def test_necessary_bound_contains_all_migration_subsets():
    jobs=jobs_for_bound([1,2,4,8]);row=capacity_lower_bounds(jobs,[1.],100,transfer_slots=2)[0]
    # Removing the two largest complete jobs is more generous than any legal
    # two one-shot migrations with full destination service and transfer gaps.
    for n in range(3):
        for chosen in combinations(jobs,n):
            remaining=sum(r['GPU_gang'] for r in jobs)-sum(r['GPU_gang'] for r in chosen)
            assert row['known_GPU_lower_bound']<=remaining
    with pytest.raises(ValueError):capacity_lower_bounds([dict(jobs[0],can_timeshift=True)],[1.],100)


def test_projection_never_promotes_feasible_relaxation(tmp_path):
    result=solve(jobs_for_bound([1]),[1.]*24,100,tmp_path,seconds=5)
    assert result['status']=='RELAXATION_FEASIBLE_REQUIRES_FULL_MODEL'
    assert not result['full_A1_infeasible_proven'] and not result['scientific_schedule_accepted']


def test_projection_infeasible_certificate_has_no_fabricated_incumbent(tmp_path):
    result=solve(jobs_for_bound([1]*121),[100.]*24,100,tmp_path,seconds=5)
    assert result['status']=='INFEASIBLE' and result['full_A1_infeasible_proven']
    assert result['full_A1_MIP_gap'] is None and not result['incumbent_available']
    assert result['MIPGap_parameter']==.001 and result['model_size']['quadratic_constraints']==0


def test_solver_diagnostic_files_preserved_under_unicode_path(tmp_path):
    output=tmp_path/'한글 경로';output.mkdir()
    result=solve(jobs_for_bound([1]*121),[100.]*24,100,output,seconds=5)
    assert result['full_A1_infeasible_proven']
    assert (output/'NATIVE_RESOURCE_PROJECTION.lp').stat().st_size>0
    assert (output/'NATIVE_RESOURCE_PROJECTION.ilp').stat().st_size>0


def test_four_stage_handoff_and_MIP_start_mapping(monkeypatch,tmp_path):
    # Control-flow test only. Fake receipts cannot be counted as Fresh AC or a
    # native canary. Production still validates a matching real OpenDSS receipt.
    import v42_native.coordinator as coordinator
    from v42_native.contracts import digest
    called=[];states={}
    def supervised(stage,worker,validator,payload,output,seconds):
        assert seconds==600
        assert payload['warm_start']==(states['A1'] if stage=='A2' else states['M1'] if stage=='M2' else None)
        called.append(stage);states[stage]={'stage':stage};return states[stage],{'test_only':True}
    class Backend:
        worker='test';validator='test';grid_sha='a'*64
        def preflight(self):return dict.fromkeys(coordinator.NATIVE_REQUIRED,True)
        def stage_payload(self,stage,a,m):return {'A':a,'M':m}
        def objective(self,a,m):return (1,)
        def combine(self,a,m):
            return dict(A=a,M=m,aidc_schedule=a,known_job_actions=[],
                unknown_arrival_policy=dict(interface='v42_native.actual.unknown_arrival',authority_sha='b'*64),
                mess_route=[],movement=[],charge_mode=[],P=[],Q=[],SOC=[],aidc_electrical_footprint=[],
                grid_anchor=dict(grid_sha=self.grid_sha),input_authority_hashes=dict(forecast='c'*64))
        def fresh_ac(self,final):return dict(engine='OpenDSS',fresh_run=True,synthetic=False,schedule_sha=digest(final),grid_sha=self.grid_sha,
            converged=True,voltage_violations=0,line_current_violations=0,transformer_current_violations=0,transformer_kVA_violations=0)
    monkeypatch.setattr(coordinator,'supervise',supervised)
    result=coordinator.run(Backend(),tmp_path)
    assert result['frozen_plan'].verify() and 'fresh_ac' not in result
    assert called==['A1','M1','A2','M2']
