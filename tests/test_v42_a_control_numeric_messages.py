"""A solver warning must not terminate the original branch-and-bound search."""
import json
from types import SimpleNamespace
import gurobipy as gp
import numpy as np
import pytest
from scipy import sparse
from v42_integration.table_v_a_control import solve_original


class Model:
    def __init__(self):
        self.Params=SimpleNamespace();self.ObjCon=0.;self.SolCount=0;self.ObjBound=.5;self.terminated=0
    def getA(self):return sparse.csr_matrix([[1.]])
    def getAttr(self,name):
        return dict(RHS=[0.],Sense=['>'],LB=[0.],UB=[1.],VType=['B'],Obj=[1.])[name]
    def getVars(self):return [0]
    def cbGet(self,attribute):return 'Numerical trouble encountered\n'
    def terminate(self):self.terminated+=1


@pytest.mark.parametrize('status',[gp.GRB.TIME_LIMIT,gp.GRB.NUMERIC,gp.GRB.INTERRUPTED])
def test_numeric_warning_is_not_callback_fatal_and_final_status_controls_bound(tmp_path,status):
    model=Model()
    class Budget:
        path=tmp_path/'ledger.json'
        def remaining(self):return 100.
        def solve(self,m,**kwargs):
            kwargs['callback'](m,gp.GRB.Callback.MESSAGE)
            assert m.terminated==0
            m.Status=status
            return dict(Native_Runtime=1.,native_numeric_attributes=dict(ObjBound=m.ObjBound,IsMIP=1.))
    case=SimpleNamespace(case_sha='case',table_v_day='2025-05-01',arm='B1',stage='A1')
    binding=dict(matrix_sha='matrix',domain_sha='domain')
    call,cert,summary=solve_original(model,Budget(),case,dict(manifest=dict(source_sha='source')),binding,'objective',{},tmp_path)
    assert model.terminated==0
    assert summary['numerical_warnings']==['Numerical trouble encountered']
    packet=json.loads((tmp_path/'ORIGINAL_INTEGER_BOUND_ATTRIBUTES.json').read_text())
    assert packet['status']==status
    assert (cert is not None)==(status==gp.GRB.TIME_LIMIT)
    assert bool(summary['numerical_errors'])==(status!=gp.GRB.TIME_LIMIT)


def test_valid_raw_incumbent_survives_later_numeric_status(tmp_path):
    class Accepted(Model):
        def cbGetSolution(self,variables):return [1.]
        def cbGet(self,attribute):
            if attribute==gp.GRB.Callback.MSG_STRING:return 'Numerical trouble encountered\n'
            return {gp.GRB.Callback.MIP_OBJBST:1.,gp.GRB.Callback.MIP_OBJBND:.5,
                    gp.GRB.Callback.RUNTIME:1.}[attribute]
    model=Accepted()
    class Budget:
        path=tmp_path/'ledger.json'
        def remaining(self):return 100.
        def solve(self,m,**kwargs):
            for where in (gp.GRB.Callback.MIPSOL,gp.GRB.Callback.MIP,gp.GRB.Callback.MESSAGE):
                kwargs['callback'](m,where)
            m.Status=gp.GRB.NUMERIC
            return dict(Native_Runtime=1.,native_numeric_attributes=dict(ObjBound=.5,IsMIP=1.))
    case=SimpleNamespace(case_sha='case',table_v_day='2025-05-01',arm='B1',stage='A1')
    _,cert,summary=solve_original(model,Budget(),case,dict(manifest=dict(source_sha='source')),
                                dict(matrix_sha='matrix',domain_sha='domain'),'objective',{},tmp_path)
    assert cert is None and summary['Global_UB']==1. and model.terminated==0
    record=json.loads((tmp_path/'RECOVERABLE_FULL_INCUMBENT.json').read_text())
    with np.load(record['point']['path']) as packet:assert np.array_equal(packet['point'],np.array([1.]))
    assert record['raw_float_values_preserved'] and not record['Global_LB_claimed']
