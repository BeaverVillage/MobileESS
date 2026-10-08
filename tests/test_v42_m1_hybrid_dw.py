"""Original-row restricted-master mapping with mocked model construction."""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_m1_hybrid import dw
from v42_m1_hybrid.blocks import build_blocks
from v42_unified.storage import sha


class MockModel:
    """No Native model or optimize/presolve is created or invoked."""
    instances = []
    def __init__(self, name):
        self.Params = SimpleNamespace()
        self.SolCount = 1
        self.ObjVal = -12345.  # Diagnostic deliberately cannot certify a bound.
        self.disposed = False
        self.instances.append(self)

    def addMVar(self, n, **kw):
        self.variable_input = kw
        self.variables = SimpleNamespace(VarName=None, X=np.zeros(n))
        self.NumVars = n
        return self.variables

    def addMConstr(self, A, variables, sense, rhs):
        self.A, self.rhs, self.sense = A.copy(), rhs.copy(), sense.copy()
        self.NumConstrs = A.shape[0]
        # A wrong sign is deliberately zeroed before any bound is admitted.
        self.rows = SimpleNamespace(Pi=np.arange(1., self.NumConstrs+1))
        return self.rows

    def update(self): pass
    def getA(self): return self.A.copy()
    def getAttr(self, name):
        assert name == 'RHS'
        return self.rhs.copy()
    def dispose(self): self.disposed = True


class MockLedger:
    @contextmanager
    def cost(self, *args, **kwargs): yield
    def optimize(self, model, **kwargs):
        assert kwargs['track'] == 'RMP'
        assert kwargs['requested_seconds'] == 30
        return dict(Native_Runtime=0., mock_only=True)


@pytest.fixture
def case():
    A = sparse.csr_matrix(np.array([
        [1.,0.,0.,0.,0.], [0.,1.,0.,0.,0.],
        [0.,0.,1.,0.,0.], [0.,0.,0.,1.,0.],
        [0.,0.,0.,0.,1.], [1.,1.,1.,1.,-1.]]))
    d = dict(names=np.array([f'route_flow[M{i},0]' for i in range(1,5)]+['rho_max']),
        lower=np.zeros(5),upper=np.array([1.,1.,1.,1.,10.]),
        types=np.array(['B','B','B','B','C']),objective=np.array([0.,0.,0.,0.,1.]),
        rhs=np.array([0.,0.,0.,0.,10.,0.]),sense=np.array(['>','>','>','>','<','<']),
        row_names=np.array(['local1','local2','local3','local4','grid','mixed']),constant=np.array(0.))
    return SimpleNamespace(A=A,d=d,point=np.array([1.,1.,1.,1.,4.]),case_sha='same_original_case')


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    MockModel.instances=[]
    monkeypatch.setattr(dw.gp,'Model',MockModel)


def catalog(tmp_path, unit, point, axis):
    file=tmp_path/(unit+'_additional.npz')
    np.savez_compressed(file,point=np.asarray(point),original_columns=np.asarray(axis))
    return dict(path=str(file),sha256=sha(file),admission={'PASS':True})


def test_empty_external_catalog_always_includes_all_four_verified_seed_columns(tmp_path,case):
    assert tmp_path.resolve().drive.upper() == 'D:'
    decomp=build_blocks(case)
    model,variables,rows,receipt,source=dw.build_master(case,decomp,{},tmp_path/'rmp')
    assert receipt['column_count_by_unit'] == dict.fromkeys(decomp.units,1)
    assert [item['unit'] for item in receipt['catalog']] == list(decomp.units)
    assert np.array_equal(source,[4,5])
    assert receipt['source_rows'] == [4,5]
    assert np.array_equal(model.A.toarray(),np.array([
        [1.,0.,0.,0.,0.],[-1.,1.,1.,1.,1.],
        [0.,1.,0.,0.,0.],[0.,0.,1.,0.,0.],
        [0.,0.,0.,1.,0.],[0.,0.,0.,0.,1.]]))
    assert receipt['original_F_subset_restricted_master'] is False
    assert receipt['restricted_master_objective_is_Global_LB'] is False
    assert receipt['restricted_master_objective_is_Global_UB'] is False
    assert receipt['full_DW_original_F_inclusion_requires_entire_feasible_trajectory_catalog'] is True


def test_seed_duplicates_are_deduplicated_without_losing_unit_seed(tmp_path,case):
    decomp=build_blocks(case)
    duplicate=catalog(tmp_path,'M1',[1.],[0])
    model,variables,rows,receipt,source=dw.build_master(case,decomp,{'M1':[duplicate]},tmp_path/'rmp')
    assert receipt['column_count_by_unit']['M1']==1
    assert len(receipt['catalog'])==4


def test_valid_additional_integer_column_changes_only_derived_catalog(tmp_path,case):
    decomp=build_blocks(case); original=case.A.copy()
    extra=catalog(tmp_path,'M1',[0.],[0])
    model,variables,rows,receipt,source=dw.build_master(case,decomp,{'M1':[extra]},tmp_path/'rmp')
    assert receipt['column_count_by_unit']['M1']==2
    assert receipt['columns']==6
    assert np.array_equal(case.A.data,original.data)
    assert np.array_equal(case.A.indices,original.indices)
    assert np.array_equal(case.A.indptr,original.indptr)
    assert receipt['restricted_master_objective_is_Global_LB'] is False


def test_changed_candidate_file_sha_rejected_before_model_construction(tmp_path,case):
    item=catalog(tmp_path,'M1',[0.],[0]); item['sha256']='0'*64
    with pytest.raises(ValueError,match='DW_COLUMN_BYTE_DRIFT'):
        dw.build_master(case,build_blocks(case),{'M1':[item]},tmp_path/'rmp')
    assert MockModel.instances==[]


@pytest.mark.parametrize('point,axis,error',[
    ([0.],[1],'ORIGINAL_AXIS_DRIFT'),
    ([0.,0.],[0],'POINT_DRIFT'),
    ([float('nan')],[0],'POINT_DRIFT'),
    ([.5],[0],'DOMAIN_REPLAY_FAILED'),
    ([2.],[0],'DOMAIN_REPLAY_FAILED')])
def test_mapped_column_axis_shape_finite_and_exact_integer_domain_rejected(tmp_path,case,point,axis,error):
    item=catalog(tmp_path,'M1',point,axis)
    with pytest.raises(ValueError,match=error):
        dw.build_master(case,build_blocks(case),{'M1':[item]},tmp_path/'rmp')
    assert MockModel.instances==[]


def test_invalid_seed_is_not_admitted_by_source_label(tmp_path,case):
    case.point[0]=.5
    with pytest.raises(ValueError,match='DOMAIN_REPLAY_FAILED'):
        dw.build_master(case,build_blocks(case),{},tmp_path/'rmp')
    assert MockModel.instances==[]


def test_external_rejected_column_does_not_displace_verified_original_seed(tmp_path,case):
    item=catalog(tmp_path,'M1',[.5],[0]); item['admission']['PASS']=False
    _,_,_,receipt,_=dw.build_master(case,build_blocks(case),{'M1':[item]},tmp_path/'rmp')
    assert receipt['column_count_by_unit']==dict.fromkeys(['M1','M2','M3','M4'],1)


def test_actual_original_rows_and_eta_mapping_has_no_native_objective_authority(tmp_path,case):
    result=dw.run(case,build_blocks(case),{},MockLedger(),tmp_path/'rmp')
    assert result['Native_objective_diagnostic']==-12345.
    assert result['restricted_master_is_Global_LB'] is False
    assert result['restricted_master_is_Global_UB'] is False
    assert result['pricing_closure']=='NOT_PROVEN'
    # Both original <= rows received a positive invalid signed Pi, so zero.
    assert result['full_original_dual']=={}
    assert result['invalid_original_inequality_multiplier_signs_zeroed']==2
    assert result['convexity_duals']=={f'M{i}':str(Fraction(i+2)) for i in range(1,5)}
    assert MockModel.instances[0].disposed is True


def test_new_output_outside_d_clone_rejected_without_write(case):
    target=Path('C:/V42_MUST_NOT_CREATE/rmp')
    with pytest.raises(ValueError,match='HYBRID_OUTPUT_MUST_BE_INSIDE_D_V42'):
        dw.build_master(case,build_blocks(case),{},target)
    assert not target.exists()
    assert MockModel.instances==[]
