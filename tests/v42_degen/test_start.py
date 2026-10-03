import pickle
from types import SimpleNamespace
import numpy as np
from scipy import sparse
import pytest

@pytest.mark.parametrize('terminal,voltage_rhs,valid',[(.5,-2e-8,False),(.7,1.,False),(.5,1.,True)])
def test_zero_action_is_checked_without_SOC_or_voltage_repair(tmp_path,monkeypatch,terminal,voltage_rhs,valid):
    from v42_degen import start,common
    import v42_bootstrap.m1 as native
    from v42_integrated.matrix import audit
    monkeypatch.setattr(start,'SOURCE',tmp_path);monkeypatch.setattr(start,'LOCAL',tmp_path);monkeypatch.setattr(common,'OUT',tmp_path)
    monkeypatch.setattr(start,'write',lambda *args:None)
    (tmp_path/'DATA.pkl').write_bytes(pickle.dumps([{}]))
    battery=SimpleNamespace(initial=.5,terminal=terminal)
    monkeypatch.setattr(native,'native_inputs',lambda bundle:(('s0',),{'u0':'s0'},(),battery,{}))
    names=[f'arc[u0,{i}]' for i in range(96)]+[f'SOC[u0,{i}]' for i in range(97)]+['rho_max']
    rows=np.zeros((3,len(names)));rows[0,-1]=-1.;rows[1,96+96]=1.
    A=sparse.csr_matrix(rows)
    d=dict(names=np.array(names),row_names=np.array(['line_thermal_face','terminal_SOC','voltage_upper']),rhs=np.array([-.4,terminal,voltage_rhs]),sense=np.array(['<','=','<']),lower=np.zeros(len(names)),upper=np.ones(len(names)),types=np.array(['B']*96+['C']*98),objective=np.array([0.]*(len(names)-1)+[1.]),constant=np.array(0.))
    def independent(point,A,d,solve):
        checked=audit(A,d,point,integral=True,tolerance=1e-8)
        return dict(PASS=checked['PASS'],full_unreduced_matrix_audit=checked,independent_physical_audit=dict(MESS=dict(PASS=True),supplement=dict(charge_mode_and_connection_PASS=True)))
    monkeypatch.setattr(start,'full',independent)
    point,result=start.zero(A,d,None)
    assert result['M1_ZERO_ACTION_START_VALID']==valid
    assert np.all(point[:96]==1.) and np.all(point[96:193]==.5)
    assert point[-1]==.4 and result['SOC_clipping']==0 and result['PQ_repair']==0 and result['route_repair']==0
    if not valid:assert result['validation']['full_unreduced_matrix_audit']['max_constraint_violation']>1e-8
