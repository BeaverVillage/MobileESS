"""Phase-I search heuristics; all certificates still use the original raw dual."""
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
from types import FunctionType
import inspect,linecache,math,re,textwrap
from time import perf_counter
import numpy as np
from v44.common import atomic,read,now
from v42_a_stage_phase1.runner import serial

EPS=Fraction(1,100000000)


def classification_atomic(original):
    def save(path,value):
        if isinstance(value,dict) and value.get('PASS') is False and 'R025B_FIXED_M1_FEASIBILITY_NOT_CERTIFIED_NO_RECOVERED_NEGATIVE_COLUMN' in value.get('error',''):
            value.update(classification='NOT_CERTIFIED',scientific_infeasibility_proven=False,
                full_native_phase1_positive_lower_bound_certified=False)
        return original(path,value)
    return save


def valid_candidates(candidates,completed):
    if not completed:raise PermissionError('R025B_MIGRATION_SEARCH_MUST_COMPLETE')
    unique={}
    for c in candidates:
        if not all(c.get(k) is True for k in ('physical_membership_PASS','exact_coupling_PASS','independent_price_PASS')):
            raise ValueError('R025B_UNVERIFIED_PHYSICAL_COLUMN')
        if Fraction(c['price'])>=-EPS:raise ValueError('R025B_NONNEGATIVE_OR_UNCERTIFIED_PRICE')
        if not c.get('native_local_replay',{}).get('PASS'):raise ValueError('R025B_LOCAL_REPLAY_REQUIRED')
        identity=c['class_id'],c['coefficient_sha256']
        if identity not in unique or Fraction(c['price'])<Fraction(unique[identity]['price']):unique[identity]=c
    return sorted(unique.values(),key=lambda c:(Fraction(c['price']),repr(c['identity'])))


def collect_targeted(function):
    function=inspect.unwrap(function)
    source=textwrap.dedent(inspect.getsource(function))
    old='    selected=select(candidates,True)'
    if source.count(old)!=1:raise ValueError('R025B_TARGETED_SOURCE_DRIFT')
    source=source.replace(old,'    selected=_R025Bcollect(candidates,True)')
    ns=dict(function.__globals__,_R025Bcollect=valid_candidates)
    worker=ns['worker']
    ns['worker']=FunctionType(worker.__code__,ns,worker.__name__,worker.__defaults__,worker.__closure__)
    exec(compile(source,__file__+'.targeted.generated','exec'),ns)
    return ns['targeted']


def features(candidate,axis_keys):
    sites=set();times=set();gpu=set()
    for row,value in candidate['coupling']:
        if not Fraction(value):continue
        key=axis_keys[int(row)]
        if key[0] in ('GPU','RUNTIME'):
            sites.add(str(key[1]));times.add(int(key[2]))
            if key[0]=='GPU':gpu.add((str(key[1]),int(key[2])))
    return sites,times,gpu


def choose(candidates,axis_keys,limit=64):
    pool=valid_candidates(candidates,True)
    if not pool:return [],dict(candidates=0,selected=0)
    magnitude=max(-Fraction(c['price']) for c in pool)
    effect=max((abs(float(c.get('residual_score',0))) for c in pool),default=0.) or 1.
    fs={id(c):features(c,axis_keys) for c in pool}
    selected=[];classes={};kinds={};sites=set();times=set();gpu=set();scores=[]
    while pool and len(selected)<limit:
        def rank(c):
            ss,tt,gg=fs[id(c)]
            exact_strength=float(-Fraction(c['price'])/magnitude)
            heuristic=max(0.,float(c.get('residual_score',0))/effect)
            overlap=len(gg&gpu)/max(1,len(gg))
            value=(2*exact_strength+heuristic+1.25/(1+classes.get(c['class_id'],0))
                +.5/(1+kinds.get(c['kind'],0))+.4*len(ss-sites)/max(1,len(ss))
                +.4*len(tt-times)/max(1,len(tt))-.6*overlap)
            return (-value,Fraction(c['price']),repr(c['identity']))
        unseen_kind=[c for c in pool if not kinds.get(c['kind'])]
        best=min(unseen_kind or pool,key=rank);scores.append(-rank(best)[0]);pool.remove(best);selected.append(best)
        ss,tt,gg=fs[id(best)];sites|=ss;times|=tt;gpu|=gg
        classes[best['class_id']]=classes.get(best['class_id'],0)+1
        kinds[best['kind']]=kinds.get(best['kind'],0)+1
    return selected,dict(candidates=len(candidates),selected=len(selected),class_counts=classes,kind_counts=kinds,
        sites=sorted(sites),times=sorted(times),greedy_heuristic_scores=scores,
        GPU_overlap_is_ranking_penalty_only=True,global_feasibility_or_optimality_claim=False,
        permanent_domain_deletions=False,exact_prices_changed=False)


class AdaptivePricing:
    def __init__(self,output,request=None):
        self.output=Path(output);self.request=request or {};self.round=0
        self.visited={};self.feedback=[];self.pending=None;self.previous=None;self.dual=None
        self.compiled={};self.last_full=-10;self.plan=None
        if self.request.get('r025b_adaptive_parent'):
            from v44.common import verify,read
            receipt=self.request['r025b_adaptive_parent'];verify([receipt]);saved=read(receipt['path'])
            if not saved.get('PASS') or not saved.get('scientific_weights_and_M1_unchanged'):
                raise ValueError('R025B_ADAPTIVE_CHECKPOINT_NOT_VERIFIED')
            self.feedback=saved['feedback'];self.visited=saved['visited']
            self.round=saved['next_round'];self.last_full=saved['last_full']
            if self.feedback:self.previous=Fraction(self.feedback[-1]['exact_full_Phi'])
        path=self.request.get('M1_result')
        if path:
            source=path['path'] if isinstance(path,dict) else path
            self.plan=read(source).get('MESS_plan')

    def plan_classes(self,attribution):
        eligible=[r['class_id'] for r in attribution['classes_ranked'] if r['inactive_candidates_available']]
        allowed=set(eligible);focus=[k for k in attribution['target_classes'] if k in allowed]
        slow=0
        for r in reversed(self.feedback):
            if r.get('relative_decrease') is None or r['relative_decrease']>=.15:break
            slow+=1
        full=(slow>=3 and self.round-self.last_full>=2) or (self.round>=4 and self.round-self.last_full>=5)
        if full:
            mode='FULL_ELIGIBLE';targets=eligible;self.last_full=self.round
        else:
            mode='EXPANDED' if slow>=2 else 'FOCUSED_PLUS_ROTATING'
            other=[k for k in eligible if k not in set(focus)]
            other.sort(key=lambda k:(self.visited.get(k,-1),eligible.index(k)))
            count=max(8,math.ceil(len(focus)*(.25 if slow<2 else 1.)))
            targets=focus+other[:count]
        for k in targets:self.visited[k]=self.round
        result=dict(round=self.round,mode=mode,slow_rounds=slow,eligible_class_ids=eligible,
            target_class_ids=targets,focused_class_ids=focus,
            complete_eligible_class_exploration=set(targets)==allowed,
            cumulative_explored_classes=len(set(self.visited)&allowed),eligible_classes=len(eligible),
            full_STAY_migration_option_pricing_closure=False,heuristic_class_ranking_only=True)
        self.round+=1
        return result

    def observe(self,state,master,point,phi,raw,rows,rec,folder,native):
        phi=Fraction(phi);s=master.original;n=s.matrix.shape[1];atlas=state['atlas'];axes=state['axes']
        weighted={}
        for j in np.flatnonzero(point[n:]):
            row=master.artificial_rows[int(j)]
            weighted[row]=weighted.get(row,Fraction(0))+master.weights[int(j)]*Fraction(float(point[n+j]))
        voltage=[]
        for row,value in weighted.items():
            family=str(atlas['rf_names'][atlas['rf'][row]]) if row<len(atlas['rf']) else 'LOCAL'
            if value<=0 or family not in ('voltage_lower','voltage_upper'):continue
            ids=atlas[family+'_rows'];index=int(np.searchsorted(ids,row));slot,node=divmod(index,len(atlas['node_names']))
            slot+=24;name=str(atlas['node_names'][node]);match=re.search(r'(IDC\d+)',name,re.I)
            site=match.group(1).upper() if match else None
            a,b=s.matrix.indptr[row:row+2];activity=float(s.matrix.data[a:b]@point[s.matrix.indices[a:b]])
            rhs=float(s.rhs[row]);deficit=max(0.,rhs-activity) if s.senses[row]=='>' else max(0.,activity-rhs)
            load={}
            for j,key in enumerate(axes):
                if key[0] in ('GPU','RUNTIME') and key[1]==site and key[2]==slot:
                    column=int(atlas['resource_variables'][j])
                    if column>=0:load[key[0]]=float(point[column])
            item=dict(row=int(row),family=family,node=name,phase=name.rsplit('.',1)[-1],slot=slot,
                weighted_artificial=str(value),original_constraint_shortfall=deficit,shortfall_units='ORIGINAL_LINEAR_MODEL_ROW_UNITS_NOT_AC_PU',
                current_AIDC_resource_values=load)
            if self.plan and site:
                # A-stage slot24 maps to M-stage slot0 in the preserved model.
                t=slot-24
                item.update(M1_slot=t,MESS_P_kW=self.plan['site_P_kW'].get(site,[0.]*96)[t],MESS_Q_kvar=self.plan['site_Q_kvar'].get(site,[0.]*96)[t],M1_plan_sha=self.plan['plan_sha'])
            voltage.append(item)
        pi=np.zeros(s.matrix.shape[0]);pi[list(rows)]=raw['Pi'];coupling=np.asarray([pi[r] for r in axes.values()])
        change=None if self.dual is None else float(np.linalg.norm(coupling-self.dual)/max(np.linalg.norm(self.dual),1e-30))
        self.dual=coupling.copy()
        gain=None if self.previous is None or not self.previous else float((self.previous-phi)/self.previous)
        feedback=dict(UTC=now(),exact_full_Phi=str(phi),full_Phi=float(phi),previous_full_Phi=None if self.previous is None else str(self.previous),
            relative_decrease=gain,previous_selected_columns=self.pending,voltage_rows=voltage,
            LP_Native_seconds=rec['native_seconds'],dual_relative_L2_change=change,dual_stabilization_applied=False,
            comparison='SAME_FULL_ORIGINAL_ROW_AUTHORITY_AND_FROZEN_WEIGHTS_AFTER_ROW_CLOSURE',
            fixed_M1_feasibility='NOT_CERTIFIED' if phi>EPS else 'PHASE_I_ZERO_REQUIRES_ORIGINAL_CERTIFICATE')
        previous_voltage=set(self.feedback[-1].get('voltage_row_ids',[])) if self.feedback else set()
        feedback['voltage_row_ids']=[r['row'] for r in voltage]
        feedback['new_voltage_rows_since_previous']=sorted(set(feedback['voltage_row_ids'])-previous_voltage) if self.feedback else []
        self.feedback.append(feedback);self.previous=phi;self.pending=None
        atomic(Path(folder)/'R025B_ACTUAL_FULL_PHI_FEEDBACK.json',feedback)
        atomic(self.output/'R025B_ADAPTIVE_PROGRESS.json',dict(UTC=now(),feedback=self.feedback,
            cumulative_priced_classes=len(self.visited),class_exploration_not_option_closure=True))

    def price(self,native,state,master,raw,local,owned,attribution,effect,baseline,folder,targeted):
        started=perf_counter()
        plan=self.plan_classes(attribution);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        atomic(folder/'R025B_CLASS_EXPLORATION.json',plan)
        flexibility=[]
        for key in plan['target_class_ids']:
            uid=state['data'][7]['classes'][key][0];job=state['data'][1][uid];domain=state['domains'][uid]
            stays=list(domain.stays)
            flexibility.append(dict(class_id=key,cardinality=len(state['data'][7]['classes'][key]),GPU=job.gpu,
                service_slots=job.service_slots,reference_start=job.reference_start,reference_site=job.reference_site,
                deadline=getattr(job,'deadline',getattr(job,'deadline_slot',None)),
                earliest_STAY_start=min((x[0] for x in stays),default=None),latest_STAY_start=max((x[0] for x in stays),default=None),
                STAY_sites=sorted({x[1] for x in stays}),STAY_options=len(stays),migration_blocks=len(domain.blocks),
                no_deadline_or_GPU_domain_relaxed=True))
        key_axes=tuple(state['axes'])
        sensitive=sorted(range(len(effect)),key=lambda j:-abs(float(effect[j])))[:64]
        voltage_sensitivity=[]
        if self.feedback:
            A=master.original.matrix;js=[j for j,k in enumerate(key_axes) if k[0] in ('GPU','RUNTIME') and int(state['atlas']['resource_variables'][j])>=0]
            cols=[int(state['atlas']['resource_variables'][j]) for j in js]
            binding=np.asarray(A[[state['axes'][key_axes[j]] for j in js],cols]).ravel() if js else np.zeros(0)
            for item in self.feedback[-1]['voltage_rows']:
                coefficients=A[item['row'],cols].toarray().ravel() if js else np.zeros(0)
                values=[(j,-float(c/b)) for j,c,b in zip(js,coefficients,binding) if c and b]
                values.sort(key=lambda x:-abs(x[1]))
                voltage_sensitivity.append(dict(row=item['row'],slot=item['slot'],node=item['node'],
                    original_binding_elimination=[dict(axis=key_axes[j],derivative=v) for j,v in values[:64]],
                    per_voltage_row_model_derivative=True,other_controls_held_fixed=True,AC_feasibility_certificate=False))
        atomic(folder/'R025B_VIOLATION_GUIDANCE.json',dict(UTC=now(),workload_flexibility=flexibility,
            original_binding_ranking_sensitivities=[dict(axis=key_axes[j],sensitivity=float(effect[j])) for j in sensitive],
            voltage_row_sensitivities=voltage_sensitivity,
            sensitivity_is_ranking_only=True,other_global_controls_held_fixed=True,full_original_replay_still_required=True))
        if targeted not in self.compiled:self.compiled[targeted]=collect_targeted(targeted)
        function=self.compiled[targeted]
        def execute(targets,where):
            return function(native,None,1,state['compact'],master,raw,state['data'],state['domains'],state['ledger'],state['axes'],local,owned,targets,effect,baseline,where)
        priced,candidates=execute(plan['target_class_ids'],folder/'EXPLORED')
        queried=list(plan['target_class_ids'])
        if not candidates and not plan['complete_eligible_class_exploration']:
            remaining=[k for k in plan['eligible_class_ids'] if k not in set(queried)]
            extra,more=execute(remaining,folder/'REMAINING');candidates+=more;queried+=remaining
            for k in remaining:self.visited[k]=self.round-1
            priced=dict(priced,receipts=priced['receipts']+extra['receipts'])
        selected,selection=choose(candidates,tuple(state['axes']))
        complete=set(queried)==set(plan['eligible_class_ids'])
        result=dict(PASS=True,classes_priced=len(queried),class_ids=queried,
            selected_batch_size=len(selected),selected_STAY=sum(c['kind']=='STAY' for c in selected),selected_migration=sum(c['kind']=='MIGRATION' for c in selected),
            negative_STAY=sum(c['kind']=='STAY' for c in candidates),negative_migration=sum(c['kind']=='MIGRATION' for c in candidates),
            selected_candidates=[dict(c,option=asdict(c['option']) if not isinstance(c['option'],dict) else c['option'],price=str(c['price'])) for c in selected],
            receipts=priced['receipts'],targeted_migration_search_completed=True,full_eligible_class_exploration=complete,
            full_native_fractional_LP_pricing_closure=False,fixed_M1_infeasibility_certified=False,permanent_deletions=0,
            selection_heuristic=selection)
        self.pending=dict(columns=len(selected),classes=len({c['class_id'] for c in selected}),
            reduced_costs=[str(c['price']) for c in selected],class_ids=[c['class_id'] for c in selected],exploration_mode=plan['mode'])
        atomic(folder/'PRICING_RESULT.json',serial(result))
        atomic(folder/'R025B_ADAPTIVE_PRICING_TIMING.json',dict(UTC=now(),wall_seconds=perf_counter()-started,
            classes_priced=len(queried),candidate_count=len(candidates),selected=len(selected),
            includes_original_native_queries_and_independent_recovery=True,Native_time_charged_to_original_shared_ledger=True))
        # Proof failure is not guessed to be mathematical infeasibility.
        if not selected:
            atomic(folder/'R025B_FIXED_M1_NOT_CERTIFIED.json',dict(UTC=now(),status='NOT_CERTIFIED',
                full_eligible_class_exploration=complete,full_native_option_closure=False,positive_PhaseI_LB_certified=False))
        return result,selected


def compile_adaptive(function,namespace,controller):
    source=textwrap.dedent(inspect.getsource(function));anchor='    # Original P1:'
    p1=source[source.index(anchor):]
    old="        if zero['PASS']:\n"
    if source.count(old)!=1:raise ValueError('R025B_PHASE_ZERO_SOURCE_DRIFT')
    source=source.replace(old,"        _R025Badaptive.observe(state,allmaster,fullpoint,Phi,raw,rows,rec,f,native)\n"+old)
    start=source.index('        priced,selected=targeted(');end=source.index('        # Preserve the current complete Phase-I witness',start)
    source=source[:start]+"        priced,selected=_R025Badaptive.price(native,state,allmaster,fmraw,local,owned,attribution,effect,baseline,f/'PRICE',targeted)\n        if not selected:raise RuntimeError('R025B_FIXED_M1_FEASIBILITY_NOT_CERTIFIED_NO_RECOVERED_NEGATIVE_COLUMN')\n"+source[end:]
    old="        if stagnation>=3:raise RuntimeError('THREE_CERTIFIED_ROW_CLOSED_NONMATERIAL_ROUNDS')"
    if source.count(old)!=1:raise ValueError('R025B_STAGNATION_SOURCE_DRIFT')
    source=source.replace(old,"        if stagnation>=3:atomic(f/'R025B_STAGNATION_WIDENING_PENDING.json',dict(consecutive_slow_rounds=stagnation,action='REOPTIMIZE_NEW_ADAPTIVE_BATCH_BEFORE_JUDGING_GAIN',shared_Native_budget_unchanged=True))")
    if source[source.index(anchor):]!=p1:raise ValueError('R025B_P1_MODIFICATION_FORBIDDEN')
    # Native400 applies to every Phase-I master and local-pricing call, not
    # merely to the LP master. Preserve the latest fully built physical state.
    source=source.replace('    while certified_zero_point is None:\n',
        '    while certified_zero_point is None:\n        if _R025Bguard is not None:_R025Bguard.checkpoint(state,day)\n')
    source=source.replace(anchor,
        '    if _R025Bguard is not None:_R025Bguard.start_p1(state,day)\n'+anchor)
    from .bounded_a_stage import current
    namespace['_R025Bguard']=current()
    namespace['_R025Badaptive']=controller
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']
