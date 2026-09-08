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
import os
import numpy as np
from gurobipy import GRB
from .early_stop import write_compute_json as write_json
from dayahead.v41.preflight import record
from .feasible_seed import row_audit
from .early_stop import VERSION, FAMILIES, GUARDS, STAGES, TOLERANCES, IMPROVEMENT_EPS, IMPROVEMENT_NOISE, FamilySweep, material_improvement, objective_floor, current_structure, neighborhood_time_limit

TOTAL_SECONDS=1800.
NOMINAL_SECONDS=GUARDS
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
        self.total=float(total);self.used=0.;self.calls=[];self.stages=[]
    @property
    def remaining(self):return max(0.,self.total-self.used)
    def charge(self,seconds,stage):
        self.used+=float(seconds);self.calls.append(dict(stage=stage,seconds=float(seconds)))


class BoundedLex:
    def __init__(self,model,seed,output,budget=None,*,fallback=True,allocation=None,metadata=None,context=None,objective_expressions=None,validator=None,fixed_mess=()):
        initialized=time.perf_counter()
        self.model=model;self.values=np.asarray(seed,dtype=float).copy();self.output=Path(output)
        self.budget=budget or PolicyBudget();self.used_start=self.budget.used
        weights=np.asarray(NOMINAL_SECONDS if context is not None else (allocation or NOMINAL_SECONDS),dtype=float)
        self.deadlines=self.used_start+np.cumsum(weights/weights.sum()*self.budget.remaining)
        self.index=0;self.stages=[];self.used_matheuristic=True;self.iteration=0
        self.context=context;self.fixed_mess=fixed_mess;self.metadata=metadata or {};self.expressions=objective_expressions or [model.getObjective()]
        self.validator=validator;self.vars=model.getVars();model.update();self.names=model.getAttr('VarName',self.vars)
        self.decision_groups={}
        for i,name in enumerate(self.names):
            match=re.match(r'^(?:choice|placement|migration_route|migration_arrival|job)\[(\d+),',name)
            if match:self.decision_groups.setdefault(int(match[1]),[]).append(i)
        self.visits={g:0 for g in self.decision_groups};self.stage_counts=dict(self.visits);self.target_free=5000
        self.control=None;self.structure={};self.previous_groups=[];self.production_verified=False
        self.incumbent_jobs=[];self.accepted_improvements=[];self.rejected_proposals=0
        self.minimum_solve_seconds=5. if context is not None and model.NumVars>100000 else min(5.,self.budget.total/100.)
        self.exploration_scale=self.budget.remaining/TOTAL_SECONDS
        recovery=os.environ.get('V41_FO_RECOVERY_PLAN')
        if recovery and context is not None and model.ModelName=='V40G_JOINT_AIDC':
            from dayahead.paper_analysis.storage import read
            plan=read(recovery);ref=plan['checkpoint']
            if record(ref['path'])!=ref:raise RuntimeError('RECOVERY_CHECKPOINT_HASH_DRIFT')
            names=plan['seed_variable_names']
            if record(names['path'])!=names:raise RuntimeError('RECOVERY_VARIABLE_AXIS_HASH_DRIFT')
            with np.load(names['path']) as z:
                if z['names'].tolist()!=self.names:raise RuntimeError('RECOVERY_VARIABLE_AXIS_CHANGED')
            with np.load(ref['path']) as z:self.values=z['values'].copy()
            if read(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json')['candidate_set_SHA']!=plan['candidate_set_SHA']:
                raise RuntimeError('RECOVERY_AUTHORITATIVE_CANDIDATES_CHANGED')
            recovered=row_audit(model,self.values)
            if recovered['status']!='PASS':raise RuntimeError('RECOVERY_SEED_NOT_ORIGINAL_MODEL_FEASIBLE')
            if any(abs(a-b)>t for a,b,t in zip(self.vector(),plan['best_vector'],TOLERANCES)):
                raise RuntimeError('RECOVERY_OBJECTIVE_VECTOR_CHANGED')
            write_json(self.output/'RECOVERED_SEED_AUDIT.json',dict(status='PASS',plan=record(recovery),
                original_model_audit=recovered,objective_vector=self.vector(),full_authoritative_candidates_preserved=True))
        self.history=[];self.initial_vector=self.vector();self.overhead_reserve=min(30.,self.budget.total*.02);self._persist_incumbent('SEED')
        self.budget.charge(time.perf_counter()-initialized,'F_AND_O_INITIALIZE_CHECKPOINT')

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
        model=self.model;model.update()
        # Discard automatic previous-solve incumbents before tightening the
        # active improvement cut. Only the independently accepted start is
        # supplied; a stale solver incumbent is not a discovery certificate.
        model.reset(0);model.setAttr('Start',self.vars,self.values.tolist())
        model._v41_bound_scope='IMPROVEMENT_FEASIBILITY_NO_OBJECTIVE_CERTIFICATE'
        model.Params.WorkLimit=GRB.INFINITY;model.Params.SolutionLimit=1
        model.Params.MIPFocus=1
        # The search objective is constant. No percentage gap on P1-P5 can
        # terminate discovery; SolutionLimit=1 ends at the first feasible point.
        model.Params.MIPGap=1e-4;model.Params.MIPGapAbs=0.
        model.Params.TimeLimit=max(0.,min(seconds,self.budget.remaining));first=[]
        objective=model.getObjective();spec=self.search_spec
        scale=1000. if spec['priority']==0 else 1.
        cut=model.addConstr(scale*objective<=scale*spec['rhs'],name='FO_TEMPORARY_ACTIVE_OBJECTIVE_IMPROVEMENT')
        higher=[]
        for k in range(spec['priority']):
            factor=1000. if k==0 else 1.
            higher.append(model.addConstr(factor*self.expressions[k]<=factor*(self.vector()[k]+TOLERANCES[k]),
                name=f'FO_TEMPORARY_CURRENT_INCUMBENT_LOCK_P{k+1}'))
        model.setObjective(0.,GRB.MINIMIZE);model.update()
        def cb(m,where):
            if where==GRB.Callback.MIPSOL:first.append(float(m.cbGet(GRB.Callback.RUNTIME)))
        started=time.perf_counter()
        try:
            model.optimize(cb)
            elapsed=time.perf_counter()-started
            candidate=np.asarray(model.getAttr('X',self.vars)) if model.SolCount else None
            data=dict(status=int(model.Status),runtime_seconds=elapsed,solver_runtime_seconds=float(model.Runtime),
                node_count=float(model.NodeCount),work=float(model.Work),solution_count=int(model.SolCount),
                first_incumbent_seconds=min(first) if first else None,raw_bound=None,raw_incumbent=None,
                neighborhood_gap=None,search='FIRST_IMPROVEMENT_FEASIBILITY',constant_objective=0.,
                SolutionLimit=1,MIPFocus=1,percentage_gap_on_P1_P5=False,improvement_constraint=dict(spec),
                original_hard_feasibility_tolerance=float(model.Params.FeasibilityTol),
                original_integrality_tolerance=float(model.Params.IntFeasTol),
                termination='FIRST_FEASIBLE_PROPOSAL' if model.SolCount else 'NO_IMPROVEMENT_PROPOSAL_WITHIN_SEARCH_LIMIT')
        finally:
            # Revalidate on original rows and higher locks, after removing the
            # search-only cut. A no-improvement subproblem can be infeasible;
            # that says nothing about the retained original-model incumbent.
            model.remove([cut]+higher);model.setObjective(objective,GRB.MINIMIZE);model.update()
        self.budget.charge(elapsed,label)
        if candidate is None:return self.values.copy(),data
        audit=row_audit(model,candidate)
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
            self.rejected_proposals+=1
            return self.values.copy(),data
        return candidate,data

    def _semantic(self):
        from dayahead.paper_analysis.storage import read
        checked=self.validator() if self.validator else dict(status='PASS',scope='MODEL_ONLY_TEST')
        rows=checked.pop('materialized_jobs',None);power=checked.pop('materialized_power',None)
        if rows is not None:
            folder=self.output/'bounded_checkpoints'/f'PROPOSAL_{self.index}_{self.iteration+1}'
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/'JOBS.json';write_json(path,rows)
            if read(path)!=rows:raise RuntimeError('PROPOSAL_JOB_READBACK')
            checked['persisted_jobs']=record(path)
            if power is not None:
                path=folder/'POWER.npz';np.savez_compressed(path,**power)
                with np.load(path) as z:
                    if not all(np.array_equal(z[k],v) for k,v in power.items()):raise RuntimeError('PROPOSAL_POWER_READBACK')
                checked['persisted_power']=record(path)
        return checked,rows

    def _refresh_structure(self,priority):
        self.structure=current_structure(self,priority)
        path=self.output/'bounded_checkpoints'/f'STRUCTURE_P{priority+1}_SWEEP_{self.control.sweep_id}.json'
        write_json(path,dict(**self.structure,incumbent=self.vector(),sweep_id=self.control.sweep_id))
        self.structure_ref=record(path)

    def _choose(self,stage):
        family=self.control.family if self.control else FAMILIES[self.iteration%len(FAMILIES)]
        groups=sorted(self.decision_groups);cycle=min(self.visits.values(),default=0)
        diversify=self.control is not None and self.control.mode=='DIVERSIFICATION'
        critical=self.structure.get('critical_issue_slot',24)
        sites=sorted({s for meta in self.metadata.values() for s in meta.get('touched_sites',[])})
        site_blocks=[sites[i:i+2] for i in range(0,len(sites),2)]
        site_block=site_blocks[(self.iteration//5)%len(site_blocks)] if site_blocks else []
        near_slots={r['issue_slot'] for r in self.structure.get('near_binding_electrical_set',[])} or {critical}
        stress=self.structure.get('reserve_stress',[])
        effects=self.structure.get('current_job_effects',{})
        sensitivity=self.structure.get('critical_site_sensitivity',{})
        # Reuse a complete prior block as an overlap anchor, then favor low-visit
        # and different-source blocks. Entire job domains are always opened.
        anchors=self.previous_groups[:1] if diversify else []
        coupled=bool(stage==0 and effects and family in ('ELECTRICAL_CRITICAL_WINDOW','IDC_BLOCK'))
        capacity_release=[];critical_jobs=[];wan_partners=[]
        if coupled:
            uidgroup={u:g for g,m in self.metadata.items() for u in m.get('members',[]) if g in self.decision_groups}
            rows=[(u,r) for u,r in effects.items() if u in uidgroup]
            def critical_score(item):
                u,r=item
                return max((r['requested_GPU']*sensitivity.get(s,0.) for s,a,b in r['segments'] if any(a<=t<b for t in near_slots)),default=0.)
            active=sorted((x for x in rows if any(a<=critical<b for s,a,b in x[1]['segments'])),key=lambda x:(-critical_score(x),x[0]))
            per_site={}
            for u,r in active:
                s=next(s for s,a,b in r['segments'] if a<=critical<b)
                if per_site.get(s,0)>=2:continue
                per_site[s]=per_site.get(s,0)+1;capacity_release.append(uidgroup[u])
            critical_jobs=[uidgroup[u] for u,r in active[:4]]
            # The UID-serial WAN clock is a genuine coupling. Late small jobs
            # can make different restart times feasible for critical jobs.
            late=sorted((x for x in rows if x[1].get('checkpoint') is not None and self.metadata[uidgroup[x[0]]].get('can_migrate')),
                key=lambda x:(-x[1]['checkpoint'],x[1]['requested_GPU'],x[0]))
            wan_partners=[uidgroup[u] for u,r in late[:4]]
            anchors=wan_partners+critical_jobs+capacity_release+anchors
        def priority(g):
            meta=self.metadata.get(g,{})
            lo=meta.get('earliest_effect',0);hi=meta.get('latest_effect',120)
            active=any(lo<=t+2 and hi>t-2 for t in near_slots)
            if family=='ELECTRICAL_CRITICAL_WINDOW':
                if stage==1:
                    score=next((i for i,r in enumerate(stress) if lo<r['end'] and hi>r['start'] and r['site'] in meta.get('touched_sites',[])),len(stress))
                else:score=int(active) if diversify else int(not active)
            elif family=='IDC_BLOCK':score=not(set(site_block)&set(meta.get('touched_sites',[])))
            elif family=='RUNNING_MIGRATION_BLOCK':score=not meta.get('can_migrate',False)
            elif family=='PENDING_RELOCATION_BLOCK':score=not meta.get('can_relocate',False)
            else:score=0
            visits=self.stage_counts[g] if stage==1 else self.visits[g]
            if stage==1 and effects and family=='ELECTRICAL_CRITICAL_WINDOW':
                rows=[effects[u] for u in meta.get('members',[]) if u in effects]
                # Prioritize short checkpoint-enabled jobs in reserve-stressed
                # intervals; remaining families still rotate every full domain.
                score=(not meta.get('can_migrate'),min((r['end']-r['start'] for r in rows),default=10**9),score)
            return (visits,score,g) if diversify or family=='COVERAGE' else (score,visits,g)
        # Low-visit rotation remains complete; during diversification explicit
        # overlap is allowed before 100% raw coverage, per corrected contract.
        available=[g for g in groups if self.visits[g]==cycle] if self.control is None else groups
        ordered=sorted(available,key=priority)
        # Deterministically interleave origins at equal primary priority to
        # permit coupled receiving/source GPU, rack and WAN reallocations.
        buckets={}
        for g in ordered:
            key=(priority(g)[:2],self.metadata.get(g,{}).get('initial_site','UNKNOWN'))
            buckets.setdefault(key,[]).append(g)
        interleaved=[]
        ranks=sorted({k[0] for k in buckets})
        for rank in ranks:
            rows=[buckets[k] for k in sorted(buckets) if k[0]==rank]
            for i in range(max(map(len,rows),default=0)):
                interleaved.extend(row[i] for row in rows if i<len(row))
        selected=[];count=0;target=max(25000,self.target_free) if coupled else self.target_free
        for g in anchors+interleaved:
            if g in selected:continue
            size=len(self.decision_groups[g])
            if size>10000:raise RuntimeError('COMPLETE_JOB_BLOCK_EXCEEDS_MAX_FREE_DISCRETE:'+str(g))
            if selected and count+size>target:continue
            selected.append(g);count+=size
            if count>=target:break
        return selected,dict(family=family,cycle=cycle,critical_issue_slot=critical,critical_window_halfwidth_slots=2,
            IDC_partition=site_blocks,current_IDC_block=site_block,target_free_discrete=target,
            MIN_FREE_DISCRETE=2000,MAX_FREE_DISCRETE=25000 if coupled else 10000,complete_job_domains_opened=True,
            coupled_capacity_release_active=coupled,capacity_occupant_groups=[g for g in capacity_release if g in selected],
            critical_load_groups=[g for g in critical_jobs if g in selected],WAN_coupling_groups=[g for g in wan_partners if g in selected],
            permanent_cross_region_constraint=False,
            sweep_id=self.control.sweep_id if self.control else None,
            sweep_mode=self.control.mode if self.control else 'NORMAL',overlap_groups=[g for g in anchors if g in selected],
            structure=getattr(self,'structure_ref',None))

    def stage_coverage(self):
        counts={g:self.metadata.get(g,{}).get('candidate_count',len(ids))*len(self.metadata.get(g,{}).get('members',[g])) for g,ids in self.decision_groups.items()}
        total=sum(counts.values());opened=sum(n for g,n in counts.items() if self.stage_counts[g])
        return dict(STAGE_CANDIDATE_VISIT_COUNT=sum(n*self.stage_counts[g] for g,n in counts.items()),
            STAGE_UNIQUE_CANDIDATES_OPENED=opened,STAGE_COVERAGE_FRACTION=opened/total if total else 1.,
            STAGE_CANDIDATES_NOT_OPENED=total-opened,
            stage_candidate_visits=[dict(group=g,visits=self.stage_counts[g],candidate_count=n,complete_domain=True) for g,n in counts.items()],
            unvisited_reason='NOT_VISITED_WITHIN_COMPUTE_BUDGET')

    def live(self,label,status,start_used):
        live_started=time.perf_counter()
        coverage=self.coverage();metrics=self.control.metrics()
        # Full detailed records reside in the stage report and checkpoints.
        metrics.pop('sweeps',None)
        visits=self.stage_coverage();visits.pop('stage_candidate_visits')
        write_json(self.output/'F_AND_O_LIVE.json',dict(day=getattr(self.context,'day',None),stage=label,
            iteration=self.iteration,status=status,budget_used_seconds=self.budget.used,
            total_budget_seconds=self.budget.total,remaining_seconds=self.budget.remaining,
            stage_runtime_seconds=self.budget.used-start_used,coverage_fraction=coverage['fraction_candidates_visited'],
            incumbent=self.vector(),global_bound=None,**metrics,**visits))
        self.budget.charge(time.perf_counter()-live_started,label+':LIVE_STATUS_ACCOUNTING')

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
            scientific_candidate_pruning=0,unvisited_reason='NOT_VISITED_WITHIN_COMPUTE_BUDGET',
            full_candidate_manifest=str(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json'))
        write_json(self.output/'CANDIDATE_COVERAGE_REPORT.json',value)
        return value

    def optimize(self,label,callback=None):
        import psutil
        stage_wall_started=time.perf_counter()
        model=self.model;model.update();objective=model.getObjective();stage_index=self.index;self.index+=1
        priority=STAGES.get(label,stage_index)
        deadline=float(self.deadlines[min(priority if self.context is not None else stage_index,len(self.deadlines)-1)])
        allocated=max(0.,deadline-self.budget.used);start_used=self.budget.used
        target=None
        starting_vector=self.vector();before=self.value(objective);bound=None;global_status=None;calls=[]
        decision_ids=sorted(i for ids in self.decision_groups.values() for i in ids)
        decision_vars=[self.vars[i] for i in decision_ids]
        original_lb=model.getAttr('LB',decision_vars);original_ub=model.getAttr('UB',decision_vars)
        original={i:(lb,ub) for i,lb,ub in zip(decision_ids,original_lb,original_ub)}
        consecutive_no_improvement=0;stage_visits=0;self.stage_counts={g:0 for g in self.decision_groups}
        self.control=FamilySweep(priority,self.budget.used,self.exploration_scale)
        stage_setup=time.perf_counter()
        if self.validator is not None and self.context is not None:
            checked,rows=self._semantic()
            if checked['status']!='PASS':raise RuntimeError('STAGE_START_INDEPENDENT_VALIDATION_FAILED')
            if rows is not None:self.incumbent_jobs=rows
            self.production_verified=len(self.expressions)==5
        floor=objective_floor(priority,self.vector(),production_verified=self.production_verified)
        if floor:self.control.reason='OBJECTIVE_PROVEN_OPTIMAL'
        else:self._refresh_structure(priority)
        self.budget.charge(time.perf_counter()-stage_setup,label+':RECOMPUTE_STRUCTURE')
        try:
            while not self.control.reason and deadline-self.budget.used>self.overhead_reserve+self.minimum_solve_seconds and self.decision_groups:
                iteration_started=time.perf_counter();used_before_iteration=self.budget.used
                groups,neighborhood=self._choose(priority)
                if not groups:break
                free={i for g in groups for i in self.decision_groups[g]}
                model.setAttr('LB',decision_vars,[original[i][0] if i in free else float(round(self.values[i])) for i in decision_ids])
                model.setAttr('UB',decision_vars,[original[i][1] if i in free else float(round(self.values[i])) for i in decision_ids]);model.update()
                old=self.values.copy();old_vector=self.vector();old_obj=self.value(objective)
                family_remaining=self.control.family_deadline-self.budget.used
                limit=neighborhood_time_limit(deadline-self.budget.used,family_remaining,self.overhead_reserve,self.minimum_solve_seconds)
                if not limit:break
                self.live(label,'SOLVING',start_used)
                self.search_spec=dict(priority=priority,incumbent=old_vector[priority],
                    absolute_improvement=IMPROVEMENT_EPS[priority],rhs=old_vector[priority]-IMPROVEMENT_EPS[priority],
                    independent_noise_tolerance=IMPROVEMENT_NOISE[priority])
                candidate,data=self._solve(limit,label+':F_AND_O');calls.append(data)
                self.values=candidate;accepted=False;semantic=None;canonical_pass=True
                rows=None
                proposal=bool(data['solution_count'] and not data.get('candidate_rejection'))
                if self.validator is not None and proposal:
                    try:semantic,rows=self._semantic()
                    except Exception as error:semantic=dict(status='FAIL',reason=repr(error))
                    names_to_index={n:i for i,n in enumerate(self.names)}
                    for name,value in semantic.get('canonical_auxiliary_values',{}).items():
                        self.values[names_to_index[name]]=value
                    canonical_audit=row_audit(model,self.values)
                    canonical_pass=canonical_audit['status']=='PASS' and semantic['status']=='PASS'
                    semantic['canonical_model_substitution']=canonical_audit
                new_vector=self.vector()
                independently_recomputed=(semantic or {}).get('independent_objective_vector')
                if independently_recomputed is not None:
                    canonical_pass=canonical_pass and all(abs(a-b)<=tol for a,b,tol in zip(new_vector,independently_recomputed,TOLERANCES))
                locks_pass=all(new_vector[k]<=old_vector[k]+TOLERANCES[k] for k in range(min(priority,len(new_vector))))
                improves=old_vector[priority]-new_vector[priority]>IMPROVEMENT_NOISE[priority]
                cut_pass=new_vector[priority]<=self.search_spec['rhs']+IMPROVEMENT_NOISE[priority]
                if proposal and improves and cut_pass and locks_pass and canonical_pass:
                    # Hard rows have already passed; independently materialize
                    # job-level GPU/rack/WAN/electrical state before acceptance.
                    semantic=semantic or {'status':'PASS','scope':'MODEL_ONLY_TEST'}
                    if semantic['status']!='PASS':raise RuntimeError('F_AND_O_JOB_MATERIALIZATION_FAILED')
                    accepted=True
                    if rows is not None:self.incumbent_jobs=rows
                    self.accepted_improvements.append(dict(stage=label,iteration=self.iteration+1,
                        policy_day_seconds=self.budget.used,before=old_vector,after=new_vector))
                else:
                    if proposal:
                        self.rejected_proposals+=1
                        path=self.output/'bounded_checkpoints'/f'REJECTED_SEMANTIC_{self.index}_{self.iteration+1}.json'
                        write_json(path,dict(status='REJECTED_PROPOSAL',semantic=semantic,locks_pass=locks_pass,
                            active_objective_improves=improves,improvement_constraint_pass=cut_pass,original_model_pass=canonical_pass,
                            candidate_vector=new_vector,retained_vector=old_vector,physical_feasibility_tolerance=model.Params.FeasibilityTol))
                        data['candidate_rejection']=record(path)
                    self.values=old
                for g in groups:self.visits[g]+=1;self.stage_counts[g]+=1
                material=material_improvement(old_vector,self.vector(),priority,accepted)
                self.previous_groups=list(groups)
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
                    first_improvement_search=data.get('improvement_constraint'),percentage_gap_on_P1_P5=False,
                    bound_scope='NEIGHBORHOOD_ONLY_NOT_GLOBAL',memory_RSS_bytes=memory.rss,
                    changed_groups=[g for g in groups if any(abs(old[i]-self.values[i])>.5 for i in self.decision_groups[g])],
                    changed_job_ids=[u for g in groups if any(abs(old[i]-self.values[i])>.5 for i in self.decision_groups[g]) for u in self.metadata.get(g,{}).get('members',[])],
                    changed_relocation_variables=[self.names[i] for i in free if abs(old[i]-self.values[i])>.5 and self.names[i].startswith(('placement','choice','job'))],
                    changed_migration_variables=[self.names[i] for i in free if abs(old[i]-self.values[i])>.5 and self.names[i].startswith('migration_')],
                    semantic_validation=semantic,candidate_rejection=data.get('candidate_rejection'),
                    material_current_objective_improvement=material,stage_sweep_id=self.control.sweep_id,sweep_mode=self.control.mode,
                    artifact=checkpoint,first_incumbent_seconds=data['first_incumbent_seconds'])
                write_json(self.output/'bounded_checkpoints'/('ITERATION_'+str(self.iteration)+'.json'),proof)
                self.history.append({k:proof[k] for k in ('objective_stage','iteration','neighborhood_id','incumbent_before','incumbent_after','accepted','material_current_objective_improvement','stage_sweep_id','sweep_mode','candidate_rejection','solve_runtime','coverage_fraction','artifact')})
                write_json(self.output/'IMPROVEMENT_TRACE.json',self.history)
                consecutive_no_improvement=0 if material else consecutive_no_improvement+1
                old_target=self.target_free
                if data['runtime_seconds']<10:self.target_free=min(10000,self.target_free+1000)
                elif data['status']==GRB.TIME_LIMIT:self.target_free=max(2000,self.target_free-1000)
                if self.target_free!=old_target:
                    write_json(self.output/'bounded_checkpoints'/('SIZE_CHANGE_'+str(self.iteration)+'.json'),dict(before=old_target,after=self.target_free,reason='FAST_SOLVE' if self.target_free>old_target else 'TIME_CAP',candidate_removals=0))
                # Termination is based on current-stage family sweeps, never
                # on raw candidate coverage or a consecutive-failure counter.
                overhead=max(0.,time.perf_counter()-iteration_started-(self.budget.used-used_before_iteration))
                self.budget.charge(overhead,label+':VALIDATE_AND_PERSIST')
                solver_startup=max(0.,data['runtime_seconds']-data['solver_runtime_seconds'])
                self.overhead_reserve=max(self.overhead_reserve,1.5*(overhead+solver_startup))
                refresh=self.control.observe(self.budget.used,material)
                floor=objective_floor(priority,self.vector(),production_verified=self.production_verified)
                if floor:self.control.reason='OBJECTIVE_PROVEN_OPTIMAL'
                elif refresh:
                    started=time.perf_counter();self._refresh_structure(priority)
                    self.budget.charge(time.perf_counter()-started,label+':RECOMPUTE_STRUCTURE')
                self.live(label,'SEARCHING' if not self.control.reason else 'CONVERGED',start_used)
                if stage_visits>=10000:raise RuntimeError('NEIGHBORHOOD_PROGRESS_GUARD')
        finally:
            model.setAttr('LB',decision_vars,original_lb);model.setAttr('UB',decision_vars,original_ub);model.update()
        final_started=time.perf_counter()
        self.control.finish(self.budget.used,'POLICY_DAY_HARD_CAP_REACHED' if self.budget.remaining<=self.overhead_reserve+self.minimum_solve_seconds else 'STAGE_SOFT_GUARD_REACHED')
        audit=row_audit(model,self.values)
        if audit['status']!='PASS':raise RuntimeError('FINAL_STAGE_INCUMBENT_NOT_FEASIBLE')
        incumbent=self.value(objective);gap=relative_gap(incumbent,bound)
        category='F_AND_O_NO_GLOBAL_CERTIFICATE'
        entry=dict(stage=label,status=calls[-1]['status'] if calls else None,OPTIMAL=False,incumbent=incumbent,bound=bound,
            best_bound=bound,achieved_relative_gap=gap,requested_relative_gap=target,requested_absolute_gap=0.,
            target_gap=target,classification=category,time_budget_seconds=allocated,runtime_seconds=self.budget.used-start_used,
            policy_day_used_seconds=self.budget.used,policy_day_total_budget_seconds=self.budget.total,unused_time_rolls_forward=True,
            accepted_within_registered_gap=False,
            feasible_incumbent_accepted=True,exact_optimum_certified=False,optimality_certificate=category,
            node_count=sum(c['node_count'] for c in calls),work=sum(c['work'] for c in calls),solver_calls=calls,
            first_incumbent_seconds=next((c['first_incumbent_seconds'] for c in calls if c['first_incumbent_seconds'] is not None),None),
            feasibility=audit,checkpoint=self._persist_incumbent('STAGE_ACCEPTED'),accepted_objective_vector=self.vector(),
            starting_objective=before,starting_objective_vector=starting_vector,
            minimum_neighborhood_solver_seconds=self.minimum_solve_seconds,exploration_scale_from_remaining_component_budget=self.exploration_scale,
            final_objective=incumbent,neighborhoods_solved=stage_visits,
            search_method='FIRST_IMPROVEMENT_FEASIBILITY',percentage_gap_controls_discovery=False,
            absolute_improvement_epsilon=IMPROVEMENT_EPS[priority],objective_noise_tolerance=IMPROVEMENT_NOISE[priority],
            rejected_proposals=self.rejected_proposals,accepted_improvements=list(self.accepted_improvements),
            consecutive_no_improvement_diagnostic=consecutive_no_improvement,
            objective_floor_certificate=floor,**self.control.metrics(),**self.stage_coverage())
        self.budget.charge(time.perf_counter()-final_started,label+':FINAL_AUDIT_AND_CHECKPOINT')
        entry['runtime_seconds']=self.budget.used-start_used
        entry['policy_day_used_seconds']=self.budget.used
        missing=max(0.,time.perf_counter()-stage_wall_started-(self.budget.used-start_used))
        self.budget.charge(missing,label+':STAGE_SCHEDULING_OVERHEAD')
        entry['runtime_seconds']=self.budget.used-start_used
        entry['policy_day_used_seconds']=self.budget.used
        self.budget.stages.append(dict(component=str(self.output.name),**entry))
        self.stages.append(entry);self.coverage()
        self.live(label,'STAGE_COMPLETE',start_used)
        entry['runtime_seconds']=self.budget.used-start_used
        entry['policy_day_used_seconds']=self.budget.used
        self.budget.stages[-1].update(entry)
        write_json(self.output/'BOUNDED_SOLVER_REPORT.json',dict(contract=CONTRACT,compute_control_version=VERSION,stages=self.stages,
            TOTAL_UNUSED_BUDGET_SECONDS=self.budget.remaining,
            optimization_seconds=self.budget.used,total_budget_seconds=self.budget.total,classification=category,
            method='bounded-compute fix-and-optimize matheuristic',global_bound_pass='NOT_RUN',one_model_reused=True))
        return entry
