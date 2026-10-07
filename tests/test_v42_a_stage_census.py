"""Tiny build-only verification of the combinatorial variable forecast."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from v42_job_capability import Job, Resources, ServiceBoundary
from v42_boundary.generator import Generator
from v42_compact.graph import GraphFactory
from v42_a_stage_domain_v2.domain import physical_domain, physical_starts, augment_stay_graph, active_stay_domain
from v42_a_stage_domain_v2.census import structural_variable_delta


@pytest.mark.parametrize('N,migration,single_site', [(1,False,False),(3,False,False),
                                                   (1,True,False),(3,True,False),
                                                   (1,False,True),(3,False,True)])
def test_structural_variable_forecast_against_tiny_native_factory(N,migration,single_site):
    gp=pytest.importorskip('gurobipy')
    from v42_root.native import local_units
    resources=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},
                        {('L',t):100 for t in range(10)}, {('A','B'):('L',),('B','A'):('L',)},
                        10,1,{}, {}, {})
    job=Job('j0','PENDING',0,0,3,'A',4,1,initial_sites=('A',) if single_site else ('A','B'),
            checkpoint_authorized=migration,duration_authority='SYNTHETIC_COUNT_FIXTURE')
    bound=ServiceBoundary('SYNTHETIC_COUNT_FIXTURE',True,True,(3,),10)
    graph=GraphFactory(resources,10).graph(job,bound)
    gen=Generator(resources,10); legacy=gen.domain(job,bound)
    domain=physical_domain(job,bound,resources,gen)
    wide=replace(bound,allowed_starts=physical_starts(job,bound))
    active_domain=active_stay_domain(job,wide,resources,graph,domain,N)
    active=augment_stay_graph(job,wide,graph,active_domain)
    members=[f'j{i}' for i in range(N)];jobs={u:replace(job,uid=u) for u in members}
    bounds={u:bound for u in members}
    class SilentContext:
        def progress(self,value):pass
    def counts(g):
        model=gp.Model('TINY_CENSUS_COUNT_FIXTURE');model.Params.OutputFlag=0
        try:
            local_units(model,jobs,bounds,resources,{u:g for u in members},{'c':members},'F2-CRA',SilentContext())
            model.update()
            return dict(binary=model.NumBinVars,integer=model.NumIntVars-model.NumBinVars,
                        continuous=model.NumVars-model.NumIntVars)
        finally:model.dispose()
    before,after=counts(graph),counts(active)
    predicted=structural_variable_delta(job,graph,active,legacy.stays,active_domain.stays,N)
    assert {key:after[key]-before[key] for key in before} == {key:predicted.get(key,0) for key in before}


def test_committed_static_membership_receipts():
    root=Path(__file__).resolve().parents[1]/'docs/v42_a_stage_domain_authority_v2_20261007'
    first=root/'MAY17_RESCUE_OPTION_MEMBERSHIP.json'
    second=root/'MAY19_PR165_PR166_OPTION_MEMBERSHIP.json'
    if not first.exists() or not second.exists():
        pytest.skip('Static audit publication still in progress')
    may17=json.loads(first.read_text(encoding='utf8')); may19=json.loads(second.read_text(encoding='utf8'))
    assert may17['MAY17_35_RESCUE_OPTIONS_INCLUDED']
    assert may17['groups']['MAY17_35_RESCUE']['checked_options']==35
    assert may19['PR165_38_AND_PR166_S_A_S_B_S_C_S_D_INCLUDED']
    assert may19['groups']['PR165_38']['checked_options']==38
    assert all(group['PASS'] for group in may19['groups'].values())
    assert may17['optimize_calls']==may19['optimize_calls']==0
