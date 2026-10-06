import json,hashlib
import numpy as np
import gurobipy as gp
import pytest
from v42_m_stage_root.dual_authority import capture,validate,canonical_dual,require_terminal_dual

def fixture(sense,scale=1.):
    m=gp.Model();m.Params.OutputFlag=0
    for k,v in dict(Threads=1,Method=2,Crossover=1,Seed=20260929,FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11).items():m.setParam(k,v)
    x=m.addVar(lb=0,ub=4,name='x');m.setObjective(-x if sense=='<' else x)
    if sense=='<':m.addConstr(scale*x<=scale*2,name='row') if scale>0 else m.addConstr(scale*x>=scale*2,name='row')
    elif sense=='>':m.addConstr(scale*x>=scale*2,name='row') if scale>0 else m.addConstr(scale*x<=scale*2,name='row')
    else:m.addConstr(scale*x==scale*2,name='row')
    m.optimize();return m

@pytest.mark.parametrize('sense',['<','>','='])
def test_native_sense_and_same_terminal_pair(tmp_path,sense):
    m=fixture(sense)
    try:
        pi=m.getAttr('Pi')[0];assert pi<=0 if sense=='<' else pi>=0
        p=tmp_path/'pair.npz';meta=capture(m,p);r=validate(p)
        assert r['PASS'] and r['strong_duality_PASS'] and r['existing_column_RC_PASS']
        assert meta['terminal_pair'].startswith('X/Pi/RC')
    finally:m.dispose()

@pytest.mark.parametrize('sense,scale',[('<',-2.),('>',-2.),('=',3.)])
def test_row_scaling_negation_transform(tmp_path,sense,scale):
    m=fixture(sense,scale)
    try:
        expected=-1. if sense=='<' else 1.
        assert canonical_dual(m.getAttr('Pi'),[scale])[0]==pytest.approx(expected,abs=1e-8)
        p=tmp_path/'scaled.npz';capture(m,p);assert validate(p)['PASS']
    finally:m.dispose()

def test_bound_dual_terms_are_required(tmp_path):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    m.addVar(lb=0,ub=2,obj=-1,name='bounded');m.optimize()
    try:
        p=tmp_path/'bounds.npz';capture(m,p);r=validate(p)
        assert r['PASS'] and r['dual_objective_including_bound_terms']==-2.
        meta=json.loads(p.with_suffix('.json').read_text())
        assert meta['primal_objective_before_gate']==-2. and meta['dual_objective_before_gate']==-2.
        assert meta['bound_dual_sum_before_gate']==-2.
        with np.load(p) as z:
            assert z['bound_upper_dual'].tolist()==[-1.] and z['bound_dual_terms'].tolist()==[-2.]
    finally:m.dispose()

def mutate(p,key,value,reseal=False):
    with np.load(p) as z:data={k:z[k] for k in z.files}
    data[key]=value
    with p.open('wb') as f:np.savez_compressed(f,**data)
    if reseal:
        from v42_m_stage_root.dual_authority import array_sha
        meta=json.loads(p.with_suffix('.json').read_text());meta['identity'][key]=array_sha(value);meta['snapshot_SHA']=hashlib.sha256(p.read_bytes()).hexdigest();p.with_suffix('.json').write_text(json.dumps(meta))

@pytest.mark.parametrize('key,value',[('row_names',np.array(['wrong_axis'])),('pi',np.array([1.])),('point',np.array([1.]))])
def test_axis_stale_dual_and_point_mutation_rejected(tmp_path,key,value):
    m=fixture('<');p=tmp_path/'pair.npz';capture(m,p);m.dispose();mutate(p,key,value)
    assert not validate(p)['PASS']

def test_even_tiny_wrong_sign_is_not_projected(tmp_path):
    m=fixture('<');p=tmp_path/'pair.npz';capture(m,p);m.dispose();mutate(p,'pi',np.array([1e-15]),True)
    r=validate(p);assert not r['PASS'] and not r['strict_sense_sign_PASS'] and r['first_bad_row']['Pi']==1e-15

def test_saved_solver_RC_mismatch_rejected(tmp_path):
    m=fixture('<');p=tmp_path/'pair.npz';capture(m,p);m.dispose();mutate(p,'rc',np.array([1.]),True)
    assert not validate(p)['existing_column_RC_PASS']

def test_rejected_capture_survives_before_pricing(tmp_path,monkeypatch):
    m=fixture('<');p=tmp_path/'pair.npz'
    import v42_m_stage_root.dual_authority as authority
    original=authority.validate
    def reject(path):
        mutate(path,'pi',np.array([1e-15]),True);return original(path)
    monkeypatch.setattr(authority,'validate',reject)
    try:
        with pytest.raises(ValueError,match='STOP_DUAL_AUTHORITY_UNRESOLVED'):require_terminal_dual(m,p)
        assert p.exists() and p.with_suffix('.audit.json').exists()
    finally:m.dispose()

def test_snapshot_cannot_be_overwritten(tmp_path):
    m=fixture('<');p=tmp_path/'pair.npz';capture(m,p)
    try:
        with pytest.raises(FileExistsError):capture(m,p)
    finally:m.dispose()

def test_barrier_dual_cannot_be_declared_a_terminal_simplex_pair(tmp_path):
    m=fixture('<');p=tmp_path/'pair.npz';capture(m,p);m.dispose()
    meta=json.loads(p.with_suffix('.json').read_text());meta['terminal_pair']='BarPi with terminal X'
    p.with_suffix('.json').write_text(json.dumps(meta))
    r=validate(p);assert not r['PASS'] and not r['same_terminal_representation_PASS']

def test_infinite_bound_nonzero_native_rc_is_saved_and_never_zeroed(tmp_path):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1
    m.addVar(lb=0,obj=1,name='unbounded_upper');m.optimize()
    class NativeReadFailureFixture:
        def __getattr__(self,name):return getattr(m,name)
        def getAttr(self,name):
            return [-1e-15] if name=='RC' else m.getAttr(name)
    try:
        p=tmp_path/'infinite_support.npz';meta=capture(NativeReadFailureFixture(),p)
        assert meta['dual_objective_before_gate'] is None and not meta['bound_dual_terms_available']
        with np.load(p) as z:
            assert z['rc'][0]==-1e-15 and np.isneginf(z['bound_dual_terms'][0])
        assert not validate(p)['strong_duality_PASS']
    finally:m.dispose()
