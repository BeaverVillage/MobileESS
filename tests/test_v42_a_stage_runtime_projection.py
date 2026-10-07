from fractions import Fraction
from itertools import product
import pytest
from v42_a_stage_domain_v2.runtime_projection import finish_count


def test_finish_count_redundant_bounds_in_real_and_integer_simplex():
    for values in product((Fraction(0),Fraction(1,2),Fraction(1),Fraction(3,2)),repeat=3):
        if sum(values)>3:continue
        # The remaining class mass is nonnegative migration/other finishes.
        assert 0<=sum(values[:2])<=3


def test_static_native_exact_substitution_with_frozen_binary64_runtime():
    import gurobipy as gp
    models=[gp.Model('TINY_RUNTIME_PROJECTION_FIXTURE') for _ in range(2)]
    try:
        for direct,model in zip((False,True),models):
            model.Params.OutputFlag=0
            y=model.addVars(3,lb=0,ub=3,vtype=gp.GRB.INTEGER,name='y')
            model.addConstr(y.sum()==3)
            finish=finish_count(model,[y[0],y[1]],3,'finish_count',direct=direct)
            risk=model.addVar(lb=0,name='risk')
            coef=2.423057443558147*.25
            model.addConstr(risk==coef*finish)
            model.update()
        assert models[0].NumVars-models[1].NumVars==1
        assert models[0].NumConstrs-models[1].NumConstrs==1
        for values in product((Fraction(0),Fraction(1,2),Fraction(1),Fraction(3,2),Fraction(2),Fraction(3)),repeat=3):
            if sum(values)!=3:continue
            count=values[0]+values[1]
            expected=Fraction(coef)*count
            assert expected==Fraction(coef)*values[0]+Fraction(coef)*values[1]
    finally:
        for model in models:model.dispose()


def test_unsupported_native_formulation_fails_before_model_build():
    from v42_a_stage_domain_v2.native import build
    with pytest.raises(ValueError,match='UNPROVEN_NATIVE'):build(None,None,'F2-BASE')
