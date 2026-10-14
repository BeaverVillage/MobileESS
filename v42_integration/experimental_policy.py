"""Bounded event selector for a declared conditional research experiment.

The signed original grid packet and literal MESS anchor remain fixed. Runtime
scoring reuses literal A2 nominal service and evaluates only Q90-Q50 aggregate
recourse. Public observations guard execution; no private future is read.
"""
from copy import deepcopy
from dataclasses import fields
import json,math,time
from pathlib import Path
from collections import OrderedDict
import hashlib
import numpy as np

from .policy import digest,migration_guard
from .qos import ObservedJob
from .q90_recourse import evaluate_q90_recourse


def rank_action_scores(rows, *, q50_tie_tolerance=1e-9):
    """Pure bounded ordering; Q90 risk never vetoes a Q50-feasible action."""
    accepted=[deepcopy(r) for r in rows if r.get('physical_feasible') is True and r.get('q50_hard_feasible') is True
        and r.get('q90_risk',{}).get('hard_feasible') is True]
    accepted.sort(key=lambda r:float(r['q50_peak_score']))
    ordered=[]
    while accepted:
        minimum=accepted[0]['q50_peak_score']
        cut=next((i for i,r in enumerate(accepted) if r['q50_peak_score']-minimum>q50_tie_tolerance),len(accepted))
        group,accepted=accepted[:cut],accepted[cut:]
        group.sort(key=lambda r:(r['q90_risk']['violation_count'],r['q90_risk']['carryout_GPUh'],
            r['q90_risk']['queue_GPUh_hours'],r['q90_risk']['peak_score'],r.get('migration_count',0),
            r.get('intentional_burden_seconds',0),str(r.get('site','')),str(r.get('action',''))))
        ordered.extend(group)
    return dict(ordered_actions=ordered)

POLICY_ID='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1'
ALGORITHMS=('FIXED','GREEDY','GRID_SENSITIVITY_AWARE')


def load_experimental_migration_authority(folder=None):
    """Verify source numeric receipts; request capabilities remain assumptions."""
    if not folder:
        root=Path(__file__).parents[1]
        folder=root/'audit/migration'
        if not (folder/'MIGRATION_PACKET_API_HANDOFF.json').is_file():
            folder=root/'docs/v42_experimental_flex_qos_20261014/evidence/migration'
    else:
        folder=Path(folder)
    handoff_path=folder/'MIGRATION_PACKET_API_HANDOFF.json'
    numeric_path=folder/'MIGRATION_SOURCE_NUMERIC_AUTHORITY.json'
    handoff=json.loads(handoff_path.read_text(encoding='utf-8'))
    numeric=json.loads(numeric_path.read_text(encoding='utf-8'))
    for rec in handoff['source_receipts']:
        path=Path(rec['path'])
        if path.stat().st_size!=rec['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=rec['sha256']:
            raise ValueError('MIGRATION_NUMERIC_SOURCE_RECEIPT_DRIFT')
    if (not numeric['exact_original_May_manifest_contract_and_authority_SHA']
            or not numeric['saved_static_WAN_equals_current_template']
            or not numeric['all_static_native_24to119_capacities_equal_original_96_slot_WAN']
            or not all(link['constant_96_slots'] for link in numeric['links'].values())):
        raise ValueError('MIGRATION_FROZEN_NUMERIC_AUTHORITY_REQUIRED')
    if numeric['scalar_authority']['maximum_active_transfers_network_wide']!=1:
        raise ValueError('ORIGINAL_GLOBAL_ONE_WAN_TRANSFER_REQUIRED')
    capacities=dict(handoff['ledger_WAN_capacities'])
    capacities.update({'LINK::'+link:row['bandwidth_bytes_per_second'] for link,row in numeric['links'].items()})
    return dict(packet_source_sha=handoff['packet_source_sha'],scalar=numeric['scalar_authority'],
        routes=numeric['routes'],links=numeric['links'],protocol=handoff['protocol'],
        wan_capacities=capacities,request_capability_is_observed=False,
        source_receipts=handoff['source_receipts']+[dict(path=str(p),bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (handoff_path,numeric_path)])


def segments_gpu(segments,sites,begin):
    result=np.zeros((96,len(sites)))
    left=begin+900*np.arange(96)
    site_index={site:i for i,site in enumerate(sites)}
    for s in segments:
        if not s['resource'].startswith('gpu:'):continue
        site=s['resource'][4:]
        if site not in sites:raise ValueError('EXPERIMENTAL_PHYSICAL_SITE_AXIS')
        j=site_index[site];a=float(s['begin']);b=float(s['end'])
        result[:,j]+=s['quantity']*np.maximum(0.,np.minimum(b,left+900)-np.maximum(a,left))/900
    return result


class ExperimentalControlPolicy:
    """Frozen program, bounded observed-event evaluation; no online optimizer."""
    def __init__(self,packet,bindings,*,qos_provider,q50_hourly,q90_hourly,kernel,
                 queue_authority,frozen_anonymous_gpu,algorithm='GRID_SENSITIVITY_AWARE',max_candidates=108,
                 migration_authority=None,nominal_service=None,train_cdf_lower=None,
                 train_cdf_upper=None,recourse_source_authority=None):
        if algorithm not in ALGORITHMS:raise ValueError('EXPERIMENTAL_ALGORITHM')
        if qos_provider.scenario=='E0':raise ValueError('E0_USES_UNCHANGED_STRICT_POLICY')
        self.packet=packet;self._bindings=deepcopy(bindings);self.qos=qos_provider
        self.algorithm=algorithm;self.max_candidates=int(max_candidates)
        self.q50=np.asarray(q50_hourly,float);self.q90=np.asarray(q90_hourly,float)
        self.kernel=np.asarray(kernel,float);self.queue_authority=deepcopy(queue_authority)
        self.frozen_anonymous=np.asarray(frozen_anonymous_gpu,float)
        self.migration_authority=deepcopy(migration_authority)
        if nominal_service is None or train_cdf_lower is None or train_cdf_upper is None or recourse_source_authority is None:
            raise ValueError('LITERAL_A2_NOMINAL_AND_ORIGINAL_TRAIN_CDF_RECOURSE_REQUIRED')
        self.nominal=deepcopy(nominal_service)
        self.cdf_lower=np.asarray(train_cdf_lower,float).copy();self.cdf_upper=np.asarray(train_cdf_upper,float).copy()
        self.recourse_authority=deepcopy(recourse_source_authority)
        if (tuple(self.nominal['site_axis'])!=tuple(packet.sites)
                or not np.array_equal(np.asarray(self.nominal['known_site_GPU']),packet.known_gpu)
                or not np.array_equal(np.asarray(self.nominal['nominal_site_GPU']),self.frozen_anonymous)
                or not np.array_equal(np.asarray(self.nominal['q50_hourly_GPUh']),self.q50)):
            raise ValueError('LITERAL_A2_NOMINAL_ANCHOR_DRIFT')
        if self.frozen_anonymous.shape!=(96,len(packet.sites)) or np.any(self.frozen_anonymous<0):
            raise ValueError('FROZEN_A2_ANONYMOUS_RESOURCE_AXIS')
        if self.q50.shape!=(24,) or self.q90.shape!=(24,):raise ValueError('FROZEN_CC4_24_HOUR_AXIS')
        self.context=None;self.audit=[];self.last_selection={};self.times=[]
        self.references={};self.reference_audit=[];self.observed_blocks={}
        self.queue_cache=OrderedDict();self.queue_cache_hits=0;self.queue_cache_misses=0
        self.reservation_profile_cache=OrderedDict()
        self.reservation_profile_cache_hits=0;self.reservation_profile_cache_misses=0
        self._original_Q50_sha=digest(self.q50.tolist());self._original_Q90_sha=digest(self.q90.tolist())
        self._doc=dict(policy_id=POLICY_ID,scenario=qos_provider.scenario,
            participation=qos_provider.participation,algorithm=algorithm,bindings=self._bindings,
            qos_spec_sha=qos_provider.stats.sha,source_grid_authority=packet.authority,
            frozen_Q50=self.q50.tolist(),frozen_Q90=self.q90.tolist(),kernel=self.kernel.tolist(),
            frozen_A2_anonymous_GPU=self.frozen_anonymous.tolist(),
            migration_authority=self.migration_authority,
            nominal_service=self.nominal,train_cdf_lower=self.cdf_lower.tolist(),train_cdf_upper=self.cdf_upper.tolist(),
            recourse_source_authority=self.recourse_authority,
            queue_authority=self.queue_authority,max_candidates=self.max_candidates,
            scoring='Q50_ORIGINAL_HARD_ROWS_THEN_Q50_PEAK_Q90_QUEUE_RISK_TIE_THEN_LESS_BURDEN',
            scope='CAUSAL_BOUNDED_EVENT_REPLAY_FIXED_A2_M2_NOT_NEW_A_M_OPTIMUM',
            online_global_optimizer_calls=0,actual_AC_status='NOT_RUN')
        self._doc['exact_input_cache']=dict(max_entries=128,quantization=False,
            key='FULL_CANDIDATE_MINUS_CAUSAL_REFERENCE_GPU_BYTES_SLOT_LITERAL_A2_RECOURSE_SOURCE')
        self._doc['reservation_profile_cache']=dict(max_entries=128,quantization=False,
            key='FULL_ORDERED_UID_STATUS_RESOURCE_BEGIN_END_QUANTITY_FRAME;REPLACE_UID_STATE_NOW')
        self._doc['science_status']='LITERAL_A2_Q50_AND_COMMON_Q90_MINUS_Q50_RECOURSE_CONDITIONAL_REPLAY'
        self._doc['execution_contract']='FROZEN_FIRST_FEASIBLE_REFERENCE_PLUS_IMMUTABLE_B;OBSERVED_PHYSICAL_BLOCK_ONLY_ADVANCE'
        self._sha=digest(self._doc)

    @property
    def bindings(self):return deepcopy(self._bindings)
    @property
    def sha(self):return self._sha
    @property
    def document(self):return deepcopy(dict(self._doc,policy_sha=self.sha))
    def require_bindings(self,bindings):
        if any(self._bindings.get(k)!=v for k,v in bindings.items()):raise ValueError('EXPERIMENTAL_ANCHOR_MISMATCH')

    def save(self,path):
        Path(path).write_text(json.dumps(self.document,sort_keys=True,ensure_ascii=False),encoding='utf-8')

    @classmethod
    def load(cls,path,*,packet,qos_provider,bindings,migration_authority=None):
        doc=json.loads(Path(path).read_text(encoding='utf-8'));claimed=doc.pop('policy_sha')
        if claimed!=digest(doc):raise ValueError('EXPERIMENTAL_POLICY_FILE_SHA_MISMATCH')
        if (doc['bindings']!=bindings or doc['source_grid_authority']!=packet.authority
                or doc['qos_spec_sha']!=qos_provider.stats.sha):
            raise ValueError('EXPERIMENTAL_RELOAD_SOURCE_BINDING_MISMATCH')
        if doc['migration_authority']!=migration_authority:
            raise ValueError('EXPERIMENTAL_RELOAD_MIGRATION_AUTHORITY_MISMATCH')
        result=cls(packet,bindings,qos_provider=qos_provider,q50_hourly=doc['frozen_Q50'],
            q90_hourly=doc['frozen_Q90'],kernel=doc['kernel'],queue_authority=doc['queue_authority'],
            frozen_anonymous_gpu=doc['frozen_A2_anonymous_GPU'],algorithm=doc['algorithm'],
            max_candidates=doc['max_candidates'],migration_authority=migration_authority,
            nominal_service=doc['nominal_service'],train_cdf_lower=doc['train_cdf_lower'],
            train_cdf_upper=doc['train_cdf_upper'],recourse_source_authority=doc['recourse_source_authority'])
        if result.sha!=claimed:raise ValueError('EXPERIMENTAL_RELOAD_PROGRAM_MISMATCH')
        return result

    def set_observed_context(self,*,now,observed_gpu,pending_nominal_work,remaining_q50,
                             remaining_q90,forecast_depletion):
        self.context=dict(now=float(now),observed_gpu=deepcopy(observed_gpu),
            pending_nominal_work=deepcopy(pending_nominal_work),remaining_q50=list(remaining_q50),
            remaining_q90=list(remaining_q90),forecast_depletion=deepcopy(forecast_depletion))
        authority={k:v for k,v in self.queue_authority.items() if k not in ('q90_hourly_GPUh','kernel')}
        authority.update(derivation='PUBLIC_FORECAST_DEPLETION_DIAGNOSTIC_ONLY_NOT_RECOURSE_INPUT',
            original_Q50_sha=self._original_Q50_sha,original_Q90_sha=self._original_Q90_sha,
            observed_nominal_depletion=deepcopy(forecast_depletion))
        self._event_queue_authority=authority
        self._queue_context_key=(tuple(remaining_q50),tuple(remaining_q90),
            tuple(sorted(observed_gpu.items())),digest(authority))

    def _receipt_window(self,metadata,receipt,base,now):
        raw=metadata['source_observed_qos_metadata']
        job=ObservedJob(**{f.name:raw[f.name] for f in fields(ObservedJob) if f.name in raw})
        ref=self.references[metadata['uid']]
        # Intentional delay within this same reference window is already on the
        # absolute clock. Only burden carried across a physical-reference advance
        # and migration pauses reduce its absolute right boundary.
        spent=ref['intentional_burden_at_reference_seconds']+float(metadata.get('cumulative_migration_interruption_seconds',0))
        window=self.qos.execution_window(job,receipt,causal_reference_start_seconds=base,
            event_seconds=ref['proof']['observed_at_seconds'],consumed_budget_seconds=spent,
            reference_proof=ref['proof'])
        window['allowed_starts_seconds']=tuple(t for t in window['allowed_starts_seconds'] if t>=now)
        window['first_causal_reference_start_seconds']=ref['first_reference_start_seconds']
        window['runtime_observed_at_seconds']=float(now)
        window['cumulative_intentional_delay_seconds']=float(metadata.get('additional_start_delay_seconds',0))
        window['cumulative_migration_interruption_seconds']=float(metadata.get('cumulative_migration_interruption_seconds',0))
        window['remaining_budget_seconds']=max(0,receipt.budget_seconds-window['cumulative_intentional_delay_seconds']-
            window['cumulative_migration_interruption_seconds'])
        window['remaining_absolute_window_seconds']=max(0,window['latest_start_seconds']-now)
        window['execution_window_sha']=digest({k:v for k,v in window.items() if k!='execution_window_sha'})
        return window

    def _rack_reason(self,metadata,site):
        gpu=metadata['gpu']
        racks=self.packet.rack_compatibility.get(site,())
        if site not in metadata.get('compatible_sites',()):return 'GPU_SITE_TYPE_INCOMPATIBLE'
        if not racks or not any(float(r)>=gpu for r in racks):return 'WHOLE_GANG_RACK_CAPACITY'
        return None

    def _causal_reference(self,metadata,now,reservations):
        earliest=max(now,metadata.get('release_seconds') or now,metadata.get('hard_earliest_start_seconds') or now)
        earliest=math.ceil(earliest/900)*900
        sites=sorted(metadata.get('compatible_sites',()))
        if metadata.get('source_site') is not None and not metadata.get('can_prestart_place'):
            sites=[metadata['source_site']]
        service=max(float(metadata.get('experimental_prediction_Q50_seconds',metadata['t50_seconds'])),1e-9)
        for start in np.arange(earliest,self.packet.begin_seconds+86400,900):
            for site in sites:
                if self._rack_reason(metadata,site):continue
                segment=[dict(resource='gpu:'+site,begin=float(start),end=float(start+service),quantity=metadata['gpu'])]
                if reservations.feasible(segment,exclude=metadata['uid']) is None:return float(start),site
        return None,None

    def _instantaneous(self,metadata,segments,now,*,replace=False):
        observed=np.array([self.context['observed_gpu'].get(s,0.) for s in self.packet.sites],float)
        if replace and metadata.get('state')=='RUNNING':
            observed[self.packet.sites.index(metadata['current_site'])]-=metadata['gpu']
        for segment in segments:
            if segment['resource'].startswith('gpu:') and segment['begin']<=now<segment['end']:
                observed[self.packet.sites.index(segment['resource'][4:])]+=segment['quantity']
        return observed

    def _score(self,metadata,segments,now,reservations,*,replace=False,base_gpu=None,reference_segments=None,base_gpu_loader=None):
        slot=int((now-self.packet.begin_seconds)//900)
        if not 0<=slot<96:return None,'OUTSIDE_REPLAY_DAY'
        caps=np.array([self.packet.capacities[s] for s in self.packet.sites])
        instant=self._instantaneous(metadata,segments,now,replace=replace)
        if np.any(instant>caps+1e-8):return None,'CURRENT_INSTANTANEOUS_WHOLE_GANG_CAPACITY'
        frozen_base=self.packet.known_gpu+self.frozen_anonymous
        _,instant_violations=self.packet._at_slot(slot,instant-frozen_base[slot])
        if instant_violations:
            return None,'CURRENT_OBSERVED_ORIGINAL_GRID_HARD:'+','.join(sorted({r['reason'] for r in instant_violations}))
        if base_gpu is None and base_gpu_loader is not None:
            base_gpu=base_gpu_loader()
        if base_gpu is None:
            existing=[]
            for key,row in reservations.reservations.items():
                if row['status']!='RELEASED' and (not replace or key!=metadata['uid']):existing.extend(row['segments'])
            base_gpu=segments_gpu(existing,self.packet.sites,self.packet.begin_seconds)
        future=[dict(seg,begin=max(now,seg['begin'])) for seg in segments if seg['end']>max(now,seg['begin'])]
        fixed=base_gpu+segments_gpu(future,self.packet.sites,self.packet.begin_seconds)
        if np.any(fixed[slot:]>caps+1e-8):return None,'CURRENT_FUTURE_ACTUAL_RESERVATION_CAPACITY'
        if reference_segments is None:
            reference_segments=reservations.reservations.get(metadata['uid'],{}).get('segments',[]) if replace else segments
        reference=[dict(seg,begin=max(now,seg['begin'])) for seg in reference_segments if seg['end']>max(now,seg['begin'])]
        delta=segments_gpu(future,self.packet.sites,self.packet.begin_seconds)-segments_gpu(reference,self.packet.sites,self.packet.begin_seconds)
        delta[:slot]=0.  # No change to completed clocks or pre-event slot portion.
        key=(delta.tobytes(),slot,instant.tobytes(),tuple(sorted(self.context['observed_gpu'].items())))
        if key in self.queue_cache:
            self.queue_cache_hits+=1;self.queue_cache.move_to_end(key)
            return deepcopy(self.queue_cache[key]),None
        self.queue_cache_misses+=1
        forecast=frozen_base+delta
        grid=self.packet.evaluate(delta,remaining_slot=slot)
        if np.any(forecast[slot:]<-1e-8) or np.any(forecast[slot:]>caps+1e-8):
            grid=deepcopy(grid);grid['hard_feasible']=False
            grid['violations'].append(dict(slot=slot,reason='LITERAL_A2_CANDIDATE_DELTA_PHYSICAL_CAPACITY'))
        if grid['hard_feasible']:
            recourse=evaluate_q90_recourse(self.packet,self.nominal,self.q90,self.cdf_lower,self.cdf_upper,
                candidate_gpu_delta=delta,remaining_slot=slot,begin=0,source_authority=self.recourse_authority)
            risk=dict(source_sha=digest(self.recourse_authority),peak_score=recourse['original_grid_score']['peak_score'],
                hard_feasible=recourse['physical_hard_feasible'],
                violation_count=len(recourse['original_grid_score']['violations'])+len(recourse['CDF_timing_violations']),
                carryout_GPUh=recourse['risk_total_unfinished_GPUh'],queue_GPUh_hours=recourse['queue_area_GPUh_hours'],
                CDF_timing_status=recourse['CDF_timing_status'],CDF_job_QoS_certificate=False)
            mass=deepcopy(recourse['mass'])
        else:
            risk=dict(status='NOT_EVALUATED_Q50_HARD_REJECTED',peak_score=None,violation_count=None,
                carryout_GPUh=None,queue_GPUh_hours=None,hard_feasible=False)
            mass=dict(status='NOT_EVALUATED_Q50_HARD_REJECTED')
        result=dict(q50_peak_score=grid['peak_score'],q50_hard_feasible=grid['hard_feasible'],
            q50_violations=grid['violations'],q90_risk=risk,q90_mass_conservation=mass,
            q50_carryout_GPUh=float(sum(self.nominal['carryout_GPUh_by_hour'])),
            candidate_gpu_delta_sha=digest(delta.tolist()),
            nominal_service_sha=self.nominal['nominal_service_sha'],
            prediction_scope='LITERAL_FROZEN_A2_Q50_PLUS_ACTION_MINUS_CAUSAL_REFERENCE;COMMON_FULL_DAY_Q90_EXTRA_COUNTERFACTUAL',
            current_observed_pending_served_before_event=False,current_instantaneous_GPU=instant.tolist(),
            current_observed_GPU=deepcopy(self.context['observed_gpu']),Fresh_AC_status='NOT_RUN')
        counts={};slots={}
        for violation in grid['violations']:
            reason=violation['reason'];counts[reason]=counts.get(reason,0)+1
            slots.setdefault(reason,set()).add(violation['slot'])
        result['q50_violation_reason_counts']=counts
        result['q50_violation_slots_by_reason']={reason:sorted(values) for reason,values in slots.items()}
        result['q50_first_violation']=grid['violations'][0] if grid['violations'] else None
        self.queue_cache[key]=deepcopy(result)
        if len(self.queue_cache)>128:self.queue_cache.popitem(last=False)
        return result,None

    def _reservation_frame_profile(self,metadata,now,reservations,*,replace=False):
        # Preserve iteration order: the exact original floating-point projection
        # sums segments in this order. No quantization or timestamp bucketing.
        frame=tuple((uid,row['status'],tuple((seg['resource'],seg['begin'],seg['end'],seg['quantity'])
            for seg in row['segments'])) for uid,row in reservations.reservations.items())
        running=replace and metadata.get('state')=='RUNNING'
        key=(frame,metadata['uid'] if replace else None,metadata.get('state') if replace else None,
            float(now) if running else None,self.packet.begin_seconds,tuple(self.packet.sites))
        if key in self.reservation_profile_cache:
            self.reservation_profile_cache_hits+=1;self.reservation_profile_cache.move_to_end(key)
            return self.reservation_profile_cache[key].copy()
        self.reservation_profile_cache_misses+=1
        existing=[]
        for uid,row in reservations.reservations.items():
            if row['status']!='RELEASED' and (not replace or uid!=metadata['uid']):existing.extend(row['segments'])
        if running:
            existing.extend(dict(seg,end=min(now,seg['end']))
                for seg in reservations.reservations.get(metadata['uid'],{}).get('segments',[])
                if seg['begin']<min(now,seg['end']))
        result=segments_gpu(existing,self.packet.sites,self.packet.begin_seconds)
        self.reservation_profile_cache[key]=result.copy()
        if len(self.reservation_profile_cache)>128:self.reservation_profile_cache.popitem(last=False)
        return result

    def _choose(self,metadata,receipt,now,reservations,variants,*,reserve):
        began=time.perf_counter();evaluated=[];rejected=[]
        calls_before=self.packet.evaluation_calls
        # One immutable serial selection snapshot. Reuse requires the complete
        # ordered reservation frame; candidate-specific phases remain exact.
        replacing=bool(variants and variants[0].get('replace'))
        base_gpu=None
        def load_base_gpu():
            nonlocal base_gpu
            if base_gpu is None:
                base_gpu=self._reservation_frame_profile(metadata,now,reservations,replace=replacing)
            return base_gpu
        for ordinal,row in enumerate(variants[:self.max_candidates]):
            reason=self._rack_reason(metadata,row['site'])
            if reason is None:reason=reservations.feasible(row['segments'],exclude=metadata['uid'] if row.get('replace') else None)
            if reason:
                rejected.append(dict(action=row['policy_action'],site=row['site'],reason=reason));continue
            score,reason=self._score(metadata,row['segments'],now,reservations,replace=row.get('replace',False),reference_segments=row.get('reference_segments'),base_gpu_loader=load_base_gpu)
            if reason:
                rejected.append(dict(action=row['policy_action'],site=row['site'],reason=reason));continue
            evaluated.append(dict(row,**score,physical_feasible=True,candidate_id=self.sha[:12]+':'+str(ordinal),
                delay_seconds=row.get('additional_start_delay_seconds',0),migration_count=int(row['action']=='CHECKPOINT_MIGRATE')))
        if self.algorithm=='GRID_SENSITIVITY_AWARE':ordered=rank_action_scores(evaluated)['ordered_actions']
        else:
            ordered=[r for r in evaluated if r['q50_hard_feasible'] and r['q90_risk']['hard_feasible']]
            if self.algorithm=='FIXED':ordered=[r for r in ordered if r.get('reference_action')]
            else:ordered.sort(key=lambda r:(r.get('current_slot_candidate_GPU',0),r['delay_seconds'],r['site']))
        selected=None
        for row in ordered:
            if reserve and row['action']!='STAY':
                ok,reason=reservations.reserve(metadata['uid'],row['segments'],replace=row.get('replace',False))
                if not ok:
                    rejected.append(dict(action=row['policy_action'],site=row['site'],reason=reason));continue
            selected=dict(row,uid=metadata['uid'],policy_sha=self.sha,rule_id=row['candidate_id'],
                status='SELECTED_EXPERIMENTAL_CONDITIONAL_ACTION',grid_safety_guaranteed=False,
                online_global_optimizer_calls=0,experiment_not_A_M_optimum=True)
            break
        if selected is None:selected=dict(uid=metadata['uid'],action='STAY' if metadata.get('state')=='RUNNING' else 'QUEUE',
            status='NO_FEASIBLE_EXPERIMENTAL_ACTION',reason='Q50_GRID_OR_PHYSICAL_CANDIDATES_REJECTED',
            policy_sha=self.sha,physical_or_Q50_veto=True,grid_safety_guaranteed=False)
        selected['online_grid_horizon_evaluations']=self.packet.evaluation_calls-calls_before
        def action_counts(rows):
            counts={}
            for row in rows:
                label='DELAY' if row['policy_action'].startswith('DELAY') else row['policy_action']
                counts[label]=counts.get(label,0)+1
            return counts
        self.audit.append(dict(uid=metadata['uid'],time_seconds=now,state=metadata.get('state'),
            generated=len(variants),physically_and_grid_evaluated=len(evaluated),
            generated_action_counts=action_counts(variants),evaluated_action_counts=action_counts(evaluated),
            signed_packet_evaluation_calls=selected['online_grid_horizon_evaluations'],
            candidate_limit=self.max_candidates,candidates_truncated=max(0,len(variants)-self.max_candidates),
            q50_hard_pass=sum(r['q50_hard_feasible'] for r in evaluated),approved=len(ordered),
            selected_action=selected['action'],selected_candidate=selected.get('candidate_id'),
            selected_Q50_peak=selected.get('q50_peak_score'),selected_Q90_risk=deepcopy(selected.get('q90_risk')),
            selected_Q90_mass=deepcopy(selected.get('q90_mass_conservation')),
            q50_scores=[dict(action=r['policy_action'],site=r['site'],score=r['q50_peak_score'],hard=r['q50_hard_feasible'],
                violation_reason_counts=r['q50_violation_reason_counts'],violation_slots_by_reason=r['q50_violation_slots_by_reason'],
                first_violation=r['q50_first_violation']) for r in evaluated],rejected=rejected))
        if reserve and selected['action'] in ('START','DELAY','PREPLACE'):
            metadata['additional_start_delay_seconds']=max(float(metadata.get('additional_start_delay_seconds',0)),selected['additional_start_delay_seconds'])
            self.references[metadata['uid']]['selected_due_seconds']=selected['start_seconds']
        self.last_selection[metadata['uid']]=deepcopy(selected);self.times.append(time.perf_counter()-began)
        return selected

    def _terminal(self,metadata,now,action,status,reason):
        selected=dict(uid=metadata['uid'],action=action,status=status,reason=reason,
            policy_sha=self.sha,physical_or_Q50_veto=action=='QUEUE',grid_safety_guaranteed=False,
            online_grid_horizon_evaluations=0,online_global_optimizer_calls=0)
        self.last_selection[metadata['uid']]=deepcopy(selected)
        self.audit.append(dict(uid=metadata['uid'],time_seconds=now,state=metadata.get('state'),
            generated=0,physically_and_grid_evaluated=0,signed_packet_evaluation_calls=0,
            candidate_limit=self.max_candidates,candidates_truncated=0,q50_hard_pass=0,
            approved=0,selected_action=action,selected_candidate=None,q50_scores=[],
            rejected=[dict(reason=reason)],terminal_status=status))
        return selected

    def _execution_reference(self,metadata,now,reservations):
        uid=metadata['uid'];ref=self.references.get(uid)
        if ref is not None and now>=ref['reference_start_seconds']:
            earlier=self.observed_blocks.get(uid)
            earlier_applies=earlier is not None and earlier['old_reference_start_seconds']==ref['reference_start_seconds']
            selected_due=ref.get('selected_due_seconds',ref['reference_start_seconds'])
            latest=ref['reference_start_seconds']+self.qos.receipts[uid].budget_seconds-ref['intentional_burden_at_reference_seconds']-float(metadata.get('cumulative_migration_interruption_seconds',0))
            new_proof_due=(now==ref['reference_start_seconds'] or now==selected_due) and now<=latest
            if not new_proof_due and not earlier_applies:
                # This branch cannot advance R0 or write a proof. In particular,
                # later current blockage cannot excuse an expired policy wait.
                return ref['reference_start_seconds'],ref['site']
            # Record a blockage only from observations at the contractual due
            # clock. A future affine score or unsupported lookup cannot move R0.
            service=max(float(metadata.get('experimental_prediction_Q50_seconds',metadata['t50_seconds'])),1e-9)
            segment=[dict(resource='gpu:'+ref['site'],begin=now,end=now+service,quantity=metadata['gpu'])]
            physical=reservations.feasible(segment,exclude=uid)
            instantaneous=self._instantaneous(metadata,segment,now)
            caps=np.array([self.packet.capacities[s] for s in self.packet.sites])
            if np.any(instantaneous>caps+1e-8):physical='CURRENT_INSTANTANEOUS_WHOLE_GANG_CAPACITY'
            slot=int((now-self.packet.begin_seconds)//900)
            violations=[]
            if 0<=slot<96:
                _,violations=self.packet._at_slot(slot,instantaneous-(self.packet.known_gpu+self.frozen_anonymous)[slot])
            # A nominal future booking collision is not evidence of current
            # observed GPU shortage. Require current gang occupancy for GPU.
            current_resource_block=physical and (not physical.startswith('NO_CAPACITY') or np.any(instantaneous>caps+1e-8))
            if (new_proof_due and (current_resource_block or violations)) or earlier_applies:
                reason=physical if current_resource_block else 'CURRENT_OBSERVED_ORIGINAL_GRID_HARD'
                proof=earlier if not new_proof_due else dict(observed_at_seconds=float(now),old_reference_start_seconds=ref['reference_start_seconds'],
                    reason=reason,observed_GPU=deepcopy(self.context['observed_gpu']),
                    original_grid_violations=violations,public_resource_sha=digest(self.context['observed_gpu']))
                self.observed_blocks[uid]=proof
                if now>ref['reference_start_seconds']:
                    base,site=self._causal_reference(metadata,now,reservations)
                    if base is not None:
                        old=deepcopy(ref)
                        ref=self._freeze_reference(metadata,base,site,now,first=old['first_reference_start_seconds'])
                        self.reference_audit.append(dict(uid=uid,event='OBSERVED_PHYSICAL_REFERENCE_ADVANCE',
                            old_reference_start_seconds=old['reference_start_seconds'],new_reference_start_seconds=base,
                            proof=proof,immutable_budget_renewed=False,intentional_spend_refunded=False,
                            wait_class='GRID_REQUIRED_WAIT' if proof['original_grid_violations'] else 'OBSERVED_PHYSICAL_RESOURCE_WAIT'))
                        self.observed_blocks.pop(uid,None)
                        if base==now:
                            # Preserve a continuous observed blockage chain at
                            # the newly due reference. This re-entry can record
                            # a proof, but cannot advance again at the same clock.
                            return self._execution_reference(metadata,now,reservations)
        if ref is None:
            base,site=self._causal_reference(metadata,now,reservations)
            if base is None:return None,None
            ref=self._freeze_reference(metadata,base,site,now,first=base)
            return self._execution_reference(metadata,now,reservations)
        return ref['reference_start_seconds'],ref['site']

    def _freeze_reference(self,metadata,base,site,now,*,first):
        ref=dict(first_reference_start_seconds=float(first),reference_start_seconds=float(base),site=site,
            intentional_burden_at_reference_seconds=float(metadata.get('additional_start_delay_seconds',0)),
            proof=dict(kind='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',uid=metadata['uid'],
                observed_at_seconds=float(now),reference_start_seconds=float(base),
                observed_resource_sha=digest(self.context['observed_gpu'])))
        self.references[metadata['uid']]=ref
        self.reference_audit.append(dict(uid=metadata['uid'],event='CAUSAL_REFERENCE_FROZEN',**deepcopy(ref)))
        return ref

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        base,site=self._execution_reference(metadata,now,reservations)
        if base is None:return self._terminal(metadata,now,'QUEUE','NO_PHYSICAL_CAUSAL_REFERENCE','NO_CAPACITY')
        window=self._receipt_window(metadata,receipt,base,now);variants=[]
        service=max(float(metadata.get('experimental_prediction_Q50_seconds',metadata['t50_seconds'])),1e-9)
        destinations=[site]
        if metadata.get('Can_Preplace') is True:destinations=sorted(metadata['compatible_sites'])
        for start in window['allowed_starts_seconds']:
            if start<base:continue
            delta=start-base
            if delta>0 and metadata.get('Can_TimeShift') is not True:continue
            for dest in destinations:
                if dest!=site and metadata.get('Can_Preplace') is not True:continue
                action='PREPLACE' if dest!=site else 'DELAY' if delta else 'START'
                variants.append(dict(action=action,policy_action='PREPLACE' if dest!=site else 'DELAY_'+str(int(delta/60)) if delta else 'START_NOW',
                    site=dest,start_seconds=start,nominal_end_seconds=start+service,
                    additional_start_delay_seconds=max(metadata.get('additional_start_delay_seconds',0),
                        self.references[metadata['uid']]['intentional_burden_at_reference_seconds']+delta),
                    intentional_burden_seconds=max(metadata.get('additional_start_delay_seconds',0),
                        self.references[metadata['uid']]['intentional_burden_at_reference_seconds']+delta)+
                        metadata.get('cumulative_migration_interruption_seconds',0),
                    causal_reference_start_seconds=base,original_reference_start_seconds=window['original_reference_start_seconds'],
                    execution_window_receipt=window,reference_action=dest==site and delta==0,
                    current_slot_candidate_GPU=metadata['gpu'] if start<now+900 else 0,
                    reference_segments=[dict(resource='gpu:'+site,begin=base,end=base+service,quantity=metadata['gpu'])],
                    segments=[dict(resource='gpu:'+dest,begin=start,end=start+service,quantity=metadata['gpu'])]))
        if not variants:return self._terminal(metadata,now,'QUEUE','EMPTY_EXPERIMENTAL_EXECUTION_WINDOW','SOURCE_HARD_WINDOW_OR_SHARED_BUDGET_EXHAUSTED')
        return self._choose(metadata,receipt,now,reservations,variants,reserve=reserve)

    def select_migration(self,metadata,receipt,now,reservations,*,checkpoint_at=None,reserve=True):
        if metadata.get('Can_Checkpoint_Migrate') is not True or (not metadata.get('migration_capability') and not self.migration_authority):
            return self._terminal(metadata,now,'STAY','NO_EXPERIMENTAL_PHYSICAL_MIGRATION_AUTHORITY','EXPLICIT_NONZERO_PHYSICAL_PACKET_REQUIRED')
        remaining=metadata['t50_seconds']-metadata.get('accumulated_compute_seconds',0)
        if remaining<=0:return self._terminal(metadata,now,'STAY','Q50_OVERRUN','Q50_OVERRUN_NO_NOMINAL_MIGRATION_ENVELOPE')
        current=metadata['current_site']
        retained=deepcopy(reservations.reservations.get(metadata['uid'],{}).get('segments',[]))
        if not retained:raise ValueError('OBSERVED_RUNNING_RESERVATION_REQUIRED')
        variants=[dict(action='STAY',policy_action='STAY',site=current,segments=retained,replace=True,
            reference_segments=deepcopy(retained),
            reference_action=True,additional_start_delay_seconds=metadata.get('additional_start_delay_seconds',0))]
        variants[0]['intentional_burden_seconds']=metadata.get('additional_start_delay_seconds',0)+metadata.get('cumulative_migration_interruption_seconds',0)
        for site in sorted(metadata['compatible_sites']):
            if site==current:continue
            candidate_metadata=metadata
            cap=metadata.get('migration_capability')
            if not cap and self.migration_authority:
                authority=self.migration_authority
                routes=[(route,row) for route,row in authority['routes'].items()
                    if row['source']==current and row['destination']==site]
                if len(routes)!=1 or self._rack_reason(metadata,site):continue
                route,row=routes[0]
                cap=dict(source_sha=authority['packet_source_sha'],checkpoint_authorized=True,
                    allowed_destinations=[site],gpu_type_confirmed=True,rack_gang_confirmed=True,
                    data_residency_confirmed=metadata.get('data_residency_confirmed') is not False,
                    wan_path=route,bandwidth_bytes_per_second=row['bandwidth_bytes_per_second'],
                    payload_bytes=authority['scalar']['bytes_per_GPU']*metadata['gpu'],
                    restart_seconds=authority['scalar']['current_conservative_restart_seconds'],source_wait_seconds=0,
                    source_hold_until=authority['protocol']['source_hold_until'],
                    destination_hold_from=authority['protocol']['destination_hold_from'],assumption=True,
                    assumption_class='ASSUMED_CHECKPOINTABLE_AND_HOLD_PROTOCOL_FOR_EXPERIMENT',
                    route_links=row['links'],measured_Kestrel_capability=False,
                    capability_confirmation_basis='FROZEN_MODEL_COMPATIBILITY_AND_EXPLICIT_EXPERIMENTAL_RIGHTS')
                candidate_metadata=dict(metadata,migration_capability=cap)
            migration,reason=migration_guard(candidate_metadata,receipt,now=now,
                accumulated_compute_seconds=metadata['accumulated_compute_seconds'],destination=site,
                remaining_nominal_seconds=remaining,reservations=reservations,checkpoint_at=checkpoint_at)
            if migration is None:continue
            if self.migration_authority and cap.get('route_links'):
                links=cap['route_links'];a=migration['times']['transfer_start'];b=migration['times']['transfer_end']
                migration['segments'].extend(dict(resource='wan:LINK::'+link,begin=a,end=b,
                    quantity=cap['bandwidth_bytes_per_second']) for link in links)
                reason=reservations.feasible(migration['segments'],exclude=metadata['uid'])
                if reason:continue
                migration['WAN_payload_bytes_on_each_ordered_link']={link:cap['payload_bytes'] for link in links}
                migration['WAN_reservation_bytes_on_each_link']=cap['bandwidth_bytes_per_second']*(b-a)
                migration['request_capability_is_observed_Kestrel']=False
                migration['post96_AC_certified']=False
            migration['migration_capability_packet']=deepcopy(cap)
            variants.append(dict(action='CHECKPOINT_MIGRATE',policy_action='CHECKPOINT_MIGRATE',site=site,
                segments=migration['segments'],reference_segments=deepcopy(retained),migration=migration,replace=True,reference_action=False,
                additional_start_delay_seconds=metadata.get('additional_start_delay_seconds',0),
                migration_interruption_seconds=migration['interruption_seconds'],
                intentional_burden_seconds=metadata.get('additional_start_delay_seconds',0)+
                    metadata.get('cumulative_migration_interruption_seconds',0)+migration['interruption_seconds']))
        selected=self._choose(metadata,receipt,now,reservations,variants,reserve=reserve)
        if selected['action']=='CHECKPOINT_MIGRATE' and reserve:
            metadata['migration_capability']=deepcopy(selected['migration']['migration_capability_packet'])
        return selected
