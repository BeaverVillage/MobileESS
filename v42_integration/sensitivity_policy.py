"""Bounded offline P1 action comparison and immutable runtime lookups.

The signed original 16-face grid equations are evaluated here, never in the
Actual event path. Prototype requests are anonymous model conditions; they are
not future jobs. CC4 Q90 is an offline stress scenario, not Actual occupation.
"""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from .policy import (FrozenControlPolicy, ReservationLedger, migration_guard,
                     digest, BINDING_FIELDS)


POLICY_ID = 'V42_GRID_SENSITIVITY_AWARE_CONDITIONAL_POLICY_V1'
SLOTS = 96
DT = 900.
REQUIRED_BINDINGS = tuple(BINDING_FIELDS) + ('cc4_sha','runtime_sha','response_sha','initial_state_sha')


def _array(value, shape=None):
    a=np.asarray(value,dtype=float)
    if (shape is not None and a.shape!=shape) or not np.isfinite(a).all():
        raise ValueError('ORIGINAL_GRID_FINITE_EXPLICIT_AXIS_REQUIRED')
    return a


def _receipt(value):
    return value.to_dict() if hasattr(value,'to_dict') else dict(value)


def _json(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if is_dataclass(value):return _json(asdict(value))
    if isinstance(value,dict):return {str(k):_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_json(v) for v in value]
    return value


def _violations_summary(rows):
    grouped={}
    for row in rows:
        item=grouped.setdefault(row['reason'],dict(slots=set(),branches=set(),occurrences=0))
        item['occurrences']+=1
        if 'slot' in row:item['slots'].add(int(row['slot']))
        if 'branch' in row:item['branches'].add(row['branch'])
    return [dict(reason=reason,slot_count=len(item['slots']),slot_examples=sorted(item['slots'])[:8],
        branch_count=len(item['branches']),branch_examples=sorted(item['branches'])[:8],
        branches_sha=digest(sorted(item['branches'])),occurrences=item['occurrences'])
        for reason,item in sorted(grouped.items())]


class OriginalGridPacket:
    """Cached source equations, controls and exact units for offline evaluation."""
    def __init__(self, coefficients, power, swing_kw, capacities, aidc_plan,
                 final_mess, grid_authority, bindings, *, begin_seconds=0.,
                 known_gpu=None, power_factor=.95, mess_validation=None,rack_compatibility=None):
        if len(coefficients)!=SLOTS or begin_seconds%DT:
            raise ValueError('ORIGINAL_GRID_FULL96_AXIS_REQUIRED')
        if any(not bindings.get(k) for k in REQUIRED_BINDINGS):
            raise ValueError('COMPLETE_SENSITIVITY_POLICY_ANCHORS_REQUIRED')
        self.bindings=dict(bindings);self.begin_seconds=float(begin_seconds)
        self.sites=tuple(sorted(capacities));self.capacities=dict(capacities)
        self.rack_compatibility={s:tuple((rack_compatibility or {}).get(s,(capacities[s],))) for s in self.sites}
        if (rack_compatibility is not None and set(rack_compatibility)!=set(self.sites)) or any(
                not limits or any(not math.isfinite(float(v)) or v<=0 for v in limits)
                for limits in self.rack_compatibility.values()):
            raise ValueError('EXACT_SOURCE_SITE_RACK_COMPATIBILITY_REQUIRED')
        self.swing_kw=float(swing_kw);self.pf=float(power_factor)
        if not 0<self.pf<=1 or self.swing_kw<=0:
            raise ValueError('FROZEN_ORIGINAL_POWER_CONTRACT_REQUIRED')
        self.q_per_p=math.tan(math.acos(self.pf))
        self.coefficients=tuple(deepcopy(c) for c in coefficients)
        self.aidc_plan=deepcopy(aidc_plan)
        self.control_names=tuple(coefficients[0].control_names)
        self.branch_names=tuple(coefficients[0].branch_names)
        if any(tuple(c.control_names)!=self.control_names or tuple(c.branch_names)!=self.branch_names
               or c.slot!=t for t,c in enumerate(coefficients)):
            raise ValueError('ORIGINAL_GRID_CONTROL_BRANCH_SLOT_AXIS_DRIFT')
        if any(len(c.coefficient_sha256)!=64 for c in coefficients):
            raise ValueError('ORIGINAL_SIGNED_RESPONSE_SOURCE_SHA_REQUIRED')
        self.response_sources=sorted({c.coefficient_sha256 for c in coefficients})
        if bindings['response_sha'] not in self.response_sources and bindings['response_sha']!=digest(self.response_sources):
            raise ValueError('ELECTRICAL_RESPONSE_ANCHOR_DRIFT')
        if (aidc_plan.get('aidc_anchor')!=bindings['aidc_anchor']
                or final_mess.get('plan_sha')!=bindings['mess_anchor']
                or digest({k:v for k,v in final_mess.items() if k!='plan_sha'})!=final_mess['plan_sha']):
            raise ValueError('FINAL_AIDC_MESS_ANCHOR_DRIFT')
        if (mess_validation is None or mess_validation.get('plan_sha')!=final_mess['plan_sha']
                or mess_validation.get('frozen_execution_validated') is not True):
            raise ValueError('FINAL_MESS_PHYSICAL_VALIDATION_REQUIRED')
        self.controls=np.zeros((SLOTS,len(self.control_names)))
        self.p_slope=np.zeros((SLOTS,len(self.sites)))
        for t,c in enumerate(coefficients):
            for j,site in enumerate(self.sites):
                affine=power[site,t]
                self.p_slope[t,j]=float(affine.slope)*self.swing_kw
                p=float(aidc_plan['AIDC_P_by_site'][site][t])
                q=float(aidc_plan['AIDC_Q_by_site'][site][t])
                if abs(q-p*self.q_per_p)>1e-7:
                    raise ValueError('ORIGINAL_COUPLED_AIDC_PQ_CONTRACT_DRIFT')
                self.controls[t,self.control_names.index('aidc_load_kw['+site+']')]=p
            for k,name in enumerate(self.control_names):
                site=name.split('[',1)[1][:-1]
                if name.startswith('aidc_load_kw['):continue
                if name.startswith('mess_p_kw['):field='P_by_site'
                elif name.startswith(('mess_q_kvar[','mess_q_kw[')):field='Q_by_site'
                else:raise ValueError('UNSUPPORTED_ORIGINAL_GRID_CONTROL:'+name)
                self.controls[t,k]=float(final_mess[field][site][t])
        self.line_indices=np.array([k for k,n in enumerate(self.branch_names)
            if not n.lower().startswith('transformer.')],dtype=int)
        self.transformer_indices=np.array([k for k,n in enumerate(self.branch_names)
            if n.lower().startswith('transformer.')],dtype=int)
        if not len(self.line_indices):raise ValueError('ORIGINAL_LINE_OBJECTIVE_AXIS_REQUIRED')
        self.voltage_lower=float(grid_authority.voltage_lower_squared)
        self.voltage_upper=float(grid_authority.voltage_upper_squared)
        if not 0<self.voltage_lower<self.voltage_upper:
            raise ValueError('ORIGINAL_PLANNING_VOLTAGE_SQUARED_BAND_REQUIRED')
        self.cos=np.cos(2*np.pi*np.arange(16)/16)
        self.sin=np.sin(2*np.pi*np.arange(16)/16)
        self.ap=[];self.correction=[];self.bias=[]
        for c in self.coefficients:
            from v42_thermal.planning import require_coefficient
            require_coefficient(c,grid_authority)
            k,b=len(self.control_names),len(self.branch_names)
            n=len(c.voltage_constant)
            for value,shape in ((c.voltage_matrix,(k,n)),(c.current_matrix,(k,b)),
                    (c.flow_p_matrix,(b,k)),(c.flow_q_matrix,(b,k)),(c.anchor,(k,)),
                    (c.current_constant,(b,)),(c.flow_p_constant,(b,)),(c.flow_q_constant,(b,))):
                _array(value,shape)
            if len(c.transformer_ratings)!=b:raise ValueError('ORIGINAL_TRANSFORMER_RATING_AXIS_REQUIRED')
            ap=_array(c.branch_limits)*math.cos(math.pi/16)
            if np.any(ap<=0):raise ValueError('ORIGINAL_BRANCH_THERMAL_DENOMINATOR_REQUIRED')
            pa=_array(c.flow_p_constant)+_array(c.flow_p_matrix)@_array(c.anchor)
            qa=_array(c.flow_q_constant)+_array(c.flow_q_matrix)@_array(c.anchor)
            raw=(pa[:,None]*self.cos+qa[:,None]*self.sin)/ap[:,None]
            active=np.argmax(raw,axis=1)
            grad=(self.cos[active,None]*c.flow_p_matrix+self.sin[active,None]*c.flow_q_matrix)/ap[:,None]
            correction=_array(c.current_matrix).T-grad
            bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
            self.ap.append(ap);self.correction.append(correction);self.bias.append(bias)
        self.known_gpu=None if known_gpu is None else _array(known_gpu,(SLOTS,len(self.sites)))
        if self.known_gpu is not None and np.any(self.known_gpu<0):raise ValueError('NONNEGATIVE_KNOWN_GPU_REQUIRED')
        self.cache={};self.scenario_cache={};self.evaluation_calls=0;self.cache_hits=0
        self.authority=dict(source_response_SHAs=self.response_sources,
            controls='ORIGINAL_kW_kvar_SIGNS',voltage='SQUARED_PU',
            line='ORIGINAL_16FACE_NORMALIZED_CURRENT_WITH_SIGNED_ANCHOR_CORRECTION',
            transformer='ALL_ORIGINAL_CURRENT_ROWS_AND_16FACE_kVA',
            AIDC_Q='ORIGINAL_PF_COUPLED_RESPONSE_NOT_DOUBLE_COUNTED',
            P_swing_kw_per_GPU=_json(self.p_slope),Q_swing_kvar_per_GPU=_json(self.p_slope*self.q_per_p),
            frozen_MESS_plan_sha=final_mess['plan_sha'],frozen_MESS_physical_validation=deepcopy(mess_validation),
            original_thermal_source=[getattr(c,'transformer_current_authority_sha256',None) for c in coefficients])
        self.authority['rack_compatibility']=_json(self.rack_compatibility)
        self.authority['rack_source']='EXPLICIT_ORIGINAL_SOURCE_MAP' if rack_compatibility is not None else 'DECLARED_SITE_CAPACITY_FIXTURE_MODEL'

    def controls_delta(self,gpu):
        gpu=_array(gpu,(SLOTS,len(self.sites)))
        delta=np.zeros_like(self.controls)
        for j,s in enumerate(self.sites):
            delta[:,self.control_names.index('aidc_load_kw['+s+']')]=gpu[:,j]*self.p_slope[:,j]
        return delta

    def _at_slot(self,t,gpu_delta):
        t=int(t)
        c=self.coefficients[t];control=self.controls[t].copy()
        for j,s in enumerate(self.sites):
            control[self.control_names.index('aidc_load_kw['+s+']')]+=gpu_delta[j]*self.p_slope[t,j]
        voltage=c.voltage_constant+c.voltage_matrix.T@control
        p=c.flow_p_constant+c.flow_p_matrix@control
        q=c.flow_q_constant+c.flow_q_matrix@control
        line=(p[:,None]*self.cos+q[:,None]*self.sin)/self.ap[t][:,None]
        line+=((self.correction[t]@(control-c.anchor))+self.bias[t])[:,None]
        line_peak=max(0.,float(np.max(line[self.line_indices])))
        violations=[]
        if np.any(voltage<self.voltage_lower-1e-9) or np.any(voltage>self.voltage_upper+1e-9):
            violations.append(dict(slot=t,reason='ORIGINAL_PLANNING_VOLTAGE'))
        if line_peak>1+1e-9:violations.append(dict(slot=t,reason='ORIGINAL_LINE_CURRENT'))
        current=c.current_constant+c.current_matrix.T@control
        if len(self.transformer_indices) and np.any(current[self.transformer_indices]>1+1e-9):
            violations.append(dict(slot=t,reason='ORIGINAL_ALL_TRANSFORMER_CURRENT'))
        for j,rating in enumerate(c.transformer_ratings):
            if rating is not None and np.max(p[j]*self.cos+q[j]*self.sin)>float(rating)*math.cos(math.pi/16)+1e-9:
                violations.append(dict(slot=t,reason='ORIGINAL_TRANSFORMER_KVA',branch=self.branch_names[j]))
        return line_peak,violations

    def evaluate(self, gpu_delta, *, remaining_slot=0, scenario_gpu=None):
        """Exact original linear rows; max includes every remaining line/time."""
        a=_array(gpu_delta,(SLOTS,len(self.sites)))
        if not 0<=remaining_slot<SLOTS:raise ValueError('REMAINING_GRID_HORIZON_REQUIRED')
        stress=np.zeros_like(a) if scenario_gpu is None else _array(scenario_gpu,a.shape)
        stress_key=stress.tobytes();key=(remaining_slot,stress_key,a.tobytes())
        if key in self.cache:
            self.cache_hits+=1;return deepcopy(self.cache[key])
        if stress_key not in self.scenario_cache:
            self.scenario_cache[stress_key]=[self._at_slot(t,stress[t]) for t in range(SLOTS)]
            if len(self.scenario_cache)>4:self.scenario_cache.pop(next(iter(self.scenario_cache)))
        base=self.scenario_cache[stress_key]
        per_slot=[r[0] for r in base];by_slot={t:r[1] for t,r in enumerate(base)}
        touched=np.flatnonzero(np.any(a!=0,axis=1))
        for t in touched:
            if t<remaining_slot:continue
            per_slot[t],by_slot[t]=self._at_slot(t,stress[t]+a[t])
        violations=[r for t in range(remaining_slot,SLOTS) for r in by_slot[t]]
        result=dict(peak_score=max(per_slot[remaining_slot:]),hard_feasible=not violations,violations=violations,
            remaining_slots=SLOTS-remaining_slot,per_slot_peak=per_slot[remaining_slot:],
            affine_approximation_only=True,Fresh_AC_PASS_claimed=False)
        self.evaluation_calls+=1;self.cache[key]=result
        # Bounded cache; serialized templates retain scores, not scenario arrays.
        if len(self.cache)>256:self.cache.pop(next(iter(self.cache)))
        return deepcopy(result)


def build_grid_packet(coefficients,power,swing_kw,capacities,aidc_plan,final_mess,grid_authority,
                      bindings,**kwargs):
    return OriginalGridPacket(coefficients,power,swing_kw,capacities,aidc_plan,
                              final_mess,grid_authority,bindings,**kwargs)


def _profile(sites,site,start,service,gpu):
    out=np.zeros((SLOTS,len(sites)))
    finish=start+service
    for t in range(max(0,int(start//DT)),min(SLOTS,int(math.ceil(finish/DT)))):
        out[t,sites.index(site)]=gpu*max(0.,min(finish,(t+1)*DT)-max(start,t*DT))/DT
    tail=gpu*max(0.,finish-max(start,SLOTS*DT))/3600.
    return out,tail


def _kernel_curve(work,kernel):
    work=_array(work,(24,));k=_array(kernel)
    if k.ndim!=1 or np.any(k<0) or abs(k.sum()-1)>1e-9 or np.any(work<0):
        raise ValueError('FROZEN_CC4_LIFETIME_KERNEL_MASS_REQUIRED')
    out=np.zeros(96+len(k))
    for h,mass in enumerate(work):out[4*h:4*h+len(k)]+=4*mass*k
    return out


def _scenarios(packet,envelope,q50,q90,kernel,authority,burst):
    q50=_array(q50,(24,));q90=_array(q90,(24,))
    if np.any(q90<q50):raise ValueError('SOURCE_CC4_Q50_Q90_ORDER_REQUIRED')
    if (authority.get('model_id')!='LGBM_weighted_c1_s20260924'
            or authority.get('prediction_sha')!=packet.bindings['cc4_sha']
            or authority.get('runtime_sha')!=packet.bindings['runtime_sha']
            or not authority.get('kernel_sha')):
        raise ValueError('EXACT_FROZEN_CC4_V21_RUNTIME_KERNEL_BINDING_REQUIRED')
    nominal=np.zeros((SLOTS,len(packet.sites)))
    for row in envelope:
        t=int((row['slot_start']-packet.begin_seconds)/DT)
        if 0<=t<SLOTS:nominal[t,packet.sites.index(row['site'])]=row['gpu_capacity']
    nominal_carry=float(authority.get('nominal_carryout_GPUh',sum(packet.aidc_plan.get('CC4_carryout',{}).values())))
    if nominal_carry<0 or abs(nominal.sum()/4+nominal_carry-q50.sum())>1e-7:
        raise ValueError('CC4_Q50_OPTIMIZED_NOMINAL_SERVICE_CARRYOUT_MASS_DRIFT')
    curve=_kernel_curve(q90-q50,kernel)
    stress=authority.get('stress_site_GPU')
    if np.any(curve>1e-10) and stress is None:
        return None,dict(status='INSUFFICIENT_SOURCE_SITE_DISTRIBUTION',
            reason='Q90_STRESS_REQUIRES_FROZEN_SITE_TIME_ALLOCATION',
            TRAIN_BURST_STRESS='INSUFFICIENT_SUPPORT',Q90_actual_load_addition=False)
    stress=np.zeros_like(nominal) if stress is None else _array(stress,nominal.shape)
    expected=curve[:96]
    carry=float(curve[96:].sum()/4)
    if authority.get('stress_allocation_source')=='A_STAGE_OPTIMIZED_RESERVE':
        if authority.get('allocation_aidc_anchor')!=packet.bindings['aidc_anchor']:
            raise ValueError('CC4_RESERVE_FINAL_A_STAGE_ALLOCATION_ANCHOR_DRIFT')
        expected=_array(authority['stress_profile_GPU'],(SLOTS,))
        carry=float(authority['stress_carryout_GPUh'])
    if (np.any(stress<0) or carry<0 or
            not np.allclose(stress.sum(axis=1),expected,atol=1e-8,rtol=0)
            or abs(stress.sum()/4+carry-(q90-q50).sum())>1e-7):
        raise ValueError('CC4_Q90_MINUS_Q50_STRESS_SLOT_MASS_DRIFT')
    # The high curve is a separate scenario. Nominal is already in AIDC_P.
    scenarios={'NOMINAL_Q50':np.zeros_like(nominal),'HIGH_DEMAND_Q90':stress}
    burst_status='INSUFFICIENT_SUPPORT'
    if burst is not None and burst.get('status')=='INSUFFICIENT_SUPPORT':
        if 'extra_site_GPU' in burst:raise ValueError('UNSUPPORTED_TRAIN_BURST_CANNOT_INVENT_PROFILE')
        burst=None
    if burst is not None:
        if (burst.get('source_partition')!='TRAIN' or burst.get('submission_version_verified') is not True
                or burst.get('future_May_data_used') is not False or not burst.get('source_sha')
                or not burst.get('observed_before_planning_issue')):
            raise ValueError('TRAIN_BURST_SOURCE_CAUSAL_SUPPORT_REQUIRED')
        a=_array(burst['extra_site_GPU'],nominal.shape)
        if np.any(a<0):raise ValueError('TRAIN_BURST_NONNEGATIVE_LIFETIME_MASS_REQUIRED')
        scenarios['TRAIN_BURST_STRESS']=a;burst_status='SOURCE_VERIFIED_TRAIN_ONLY'
    return (nominal,scenarios),dict(status='SOURCE_BOUND_SCENARIOS_READY',
        Q50_GPUh=float(q50.sum()),Q90_GPUh=float(q90.sum()),nominal_carryout_GPUh=nominal_carry,
        Q90_minus_Q50_GPUh=float((q90-q50).sum()),
        Q90_stress_day_GPUh=float(stress.sum()/4),Q90_stress_tail_GPUh=carry,
        scenario_names=list(scenarios),TRAIN_BURST_STRESS=burst_status,
        Q50_already_in_AIDC_baseline=True,Q90_actual_load_addition=False,
        stress_allocation_role='FROZEN_ARRIVAL_TARGET_DEMAND;NOT_CAPACITY_BACKED_ACTUAL_GPU'
            if authority.get('stress_allocation_source')=='A_STAGE_OPTIMIZED_RESERVE'
            else 'FROZEN_Q90_MINUS_Q50_KERNEL_STRESS;NOT_ACTUAL_GPU',
        model_retraining_calls=0,new_calibrators=0,prediction_scaling_or_clipping=False,
        source_authority={k:v for k,v in authority.items() if k!='stress_site_GPU'})


def compile_sensitivity_policy(packet,envelope,cc4_q50,cc4_q90,kernel,prototypes,bindings,
                               cc4_authority,*,burst=None,grammar=None):
    """Evaluate bounded anonymous conditions; freeze scores and ordered actions."""
    began=perf_counter()
    if dict(bindings)!=packet.bindings:raise ValueError('GRID_PACKET_POLICY_BINDINGS_DRIFT')
    if packet.known_gpu is None:raise ValueError('FROZEN_KNOWN_GPU_BASELINE_REQUIRED')
    envelope=deepcopy(list(envelope));grammar=dict(grammar or {})
    if not envelope or not prototypes:raise ValueError('NONEMPTY_RESOURCE_ENVELOPE_AND_PROTOTYPES_REQUIRED')
    if any(row['slot_end']-row['slot_start']!=DT or row['site'] not in packet.sites
           or row['slot_start']<packet.begin_seconds or row['slot_start']>=packet.begin_seconds+SLOTS*DT
           or (row['slot_start']-packet.begin_seconds)%DT or row['gpu_capacity']<0
           or not row.get('source_variable') for row in envelope):
        raise ValueError('A_STAGE_OPTIMIZATION_DERIVED_ENVELOPE_REQUIRED')
    if len({(r['site'],r['slot_start']) for r in envelope})!=len(envelope):
        raise ValueError('A_STAGE_ENVELOPE_DUPLICATE_SITE_TIME')
    frozen_scenarios,scenario_audit=_scenarios(packet,envelope,cc4_q50,cc4_q90,kernel,cc4_authority,burst)
    templates=[];comparisons=[];count=0
    anonymous=None if frozen_scenarios is None else frozen_scenarios[0]
    scenario_arrays={} if frozen_scenarios is None else frozen_scenarios[1]
    for ordinal,source in enumerate(prototypes):
        if any(k in source for k in ('uid','job_uid','actual_end','realized_seconds','future_queue')):
            raise ValueError('ANONYMOUS_PROTOTYPES_CANNOT_CONTAIN_FUTURE_JOB_IDENTITIES')
        proto=deepcopy(source)
        if proto.get('reference_resource_scope','ANONYMOUS')!='ANONYMOUS':
            raise ValueError('UNKNOWN_POLICY_MUST_NOT_BORROW_KNOWN_SERVICE')
        state=proto.get('state','PENDING');gpu=proto['gpu'];service=float(proto['service_seconds'])
        lower=float(proto.get('runtime_lower_seconds',service));upper=float(proto.get('runtime_upper_seconds',service))
        if not 0<=lower<=upper or upper!=service:raise ValueError('FROZEN_RUNTIME_UPPER_BUCKET_REQUIRED')
        service_points=sorted({upper,max(lower,1e-9)}|{float(v) for v in np.arange(
            math.ceil(lower/DT)*DT,upper,DT) if v>0})
        if state not in ('PENDING','RUNNING') or type(gpu) is not int or gpu<1 or service<=0:
            raise ValueError('WHOLE_GANG_NOMINAL_PROTOTYPE_REQUIRED')
        budget=float(proto.get('budget_seconds',3600))
        if budget not in range(0,3601,900):raise ValueError('PROTOTYPE_BUDGET_GRAMMAR_REQUIRED')
        source_site=proto['reference_site']
        if source_site not in packet.sites:raise ValueError('PROTOTYPE_REFERENCE_SITE_REQUIRED')
        compatible=tuple(proto.get('compatible_sites',packet.sites))
        if source_site not in compatible or any(s not in packet.sites or
                gpu>max(packet.rack_compatibility[s]) or gpu>packet.capacities[s] for s in compatible):
            raise ValueError('PROTOTYPE_WHOLE_GANG_ORIGINAL_SITE_RACK_COMPATIBILITY')
        for slot in proto.get('time_slots',range(SLOTS)):
            now=packet.begin_seconds+slot*DT
            if type(slot) is not int or not 0<=slot<SLOTS:raise ValueError('PROTOTYPE_TIME_SLOT_REQUIRED')
            ref,ref_tail=_profile(packet.sites,source_site,slot*DT,service,gpu)
            ordered=[];rejected=[];scores=[]
            baseline_supported=(frozen_scenarios is not None and np.all(ref<=anonymous+1e-8))
            if not baseline_supported:
                rejected.append(dict(reason=scenario_audit['status'] if frozen_scenarios is None
                    else 'PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE'))
            metadata=dict(uid='__ANONYMOUS_PROTOTYPE__',submit_seconds=now,event_seconds=now,
                state=state,qos=proto.get('qos','normal'),protected=False,batch_eligible=True,
                is_observed=True,gpu=gpu,t50_seconds=service,nominal_service_seconds=service,
                current_site=source_site,source_site=source_site,compatible_sites=list(compatible),
                accumulated_compute_seconds=float(proto.get('accumulated_compute_seconds',1800)),
                migration_capability=proto.get('migration_capability'),migration_count=0)
            receipt=dict(uid=metadata['uid'],case_sha=bindings['case_sha'],reference_start_seconds=now,
                budget_seconds=budget,allowed_starts_seconds=[now+d for d in range(0,int(budget)+1,900)])
            variants=[]
            if state=='PENDING':
                for delay in grammar.get('delays_seconds',(0,900,1800,2700,3600)):
                    if delay>budget or delay%DT:continue
                    for site in compatible:
                        if site not in packet.sites:continue
                        if site!=source_site and proto.get('can_prestart_place') is not True:continue
                        action=('PREPLACE' if site!=source_site else 'START_NOW' if delay==0 else 'DELAY_'+str(int(delay//60)))
                        after,tail=_profile(packet.sites,site,slot*DT+delay,service,gpu)
                        variants.append(dict(action=action,site=site,delay_seconds=delay,after=after,
                            tail_GPUh=tail,segments=[dict(resource='gpu:'+site,begin=now+delay,
                            end=now+delay+service,quantity=gpu)],qos_consumption_seconds=delay))
            else:
                variants.append(dict(action='STAY',site=source_site,delay_seconds=0,after=ref,
                    tail_GPUh=ref_tail,segments=[],qos_consumption_seconds=0))
                ledger=ReservationLedger(packet.capacities,proto.get('wan_capacities'))
                for site in compatible:
                    migrated,reason=migration_guard(metadata,receipt,now=now,
                        accumulated_compute_seconds=metadata['accumulated_compute_seconds'],destination=site,
                        remaining_nominal_seconds=service,reservations=ledger,checkpoint_at=now)
                    if migrated is None:
                        if site!=source_site:rejected.append(dict(action='CHECKPOINT_MIGRATE',site=site,reason=reason))
                        continue
                    interruption=migrated['interruption_seconds']
                    # Inherited GPU hold phases consume IT/PCC, without claiming
                    # useful compute during transfer or restart.
                    after=np.zeros_like(ref);tail=0.
                    for segment in migrated['segments']:
                        if segment['resource'].startswith('gpu:'):
                            profile,p_tail=_profile(packet.sites,segment['resource'][4:],
                                segment['begin']-packet.begin_seconds,segment['end']-segment['begin'],gpu)
                            after+=profile;tail+=p_tail
                    variants.append(dict(action='CHECKPOINT_MIGRATE',site=site,delay_seconds=0,
                        after=after,tail_GPUh=tail,segments=migrated['segments'],
                        interruption_seconds=interruption,qos_consumption_seconds=interruption,
                        migration_hold_contract=migrated['hold_contract'],
                        migration_timing_offsets_seconds={name:value-now for name,value in migrated['times'].items()},
                        migration_capability_source_sha=migrated['capability_source_sha'],
                        preserved_compute_GPUh=gpu*service/3600.))
            for variant in variants:
                count+=1
                if not baseline_supported:continue
                resource_reason=None
                ledger=ReservationLedger(packet.capacities,proto.get('wan_capacities'))
                if variant['action']!='STAY':
                    guarded=[dict(s,scope='anonymous',envelope_guard=s['resource']=='gpu:'+variant['site']) for s in variant['segments']]
                    resource_reason=ledger.feasible(guarded,envelope=envelope,scope='anonymous')
                if resource_reason:
                    rejected.append(dict(action=variant['action'],site=variant['site'],reason=resource_reason));continue
                evaluation={}
                for name,stress in scenario_arrays.items():
                    endpoint_scores=[]
                    for endpoint in service_points:
                        reference_profile,_=_profile(packet.sites,source_site,slot*DT,endpoint,gpu)
                        if variant['action']=='STAY':after=reference_profile
                        elif state=='PENDING':
                            after,_=_profile(packet.sites,variant['site'],slot*DT+variant['delay_seconds'],endpoint,gpu)
                        else:
                            after=np.zeros_like(ref)
                            for segment in variant['segments']:
                                if not segment['resource'].startswith('gpu:'):continue
                                end=segment['end']+(endpoint-service if segment['resource']=='gpu:'+variant['site'] else 0)
                                if end>segment['begin']:
                                    profile,_=_profile(packet.sites,segment['resource'][4:],
                                        segment['begin']-packet.begin_seconds,end-segment['begin'],gpu)
                                    after+=profile
                        delta=after-reference_profile
                        score=packet.evaluate(delta,remaining_slot=slot,scenario_gpu=stress)
                        total=packet.known_gpu+anonymous+stress+delta
                        if np.any(total>np.asarray([packet.capacities[s] for s in packet.sites])+1e-8) or np.any(total<-1e-8):
                            score=dict(score,hard_feasible=False,violations=score['violations']+
                                [dict(reason='WHOLE_GANG_SITE_GPU_CAPACITY')])
                        endpoint_scores.append(score)
                    evaluation[name]=dict(peak_score=max(s['peak_score'] for s in endpoint_scores),
                        hard_feasible=all(s['hard_feasible'] for s in endpoint_scores),
                        violations=_violations_summary([r for s in endpoint_scores for r in s['violations']]),
                        runtime_bucket_piecewise_endpoints_seconds=service_points)
                scores.append(dict(action=variant['action'],site=variant['site'],delay_seconds=variant['delay_seconds'],
                    scenario_scores={name:v['peak_score'] for name,v in evaluation.items()},
                    hard_feasible=all(v['hard_feasible'] for v in evaluation.values())))
                if not all(v['hard_feasible'] for v in evaluation.values()):
                    rejected.append(dict(action=variant['action'],site=variant['site'],
                        reason='ORIGINAL_GRID_OR_RESOURCE_HARD_CONSTRAINT',scenarios=evaluation));continue
                row={k:v for k,v in variant.items() if k not in ('after','segments')}
                row.update(worst_peak_score=max(v['peak_score'] for v in evaluation.values()),
                    scenario_scores={name:v['peak_score'] for name,v in evaluation.items()},
                    service_seconds=service,compute_service_GPUh=gpu*service/3600.,
                    reference_service_GPUh=gpu*service/3600.,service_preserved=True,
                    original_A_source_variables=sorted({r['source_variable'] for r in envelope if r['site']==variant['site']
                        and r['slot_start']<now+variant['delay_seconds']+service and r['slot_end']>now+variant['delay_seconds']}))
                ordered.append(row)
            ordered.sort(key=lambda r:(r['worst_peak_score'],r['qos_consumption_seconds'],r['site'],r['action']))
            template=dict(template_id='T'+str(ordinal)+'_'+str(slot),time_slot=slot,state=state,
                qos=proto.get('qos','normal'),gpu=gpu,service_seconds=service,reference_site=source_site,
                event='OBSERVED_JOB_SUBMISSION' if state=='PENDING' else 'OBSERVED_COMPUTE_CHECKPOINT',
                runtime_match='EXACT_NOMINAL_SERVICE_SECONDS' if lower==upper else 'PIECEWISE_CERTIFIED_UPPER_BUCKET',
                runtime_lower_seconds=lower,runtime_upper_seconds=upper,prototype_budget_seconds=budget,
                reference_resource_scope='ANONYMOUS',Known_schedule_modifications=0,
                migration_capability_status='SOURCE_CONTRACT_SUPPLIED' if proto.get('migration_capability')
                    else 'MIGRATION_CAPABILITY_UNCONFIRMED' if state=='RUNNING' else 'NOT_APPLICABLE',
                ordered_actions=ordered,fallback='QUEUE' if state=='PENDING' else 'STAY',
                status='OFFLINE_POLICY_OPTIMIZATION_VALIDATED' if len(scores)>=2 and ordered else 'NO_FEASIBLE_ACTION',
                rejected_candidates=rejected,scenario_comparisons=scores)
            templates.append(template)
            comparisons.append(dict(template_id=template['template_id'],candidate_scores=scores,
                selected=ordered[0] if ordered else None,remaining_all_line_slots=SLOTS-slot))
    elapsed=perf_counter()-began
    try:
        import psutil
        memory=psutil.Process().memory_info();rss=memory.rss;peak_rss=getattr(memory,'peak_wset',None)
    except ImportError:rss=peak_rss=None
    support=None
    if anonymous is not None:
        profiles=np.stack([packet.known_gpu+anonymous+stress for stress in scenario_arrays.values()])
        lower_profile=profiles.min(axis=0).tolist();upper_profile=profiles.max(axis=0).tolist()
        support=dict(lower_GPU=lower_profile,upper_GPU=upper_profile,scenario_ids=list(scenario_arrays),
            source_sha=digest(dict(bindings=bindings,lower=lower_profile,upper=upper_profile)),
            support_is_necessary_guard_not_Actual_grid_certificate=True)
    body=dict(policy_version=POLICY_ID,bindings=dict(bindings),begin_seconds=packet.begin_seconds,
        end_seconds=packet.begin_seconds+SLOTS*DT,control_grid_seconds=900,checkpoint_period_seconds=1800,
        envelope=envelope,templates=templates,rules=[],scenario_audit=scenario_audit,
        site_axis=list(packet.sites),runtime_resource_baseline_GPU=(packet.known_gpu+
            (anonymous if anonymous is not None else np.zeros_like(packet.known_gpu))).tolist(),
        runtime_resource_baseline_is_forecast_not_Actual=True,
        runtime_resource_support=support,
        Event30=dict(status='NOT_AUTHORIZED_THRESHOLD_METRIC_SOURCE_MISSING',
            activation_claimed=False,execution_1800_compute_checkpoint_is_separate=True),
        candidate_comparison_audit=comparisons,original_grid_authority=packet.authority,
        grammar=grammar,status='OFFLINE_POLICY_OPTIMIZATION_VALIDATED' if any(
            r['status']=='OFFLINE_POLICY_OPTIMIZATION_VALIDATED' for r in templates) else 'POLICY_COMPILER_ONLY',
        compiler_source_sha=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
        metrics=dict(compile_wall_seconds=elapsed,RSS_bytes_at_compile_end=rss,
            process_lifetime_peak_RSS_bytes=peak_rss,
            peak_RSS_scope='PROCESS_LIFETIME_INCLUDING_SOURCE_PACKET_LOAD',
            templates=len(templates),bounded_candidates=count,grid_evaluation_calls=packet.evaluation_calls,
            cache_hits=packet.cache_hits,scenario_tree_nodes=0,Native_Optimize_calls=0),
        objective='MIN_MAX_SCENARIO_MAX_ALL_LINES_REMAINING_96_SLOTS_ORIGINAL_P1',
        P2_calls=0,global_LB_or_optimality_certificate=False,Fresh_AC_status='NOT_RUN',
        online_global_optimizer_calls=0,online_grid_horizon_evaluations=0,
        policy_scope='ANONYMOUS_EXACT_NOMINAL_PROTOTYPE_CONDITIONS;UNMATCHED_JOBS_FAIL_CLOSED')
    # Measurements are evidence, not scientific policy identity.
    body=_json(body)
    body['policy_sha']=digest({k:v for k,v in body.items() if k!='metrics'})
    return FrozenSensitivityPolicy(dict(body,content_sha=digest(body)))


def bounded_prototypes(packet,envelope,*,time_slots=None,gpu_gangs=(1,4,16),
                       runtime_bounds=(900.,3600.,14400.),max_templates=144,
                       migration_capability=None,wan_capacities=None):
    """Preregistered finite conditions, chosen only from frozen Planning arrays."""
    if type(max_templates) is not int or max_templates<1:raise ValueError('BOUNDED_TEMPLATE_LIMIT_REQUIRED')
    if time_slots is None:
        baseline=packet.evaluate(np.zeros((SLOTS,len(packet.sites))))['per_slot_peak']
        time_slots=sorted(range(SLOTS),key=lambda t:(-baseline[t],t))[:8]
    bounds=tuple(map(float,runtime_bounds))
    if not bounds or any(v<=0 for v in bounds) or list(bounds)!=sorted(set(bounds)):
        raise ValueError('PREREGISTERED_RUNTIME_BUCKET_ORDER_REQUIRED')
    anonymous=np.zeros((SLOTS,len(packet.sites)))
    for row in envelope:
        t=int((row['slot_start']-packet.begin_seconds)/DT)
        if 0<=t<SLOTS:anonymous[t,packet.sites.index(row['site'])]=row['gpu_capacity']
    prototypes=[]
    for t in time_slots:
        if type(t) is not int or not 0<=t<SLOTS:raise ValueError('PREREGISTERED_CRITICAL_TIME_AXIS_REQUIRED')
        for gpu in gpu_gangs:
            compatible=[s for s in packet.sites if type(gpu) is int and
                0<gpu<=packet.capacities[s] and gpu<=max(packet.rack_compatibility[s])]
            if not compatible:continue
            lower=0.
            for upper in bounds:
                eligible=[]
                for site in compatible:
                    reference,_=_profile(packet.sites,site,t*DT,upper,gpu)
                    if np.all(reference<=anonymous+1e-8) and t*DT+upper<=SLOTS*DT:eligible.append(site)
                reference=eligible[0] if eligible else compatible[0]
                pending=dict(state='PENDING',qos='normal',gpu=gpu,service_seconds=upper,
                    runtime_lower_seconds=lower,runtime_upper_seconds=upper,reference_site=reference,
                    compatible_sites=compatible,time_slots=[t],can_prestart_place=True,budget_seconds=3600,
                    prototype_source='FROZEN_A_ENVELOPE_AND_PREREGISTERED_ANONYMOUS_GRAMMAR',
                    reference_rule='FIXED_ASCENDING_COMPATIBLE_SITE_CONTINUOUS_ENVELOPE_FIT',
                    reference_resource_scope='ANONYMOUS',baseline_reference_supported=bool(eligible),future_individual_UIDs=0)
                prototypes.append(pending)
                if len(prototypes)<max_templates:
                    prototypes.append(dict(pending,state='RUNNING',can_prestart_place=False,
                        accumulated_compute_seconds=1800.,migration_capability=deepcopy(migration_capability),
                        wan_capacities=deepcopy(wan_capacities)))
                lower=upper
                if len(prototypes)>=max_templates:return prototypes
    return prototypes


def export_policy_evidence(policy,output):
    """Serialize bounded offline evidence; this does not execute Actual or AC."""
    from .actual_validation import write,record
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    doc=policy.document
    docs={
        'A_STAGE_RESOURCE_ENVELOPE.json':dict(aidc_anchor=policy.bindings['aidc_anchor'],envelope=doc['envelope']),
        'GRID_SENSITIVITY_SCORE_AUDIT.json':dict(authority=doc['original_grid_authority'],
            objective=doc['objective'],comparisons=doc['candidate_comparison_audit'],
            full_all_line_remaining_horizon=True,Fresh_AC_status='NOT_RUN'),
        'CONTROL_CANDIDATE_GENERATION.json':dict(status=doc['status'],templates=doc['templates'],
            future_individual_UIDs=0,scope=doc['policy_scope']),
        'Q50_Q90_BURST_POLICY_COMPARISON.json':dict(scenarios=doc['scenario_audit'],
            comparisons=doc['candidate_comparison_audit'],Q90_is_Actual_load=False),
        'CONTROL_POLICY_SHA_MANIFEST.json':dict(policy=POLICY_ID,policy_sha=policy.sha,
            content_sha=doc['content_sha'],bindings=policy.bindings,compiler_source_sha=doc['compiler_source_sha']),
        'CONTROL_POLICY_RUNTIME_MEMORY.json':dict(**doc['metrics'],**policy.runtime_metrics()),
    }
    path=output/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json';policy.save(path)
    reloaded=FrozenSensitivityPolicy.load(path,bindings=policy.bindings)
    docs['CONTROL_POLICY_RELOAD_TEST.json']=dict(PASS=reloaded.sha==policy.sha and
        reloaded.document['templates']==doc['templates'],policy_sha=policy.sha,
        runtime_actions_executed=False,Actual_status='NOT_RUN',Fresh_AC_status='NOT_RUN')
    for name,payload in docs.items():write(output/name,payload)
    return {name:record(output/name) for name in list(docs)+[path.name]}


class FrozenSensitivityPolicy(FrozenControlPolicy):
    """No score reconstruction online: immutable order plus existing guards."""
    def __init__(self,document):
        body=deepcopy(document);expected=body.pop('content_sha',None)
        if expected!=digest(body) or body.get('policy_version')!=POLICY_ID:
            raise ValueError('FROZEN_SENSITIVITY_POLICY_SHA_MISMATCH')
        if body.get('policy_sha')!=digest({k:v for k,v in body.items() if k not in ('metrics','policy_sha')}):
            raise ValueError('FROZEN_SENSITIVITY_SEMANTIC_SHA_MISMATCH')
        if any(not body['bindings'].get(k) for k in REQUIRED_BINDINGS):
            raise ValueError('COMPLETE_SENSITIVITY_POLICY_ANCHORS_REQUIRED')
        self._body=dict(body,content_sha=expected);self._bindings=dict(body['bindings'])
        self._sha=body['policy_sha'];self._index={}
        for template in body['templates']:
            key=(template['time_slot'],template['state'],template['qos'],template['gpu'],template['reference_site'])
            peers=self._index.setdefault(key,[])
            lo,hi=template['runtime_lower_seconds'],template['runtime_upper_seconds']
            if any((r['runtime_lower_seconds']==r['runtime_upper_seconds']==lo==hi) or
                   max(lo,r['runtime_lower_seconds'])<min(hi,r['runtime_upper_seconds'])
                   for r in peers):raise ValueError('AMBIGUOUS_CONDITIONAL_POLICY_TEMPLATE')
            peers.append(template)
        self._lookup_times=[]

    @property
    def document(self):return deepcopy(self._body)
    @property
    def bindings(self):return dict(self._bindings)
    @property
    def sha(self):return self._sha
    def require_bindings(self,expected):
        if any(expected.get(k)!=self._bindings[k] for k in REQUIRED_BINDINGS):
            raise ValueError('FINAL_AIDC_MESS_RESPONSE_INITIAL_STATE_ANCHOR_MISMATCH')
    def resource_baseline_at(self,now):
        t=int((now-self._body['begin_seconds'])//DT)
        if not 0<=t<SLOTS:return None
        return dict(zip(self._body['site_axis'],self._body['runtime_resource_baseline_GPU'][t]))
    def resource_support_at(self,now):
        t=int((now-self._body['begin_seconds'])//DT);support=self._body['runtime_resource_support']
        if support is None or not 0<=t<SLOTS:return None
        return dict(lower_by_site=dict(zip(self._body['site_axis'],support['lower_GPU'][t])),
            upper_by_site=dict(zip(self._body['site_axis'],support['upper_GPU'][t])),
            source_sha=support['source_sha'],scenario_ids=list(support['scenario_ids']),
            support_is_necessary_guard_not_Actual_grid_certificate=True)
    def save(self,path):
        Path(path).write_text(json.dumps(_json(self._body),sort_keys=True,allow_nan=False)+'\n',encoding='utf8')
    @classmethod
    def load(cls,path,*,bindings=None):
        policy=cls(json.loads(Path(path).read_text(encoding='utf8')))
        if bindings is not None:policy.require_bindings(bindings)
        return policy

    def lookup(self,metadata,receipt,now):
        from .actual import _require_public_metadata
        _require_public_metadata(metadata)
        receipt=_receipt(receipt)
        if receipt['uid']!=metadata['uid'] or receipt['case_sha']!=self._bindings['case_sha']:
            raise ValueError('QOS_RECEIPT_UID_OR_CASE_MISMATCH')
        if metadata.get('is_observed',True) is not True or metadata['submit_seconds']>now:
            return None,'NOT_YET_SUBMITTED'
        if now%DT:return None,'CONTROL_GRID_EVENT_NOT_DUE'
        state=metadata.get('state','PENDING')
        if metadata.get('protected') is not False or metadata.get('batch_eligible') is not True:
            return None,'ACTION_QOS_AUTHORITY_UNCONFIRMED'
        service=(float(metadata['t50_seconds'])-float(metadata.get('accumulated_compute_seconds',0))
            if state=='RUNNING' else float(metadata.get('nominal_service_seconds',metadata['t50_seconds'])))
        site=metadata.get('current_site') if state=='RUNNING' else metadata.get('reference_site',metadata.get('source_site'))
        if site is None:
            compatible=sorted(metadata.get('compatible_sites',()))
            site=compatible[0] if compatible else None
        key=(int((now-self._body['begin_seconds'])//DT),state,metadata.get('qos','normal'),
            metadata['gpu'],site)
        template=next((r for r in self._index.get(key,[]) if
            (service==r['runtime_lower_seconds']==r['runtime_upper_seconds']) or
            r['runtime_lower_seconds']<service<=r['runtime_upper_seconds']),None)
        return template,'MATCH' if template is not None else 'NO_MATCHED_FROZEN_TEMPLATE'

    def candidates(self,metadata,receipt,now):
        template,reason=self.lookup(metadata,receipt,now)
        if template is None:return [],reason
        if metadata.get('state','PENDING')!='PENDING':return [],'RUNNING_START_IMMUTABLE'
        receipt=_receipt(receipt);out=[]
        for row in template['ordered_actions']:
            site=row['site'];start=now+row['delay_seconds']
            service=float(metadata.get('nominal_service_seconds',metadata['t50_seconds']))
            end=start+service
            delay=max(0.,start-receipt['reference_start_seconds'])
            consumed=delay+float(metadata.get('cumulative_migration_interruption_seconds',0))
            if (start not in receipt['allowed_starts_seconds'] or consumed>receipt['budget_seconds']+1e-9
                    or site not in metadata.get('compatible_sites',())
                    or (metadata.get('source_site') is not None and site!=metadata['source_site']
                        and metadata.get('can_prestart_place') is not True)):
                continue
            if any(metadata.get(name) is not None and value>metadata[name] for name,value in
                   (('hard_latest_start_seconds',start),('completion_deadline_seconds',end))):continue
            if start<max(metadata.get('release_seconds') or -math.inf,
                         metadata.get('hard_earliest_start_seconds') or -math.inf):continue
            out.append(dict(uid=metadata['uid'],action='PREPLACE' if row['action']=='PREPLACE'
                else 'DELAY' if row['delay_seconds'] else 'START',policy_action=row['action'],
                site=site,start_seconds=start,nominal_end_seconds=end,additional_start_delay_seconds=delay,
                rule_id=template['template_id'],estimated_worst_peak=row['worst_peak_score'],
                scenario_scores=row['scenario_scores'],segments=[dict(resource='gpu:'+site,
                    begin=start,end=end,quantity=metadata['gpu'])]))
        return out,'MATCH' if out else 'NO_CURRENTLY_AUTHORIZED_FROZEN_ACTION'

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        if metadata.get('state')=='RUNNING':
            return self.select_migration(metadata,receipt,now,reservations,reserve=reserve)
        began=perf_counter();candidates,reason=self.candidates(metadata,receipt,now);rejected=[]
        for row in candidates:
            if reserve:ok,reason=reservations.reserve(metadata['uid'],row['segments'],envelope=self._body['envelope'],scope='anonymous')
            else:
                segments=[dict(s,scope='anonymous') for s in row['segments']]
                reason=reservations.feasible(segments,envelope=self._body['envelope'],scope='anonymous');ok=reason is None
            if ok:
                self._lookup_times.append(perf_counter()-began)
                return dict(row,status='SELECTED_FROZEN_OFFLINE_RANK',policy_sha=self.sha,
                    rejected_candidates=rejected,online_global_optimizer_calls=0,online_grid_horizon_evaluations=0,
                    affine_approximation_only=True,grid_safety_guaranteed=False,Fresh_AC_status='NOT_RUN')
            rejected.append(dict(action=row['policy_action'],site=row['site'],reason=reason))
        self._lookup_times.append(perf_counter()-began)
        return dict(uid=metadata['uid'],action='QUEUE',status='NO_FEASIBLE_ACTION',reason=reason,
            rejected_candidates=rejected,policy_sha=self.sha,grid_safety_guaranteed=False,
            online_global_optimizer_calls=0,online_grid_horizon_evaluations=0)

    def select_migration(self,metadata,receipt,now,reservations,*,checkpoint_at=None,reserve=True):
        if now%DT:
            return dict(action='STAY',status='NO_FEASIBLE_ACTION',
                reason='OFF_GRID_CHECKPOINT_OUTSIDE_FROZEN_SCORE_TEMPLATE',grid_safety_guaranteed=False)
        template,reason=self.lookup(metadata,receipt,now)
        if template is None:return dict(action='STAY',status='NO_FEASIBLE_ACTION',reason=reason,grid_safety_guaranteed=False)
        rejected=[]
        for row in template['ordered_actions']:
            if row['action']=='STAY':
                unconfirmed=template['migration_capability_status']=='MIGRATION_CAPABILITY_UNCONFIRMED'
                return dict(action='STAY',status='NO_FEASIBLE_ACTION' if unconfirmed else 'SELECTED_FROZEN_OFFLINE_RANK',
                    rule_id=template['template_id'],reason='MIGRATION_CAPABILITY_UNCONFIRMED' if unconfirmed
                        else rejected[-1]['reason'] if rejected else 'FROZEN_STAY_RANK',
                    rejected_candidates=rejected,grid_safety_guaranteed=False)
            remaining=metadata['t50_seconds']-metadata.get('accumulated_compute_seconds',0)
            migration,reason=migration_guard(metadata,receipt,now=now,
                accumulated_compute_seconds=metadata.get('accumulated_compute_seconds',0),destination=row['site'],
                remaining_nominal_seconds=remaining,reservations=reservations,checkpoint_at=checkpoint_at)
            if migration is None:
                rejected.append(dict(site=row['site'],reason=reason));continue
            actual_offsets={name:value-migration['control_checkpoint_seconds']
                for name,value in migration['times'].items()}
            if (actual_offsets!=row.get('migration_timing_offsets_seconds')
                    or migration['hold_contract']!=row.get('migration_hold_contract')):
                reason='MIGRATION_PHYSICAL_PROFILE_OUTSIDE_FROZEN_TEMPLATE'
                rejected.append(dict(site=row['site'],reason=reason))
                continue
            segments=[dict(s,scope='anonymous',envelope_guard=s['resource']=='gpu:'+row['site']) for s in migration['segments']]
            if reserve:ok,reason=reservations.reserve(metadata['uid'],segments,replace=True,envelope=self._body['envelope'],scope='anonymous')
            else:
                reason=reservations.feasible(segments,exclude=metadata['uid'],envelope=self._body['envelope'],scope='anonymous');ok=reason is None
            if ok:return dict(action='CHECKPOINT_MIGRATE',status='SELECTED_FROZEN_OFFLINE_RANK',
                migration=migration,rule_id=template['template_id'],policy_sha=self.sha,
                estimated_worst_peak=row['worst_peak_score'],online_global_optimizer_calls=0,online_grid_horizon_evaluations=0,
                rejected_candidates=rejected,affine_approximation_only=True,grid_safety_guaranteed=False,Fresh_AC_status='NOT_RUN')
            rejected.append(dict(site=row['site'],reason=reason))
        return dict(action='STAY',status='NO_FEASIBLE_ACTION',reason=reason,rejected_candidates=rejected,grid_safety_guaranteed=False)

    def runtime_metrics(self):
        samples=np.asarray(self._lookup_times[-4096:])*1000
        return dict(lookup_calls=len(self._lookup_times),event_median_ms=None if not len(samples) else float(np.median(samples)),
            event_p95_ms=None if not len(samples) else float(np.percentile(samples,95)),
            online_global_optimizer_calls=0,online_grid_horizon_evaluations=0)
