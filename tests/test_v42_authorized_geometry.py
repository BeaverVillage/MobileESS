"""Exact preparation acceleration versus the immutable PR230 enumerator."""
from dataclasses import replace
from pathlib import Path
import subprocess
import numpy as np
import pytest
from v42_job_capability import Job,ServiceBoundary,Resources
from v42_boundary.generator import Generator
from v42_a_stage_domain_v2.domain import physical_domain
from v42_a_stage_phase1.producer import complete_graph
from v42_integration.a_engine import authorized_geometry


@pytest.fixture(scope='module')
def prior_enumerator():
    root=Path(__file__).resolve().parents[1]
    source=subprocess.check_output(['git','show','f32b22adf8e3e53ab68256458cb991f9d30d2ecb:v42_a_stage_domain_v2/domain.py'],cwd=root,text=True)
    space=dict(__name__='v42_a_stage_domain_v2.pr230_domain',__package__='v42_a_stage_domain_v2')
    exec(compile(source,'PR230_DOMAIN.py','exec'),space)
    return space['physical_domain']


def geometry(budget=3600.,burden=0.):
    starts=tuple(t for t in range(2,7) if burden+(t-2)*900<=budget+1e-9)
    job=Job('a','PENDING',0,0,2,'A',6,1,initial_sites=('A','B'),
        checkpoint_authorized=True,duration_authority='FIXTURE',qos_policy_id='RESEARCH',
        qos_receipt_sha='a'*64,qos_allowed_starts=starts,
        qos_budget_seconds=budget,qos_start_delay_seconds=burden)
    bound=ServiceBoundary('FIXTURE',True,True,job.qos_allowed_starts,16)
    r=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},
        {('AB',t):2 for t in range(16)},{('A','B'):('AB',),('B','A'):('AB',)},
        16,3,{}, {}, {},restart_slots=1,max_active_transfers=2)
    return job,bound,r


@pytest.mark.parametrize('edge',(1800.,2700.,3600.))
@pytest.mark.parametrize('toward',(-np.inf,0.,np.inf))
@pytest.mark.parametrize('burden',(0.,.125,899.9999999999999))
@pytest.mark.parametrize('rate',(2,4))
def test_necessary_tau_bound_preserves_every_pr230_option(prior_enumerator,edge,toward,burden,rate):
    budget=edge if toward==0 else np.nextafter(edge,toward)
    job,bound,r=geometry(float(budget),burden)
    r.wan_capacities={k:rate for k in r.wan_capacities}
    before=prior_enumerator(job,bound,r);after=physical_domain(job,bound,r)
    assert (before.stays,before.blocks,before.sha)==(after.stays,after.blocks,after.sha)
    assert tuple(before)==tuple(after)


def test_unrestricted_domain_is_identical(prior_enumerator):
    job,bound,r=geometry();job=replace(job,qos_policy_id='',qos_allowed_starts=None)
    before=prior_enumerator(job,bound,r);after=physical_domain(job,bound,r)
    assert (before.stays,before.blocks,before.sha)==(after.stays,after.blocks,after.sha)
    assert tuple(before)==tuple(after)


def test_geometry_cache_receipts_retain_original_uid_domain_hash(prior_enumerator):
    job,bound,r=geometry();gen=Generator(r,bound.latest_completion);cache={}
    first,graph,hit=authorized_geometry(job,bound,r,gen,False,cache)
    assert not hit
    other=replace(job,uid='b',qos_receipt_sha='b'*64)
    second,shared,hit=authorized_geometry(other,bound,r,gen,False,cache)
    direct=prior_enumerator(other,bound,r)
    assert hit and graph is shared and first is not second
    assert (second.stays,second.blocks,second.sha)==(direct.stays,direct.blocks,direct.sha)
    assert second.sha!=first.sha
    assert shared.sha==complete_graph(other,direct).sha
    for changed in (replace(other,gpu=2),replace(other,service_slots=5),
                    replace(other,qos_budget_seconds=4500.),replace(other,initial_sites=('A',))):
        _,_,hit=authorized_geometry(changed,bound,r,gen,False,cache)
        assert not hit
    _,_,hit=authorized_geometry(other,replace(bound,latest_completion=15),r,gen,False,cache)
    assert not hit
    _,_,hit=authorized_geometry(other,bound,r,gen,True,cache)
    assert not hit


def test_cached_geometry_rejects_mutated_resource_snapshot():
    job,bound,r=geometry();gen=Generator(r,bound.latest_completion);cache={}
    authorized_geometry(job,bound,r,gen,False,cache)
    r.capacities['A']=7
    with pytest.raises(ValueError,match='PHYSICAL_RESOURCE_IDENTITY'):
        authorized_geometry(replace(job,uid='b'),bound,r,gen,False,cache)
