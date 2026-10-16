"""Four-unit arithmetic fixtures only; no Gurobi model or OpenDSS work."""
from copy import deepcopy
from types import SimpleNamespace
import sys

import numpy as np
import pytest
from scipy import sparse

from v43_mess.library import load,current_identity
from v42_native.contracts import digest
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha


def example():
    names=[]
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        names += [f'arc[{unit},0]',f'SOC[{unit},0]',f'Pch[{unit},IDC00,0]',
            f'Pdis[{unit},IDC00,0]',f'Q[{unit},IDC00,0]']
        names += [f'charge_mode[{unit},{t}]' for t in range(96)]
    names += ['injection_P[IDC00,0]','response_P[0]','rho_max']
    columns={n:j for j,n in enumerate(names)}
    rows=[];rhs=[];sense=[];terms=[]
    def add(name,values,bound,sign='<'):
        i=len(rows);rows.append(name);rhs.append(bound);sense.append(sign)
        terms.extend((i,columns[n],v) for n,v in values.items())
    inject={'injection_P[IDC00,0]':1.}
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        add('flow['+unit+',0]',{f'arc[{unit},0]':1.},1.,'=')
        inject[f'Pch[{unit},IDC00,0]']=1.;inject[f'Pdis[{unit},IDC00,0]']=-1.
    add('injection_P_binding[IDC00,0]',inject,0.,'=')
    add('response_P_binding[0]',{'response_P[0]':1.,'injection_P[IDC00,0]':-.3},0.,'=')
    for t in range(96):
        add(f'line_thermal_face[{t},0,0]',{'response_P[0]':.1,'rho_max':-1.},-.6+t*.0001)
    i,j,v=zip(*terms)
    A=sparse.coo_matrix((v,(i,j)),shape=(len(rows),len(names))).tocsr()
    types=np.array(['B' if n.startswith(('arc[','charge_mode[')) else 'C' for n in names])
    objective=np.zeros(len(names));objective[-1]=1.
    lower=np.zeros(len(names));lower[-3:-1]=-2.
    upper=np.ones(len(names));upper[-3:-1]=2.
    d=dict(names=np.array(names),lower=lower,upper=upper,types=types,objective=objective,
        constant=np.array(0.),rhs=np.array(rhs),sense=np.array(sense),row_names=np.array(rows))
    ident=dict(schema='V43_MAY01_FIXED_AIDC_MESS_CASE_V1',day='2025-05-01',arm='B2',stage='M1',
        source_sha=digest('NAMED_FIXTURE_SOURCE_NOT_PRODUCTION'),parent_case_sha=digest('NAMED_REFERENCE'),
        aidc_anchor=digest('NAMED_AIDC'),original_matrix_sha=matrix_sha(A),original_domain_sha=_domain_sha(d))
    return SimpleNamespace(original_A=A,original_d=d,identity=ident,case_sha=digest(ident),
        bundle=dict(day='2025-05-01'),lift=lambda x:x.copy(),coefficients=[SimpleNamespace(
            node_names=('fixture.1',),branch_names=('line.fixture::1',),transformer_ratings=(100.,))])


def test_loading_preserves_import_path_and_excludes_historical_globals():
    before=list(sys.path)
    modules=load()
    assert before==sys.path
    assert modules['m_engine'].APPROVED_JOINT_PARAMETERS['Threads']==1
    assert modules['m_adaptive'].JOINT_CAP_SECONDS==140.
    oracle=sys.modules['tools.critical_grid_cg.oracle']
    verifier=sys.modules['tools.critical_grid_cg.verify']
    for module in (oracle,verifier):
        assert not any(k in vars(module) for k in ('SAVED','CASE','UB','LB_OLD','ROOT','COEFFICIENTS'))


def test_seedless_k16_keeps_four_units_and_384_modes_without_a_point(tmp_path):
    k=load()['table_v_k48'];case=example()
    packet,proof=k.prepare_k16(case,None,tmp_path/'K16')
    assert proof['PASS'] and proof['original_domain_projection_included']
    assert proof['independent_original_geometry_replayed']
    assert packet['start'] is None and packet['full_start'] is None
    assert proof['current_FULL_UB'] is None and proof['Native_optimize_calls']==0
    assert sum(n.startswith('charge_mode[') for n in packet['d']['names'])==384
    assert {n.split('[',1)[1].split(',')[0] for n in packet['d']['names'] if n.startswith('arc[')}=={
        'MESS01','MESS02','MESS03','MESS04'}


def test_nested_original_k32_k48_inclusion_does_not_promote_a_bound(tmp_path):
    k=load()['table_v_k48'];case=example()
    packet,proof=k.prepare_k16(case,None,tmp_path/'K16')
    search=np.zeros(len(packet['columns']))
    for expected in (32,48):
        cuts,separation=k.separate(case,packet,search)
        assert separation['selected_count']==16
        previous=packet
        packet,proof=k.append_cuts(case,packet,cuts,tmp_path/('K'+str(expected)))
        assert proof['K']==expected and proof['PASS']
        assert (packet['A'][:previous['A'].shape[0]]!=previous['A']).nnz==0
    summary=k.summarize_current_k48(packet,proof,[])
    assert summary['K48_cuts_reached'] and not summary['K48_completed']
    assert summary['Global_LB'] is None and summary['current_FULL_UB'] is None


@pytest.mark.parametrize('field',('grid_row','bound','type','objective','aidc_anchor'))
def test_current_full_or_projected_packet_tampering_is_rejected(tmp_path,field):
    k=load()['table_v_k48'];case=example()
    packet,_=k.prepare_k16(case,None,tmp_path/'K16')
    altered=deepcopy(packet)
    if field=='grid_row':altered['A'].data[-1]+=.01
    if field=='bound':altered['d']['upper'][0]=.5
    if field=='type':altered['d']['types'][0]='C'
    if field=='objective':altered['d']['objective'][0]=1.
    if field=='aidc_anchor':altered['source']['aidc_anchor']=digest('OTHER_CASE')
    with pytest.raises(ValueError):k.verify_packet(case,altered)


def test_may02_and_forged_old_d0_identity_are_not_authorized():
    case=example();case.identity['day']='2025-05-02';case.bundle['day']='2025-05-02';case.case_sha=digest(case.identity)
    with pytest.raises(ValueError,match='MAY01'):current_identity(case)
    case=example();case.identity['schema']='TABLE_V_D0_CASE';case.case_sha=digest(case.identity)
    with pytest.raises(ValueError,match='EXPLICIT_CURRENT_CASE'):current_identity(case)


def test_global_control_binds_v43_source_without_fabricating_d0():
    case=example();module=load()['table_v_global_control']
    control=module.GlobalGapControl(module.mess_scope(case),.03)
    assert module.mess_upper(control,case,SimpleNamespace(best=None)) is False
    assert 'D0_source_sha' not in case.identity


def test_real_m_budget_gate_rejects_duck_typed_fixture():
    from v43_mess.budget import require_budget
    with pytest.raises(PermissionError,match='REAL_M_STAGE_BUDGET'):
        require_budget(SimpleNamespace(kind='K48_SEPARATE',inflight=None),'K48_SEPARATE')
