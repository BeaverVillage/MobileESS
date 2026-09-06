from copy import deepcopy
from types import SimpleNamespace
import gurobipy as gp
from gurobipy import GRB
import pytest


def test_gap_switches_for_each_priority_without_changing_physics():
    from dayahead.v41r1.migration_solver_policy import apply_gap
    m=gp.Model();m.Params.OutputFlag=0
    m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.OptimalityTol=1e-9
    for label,expected in [('PRIMARY_MIN_RHO',.001),('V41_SECONDARY_MIN_MEAN_H4_SHORTFALL',.001),
        ('V41_SECONDARY_MIN_MEAN_H4_SHORTFALL_NUMERICAL_CAP_RECHECK',.001),
        ('SECONDARY_MIN_MIGRATIONS',0.),('TERTIARY_COMPLETE_REFERENCE_DEVIATION',0.),('QUATERNARY_STABLE_TIE',0.)]:
        apply_gap(m,label,revision=True)
        assert m.Params.MIPGap==expected and m.Params.MIPGapAbs==0.
        assert m.Params.FeasibilityTol==m.Params.IntFeasTol==m.Params.OptimalityTol==1e-9
    apply_gap(m,'PRIMARY_MIN_RHO',revision=False);assert m.Params.MIPGap==0.
    m.dispose()


@pytest.mark.parametrize('gap,status,accepted,exact',[(.0009,GRB.OPTIMAL,True,False),
    (0.,GRB.OPTIMAL,True,True),(.08,GRB.WORK_LIMIT,False,False)])
def test_certificate_does_not_claim_bounded_or_interrupted_result_is_exact(gap,status,accepted,exact):
    from dayahead.v41r1.migration_solver_policy import certificate
    model=SimpleNamespace(IsMIP=True,SolCount=1,MIPGap=gap,Status=status,
        Params=SimpleNamespace(MIPGap=.001,MIPGapAbs=0.))
    value=certificate(model)
    assert value['accepted_within_registered_gap']==accepted
    assert value['exact_optimum_certified']==exact


def test_certificate_rejects_outside_registered_gap():
    from dayahead.v41r1.migration_solver_policy import certificate
    model=SimpleNamespace(IsMIP=True,SolCount=1,MIPGap=.01,Status=GRB.OPTIMAL,
        Params=SimpleNamespace(MIPGap=.001,MIPGapAbs=0.))
    with pytest.raises(RuntimeError,match='OUTSIDE_REGISTERED_LIMIT'):certificate(model)


def test_production_all_five_passes_record_registered_gap(tmp_path):
    from tests.dayahead.test_v41_scalar_interface import fixture
    from dayahead.v41.reserve import bind
    from dayahead.v41r1.migration import attach
    from dayahead.v40g.optimizer import solve
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.paper_analysis.storage import write_json,sha
    ctx,row,snapshot=fixture();row=attach([row])[0]
    path=tmp_path/'snapshot.json';write_json(path,snapshot);bind(ctx,path,sha(path))
    power=planning_power(import_frozen([row]),ctx)
    out=solve([row],power['pcc'],ctx,tmp_path/'solve')
    stages=out['solver_stages']
    assert [r['requested_relative_gap'] for r in stages]==[.001,.001,0.,0.,0.]
    assert all(r['accepted_within_registered_gap'] for r in stages)
    assert all(r['exact_optimum_certified'] for r in stages[2:])
    assert out['primary_degradation_allowance']==0.


@pytest.mark.parametrize('start,duration',[(24,10),(96,44)])
def test_b3_guard_preserves_pending_to_running_migration(start,duration):
    import numpy as np
    from tests.dayahead.test_v41r1_migration import job
    from tests.dayahead.test_v40g_joint import Wan
    from tests.dayahead.test_v40g_segments import context96,trajectory
    from dayahead.v40g.domain import options,materialize
    from dayahead.v40g_segments.canonical import import_frozen,identities,planning_power
    from dayahead.v40g_segments.b3 import coordinate_segments
    ctx,_=context96();_,row=job(start,duration)
    opt=next(o for o in options(row,ctx.capacity,Wan(),{}) if o.migrated and o.initial_site=='AIDC02')
    jobs=import_frozen([materialize(row,opt,ctx.capacity,Wan())]);expected=planning_power(jobs,ctx)['pcc'];calls=[]
    def search(pcc,cert):
        calls.append('M1');np.testing.assert_array_equal(pcc,expected)
        return trajectory(),{}
    def feedback(current,m1):
        calls.append('A1');return dict(status='PASS',jobs=deepcopy(current))
    def recourse(pcc,m1,cert):
        calls.append('MF');np.testing.assert_array_equal(pcc,expected)
        return dict(status='PASS',trajectory=m1)
    result=coordinate_segments(jobs,ctx,search,feedback,recourse,{'test':'frozen current authority'})
    assert calls==['M1','A1','MF']
    assert identities(result['a1'])==identities(jobs)
    assert result['B3_A0_optimize_calls']==0
