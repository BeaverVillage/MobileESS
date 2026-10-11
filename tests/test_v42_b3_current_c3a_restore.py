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
from v42_native.mess import RouteArc
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
    native=(tuple(graph[0]),graph[1],routes,SimpleNamespace(**graph[3]),graph[4])
    class Registry:
        def resolve(self,module):return importlib.import_module(module)
        def callable(self,module,symbol):
            if module=='v42_bootstrap/m1.py' and symbol=='native_inputs':return lambda bundle:native
            return getattr(self.resolve(module.removesuffix('.py').replace('/','.')),symbol)
    context=SimpleNamespace(output=folder,source_registry=Registry(),original_bundle=packet['bundle'],
        request=SimpleNamespace(stage='M1',request_sha='a'*64,authority=SimpleNamespace(day='2025-05-01')),
        grid_authority=SimpleNamespace(coefficients=lambda *args:[]))
    bridge=MSourceBridge();case=bridge._restore_case(context,packet)
    assert case.ultra is not None and case.A.shape[0]<case.presolve.A.shape[0]
    assert case.ultra.physical_original is case.original_A
    assert case.identity['selected_matrix_sha']==m_model.matrix_sha(case.A)
    assert case.identity['selected_domain_sha']==m_model._domain_sha(case.d)
    assert any(case.d['upper']<case.presolve.d['upper'])
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
