"""Verify the production MESS adapter has no time, work, or soft-memory cutoff."""
from bootstrap import *
import gurobipy as gp
import math
import mess_runtime
from dayahead.v34 import integrated_mess as module


def main():
    previous=module.WORK_LIMIT_TIERS
    try:
        module.WORK_LIMIT_TIERS=(gp.GRB.INFINITY,)
        solve=mess_runtime.integrated_adapter()
        model=solve.__globals__['_configured_model']('ieee8500_cutoff_audit')
        try:
            limits=tuple(float(getattr(model.Params,key)) for key in ('TimeLimit','WorkLimit','SoftMemLimit'))
            full=tuple(solve.__globals__['WORK_LIMIT_TIERS'])
            restricted=tuple(module._stationary_restricted_incumbent.__globals__['WORK_LIMIT_TIERS'])
            preferred=tuple(module._preferred_restricted_incumbent.__globals__['WORK_LIMIT_TIERS'])
            assert model.Params.Threads==4
            assert all(math.isinf(value) or value>=gp.GRB.INFINITY for value in limits)
            assert full==restricted==preferred==(gp.GRB.INFINITY,)
            report=dict(status='PASS',configured_time_limit='INFINITY',
                configured_work_limit='INFINITY',configured_soft_memory_limit='INFINITY',
                full_solve_work_tiers=['INFINITY'],restricted_solve_work_tiers=['INFINITY'],
                preferred_restricted_work_tiers=['INFINITY'],threads=4)
        finally:
            model.dispose()
        save(H/'MESS_NO_CUTOFF_AUDIT.json',report)
        print(report)
    finally:
        module.WORK_LIMIT_TIERS=previous


if __name__=='__main__':main()
