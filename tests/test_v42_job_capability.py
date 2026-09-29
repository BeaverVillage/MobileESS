from dataclasses import replace
from itertools import product
import pytest
from v42_job_capability import (Job, ServiceBoundary, Resources, Cohort, Option, GridRow,
    temporal_candidate, checkpoint_records, build_domain, validate, capability,
    resources_used, resource_limit, solve_joint, executable_domains, ACTION_CLASSES)


def fixture(case='F'):
    r = Resources({'A': 8, 'B': 8}, {'A': (8,), 'B': (8,)},
                  {('AB', t): 640 for t in range(12)}, {('A','B'): ('AB',), ('B','A'): ('AB',)},
                  10, 80, {}, {}, {})
    j = Job(case, 'PENDING', 0, 0, 0, 'A', 6, 4, 'standby', initial_sites=('A','B'),
            checkpoint_authorized=True, duration_authority='SYNTHETIC_FULL_COMPUTE',standby_candidate_authorized=True)
    b = ServiceBoundary('SYNTHETIC_COMPLETE_CARRYOUT', True, True, (0,1), 16)
    if case in ('A','B','J'):
        j = replace(j, initial_sites=('A',), checkpoint_authorized=False)
    if case in ('A','C','E','G','H','J'):
        b = replace(b, allowed_starts=(0,))
    if case in ('C','D','I'):
        j = replace(j, checkpoint_authorized=False)
    if case == 'E':
        j = replace(j, state='RUNNING', elapsed_seconds=1800.)
    if case == 'G':
        r = replace(r, wan_capacities={})
    if case == 'H':
        r = replace(r, capacities={'A':8, 'B':2}, rack_limits={'A':(8,), 'B':(2,)})
    if case == 'I':
        j = replace(j, event=94, reference_start=94)
        b = replace(b, allowed_starts=(94,95), latest_completion=104)
        r = replace(r, control_end=96)
    if case == 'J':
        j = replace(j, protected=True, qos='high')
        b = replace(b, allowed_starts=(0,1,2))
    # One electrical row per supported slot; never score a sum across time as loading.
    grid = [GridRow('LINE', .5, {(s,t):.01 for s in r.capacities}, 0, 1) for t in range(r.control_end)]
    grid += [GridRow('TRANSFORMER', .2, {}, 0, 1), GridRow('VOLTAGE', 1., {}, .95, 1.05)]
    return j,b,r,grid


@pytest.mark.parametrize('case,masks', [('A',(0,0,0)),('B',(1,0,0)),('C',(0,1,0)),('D',(1,1,0)),
    ('E',(0,0,1)),('F',(1,1,1)),('G',(0,1,0)),('H',(0,0,0)),('I',(1,1,0)),('J',(0,0,0))])
def test_canaries(case,masks):
    j,b,r,g = fixture(case)
    opts, audit = build_domain(j,b,r)
    witnessed = executable_domains({j.uid:j}, {j.uid:opts},r,g)[j.uid]
    actual = capability(j,witnessed)
    assert tuple(actual[k] for k in ('can_timeshift','can_prestart_place','can_checkpoint_migrate')) == masks
    for o in opts:
        assert validate(j,o,b,r)
        assert sum(end-start for _,start,end in o.segments) == j.service_slots
        assert sum(v for k,v in resources_used(j,o).items() if k[0]=='GPU') == j.gpu*j.service_slots
    if case == 'F':
        assert set(o.action(j) for o in opts) == set(ACTION_CLASSES)
    if case == 'I':
        assert all(o.segments[-1][2] > 96 for o in opts)


def test_service_authority_missing_and_native_fail_closed():
    j,b,r,_ = fixture()
    for change in ({'finalized':False}, {'synthetic':False}, {'authority_id':''}):
        with pytest.raises(ValueError):
            build_domain(j,replace(b,**change),r)


@pytest.mark.parametrize('elapsed', [0, 1, 899, 900, 1799, 1800, 1801, 57238.3])
def test_checkpoint_physical_phase(elapsed):
    j,_,_,_ = fixture('E')
    j = replace(j, elapsed_seconds=elapsed)
    records = checkpoint_records(j,0,6)
    for cp,physical in records:
        assert 0 <= cp*900-physical < 900
        assert (physical+elapsed)/1800 == pytest.approx(round((physical+elapsed)/1800))
    if elapsed == 1800:
        assert records[0] == (0,0)


def test_missing_elapsed_only_disables_migration():
    j,b,r,_ = fixture('E')
    opts,_ = build_domain(replace(j,elapsed_seconds=None),b,r)
    assert len(opts)==1 and not opts[0].migrated


def test_rule_support_and_no_semantic_dependency():
    j,_,_,_ = fixture('D'); j=replace(j,qos='normal')
    assert temporal_candidate(j,'T2_CONSERVATIVE_Q25',Cohort(99,5000,1800))[0] is False
    assert temporal_candidate(j,'T2_CONSERVATIVE_Q25',Cohort(100,5000,899))[0] is False
    assert temporal_candidate(j,'T2_CONSERVATIVE_Q25',Cohort(100,5000,1801))[:2] == (True,2)
    assert temporal_candidate(replace(j,qos='high'),'T2_CONSERVATIVE_Q25',Cohort(100,5000,1801))[0] is False
    assert temporal_candidate(replace(j,qos='standby'),'T2_CONSERVATIVE_Q25')[:2] == (True,None)


def test_candidate_is_not_executable():
    j,b,r,_ = fixture('A')
    opts,audit = build_domain(j,b,r)
    assert audit['temporal_candidate'] and not capability(j,opts)['can_timeshift']


def test_unknown_site_only_and_no_pre_submit():
    j,b,r,_ = fixture('F'); j=replace(j,unknown_arrival=True)
    opts,_ = build_domain(j,b,r)
    assert {o.action(j) for o in opts} == {'STAY','PREPLACE_ONLY'}
    with pytest.raises(ValueError,match='NOT_YET_SUBMITTED'):
        replace(j,submit=1)


def test_full_carryout_capacity_is_enforced():
    j,b,r,_ = fixture('I'); r=replace(r,fixed_gpu={('A',100):8,('B',100):8})
    opts,_=build_domain(j,b,r)
    assert all(o.start == 94 for o in opts)  # 95+6 reaches slot100, 94+6 does not


def test_protected_no_temporal_but_independent_spatial():
    j,b,r,_=fixture('F');j=replace(j,protected=True,qos='high')
    opts,_=build_domain(j,b,r)
    assert all(o.start==0 for o in opts) and any(o.initial_site=='B' for o in opts)


def test_invalid_service_wan_restart_and_overlap():
    j,b,r,_=fixture('F');opts,_=build_domain(j,b,r)
    o=next(o for o in opts if o.migrated)
    bad=[replace(o,segments=((o.initial_site,0,6),)), replace(o,wan=()),
         replace(o,restart_end=o.transfer_end), replace(o,physical_checkpoint_seconds=1),
         replace(o,segments=(o.segments[0],(o.destination,1,7))), replace(o,destination=o.initial_site)]
    for value in bad:
        with pytest.raises(ValueError):validate(j,value,b,r)


def test_coupled_joint_swap_not_removed_by_fixed_neighbor_screen():
    j,b,r,g=fixture('C'); r=replace(r,capacities={'A':4,'B':4})
    k=replace(j,uid='K',reference_site='B')
    jobs={j.uid:j,k.uid:k};domains={u:build_domain(v,b,r)[0] for u,v in jobs.items()}
    witnessed=executable_domains(jobs,domains,r,g)
    assert all(len(opts)==2 for opts in witnessed.values())
    result=solve_joint(jobs,domains,r,g)
    assert all(o.initial_site==jobs[u].reference_site for u,o in result['selected'].items())
    for combination in product(*domains.values()):
        if combination[0].initial_site==combination[1].initial_site:
            assert sum(j.gpu for j in jobs.values()) > 4


def test_grid_witness_not_confused_with_resource_option():
    j,b,r,_=fixture('C'); opts,_=build_domain(j,b,r)
    g=[GridRow('LINE',.1,{('B',0):1},0,1)]
    witnessed=executable_domains({j.uid:j},{j.uid:opts},r,g)
    assert len(opts)==2 and len(witnessed[j.uid])==1
    assert not capability(j,witnessed[j.uid])['can_prestart_place']


def test_primary_degeneracy_and_secondary_retains_reference():
    j,b,r,g=fixture('F'); opts,_=build_domain(j,b,r)
    chosen=[next(o for o in opts if o.action(j)==kind) for kind in ('STAY','SHIFT_PREPLACE_MIGRATE')]
    a=solve_joint({j.uid:j},{j.uid:chosen},r,g,secondary=False,force=(j.uid,0))
    z=solve_joint({j.uid:j},{j.uid:chosen},r,g,secondary=False,force=(j.uid,1))
    assert a['passes'][0]['value']==pytest.approx(z['passes'][0]['value'])
    result=solve_joint({j.uid:j},{j.uid:chosen},r,g)
    assert result['selected'][j.uid].action(j)=='STAY'


def test_shortfall_cannot_be_deleted_and_fixed_jobs_keep_load():
    j,b,r,g=fixture('C'); opts,_=build_domain(j,b,r)
    result=solve_joint({j.uid:j},{j.uid:opts},r,g,shortfall_cost={(j.uid,0):1,(j.uid,1):0})
    assert result['passes'][1]['objective']=='required_shortfall'
    assert result['selected'][j.uid].initial_site=='B'
    fixed=solve_joint({j.uid:j},{j.uid:(opts[0],)},r,g)
    assert fixed['binary_variables']==0 and fixed['fixed_jobs']==1
    assert fixed['passes'][0]['value']==pytest.approx(.54)


def test_transformer_and_voltage_hard_but_not_in_primary():
    j,b,r,g=fixture('A');opts,_=build_domain(j,b,r)
    assert solve_joint({j.uid:j},{j.uid:opts},r,g+[GridRow('TRANSFORMER',1.01,{},0,1)]) is None
    assert solve_joint({j.uid:j},{j.uid:opts},r,g+[GridRow('VOLTAGE',.94,{},.95,1.05)]) is None


def test_no_future_fields_in_input_and_causal_perturbation():
    j,b,r,g=fixture('D')
    # Projection deliberately admits ONLY dataclass causal fields.
    source=dict(vars(j),realized_start=999,realized_end=9999,actual_runtime=99999,future_queue=9000)
    def project(s):return Job(**{k:s[k] for k in Job.__dataclass_fields__})
    before=build_domain(project(source),b,r)[0]
    for k in ('realized_start','realized_end','actual_runtime','future_queue'):source[k]=-1
    assert before==build_domain(project(source),b,r)[0]
    source['qos']='high'
    assert all(o.start==0 for o in build_domain(project(source),b,r)[0])


def test_oversize_never_clipped_or_split():
    j,b,r,_=fixture('F');j=replace(j,gpu=256)
    opts,_=build_domain(j,b,r)
    assert opts==()


def test_serial_wan_and_total_link_capacity_are_joint():
    j,b,r,g=fixture('F');opts,_=build_domain(j,b,r)
    o=next(o for o in opts if o.migrated)
    k=replace(j,uid='K')
    assert solve_joint({j.uid:j,k.uid:k},{j.uid:(o,),k.uid:(o,)},r,g) is None


def test_previous_migration_disables_second_move():
    j,b,r,_=fixture('E');j=replace(j,migrations_used=1)
    assert not any(o.migrated for o in build_domain(j,b,r)[0])


def test_milp_matches_independent_exhaustive_schedule_search():
    j,b,r,_=fixture('D');r=replace(r,capacities={'A':4,'B':4})
    k=replace(j,uid='K',reference_site='B')
    jobs={j.uid:j,k.uid:k};domains={u:build_domain(v,b,r)[0] for u,v in jobs.items()}
    g=[GridRow('LINE',.1,{('A',0):.1,('B',0):.03},0,1),
       GridRow('LINE',.2,{('B',1):.02,('A',1):.1},0,1)]
    candidates=[]
    for combo in product(*domains.values()):
        load={}
        for job,o in zip(jobs.values(),combo):
            for key,n in resources_used(job,o).items():load[key]=load.get(key,0)+n
        if any(n>resource_limit(key,r) for key,n in load.items()):continue
        rho=max(row.baseline+sum(coef*load.get(('GPU',s,t),0) for (s,t),coef in row.gpu_coefficients.items()) for row in g)
        candidates.append((rho,sum(int(o.migrated) for o in combo),
                           sum(abs(o.start-job.reference_start) for job,o in zip(jobs.values(),combo)),
                           sum(o.initial_site!=job.reference_site for job,o in zip(jobs.values(),combo))))
    optimum=min(candidates)
    result=solve_joint(jobs,domains,r,g)
    assert tuple(p['value'] for p in result['passes'][:4])==pytest.approx(optimum)


def test_primary_jointly_selects_shift_and_placement_when_useful():
    j,b,r,_=fixture('D');opts,_=build_domain(j,b,r)
    g=[GridRow('LINE',.1,{('A',t):.1,('B',t):.1 if t==0 else 0.},0,1) for t in range(8)]
    result=solve_joint({j.uid:j},{j.uid:opts},r,g)
    assert result['selected'][j.uid].action(j)=='SHIFT_PREPLACE'
    assert result['passes'][0]['value']==pytest.approx(.1)


def test_running_migration_selected_only_when_grid_useful():
    j,b,r,_=fixture('E');opts,_=build_domain(j,b,r)
    g=[GridRow('LINE',.1,{('A',5):.1},0,1)]
    result=solve_joint({j.uid:j},{j.uid:opts},r,g)
    assert result['selected'][j.uid].action(j)=='MIGRATE'


def test_qos_alone_does_not_promote_standby_candidate():
    j,b,r,_=fixture('D');j=replace(j,standby_candidate_authorized=False)
    opts,audit=build_domain(j,b,r)
    assert not audit['temporal_candidate'] and all(o.start==j.reference_start for o in opts)
