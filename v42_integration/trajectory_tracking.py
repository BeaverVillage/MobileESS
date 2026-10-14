"""Observed-job aggregate trajectory tracking; explicit online greedy contract.

This is not Hall et al.'s class-specific Y* or a DRO guarantee. No optimizer,
future request bank, realized runtime or Frozen lookup table is available here.
"""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import math
import json
import numpy as np

from .actual import JobEventController, _require_public_metadata
from .experimental_actual import ExperimentalJobEventController
from .policy import digest, _receipt, migration_guard
from .reservation_state import ContractReservationLedger, union_job_segments
from .frozen_unknown import _migration_capability

MODE = 'CAUSAL_JOB_TRACKING'
CONTRACT = 'OBSERVED_JOB_AGGREGATE_GREEDY_TRACKING_V1'


def require_tracking_public(value):
    _require_public_metadata(value)
    if isinstance(value,dict):
        if {'future_job_uid','future_unknown_uids','actual_duration_seconds','completion_time'} & value.keys():
            raise ValueError('PRIVATE_REALIZATION_IN_TRACKING_METADATA')
        for child in value.values(): require_tracking_public(child)
    elif isinstance(value,(list,tuple)):
        for child in value: require_tracking_public(child)


def service_integral(sites, segments, begin):
    """GPU occupancy averaged over each 900s slot; sum/4 is nominal GPUh."""
    out = np.zeros((96, len(sites)))
    for seg in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
        site = seg['resource'][4:]
        a, b = seg['begin']-begin, seg['end']-begin
        for t in range(max(0, int(a//900)), min(96, int(math.ceil(b/900)))):
            overlap = max(0., min(b, (t+1)*900)-max(a, t*900))
            out[t, sites.index(site)] += seg['quantity']*overlap/900
    return out


class TrackingReference:
    def __init__(self, known, unknown, it, p, q, *, sites, begin, commands, identity):
        self.sites = tuple(sites); self.begin = float(begin)
        self._commands = deepcopy(commands); self.identity = deepcopy(identity)
        self.arrays = {}
        for name, value in dict(G_Known_Plan=known, G_Unknown_Q50_Plan=unknown,
                                IT_Plan=it, PCC_P_Plan=p, PCC_Q_Plan=q).items():
            a = np.array(value, dtype=float, copy=True)
            if a.shape != (96, len(sites)) or not np.isfinite(a).all():
                raise ValueError('TRACKING_REFERENCE_FULL96_FINITE_AXIS')
            if name.startswith('G_') and np.any(a < 0):
                raise ValueError('NONNEGATIVE_GPU_TARGET')
            a.setflags(write=False); self.arrays[name] = a
        total = self.arrays['G_Known_Plan'] + self.arrays['G_Unknown_Q50_Plan']
        total.setflags(write=False); self.arrays['G_Total_Plan'] = total
        self.sha = self._digest()

    @property
    def commands(self): return deepcopy(self._commands)

    def _digest(self):
        return digest(dict(arrays={k:a.tolist() for k,a in self.arrays.items()},
                           commands=self._commands, sites=self.sites, begin=self.begin,
                           identity=self.identity))

    def require_immutable(self):
        if self._digest() != self.sha: raise ValueError('PLANNING_TARGET_SHA_DRIFT')

    def save(self, path):
        self.require_immutable()
        extras={}
        for name in ('CC4_Q50','CC4_Q90','Timing_CDF_Q10','Timing_CDF_Q90'):
            if name in self.identity: extras[name]=np.asarray(self.identity[name],float)
        np.savez_compressed(Path(path), **self.arrays, sites=np.asarray(self.sites),
                            begin_seconds=self.begin, target_sha=self.sha,**extras,
                            Known_UID_Schedule_JSON=json.dumps(self._commands,sort_keys=True),
                            Nominal_Service_Carry_JSON=json.dumps({k:self.identity[k] for k in
                                ('CC4_service','CC4_carryout') if k in self.identity},sort_keys=True))


class TrajectoryTrackingPolicy:
    """Own explicit policy contract; lookup_only remains False."""
    lookup_only = False
    controller_contract = CONTRACT
    execution_mode = MODE

    def __init__(self, reference, packet, *, bindings, migration_authority=None,
                 preplace=True, basic=False, grid_lookahead_slots=16):
        reference.require_immutable()
        if tuple(packet.sites) != reference.sites or packet.begin_seconds != reference.begin:
            raise ValueError('TRACKING_GRID_TARGET_AXIS_DRIFT')
        if packet.bindings != bindings: raise ValueError('TRACKING_GRID_BINDINGS_DRIFT')
        self.reference = reference; self.packet = packet; self.bindings = dict(bindings)
        self.migration_authority = deepcopy(migration_authority)
        self.preplace = preplace; self.basic = basic
        self.grid_lookahead_slots = grid_lookahead_slots
        self.spec = dict(contract=CONTRACT, mode=MODE, target_sha=reference.sha,
            preplace=preplace, basic=basic, lookup_only=False,
            ranking=['HARD_FEASIBILITY', 'AGGREGATE_SHARE_DEFICIT', 'GRID_PEAK',
                     'CRITICAL_LINE_LOADING_HOURS', 'Q90_RUNTIME_CARRY_RISK', 'BURDEN'],
            first_assignment_share='ZERO', nominal_volume='GPU*Q50_seconds/3600',
            job_Q90_source='PUBLIC_SOURCE_ONLY;UNAVAILABLE=NULL;AGGREGATE_CC4_Q90_SEPARATE',
            tracking_scope='AGGREGATE_FULL96_SITE_TIME_GPU_SERVICE_NOT_CLASS_SPECIFIC_Y_STAR',
            grid_lookahead_slots=grid_lookahead_slots, global_optimizer_calls=0,
            Event30='OBSERVED_JOB_EVENT_TRACKING;SOURCE_TRIGGER_UNDEFINED', bindings=self.bindings,
            migration_authority_sha=None if migration_authority is None else digest(migration_authority))
        self.sha = digest(self.spec)
        self.assignments = {}; self.audit = []; self.funnel = []; self.times = []
        self.current = None; self.metadata = {}; self.last_selection = {}
        self._known_segments={u:c['protected_segments'] for u,c in reference.commands.items() if c.get('protected_segments')}
        self._known_profiles={u:service_integral(packet.sites,rows,reference.begin)
                              for u,rows in self._known_segments.items()}

    def require_bindings(self, expected):
        if expected != self.bindings: raise ValueError('TRACKING_BINDINGS_DRIFT')
        if digest(self.spec) != self.sha: raise ValueError('TRACKING_POLICY_SHA_DRIFT')
        self.reference.require_immutable()

    def observe(self, now, use, metadata):
        self.current = (float(now), dict(use)); self.metadata = metadata
        # Initial Running unknowns are already observed public episodes.
        for uid,m in metadata.items():
            if m['origin_unknown'] and m['state'] == 'RUNNING' and uid not in self.assignments:
                remaining = max(0., m['t50_seconds']-m.get('accumulated_compute_seconds',0))
                self.assignments[uid] = service_integral(self.packet.sites, [dict(
                    resource='gpu:'+m['current_site'], begin=now, end=now+remaining,
                    quantity=m['gpu'])], self.reference.begin)/4

    def current_guard(self, metadata, segments, now, observed):
        slot = int((now-self.reference.begin)//900)
        if not 0 <= slot < 96: return 'CURRENT_GRID_SLOT_UNSUPPORTED'
        instant = np.array([observed[s] for s in self.packet.sites],float)
        if metadata.get('state') == 'RUNNING':
            instant[self.packet.sites.index(metadata['current_site'])] -= metadata['gpu']
        for seg in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            site = seg['resource'][4:]
            if metadata['gpu'] > max(self.packet.rack_compatibility[site]): return 'RACK_GANG_INCOMPATIBLE'
            if seg['begin'] <= now < seg['end']: instant[self.packet.sites.index(site)] += seg['quantity']
        if np.any(instant > np.array([self.packet.capacities[s] for s in self.packet.sites])+1e-9):
            return 'GPU_CAPACITY'
        _, violations = self.packet._at_slot(slot, instant-self.reference.arrays['G_Total_Plan'][slot])
        return None if not violations else 'CURRENT_OBSERVED_'+violations[0]['reason']

    def _public_future(self, reservations, exclude):
        """Known + committed + Running public Q50; per-UID union prevents duplicates."""
        total = np.zeros_like(self.reference.arrays['G_Total_Plan']); known = total.copy()
        uids = set(reservations.reservations) | set(getattr(reservations,'known_plans',{}))
        for uid in uids:
            if uid == exclude: continue
            booking = reservations.reservations.get(uid,{})
            rows = [] if booking.get('status') == 'RELEASED' else booking.get('segments',[])
            plans=getattr(reservations,'known_plans',{}).get(uid,[])
            m = self.metadata.get(uid,{})
            if not rows and m.get('state')!='RUNNING' and uid in self._known_profiles and plans==self._known_segments[uid]:
                total+=self._known_profiles[uid];known+=self._known_profiles[uid]
                continue
            rows = rows + plans
            if m.get('state') == 'RUNNING':
                remaining = max(0.,m['t50_seconds']-m.get('accumulated_compute_seconds',0))
                rows = rows + [dict(resource='gpu:'+m['current_site'],begin=self.current[0],
                                    end=self.current[0]+remaining,quantity=m['gpu'])]
            profile = service_integral(self.packet.sites,rows,self.reference.begin)
            total += profile
            if uid in getattr(reservations,'known_plans',{}) or m.get('origin_unknown') is False:
                known += profile
        slot = int((self.current[0]-self.reference.begin)//900)
        if 0 <= slot < 96:
            # Physical truth applies at the current instant; average predictions
            # are not permission to evict an observed gang.
            total[slot] = np.maximum(total[slot], [self.current[1][s]-(
                self.metadata.get(exclude,{}).get('gpu',0) if self.metadata.get(exclude,{}).get('state')=='RUNNING'
                and self.metadata[exclude]['current_site']==s else 0) for s in self.packet.sites])
        return total, known

    def _score(self, metadata, segments, now, baseline, assigned, *, service_segments=None):
        profile = service_integral(self.packet.sites,segments,self.reference.begin)
        service_profile = profile if service_segments is None else service_integral(
            self.packet.sites,service_segments,self.reference.begin)
        volume = service_profile.sum()/4
        target = self.reference.arrays['G_Unknown_Q50_Plan']/4
        target_share = target/target.sum() if target.sum() else np.zeros_like(target)
        assigned_share = assigned/assigned.sum() if assigned.sum() else np.zeros_like(assigned)
        deficit = float(np.sum((target_share-assigned_share)*(service_profile/4))/volume) if volume else 0.
        slot = int((now-self.reference.begin)//900)
        touched = [t for t in range(max(0,slot), min(96,slot+self.grid_lookahead_slots)) if np.any(profile[t])]
        peaks = []; violations = []
        for t in touched:
            gpu = baseline[t]+profile[t]
            if np.any(gpu > [self.packet.capacities[s]+1e-9 for s in self.packet.sites]):
                return None, 'PREDICTED_COMMITTED_GPU_CAPACITY'
            peak, bad = self.packet._at_slot(t,gpu-self.reference.arrays['G_Total_Plan'][t])
            peaks.append(peak); violations.extend(bad)
        if violations: return None, 'Q50_'+violations[0]['reason']
        estimate = baseline+profile
        error_gpu = float(np.abs(estimate-self.reference.arrays['G_Total_Plan']).sum()*.25)
        # Affine planning endpoint model in kWh, separately from GPUh.
        error_p = float(np.sum(np.abs(estimate-self.reference.arrays['G_Total_Plan'])*self.packet.p_slope)*.25)
        carry = sum(s['quantity']*max(0,s['end']-max(s['begin'],self.reference.begin+86400))/3600
                    for s in segments if s['resource'].startswith('gpu:'))
        q90=metadata.get('experimental_prediction_Q90_seconds')
        risk = max(0.,float(metadata['t50_seconds'] if q90 is None else q90)
                   -metadata['t50_seconds'])*metadata['gpu']/3600 + carry
        return dict(deficit=deficit, grid_peak=max(peaks,default=0.),
                    loading_hours=sum(peaks)*.25, risk_GPUh=risk,
                    GPU_error_GPUh=error_gpu, P_error_kWh=error_p,
                    Job_Q90_seconds=q90,Job_Q90_available=q90 is not None,
                    checked_grid_slots=len(touched), profile=profile,service_profile=service_profile), None

    def _record(self, metadata, now, decision, began, candidates, rejected):
        elapsed = perf_counter()-began; self.times.append(elapsed)
        decision.update(uid=metadata['uid'],policy_sha=self.sha,online_global_optimizer_calls=0,
                        execution_mode=MODE,controller_contract=CONTRACT,
                        candidate_count=candidates,decision_seconds=elapsed,rejected_candidates=rejected)
        self.last_selection[metadata['uid']] = deepcopy(decision)
        self.audit.append(dict(uid=metadata['uid'],time_seconds=now,state=metadata['state'],
                               decision=deepcopy(decision)))
        return decision

    def select(self, metadata, receipt, now, reservations, *, reserve=True):
        began = perf_counter(); require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True: raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_TRACKER')
        if not metadata.get('is_observed',True) or metadata['submit_seconds'] > now:
            return self._record(metadata,now,dict(action='QUEUE',status='OBSERVATION_REQUIRED'),began,0,[])
        if self.current is None or self.current[0] != now: raise ValueError('CURRENT_OBSERVATION_REQUIRED')
        r = _receipt(receipt); rejected = []; rows = []; count = 0
        baseline, known = self._public_future(reservations,metadata['uid'])
        assigned = sum((a for u,a in self.assignments.items() if u!=metadata['uid']),
                       np.zeros_like(baseline))
        source = metadata.get('reference_site',metadata.get('source_site'))
        origin = math.ceil(max(now,r['reference_start_seconds'],metadata.get('release_seconds') or -math.inf,
                               metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        sites = sorted(set(metadata['compatible_sites']))
        allowed = list(r['allowed_starts_seconds'])
        starts = sorted(set([origin]+[s for s in allowed if s >= now]))
        for site in sites:  # Every source-compatible site is audited, including authority vetoes.
            if site != source and (self.basic or not self.preplace or metadata.get('can_prestart_place') is not True):
                rejected.append(dict(site=site,reason='PREPLACE_SOURCE_AUTHORITY_OR_ABLATION')); continue
            for start in starts:
                count += 1; end = start+max(metadata['t50_seconds'],1e-9)
                spend = max(metadata.get('additional_start_delay_seconds',0), start-r['reference_start_seconds'],0)
                reason = None
                if self.basic and start != origin: continue
                # Queue at the original site after the authorized window is a
                # physical wait, not newly granted intentional flexibility.
                queue_only = site == source and start == origin and origin > r['latest_start_seconds']
                if not queue_only and start not in allowed: reason = 'SOURCE_START_WINDOW'
                if not queue_only and spend+metadata.get('cumulative_migration_interruption_seconds',0)>r['budget_seconds']+1e-9:
                    reason = 'SHARED_QOS_BUDGET'
                if start > origin and metadata.get('Can_TimeShift') is not True: reason='NO_TIME_SHIFT_AUTHORITY'
                if metadata['gpu'] > max(self.packet.rack_compatibility[site]): reason='RACK_GANG_INCOMPATIBLE'
                if any(metadata.get(k) is not None and v>metadata[k] for k,v in (
                        ('hard_latest_start_seconds',start),('completion_deadline_seconds',end))): reason='HARD_WINDOW'
                segments = [dict(resource='gpu:'+site,begin=start,end=end,quantity=metadata['gpu'])]
                if reason is None: reason = reservations.feasible(segments,exclude=metadata['uid'])
                if reason is None: reason = self.current_guard(metadata,segments,now,self.current[1])
                score = None
                if reason is None: score,reason = self._score(metadata,segments,now,baseline,assigned)
                if reason:
                    rejected.append(dict(site=site,start_seconds=start,reason=reason)); continue
                burden = metadata.get('additional_start_delay_seconds',0) if queue_only else spend
                key = (0. if self.basic else -round(score['deficit'],12),round(score['grid_peak'],9),
                       score['loading_hours'],score['risk_GPUh'],burden,site,start)
                rows.append((key,dict(site=site,start_seconds=start,nominal_end_seconds=end,
                    segments=segments,additional_start_delay_seconds=burden,
                    action='PREPLACE' if site!=source else 'DELAY' if start>origin else 'START',
                    status='BASIC_SOURCE_ALLOCATION' if self.basic else 'GREEDY_TRACKING_SELECTED',
                    tracking={k:v for k,v in score.items() if k not in ('profile','service_profile')},
                    residual_target_nonnegative=True,known_mismatch_GPUh=float(np.abs(
                        known-self.reference.arrays['G_Known_Plan']).sum()/4),
                    residual_target_GPUh=float(np.maximum(0,self.reference.arrays['G_Total_Plan']-known).sum()/4),
                    negative_residual_clamped_GPUh=float(np.maximum(0,known-self.reference.arrays['G_Total_Plan']).sum()/4),
                    unknown_prediction_mismatch_GPUh=float(np.abs(np.maximum(0,baseline-known)+score['profile']
                        -self.reference.arrays['G_Unknown_Q50_Plan']).sum()/4)),score['profile']/4))
        for _,row,profile in sorted(rows,key=lambda x:x[0]):
            if reserve:
                ok,reason = reservations.reserve(metadata['uid'],row['segments'],replace=True)
                if not ok: rejected.append(dict(site=row['site'],reason=reason)); continue
                metadata['additional_start_delay_seconds'] = max(metadata.get('additional_start_delay_seconds',0),row['additional_start_delay_seconds'])
                self.assignments[metadata['uid']] = profile
            return self._record(metadata,now,row,began,count,rejected)
        return self._record(metadata,now,dict(action='QUEUE',status='NO_HARD_FEASIBLE_TRACKING_ACTION',
                            reason=rejected[-1]['reason'] if rejected else 'NO_AUTHORIZED_ACTION'),began,count,rejected)

    def select_migration(self, metadata, receipt, now, reservations, *, checkpoint_at=None, reserve=True):
        began = perf_counter(); require_tracking_public(metadata); uid = metadata['uid']
        if metadata.get('origin_unknown') is not True: raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_TRACKER')
        rejected = []; stages = dict(RUNNING=metadata.get('state')=='RUNNING',CHECKPOINT=False,
            AUTHORITY=False,DESTINATION=False,REMAINING=False,WAN=False,GPU_RACK=False,BUDGET=False,
            SELECTED=False,COMPLETED=False)
        def stay(reason,count=0):
            self.funnel.append(dict(uid=uid,time_seconds=now,reason=reason,**stages))
            return self._record(metadata,now,dict(action='STAY',status=reason,reason=reason),began,count,rejected)
        if not stages['RUNNING'] or not metadata.get('is_observed',True) or metadata['submit_seconds']>now:
            return stay('NO_OBSERVED_RUNNING_AUTHORITY')
        elapsed = metadata.get('accumulated_compute_seconds',0)
        if elapsed<1800 or abs(elapsed%1800)>1e-7 or (checkpoint_at is not None and checkpoint_at>now):
            return stay('NOT_OBSERVED_EXECUTION_CHECKPOINT')
        stages['CHECKPOINT']=True
        if metadata.get('migration_count',0): return stay('MAXIMUM_ONE_MIGRATION')
        if self.basic or metadata.get('Can_Checkpoint_Migrate') is not True: return stay('NO_CHECKPOINT_SOURCE_AUTHORITY')
        stages['AUTHORITY']=True
        if metadata.get('tracking_first_checkpoint') is not None: return stay('FIRST_CHECKPOINT_ONLY')
        if reserve: metadata['tracking_first_checkpoint']=now
        remaining = max(0.,metadata['t50_seconds']-elapsed)
        baseline,known = self._public_future(reservations,uid)
        assigned = sum((a for u,a in self.assignments.items() if u!=uid),np.zeros_like(baseline))
        stay_segments = [dict(resource='gpu:'+metadata['current_site'],begin=now,end=now+remaining,quantity=metadata['gpu'])]
        stay_score,_ = self._score(metadata,stay_segments,now,baseline,assigned)
        rows = []; count = 0
        for destination in sorted(set(metadata['compatible_sites'])-{metadata['current_site']}):
            count += 1; stages['DESTINATION']=True
            if remaining<=0: rejected.append(dict(site=destination,reason='Q50_OVERRUN_NO_NOMINAL_MIGRATION_ENVELOPE'));continue
            stages['REMAINING']=True
            cap = deepcopy(metadata.get('migration_capability') or _migration_capability(
                self.migration_authority,metadata['current_site'],destination,metadata['gpu']))
            if not cap or cap.get('payload_bytes',0)<=0 or cap.get('restart_seconds',0)<=0:
                rejected.append(dict(site=destination,reason='NO_POSITIVE_SOURCE_TRANSFER_RESTART_AUTHORITY'));continue
            stages['WAN']=True
            m = dict(metadata,migration_capability=cap)
            migration,reason = migration_guard(m,receipt,now=now,accumulated_compute_seconds=elapsed,
                destination=destination,remaining_nominal_seconds=remaining,reservations=reservations,checkpoint_at=checkpoint_at)
            if migration is None: rejected.append(dict(site=destination,reason=reason));continue
            a,b=migration['times']['transfer_start'],migration['times']['transfer_end']
            migration['segments'].extend(dict(resource='wan:LINK::'+link,begin=a,end=b,
                quantity=cap['bandwidth_bytes_per_second']) for link in cap.get('route_links',[]))
            reason = reservations.feasible(migration['segments'],exclude=uid)
            if reason is None: reason=self.current_guard(metadata,migration['segments'],now,self.current[1])
            if reason: rejected.append(dict(site=destination,reason=reason));continue
            stages['GPU_RACK']=True;stages['BUDGET']=True
            computing_segments=[dict(resource='gpu:'+destination,begin=migration['times']['restart_end'],
                end=migration['times']['restart_end']+remaining,quantity=metadata['gpu'])]
            score,reason=self._score(metadata,migration['segments'],now,baseline,assigned,
                service_segments=computing_segments)
            if reason: rejected.append(dict(site=destination,reason=reason));continue
            key=lambda s,burden: (-round(s['deficit'],12),round(s['grid_peak'],9),s['loading_hours'],s['risk_GPUh'],burden)
            if stay_score is not None and key(score,migration['interruption_seconds'])>=key(stay_score,0):
                rejected.append(dict(site=destination,reason='STAY_TRACKING_GRID_RANK_PREFERRED'));continue
            rows.append((key(score,migration['interruption_seconds']),destination,cap,migration,score))
        for _,destination,cap,migration,score in sorted(rows,key=lambda x:(x[0],x[1])):
            if reserve:
                ok,reason=reservations.reserve(uid,migration['segments'],replace=True)
                if not ok: rejected.append(dict(site=destination,reason=reason));continue
                metadata['migration_capability']=cap
                # Preserve already assigned past volume; replace only future own placement.
                old=self.assignments.get(uid,np.zeros_like(baseline)).copy()
                fraction=np.clip((now-(self.reference.begin+np.arange(96)*900))/900,0,1)
                old*=fraction[:,None]
                self.assignments[uid]=old+score['service_profile']/4
            stages['SELECTED']=True;self.funnel.append(dict(uid=uid,time_seconds=now,reason='SELECTED',**stages))
            return self._record(metadata,now,dict(action='CHECKPOINT_MIGRATE',status='GREEDY_TRACKING_MIGRATION',
                migration=migration,tracking={k:v for k,v in score.items() if k not in ('profile','service_profile')}),began,count,rejected)
        return stay(rejected[-1]['reason'] if rejected else 'NO_DESTINATION',count)


class TrackingJobEventController(JobEventController):
    """Reuse original execution physics with a new, checked online policy type."""
    _overlay = ExperimentalJobEventController._overlay

    def __init__(self,*args,**kwargs):
        policy=kwargs.get('frozen_policy')
        if not isinstance(policy,TrajectoryTrackingPolicy) or policy.controller_contract!=CONTRACT or policy.lookup_only:
            raise ValueError('EXPLICIT_TRACKING_CONTROLLER_CONTRACT_REQUIRED')
        authority=policy.migration_authority or {}
        inherited=dict(kwargs.get('wan_capacities') or {})
        for key,value in authority.get('wan_capacities',{}).items():
            if key in inherited and inherited[key]!=value: raise ValueError('SOURCE_WAN_CAPACITY_DRIFT')
            inherited[key]=value
        kwargs['wan_capacities']=inherited
        super().__init__(*args,**kwargs)
        self.reservations=ContractReservationLedger(self,capacities=self.ledger.capacities,wan_capacities=inherited)
        self.frozen_known_sha=digest(self.known_schedule)

    def submit(self,request,now):
        if request.uid not in self.qos.contexts:
            self.qos.register_observed(request.uid,episode_id=request.metadata.get('experimental_participation_episode_id'),
                source_authority=request.metadata.get('source_qos_authority'))
        super().submit(request,now);self._overlay(request.uid,self.observed[request.uid].state)
        self.metadata[request.uid]['experimental_prediction_Q50_seconds']=request.q50
        if request.uid in self.known_schedule and request.uid not in self.reservations.known_plans:
            command=self.known_schedule[request.uid]
            if command['start_seconds']>=self.policy.reference.begin:
                self.reservations.install_known(request.uid,[dict(resource='gpu:'+command['site'],
                    begin=command['start_seconds'],end=command['start_seconds']+max(request.q50,1e-9),quantity=request.gpu)])

    def _policy_resource_guard(self,now,*,lookup_at=None,observed_use=None):
        self.policy.observe(now,self.ledger.physical(now) if observed_use is None else observed_use,self.metadata)
        return None,dict(observed_at_seconds=now,controller_contract=CONTRACT,grid_safety_guaranteed=False)

    def admit(self,now):
        if digest(self.known_schedule)!=self.frozen_known_sha:raise ValueError('KNOWN_SCHEDULE_DRIFT')
        if now%900==0:
            self.policy.require_bindings(self.policy.bindings)
            for _,uid in sorted(self.pending):
                if not self.metadata[uid]['origin_unknown']:continue
                decision=self.decisions.get(uid)
                if not decision or decision['action']=='QUEUE' or decision['start_seconds']>now:continue
                m=self.metadata[uid];use=self.ledger.physical(now)
                segments=[dict(resource='gpu:'+decision['site'],begin=now,end=now+max(self.requests[uid].q50,1e-9),quantity=m['gpu'])]
                reason=self.policy.current_guard(m,segments,now,use)
                if reason is None:reason=self.reservations.feasible(segments,exclude=uid)
                if reason:
                    m['additional_start_delay_seconds']=max(m.get('additional_start_delay_seconds',0),decision.get('additional_start_delay_seconds',0))
                    self.reservations.release(uid,now)
                    self.decisions[uid]=dict(uid=uid,action='QUEUE',status='TRACKING_REVALIDATION_REQUIRED',reason=reason)
                    self._event(uid,now,'TRACKING_COMMAND_CURRENT_GUARD_FAILED',reason=reason,QoS_budget_refunded=False)
        return super().admit(now)

    def migration(self,uid,now,physical_checkpoint):
        self._overlay(uid,'RUNNING')
        return super().migration(uid,now,physical_checkpoint)

    def snapshot(self,now):
        result=super().snapshot(now)
        result['tracking_state']=dict(contract=CONTRACT,target_sha=self.policy.reference.sha,
            Known_schedule_sha=self.frozen_known_sha,online_global_optimizer_calls=0,
            assignments_GPUh={u:a.tolist() for u,a in self.policy.assignments.items()})
        return result

    def restore(self,snapshot):
        raise ValueError('TRACKING_CONTINUATION_REQUIRES_SEPARATE_FULL96_PACKAGE')
