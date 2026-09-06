from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from dayahead.v28r2.electrical_subproblem import SlotCoefficients
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory,MessTrajectorySlot
from dayahead.v40a.recourse import solve_fixed_route,validate_physics
from dayahead.v40a.invariants import route_sha


def test_fixed_route_solver_does_not_enumerate_mobility(monkeypatch):
    import dayahead.v33m.mess_mobility_milp as mobility
    import dayahead.v35r3.algorithm as search
    def forbidden(*args,**kwargs):raise AssertionError('SECOND_ROUTE_SEARCH')
    monkeypatch.setattr(mobility,'add_mess_mobility_block',forbidden)
    monkeypatch.setattr(search,'enumerate_initial_relocations',forbidden)
    names=tuple([f'aidc_load_kw[AIDC{i:02d}]' for i in range(1,13)]+
                [f'mess_p_kw[STA{i:02d}]' for i in range(1,25)]+
                [f'mess_q_kvar[STA{i:02d}]' for i in range(1,25)])
    v=np.zeros((60,1));v[0,0]=-.001;v[12,0]=.001
    current=np.zeros((60,1));current[0,0]=.01;current[12,0]=-.01
    flow=np.zeros((1,60));flow[0,0]=1;flow[0,12]=-1
    c=SlotCoefficients(0,names,('line.test::a',),np.zeros(60),np.ones(1),v,np.array([.1]),current,
                       np.array([1.]),np.zeros(1),flow,np.zeros((1,60)),(100.,),(None,),'a'*64)
    context=SimpleNamespace(coefficients=tuple(replace(c,slot=t) for t in range(96)),nodes=['bus.1'])
    a=MessElectricalAuthority.from_repository()
    traj=MessTrajectory(tuple(MessTrajectorySlot('MESS01',t,'CONNECTED','STA01',None,None,(),None,
                   0,0,0,0,0,None,0,0,0,0,a.initial_energy_kwh,a.initial_energy_kwh/a.capacity_kwh) for t in range(96)))
    pcc=np.zeros((96,12));pcc[:,0]=1
    result=solve_fixed_route(pcc,traj,context)
    assert result['status']=='PASS'
    assert result['route_search_calls']==0
    assert route_sha(result['trajectory'].slots)==route_sha(traj.slots)
    assert validate_physics(result['trajectory'])['status']=='PASS'
