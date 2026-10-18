"""Observe actual column activations; relax only certified offending voltage rows."""
from collections import deque,defaultdict
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import inspect,textwrap,linecache
import numpy as np
from v44.common import atomic,record,now,digest,verify,read

LOWER_DELTA=F(-379,40000)
UPPER_DELTA=F(421,40000)


class ConditionalVoltage:
    def __init__(self,request):
        self.request=request;self.output=Path(request['output']);self.nodes=None
        self.mask={};self.events=[];self.history=[];self.gains=deque(maxlen=2)
        self.previous=None;self.last_activation=None;self.generation=0
        self.full_sweeps=[];self.attribution=None;self.proposal=None
        self.frozen_weights=None
    def bind(self,state):
        names=tuple(map(str,state['atlas']['node_names']))
        if self.nodes is not None and names!=self.nodes:raise ValueError('R029_VOLTAGE_NODE_AXIS_DRIFT')
        self.nodes=names
    def bounds(self,slot,count):
        lower=np.full(count,.9025);upper=np.full(count,1.1025)
        if self.nodes is None:
            if self.mask:raise ValueError('R029_BOUND_NODE_AXIS')
            return lower,upper
        if count!=len(self.nodes):raise ValueError('R029_BOUND_NODE_AXIS')
        for n,name in enumerate(self.nodes):
            if ('voltage_lower',int(slot),name) in self.mask:lower[n]=.893025
            if ('voltage_upper',int(slot),name) in self.mask:upper[n]=1.113025
        return lower,upper
    def report(self):
        return dict(policy='CONDITIONAL_SELECTIVE_A2_VOLTAGE',model_generation=self.generation,
            approved_rows=[dict(family=k[0],slot=k[1],issue_slot=k[1]+24,node=k[2],phase=k[2].rsplit('.',1)[-1],**v)
                for k,v in sorted(self.mask.items())],
            full_eligible_class_pricing_sweeps=self.full_sweeps,relaxation_events=self.events,
            column_activation_history=self.history,all_other_voltage_rows_strict=True)
    def wrap_analyze(self,function):
        def analyze(*a,**k):
            answer=function(*a,**k);self.attribution=answer[0];return answer
        return analyze
    def wrap_targeted(self,function):
        def targeted(*args,**kwargs):
            values=list(args)
            eligible=[r['class_id'] for r in self.attribution['classes_ranked'] if r['inactive_candidates_available']]
            full=not self.full_sweeps
            if full:values[12]=eligible
            result,selected=function(*values,**kwargs)
            if set(result['class_ids'])==set(eligible) and result['classes_priced']==len(eligible) and eligible:
                proof=dict(UTC=now(),PASS=True,eligible_classes=len(eligible),priced_classes=result['classes_priced'],
                    eligible_class_ids=eligible,pricing_result=record(Path(values[-1])/'PRICING_RESULT.json'),
                    full_fractional_option_closure_claimed=False)
                self.full_sweeps.append(proof)
                atomic(Path(values[-1])/'R029_FULL_ELIGIBLE_CLASS_PRICING.json',proof)
            return result,selected
        return targeted
    def observe(self,state,master,point,phi,activation,folder):
        self.bind(state);phi=F(phi);n=state['compact'].matrix.shape[1]
        parts=defaultdict(F);positive=F(0);voltage_positive=F(0);voltage_signed=F(0);targets=[]
        A=state['compact'].matrix;atlas=state['atlas'];activity=A@point[:n]
        for j in np.flatnonzero(point[n:]):
            row=master.artificial_rows[int(j)];value=master.weights[int(j)]*F(float(point[n+j]));parts[row]+=value
        for row,value in parts.items():
            family=str(atlas['rf_names'][atlas['rf'][row]]) if row<len(atlas['rf']) else 'LOCAL'
            is_voltage=family in ('voltage_lower','voltage_upper')
            if value>0:
                positive+=value
                if is_voltage:voltage_positive+=value
            if not is_voltage:continue
            voltage_signed+=value
            ids=atlas[family+'_rows'];position=int(np.searchsorted(ids,row))
            if position>=len(ids) or ids[position]!=row:raise ValueError('R029_VOLTAGE_ROW_AXIS')
            slot,node=divmod(position,len(self.nodes));key=(family,slot,self.nodes[node])
            deficit=float(state['compact'].rhs[row]-activity[row]) if family=='voltage_lower' else float(activity[row]-state['compact'].rhs[row])
            if value>0 and deficit>1e-6 and key not in self.mask:
                targets.append(dict(key=key,row=int(row),original_linear_shortfall_pu_squared=deficit,weighted_artificial=str(value)))
        kind='BASELINE' if self.last_activation is None else 'ROW_CLOSURE_RECHECK'
        gain=None
        if self.last_activation is not None and activation>self.last_activation:
            if activation!=self.last_activation+1:raise ValueError('R029_SKIPPED_COLUMN_ACTIVATION_OBSERVATION')
            if self.previous is not None and self.previous>0:
                gain=(self.previous-phi)/self.previous
                self.gains.append(dict(from_activation=self.last_activation,to_activation=activation,
                    previous_full_Phi=str(self.previous),full_Phi=str(phi),relative_decrease=str(gain),
                    model_generation=self.generation,actual_column_activation=True))
            kind='COLUMN_ACTIVATION_RESULT'
        self.previous=phi;self.last_activation=activation
        signed_share=voltage_signed/phi if phi>0 else F(0)
        positive_share=voltage_positive/positive if positive>0 else F(0)
        slow=len(self.gains)==2 and all(F(0)<=F(r['relative_decrease'])<F(1,20) for r in self.gains)
        eligible=bool(self.full_sweeps and slow and signed_share>=F(19,20) and positive_share>=F(19,20) and targets)
        observation=dict(UTC=now(),kind=kind,column_activation=activation,model_generation=self.generation,
            full_Phi=str(phi),relative_decrease=None if gain is None else str(gain),
            voltage_weighted_artificial=str(voltage_signed),voltage_fraction_of_full_Phi=str(signed_share),
            positive_voltage_fraction=str(positive_share),recent_two_actual_column_activations=list(self.gains),
            full_eligible_pricing_completed=bool(self.full_sweeps),eligible_to_relax=eligible,
            verified_unrelaxed_voltage_violations=targets)
        full_phi=Path(folder)/'R029_FULL_PHI.json'
        if not full_phi.exists():raise ValueError('R029_FULL_PHI_OBSERVATION_CERTIFICATE_REQUIRED')
        certificate=read(full_phi)
        if not certificate['PASS'] or F(certificate['exact_full_Phi'])!=phi:raise ValueError('R029_FULL_PHI_OBSERVATION_MISMATCH')
        observation['full_Phi_certificate']=record(full_phi)
        self.history.append(observation);atomic(Path(folder)/'R029_CONDITIONAL_VOLTAGE_OBSERVATION.json',observation)
        atomic(self.output/'R029_CONDITIONAL_VOLTAGE_PROGRESS.json',self.report())
        self.proposal=observation if eligible else None
        return eligible
    def apply(self,state,rowgen,native,elastic_master,make_point,folder):
        if not self.proposal or not self.proposal['eligible_to_relax']:raise PermissionError('R029_RELAXATION_WITHOUT_TRIGGER')
        before=state;new=dict(state);changes=[]
        for item in self.proposal['verified_unrelaxed_voltage_violations']:
            key=tuple(item['key']);delta=LOWER_DELTA if key[0]=='voltage_lower' else UPPER_DELTA
            if key in self.mask:raise PermissionError('R029_REPEATED_VOLTAGE_RELAXATION')
            self.mask[key]=dict(lower_pu=.945 if key[0]=='voltage_lower' else .95,
                upper_pu=1.055 if key[0]=='voltage_upper' else 1.05,maximum_relaxation_pu=.005,
                exact_squared_rhs_delta=str(delta),trigger_generation=self.generation)
            changes.append(dict(row=item['row'],delta=delta,key=key))
        fingerprints={};proofs={}
        for label in ('compact','reference'):
            old=state[label];rhs=old.rhs.copy()
            for item in changes:rhs[item['row']]=float(F(float(rhs[item['row']]))+item['delta'])
            updated=replace(old,rhs=rhs).require();new[label]=updated
            if updated.matrix is not old.matrix:raise ValueError('R029_MATRIX_OBJECT_CHANGED_DURING_RHS_RELAXATION')
            changed=set(map(int,np.flatnonzero(old.rhs!=updated.rhs)))
            if changed!={item['row'] for item in changes}:raise ValueError('R029_NONSELECTED_RHS_CHANGE')
            fingerprints[label]=dict(before=old.fingerprint(),after=updated.fingerprint())
            proofs[label]=dict(PASS=True,identical_matrix_boxes_types_senses_objectives=True,
                changed_rows=sorted(changed),only_verified_voltage_rows_changed=True)
        if self.frozen_weights is not None:
            # Original frozen-weight checks remain active. Authorize precisely
            # these certified RHS changes; never regenerate weights or signs.
            for item in changes:
                row=item['row']
                if self.frozen_weights.rhs[row]!=before['reference'].rhs[row]:raise ValueError('R029_FROZEN_PRIOR_RHS_DRIFT')
            for item in changes:self.frozen_weights.rhs[item['row']]=new['reference'].rhs[item['row']]
        from .row_generation import ActiveRows,exact_phi
        from v42_a_stage_phase1.core import primal_replay
        full=elastic_master(new['compact'],new['grows'])
        point=make_point(full,rowgen.seed[:state['compact'].matrix.shape[1]])
        replay=primal_replay(full.snapshot,point)
        if not replay['PASS']:raise ValueError('R029_RELAXED_PRIOR_FULL_ELASTIC_REPLAY')
        next_rows=ActiveRows(new,rowgen.included,full);next_rows.seed=point
        native.seed=None
        self.generation+=1;self.previous=None;self.last_activation=None;self.gains.clear()
        event=dict(UTC=now(),PASS=True,trigger=self.proposal,model_fingerprints=fingerprints,
            matrix_difference_proofs=proofs,changes=[dict(r,delta=str(r['delta'])) for r in changes],
            prior_elastic_replay=replay,new_prior_full_Phi=str(exact_phi(full,point)),
            prior_dual_discarded=True,P1_not_started=True,original_non_voltage_constraints_unchanged=True,
            original_frozen_artificial_weights_and_signs_unchanged=True,
            squared_lower_exact='2209/2500',squared_upper_exact='2809/2500',new_model_generation=self.generation)
        path=Path(folder)/'R029_SELECTIVE_VOLTAGE_RELAXATION.json';atomic(path,event)
        self.events.append(dict(receipt=record(path),**event));self.proposal=None
        atomic(self.output/'R029_CONDITIONAL_VOLTAGE_PROGRESS.json',self.report())
        from .model_difference import verify_state_policy
        verify_state_policy(new,self.output,controller=self)
        return new,next_rows


def validate_execution(execution):
    if not execution.get('approved_rows') or not execution.get('relaxation_events'):raise ValueError('R029_NO_APPROVED_RELAXATION_EVENT')
    sweeps=execution.get('full_eligible_class_pricing_sweeps',[])
    if not sweeps:raise ValueError('R029_FULL_ELIGIBLE_PRICING_REQUIRED')
    for sweep in sweeps:
        verify([sweep['pricing_result']]);price=read(sweep['pricing_result']['path'])
        if (not sweep['PASS'] or not price['PASS'] or price['classes_priced']!=sweep['eligible_classes']
            or set(price['class_ids'])!=set(sweep['eligible_class_ids'])):raise ValueError('R029_FULL_ELIGIBLE_PRICING_COVERAGE')
    approved=set()
    for event in execution['relaxation_events']:
        verify([event['receipt']]);e=read(event['receipt']['path']);trigger=e['trigger']
        gains=trigger['recent_two_actual_column_activations']
        if (len(gains)!=2 or not all(g['actual_column_activation'] and F(0)<=F(g['relative_decrease'])<F(1,20) for g in gains)
            or not trigger['full_eligible_pricing_completed'] or F(trigger['voltage_fraction_of_full_Phi'])<F(19,20)
            or F(trigger['positive_voltage_fraction'])<F(19,20)):raise ValueError('R029_CONDITIONAL_TRIGGER_NOT_PROVEN')
        for gain in gains:
            previous=F(gain['previous_full_Phi']);current=F(gain['full_Phi'])
            if (previous<=0 or (previous-current)/previous!=F(gain['relative_decrease'])
                or gain['to_activation']!=gain['from_activation']+1
                or gain['model_generation']!=trigger['model_generation']):raise ValueError('R029_ACTIVATION_GAIN_ARITHMETIC')
        if gains[0]['to_activation']!=gains[1]['from_activation']:raise ValueError('R029_TWO_CONSECUTIVE_ACTIVATIONS_REQUIRED')
        verify([trigger['full_Phi_certificate']]);phi=read(trigger['full_Phi_certificate']['path'])
        if not phi['PASS'] or F(phi['exact_full_Phi'])!=F(trigger['full_Phi']):raise ValueError('R029_FULL_PHI_TRIGGER_BINDING')
        proposed={tuple(t['key']) for t in trigger['verified_unrelaxed_voltage_violations']}
        for change in e['changes']:
            key=tuple(change['key']);expected=LOWER_DELTA if key[0]=='voltage_lower' else UPPER_DELTA
            if key not in proposed or F(change['delta'])!=expected or key in approved:raise ValueError('R029_NONVERIFIED_OR_REPEATED_ROW_RELAXATION')
            approved.add(key)
        if not all(p['PASS'] and p['only_verified_voltage_rows_changed'] for p in e['matrix_difference_proofs'].values()):
            raise ValueError('R029_ORIGINAL_MODEL_DIFFERENCE_PROOF_REQUIRED')
    reported={(x['family'],x['slot'],x['node']) for x in execution['approved_rows']}
    if reported!=approved:raise ValueError('R029_APPROVED_ROW_MASK_DRIFT')
    return True


def compile_conditional(function,namespace,controller):
    source=textwrap.dedent(inspect.getsource(function));anchor='    # Original P1:';p1=source[source.index(anchor):]
    old="        if zero['PASS']:\n"
    assert source.count(old)==1
    insert=("        if _r029_conditional.observe(state,allmaster,fullpoint,Phi,activation_round,f):\n"
            "            state,rowgen=_r029_conditional.apply(state,rowgen,native,elastic_master,artificial_point,f)\n"
            "            included=set(rowgen.included);bestPhi=None;stagnation=0\n"
            "            continue\n")
    source=source.replace(old,insert+old)
    assert source[source.index(anchor):]==p1,'R029_P1_STRUCTURE_CHANGED'
    namespace['_r029_conditional']=controller
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']
