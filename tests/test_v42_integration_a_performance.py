"""Projection equivalence and unrestricted current-case seed boundaries."""
import numpy as np
from scipy import sparse
from v42_integration.a_engine import authorized_data
from v42_integration.a_seed import reference_assignments,full_replay,value_at
from v42_integration.fixture_validation import build_fixture
from v42_root.native import build
from v42_native.voltage import Stage


def make(tmp_path,alias):
    case=build_fixture(tmp_path/('yes' if alias else 'no'))
    acase=case.make_a_case('B3','A1',case.initial_mess,tmp_path/('ay' if alias else 'an'))
    acase.output.mkdir();acase.grid.alias_controls=alias
    data,_=authorized_data(acase)
    class Context:
        folder=acase.output
        def check(self):pass
        def progress(self,value):pass
    result=build(Context(),data,'F2-CRA',grid_context=acase.grid,stage=Stage.A1)
    result[0].update()
    return result,data


def test_pcc_alias_projection_preserves_every_original_row(tmp_path):
    (old,*_),_=make(tmp_path,False)
    (new,*_),_=make(tmp_path,True)
    try:
        oldnames=old.getAttr('VarName');newnames=new.getAttr('VarName')
        aliases=[i for i,n in enumerate(newnames) if n.startswith('PCC_affine_alias[')]
        retained=[i for i in range(len(newnames)) if i not in set(aliases)]
        assert [newnames[i] for i in retained]==oldnames
        identityrows=[i for i,n in enumerate(new.getAttr('ConstrName')) if n.startswith('PCC_affine_identity[')]
        A=new.getA();rhs=np.asarray(new.getAttr('RHS'));offset=np.zeros(new.NumVars)
        mapping=sparse.lil_matrix((new.NumVars,old.NumVars))
        for j,i in enumerate(retained):mapping[i,j]=1.
        for row,alias in zip(identityrows,aliases):
            expression=A.getrow(row)
            assert expression[0,alias]==1.
            for i,v in zip(expression.indices,expression.data):
                if i!=alias:mapping[alias,retained.index(i)]=-v
            offset[alias]=rhs[row]
        keep=[i for i in range(new.NumConstrs) if i not in set(identityrows)]
        assert [new.getAttr('ConstrName')[i] for i in keep]==old.getAttr('ConstrName')
        projected=A[keep]@mapping.tocsr();difference=projected-old.getA()
        assert np.max(abs(difference.data),initial=0)<1e-12
        assert np.max(abs(rhs[keep]-(A@offset)[keep]-old.getAttr('RHS')),initial=0)<1e-12
        assert [new.getAttr('Sense')[i] for i in keep]==old.getAttr('Sense')
        assert np.array_equal(np.asarray(new.getAttr('VType'))[retained],old.getAttr('VType'))
    finally:old.dispose();new.dispose()


def test_reference_seed_assignments_cover_current_aggregate_count(tmp_path):
    (model,units,*_),data=make(tmp_path,True)
    try:
        fixed,plans=reference_assignments(model,units,data)
        assert set(plans)==set(data[1])
        assert all(plans[u]['start']==data[1][u].reference_start for u in plans)
        assert fixed and max(fixed.values())==2.
        assert all(model.getVars()[i].LB<=v<=model.getVars()[i].UB for i,v in fixed.items())
        # The main domain is still free after computing the disposable seed.
        assert any(model.getVars()[i].LB!=model.getVars()[i].UB for i in fixed)
    finally:model.dispose()


def test_full_replay_checks_rows_bounds_and_integrality_without_optimize():
    import gurobipy as gp
    model=gp.Model();model.Params.OutputFlag=0
    try:
        x=model.addVar(vtype='B');y=model.addVar(lb=0,ub=2)
        model.addConstr(x+y==2);model.update()
        assert full_replay(model,[1,1])['PASS']
        assert not full_replay(model,[.5,1.5])['PASS']
        assert not full_replay(model,[1,2])['PASS']
        assert not full_replay(model,[0,3])['PASS']
        assert value_at(2*x+3*y+4,np.array([1.,1.]))==9.
    finally:model.dispose()
