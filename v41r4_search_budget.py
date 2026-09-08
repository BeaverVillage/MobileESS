"""B1/A1 budget clock: only Gurobi Runtime in F&O neighborhood optimize calls.

The original model, neighborhoods, ranking, objective
locks and feasibility checks are unchanged. All other work has no charge
against the 1,800-second search allowance.
"""
from pathlib import Path
import time, inspect, textwrap
from dayahead.v41r1 import bounded_solver as core
from dayahead.v41r1.early_stop import FamilySweep
from dayahead.paper_analysis.storage import read
from dayahead.v41r1.early_stop import write_compute_json as write_json
from fast_prepare import record

OriginalBudget=core.PolicyBudget
OriginalBoundedLex=core.BoundedLex
VERSION='V41R4_ACTUAL_FO_SOLVER_SECONDS_V1'
PATCHES=[]


class SearchBudget(OriginalBudget):
    def __init__(self,total=1800.):
        super().__init__(total)
        self.excluded_calls=[];self.wall_started=time.perf_counter()
        self.solver_call_wall_seconds=0.

    def charge(self,seconds,stage):
        assert not stage.endswith(':F_AND_O'), 'SEARCH_MUST_USE_EXPLICIT_SOLVER_RUNTIME'
        self.excluded_calls.append(dict(stage=stage,seconds=float(seconds),charged_search_seconds=0.))

    def charge_solver(self,seconds,stage,wall_call_seconds):
        assert stage.endswith(':F_AND_O') and seconds>=0 and wall_call_seconds>=0
        self.used+=float(seconds);self.solver_call_wall_seconds+=float(wall_call_seconds)
        self.calls.append(dict(stage=stage,seconds=float(seconds),solver_runtime_seconds=float(seconds),
            optimize_call_wall_seconds=float(wall_call_seconds),budget_basis='Gurobi.Model.Runtime'))

    def report(self):
        elapsed=time.perf_counter()-self.wall_started
        return dict(contract=VERSION,total_search_budget_seconds=self.total,actual_search_seconds=self.used,
            remaining_search_seconds=self.remaining,elapsed_component_wall_seconds=elapsed,
            solver_optimize_call_wall_seconds=self.solver_call_wall_seconds,
            non_solver_wall_seconds=max(0.,elapsed-self.solver_call_wall_seconds),
            search_calls=self.calls,excluded_timing_observations=self.excluded_calls,
            excluded_observations_may_overlap=True,excluded_observations_are_not_summed=True,
            excluded=['candidate preparation','model construction','coefficient loading','validation',
                'persistence','reporting','supervisor overhead'])


class SearchSweep(FamilySweep):
    def __init__(self,priority,used,scale=1.):
        super().__init__(priority,used,scale)
        self.last_material_search_seconds=float(used)
        self.completed_no_improvement_sweeps_since_last_material=0

    def observe(self,used,material):
        self.stage_families.add(self.family);self.neighborhoods+=1
        if material:
            self.last_material_search_seconds=float(used)
            self.completed_no_improvement_sweeps_since_last_material=0
            self.material_improvements+=1
            self._record(used,'MATERIAL_CURRENT_OBJECTIVE_IMPROVEMENT')
            self._begin('NORMAL',used)
            return True
        if used<self.family_deadline:return False
        self.families.add(self.family)
        if self.family_index<len(self.order)-1:
            self.family_index+=1;self.family_started=used
            return False
        self._record(used,'COMPLETED_NO_MATERIAL_IMPROVEMENT')
        assert self.records[-1]['family_coverage_fraction']==1.
        self.normal_completed+=1
        self.completed_no_improvement_sweeps_since_last_material=1
        self.reason='LOCAL_STAGNATION_COMPLETE_NO_IMPROVEMENT_SWEEP'
        return False

    def finish(self,used,reason):
        if self.reason is None:
            reason='TIME_LIMIT_UNCERTIFIED'
        super().finish(used,reason)

    def metrics(self):
        result=super().metrics()
        result.update(compute_control_version=VERSION,budget_basis='ACTUAL_FO_NEIGHBORHOOD_SOLVER_SECONDS',
            last_material_improvement_search_seconds=self.last_material_search_seconds,
            complete_no_improvement_sweeps_after_last_material=self.completed_no_improvement_sweeps_since_last_material,
            stagnation_sweep_requirement_satisfied=self.completed_no_improvement_sweeps_since_last_material>=1,
            global_convergence_certified=False,
            search_budget_exhaustion_is_convergence=False)
        return result


def adapted(fn,replacements,extra=None):
    source=textwrap.dedent(inspect.getsource(fn))
    for old,new in replacements:
        assert source.count(old)==1,('SEARCH_BUDGET_SOURCE_DRIFT',fn.__name__,old)
        source=source.replace(old,new)
    ns=dict(fn.__globals__);ns.update(extra or {})
    exec(compile(source,__file__+'::'+fn.__name__,'exec'),ns)
    PATCHES.append(dict(function=fn.__qualname__,source=record(inspect.getsourcefile(fn)),
        replacements=[dict(before=a,after=b) for a,b in replacements]))
    return ns[fn.__name__]


_search_solve=adapted(OriginalBoundedLex._solve,[
    ('self.budget.charge(elapsed,label)',
     "self.budget.charge_solver(data['solver_runtime_seconds'],label,wall_call_seconds=elapsed)")])
_search_optimize=adapted(OriginalBoundedLex.optimize,[
    ('self.overhead_reserve=max(self.overhead_reserve,1.5*(overhead+solver_startup))','self.overhead_reserve=0.'),
    ('missing=max(0.,time.perf_counter()-stage_wall_started-(self.budget.used-start_used))','missing=0.  # Non-search wall time is reported separately, never charged.')
],dict(FamilySweep=SearchSweep))


class SearchBoundedLex(OriginalBoundedLex):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        assert isinstance(self.budget,SearchBudget)
        self.nominal_stage_deadlines=self.deadlines.copy()
        # A former P1 soft allocation cannot stop an unfinished post-improvement
        # sweep. All stages share the one 1800-second AIDC search ceiling.
        self.deadlines[:]=self.used_start+self.budget.remaining
        self.overhead_reserve=0.

    _solve=_search_solve

    def optimize(self,label,callback=None):
        start=time.perf_counter();before=self.budget.used
        result=_search_optimize(self,label,callback)
        wall=time.perf_counter()-start;search=self.budget.used-before
        if result['termination_reason']=='LOCAL_STAGNATION_COMPLETE_NO_IMPROVEMENT_SWEEP':
            assert result['complete_no_improvement_sweeps_after_last_material']>=1
        result.update(actual_search_seconds=search,stage_wall_seconds=wall,
            excluded_stage_wall_seconds=max(0.,wall-search),budget_basis='Gurobi.Model.Runtime',
            termination_classification=result['termination_reason'],
            nominal_stage_deadlines_informational_only=self.nominal_stage_deadlines.tolist(),
            premature_stage_time_cutoff_disabled=True)
        self.budget.stages[-1].update(result)
        path=self.output/'BOUNDED_SOLVER_REPORT.json';report=read(path)
        report.update(contract=VERSION,compute_control_version=VERSION,stages=self.stages,
            budget_basis='ACTUAL_FO_NEIGHBORHOOD_SOLVER_SECONDS',search_accounting=self.budget.report())
        write_json(path,report)
        return result

    def live(self,label,status,start_used):
        super().live(label,status,start_used)
        path=self.output/'F_AND_O_LIVE.json'
        if path.exists():
            value=read(path);value.update(budget_basis='ACTUAL_FO_NEIGHBORHOOD_SOLVER_SECONDS',
                actual_search_seconds=self.budget.used,elapsed_component_wall_seconds=time.perf_counter()-self.budget.wall_started)
            write_json(path,value)


def engine(*args,**kwargs):
    budget=args[3] if len(args)>3 else kwargs.get('budget')
    return (SearchBoundedLex if isinstance(budget,SearchBudget) else OriginalBoundedLex)(*args,**kwargs)


def install():
    core.BoundedLex=engine
