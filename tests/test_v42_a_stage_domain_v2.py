"""Small synthetic/static tests. No production/native optimization."""
from dataclasses import replace
from fractions import Fraction
import pytest
from v42_job_capability import Job, ServiceBoundary, Resources, Option
from v42_a_stage_domain_v2.domain import (physical_starts,physical_domain,noflex_anchor,
    verify_nesting,contains,prepare_active,activate_migration,activate_stay)
from v42_a_stage_domain_v2.screening import ScientificColumn,exact_duplicates,grid_priority
from v42_a_stage_domain_v2.pricing import PricingEvidence,price_column,scan
from v42_a_stage_domain_v2.causality import require_causal_information


def fixture():
    job = Job('j','PENDING',0,0,4,'A',2,2,initial_sites=('A','B'),
              checkpoint_authorized=True,duration_authority='SYNTHETIC_FIXTURE')
    bound = ServiceBoundary('FIXTURE',True,True,(4,5),10)
    resources = Resources({'A':8,'B':8},{'A':(4,),'B':(4,)},
        {('AB',t):8 for t in range(12)}, {('A','B'):('AB',),('B','A'):('AB',)},
        12,4,{}, {}, {}, restart_slots=1,max_active_transfers=2)
    return job,bound,resources


def test_reference_is_not_physical_wall_and_tail_is_preserved():
    j,b,r=fixture()
    assert physical_starts(j,b)==tuple(range(9))
    assert physical_starts(j,replace(b,latest_completion=18),control_end=12)[-1]==16
    assert physical_starts(j,b,hard_release=3)[0]==3


def test_causal_release_and_latest_completion():
    j,b,r=fixture();j=replace(j,submit=2,event=3)
    d=physical_domain(j,b,r)
    assert min(s for s,_ in d.stays)==3
    assert max(s+j.service_slots for s,_ in d.stays)==b.latest_completion
    assert not contains(j,b,r,d,Option(2,'A',(('A',2,4),)))


@pytest.mark.parametrize('change',[{'protected':True},{'qos':'high'},{'qos':'urgent'},{'unknown_arrival':True}])
def test_protected_urgent_high_and_unknown_timing(change):
    j,b,r=fixture();j=replace(j,**change)
    assert physical_starts(j,b)==(j.reference_start,)


def test_running_fixed_history():
    j,b,r=fixture();j=replace(j,state='RUNNING',event=4,elapsed_seconds=900)
    d=physical_domain(j,b,r)
    assert set(d.stays)=={(4,'A')}
    assert not contains(j,b,r,d,Option(4,'B',(('B',4,6),)))


def test_same_site_and_compatible_prestart():
    j,b,r=fixture();d=physical_domain(j,b,r)
    assert (1,'A') in d.stays and (1,'B') in d.stays
    assert contains(j,b,r,d,Option(1,'B',(('B',1,3),)))
    assert not contains(j,b,r,d,Option(1,'C',(('C',1,3),)))
    canonical=Option(1,'A',(('A',1,3),))
    assert not contains(j,b,r,d,replace(canonical,checkpoint=-2))
    assert not contains(j,b,r,d,replace(canonical,destination='B'))


def test_rack_invalid_and_oversized():
    j,b,r=fixture();r.rack_limits['B']=(1,)
    assert all(site=='A' for _,site in physical_domain(j,b,r).stays)
    j=replace(j,gpu=20)
    d=physical_domain(j,b,r)
    assert d.count==0


def test_checkpoint_forbidden_and_wan_infeasible():
    j,b,r=fixture();j=replace(j,service_slots=4)
    assert physical_domain(j,b,r).blocks
    assert not physical_domain(replace(j,checkpoint_authorized=False),b,r).blocks
    r.wan_capacities={}
    assert not physical_domain(j,b,r).blocks


def test_migration_attributes_and_low_priority_are_preserved():
    j,b,r=fixture();j=replace(j,service_slots=4)
    d=physical_domain(j,b,r);option=next(o for o in d if o.migrated)
    assert contains(j,b,r,d,option)
    assert not contains(j,b,r,d,replace(option,wan=()))
    priority=grid_priority(option,j,{('A',t):1 for t in range(12)})
    assert priority['priority']=='LOW_PRIORITY' and not priority['permanent_cut']
    assert contains(j,b,r,d,option)


def test_noflex_anchor_and_independent_nesting():
    j,b,r=fixture();d=physical_domain(j,b,r)
    assert noflex_anchor(j,b,r) in tuple(d)
    result=verify_nesting({'j':j},{'j':b},r,{'j':d})
    assert result['PASS'] and not result['global_noflex_feasibility_claimed']
    d.stays=tuple(k for k in d.stays if k!=(4,'A'))
    assert not verify_nesting({'j':j},{'j':b},r,{'j':d})['PASS']


def test_deterministic_domain_hash_and_class_cardinality():
    from v42_compact.graph import GraphFactory
    j,b,r=fixture();old=GraphFactory(r,b.latest_completion).graph(j,b)
    members={'j':j,'j2':replace(j,uid='j2')}
    data=({},members,{'j':b,'j2':b},r,{}, {'j':old,'j2':old},
          {'j':old,'j2':old},{'classes':{'c':['j','j2']}})
    active,domains=prepare_active(data)
    assert active[7]['classes']==data[7]['classes']
    assert len(active[7]['classes']['c'])==2
    assert active[7]['class_exact_cardinality_preserved']
    assert physical_domain(j,b,r).sha==physical_domain(j,b,r).sha==domains['j'].sha
    broken=(*data[:-1],{'classes':{'c':['j','j']}})
    with pytest.raises(ValueError,match='CARDINALITY'):prepare_active(broken)


def test_lazy_activation_validates_full_attributes():
    from v42_compact.graph import GraphFactory
    j,b,r=fixture();j=replace(j,service_slots=4)
    g=GraphFactory(r,b.latest_completion).graph(j,b)
    data=({}, {'j':j},{'j':b},r,{}, {'j':g},{'j':g},{'classes':{'c':['j']}})
    active,domains=prepare_active(data)
    option=next(o for o in domains['j'] if o.migrated and o.start<j.reference_start)
    expanded=activate_migration(active,domains,{'c':[option]})
    assert option.start in expanded[5]['j'].compatible[option.initial_site,option.checkpoint]
    assert expanded[7]['classes']==active[7]['classes']
    assert expanded[7]['full_migration_domain_active'] is False
    with pytest.raises(ValueError):activate_migration(active,domains,{'c':[replace(option,wan=())]})


def test_safe_duplicate_all_rows_objectives_and_no_heuristic_dominance():
    a=ScientificColumn('a','c','0'*64,(('GPU_A0','2'),('Runtime_A2','1')), (('P1','0'),('P2','1')),True)
    b=replace(a,candidate_id='b')
    different=replace(a,candidate_id='c',rows=a.rows+(('CC4','1/999999999999'),))
    ambiguous=replace(a,candidate_id='d',complete=False)
    report=exact_duplicates([b,a,different,ambiguous])
    assert report['exact_duplicates']=={'b':'a'}
    assert 'c' in report['kept'] and 'd' in report['kept']
    assert report['safe_dominance_count']==0


def test_exact_feasibility_and_improvement_pricing_are_separate():
    column=ScientificColumn('a','c','0'*64,(('GPU','2'),('CARD','1')), (('rho','0'),),True)
    proof=PricingEvidence('FEASIBILITY_RESCUE','0'*64,(('GPU','-1'),),True,'EXACTLY_PROVEN_INFEASIBLE','-1')
    assert price_column(column,proof)['classification']=='CERTIFICATE_BREAKING'
    with pytest.raises(ValueError):price_column(column,replace(proof,restricted_status='TIME_LIMIT'))
    dual=PricingEvidence('IMPROVEMENT_SEARCH','0'*64,(('GPU','-1'),),True,'INDEPENDENTLY_FEASIBLE',objective_name='rho')
    result=scan([column],dual,complete_finite_scan=True)
    assert not result['LP_PRICING_CLOSED']
    verified=replace(dual,lp_direction_coverage_verified=True,
                     lp_direction_coverage_evidence_hash='1'*64,lp_representation='EXACT_PATH_COLUMN_MASTER')
    assert scan([column],verified,complete_finite_scan=True)['LP_PRICING_CLOSED']
    assert not result['INTEGER_DOMAIN_CLOSURE_PROVEN'] and not result['PRODUCTION_DOMAIN_ACCEPTED']
    with pytest.raises(ValueError):scan([],replace(dual,independently_verified=False),complete_finite_scan=True)


def test_future_information_rejected():
    issue='2025-05-09T18:00:00+00:00'
    assert require_causal_information([{'available_at':issue,'request_gpu':2}],issue)
    with pytest.raises(PermissionError,match='FUTURE_INFORMATION'):
        require_causal_information([{'available_at':'2025-05-10T18:00:00+00:00'}],issue)
    with pytest.raises(PermissionError,match='FUTURE_INFORMATION'):
        require_causal_information([{'available_at':issue,'actual_end':5}],issue)


def test_old_shift_coefficients_unchanged_new_shift_is_magnitude():
    j,b,r=fixture()
    assert all(abs(s-j.reference_start)==s-j.reference_start for s in b.allowed_starts)
    from v42_compact.formulation import intervention
    metrics=intervention(j,dict(q={},y={('A',1):1}))
    assert metrics[1].getConstant()==3
