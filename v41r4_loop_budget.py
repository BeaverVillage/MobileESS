"""Fixed, continuous F&O loop wall clock; unchanged scientific model/search keys."""
import time
from pathlib import Path
from dayahead.v41r1 import bounded_solver as core
from dayahead.v41r1.early_stop import FamilySweep
from dayahead.paper_analysis.storage import read
from dayahead.v41r1.early_stop import write_compute_json as write_json
from v41r4_search_budget import adapted,OriginalBudget,OriginalBoundedLex

VERSION='V41R4_FIXED_1800_SECOND_SEARCH_LOOP_WALL_CLOCK_V1'


class LoopBudget(OriginalBudget):
    def __init__(self,total=1800.,clock=None):
        self.clock=clock or time.perf_counter
        self.loop_started=None;self.loop_stopped=None
        self.loop_started_unix=None
        super().__init__(total)
        self.component_started=self.clock();self.observations=[];self.stage_deadline=self.total

    @property
    def elapsed(self):
        if self.loop_started is None:return 0.
        return max(0.,(self.clock() if self.loop_stopped is None else self.loop_stopped)-self.loop_started)

    @property
    def used(self):return min(self.total,self.elapsed)

    @used.setter
    def used(self,value):
        assert value==0.,'WALL_CLOCK_BUDGET_CANNOT_BE_MANUALLY_CHARGED'

    @property
    def stage_remaining(self):return max(0.,min(self.total,self.stage_deadline)-self.elapsed)

    def start_loop(self):
        if self.loop_started is None:self.loop_started=self.clock();self.loop_started_unix=time.time()

    def stop_loop(self):
        if self.loop_started is not None and self.loop_stopped is None:self.loop_stopped=self.clock()

    def charge(self,seconds,stage):
        # Timing observations do not increment a second counter. The monotonic
        # clock already includes overlapping ranking, solve and validation work.
        row=dict(stage=stage,seconds=float(seconds),observation_only=True,
            inside_search_timer=self.loop_started is not None and self.loop_stopped is None,
            clock_used_seconds=self.used)
        self.calls.append(row);self.observations.append(row)

    def report(self):
        return dict(contract=VERSION,budget_basis='CONTINUOUS_SEARCH_LOOP_WALL_CLOCK',
            total_search_budget_seconds=self.total,search_loop_wall_seconds=self.used,
            observed_elapsed_at_safe_return_seconds=self.elapsed,
            deadline_overrun_noninterruptible_work_seconds=max(0.,self.elapsed-self.total),
            remaining_search_seconds=self.remaining,elapsed_component_wall_seconds=self.clock()-self.component_started,
            loop_started=self.loop_started is not None,loop_stopped=self.loop_stopped is not None,
            stagnation_early_stop=False,no_improvement_early_stop=False,
            included=['candidate evaluation','ranking and updates','physical/electrical effect evaluation',
                'neighborhood Gurobi solves','validation and checkpointing inside the loop',
                'stage transitions','search-loop overhead'],
            excluded=['one-time model/seed preparation before loop entry','cached coefficient generation',
                'Fresh and Actual replay','final export after loop deadline'],observations=self.observations)


class ContinuousSweep(FamilySweep):
    def observe(self,used,material):
        self.stage_families.add(self.family);self.neighborhoods+=1
        if material:
            self.material_improvements+=1;self._record(used,'MATERIAL_CURRENT_OBJECTIVE_IMPROVEMENT')
            self._begin('NORMAL',used);return True
        if used<self.family_deadline:return False
        self.families.add(self.family)
        if self.family_index<len(self.order)-1:
            self.family_index+=1;self.family_started=used;return False
        self._record(used,'NO_IMPROVEMENT_SWEEP_CONTINUE_SEARCH')
        if self.mode=='NORMAL':
            self.normal_completed+=1;self._begin('NORMAL' if self.priority==4 else 'DIVERSIFICATION',used)
        else:
            self.diversification_completed+=1;self._begin('NORMAL',used)
        return True

    def finish(self,used,reason):
        super().finish(used,'SEARCH_LOOP_WALL_CLOCK_LIMIT' if reason=='POLICY_DAY_HARD_CAP_REACHED'
            else 'LEX_STAGE_WALL_CLOCK_ALLOCATION_COMPLETE')

    def metrics(self):
        r=super().metrics();r.update(compute_control_version=VERSION,
            budget_basis='CONTINUOUS_SEARCH_LOOP_WALL_CLOCK',stagnation_early_stop=False,
            no_improvement_early_stop=False,global_convergence_certified=False)
        return r


def remaining_limit(remaining,family_remaining,overhead,minimum):
    return max(0.,min(60.,remaining,max(.001,family_remaining)))


_solve=adapted(OriginalBoundedLex._solve,[
    ('        model.optimize(cb)',
     '        if self.budget.stage_remaining<=0:return self.values.copy(),self._expired_solve()\n        model.Params.TimeLimit=max(0.,min(seconds,self.budget.stage_remaining))\n        model.optimize(cb)'),
    ('        if where==GRB.Callback.MIPSOL:first.append(float(m.cbGet(GRB.Callback.RUNTIME)))',
     '        if self.budget.stage_remaining<=0:m.terminate()\n        if where==GRB.Callback.MIPSOL:first.append(float(m.cbGet(GRB.Callback.RUNTIME)))')
])

_optimize=adapted(OriginalBoundedLex.optimize,[
    ('self.control=FamilySweep(priority,self.budget.used,self.exploration_scale)',
     "self.control=FamilySweep(priority,self.budget.used,self.exploration_scale)\n    self.live(label,'SEARCH_LOOP_ENTERED',start_used)"),
    ('deadline-self.budget.used>self.overhead_reserve+self.minimum_solve_seconds',
     'deadline-self.budget.used>0.'),
    ('            if not groups:break',
     "            if not groups:raise RuntimeError('EMPTY_NEIGHBORHOOD_WITH_REMAINING_WALL_CLOCK')\n            if self.budget.used>=deadline:break"),
    ('            if proposal and improves and cut_pass and locks_pass and canonical_pass:',
     '            if proposal and improves and cut_pass and locks_pass and canonical_pass and self.budget.elapsed<self.budget.total:'),
    ('self.overhead_reserve=max(self.overhead_reserve,1.5*(overhead+solver_startup))','self.overhead_reserve=0.'),
    ("            if stage_visits>=10000:raise RuntimeError('NEIGHBORHOOD_PROGRESS_GUARD')",
     "            # The monotonic deadline bounds repeated small neighborhoods; no iteration/stagnation cutoff."),
    ("    final_started=time.perf_counter()",
     "    if self.budget.remaining<=0:self.budget.stop_loop()\n    final_started=time.perf_counter()"),
    ("self.control.finish(self.budget.used,'POLICY_DAY_HARD_CAP_REACHED' if self.budget.remaining<=self.overhead_reserve+self.minimum_solve_seconds else 'STAGE_SOFT_GUARD_REACHED')",
     "self.control.finish(self.budget.used,'POLICY_DAY_HARD_CAP_REACHED' if self.budget.remaining<=0 else 'STAGE_SOFT_GUARD_REACHED')"),
    ('elif refresh:', 'elif refresh and self.budget.used<deadline:'),
    ('missing=max(0.,time.perf_counter()-stage_wall_started-(self.budget.used-start_used))','missing=0.')
],dict(FamilySweep=ContinuousSweep,objective_floor=lambda *a,**kw:None,neighborhood_time_limit=remaining_limit))


class LoopBoundedLex(OriginalBoundedLex):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        assert isinstance(self.budget,LoopBudget)
        # Retain the original P1 -> P5 allocation and exact priority locks.
        self.overhead_reserve=0.
        if self.context is not None and self.output.name=='A0':
            from v41r4_loop_runtime import MAY_OUT
            expected=read(MAY_OUT/self.context.day/'B0_DAYAHEAD_SUMMARY.json')['OBJECTIVE_VECTOR']
            assert all(abs(a-b)<=t for a,b,t in zip(self.initial_vector,expected,core.TOLERANCES)), 'B1_INITIAL_INCUMBENT_NOT_SAME_DAY_B0'
            assert not (self.output/'RECOVERED_SEED_AUDIT.json').exists(), 'PREVIOUS_B1_SEED_FORBIDDEN'
            write_json(self.output/'B0_COLD_START_VERIFICATION.json',dict(status='PASS',initial_vector=self.initial_vector,
                B0_vector=expected,previous_B1_seed_used=False,checked_before_search_timer=True))

    def _expired_solve(self):
        return dict(status=core.GRB.TIME_LIMIT,runtime_seconds=0.,solver_runtime_seconds=0.,node_count=0.,work=0.,
            solution_count=0,first_incumbent_seconds=None,neighborhood_gap=None,
            termination='WALL_CLOCK_EXPIRED_BEFORE_SOLVER_ENTRY')

    _solve=_solve

    def optimize(self,label,callback=None):
        self.budget.start_loop()
        priority=core.STAGES.get(label,self.index)
        self.budget.stage_deadline=float(self.deadlines[min(priority,len(self.deadlines)-1)])
        r=_optimize(self,label,callback)
        r.update(search_loop_wall_seconds=self.budget.used,budget_basis='CONTINUOUS_SEARCH_LOOP_WALL_CLOCK',
            stagnation_early_stop=False,no_improvement_early_stop=False)
        if self.budget.remaining<=0:self.budget.stop_loop()
        self.budget.stages[-1].update(r)
        path=self.output/'BOUNDED_SOLVER_REPORT.json';v=read(path)
        v.update(contract=VERSION,compute_control_version=VERSION,stages=self.stages,
            budget_basis='CONTINUOUS_SEARCH_LOOP_WALL_CLOCK',search_accounting=self.budget.report())
        write_json(path,v)
        return r

    def live(self,label,status,start_used):
        super().live(label,status,start_used)
        path=self.output/'F_AND_O_LIVE.json'
        if path.exists():
            r=read(path);r.update(compute_control_version=VERSION,
                budget_basis='CONTINUOUS_SEARCH_LOOP_WALL_CLOCK',search_loop_wall_seconds=self.budget.used,
                search_loop_started_at_unix=self.budget.loop_started_unix,search_loop_stopped=self.budget.loop_stopped is not None,
                elapsed_component_wall_seconds=self.budget.clock()-self.budget.component_started,
                stagnation_early_stop=False,no_improvement_early_stop=False)
            write_json(path,r)


def engine(*args,**kwargs):
    budget=args[3] if len(args)>3 else kwargs.get('budget')
    return (LoopBoundedLex if isinstance(budget,LoopBudget) else OriginalBoundedLex)(*args,**kwargs)


def install():core.BoundedLex=engine
