"""Native0 integration, actual-parameter overrides and Root HOLD attacks."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from scipy import sparse

from v42_may_campaign_native90.m_model import CampaignMCase
from v42_ultracompact.response import reformulate_responses
from v42_ultracompact.native_readback import ROOT_PARAMETERS,snapshot,verify_root_readback
from test_v42_current_exact_c3a import fixture


def test_original_forward_and_inverse_compose_after_c3a_extension():
    ultra,graph,compact,presolve=fixture(H=4)
    expression=sparse.csr_matrix(([1.,2.**-53,np.nextafter(0.,1.)],([0,0,0],[0,1,2])),shape=(1,ultra.A.shape[1]))
    baseline=sparse.vstack((ultra.A,expression,expression),format='csr')
    data=dict(ultra.d,rhs=np.r_[ultra.d['rhs'],-1.,2.],sense=np.concatenate((ultra.d['sense'],['>','<'])),
        row_names=np.concatenate((ultra.d['row_names'],['voltage_lower[0,0]','voltage_upper[0,0]'])))
    result=reformulate_responses(baseline,data)
    case=CampaignMCase(result.A,result.d,compact.original,compact.original_data,None,graph,'fixture',{},
        compact,presolve,{}, {}, {}, None,Path('.'),ultra,result)
    raw=np.zeros(compact.original.shape[1])
    for j,name in enumerate(map(str,compact.original_data['names'])):
        if name.startswith('arc['):
            k=int(name[:-1].rsplit(',',1)[1]);arc=graph[2][k]
            raw[j]=float(arc[-1] is None and arc[0]=='A')
        elif name.startswith('response_line_P['):raw[j]=1+int(name.split('[',1)[1].split(',',1)[0])
    current=presolve.forward(compact.forward(raw))
    original=compact.inverse(presolve.inverse(current))
    projected=case.forward(original)
    assert result.proof['new_continuous_helpers']==1
    assert projected.shape==(result.A.shape[1],)
    assert np.array_equal(projected[:ultra.A.shape[1]],current)
    assert np.array_equal(case.lift(projected),original)
    with pytest.raises(ValueError,match='POINT_AXIS_DRIFT'):
        case.lift(np.zeros(result.A.shape[1]+1))


def test_actual_parameter_readback_rejects_late_override_without_optimize(tmp_path,monkeypatch):
    import gurobipy as gp
    from v42_may_campaign_native90.preflight import native_zero
    # Verification uses the actual native parameter interface, not a mocked
    # requested dictionary. Keep this portable outside the Windows D: host.
    import v42_ultracompact.native_readback as module
    actual_path=module.Path
    class LocalDirectory:
        drive='D:'
        def __init__(self,value):self.path=actual_path(value)
        def is_dir(self):return self.path.is_dir()
    monkeypatch.setattr(module,'Path',LocalDirectory)
    with native_zero() as calls:
        model=gp.Model();model.Params.OutputFlag=0
        try:
            for name,value in ROOT_PARAMETERS.items():setattr(model.Params,name,value)
            model.Params.TimeLimit=600.;model.Params.NodefileDir=str(tmp_path)
            model.Params.SolutionLimit=gp.GRB.MAXINT;model.update()
            saved=snapshot(model)
            assert verify_root_readback(saved)['PASS']
            assert len(saved['actual_parameters'])>=len(ROOT_PARAMETERS)
            model.Params.FeasibilityTol=1e-8
            with pytest.raises(ValueError,match='FeasibilityTol'):
                verify_root_readback(snapshot(model))
            for name in ROOT_PARAMETERS:
                attacked=dict(saved,actual_parameters=dict(saved['actual_parameters']))
                attacked['actual_parameters'][name]=saved['actual_parameters'][name]+1
                with pytest.raises(ValueError,match='PARAMETER_READBACK_DRIFT'):
                    verify_root_readback(attacked)
        finally:model.dispose()
    assert calls==[]


def test_dense_gain_requires_exact_proof_but_zero_physical_exclusions_are_valid():
    path=Path(__file__).resolve().parents[1]/'tools/validate_svr11_dense_response.py'
    spec=importlib.util.spec_from_file_location('dense_native0_runner',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sizes={'C3A':{'nnz':8609710},'Dense':{'nnz':7911369}}
    gate=module.native_gate({'additional_exact_removed_arcs':0},sizes,{'PASS':True})
    assert gate['dense_NNZ_improvement']
    assert gate['allowed'] is False and gate['maximum_new_Full_calls']==0
    assert gate['maximum_new_Full_seconds']==0
    assert gate['reason']=='EXACT_OR_STRUCTURE_GATE_NOT_MET'
    physical={'additional_exact_removed_arcs':0,'PASS':True,'independent_proof':{'PASS':True},
        'original_matrix_bridge':{'PASS':True}}
    gate=module.native_gate(physical,sizes,{'PASS':True,'integer_and_full_LP_domains_identical':True})
    assert gate['allowed'] and gate['maximum_new_Full_calls']==1
    assert gate['maximum_new_Full_seconds']==600
    assert gate['physical_prescreen_completed'] and gate['zero_additional_exclusions_accepted']


@pytest.mark.parametrize('message',[
    'Root relaxation: time limit, 79764 iterations, 532.16 seconds (831.30 work units)',
    'Root relaxation: interrupted, 1 iterations, 180.00 seconds (1 work units)',
    'Root relaxation: infeasible, 180.00 seconds (1 work units)'])
def test_shared_telemetry_rejects_noncompleted_root_message(tmp_path,message):
    from v42_common_mess.telemetry import root_lp
    path=tmp_path/'native.log';path.write_text(message)
    assert root_lp(path)['Root_LP_status']=='NATIVE_LOG_ROOT_INTERRUPTED'
