"""Unchanged original BoundedLex search; IEEE8500 grid, exact AC and telemetry."""
from common8500 import *
import gurobipy as gp
from dayahead.v41r1 import bounded_solver,feasible_seed,migration_memory
from dayahead.v40a import grid
from dayahead.v40g import optimizer
from v41r4_loop_budget import LoopBoundedLex
from v41r4_ieee8500_adapter import original_solver_binding
import grid8500
from types import FunctionType
class ASCIIPath(type(Path())):
    def resolve(self,strict=False):
        assert Path(self).absolute().is_relative_to(P)
        return self.absolute()

class ProductionLex(LoopBoundedLex):
    def __init__(self,*a,**kw):
        self.ac_count=0;self.ac_times=[];self.solve_times=[];self.ranking_seconds=0.;self.ranking_calls=0;self.milestones={};self.latest=None;self.done=threading.Event();self.accepted_counter=0
        original=kw.get('validator')
        def validated():
            r=original()
            if r['status']=='PASS':
                self.ac_count+=1;folder=self.output/'exact_proposals'/f'{self.ac_count:06}'
                ac=exact(r['materialized_power']['pcc'],self.fixed_mess,folder);self.ac_times.append(ac['wall_seconds'])
                r['exact_IEEE8500_AC']=record(folder/'AC_VALIDATION.json')
                if ac['status']!='PASS':r['status']='FAIL';r['reason']='EXACT_AC_REJECTED_KEEP_PRIOR_VALIDATED_INCUMBENT'
            return r
        kw['validator']=validated
        super().__init__(*a,**kw)
        from structural_projection import canonical,expr,digest
        expected=read(BIND/'IEEE8500_B1/STRUCTURE.json');model=self.model
        vv=[(v.VarName,v.VType,float(v.LB),float(v.UB)) for v in self.vars if v.VarName!='rho_max']
        assert digest(vv)==expected['decision_variable_sha256']
        assert [digest(expr(x)) for x in self.expressions[1:]]==expected['P2_P3_P4_P5_sha256']
        matrix=model.getA();linear=hashlib.sha256();wan=hashlib.sha256();general=hashlib.sha256();core_rows=0
        for i,c in enumerate(model.getConstrs()):
            if c.ConstrName.startswith('IEEE8500_'):continue
            start,end=matrix.indptr[i:i+2];terms=[(self.names[int(j)],float(v)) for j,v in zip(matrix.indices[start:end],matrix.data[start:end])]
            raw=canonical((c.ConstrName,c.Sense,float(c.RHS),terms))+b'\n';linear.update(raw);core_rows+=1
            if any(n.startswith(('WAN_','migration_','placement[')) for n,_ in terms):wan.update(raw)
        for c in model.getGenConstrs():
            kind=c.GenConstrType
            if kind==gp.GRB.GENCONSTR_PWL:
                x,y,xx,yy=model.getGenConstrPWL(c);data=[x.VarName,y.VarName,xx,yy]
            elif kind==gp.GRB.GENCONSTR_MAX:
                v,args,const=model.getGenConstrMax(c);data=[v.VarName,[x.VarName for x in args],const]
            elif kind==gp.GRB.GENCONSTR_INDICATOR:
                v,val,e,s,rhs=model.getGenConstrIndicator(c);data=[v.VarName,val,expr(e),s,rhs]
            else:raise RuntimeError('UNEXPECTED_NON_ELECTRICAL_GENERAL_CONSTRAINT')
            general.update(canonical([c.GenConstrName,kind,data])+b'\n')
        assert linear.hexdigest()==expected['linear_rows_sha256']
        assert wan.hexdigest()==expected['WAN_migration_linear_rows_sha256']
        assert general.hexdigest()==expected['general_rows_sha256']
        save(self.output/'PRODUCTION_AIDC_BINDING_GATE.json',dict(status='PASS',variables_SHA=digest(vv),P2_P3_P4_P5_SHA=[digest(expr(x)) for x in self.expressions[1:]],linear_SHA=linear.hexdigest(),WAN_SHA=wan.hexdigest(),general_SHA=general.hexdigest(),core_rows=core_rows,search_started=False,original_BoundedLex_stage_order=['P1','P2','P3','P4','P5'],budget_seconds=self.budget.total))
        self.checkpointer=threading.Thread(target=self._timer,daemon=True);self.checkpointer.start()
    def _persist_incumbent(self,label):
        ref=super()._persist_incumbent(label)
        self.latest=dict(checkpoint=ref,P1=self.vector()[0],objective_vector=self.vector(),iteration=self.iteration,accepted_at_unix=time.time())
        if label=='ACCEPTED':self.accepted_counter+=1
        return ref
    def _timer(self):
        while not self.done.wait(.25):
            if self.budget.loop_started is None:continue
            for seconds,label in [(1800,'30min'),(3600,'1h'),(7200,'2h'),(14400,'4h')]:
                if self.budget.elapsed>=seconds and label not in self.milestones and self.latest:
                    r=dict(self.latest,target_seconds=seconds,observed_seconds=self.budget.elapsed,recorded_unix=time.time(),policy=self.context.v41_policy,independently_validated_feasible=True)
                    save(self.output/'timed_checkpoints'/f'{label}.json',r);self.milestones[label]=r
            state(checkpoints=self.milestones,search_elapsed_seconds=self.budget.used)
    def live(self,label,status,start_used):
        super().live(label,status,start_used)
        mem=__import__('psutil').Process().memory_info()
        state(status='RUNNING',stage=self.context.v41_policy+':'+label,search_started=self.budget.loop_started is not None,search_started_unix=self.budget.loop_started_unix,search_elapsed_seconds=self.budget.used,search_stopped=self.budget.loop_stopped is not None,P1=self.vector()[0],objective_vector=self.vector(),neighborhood_solve_count=len(self.solve_times),solve_median_seconds=float(np.median(self.solve_times)) if self.solve_times else None,solve_P95_seconds=float(np.percentile(self.solve_times,95)) if self.solve_times else None,exact_AC_validation_count=self.ac_count,exact_AC_median_seconds=float(np.median(self.ac_times)) if self.ac_times else None,exact_AC_P95_seconds=float(np.percentile(self.ac_times,95)) if self.ac_times else None,incumbent_updates=self.accepted_counter,peak_RAM_bytes=getattr(mem,'peak_wset',mem.rss),checkpoints=self.milestones)
        if (P/'STOP_REQUESTED').exists():raise KeyboardInterrupt('USER_GRACEFUL_STOP_PRESERVE_CHECKPOINTS')
    def _solve(self,*a,**kw):
        started=time.perf_counter();r=super()._solve(*a,**kw);self.solve_times.append(time.perf_counter()-started);return r
    def _refresh_structure(self,*a,**kw):
        started=time.perf_counter();r=super()._refresh_structure(*a,**kw);self.ranking_seconds+=time.perf_counter()-started;self.ranking_calls+=1;return r
    def _choose(self,*a,**kw):
        started=time.perf_counter();r=super()._choose(*a,**kw);self.ranking_seconds+=time.perf_counter()-started;return r
    def optimize(self,*a,**kw):
        result=super().optimize(*a,**kw)
        if self.budget.remaining<=0:
            self._timer_final();self.done.set()
        return result
    def _timer_final(self):
        for seconds,label in [(1800,'30min'),(3600,'1h'),(7200,'2h'),(14400,'4h')]:
            if label not in self.milestones:
                assert self.budget.elapsed>=seconds
                r=dict(self.latest,target_seconds=seconds,observed_seconds=self.budget.elapsed,independently_validated_feasible=True)
                save(self.output/'timed_checkpoints'/f'{label}.json',r);self.milestones[label]=r
        state(checkpoints=self.milestones,search_stopped=True)
        coverage=self.coverage();exposures=sum(int(k)*v for k,v in coverage['visit_count_distribution'].items())
        save(self.output/'SCALABILITY_METRICS.json',dict(coefficient_generation_wall_seconds=read(PREF/'COEFFICIENT_GENERATION.json')['wall_seconds'],candidate_generation_seconds=0.,candidate_generation_reason='Immutable full stream consumed without regeneration',candidate_ranking_seconds=self.ranking_seconds,ranking_refresh_count=self.ranking_calls,candidate_domain_exposures=exposures,candidate_domain_exposures_per_second=exposures/max(self.budget.used,1e-9),candidate_evaluations_per_second=len(self.solve_times)/max(self.budget.used,1e-9),candidate_evaluation_unit='Complete-domain neighborhood proposal solve; raw candidate exposure rate reported separately',neighborhood_LP_MILP_solve_count=len(self.solve_times),solve_median_seconds=float(np.median(self.solve_times)) if self.solve_times else None,solve_P95_seconds=float(np.percentile(self.solve_times,95)) if self.solve_times else None,exact_AC_validation_count=self.ac_count,AC_median_seconds=float(np.median(self.ac_times)) if self.ac_times else None,AC_P95_seconds=float(np.percentile(self.ac_times,95)) if self.ac_times else None,incumbent_updates=self.accepted_counter,P1_checkpoints={k:v['P1'] for k,v in self.milestones.items()},time_to_best_P1_seconds=min((r['policy_day_seconds'] for r in self.accepted_improvements if r['after'][0]==self.vector()[0]),default=0.),peak_RAM_bytes=getattr(__import__('psutil').Process().memory_info(),'peak_wset',0)))

def run(ctx,role):
    folder=P/role;ctx.v41_policy=role;grid8500.CTX=ctx
    ctx.production_electrical_rows=P/('B1_electrical_rows' if role=='B1' else 'B3_A1_electrical_rows')
    old=(grid.add_grid,grid.evaluate_grid,migration_memory.Path,feasible_seed.Path)
    grid.add_grid=grid8500.add_grid;grid.evaluate_grid=evaluate_grid;migration_memory.Path=ASCIIPath;feasible_seed.Path=ASCIIPath
    state(status='RUNNING',stage=role+':MODEL_BUILD',search_started=False,search_stopped=False,checkpoints={})
    started=time.perf_counter()
    try:
        with original_solver_binding(ctx,'B1' if role=='B1' else 'B3_A1',folder) as solver:
            bounded_solver.BoundedLex=ProductionLex
            solver.__globals__.update(add_grid=grid8500.add_grid,evaluate_grid=evaluate_grid,Path=ASCIIPath)
            if role=='B1':assert solver.__code__ is optimizer.solve.__code__
            r=solver(ctx.reference,ctx.power['pcc'],ctx,folder)
            assert ctx.v41_policy_budget.total==14400 and ctx.v41_policy_budget.used==14400
        ac=exact(r['PCC'],getattr(ctx,'v41_fixed_mess',()),folder/'final_exact')
        assert ac['status']=='PASS'
        save(folder/'FINAL_AUTHORITY.json',dict(status='PASS',P1=r['grid']['rho_max'],AC=ac['metrics'],search_budget_seconds=14400,total_runtime_seconds=time.perf_counter()-started,decision=record(folder/'ACCEPTED_AIDC.json'),exact=record(folder/'final_exact/AC_VALIDATION.json')))
        return r
    finally:grid.add_grid,grid.evaluate_grid,migration_memory.Path,feasible_seed.Path=old
