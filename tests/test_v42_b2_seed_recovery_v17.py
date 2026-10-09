from pathlib import Path
from copy import deepcopy
import pytest
import numpy as np
from types import SimpleNamespace
from v42_b2_seed_recovery_v17 import policy,coordinator,stationary_dispatch
from v42_b2_seed_recovery_v17.common import atomic,record


def prior(root,day='2025-05-01'):
    folder=root/'dates/B2'/day/'attempts/old';folder.mkdir(parents=True)
    atomic(folder/'request.json',dict(arm='B2',day=day))
    atomic(folder/'RESULT.json',dict(identity=dict(arm='B2',day=day),Native_Runtime=3318.513))
    atomic(folder/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=3318.513,inflight=None,
        calls=[dict(Native_Runtime=3318.513,entered_native=True,runtime_unavailable=False)]))
    return dict(ledger=record(folder/'NATIVE_RUNTIME_LEDGER.json'),result=record(folder/'RESULT.json'),
        request=record(folder/'request.json'),Native_Runtime=3318.513)


def test_completed_prior_runtime_is_carried_exactly(tmp_path):
    receipt=prior(tmp_path)
    assert policy.prior_runtime(receipt,root=tmp_path,day='2025-05-01')==3318.513


@pytest.mark.parametrize('attack',['inflight','unknown','wrong_sum','reset','other_day','mutated_result'])
def test_unsafe_prior_clock_is_quarantined(tmp_path,attack):
    receipt=prior(tmp_path);ledger=Path(receipt['ledger']['path'])
    if attack=='mutated_result':
        atomic(receipt['result']['path'],dict(Native_Runtime=0))
    elif attack!='other_day':
        from v42_b2_seed_recovery_v17.common import read
        data=read(ledger)
        if attack=='inflight':data['inflight']={}
        elif attack=='unknown':data['calls'][0]['runtime_unavailable']=True
        elif attack=='wrong_sum':data['calls'][0]['Native_Runtime']=0
        elif attack=='reset':data['measured_Native_Runtime']=0
        atomic(ledger,data);receipt['ledger']=record(ledger)
    with pytest.raises(PermissionError):
        policy.prior_runtime(receipt,root=tmp_path,day='2025-05-02' if attack=='other_day' else '2025-05-01')


@pytest.mark.parametrize('available,peak,expected',[(19,4,3),(12,5,1),(16,5,2),(3,5,1)])
def test_ram_selects_parallelism_after_canary(available,peak,expected):
    assert coordinator.concurrency(available*1024**3,peak*1024**3)==expected


def test_stationary_fixes_only_current_route_and_modes():
    case=SimpleNamespace(d=dict(names=np.array(['arc[u,0]','arc[u,1]','charge_mode[u,A,0]','Q[u,A,0]',
        'node_activity[u,A,0]','node_activity[u,B,0]']),
        types=np.array(['B','B','B','C','B','B'])),graph=(None,{'u':'A'},[('A',0,'A',1,None),('B',0,'B',1,None)]))
    ids,values=stationary_dispatch.discrete_stationary(case)
    assert ids.tolist()==[0,1,2,4,5] and values.tolist()==[1.,0.,0.,1.,0.]
