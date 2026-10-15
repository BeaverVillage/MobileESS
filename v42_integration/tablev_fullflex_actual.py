"""Additive Table V E1/FLEX30 workload control, using original service/physics.

Planning commands are immutable. Only public observations, the existing E1
budget and existing R1/checkpoint/WAN contracts enter event decisions. R2 is
held. Conditional Q50 AC is a prediction, never an Actual state certificate.
"""
from copy import deepcopy
from dataclasses import fields
import gzip
import heapq
import json
import math
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import numpy as np

from .actual import JobEventController,run_actual
from .aidc_sensitivity_runtime import (CurrentEventJobEventController,CurrentEventReservationLedger,
    CurrentEventSensitivityPolicy,SignedSensitivityPolicy,safe_backfill,_bind_driver_current_c1)
from .experimental_actual import ExperimentalJobEventController
from .experimental_policy import ExperimentalControlPolicy
from .experimental_qos import ExperimentalQoSProvider
from .frozen_unknown import _migration_capability
from .release_production_actual import ProductionCurrentController,ProductionResearchPolicy,_resource_bridge,_physical_packet
from .release_date_ac import DateResearchCurrentAC
from .release_actual import initial_authority
from .policy import digest,_receipt,migration_guard
from .policy import ReservationLedger
from .reservation_state import union_job_segments
from .qos import ObservedJob
from .m_engine import _write,file_record
from .table_v_dates import context_day


class StreamingAudit:
    """Lossless append, with no retained copy of candidate/prefix receipts."""
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():raise FileExistsError('TABLE_V_AUDIT_MUST_NOT_OVERWRITE')
        self.path.touch(exist_ok=False);self.count=0
    def append(self,value):
        payload=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        with self.path.open('a',encoding='utf-8') as stream:stream.write(payload+'\n')
        self.count+=1
    def __len__(self):return self.count
    def receipt(self):return dict(format='LOSSLESS_JSONL_APPEND',count=self.count,record=file_record(self.path))


class PhysicalProofStore:
    """Content-addressed lossless evidence; scores never depend on storage."""
    def __init__(self,folder):self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
    def save(self,value):
        sha=digest(value);path=self.folder/(sha+'.json.gz')
        if not path.exists():
            encoded=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
            path.write_bytes(gzip.compress(encoded,mtime=0))
        if digest(json.loads(gzip.decompress(path.read_bytes())))!=sha:
            raise ValueError('TABLE_V_PHYSICAL_PROOF_LOSSLESS_ROUNDTRIP_FAILED')
        return dict(semantic_sha=sha,record=file_record(path),format='LOSSLESS_GZIP_JSON')


def _union(intervals):
    merged=[]
    for left,right in sorted(intervals):
        if right<=left:continue
        if merged and left<=merged[-1][1]:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
        else:merged.append((left,right))
    return merged


def observed_gpu_intervals(controller,uid,now):
    """Committed physical GPU phases only, clipped at the observation watermark."""
    job=controller.ledger.jobs[uid];start=job.get('start_time')
    if start is None:return {}
    finish=job.get('completion_observed_time')
    if finish is not None and finish>now:raise ValueError('TABLE_V_FUTURE_COMPLETION_IN_PUBLIC_LEDGER')
    finish=now if finish is None else finish
    migrations=[r for r in controller.migrations if r.get('job_id')==uid]
    if len(migrations)>1:raise ValueError('TABLE_V_ORIGINAL_ONE_MIGRATION_LIMIT')
    intervals={}
    def add(site,left,right):
        left=max(start,left);right=min(finish,now,right)
        if right>left:intervals.setdefault(site,[]).append((left,right))
    if not migrations:add(job['current_site'],start,finish)
    else:
        receipt=migrations[0];checkpoint=receipt['physical_checkpoint_seconds'];restart=receipt['times']['restart_end']
        if checkpoint>now:raise ValueError('TABLE_V_UNOBSERVED_CHECKPOINT_IN_COMMITTED_LEDGER')
        add(receipt['source'],start,checkpoint)
        for row in receipt['segments']:
            if row['resource'].startswith('gpu:'):
                if row['quantity']!=controller.requests[uid].gpu:raise ValueError('TABLE_V_MIGRATION_GANG_DRIFT')
                add(row['resource'][4:],max(checkpoint,row['begin']),min(restart,row['end']))
        add(receipt['destination'],restart,finish)
    return {s:_union(rows) for s,rows in intervals.items()}


def completed_migration_prefix(controller,now):
    """Same occupation integral as original Actual, including double-hold phases."""
    oracle=controller.policy.oracle;sites=oracle.sites;count=int((now-oracle.begin)//900);rows=[]
    public={uid:observed_gpu_intervals(controller,uid,now) for uid in controller.ledger.jobs}
    for slot in range(count):
        begin=oracle.begin+slot*900;end=begin+900;gpu=np.zeros(len(sites))
        for uid,by_site in public.items():
            for site,intervals in by_site.items():
                gpu[sites.index(site)]+=controller.requests[uid].gpu*sum(
                    max(0.,min(end,right)-max(begin,left)) for left,right in intervals)/900
        obs=oracle.observations.at(begin,observed_now=now)
        physical=oracle.model.recompute(gpu[None,:],sites,[obs['weather']['values']])
        rows.append(dict(slot=slot,start_seconds=begin,end_seconds=end,GPU=gpu.tolist(),
            P=physical['PCC_P_kw'][0].tolist(),Q=physical['PCC_Q_kvar'][0].tolist(),observations=obs,
            authority='OBSERVED_COMMITTED_EPISODE_AND_MIGRATION_PHASE_UNION_INTEGRAL'))
    return rows


class TableVReservationLedger(CurrentEventReservationLedger):
    def _fits(self,segments,*,exclude=None,envelope=None,scope='physical'):
        reason=super()._fits(segments,exclude=exclude,envelope=envelope,scope=scope)
        if reason:return reason
        non_gpu=[r for r in segments if not r['resource'].startswith('gpu:')]
        if not non_gpu:return None
        # Existing frozen Known WAN/transfer commitments remain temporal.
        # Their GPU forecasts do not become future admission vetoes.
        peers={}
        for uid in set(self.reservations)|set(self.known_plans):
            if uid==exclude:continue
            booked=self.reservations.get(uid,{})
            active=[] if booked.get('status')=='RELEASED' else booked.get('segments',[])
            rows=[r for r in active+self.known_plans.get(uid,[]) if not r['resource'].startswith('gpu:')]
            if rows:peers[uid]=dict(status='ACTIVE',segments=union_job_segments(rows))
        return ReservationLedger._fits(SimpleNamespace(capacities=self.capacities,reservations=peers),
            non_gpu,exclude=None,envelope=None,scope=scope)

    def current_gpu_use(self,now,*,exclude=None):
        use=super().current_gpu_use(now,exclude=None)
        if exclude is None:return use
        job=self.owner.ledger.jobs.get(exclude,{})
        if job.get('latest_observed_state')=='RUNNING':
            migration=self.owner.ledger.in_flight.get(exclude)
            if migration:
                active={r['resource'][4:]:r['quantity'] for r in migration['segments']
                    if r['resource'].startswith('gpu:') and r['begin']<=now<r['end']}
                for site,gpu in active.items():use[site]-=gpu
            else:use[job['current_site']]-=job['gpu']
        elif self.owner.metadata.get(exclude,{}).get('state')=='PENDING':
            booked=self.reservations.get(exclude,{})
            if booked.get('status')!='RELEASED':
                active={r['resource'][4:]:r['quantity'] for r in booked.get('segments',[])
                    if r['resource'].startswith('gpu:') and r['begin']<=now<r['end']}
                for site,gpu in active.items():use[site]-=gpu
        if any(v<0 for v in use.values()):raise ValueError('TABLE_V_NEGATIVE_CURRENT_GPU_UNION')
        return use


class TableVCurrentAC(DateResearchCurrentAC):
    """Existing conditional Original AC, with public migration-phase profiles."""
    def predicted_segments(self,now,metadata,segments,public_jobs,*,finish,replace_running=False):
        if now!=self.now:raise ValueError('TABLE_V_PREDICTION_CURRENT_WATERMARK_REQUIRED')
        if finish>self.begin+86400:
            return dict(status='NOT_CERTIFIED',reason='PUBLIC_Q50_TAIL_OUTSIDE_ORIGINAL_96_SUPPORT',
                current_hard_veto=False,tail_carry_certified=False)
        first=int((now-self.begin)//900);stop=min(96,max(first+1,math.ceil((finish-self.begin)/900)))
        obs=self.observations.at(now,observed_now=now);rows=[];owner=self.owner
        for slot in range(first,stop):
            left=self.begin+slot*900;right=left+900;gpu=np.zeros(len(self.sites))
            for uid,m in public_jobs.items():
                if m.get('state')!='RUNNING' or replace_running and uid==metadata['uid']:continue
                inflight=owner.ledger.in_flight.get(uid)
                if inflight:
                    if slot==first:
                        active={r['resource'][4:] for r in inflight['segments'] if r['resource'].startswith('gpu:')
                            and r['begin']<=now<r['end']}
                    else:
                        active={r['resource'][4:] for r in inflight['segments'] if r['resource'].startswith('gpu:')
                            and min(right,r['end'])>max(left,r['begin'])}
                    for site in active:gpu[self.sites.index(site)]+=m['gpu']
                else:
                    nominal_end=now+max(0.,m['t50_seconds']-m.get('accumulated_compute_seconds',0))
                    if slot==first or nominal_end>left:gpu[self.sites.index(m['current_site'])]+=m['gpu']
            active={r['resource'][4:] for r in segments if r['resource'].startswith('gpu:')
                and (r['begin']<=now<r['end'] if slot==first else min(right,r['end'])>max(left,r['begin']))}
            for site in active:gpu[self.sites.index(site)]+=metadata['gpu']
            power=self.model.recompute(gpu[None,:],self.sites,[obs['weather']['values']])
            rows.append(dict(slot=slot,start_seconds=left,GPU=gpu.tolist(),P=power['PCC_P_kw'][0].tolist(),
                Q=power['PCC_Q_kvar'][0].tolist(),observations=obs))
        if perf_counter()-self.tick_began>self.max_tick_seconds:
            return dict(status='NOT_CERTIFIED',reason='PREDICTION_TICK_RESOURCE_LIMIT')
        if self.probe is not None:
            callback=getattr(self.probe,'predicted_score',None)
            result=callback(deepcopy(rows)) if callback else dict(status='NOT_CERTIFIED',reason='NO_VALIDATED_PREDICTION_PROBE')
        else:
            self.prediction_calls+=1;proof=self._probe(self.history,rows[0],future_rows=rows)
            peaks=[s['maximum_phase_line_loading'] for s in proof['physical_steps'] if s['kind'].startswith('CONDITIONAL_PUBLIC_')]
            result=dict(status='PASS',grid_peak=max(peaks),loading_hours=sum(peaks)*.25,physical_receipt=proof)
        q90=metadata.get('experimental_prediction_Q90_seconds')
        soft_over=sum(float(np.maximum(np.asarray(row['GPU'])-[self.model.capacities[s] for s in self.sites],0).sum())/4
            for row in rows)
        result.update(risk_GPUh=soft_over+max(0.,float(metadata['t50_seconds'] if q90 is None else q90)-metadata['t50_seconds'])*metadata['gpu']/3600,
            soft_prediction_capacity_risk_GPUh=soft_over,Job_Q90_seconds=q90,
            conditional_remaining_runtime_provider='NOT_CERTIFIED' if q90 is None else 'PUBLIC_SOURCE_Q90',
            anonymous_CC4_and_runtime_reserve_are_physical_GPU=False)
        result.update(checked_slots=list(range(first,stop)),projection='PUBLIC_Q50_COMMITTED_PHASES_CURRENT_EXOGENOUS_HOLD',
            future_Actual_Tap_Completion_reads=0,predicted_AUTO_actions_are_not_Actual_state=True,
            current_hard_veto=False,tail_carry_certified=False)
        if getattr(self,'proof_store',None) is not None and 'physical_receipt' in result:
            result['physical_receipt_lossless']=self.proof_store.save(result.pop('physical_receipt'))
        self.prediction_audit.append(deepcopy(result));return result


class TableVFullFlexPolicy(ProductionResearchPolicy):
    _receipt_window=ExperimentalControlPolicy._receipt_window
    _freeze_reference=ExperimentalControlPolicy._freeze_reference
    _rack_reason=ExperimentalControlPolicy._rack_reason

    def __init__(self,*args,qos_provider,migration_authority,**kwargs):
        super().__init__(*args,**kwargs)
        if self.research.spec['scenario']!='R1':raise ValueError('TABLE_V_R2_HOLD_R1_ONLY')
        if not isinstance(qos_provider,ExperimentalQoSProvider) or (qos_provider.scenario,qos_provider.participation)!=('E1','FLEX30'):
            raise ValueError('TABLE_V_ORIGINAL_E1_FLEX30_REQUIRED')
        self.qos=qos_provider;self.migration_authority=deepcopy(migration_authority)
        self.references={};self.reference_audit=[];self.observed_blocks={};self.context={};self.migration_funnel=[]
        self.runtime_repair=True
        self.spec.update(release_scope='TABLE_V_FULL_E1_FLEX30_R1_WORKLOAD_FLEXIBILITY',
            migration_authority_sha=digest(self.migration_authority),runtime_repair=True,
            migration=True,candidates_seconds=[0,900,1800,2700,3600],
            future_power_model='PUBLIC_Q50_CURRENT_EXOGENOUS_HOLD_ORIGINAL_AC_CONDITIONAL',
            intentional_time_shift='ORIGINAL_E1_SHARED_CUMULATIVE_BUDGET',checkpoint_migration='ORIGINAL_GUARD_WAN_AND_EXPLICIT_E1_ELIGIBILITY',
            future_Known_speculative_GPU_veto=False,scope_is_PreSite_only=False,R2='HOLD',
            conditional_Q50_AC_is_not_Actual_or_official_Fresh=True)
        self.spec.update(Table_V_actual_material_source=file_record(__file__),E1_policy_spec_sha=qos_provider.stats.sha,
            Pending_R1_and_Running_WAN_authorities_are_separate=True,
            source_raw_permission_flags_modified=False)
        self.sha=digest(self.spec)

    def _record(self,m,now,decision,began,count,rejected):
        result=SignedSensitivityPolicy._record(self,m,now,decision,began,count,rejected)
        result.update(full_E1_workload_flexibility=True,time_shift=decision.get('start_seconds',now)>now,
            intentional_delay_seconds=decision.get('additional_start_delay_seconds',0),
            checkpoint_migration_selected=decision.get('action')=='CHECKPOINT_MIGRATE',runtime_repair=True,
            future_Known_speculative_GPU_veto=False)
        self.last_selection[m['uid']]=deepcopy(result);self.audit[-1]['decision']=deepcopy(result)
        return result

    def corrective_allowed(self,m):
        # The E1 model overlay is not an additional Known corrective permit.
        # Preserve CurrentEvent's existing raw Source/research authority gate.
        owner=getattr(self,'_current_resource_ledger',None)
        if owner is not None and m.get('origin_unknown') is False:
            raw=owner.owner.requests[m['uid']].metadata
            m=dict(m,can_prestart_place=raw.get('can_prestart_place') is True)
        return CurrentEventSensitivityPolicy.corrective_allowed(self,m)

    def _hard_candidate(self,m,site,start,now):
        if m['state']!='PENDING':return 'PENDING_ONLY'
        if site not in m['compatible_sites']:return 'SOURCE_SITE_INCOMPATIBLE'
        if m['gpu']>max(self.packet.rack_compatibility[site]):return 'RACK_GANG_INCOMPATIBLE'
        if start not in set(m.get('representation_starts_seconds') or ()):return 'SOURCE_REPRESENTATION_WINDOW'
        if start<self._earliest_event(m,None):return 'SOURCE_RELEASE_WINDOW'
        if m.get('hard_latest_start_seconds') is not None and start>m['hard_latest_start_seconds']:return 'SOURCE_LATEST_WINDOW'
        if m.get('completion_deadline_seconds') is not None and start+m['t50_seconds']>m['completion_deadline_seconds']:return 'SOURCE_DEADLINE'
        use=self._current_resource_ledger.current_gpu_use(now,exclude=m['uid'])
        if start==now and use[site]+m['gpu']>self.packet.capacities[site]:return 'CURRENT_GPU_CAPACITY'
        return None

    def _candidate_at(self,m,site,start,now,window):
        basic=self.initial[m['uid']]['basic_site'];changing=site!=basic
        row=dict(site=site,start_seconds=start,kind='PRE_SITE' if changing else 'STAY',
            feasible=False,reason=self._hard_candidate(m,site,start,now),data='NOT_EVALUATED',
            QoS='NOT_EVALUATED',AC='NOT_EVALUATED',sensitivity_score=None)
        if not self.initial[m['uid']]['allowed']:row['reason']='INITIAL_AUTHORITY_MISSING'
        if row['reason']:return row
        if changing:
            proposal=self.research.propose(m,site,now,day_begin=self.reference.begin,qos_receipt=window)
            row['research_data_contract']=proposal
            if proposal['status']!='READY' or proposal['ready_at_seconds']>start:
                row['reason']=proposal.get('reason') or 'R1_SHARED_INPUT_NOT_READY';return row
        row['data']='PASS_STAY_NO_CHANGE' if not changing else 'PASS_R1_ASSUMED_SHARED_INPUT'
        if start not in window['allowed_starts_seconds']:row['reason']='ORIGINAL_E1_EXECUTION_WINDOW';return row
        if start>now and m.get('Can_TimeShift') is not True:row['reason']='NO_E1_TIMESHIFT_AUTHORITY';return row
        burden=max(m.get('additional_start_delay_seconds',0),
            self.references[m['uid']]['intentional_burden_at_reference_seconds']+start-window['reference_start_seconds'])
        if burden+m.get('cumulative_migration_interruption_seconds',0)>window['budget_seconds']:
            row['reason']='SHARED_DELAY_MIGRATION_BUDGET';return row
        row['QoS']='PASS';row['additional_start_delay_seconds']=burden
        segments=[dict(resource='gpu:'+site,begin=start,end=start+max(m['t50_seconds'],1e-9),quantity=m['gpu'])]
        row['segments']=segments
        if start==now:
            reason=self.current_guard(m,segments,now,self.current[1])
            if reason:row['reason']=reason;row['AC']='FAIL';return row
            row['AC']='PASS_CURRENT_CANDIDATE'
        else:row['AC']='NOT_EVALUATED_DEFERRED_START_ATOMIC_RECHECK_REQUIRED'
        if getattr(self,'_backfill_active',False) and start==now:
            okay,reason=safe_backfill(m,now=now,site=site,reservations=self._current_resource_ledger,
                uid=m['uid'],evidence_scope=self.evidence_scope)
            self._current_resource_ledger.owner.backfill_audit.append(dict(uid=m['uid'],time_seconds=now,site=site,
                feasible=okay,reason=reason,guaranteed_completion_claim=False))
            if not okay:row['reason']='BACKFILL_'+reason;return row
        row['feasible']=True;return row

    def select(self,m,receipt,now,reservations,*,reserve=True):
        began=perf_counter();self.designate(m,now)
        if m['origin_unknown'] is not True:raise ValueError('TABLE_V_KNOWN_NEVER_ENTERS_UNKNOWN_SELECTOR')
        prior=self.references.get(m['uid']);eligible=m.get('Can_TimeShift') is True
        self.context=dict(observed_gpu=dict(self.current[1]))
        basic=self.initial[m['uid']]['basic_site']
        # A public, grid-blind current whole-gang opportunity establishes R0.
        if prior is None:
            if self._hard_candidate(m,basic,now,now) is not None:
                ready=[s for s in m['compatible_sites'] if self._hard_candidate(m,s,now,now) is None]
                if not ready:
                    return self._record(m,now,dict(action='QUEUE',status='OBSERVED_CURRENT_GPU_OR_SOURCE_WAIT'),began,0,[])
            prior=self._freeze_reference(m,now,basic,now,first=now)
        block=self.observed_blocks.get(m['uid'])
        if block and block['time_seconds']<now and block['reference_start_seconds']==prior['reference_start_seconds']:
            first=prior['first_reference_start_seconds'];old=prior['reference_start_seconds']
            prior=self._freeze_reference(m,now,basic,now,first=first)
            self.reference_audit.append(dict(uid=m['uid'],event='OBSERVED_PHYSICAL_REFERENCE_ADVANCE',
                old_reference_start_seconds=old,new_reference_start_seconds=now,proof=deepcopy(block),budget_reissued=False))
            self.observed_blocks.pop(m['uid'],None)
        window=self._receipt_window(m,receipt,prior['reference_start_seconds'],now)
        starts=[t for t in window['allowed_starts_seconds'] if now<=t<self.reference.begin+86400
            and (eligible or t==now)]
        # Zero-budget Basic remains executable after unavoidable queue wait.
        if not eligible and now not in starts:starts=[now]
        window=dict(window,allowed_starts_seconds=tuple(starts))
        sites=[basic]+sorted(set(m['compatible_sites'])-{basic}) if m.get('Can_Preplace') else [basic]
        rows=[self._candidate_at(m,site,start,now,window) for site in sites for start in starts]
        feasible=[r for r in rows if r['feasible']]
        stay=next((r for r in feasible if r['site']==basic and r['start_seconds']==now),None)
        choices=[]
        for row in feasible:
            if row is stay and len(feasible)==1:continue
            try:score=self.oracle.predicted_segments(now,m,row['segments'],self.metadata,
                finish=row['segments'][0]['end'])
            except (ValueError,RuntimeError) as exc:score=dict(status='NOT_CERTIFIED',reason=str(exc))
            row['sensitivity_score']=score
            if score.get('status')=='PASS':choices.append(row)
        chosen=stay
        if choices:
            best=min(choices,key=lambda r:(r['sensitivity_score']['grid_peak'],r['sensitivity_score'].get('loading_hours',0),
                r['sensitivity_score'].get('risk_GPUh',0),r['additional_start_delay_seconds'],
                r['site'],r['start_seconds']))
            if stay is None or (stay.get('sensitivity_score') or {}).get('status')=='PASS' and (
                    best['sensitivity_score']['grid_peak']<stay['sensitivity_score']['grid_peak']-1e-10):chosen=best
        self.candidate_events.append(dict(uid=m['uid'],time_seconds=now,candidates=deepcopy(rows),
            chosen_site=None if chosen is None else chosen['site'],chosen_start=None if chosen is None else chosen['start_seconds'],
            initial_site=basic,execution_window=window,full_TimeShift_domain=eligible,R2='HOLD',future_private_reads=0))
        if chosen is None:
            if now in (prior['reference_start_seconds'],prior.get('selected_due_seconds')):
                self.observed_blocks[m['uid']]=dict(time_seconds=now,reference_start_seconds=prior['reference_start_seconds'],
                    reason='OBSERVED_CURRENT_SOURCE_GPU_OR_AC_REJECTION',candidate_reasons=[r['reason'] for r in rows])
            decision=dict(action='QUEUE',status='NO_CURRENT_OR_VALIDATED_CONDITIONAL_E1_ACTION')
        else:
            if reserve:
                okay,reason=reservations.reserve(m['uid'],chosen['segments'],replace=True)
                if not okay:return self._record(m,now,dict(action='QUEUE',status=reason),began,len(rows),rows)
                m['additional_start_delay_seconds']=max(m.get('additional_start_delay_seconds',0),chosen['additional_start_delay_seconds'])
                prior['selected_due_seconds']=chosen['start_seconds']
            decision=dict(action='PREPLACE' if chosen['site']!=basic else 'DELAY' if chosen['start_seconds']>now else 'START',
                site=chosen['site'],start_seconds=chosen['start_seconds'],nominal_end_seconds=chosen['segments'][0]['end'],
                segments=chosen['segments'],additional_start_delay_seconds=chosen['additional_start_delay_seconds'],
                execution_window_receipt=window,status='TABLE_V_FULL_E1_SELECTED',tracking=chosen['sensitivity_score'])
        return self._record(m,now,decision,began,len(rows),[r for r in rows if not r['feasible']])

    def current_guard(self,m,segments,now,observed):
        owner=self._current_resource_ledger.owner
        use=self._current_resource_ledger.current_gpu_use(now,exclude=m['uid'])
        vector=np.array([use[s] for s in self.packet.sites],float)
        active={r['resource'][4:]:r['quantity'] for r in segments if r['resource'].startswith('gpu:') and r['begin']<=now<r['end']}
        for site,gpu in active.items():
            if site not in m['compatible_sites']:return 'ATOMIC_SOURCE_SITE_INCOMPATIBLE'
            if gpu>max(self.packet.rack_compatibility[site]):return 'ATOMIC_RACK_GANG_INCOMPATIBLE'
            vector[self.packet.sites.index(site)]+=gpu
        if any(vector[j]>self.packet.capacities[s] for j,s in enumerate(self.packet.sites)):return 'ATOMIC_GPU_CAPACITY'
        if now%900:
            # At an execution-anchored off-grid checkpoint, source retention
            # is the already observed state. A new destination injection is
            # never approved with a previous tick's electrical proof.
            current=np.array([owner.ledger.physical(now)[s] for s in self.packet.sites])
            if np.array_equal(vector,current):return None
            return 'OFFGRID_NEW_GPU_INJECTION_HAS_NO_CURRENT_AC_PROOF'
        if self.oracle.now!=now:self.oracle.observe(now,completed_migration_prefix(owner,now))
        proof=self.oracle.evaluate(now,vector,uid=m['uid'])
        return None if proof.get('PASS') is True else 'ATOMIC_CURRENT_CANDIDATE_AC_'+proof.get('status','NOT_CERTIFIED')

    def select_migration(self,m,receipt,now,reservations,*,checkpoint_at=None,reserve=True):
        began=perf_counter();rejected=[];candidates=[]
        elapsed=m.get('accumulated_compute_seconds',0);remaining=max(0.,m['t50_seconds']-elapsed)
        def stay(reason):
            self.migration_funnel.append(dict(uid=m['uid'],time_seconds=now,checkpoint=checkpoint_at,
                eligible=m.get('Can_Checkpoint_Migrate') is True,executed=False,reason=reason,
                candidate_count=len(candidates),rejected=deepcopy(rejected)))
            return self._record(m,now,dict(action='STAY',status=reason),began,len(candidates),rejected)
        if (m.get('state')!='RUNNING' or m.get('Can_Checkpoint_Migrate') is not True
                or elapsed<1800 or abs(elapsed%1800)>1e-7 or checkpoint_at is None or checkpoint_at>now):
            return stay('NO_OBSERVED_ELIGIBLE_EXECUTION_CHECKPOINT')
        if m.get('migration_count',0):return stay('ORIGINAL_MAXIMUM_ONE_MIGRATION')
        if remaining<=0:return stay('Q50_OVERRUN_RUNNING_HOLD_NO_NOMINAL_MOVE')
        if now%900:return stay('EXECUTION_CHECKPOINT_OFFGRID_NO_CONDITIONAL_CURRENT_AC_PROOF')
        stay_segments=[dict(resource='gpu:'+m['current_site'],begin=now,end=now+remaining,quantity=m['gpu'])]
        stay_score=self.oracle.predicted_segments(now,m,stay_segments,self.metadata,finish=now+remaining,replace_running=True)
        for destination in sorted(set(m['compatible_sites'])-{m['current_site']}):
            cap=deepcopy(m.get('migration_capability') or _migration_capability(self.migration_authority,
                m['current_site'],destination,m['gpu']))
            if not cap:
                rejected.append(dict(site=destination,reason='ORIGINAL_WAN_CHECKPOINT_AUTHORITY_UNAVAILABLE'));continue
            if self._rack_reason(m,destination):
                rejected.append(dict(site=destination,reason='RACK_GANG_INCOMPATIBLE'));continue
            candidate=dict(m,migration_capability=cap)
            migration,reason=migration_guard(candidate,receipt,now=now,accumulated_compute_seconds=elapsed,
                destination=destination,remaining_nominal_seconds=remaining,reservations=reservations,checkpoint_at=checkpoint_at)
            if migration is None:
                rejected.append(dict(site=destination,reason=reason));continue
            left=migration['times']['transfer_start'];right=migration['times']['transfer_end']
            migration['segments'].extend(dict(resource='wan:LINK::'+link,begin=left,end=right,
                quantity=cap['bandwidth_bytes_per_second']) for link in cap.get('route_links',[]))
            reason=reservations.feasible(migration['segments'],exclude=m['uid'])
            if reason is None:reason=self.current_guard(m,migration['segments'],now,self.current[1])
            if reason:
                rejected.append(dict(site=destination,reason=reason));continue
            score=self.oracle.predicted_segments(now,m,migration['segments'],self.metadata,
                finish=migration['times']['restart_end']+remaining,replace_running=True)
            if score.get('status')!='PASS':
                rejected.append(dict(site=destination,reason='CONDITIONAL_MIGRATION_SCORE_NOT_CERTIFIED'));continue
            if stay_score.get('status')=='PASS' and score['grid_peak']>=stay_score['grid_peak']-1e-10:
                rejected.append(dict(site=destination,reason='FEASIBLE_STAY_RANK_PREFERRED'));continue
            candidates.append((score['grid_peak'],migration['interruption_seconds'],destination,cap,migration,score))
        for _,_,destination,cap,migration,score in sorted(candidates,key=lambda r:r[:3]):
            if reserve:
                okay,reason=reservations.reserve(m['uid'],migration['segments'],replace=True)
                if not okay:
                    rejected.append(dict(site=destination,reason=reason));continue
                m['migration_capability']=cap
            self.migration_funnel.append(dict(uid=m['uid'],time_seconds=now,eligible=True,executed=True,
                destination=destination,reason='ORIGINAL_E1_WAN_CURRENT_AC_AND_SIGNED_MINMAX',candidate_count=len(candidates)))
            return self._record(m,now,dict(action='CHECKPOINT_MIGRATE',status='TABLE_V_ORIGINAL_MIGRATION_SELECTED',
                migration=migration,tracking=score),began,len(candidates),rejected)
        return stay('NO_LEGAL_OR_BETTER_CHECKPOINT_DESTINATION')


class TableVFullFlexController(ProductionCurrentController):
    _overlay=ExperimentalJobEventController._overlay

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.reservations=TableVReservationLedger(self,capacities=self.ledger.capacities,
            wan_capacities=kwargs.get('wan_capacities'))
        self.policy._current_resource_ledger=self.reservations
        self.policy.oracle.owner=self

    def submit(self,request,now):
        # CurrentEvent's Source-preserving submit happens first. Its inactive
        # SiteOnly flag mask is then replaced by the original E1 overlay.
        if request.uid not in self.qos.contexts:
            self.qos.register_observed(request.uid,episode_id=request.metadata.get('episode_id'),
                source_authority=request.metadata.get('source_qos_authority'))
        super().submit(request,now)
        self._overlay(request.uid,self.observed[request.uid].state)
        self.metadata[request.uid]['experimental_prediction_Q50_seconds']=request.q50

    def admit(self,now):
        if now%900:return []
        began=perf_counter();count=len(self.pending)
        self.policy.oracle.observe(now,completed_migration_prefix(self,now))
        if digest(self.known_schedule)!=self.frozen_known_sha:raise ValueError('TABLE_V_IMMUTABLE_KNOWN_PLAN_DRIFT')
        self.policy.require_bindings(self.policy.bindings)
        for uid,m in self.metadata.items():
            if m['state']=='RUNNING' and m.get('accumulated_compute_seconds',0)>m['t50_seconds'] and uid not in self._overrun_seen:
                self._overrun_seen.add(uid);self.runtime_audit.append(dict(uid=uid,time_seconds=now,event='OVERRUN_RUNNING_HOLD',
                    elapsed_seconds=m['accumulated_compute_seconds'],Q50_seconds=m['t50_seconds'],Running_gpu_preserved=True))
        remaining=[];starts=[]
        try:
            for row in sorted(self.pending,key=lambda r:(self.metadata[r[1]]['origin_unknown'],r[0],r[1])):
                uid=row[1];old=self.decisions.get(uid);self.pending=[row]
                # Delay is a real committed E1 command, not reselected each
                # tick. Current AC is rechecked atomically when it becomes due.
                if not old or old.get('action')=='QUEUE' or uid in self.planning_commands:
                    self.decisions.pop(uid,None)
                self.policy.observe(now,self.reservations.current_gpu_use(now,exclude=uid),self.metadata)
                self._overlay(uid,'PENDING')
                self.policy._backfill_active=bool(self.released_since_control and old and
                    old.get('start_seconds',now)>now and self.metadata[uid]['origin_unknown'])
                if self.policy._backfill_active:self.decisions.pop(uid,None)
                if not self.metadata[uid]['origin_unknown'] and uid not in self.planning_commands:
                    self.decisions[uid]=dict(uid=uid,action='QUEUE',status='SAME_CASE_KNOWN_PLANNING_COMMAND_MISSING')
                one=JobEventController.admit(self,now);starts.extend(one);remaining.extend(self.pending)
                decision=self.decisions.get(uid,{})
                if not one and decision.get('action') not in (None,'QUEUE') and decision.get('start_seconds',math.inf)<=now:
                    last=next((e for e in reversed(self.events) if e['uid']==uid and e['time_seconds']==now),None)
                    if last and last['event']=='QUEUED':
                        proof=dict(time_seconds=now,queue_event=deepcopy(last),actual_START_attempt_observed=True,
                            original_command_sha=digest(self.planning_commands[uid]) if uid in self.planning_commands else None)
                        if uid in self.planning_commands:self.observed_known_waits[uid]=proof
                        else:
                            ref=self.policy.references.get(uid)
                            if ref:self.policy.observed_blocks[uid]=dict(proof,reference_start_seconds=ref['reference_start_seconds'])
                            self.decisions[uid]=dict(uid=uid,action='QUEUE',status='OBSERVED_E1_CURRENT_RESOURCE_WAIT')
                if one:
                    m=self.metadata[uid]
                    reference=self.policy.references.get(uid)
                    executed_delay=(decision.get('additional_start_delay_seconds',0) if reference is None else max(0.,
                        reference['intentional_burden_at_reference_seconds']+now-reference['reference_start_seconds']))
                    self.actual_start_events.append(dict(uid=uid,time_seconds=now,site=m['current_site'],GPU=m['gpu'],
                        origin_unknown=m['origin_unknown'],basic_site=self.policy.initial.get(uid,{}).get('basic_site'),
                        atomic_AC_rechecked=True,intentional_delay_seconds=decision.get('additional_start_delay_seconds',0),
                        executed_intentional_time_shift_seconds=executed_delay))
                    if uid in self.corrective_commands:self.corrective_commands[uid]['actual_start_seconds']=now
                    if uid in self.planning_commands:
                        self.known_actual_audit.append(dict(uid=uid,original_command=deepcopy(self.planning_commands[uid]),
                            actual_site=m['current_site'],actual_start_seconds=now,planning_command_modified=False))
                    for backfill in self.backfill_audit:
                        if backfill.get('uid')==uid and backfill.get('time_seconds')==now:
                            backfill['selected']=True
            return starts
        finally:
            self.pending=remaining;heapq.heapify(self.pending);self.policy._backfill_active=False
            self.released_since_control=[]
            if self.resource_bridge:self.resource_bridge.snapshot(now,self.metadata,self.reservations)
            self.control_tick_times.append(dict(time_seconds=now,wall_seconds=perf_counter()-began,
                pending_before=count,pending_after=len(self.pending),scope='ENTIRE_FULL_E1_CONTROLLER_TICK'))

    def migration(self,uid,now,physical_checkpoint):
        self._overlay(uid,'RUNNING')
        self.policy.observe(now,self.reservations.current_gpu_use(now),self.metadata)
        if now%900==0 and self.policy.oracle.now!=now:
            self.policy.oracle.observe(now,completed_migration_prefix(self,now))
        eligible=self.metadata[uid].get('Can_Checkpoint_Migrate') is True
        if (not eligible and
                self.known_schedule.get(uid,{}).get('migration_destination') is not None):
            self._event(uid,now,'RUNNING_STAY',reason='E1_CHECKPOINT_ELIGIBILITY_NOT_AUTHORIZED');return None
        result=JobEventController.migration(self,uid,now,physical_checkpoint)
        last=next((r for r in reversed(self.events) if r['uid']==uid and r['time_seconds']==now),{})
        self.policy.migration_funnel.append(dict(uid=uid,time_seconds=now,
            origin_unknown=self.metadata[uid]['origin_unknown'],eligible=eligible,
            frozen_Known_migration_requested=self.known_schedule.get(uid,{}).get('migration_destination') is not None,
            original_execution_checkpoint_seconds=physical_checkpoint,
            executed=result is not None,reason='ORIGINAL_CHECKPOINT_COMMITTED' if result else last.get('reason','NO_MIGRATION_SELECTED')))
        return result

    def snapshot(self,now):
        result=CurrentEventJobEventController.snapshot(self,now)
        result['current_event_state'].update(
            checkpoint_migration_status='ACTIVE_ORIGINAL_E1_CHECKPOINT_WAN_AND_ATOMIC_PHASE_GUARDS',
            intentional_time_shift_status='ACTIVE_ORIGINAL_E1_CUMULATIVE_EXECUTION_WINDOWS',
            checkpoint_migrations_committed=len(self.migrations),PreSite_only_case=False)
        result['tablev_state']=dict(scope='TABLE_V_FULL_E1_FLEX30_R1',actual_starts=deepcopy(self.actual_start_events),
            control_tick_timings=deepcopy(self.control_tick_times),prefix=completed_migration_prefix(self,now),
            initial_placements=deepcopy(self.policy.initial_events),full_flexibility_domain_connected=True,
            RuntimeShortOverrunBackfill=True,TimeShift=True,R1_Pending_PreSite=True,
            OriginalCheckpointWAN=True,R2='HOLD',Known_planning_commands_modified=False)
        return result


def require_full_a_parent(context,arm,result,receipt):
    """Cross-check the original numeric FULL authority, not only its header."""
    full=receipt.get('Original_FULL',{});replay=result.get('FULL_point_replay',{})
    residual=full.get('FULL_max_residual',math.inf);binding=result.get('native_binding',{})
    if (receipt.get('arm')!=arm or receipt.get('stage_case_sha')!=result.get('case_sha')
            or receipt.get('D0_input_sha')!=context['input_audit']['a_input_sha']
            or receipt.get('AIDC_anchor')!=result.get('aidc_anchor')
            or receipt.get('MESS_anchor')!=result.get('input_MESS_anchor')
            or full.get('PASS') is not True or replay.get('PASS') is not True
            or type(residual) not in (int,float) or not math.isfinite(residual) or not 0<=residual<=1e-5
            or not receipt.get('point_sha256') or full.get('point_sha256')!=receipt['point_sha256']
            or replay.get('point_sha256')!=receipt['point_sha256']
            or receipt.get('native_binding')!=binding or binding.get('objective_sense')!=1
            or not binding.get('rows') or binding.get('rows')!=full.get('rows')
            or not binding.get('columns') or binding.get('columns')!=full.get('columns')):
        raise ValueError('TABLE_V_LITERAL_ORIGINAL_A_FULL_POINT_SOURCE_JOIN_REQUIRED')
    return receipt


def run_fullflex_actual(*,context,arm,a_result,a_acceptance,reference_result,reference_acceptance,output,
        m_result=None,m_acceptance=None,gate,slots=96):
    """Real A1(B1)/A2+M2(B3) handoff before any private service bank IO."""
    from .table_v_flex_planning import require_flex_context,compile_flex_commands
    from .release_p1_acceptance import require_acceptance
    from .coordinator import _full_a,_full_m,verify_sources
    from .tablev_actual import (prepare_reference_inputs,project_public_initial,_require_mess,
        _source_freeze,SCHEMA)
    from .release_ac_contract import CONTRACT
    require_flex_context(context)
    if arm not in ('B1','B3') or slots not in (16,96):raise ValueError('TABLE_V_FLEXIBLE_ARM_AND_SCOPE_REQUIRED')
    if gate.get('Gate_contract')!=CONTRACT or gate.get('official_contract_authorized') is not True:
        raise ValueError('TABLE_V_ORIGINAL_SETTLED_AC_CONTRACT_REQUIRED')
    identity=context['manifest']['identity'];stage='A1' if arm=='B1' else 'A2'
    require_acceptance(a_acceptance,stage=stage,source_identity=identity,result=a_result)
    if (a_acceptance.get('fixture') is not False or a_acceptance.get('evidence_scope')!='REAL_PRODUCTION'
            or a_acceptance.get('source_sha')!=context['manifest']['source_sha'] or a_result.get('arm')!=arm):
        raise ValueError('TABLE_V_CURRENT_ARM_ORIGINAL_FULL_A_P1_REQUIRED')
    require_full_a_parent(context,arm,a_result,a_acceptance)
    day=context_day(context)
    _full_a(a_result);commands=compile_flex_commands(a_result,context)
    mess=_require_mess(context,arm,m_result,m_acceptance)
    if arm=='B3':
        _full_m(m_result)
        if (m_acceptance.get('parent_acceptance_sha')!=a_acceptance['acceptance_sha']
                or m_acceptance.get('AIDC_anchor')!=a_result['aidc_anchor']):
            raise ValueError('TABLE_V_B3_CURRENT_A2_M2_FULL_PARENT_REQUIRED')
    elif a_result.get('input_MESS_anchor')!=mess['plan_sha']:
        raise ValueError('TABLE_V_B1_A1_AND_ACTUAL_LITERAL_MESS_OFF_REQUIRED')
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_FULL_FLEX_ACTUAL_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    private=prepare_reference_inputs(context,reference_result=reference_result,reference_acceptance=reference_acceptance,
        output=output/'PRIVATE_INPUTS',slots=slots)
    args=dict(private['arguments']);flex=context['tablev_flex']
    provider=ExperimentalQoSProvider(args['qos_window_provider'],scenario='E1',participation='FLEX30',
        case_sha=identity['case_sha'],provider_sha=flex['provider_sha'],receipts=flex['known_issued_receipts'])
    if provider.stats.sha!=flex['stats_sha'] or provider.contexts!=flex['known_source_contexts']:
        raise ValueError('TABLE_V_E1_ISSUED_PLANNING_BUDGET_CONTEXT_DRIFT')
    args=project_public_initial(args,context['state'],reference=args['reference'],provider=provider,
        known_observed=flex['known_observed_records'])
    args.update(arm=arm,known_schedule=commands)
    bridge,actual_identity=_resource_bridge(context,a_result,args['capacities'])
    from .research_presite_contract import make_spec,ResearchPresiteProvider
    from .research_presite_actual import ObservedSourceAuthority
    raw=private['raw_folder']/'ACTUAL_INPUT_BUNDLE.json'
    spec=make_spec(scenario='R1',source_records=[file_record(raw)],native_wan_sha=digest(context['data'][0]['WAN']),
        shared_sites=sorted(args['capacities']),ready_delay_slots=0)
    _write(output/'R1_RESEARCH_CONTRACT.json',spec)
    actual_policy=dict(schema='TABLE_V_ACTUAL_FULL_FLEX_E1_FLEX30_R1_V1',arm=arm,
        policy=deepcopy(flex['spec']),research_spec_sha=digest(spec),R2='HOLD',
        command_sha=digest(commands),MESS_plan_sha=mess['plan_sha'])
    packet,reference,bindings=_physical_packet(context,a_result,mess,args,commands,actual_policy)
    from .trajectory_tracking import TrackingReference
    arrays=reference.arrays
    reference=TrackingReference(arrays['G_Known_Plan'],arrays['G_Unknown_Q50_Plan'],arrays['IT_Plan'],
        arrays['PCC_P_Plan'],arrays['PCC_Q_Plan'],sites=reference.sites,begin=reference.begin,commands=commands,
        identity=dict(reference.identity,C1_Power_Model_SHA=args['power_model'].authority_sha))
    research=ResearchPresiteProvider(spec,native_wan=context['data'][0]['WAN'])
    modules=('release_date_ac.py','release_production_actual.py','research_presite_contract.py',
        'research_presite_actual.py','current_ac_admission.py','rc02_prefix_cache.py',
        'aidc_sensitivity_runtime.py','aidc_resource_bridge.py','release_actual.py',
        'reservation_state.py','known_commands.py','experimental_actual.py','experimental_policy.py',
        'experimental_qos.py','frozen_unknown.py','sensitivity_policy.py','trajectory_tracking.py',
        'release_p1_acceptance.py','table_v_a.py','table_v_mess.py','actual_validation.py')
    extra=[file_record(__file__),*[file_record(Path(__file__).with_name(name)) for name in modules]]
    root=Path(__file__).resolve().parents[1]
    extra += [file_record(root/name) for name in ('v42_voltage_control/b0_new.py',
        'v42_final/state.py','v42_final/workload.py')]
    private['sources']+=extra
    freeze=_source_freeze(context,private,output)
    from .actual_validation import read,_validated_hardware_context
    from .tablev_actual import ARCHIVE
    campaign=read(ARCHIVE/'CAMPAIGN_MANIFEST.json')
    oracle=TableVCurrentAC(begin=args['begin'],sites=packet.sites,power_model=args['power_model'],
        observations=private['observations'],source_freeze=freeze,manifest=campaign,mess=mess,proof_records=extra)
    oracle.audit=StreamingAudit(output/'CURRENT_CANDIDATE_AC_LEDGER.jsonl')
    oracle.prediction_audit=StreamingAudit(output/'CONDITIONAL_PUBLIC_Q50_LEDGER.jsonl')
    oracle.proof_store=PhysicalProofStore(output/'CONDITIONAL_PHYSICAL_PROOFS')
    policy=TableVFullFlexPolicy(reference,packet,qos_provider=provider,migration_authority=flex['migration_authority'],
        research_provider=research,source_authority_lookup=ObservedSourceAuthority(raw),variant='C1',oracle=oracle,
        bindings=bindings,expected_bindings=bindings,evidence_scope='REAL_TABLE_V_FULL_FLEX',
        source_identity=dict(planning_identity=actual_identity,study_case_sha=identity['case_sha']),
        site_authority=initial_authority(bindings,identity['case_sha']))
    _bind_driver_current_c1(policy,args);policy.save(output/'FROZEN_POLICY.json')
    args.update(frozen_policy=policy,expected_bindings=bindings,wan_capacities=flex['migration_authority']['wan_capacities'])
    active={}
    def controller(*a,**kw):
        value=TableVFullFlexController(*a,resource_bridge=bridge,actual_identity=actual_identity,
            initial_pending={r['uid']:r for r in context['state']['pending']},backlog_contract=context['backlog'],**kw)
        active['controller']=value;return value
    from .rc02_prefix_cache import memory_gate
    from .isolated_unknown import no_native
    memory_gate();began=perf_counter();environment=args['environment']
    try:
        with no_native() as attempts,_validated_hardware_context(freeze,campaign):
            result=run_actual(**args,controller_class=controller)
    except Exception as exc:
        current=active.get('controller')
        if current is not None:
            observed_at=max([args['begin']]+[r['time_seconds'] for r in current.events])
            _write(output/'ACTUAL_FAILURE_PARTIAL_PUBLIC_STATE.json',current.snapshot(observed_at))
        _write(output/'ACTUAL_FAILURE_STATUS.json',dict(status='NOT_CERTIFIED',error=repr(exc),
            completed_Full96=False,no_automatic_retry=True,Native_calls=0,partial_JSONL_evidence_preserved=True))
        raise
    if args['environment'] is not environment or attempts:raise ValueError('TABLE_V_PRIVATE_ENVIRONMENT_OR_NATIVE_GUARD_DRIFT')
    state=result['carryout']['controller']['tablev_state'];prefix=state['prefix']
    np.testing.assert_allclose(result['occupancy_GPU'],[r['GPU'] for r in prefix],rtol=0,atol=1e-10)
    np.testing.assert_allclose(result['physical']['PCC_P_kw'],[r['P'] for r in prefix],rtol=0,atol=1e-9)
    np.testing.assert_allclose(result['physical']['PCC_Q_kvar'],[r['Q'] for r in prefix],rtol=0,atol=1e-9)
    trace=output/'ACTUAL_OCCUPANCY_POWER_TRACE.npz'
    np.savez_compressed(trace,sites=result['sites'],timestamps_start_epoch_seconds=np.arange(args['begin'],args['end'],900),
        GPU=result['occupancy_GPU'],compute_GPU=result['compute_occupancy_GPU'],**result['physical'])
    for name,value in dict(PUBLIC_EPISODE_STATE=result['carryout']['controller'],QOS_LEDGER=result['qos_ledger'],
            QUEUE_LEDGER=result['queue_ledger'],JOB_EVENT_LEDGER=result['job_event_ledger'],
            INITIAL_PLACEMENT_LEDGER=policy.initial_events,FULL_FLEX_CANDIDATE_LEDGER=policy.candidate_events,
            E1_CAUSAL_REFERENCE_LEDGER=policy.reference_audit,MIGRATION_FUNNEL=policy.migration_funnel,
            MIGRATION_RECEIPTS=result['migration_receipts'],RESEARCH_R1_LEDGER=research.export(),
            RESOURCE_BRIDGE=bridge.export()).items():_write(output/(name+'.json'),value)
    payload=dict(schema='TABLE_V_FULL_FLEX_ACTUAL_EVALUATION_CASE_V1',day=day,arm=arm,source_identity=identity,
        source_sha=context['manifest']['source_sha'],initial_state_sha=context['state']['common_initial_state_sha'],
        A_result_sha=digest(a_result),A_acceptance_sha=a_acceptance['acceptance_sha'],
        reference_result_sha=digest(reference_result),reference_acceptance_sha=digest(reference_acceptance),
        M_result_sha=None if m_result is None else digest(m_result),
        M_acceptance_sha=None if m_acceptance is None else m_acceptance['acceptance_sha'],
        AIDC_anchor=a_result['aidc_anchor'],MESS_plan_sha=mess['plan_sha'],
        final_AIDC_stage=stage,final_MESS_stage='OFF' if arm=='B1' else 'M2',
        policy=actual_policy,policy_sha=digest(actual_policy),
        actual_policy=actual_policy,actual_policy_sha=digest(actual_policy),slots=slots,clock_contract=CONTRACT)
    failures=[k for k in ('capacity_violations','dropped_jobs','future_duration_controller_reads',
        'future_completion_controller_reads','optimizer_calls','actual_global_reoptimization') if result['receipt'][k]!=0]
    for row in result['qos_ledger']:
        if row['total_intentional_burden_seconds']>row['budget_seconds']+1e-7:failures.append('SHARED_E1_QOS_BUDGET:'+row['uid'])
        if (row.get('actual_completion_deadline_excess_seconds') or 0)>0:failures.append('ACTUAL_SOURCE_HARD_DEADLINE:'+row['uid'])
    from .table_v_evaluation import evaluate
    common,common_failures=evaluate(result,arm=arm,begin=args['begin'],end=args['end'])
    failures=list(dict.fromkeys(failures+common_failures))
    _write(output/'COMMON_QOS_THROUGHPUT_METRICS.json',common)
    tick_max=max((r['wall_seconds'] for r in state['control_tick_timings']),default=math.inf)
    if tick_max>=900:failures.append('CONTROLLER_900_SECOND_LIMIT')
    verify_sources(freeze,[])
    starts=state['actual_starts'];unknown=[r for r in starts if r['origin_unknown']]
    changed=[r for r in unknown if r['site']!=r['basic_site']]
    public=result['carryout']['controller'];jobs=public['episode_jobs']
    changed_gpuh=0.
    observed=SimpleNamespace(ledger=SimpleNamespace(jobs=jobs),migrations=result['migration_receipts'],
        requests={u:SimpleNamespace(gpu=m['gpu']) for u,m in public['metadata'].items()})
    for row in changed:
        uid=row['uid'];boundary=min([args['end']]+[m['physical_checkpoint_seconds'] for m in result['migration_receipts']
            if m['job_id']==uid])
        intervals=observed_gpu_intervals(observed,uid,args['end'])
        changed_gpuh+=row['GPU']*sum(max(0.,min(right,boundary)-max(left,row['time_seconds']))
            for left,right in intervals.get(row['site'],[]))/3600
    eligible_unknown=[u for u,b in provider.receipts.items() if u not in flex['known_issued_receipts']
        and b.participant and b.eligible_for_contract]
    funnel=dict(Unknown_submitted_UIDs=sum(m['origin_unknown'] for m in public['metadata'].values()),
        Initial_placement_UIDs=len(policy.initial_events),Unknown_started_UIDs=len(unknown),
        FLEX30_eligible_Unknown_UIDs=len(eligible_unknown),R1_PreSite_executed_UIDs=len(changed),
        Changed_GPUh=changed_gpuh,TimeShift_evaluated_UIDs=len({r['uid'] for r in policy.candidate_events if r['full_TimeShift_domain']}),
        Changed_GPUh_definition='OBSERVED_OCCUPATION_AT_PRESITE_INITIAL_SITE_UNTIL_FIRST_MIGRATION_CHECKPOINT_OR_COMPLETION_OR_DAY_END',
        Changed_GPUh_is_compute_GPUh_difference=False,
        TimeShift_executed_UIDs=sum(r['executed_intentional_time_shift_seconds']>0 for r in unknown),
        TimeShift_executed_seconds=sum(r['executed_intentional_time_shift_seconds'] for r in unknown),
        TimeShift_budget_charged_seconds=sum(r['intentional_delay_seconds'] for r in unknown),
        Running_migration_evaluated_UIDs=len({r['uid'] for r in policy.migration_funnel}),
        Running_migration_eligible_UIDs=sum(b.participant and b.eligible_for_contract and jobs[u].get('start_time') is not None
            for u,b in provider.receipts.items()),
        Known_planned_checkpoint_migration_UIDs=sum(c.get('migration_destination') is not None for c in commands.values()),
        Running_migration_executed_UIDs=len(result['migration_receipts']),
        Known_corrective_executed_UIDs=sum(r.get('actual_start_seconds') is not None for r in public['current_event_state']['actual_corrective_commands'].values()),
        Runtime_short_completion_UIDs=sum(r['event']=='RUNTIME_SHORT_COMPLETION' for r in public['current_event_state']['runtime_events']),
        Overrun_hold_UIDs=sum(r['event']=='OVERRUN_RUNNING_HOLD' for r in public['current_event_state']['runtime_events']),
        Backfill_evaluations=len(public['current_event_state']['backfill_results']),
        Additional_intentional_burden_violations=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-7 for r in result['qos_ledger']),
        Source_actual_hard_deadline_violations=sum((r.get('actual_completion_deadline_excess_seconds') or 0)>0 for r in result['qos_ledger']),
        Original_reference_latest_start_excess_UIDs=sum(r['latest_start_excess_seconds']>0 for r in result['qos_ledger']),
        Original_reference_lateness_is_not_additional_intentional_burden=True,
        full_TimeShift_R1_Runtime_Backfill_Checkpoint_domain_connected=True,PreSite_only_case=False,R2='HOLD')
    receipt=dict(common_metrics=common,common_metrics_record=file_record(output/'COMMON_QOS_THROUGHPUT_METRICS.json'),
        schema=SCHEMA,fixture=False,arm=arm,day=day,status='FULL_PASS' if not failures else 'NOT_CERTIFIED',
        Actual_stage_PASS=not failures,Actual_stage_failures=failures,source_identity=identity,source_sha=context['manifest']['source_sha'],
        evaluation_case_payload=payload,evaluation_case_sha=digest(payload),initial_state_sha=identity['initial_state_sha'],
        AIDC_anchor=a_result['aidc_anchor'],policy_sha=payload['policy_sha'],
        final_AIDC_stage=payload['final_AIDC_stage'],final_MESS_stage=payload['final_MESS_stage'],
        MESS_plan_sha=mess['plan_sha'],executed_actual_slots=slots,actual_trace=file_record(trace),
        actual_source_freeze=file_record(output/'TABLE_V_ACTUAL_SOURCE_FREEZE.json'),Original_event_driver_reused=True,
        private_Environment_identity_preserved=True,Actual_global_MILP_calls=0,blocked_native_attempts=attempts,
        actual_wall_seconds=perf_counter()-began,receipt=result['receipt'],raw_folder=str(private['raw_folder']),Gate_contract=CONTRACT,
        control_tick_timings=state['control_tick_timings'],controller_max_seconds=tick_max,action_funnel=funnel,
        compact_audit_receipts=dict(current_AC=oracle.audit.receipt(),conditional_Q50=oracle.prediction_audit.receipt()),
        exact_public_migration_prefix_equals_original_Actual_occupancy=True,Fresh_status='NOT_RUN',
        E1_Source_hard_deadline_extended=False,original_EMPIRICAL_QoS_statistics_changed=False)
    _write(output/'TABLE_V_ACTUAL_EXECUTION.json',receipt)
    return dict(status=receipt['status'],result=receipt,raw_records=[file_record(output/'TABLE_V_ACTUAL_EXECUTION.json'),file_record(trace)])

