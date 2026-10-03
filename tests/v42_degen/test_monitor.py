import numpy as np
import pytest
import gurobipy as gp
from scipy import sparse
from v42_degen.monitor import Monitor,TIMES,should_stop

@pytest.mark.parametrize('updates,incumbent,valid,cuts,stop',[
    ({},False,False,False,True),
    ({'root_relaxation_complete':200.,'crossover_end':190.},False,False,False,True),
    ({'first_nonroot':500.},False,False,False,False),
    ({'root_processing_complete':500.},False,False,False,False),
    ({},True,True,True,False),
])
def test_checkpoint_uses_registered_conjunction(updates,incumbent,valid,cuts,stop):
    times=dict.fromkeys(TIMES);times.update(updates)
    assert should_stop(times,incumbent,valid,cuts)==stop

def test_activity_message_does_not_invent_DegenMoves_start_end():
    monitor=Monitor(None,None,[])
    monitor.message('Total elapsed time = 362.57s (DegenMoves)',362.568)
    assert monitor.times['DegenMoves_start'] is None and monitor.times['DegenMoves_end'] is None
    assert monitor.events[0]['event']=='DegenMoves_activity'

def test_watchdog_does_not_relabel_stale_MIP_values_as_exact_checkpoint():
    monitor=Monitor(None,None,[])
    monitor.latest=dict(time=550.,nodes=1.,nodes_left=0.,UB=None,LB=.5,cuts=0)
    value=monitor.checkpoint_state('monotonic_wall_since_optimize',600.1)
    assert value['checkpoint_node_count'] is None and value['checkpoint_LB'] is None
    assert value['last_MIP_observation']['nodes']==1 and value['last_MIP_observation']['time']==550.
    assert value['termination_requested']

def test_callback_keeps_each_MIPSOL_for_independent_audit_without_file_IO(tmp_path,monkeypatch):
    A=sparse.csr_matrix([[1.]])
    d=dict(rhs=np.array([1.]),sense=np.array(['<']),lower=np.array([0.]),upper=np.array([1.]),types=np.array(['B']),objective=np.array([1.]),constant=np.array(0.))
    monitor=Monitor(A,d,[object()],checkpoint=False)
    class Model:
        def cbGet(self,key):return {gp.GRB.Callback.RUNTIME:1.,gp.GRB.Callback.MIPSOL_OBJ:1.}[key]
        def cbGetSolution(self,variables):return [1.]
        def terminate(self):raise AssertionError('unexpected termination')
    monkeypatch.chdir(tmp_path)
    monitor(Model(),gp.GRB.Callback.MIPSOL);monitor(Model(),gp.GRB.Callback.MIPSOL)
    assert len(monitor.solutions)==2 and monitor.quick_valid and monitor.calls==2
    assert monitor.times['first_incumbent']==1. and monitor.times['first_branch'] is None
    assert list(tmp_path.iterdir())==[]
    assert monitor.body_wall>=0 and monitor.body_CPU>=0 and not monitor.errors

def test_checkpoint_accepts_actual_callback_observation_with_explicit_time():
    monitor=Monitor(None,None,[])
    monitor.latest=dict(time=600.2,nodes=5.,nodes_left=10.,UB=.7,LB=.5,cuts=2)
    monitor.times['first_nonroot']=450.
    value=monitor.checkpoint_state('solver_runtime',600.2)
    assert value['checkpoint_node_count']==5. and value['checkpoint_state_solver_seconds']==600.2
    assert value['exact_600_node_count'] is None and not value['termination_requested']
