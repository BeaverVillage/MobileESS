"""Independent LP/hull counterexample and adversarial pricing-cover contracts."""
from copy import deepcopy
from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from scipy.optimize import linprog
import pytest
from v42_trajectory_hull.certificate import check_cover, node_bound, check_global


def fixture():
    # Full 96-slot state axis, one binary mode, one resource response.
    # p <= z and p <= 1-z; both integer regions force p=0.
    # This bounded mathematical fixture is not claimed to be actual May01 data.
    A = sparse.csr_matrix(np.array([[-1.,1.], [1.,1.]]))
    d = dict(lower=np.array([0.,0.]), upper=np.array([1.,1.]),
             types=np.array(['B','C']), objective=np.zeros(2),
             rhs=np.array([0.,1.]), sense=np.array(['<','<']),
             names=np.array(['charge_mode[MESS01,0]','Pdis[MESS01,IDC01,0]']),
             row_names=np.array(['mode_resource_0','mode_resource_1']), constant=np.array(0.))
    # Append unchanged full-horizon SOC equalities with a constant terminal state.
    soc = sparse.eye(96, format='csr')
    A = sparse.block_diag((A,soc), format='csr')
    for key, values in [('lower',np.ones(96)),('upper',np.ones(96)),('types',np.full(96,'C')),
                        ('objective',np.zeros(96)),('rhs',np.ones(96)),('sense',np.full(96,'=')),
                        ('names',np.array([f'SOC[MESS01,{t}]' for t in range(96)])),
                        ('row_names',np.array([f'SOC_fixture[{t}]' for t in range(96)]))]:
        d[key] = np.concatenate((d[key],values))
    return SimpleNamespace(A=A,d=d), {'1':'-1'}


def cover():
    return {'r':dict(fixes={},proof=dict(kind='DUAL',dual={'0':'-1/2','1':'-1/2'}),split=0),
            'r0':dict(fixes={'0':0},proof=dict(kind='DUAL',dual={'0':'-1'}),split=None),
            'r1':dict(fixes={'0':1},proof=dict(kind='DUAL',dual={'1':'-1'}),split=None)}


def test_full_horizon_integer_cover_strictly_stronger_than_lp():
    b,q = fixture()
    native = np.zeros(98); native[1] = -1
    result = linprog(native, A_ub=b.A[:2], b_ub=b.d['rhs'][:2],
                     A_eq=b.A[2:], b_eq=b.d['rhs'][2:],
                     bounds=list(zip(b.d['lower'],b.d['upper'])), method='highs')
    assert result.success and result.fun == -.5
    assert node_bound(b,q,{},cover()['r']['proof']) == F(-1,2)
    assert check_cover(b,q,cover()) == 0
    # Original integer witnesses z=0 or z=1, p=0 survive unchanged.
    for bit in (0,1):
        x = np.concatenate(([bit,0.],np.ones(96)))
        assert np.all(b.A[:2]@x <= b.d['rhs'][:2])
        assert np.array_equal(b.A[2:]@x,b.d['rhs'][2:])


@pytest.mark.parametrize('mutation', ['missing_child','wrong_fix','continuous_split','wrong_sign',
                                     'unproved_empty','extra_region'])
def test_unsound_cover_rejected(mutation):
    b,q = fixture();tree = deepcopy(cover())
    if mutation == 'missing_child': del tree['r1']
    if mutation == 'wrong_fix': tree['r1']['fixes']={'0':0}
    if mutation == 'continuous_split': tree['r']['split']=1
    if mutation == 'wrong_sign': tree['r0']['proof']['dual']={'0':'1'}
    if mutation == 'unproved_empty': tree['r0']['proof']=dict(kind='FARKAS',dual={})
    if mutation == 'extra_region': tree['other']=deepcopy(tree['r0'])
    with pytest.raises((ValueError,IndexError)):
        check_cover(b,q,tree)


def test_interrupted_children_retain_parent_proof():
    b,q = fixture();tree=cover()
    tree['r0']['proof']=tree['r1']['proof']=None
    assert check_cover(b,q,tree)==F(-1,2)


def test_exact_price_rounding_error_is_outward():
    b,q=fixture();q={'1':str(F(-1)-F(1,2**60))}
    bound=node_bound(b,q,{},cover()['r']['proof'])
    assert bound <= (F(-1)-F(1,2**60))/2


def test_original_grid_objective_certifies_integer_hull_gain():
    b,q=fixture()
    # Keep original coupling rho+p >= 1. q_u=-p, q_nonunit=0.
    A=sparse.hstack((b.A,sparse.csr_matrix((98,1))),format='csr')
    coupling=sparse.csr_matrix(([1.,1.],([0,0],[1,98])),shape=(1,99))
    A=sparse.vstack((A,coupling),format='csr')
    d=dict(b.d)
    d['objective']=np.concatenate((np.zeros(98),[1.]))
    d['rhs']=np.concatenate((b.d['rhs'],[1.]))
    d['sense']=np.concatenate((b.d['sense'],['>']))
    case=SimpleNamespace(A=A,d=d,case_sha='fixture',lower=np.zeros(99),upper=np.ones(99))
    nonunit=SimpleNamespace(A=sparse.csr_matrix((0,1)),original_columns=np.array([98]),
        d=dict(lower=np.array([0.]),upper=np.array([1.]),types=np.array(['C']),
               objective=np.array([1.]),rhs=np.array([]),sense=np.array([],dtype='U1'),constant=np.array(0.)))
    b.original_columns=np.arange(98)
    decomp=SimpleNamespace(units={'MESS01':b},coupling_rows=np.array([98]),nonunit_block=nonunit)
    packet=dict(case_sha='fixture',coupling_dual={'0':'1'},nonunit_dual={},
                units={'MESS01':dict(exact_price=q,tree=cover())})
    cert=check_global(case,decomp,packet)
    assert cert['PASS'] and F(cert['exact_bound'])==1
    assert cert['independently_certified_LB']==1
    packet['units']['MESS01']['exact_price']={'1':'-2'}
    with pytest.raises(ValueError,match='UNROUNDED_PRICE'):
        check_global(case,decomp,packet)
