"""Date axes are bound exactly while the original physical gates stay active."""
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from v42_may_final.pr221 import rebound,current_axes,InterfaceBlocked

def archived_dimension(n):
    assert n==354277
    return n+384

def fixture():
    units=[f'MESS{u:02d}' for u in range(1,5)]
    names=[f'route_flow[{u},0]' for u in units]
    names += [f'charge_mode[{u},{t}]' for u in units for t in range(96)]
    names+=['Pch[MESS01,S0,0]','rho_max']
    n=len(names);d=dict(names=np.asarray(names),row_names=np.asarray(['flow']),types=np.r_[np.full(4,'C'),np.full(384,'B'),['C','C']],
        lower=np.zeros(n),upper=np.ones(n),objective=np.r_[np.zeros(n-1),1.],constant=np.asarray(0.))
    A=sparse.csr_matrix((1,n))
    return SimpleNamespace(A=A,d=d,original_A=A,original_d=d,
        graph=([f'S{i}' for i in range(24)],dict(zip(units,['S0']*4)),[('S0',0,'S0',96,None)],None,{}))

def test_archived_dimension_gate_is_rebound_to_current_axis():
    fn=rebound(archived_dimension,axes={354277:399})
    assert fn(399)==783
    with pytest.raises(AssertionError):fn(354277)
    with pytest.raises(InterfaceBlocked,match='LITERAL_DRIFT'):
        rebound(archived_dimension,axes={1130336:20})

def test_current_named_axes_admitted_without_archived_matrix_shape():
    assert current_axes(fixture())['charge_modes']==384

@pytest.mark.parametrize('attack',['mode_count','mode_fixed','objective','extra_binary','duplicate_name','unit','horizon'])
def test_current_named_axes_reject_physical_drift(attack):
    case=fixture()
    if attack=='mode_count':case.d['names'][4]='unrelated_mode'
    elif attack=='mode_fixed':case.d['upper'][4]=0.
    elif attack=='objective':case.d['objective'][0]=1.
    elif attack=='extra_binary':case.d['types'][-2]='B'
    elif attack=='duplicate_name':case.d['names'][1]=case.d['names'][0]
    elif attack=='unit':case.graph[1].pop('MESS04')
    else:case.graph[2][0]=('S0',0,'S0',95,None)
    with pytest.raises(InterfaceBlocked):current_axes(case)
