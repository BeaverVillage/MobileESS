"""No optimizer/model: exact structural masks, fractional-SOC guard and mutations."""
from dataclasses import dataclass, replace
from fractions import Fraction as F
import pytest
from v42_native.contracts import digest, ContractError
from v42_native.mess_domain import build_domain, verify_domain, _cached, _outward

@dataclass(frozen=True)
class Battery:
    minimum:float=440.
    maximum:float=1080.
    initial:float=760.
    terminal:float=760.
    p_limit:float=300.
    pcs_kva:float=400.
    eta_charge:float=.95
    eta_discharge:float=.95
    dt_hours:float=.25
    def validate(self):assert self.dt_hours==.25

@dataclass(frozen=True)
class Route:
    source:str
    depart:int
    destination:str
    connect:int
    energy_kwh:float
    authority_sha256:str='a'*64
    def validate(self,H):assert self.source!=self.destination and 0<=self.depart<self.connect<H and self.energy_kwh>=0

def domain(routes=(),H=8,initial=None):
    return build_domain(('A','B'),{'MESS01':'A'} if initial is None else initial,routes,Battery(),H)

def reseal(value):return replace(value,state_sha=digest(value.scientific_state()))

def test_forward_reachability_matches_original_constructor_and_backward_adds_zero():
    value=domain((Route('A',2,'B',4,10.),Route('B',5,'A',7,10.)))
    reachable={('A',0)}
    for t in range(value.horizon):
        for s,start,d,end,r in value.arcs:
            if start==t and (s,start) in reachable:reachable.add((d,end))
    old=tuple(k for k,a in enumerate(value.arcs) if a[:2] in reachable)
    assert value.units[0].retained==old
    assert not [p for p in value.units[0].removals if p[1]=='BACKWARD_DEAD_END']
    assert verify_domain(value)['original_integer_and_fractional_LP_zero_masks_verified'] is True

def test_no_integer_only_SOC_arc_pruning_and_fractional_counterexample():
    value=domain((Route('A',0,'B',1,640.),))
    route_index=2*value.horizon
    unit=value.units[0]
    assert route_index in unit.retained
    assert unit.path_soc_rejections
    # Integer arc1 violates Emin. Fractional arc1/2 + stay1/2 remains feasible:
    # charge150 in the source at t0, then recharge both stay branches later.
    c=F(float(.25*.95));soc1=F(760)-F(640)/2+c*150
    assert F(760)-F(640)<F(440)<=soc1<F(760)
    remaining=(F(760)-soc1)/c
    assert 0<remaining<300*4
    assert unit.receipt()['SOC_arc_deletions_applied']==0
    assert unit.receipt()['SOC_bound_changes_applied']==0

def test_all_input_actions_and_exact_parallel_routes_preserved():
    first=Route('A',2,'B',4,10.)
    second=replace(first,energy_kwh=11.,authority_sha256='b'*64)
    value=domain((first,first,second))
    assert len(value.arcs)==2*value.horizon+2
    assert all(k in value.units[0].retained for k in range(2*value.horizon,len(value.arcs)))
    assert len(value.units[0].slots)==8
    assert all(row[5]==row[6]==row[7]==row[2] for row in value.units[0].slots)

def test_mask_removal_and_unsupported_addition_rejected_even_with_resealed_digest():
    value=domain((Route('A',2,'B',4,10.),));unit=value.units[0]
    missing=replace(unit,retained=unit.retained[1:])
    with pytest.raises(ContractError,match='MASK_DRIFT'):verify_domain(reseal(replace(value,units=(missing,))))
    bad=next(k for k in range(len(value.arcs)) if k not in unit.retained)
    extra=replace(unit,retained=tuple(sorted(unit.retained+(bad,))))
    with pytest.raises(ContractError,match='MASK_DRIFT'):verify_domain(reseal(replace(value,units=(extra,))))

def test_SOC_and_slot_metadata_mutations_rejected_even_with_resealed_digest():
    value=domain();unit=value.units[0];soc=list(unit.global_soc)
    t,lo,hi=soc[1];soc[1]=(t,lo+1,hi)
    mutated=replace(unit,global_soc=tuple(soc))
    with pytest.raises(ContractError,match='GLOBAL_SOC_DIAGNOSTIC_DRIFT'):
        verify_domain(reseal(replace(value,units=(mutated,))))
    slots=list(unit.slots);row=list(slots[0]);row[5]+=1;slots[0]=tuple(row)
    with pytest.raises(ContractError,match='SLOT_COUNTS_DRIFT'):
        verify_domain(reseal(replace(value,units=(replace(unit,slots=tuple(slots)),))))

def test_binary_rational_outward_bounds_and_subnormal():
    for value in (F(1,10),-F(1,10),F(1,1<<1075),-F(1,1<<1075)):
        assert F(_outward(value,True))<=value<=F(_outward(value,False))

def test_input_cache_state_excludes_wall_grid_anchor_and_points():
    _cached.cache_clear();first=domain();second=domain()
    assert first.cache_hit is False and second.cache_hit is True
    assert first.state_sha==second.state_sha
    cosmetic=replace(second,producer_wall_seconds=123.,lookup_wall_seconds=456.,cache_hit=False)
    assert digest(cosmetic.scientific_state())==second.state_sha
    assert verify_domain(cosmetic)['PASS']

def test_four_units_96_slots_original_physical_axes():
    value=domain((Route('A',2,'B',4,10.),),H=96,initial={f'MESS0{i}':'A' for i in range(1,5)})
    assert len(value.units)==4
    assert all(len(unit.slots)==96 and len(unit.global_soc)==97 for unit in value.units)
    receipt=value.receipt()
    assert receipt['native_optimize_calls']==0
    assert all(unit['SOC_arc_deletions_applied']==0 for unit in receipt['units'])

def original_row_fixture(value):
    """A tiny unit-flow/SOC matrix, independent of any model constructor."""
    import numpy as np
    from scipy import sparse
    unit=value.units[0];H=value.horizon;names=[];lower=[];upper=[];types=[]
    def variable(name,lo,hi,kind='C'):
        names.append(name);lower.append(lo);upper.append(hi);types.append(kind)
    for k in unit.retained:variable(f'arc[{unit.mess},{k}]',0,1,'B')
    for k in unit.retained:
        site,t,_,_,route=value.arcs[k]
        if route is None:
            for family in ('Pch','Pdis','Q'):
                variable(f'{family}[{unit.mess},{site},{t}]',-400 if family=='Q' else 0,
                    400 if family=='Q' else 300)
    for t in range(H+1):variable(f'SOC[{unit.mess},{t}]',440,1080)
    lookup={name:j for j,name in enumerate(names)};rows=[];rhs=[];families=[]
    def constraint(family,terms,bound):
        rows.append({lookup[name]:weight for name,weight in terms.items() if weight})
        rhs.append(bound);families.append(family)
    for site in value.sites:
        for t in range(H):
            terms={}
            for k in unit.retained:
                s,start,d,end,_=value.arcs[k];weight=int((s,start)==(site,t))-int((d,end)==(site,t))
                if weight:terms[f'arc[{unit.mess},{k}]']=weight
            constraint('flow',terms,int((site,t)==(unit.origin,0)))
    constraint('terminal_location',{f'arc[{unit.mess},{k}]':1 for k in unit.retained if value.arcs[k][3]==H},1)
    constraint('initial_SOC',{f'SOC[{unit.mess},0]':1},760)
    constraint('terminal_SOC',{f'SOC[{unit.mess},{H}]':1},760)
    for t in range(H):
        terms={f'SOC[{unit.mess},{t+1}]':1,f'SOC[{unit.mess},{t}]':-1}
        for k in unit.retained:
            site,start,_,_,route=value.arcs[k]
            if start!=t:continue
            if route is None:
                terms[f'Pch[{unit.mess},{site},{t}]']=-float(.25*.95)
                terms[f'Pdis[{unit.mess},{site},{t}]']=float(.25/.95)
            elif route.energy_kwh:terms[f'arc[{unit.mess},{k}]']=route.energy_kwh
        constraint('energy_balance',terms,0)
    A=sparse.csr_matrix((len(rows),len(names)),dtype=float).tolil()
    for i,terms in enumerate(rows):
        for j,w in terms.items():A[i,j]=w
    return A.tocsr(),dict(names=np.asarray(names),lower=np.asarray(lower,float),upper=np.asarray(upper,float),
        types=np.asarray(types),rhs=np.asarray(rhs,float),sense=np.asarray(['=']*len(rows)),row_names=np.asarray(families))

def test_actual_original_rows_bridge_and_departure_debit_mutation():
    from v42_native.mess_domain_verify import verify_original_rows
    value=domain((Route('A',0,'B',2,10.),),H=4);A,d=original_row_fixture(value)
    proof=verify_original_rows(value,A,d)
    assert proof['PASS'] and proof['actual_original_matrix_row_bridge_required'] is False
    assert proof['actual_original_flow_rows_checked']==8 and proof['actual_original_energy_rows_checked']==4
    j=list(d['names']).index('arc[MESS01,8]');i=list(d['row_names']).index('energy_balance')
    shifted=A.tolil();shifted[i,j]=0;shifted[i+1,j]=10
    with pytest.raises(ContractError,match='ENERGY_DEBIT_OR_COEFFICIENT_DRIFT'):
        verify_original_rows(value,shifted.tocsr(),d)

def test_actual_original_nonnegative_unit_flow_mutation_rejected():
    from v42_native.mess_domain_verify import verify_original_rows
    value=domain(H=4);A,d=original_row_fixture(value)
    d['lower']=d['lower'].copy();d['lower'][0]=-1
    with pytest.raises(ContractError,match='NONNEGATIVE_ARC_BOX'):verify_original_rows(value,A,d)
    A,d=original_row_fixture(value);changed=A.tolil();changed[0,0]=2
    with pytest.raises(ContractError,match='UNIT_DAG_FLOW_DRIFT'):verify_original_rows(value,changed.tocsr(),d)
