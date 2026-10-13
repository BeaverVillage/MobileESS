"""New domain semantics pass through existing generators and hard validators."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from v42_job_capability import Job,ServiceBoundary,Resources,Option,validate
from v42_a_stage_domain_v2.domain import physical_domain,physical_starts,contains
from v42_a_stage_phase1.producer import complete_graph
from v42_integration.a_engine import ACase,authorized_data


def data():
    j=Job('a','PENDING',0,0,2,'A',5,2,initial_sites=('A','B'),checkpoint_authorized=True,
        duration_authority='LABELED_FIXTURE_NOMINAL')
    b=ServiceBoundary('FIXTURE',True,True,(2,),12)
    r=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},{('ab',t):1000 for t in range(15)},
        {('A','B'):('ab',),('B','A'):('ab',)},15,10,{}, {}, {})
    raw={'risk_nominal_completion_issue_slot':7,'reference_end':7}
    return ({'day':'2025-05-01'}, {'a':j,'b':replace(j,uid='b')}, {'a':b,'b':b},r,
        {'a':raw,'b':raw},{},{},{'classes':{'old':['a','b']}})


def case():
    receipts={u:dict(policy_id='EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1',budget_seconds=3600,
        batch_eligible=True,hard_contract={'release':0}) for u in ('a','b')}
    return ACase(data(),None,None,'case','A1','B3',{'a':(1,2,3),'b':(1,2,3)},receipts)


def test_authorized_domain_is_consumed_by_original_graph_and_full_validator():
    c=case();d,domains=authorized_data(c);j=d[1]['a'];b=d[2]['a'];r=d[3]
    assert physical_starts(j,b)==(1,2,3)
    assert {s for s,_ in domains['a'].stays}=={1,2,3}
    graph=complete_graph(j,domains['a'])
    assert {s for _,s in graph.events['y']}=={1,2,3}
    assert contains(j,b,r,domains['a'],Option(1,'A',(('A',1,6),)))
    with pytest.raises(ValueError,match='START_WINDOW'):
        validate(j,Option(0,'A',(('A',0,5),)),b,r)


def test_distinct_hard_contracts_are_never_class_merged():
    c=case();c.qos_receipts['b']['hard_contract']={'completion_deadline':8000}
    d,_=authorized_data(c)
    assert len(d[7]['classes'])==2
    c=case();d,_=authorized_data(c)
    assert len(d[7]['classes'])==1


def test_observed_unknown_has_same_original_domain_and_joint_budget():
    c=case();c.data=tuple(list(c.data[:1])+[dict(c.data[1],b=replace(c.data[1]['b'],unknown_arrival=True))]+list(c.data[2:]))
    d,domains=authorized_data(c)
    assert domains['a'].stays==domains['b'].stays
    assert domains['b'].blocks
    for start,source,cp,physical,dest,gpu,taus in domains['b'].blocks:
        for tau in taus:
            tr=domains['b'].cache.transfer(source,dest,gpu,tau)
            assert max(0,start-d[1]['b'].reference_start)*900+(tr.restart-cp)*900<=3600


def test_representation_ceiling_and_running_history_survive_new_policy():
    c=case();c.window_slots={u:(2,3,20) for u in ('a','b')}
    d,domains=authorized_data(c)
    assert all(s<=7 for s,_ in domains['a'].stays)
    running=replace(d[1]['a'],state='RUNNING',event=2,elapsed_seconds=1800.)
    assert physical_starts(running,d[2]['a'])==(2,)


def test_empty_new_start_window_does_not_delete_observed_running_service():
    c=case();jobs=dict(c.data[1])
    jobs['a']=replace(jobs['a'],state='RUNNING',event=2,elapsed_seconds=1800.)
    c.data=(c.data[0],jobs,*c.data[2:]);c.window_slots['a']=()
    d,domains=authorized_data(c)
    assert d[1]['a'].qos_allowed_starts==(2,)
    assert {s for s,_ in domains['a'].stays}=={2}
    assert all(site=='A' for _,site in domains['a'].stays)


def test_shared_resource_cache_preserves_every_authorized_option():
    c=case();d,domains=authorized_data(c)
    assert domains['a'].cache is domains['b'].cache
    for uid in d[1]:
        independent=physical_domain(d[1][uid],d[2][uid],d[3])
        assert tuple(domains[uid])==tuple(independent)
        assert domains[uid].sha==independent.sha


def test_zero_budget_cannot_authorize_positive_restart_migration():
    c=case()
    c.window_slots={uid:(1,2) for uid in c.window_slots}
    for receipt in c.qos_receipts.values():receipt['budget_seconds']=0
    d,domains=authorized_data(c)
    for uid in d[1]:
        assert not domains[uid].blocks
        assert domains[uid].stays==((1,'A'),(1,'B'),(2,'A'),(2,'B'))
