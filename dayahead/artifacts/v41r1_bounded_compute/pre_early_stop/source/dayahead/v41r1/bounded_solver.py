"""Finite shared optimization budget; verified incumbents survive every status.

Bounds from a fixed neighborhood are never treated as global bounds. All
original rows remain in the reused model. Higher priorities are locked by
the caller to accepted values, without multiplying by the target MIP gap.
"""
from pathlib import Path
import hashlib
import math
import time
import re
import numpy as np
from gurobipy import GRB
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.preflight import record
from .feasible_seed import row_audit

TOTAL_SECONDS=1800.
NOMINAL_SECONDS=(900.,480.,240.,150.,30.)
CONTRACT='V41R1_BOUNDED_COMPUTE_30MIN_V1'


def finite(x):
    x=float(x)
    return x if math.isfinite(x) and abs(x)<1e90 else None


def relative_gap(incumbent,bound):
    if incumbent is None or bound is None:return None
    return abs(incumbent-bound)/abs(incumbent) if incumbent else (0. if bound==0 else None)


def classification(incumbent,bound,target,*,solver_status=None,matheuristic=False):
    if incumbent is None:return 'NO_FEASIBLE_INCUMBENT'
    gap=relative_gap(incumbent,bound)
    if solver_status==GRB.OPTIMAL and gap==0:return 'PROVEN_OPTIMAL'
    if matheuristic:return 'MATHEURISTIC_BOUNDED_COMPUTE'
    if gap is not None and gap<=target:return 'CERTIFIED_3PCT' if target else 'PROVEN_OPTIMAL'
    return 'BOUNDED_COMPUTE_FEASIBLE'


class PolicyBudget:
    def __init__(self,total=TOTAL_SECONDS):
        if not 0<float(total)<=TOTAL_SECONDS:raise ValueError('INVALID_POLICY_DAY_BUDGET')
        self.total=float(total);self.used=0.;self.calls=[]
    @property
    def remaining(self):return max(0.,self.total-self.used)
    def charge(self,seconds,stage):
        self.used+=float(seconds);self.calls.append(dict(stage=stage,seconds=float(seconds)))


class BoundedLex:
    def __init__(self,model,seed,output,budget=None,*,fallback=True,allocation=None,metadata=None,context=None,objective_expressions=None,validator=None,fixed_mess=()):
        self.model=model;self.values=np.asarray(seed,dtype=float).copy();self.output=Path(output)
        self.budget=budget or PolicyBudget();self.used_start=self.budget.used
        weights=np.asarray(allocation or NOMINAL_SECONDS,dtype=float)
        self.deadlines=self.used_start+np.cumsum(weights/weights.sum()*self.budget.remaining)
        self.index=0;self.stages=[];self.used_matheuristic=True;self.iteration=0
        self.context=context;self.fixed_mess=fixed_mess;self.metadata=metadata or {};self.expressions=objective_expressions or [model.getObjective()]
        self.validator=validator;self.vars=model.getVars();model.update();self.names=model.getAttr('VarName',self.vars)
        self.decision_groups={}
        for i,name in enumerate(self.names):
            match=re.match(r'^(?:choice|placement|migration_route|migration_arrival|job)\[(\d+),',name)
            if match:self.decision_groups.setdefault(int(match[1]),[]).append(i)
        self.visits={g:0 for g in self.decision_groups};self.target_free=5000
        self.history=[];self.initial_vector=self.vector();self.overhead_reserve=min(10.,self.budget.total*.02);self._persist_incumbent('SEED')

    def value(self,expr):
        if isinstance(expr,(int,float,np.number)):return float(expr)
        if hasattr(expr,'index'):return float(self.values[expr.index])
        return float(expr.getConstant()+math.fsum(expr.getCoeff(i)*self.values[expr.getVar(i).index] for i in range(expr.size())))

    def vector(self):return [self.value(e) for e in self.expressions]

    def _persist_incumbent(self,label):
        folder=self.output/'bounded_checkpoints';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(str(len(self.stages))+'_'+str(self.iteration)+'_'+label+'.npz')
        np.savez_compressed(path,values=self.values)
        with np.load(path,allow_pickle=False) as z:
            if not np.array_equal(z['values'],self.values):raise RuntimeError('INCUMBENT_CHECKPOINT_READBACK')
        return record(path)

    def _solve(self,seconds,label):
        model=self.model;model.update();model.setAttr('Start',self.vars,self.values.tolist())
        model._v41_bound_scope='FIXED_NEIGHBORHOOD_ONLY_NOT_GLOBAL'
        model.Params.WorkLimit=GRB.INFINITY;model.Params.SolutionLimit=GRB.MAXINT
        model.Params.TimeLimit=max(0.,min(seconds,self.budget.remaining));first=[]
        def cb(m,where):
            if where==GRB.Callback.MIPSOL:first.append(float(m.cbGet(GRB.Callback.RUNTIME)))
        started=time.perf_counter();model.optimize(cb);elapsed=time.perf_counter()-started
        self.budget.charge(elapsed,label)
        data=dict(status=int(model.Status),runtime_seconds=elapsed,solver_runtime_seconds=float(model.Runtime),
            node_count=float(model.NodeCount),work=float(model.Work),solution_count=int(model.SolCount),
            first_incumbent_seconds=min(first) if first else None,raw_bound=finite(model.ObjBound),
            raw_incumbent=finite(model.ObjVal) if model.SolCount else None,
            neighborhood_gap=finite(model.MIPGap) if model.IsMIP and model.SolCount else None)
        if model.Status in (GRB.INFEASIBLE,GRB.INF_OR_UNBD):raise RuntimeError('VERIFIED_INCUMBENT_BUT_SOLVER_INFEASIBLE')
        if not model.SolCount:
            write_json(self.output/'MIPSTART_NO_INCUMBENT_DEFECT.json',dict(solver=data,retained_seed=row_audit(model,self.values)))
            raise RuntimeError('VERIFIED_SEED_MIPSTART_NOT_ACCEPTED')
        candidate=np.asarray(model.getAttr('X',self.vars));audit=row_audit(model,candidate)
        if audit['status']!='PASS':
            # A solver incumbent can exceed its own numerical tolerance. Reject
            # that proposal, preserving both evidence and the verified incumbent.
            # Never relax a row or terminate a policy-day with a valid incumbent.
            retained=row_audit(model,self.values)
            if retained['status']!='PASS':raise RuntimeError('RETAINED_INCUMBENT_HARD_CONSTRAINT_FAILURE')
            path=self.output/'bounded_checkpoints'/f'REJECTED_{self.index}_{self.iteration+1}.npz'
            np.savez_compressed(path,values=candidate)
            with np.load(path,allow_pickle=False) as saved:
                if not np.array_equal(saved['values'],candidate):raise RuntimeError('REJECTED_CANDIDATE_READBACK')
            receipt=path.with_suffix('.json')
            write_json(receipt,dict(status='REJECTED',reason='SOLVER_CANDIDATE_RESIDUAL_EXCEEDS_UNCHANGED_TOLERANCE',
                candidate_audit=audit,retained_incumbent_audit=retained,solver=dict(data),candidate=record(path),
                variable_names_source=str(self.output/'POLICY_FEASIBLE_SEED.npz'),
                physical_constraints_relaxed=False,incumbent_modified=False))
            data['candidate_rejection']=record(receipt)
            return self.values.copy(),data
        return candidate,data

    def _choose(self,stage):
        families=('ELECTRICAL_CRITICAL_WINDOW','IDC_BLOCK','RUNNING_MIGRATION_BLOCK','PENDING_RELOCATION_BLOCK','COVERAGE')
        family=families[self.iteration%len(families)];groups=sorted(self.decision_groups)
        cycle=min(self.visits.values(),default=0)
        # No second cycle before every eligible complete decision block was free.
        available=[g for g in groups if self.visits[g]==cycle]
        critical=24
        if self.context is not None:
            from dayahead.v40a.grid import evaluate_grid,controls_from_trajectory
            sites=tuple(self.context.capacity.aidc_ids);names={n:i for i,n in enumerate(self.names)}
            controls=np.zeros((len(self.context.coefficients),len(self.context.coefficients[0].control_names)))
            for t in range(len(controls)):
                for k,s in enumerate(sites):controls[t,k]=self.values[names[f'PCC[{t},{s}]']]
            if self.fixed_mess:controls=controls_from_trajectory(self.context.coefficients,controls[:,:len(sites)],self.fixed_mess)
            critical=24+evaluate_grid(self.context.coefficients,controls,self.context.nodes)['critical_slot']
        sites=sorted({s for meta in self.metadata.values() for s in meta.get('touched_sites',[])})
        site_blocks=[sites[i:i+2] for i in range(0,len(sites),2)]
        site_block=site_blocks[(self.iteration//5)%len(site_blocks)] if site_blocks else []
        def priority(g):
            meta=self.metadata.get(g,{})
            if family=='ELECTRICAL_CRITICAL_WINDOW':score=not(meta.get('earliest_effect',0)<=critical+2 and meta.get('latest_effect',120)>critical-2)
            elif family=='IDC_BLOCK':score=not(set(site_block)&set(meta.get('touched_sites',[])))
            elif family=='RUNNING_MIGRATION_BLOCK':score=not meta.get('can_migrate',False)
            elif family=='PENDING_RELOCATION_BLOCK':score=not meta.get('can_relocate',False)
            else:score=False
            return (score,g)
        selected=[];count=0
        for g in sorted(available,key=priority):
            size=len(self.decision_groups[g])
            if size>10000:raise RuntimeError('COMPLETE_JOB_BLOCK_EXCEEDS_MAX_FREE_DISCRETE:'+str(g))
            if selected and count+size>self.target_free:continue
            selected.append(g);count+=size
            if count>=self.target_free:break
        return selected,dict(family=family,cycle=cycle,critical_issue_slot=critical,critical_window_halfwidth_slots=2,
            IDC_partition=site_blocks,current_IDC_block=site_block,target_free_discrete=self.target_free,
            MIN_FREE_DISCRETE=2000,MAX_FREE_DISCRETE=10000,complete_job_domains_opened=True)

    def coverage(self):
        rows=[];total=visited=0
        for g in sorted(self.decision_groups):
            meta=self.metadata.get(g,{})
            members=meta.get('members',[str(g)]);n=meta.get('candidate_count',len(self.decision_groups[g]))
            total+=n*len(members);visited+=n*len(members)*int(self.visits[g]>0)
            rows.append(dict(group=g,members=members,option_index_start=0,option_index_end_exclusive=n,
                CANDIDATE_VISIT_COUNT=self.visits[g],all_options_share_visit_count=True))
        value=dict(total_eligible_candidates=total,unique_candidates_ever_opened=visited,
            total_eligible_relocation_jobs=sum(len(self.metadata.get(g,{}).get('members',[g])) for g in self.decision_groups if self.metadata.get(g,{}).get('can_relocate')),
            total_eligible_migration_jobs=sum(len(self.metadata.get(g,{}).get('members',[g])) for g in self.decision_groups if self.metadata.get(g,{}).get('can_migrate')),
            visit_count_distribution={str(v):sum(self.metadata.get(g,{}).get('candidate_count',len(self.decision_groups[g]))*len(self.metadata.get(g,{}).get('members',[g])) for g in self.visits if self.visits[g]==v) for v in sorted(set(self.visits.values()))},
            fraction_candidates_visited=visited/total if total else 1.,
            candidates_never_opened=total-visited,exhaustive_coverage=visited==total,
            visit_count_encoding='EXACT_RUN_LENGTH_BY_JOB_AND_FULL_OPTION_INDEX_RANGE',candidate_visits=rows,
            scientific_candidate_pruning=0,unvisited_reason='FINITE_COMPUTE_OR_STAGE_STAGNATION',
            full_candidate_manifest=str(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json'))
        write_json(self.output/'CANDIDATE_COVERAGE_REPORT.json',value)
        return value

    def optimize(self,label,callback=None):
        import psutil
        model=self.model;model.update();objective=model.getObjective();stage_index=self.index;self.index+=1
        deadline=float(self.deadlines[min(stage_index,len(self.deadlines)-1)])
        allocated=max(0.,deadline-self.budget.used);start_used=self.budget.used
        target=.03 if stage_index<2 else 0.;model.Params.MIPGap=target;model.Params.MIPGapAbs=0.
        before=self.value(objective);bound=None;global_status=None;calls=[]
        decision_ids=sorted(i for ids in self.decision_groups.values() for i in ids)
        decision_vars=[self.vars[i] for i in decision_ids]
        original_lb=model.getAttr('LB',decision_vars);original_ub=model.getAttr('UB',decision_vars)
        original={i:(lb,ub) for i,lb,ub in zip(decision_ids,original_lb,original_ub)}
        consecutive_no_improvement=0;stage_visits=0;stage_opened=set()
        try:
            while deadline-self.budget.used>self.overhead_reserve+.2 and self.decision_groups:
                iteration_started=time.perf_counter();used_before_iteration=self.budget.used
                groups,neighborhood=self._choose(stage_index)
                if not groups:break
                free={i for g in groups for i in self.decision_groups[g]}
                model.setAttr('LB',decision_vars,[original[i][0] if i in free else float(round(self.values[i])) for i in decision_ids])
                model.setAttr('UB',decision_vars,[original[i][1] if i in free else float(round(self.values[i])) for i in decision_ids]);model.update()
                old=self.values.copy();old_vector=self.vector();old_obj=self.value(objective)
                limit=min(60.,deadline-self.budget.used-self.overhead_reserve)
                write_json(self.output/'F_AND_O_LIVE.json',dict(day=getattr(self.context,'day',None),stage=label,
                    iteration=self.iteration+1,status='SOLVING',budget_used_seconds=self.budget.used,
                    total_budget_seconds=self.budget.total,coverage_fraction=self.coverage()['fraction_candidates_visited'],
                    incumbent=self.vector(),neighborhood=neighborhood,global_bound=None))
                candidate,data=self._solve(limit,label+':F_AND_O');calls.append(data)
                self.values=candidate;accepted=False;semantic=None;canonical_pass=True
                if self.validator is not None:
                    semantic=self.validator()
                    if semantic['status']!='PASS':raise RuntimeError('F_AND_O_JOB_MATERIALIZATION_FAILED')
                    names_to_index={n:i for i,n in enumerate(self.names)}
                    for name,value in semantic.get('canonical_auxiliary_values',{}).items():
                        self.values[names_to_index[name]]=value
                    canonical_audit=row_audit(model,self.values)
                    canonical_pass=canonical_audit['status']=='PASS'
                    semantic['canonical_model_substitution']=canonical_audit
                new_vector=self.vector()
                tolerances=[1e-10,1e-9,0.,0.,0.][:len(old_vector)]
                comparison=0
                for a,b,tol in zip(new_vector,old_vector,tolerances):
                    if a<b-tol:comparison=-1;break
                    if a>b+tol:comparison=1;break
                if comparison<0 and canonical_pass and not data.get('candidate_rejection'):
                    # Hard rows have already passed; independently materialize
                    # job-level GPU/rack/WAN/electrical state before acceptance.
                    semantic=semantic or {'status':'PASS','scope':'MODEL_ONLY_TEST'}
                    if semantic['status']!='PASS':raise RuntimeError('F_AND_O_JOB_MATERIALIZATION_FAILED')
                    accepted=True
                else:
                    self.values=old
                for g in groups:self.visits[g]+=1
                stage_opened.update(groups)
                self.iteration+=1;stage_visits+=1
                checkpoint=self._persist_incumbent('ACCEPTED' if accepted else 'RETAINED')
                coverage=self.coverage();memory=psutil.Process().memory_info()
                proof=dict(day=getattr(self.context,'day',None),policy='B1' if model.ModelName=='V40G_JOINT_AIDC' else 'B3',
                    objective_stage=label,iteration=self.iteration,neighborhood_id=f'{stage_index}:{self.iteration}',
                    neighborhood=neighborhood,free_cohorts=groups,
                    free_job_count=sum(len(self.metadata.get(g,{}).get('members',[g])) for g in groups),
                    free_candidate_count=sum(self.metadata.get(g,{}).get('candidate_count',len(self.decision_groups[g]))*len(self.metadata.get(g,{}).get('members',[g])) for g in groups),
                    free_discrete_variable_count=len(free),total_model_variables=model.NumVars,matrix_nonzeros=model.NumNZs,
                    candidate_coverage_count=coverage['unique_candidates_ever_opened'],coverage_fraction=coverage['fraction_candidates_visited'],
                    incumbent_before=old_vector,incumbent_after=self.vector(),accepted=accepted,
                    higher_priority_locks=[dict(name=c.ConstrName,rhs=c.RHS) for c in model.getConstrs() if 'LOCK' in c.ConstrName or 'EXACT_CAP' in c.ConstrName],
                    solve_runtime=data['runtime_seconds'],solver_status=data['status'],neighborhood_MIP_gap=data['neighborhood_gap'],
                    bound_scope='NEIGHBORHOOD_ONLY_NOT_GLOBAL',memory_RSS_bytes=memory.rss,
                    changed_groups=[g for g in groups if any(abs(old[i]-self.values[i])>.5 for i in self.decision_groups[g])],
                    changed_job_ids=[u for g in groups if any(abs(old[i]-self.values[i])>.5 for i in self.decision_groups[g]) for u in self.metadata.get(g,{}).get('members',[])],
                    changed_relocation_variables=[self.names[i] for i in free if abs(old[i]-self.values[i])>.5 and self.names[i].startswith(('placement','choice','job'))],
                    changed_migration_variables=[self.names[i] for i in free if abs(old[i]-self.values[i])>.5 and self.names[i].startswith('migration_')],
                    semantic_validation=semantic,candidate_rejection=data.get('candidate_rejection'),
                    artifact=checkpoint,first_incumbent_seconds=data['first_incumbent_seconds'])
                write_json(self.output/'bounded_checkpoints'/('ITERATION_'+str(self.iteration)+'.json'),proof)
                self.history.append({k:proof[k] for k in ('objective_stage','iteration','neighborhood_id','incumbent_before','incumbent_after','accepted','candidate_rejection','solve_runtime','coverage_fraction','artifact')})
                write_json(self.output/'IMPROVEMENT_TRACE.json',self.history)
                consecutive_no_improvement=0 if accepted else consecutive_no_improvement+1
                old_target=self.target_free
                if data['runtime_seconds']<10:self.target_free=min(10000,self.target_free+1000)
                elif data['status']==GRB.TIME_LIMIT:self.target_free=max(2000,self.target_free-1000)
                if self.target_free!=old_target:
                    write_json(self.output/'bounded_checkpoints'/('SIZE_CHANGE_'+str(self.iteration)+'.json'),dict(before=old_target,after=self.target_free,reason='FAST_SOLVE' if self.target_free>old_target else 'TIME_CAP',candidate_removals=0))
                # One complete coverage sweep without improvement is a finite
                # stagnation stop; unspent time rolls to the next priority.
                overhead=max(0.,time.perf_counter()-iteration_started-(self.budget.used-used_before_iteration))
                self.budget.charge(overhead,label+':VALIDATE_AND_PERSIST')
                self.overhead_reserve=max(self.overhead_reserve,overhead*1.5)
                if consecutive_no_improvement>=5 and len(stage_opened)==len(self.decision_groups):break
                if stage_visits>=10000:raise RuntimeError('NEIGHBORHOOD_PROGRESS_GUARD')
        finally:
            model.setAttr('LB',decision_vars,original_lb);model.setAttr('UB',decision_vars,original_ub);model.update()
        audit=row_audit(model,self.values)
        if audit['status']!='PASS':raise RuntimeError('FINAL_STAGE_INCUMBENT_NOT_FEASIBLE')
        incumbent=self.value(objective);gap=relative_gap(incumbent,bound)
        category='F_AND_O_NO_GLOBAL_CERTIFICATE'
        entry=dict(stage=label,status=calls[-1]['status'] if calls else None,OPTIMAL=False,incumbent=incumbent,bound=bound,
            best_bound=bound,achieved_relative_gap=gap,requested_relative_gap=target,requested_absolute_gap=0.,
            target_gap=target,classification=category,time_budget_seconds=allocated,runtime_seconds=self.budget.used-start_used,
            policy_day_used_seconds=self.budget.used,policy_day_total_budget_seconds=self.budget.total,unused_time_rolls_forward=True,
            termination_reason='BUDGET_OR_STAGNATION_WITH_FEASIBLE_INCUMBENT',accepted_within_registered_gap=False,
            feasible_incumbent_accepted=True,exact_optimum_certified=False,optimality_certificate=category,
            node_count=sum(c['node_count'] for c in calls),work=sum(c['work'] for c in calls),solver_calls=calls,
            first_incumbent_seconds=next((c['first_incumbent_seconds'] for c in calls if c['first_incumbent_seconds'] is not None),None),
            feasibility=audit,checkpoint=self._persist_incumbent('STAGE_ACCEPTED'),accepted_objective_vector=self.vector())
        self.stages.append(entry);self.coverage()
        write_json(self.output/'F_AND_O_LIVE.json',dict(day=getattr(self.context,'day',None),stage=label,
            iteration=self.iteration,status='STAGE_COMPLETE',budget_used_seconds=self.budget.used,
            total_budget_seconds=self.budget.total,coverage_fraction=self.coverage()['fraction_candidates_visited'],
            incumbent=self.vector(),global_bound=None))
        write_json(self.output/'BOUNDED_SOLVER_REPORT.json',dict(contract=CONTRACT,stages=self.stages,
            optimization_seconds=self.budget.used,total_budget_seconds=self.budget.total,classification=category,
            method='bounded-compute fix-and-optimize matheuristic',global_bound_pass='NOT_RUN',one_model_reused=True))
        return entry
