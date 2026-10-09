"""Native-zero current-date M adapter and lossless-transport attacks."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from scipy import sparse

from v42_supercompact.formulation import Compact
from v42_supercompact.presolve import Presolve
from v42_may_campaign.m_model import verify_transport
from v42_m1_research.ub import binary_inventory


@pytest.fixture
def current_case():
    sites=('A','B');units=('MESS01','MESS02','MESS03','MESS04');H=2
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(H)]
    arcs.append(('A',0,'B',1,SimpleNamespace(route_id='current_day_move')))
    names=[f'arc[{u},{k}]' for u in units for k in range(len(arcs))]+['rho_max']
    byname={n:j for j,n in enumerate(names)};rows=[];rhs=[];sense=[];labels=[]
    for unit in units:
        for site in sites:
            for t in range(H):
                row=np.zeros(len(names))
                for k,a in enumerate(arcs):
                    j=byname[f'arc[{unit},{k}]']
                    if a[:2]==(site,t):row[j]+=1
                    if a[2:4]==(site,t):row[j]-=1
                rows.append(row);rhs.append(float(site=='A' and t==0));sense.append('=');labels.append('flow')
        row=np.zeros(len(names))
        for k,a in enumerate(arcs):
            if a[3]==H:row[byname[f'arc[{unit},{k}]']]=1
        rows.append(row);rhs.append(1.);sense.append('=');labels.append('terminal_location')
    row=np.zeros(len(names));row[-1]=-1
    rows.append(row);rhs.append(-.5);sense.append('<');labels.append('line_thermal_face[0,0,0]')
    A=sparse.csr_matrix(np.asarray(rows));d=dict(names=np.asarray(names),lower=np.zeros(len(names)),
        upper=np.ones(len(names)),types=np.asarray(['B']*(len(names)-1)+['C']),
        objective=np.r_[np.zeros(len(names)-1),1.],constant=np.asarray(0.),rhs=np.asarray(rhs),
        sense=np.asarray(sense),row_names=np.asarray(labels))
    compact=Compact(A,d,arcs,{u:'A' for u in units},H)
    presolve=Presolve(compact.A,compact.d);presolve.run()
    original=np.zeros(len(names));original[-1]=.5
    for unit in units:
        original[byname[f'arc[{unit},0]']]=original[byname[f'arc[{unit},1]']]=1.
    point=presolve.forward(compact.forward(original))
    case=SimpleNamespace(A=presolve.A,d=presolve.d,original_A=A,original_d=d,
        identity=dict(binary_count=int(np.count_nonzero(presolve.d['types']=='B'))),case_sha='fresh_May02_case',
        point=point,graph=(sites,{u:'A' for u in units},arcs,SimpleNamespace(maximum=100.),{}),
        lift=lambda p:compact.inverse(presolve.inverse(p)))
    return case,compact,presolve


def test_current_date_lossless_transport_calls_no_solver(current_case):
    case,compact,presolve=current_case
    receipt=verify_transport(compact,presolve)
    assert receipt['PASS'] and receipt['Native_optimize_calls']==0
    assert receipt['integer_and_full_LP_domains_identical']
    assert receipt['C3A_policy']=='KEEP_ALL_REGENERATED_C2_ROWS'
    assert receipt['exact_aliases_checked']>0 and receipt['deleted_row_implications_checked']>0


@pytest.mark.parametrize('attack',['original_coefficient','retained_coefficient','objective','alias','bound','flow','deleted_proof'])
def test_lossless_proof_rejects_current_case_mutations(current_case,attack):
    _,compact,presolve=current_case
    if attack=='original_coefficient':compact.A.data[0]=2.
    elif attack=='retained_coefficient':presolve.A.data[0]=np.nextafter(presolve.A.data[0],np.inf)
    elif attack=='objective':presolve.d['objective'][-1]=.75
    elif attack=='alias':presolve.steps[0]['constant']+=.1
    elif attack=='bound':presolve.d['upper'][0]=.5
    elif attack=='flow':
        compact.original_data['rhs'][0]=.5;compact.d['rhs'][0]=.5
    else:presolve.rows.pop()
    with pytest.raises(ValueError,match='CURRENT_M_'):verify_transport(compact,presolve)


def test_binary_guard_defaults_remain_historical_and_current_axis_is_explicit(current_case):
    case,_,_=current_case
    with pytest.raises(ValueError,match='COUNT_DRIFT'):binary_inventory(case.d)
    rows=binary_inventory(case.d,expected_count=case.identity['binary_count'])
    assert len(rows)==case.identity['binary_count']
    with pytest.raises(ValueError,match='COUNT_DRIFT'):
        binary_inventory(case.d,expected_count=case.identity['binary_count']+1)


def test_current_axis_candidate_replays_original_rows_without_rounding(current_case,monkeypatch):
    from v42_m1_research import check_ub
    case,_,_=current_case
    monkeypatch.setattr(check_ub,'physical_replay',lambda case,point:dict(PASS=True,Native_optimize_calls=0))
    receipt=check_ub.validate_candidate(case,case.point)
    assert receipt['PASS'] and receipt['expected_original_binary_count']==case.identity['binary_count']
    assert receipt['raw_point_unchanged'] and receipt['all_original_C3A_binaries_correspond']
    case.identity['binary_count']+=1
    with pytest.raises(ValueError,match='COUNT_AUTHORITY_DRIFT'):check_ub.validate_candidate(case,case.point)


def test_current_hybrid_selection_reuses_original_dynamic_axes(current_case,monkeypatch):
    from v42_m1_anytime import algorithms
    case,_,_=current_case
    monkeypatch.setattr(algorithms.neighborhood,'_moves',lambda case,point:[])
    target=dict(site='A',slot=1,numeric_score=1.)
    spec=algorithms.select(case,case.point,'U1',0,([target],dict(active_voltage_observations=[])),context={})
    assert spec['case_sha']==case.case_sha
    assert spec['original_binary_columns']==case.identity['binary_count']
    assert spec['full_original_flow_route_SOC_rows_and_arcs_preserved']
    assert len(spec['free_binary_columns'])>0


def test_same_day_master_never_loads_historical_column(current_case,tmp_path,monkeypatch):
    from v42_m1_anytime import algorithms
    from v42_m1_hybrid.blocks import build_blocks
    case,_,_=current_case;decomp=build_blocks(case)
    monkeypatch.setattr(algorithms.pricing,'validate_local_column',lambda *args:dict(PASS=True))
    seen={}
    def master(case,decomp,columns,ledger,path,seconds):
        seen.update(columns)
        return dict(identity=dict(column_count_by_unit={u:1 for u in decomp.units}))
    monkeypatch.setattr(algorithms.dw,'run',master)
    monkeypatch.setattr(np,'load',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('FORBIDDEN_HISTORICAL_READ')))
    result=algorithms.feedback_master(case,decomp,case.point,None,tmp_path,context=dict(seed_columns={}))
    assert result['identity']['column_count_by_unit']=={u:1 for u in decomp.units}
    assert seen=={u:[] for u in decomp.units}


def test_context_default_does_not_mutate_historical_case_or_projection_authority():
    from v42_m1_anytime import algorithms,core
    from v42_m1_research import projection_rows
    assert core.CASE=='cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a'
    assert projection_rows.FIXED_ROWS==(438197,465244,492778,520001,546995,570130,439268,548296)
    assert algorithms.feedback_master.__kwdefaults__=={'context':None}


def test_grid_row_labels_materialize_pending_original_normalamps_names():
    from types import SimpleNamespace
    from v42_may_campaign.m_model import _label_grid
    class Row:
        def __init__(self, name, coefficients):
            self.ConstrName=name; self.coefficients=coefficients
    original=Row('transformer_current', (1., 2., 3.))
    omitted=Row('NormalAmps[0,transformer.mess_idc01_tx::a]', (4., 5.))
    class Model:
        updates=0
        def update(self):
            self.updates+=1
            original.ConstrName='NormalAmps[0,transformer.main_tx::a]'
        def getConstrs(self): return [original, omitted]
    model=Model()
    c=SimpleNamespace(voltage_constant=[], branch_names=['transformer.main_tx::a',
        'transformer.mess_idc01_tx::a'], transformer_ratings=[None,None])
    _label_grid(model, 0, [c], [])
    assert model.updates==2
    assert original.ConstrName=='NormalAmps[0,transformer.main_tx::a]'
    assert omitted.ConstrName=='NormalAmps[0,transformer.mess_idc01_tx::a]'
    assert original.coefficients==(1.,2.,3.) and omitted.coefficients==(4.,5.)


def _identical_affine_case(current_case,unbounded=False):
    _,old,_=current_case
    A=old.original;d=deepcopy(old.original_data);n=A.shape[1]
    # Two distinct original response bindings have identical multivariate
    # affine expressions. Existing Presolve stores their equality as j=k.
    rows=np.zeros((4,n+3))
    rows[0,n+1]=rows[1,n+2]=1.
    rows[0,n]=rows[1,n]=-2.
    rows[0,n-1]=rows[1,n-1]=-3.
    rows[2,n+1]=rows[3,n+2]=1.
    A=sparse.vstack((sparse.hstack((A,sparse.csr_matrix((A.shape[0],3)))),sparse.csr_matrix(rows)),format='csr')
    d.update(names=np.r_[d['names'],['Q[MESS01,A,0]','response_line_P[0,0]','response_line_P[0,1]']],
        types=np.r_[d['types'],['C']*3],lower=np.r_[d['lower'],[0.,-np.inf if unbounded else -100.,-np.inf if unbounded else -100.]],
        upper=np.r_[d['upper'],[1.,np.inf if unbounded else 100.,np.inf if unbounded else 100.]],objective=np.r_[d['objective'],[0.]*3],
        rhs=np.r_[d['rhs'],[1.,1.,20.,30.]],sense=np.r_[d['sense'],['=','=','<','<']],
        row_names=np.r_[d['row_names'],['response_line_P_binding[0,0]','response_line_P_binding[0,1]','consumer1','consumer2']])
    compact=Compact(A,d,old.arcs,old.initial,old.H)
    presolve=Presolve(compact.A,compact.d);presolve.run()
    return compact,presolve


def test_duplicate_multivariate_affine_bindings_use_two_exact_original_equalities(current_case):
    compact,presolve=_identical_affine_case(current_case)
    receipt=verify_transport(compact,presolve)
    assert receipt['PASS'] and receipt['exact_identical_affine_binding_witnesses_checked']==1
    assert receipt['integer_and_full_LP_domains_identical'] and receipt['Native_optimize_calls']==0


def test_affine_duplicate_witness_rejects_distinct_original_definition(current_case):
    compact,presolve=_identical_affine_case(current_case)
    step=next(s for s in presolve.steps if s['name']=='response_line_P[0,1]')
    row=step['defining_row']
    compact.d['rhs'][row]+=1/1024
    compact.original_data['rhs'][row]+=1/1024
    with pytest.raises(ValueError,match='CURRENT_M_EXACT_ELIMINATION_EQUATION_DRIFT') as info:
        verify_transport(compact,presolve)
    assert info.value.transport_diagnostic['step']['name']=='response_line_P[0,1]'
    assert info.value.transport_diagnostic['exact_affine_duplicate_witness_not_found']


def test_deleted_row_implication_cannot_certify_itself(current_case):
    _,compact,presolve=current_case
    certificate=presolve.rows[0]
    certificate.update(kind='EXACT_PROPORTIONAL_IMPLICATION',representative=certificate['row'])
    with pytest.raises(ValueError,match='CURRENT_M_DELETED_ROW_IMPLICATION_CYCLE'):
        verify_transport(compact,presolve)


def test_unbounded_original_affine_aliases_preserve_extended_rational_box(current_case):
    compact,presolve=_identical_affine_case(current_case,unbounded=True)
    receipt=verify_transport(compact,presolve)
    assert receipt['PASS'] and receipt['exact_identical_affine_binding_witnesses_checked']==1
    assert np.isneginf(compact.original_data['lower']).any()
    assert np.isposinf(presolve.d['upper']).any()


def test_infinite_box_endpoint_never_rounds_small_exact_coefficient_to_zero():
    from fractions import Fraction
    from v42_may_campaign.m_model import _scaled_bound, _sum_bound
    tiny=Fraction(1,2**2000)
    assert float(tiny)==0.
    assert _scaled_bound(tiny,np.inf)==np.inf
    assert _scaled_bound(-tiny,np.inf)==-np.inf
    assert _scaled_bound(tiny,-np.inf)==-np.inf
    assert _sum_bound(Fraction(5),-np.inf)==-np.inf
    with pytest.raises(ValueError,match='OPPOSITE_INFINITE_INTERVAL'):
        _sum_bound(-np.inf,np.inf)


def _cached_case(current_case,tmp_path):
    from v42_may_campaign.m_model import _freeze_transport,_domain_sha
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_native.contracts import digest
    case,compact,presolve=current_case
    proof=verify_transport(compact,presolve)
    case.output=tmp_path;case.compact=compact;case.presolve=presolve
    case.bundle=dict(day='2025-05-02');case.anchor=dict(day='2025-05-02',PCC_P_kw=[[1.]])
    case.identity.update(original_matrix_sha=matrix_sha(case.original_A),original_domain_sha=_domain_sha(case.original_d),
        selected_matrix_sha=matrix_sha(case.A),selected_domain_sha=_domain_sha(case.d),
        bundle_sha=digest(case.bundle),anchor_sha=digest(case.anchor),transport=proof,
        transport_authority=_freeze_transport(compact,presolve,case.graph,proof,tmp_path))
    case.case_sha=digest(case.identity)
    return case


def test_same_case_proof_reuse_checks_all_state_bytes_without_second_full_replay(current_case,tmp_path,monkeypatch):
    from v42_may_campaign import m_model
    case=_cached_case(current_case,tmp_path)
    monkeypatch.setattr(m_model,'verify_transport',lambda *a:(_ for _ in ()).throw(AssertionError('UNNECESSARY_REPLAY')))
    receipt=m_model.verify_case(case)
    assert receipt['PASS'] and receipt['proof_reused_after_all_transport_state_SHA_checks']


@pytest.mark.parametrize('attack',['alias','graph','compact_matrix','proof_packet'])
def test_proof_reuse_rejects_transport_state_or_packet_mutation(current_case,tmp_path,attack):
    from v42_may_campaign.m_model import verify_case
    case=_cached_case(current_case,tmp_path)
    if attack=='alias':case.presolve.steps[0]['constant']+=1/1024
    elif attack=='graph':case.compact.arcs[0]=('B',0,'B',1,None)
    elif attack=='compact_matrix':case.compact.A.data[0]+=1/1024
    else:(tmp_path/'ORIGINAL_DOMAIN_EQUIVALENCE.json').write_text('{"PASS":true}')
    with pytest.raises(ValueError,match='CURRENT_M_TRANSPORT_STATE_BYTES_DRIFT|CURRENT_M_TRANSPORT_PROOF_PACKET_DRIFT'):
        verify_case(case)
