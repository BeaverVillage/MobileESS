"""A fresh process reloads actual selected C3A mathematical packets, no solve."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import shutil
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from test_v42_current_exact_c3a import fixture
from v42_b3_joint.m_source import MSourceBridge, _plain
from v42_may_campaign_native90 import m_model
from v42_native.mess import RouteArc, Battery
from v42_pr134_b1.common import atomic, digest, read, record
from v42_ultracompact.current import POLICY


def save_packet(folder):
    ultra, graph, compact, presolve = fixture(H=96)
    A, data = compact.original, compact.original_data
    c3 = m_model._freeze_c3(ultra, folder)
    proof = dict(m_model.verify_transport(compact,presolve),C3A_policy=POLICY,
        selected_C3A_independent_proof_PASS=ultra.proof['PASS'],
        selected_C3A_rows_removed=ultra.proof['removed_rows'],
        selected_C3A_bounds_tightened=ultra.proof['bounds_tightened'],
        selected_C3A_original_P1_bit_exact=ultra.proof['original_P1_bit_exact'],
        selected_C3A_integer_and_full_LP_domains_identical=ultra.proof['integer_and_full_LP_domains_identical'])
    transport = m_model._freeze_transport(compact,presolve,graph,proof,folder)
    bundle={'day':'2025-05-01','pure_mathematical_fixture':True};anchor={'fixed_input_fixture':True}
    identity=dict(original_matrix_sha=m_model.matrix_sha(A),original_domain_sha=m_model._domain_sha(data),
        selected_matrix_sha=m_model.matrix_sha(ultra.A),selected_domain_sha=m_model._domain_sha(ultra.d),
        bundle_sha=digest(bundle),anchor_sha=digest(anchor),C3A_policy=POLICY,
        transport=proof,transport_authority=transport,c3_authority=c3)
    packet=dict(graph=_plain(graph),graph_sha=digest(_plain(graph)),case_identity=identity,
        case_sha=digest(identity),raw_point=np.zeros(ultra.A.shape[1]).tolist(),anchor=anchor,
        planning_arrays={},bundle=bundle)
    sparse.save_npz(folder/'FULL_A.npz',A);np.savez_compressed(folder/'FULL_DATA.npz',**data)
    sparse.save_npz(folder/'C3A_A.npz',ultra.A);np.savez_compressed(folder/'C3A_DATA.npz',**ultra.d)
    atomic(folder/'RESTORE_PACKET.json',packet)
    return packet


def restore(folder):
    folder=Path(folder);packet=read(folder/'RESTORE_PACKET.json');graph=packet['graph']
    routes=tuple(RouteArc(**arc[-1]) for arc in graph[2] if arc[-1] is not None)
    battery=Battery(**graph[3]) if 'dt_hours' in graph[3] else SimpleNamespace(**graph[3])
    native=(tuple(graph[0]),graph[1],routes,battery,graph[4])
    class Registry:
        def resolve(self,module):return importlib.import_module(module)
        def callable(self,module,symbol):
            if module=='v42_bootstrap/m1.py' and symbol=='native_inputs':return lambda bundle:native
            return getattr(self.resolve(module.removesuffix('.py').replace('/','.')),symbol)
    context=SimpleNamespace(output=folder,source_registry=Registry(),original_bundle=packet['bundle'],
        request=SimpleNamespace(stage='M1',request_sha='a'*64,authority=SimpleNamespace(day='2025-05-01')),
        grid_authority=SimpleNamespace(coefficients=lambda *args:[SimpleNamespace(**v) for v in packet.get('fixture_coefficients',[])]))
    bridge=MSourceBridge();case=bridge._restore_case(context,packet)
    assert case.ultra is not None and case.A.shape[0]<case.presolve.A.shape[0]
    assert case.ultra.physical_original is case.original_A
    assert case.identity['selected_matrix_sha']==m_model.matrix_sha(case.A)
    assert case.identity['selected_domain_sha']==m_model._domain_sha(case.d)
    if case.response is None:
        assert any(case.ultra.d['upper']<case.presolve.d['upper'])
    else:
        assert case.presolve.current_security['bounds']
    assert m_model.verify_case(case)['PASS']
    return case


@pytest.fixture(scope='module')
def sealed_packet(tmp_path_factory):
    folder=tmp_path_factory.mktemp('actual_C3A_mathematical_packet')
    save_packet(folder)
    return folder


def copy_packet(source,folder):
    # Construct/prove the 96-slot fixture once. Each attack receives independent
    # file bytes and correctly rebinds its own receipt paths before mutation.
    shutil.copytree(source,folder,dirs_exist_ok=True)
    packet=read(folder/'RESTORE_PACKET.json');identity=packet['case_identity']
    identity['transport_authority']['certificate']=record(folder/'ORIGINAL_DOMAIN_EQUIVALENCE.json')
    identity['c3_authority']['certificate']=record(folder/'CURRENT_EXACT_C3A_PROOF.json')
    for name,filename in (('response_authority','DENSE_RESPONSE_EQUIVALENCE.json'),
            ('physical_prescreen_authority','EXACT_PHYSICAL_PRESCREEN.json'),
            ('grid_prescreen_authority','EXACT_GRID_OUTER_PRESCREEN.json')):
        if name in identity:identity[name]['certificate']=record(folder/filename)
    packet['case_sha']=digest(identity);atomic(folder/'RESTORE_PACKET.json',packet)


def test_selected_c3a_packet_roundtrip_in_fresh_process(tmp_path,sealed_packet):
    copy_packet(sealed_packet,tmp_path)
    code="import sys;sys.path.insert(0,'tests');from test_v42_b3_current_c3a_restore import restore;restore(sys.argv[1]);print('SELECTED_C3A_DURABLE_RESTORE_PASS')"
    result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'SELECTED_C3A_DURABLE_RESTORE_PASS' in result.stdout


@pytest.mark.parametrize('attack',('selected_matrix','selected_bound','proof','row_certificate','row_axis','column_axis','source_sha'))
def test_selected_c3a_restore_rejects_durable_packet_tampering(tmp_path,attack,sealed_packet):
    copy_packet(sealed_packet,tmp_path)
    if attack=='selected_matrix':
        path=tmp_path/'C3A_A.npz';A=sparse.load_npz(path);A.data[0]*=2;sparse.save_npz(path,A)
    elif attack=='selected_bound':
        path=tmp_path/'C3A_DATA.npz'
        with np.load(path) as archive:data={k:archive[k].copy() for k in archive.files}
        data['upper'][-1]=0.;np.savez_compressed(path,**data)
    elif attack=='proof':
        path=tmp_path/'CURRENT_EXACT_C3A_PROOF.json';value=read(path);value['PASS']=False;atomic(path,value)
    elif attack=='row_certificate':
        path=tmp_path/'CURRENT_C3A_ROW_CERTIFICATES.json';value=read(path);value.pop();atomic(path,value)
    elif attack=='source_sha':
        path=tmp_path/'RESTORE_PACKET.json';value=read(path)
        value['case_identity']['c3_authority']['sources']['v42_ultracompact/current.py']['sha256']='0'*64
        value['case_sha']=digest(value['case_identity']);atomic(path,value)
    else:
        path=tmp_path/'CURRENT_C3A_AXES.npz'
        with np.load(path) as archive:axes={k:archive[k].copy() for k in archive.files}
        axes['rows' if attack=='row_axis' else 'columns'][0]=999999;np.savez_compressed(path,**axes)
    with pytest.raises(ValueError,match='RESTORED_|CURRENT_M_'):restore(tmp_path)


def save_v2_packet(folder):
    """A complete small 96-slot physical/affine case; no native Model or solve."""
    from math import cos,sin,pi
    from test_v42_physical_prescreen import domain,original_row_fixture
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_ultracompact.security import prepare_current_security
    from v42_ultracompact.current import reduce_current_c3a
    from v42_ultracompact.response import reformulate_responses
    from v42_native.grid_prescreen import build_grid_prescreen
    route=RouteArc('AB','A','B',0,1,1,1.,'a'*64)
    physical=domain((route,),H=96)
    A,data=original_row_fixture(physical);unit=physical.units[0]
    names=list(map(str,data['names']));lo=list(data['lower']);hi=list(data['upper']);types=list(data['types'])
    def column(name,lower,upper,kind='C'):
        names.append(name);lo.append(lower);hi.append(upper);types.append(kind)
    for t in range(96):column(f'charge_mode[MESS01,{t}]',0,1,'B')
    for t in range(96):
        for site in physical.sites:
            for family in ('injection_P','injection_Q'):column(f'{family}[{site},{t}]',-np.inf,np.inf)
    column('response_line_P[0,0]',-np.inf,np.inf);column('rho_max',0,1)
    n=len(names);lookup={name:j for j,name in enumerate(names)};rows=[];labels=[];rhs=[];senses=[]
    def row(label,sense,right,terms):
        rows.append({lookup[name]:weight for name,weight in terms.items() if weight})
        labels.append(label);senses.append(sense);rhs.append(right)
    for k in unit.retained:
        site,t,_,_,route_at_arc=physical.arcs[k]
        if route_at_arc is not None:continue
        ch,pd,q=(f'{family}[MESS01,{site},{t}]' for family in ('Pch','Pdis','Q'))
        mass=f'arc[MESS01,{k}]';mode=f'charge_mode[MESS01,{t}]'
        row('connected_Pch','<',0,{ch:1,mass:-300});row('connected_Pdis','<',0,{pd:1,mass:-300})
        row('connected_Qmax','<',0,{q:1,mass:-400});row('connected_Qmin','>',0,{q:1,mass:400})
        row('no_simultaneous_charge','<',0,{ch:1,mode:-300})
        row('no_simultaneous_discharge','<',300,{pd:1,mode:300})
        for face in range(16):
            p=cos(2*pi*face/16);qq=sin(2*pi*face/16)
            row('PCS16','<',0,{pd:p,ch:-p,q:qq,mass:-400*cos(pi/16)})
    for t in range(96):
        for site in physical.sites:
            for family in ('injection_P','injection_Q'):
                terms={f'{family}[{site},{t}]':1}
                for raw,w in ([('Q',-1)] if family=='injection_Q' else [('Pch',1),('Pdis',-1)]):
                    name=f'{raw}[MESS01,{site},{t}]'
                    if name in lookup:terms[name]=w
                row(family+'_binding','=',0,terms)
    row('response_line_P_binding[0,0]','=',.375,
        {'response_line_P[0,0]':1,'injection_P[A,0]':-.25,'injection_Q[A,0]':-.125})
    row('line_thermal_face[0,0,0]','<',10000,{'response_line_P[0,0]':1,'rho_max':-1})
    expression={'Pch[MESS01,A,0]':-.25,'Pdis[MESS01,A,0]':.25,'Q[MESS01,A,0]':.125}
    row('voltage_lower[0,0]','>',-1,expression);row('voltage_upper[0,0]','<',1,expression)
    rr=[];cc=[];vv=[]
    for i,terms in enumerate(rows):
        for j,w in terms.items():rr.append(i);cc.append(j);vv.append(w)
    extra=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),n))
    A=sparse.vstack((sparse.hstack((A,sparse.csr_matrix((A.shape[0],n-A.shape[1]))),format='csr'),extra),format='csr')
    data=dict(data,names=np.asarray(names),lower=np.asarray(lo,float),upper=np.asarray(hi,float),types=np.asarray(types),
        objective=np.eye(1,n,n-1).ravel(),constant=np.asarray(0.),
        rhs=np.r_[data['rhs'],rhs],sense=np.concatenate((data['sense'],senses)),row_names=np.concatenate((data['row_names'],labels)))
    battery=Battery(**dict(zip(('minimum','maximum','initial','terminal','p_limit','pcs_kva','eta_charge','eta_discharge','dt_hours'),physical.battery)))
    graph=(physical.sites,dict(physical.initial),list(physical.arcs),battery,{})
    compact=Compact(A,data,graph[2],graph[1],96)
    pre=prepare_current_security(compact,graph);pre['battery']=battery
    presolve=Presolve(compact.A,dict(compact.d,lower=pre['lower'],upper=pre['upper']))
    presolve.current_security=pre;presolve.bound.extend(pre['bounds'])
    presolve.row_delete({int(p['row']) for p in pre['certificates']},pre['certificates']);presolve.run()
    ultra=reduce_current_c3a(presolve.A,presolve.d,graph,physical_original=(A,data))
    c3=m_model._freeze_c3(ultra,folder)
    proof=dict(m_model.verify_transport(compact,presolve),C3A_policy=POLICY,
        selected_C3A_independent_proof_PASS=ultra.proof['PASS'],selected_C3A_rows_removed=ultra.proof['removed_rows'],
        selected_C3A_bounds_tightened=ultra.proof['bounds_tightened'],selected_C3A_original_P1_bit_exact=ultra.proof['original_P1_bit_exact'],
        selected_C3A_integer_and_full_LP_domains_identical=ultra.proof['integer_and_full_LP_domains_identical'])
    transport=m_model._freeze_transport(compact,presolve,graph,proof,folder)
    response=reformulate_responses(ultra.A,ultra.d)
    assert response.plans and pre['bounds'] and pre['certificates']
    response_authority=m_model._freeze_response(response,folder)
    control_names=['aidc_load_kw[IDC]']+[f'{family}[{site}]' for site in physical.sites for family in ('mess_p_kw','mess_q_kvar')]
    coefficients=[dict(slot=t,coefficient_sha256=digest({'fixture_slot':t}),control_names=control_names) for t in range(96)]
    anchor={'controls':[[1.,0.,0.,0.,0.] for _ in range(96)]};bundle={'day':'2025-05-01','pure_mathematical_fixture':True}
    grid=build_grid_prescreen(physical,[SimpleNamespace(**c) for c in coefficients],anchor['controls'])
    identity=dict(schema='V42_CURRENT_DATE_B3_M_CASE_V2',original_matrix_sha=m_model.matrix_sha(A),original_domain_sha=m_model._domain_sha(data),
        selected_matrix_sha=m_model.matrix_sha(response.A),selected_domain_sha=m_model._domain_sha(response.d),
        C3A_matrix_sha=m_model.matrix_sha(ultra.A),C3A_domain_sha=m_model._domain_sha(ultra.d),
        bundle_sha=digest(bundle),anchor_sha=digest(anchor),C3A_policy=POLICY,transport=proof,transport_authority=transport,c3_authority=c3,
        response_authority=response_authority,physical_prescreen_authority=m_model._freeze_physical(physical,folder,A,data),
        grid_prescreen_authority=m_model._freeze_grid_prescreen(grid,folder,A,data,None))
    packet=dict(graph=_plain(graph),graph_sha=digest(_plain(graph)),case_identity=identity,case_sha=digest(identity),
        raw_point=np.zeros(A.shape[1]).tolist(),anchor=anchor,planning_arrays={},bundle=bundle,fixture_coefficients=coefficients)
    for name,matrix,values in (('FULL',A,data),('C3A',ultra.A,ultra.d),('DENSE_RESPONSE',response.A,response.d)):
        sparse.save_npz(folder/(name+'_A.npz'),matrix);np.savez_compressed(folder/(name+'_DATA.npz'),**values)
    atomic(folder/'CURRENT_SECURITY_PRE_C2_SUMMARY.json',pre['summary'])
    atomic(folder/'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json',pre['certificates'])
    atomic(folder/'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json',pre['bounds'])
    atomic(folder/'RESTORE_PACKET.json',packet)
    return m_model.CampaignMCase(response.A,response.d,A,data,None,graph,packet['case_sha'],identity,
        compact,presolve,bundle,anchor,{},[SimpleNamespace(**c) for c in coefficients],folder,ultra,response,
        physical_domain=physical)


@pytest.fixture(scope='module')
def sealed_v2_packet(tmp_path_factory):
    folder=tmp_path_factory.mktemp('actual_V2_physical_security_dense_packet');save_v2_packet(folder);return folder


def test_v2_physical_security_dense_restore_roundtrip_without_model(tmp_path,sealed_v2_packet):
    copy_packet(sealed_v2_packet,tmp_path);case=restore(tmp_path)
    assert case.response is not None and case.presolve.current_security['bounds']
    assert case.response.original is case.ultra.A and case.response.A is case.A
    assert m_model.verify_case(case)['PASS']
    code="import sys;sys.path.insert(0,'tests');from test_v42_b3_current_c3a_restore import restore;restore(sys.argv[1]);print('V2_SECURITY_DENSE_DURABLE_RESTORE_PASS')"
    result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'V2_SECURITY_DENSE_DURABLE_RESTORE_PASS' in result.stdout


@pytest.mark.parametrize('attack',('missing_security','security_bound','response_matrix','response_plan','response_axis'))
def test_v2_restore_rejects_security_and_dense_packet_tampering(tmp_path,sealed_v2_packet,attack):
    copy_packet(sealed_v2_packet,tmp_path)
    if attack=='missing_security':
        (tmp_path/'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json').unlink()
    elif attack=='security_bound':
        path=tmp_path/'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json';values=read(path);values[0]['old_lower']+=1;atomic(path,values)
    elif attack=='response_matrix':
        path=tmp_path/'DENSE_RESPONSE_A.npz';A=sparse.load_npz(path);A.data[-1]*=2;sparse.save_npz(path,A)
    elif attack=='response_plan':
        path=tmp_path/'DENSE_RESPONSE_PLANS.json';values=read(path);values[0]['column']+=1;atomic(path,values)
    else:
        path=tmp_path/'DENSE_RESPONSE_AXES.npz'
        with np.load(path) as archive:axes={k:archive[k].copy() for k in archive.files}
        axes['columns'][-1]+=1;np.savez_compressed(path,**axes)
    with pytest.raises((ValueError,FileNotFoundError),match='RESTORED_|CURRENT_M_|RESPONSE_|CURRENT_SECURITY'):
        restore(tmp_path)
