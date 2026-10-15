"""PR223 fixed-MESS diagnostic: common current feasibility, ranking only.

No D0 A-stage or historical prefix certificate is an entry requirement. The
approved midnight model state and the byte-pinned PR223 reference/fallback
method are inputs. Private service remains in the unchanged event simulator.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import csv
import heapq
import importlib.util
import json
import math
from pathlib import Path
import pickle
import sys
from time import perf_counter

import numpy as np

from .actual import JobEventController, run_actual
from .aidc_sensitivity_runtime import (CurrentEventSensitivityPolicy,
    CurrentEventJobEventController, _bind_driver_current_c1)
from .policy import digest, _receipt
from .trajectory_tracking import TrackingReference, require_tracking_public, service_integral
from .actual_validation import record, read, write

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=Path('D:/v42_common_am_qos_integration_20261013/v42_integration/actual.py')
ORIGINAL_SHA='e27b6ad697006d33c67c9ddc612bf9508006f38af3052c36ba986f71361dcc38'
BASE=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
INITIAL=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
M2_REL=Path('M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
M2_SHA='72be8ee7c73024643bcce927eb2373c40872bc06fb9e9c9da98b6b6b84cb8656'
SCOPE='PR223_REFERENCE_DIAGNOSTIC_ACTUAL'


def original_driver():
    """Execute the actual preserved function, rather than a rewritten fallback."""
    if record(ORIGINAL)['sha256']!=ORIGINAL_SHA:raise ValueError('PR223_DRIVER_BYTES_DRIFT')
    name='v42_integration._isolated_pr223_original_actual'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,ORIGINAL)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        spec.loader.exec_module(module)
    return sys.modules[name]


@contextmanager
def no_native():
    """Global process guard covers every incidental Gurobi model entrypoint."""
    import gurobipy as gp
    methods={key:getattr(gp.Model,key) for key in ('optimize','presolve','computeIIS')}
    attempts=[]
    def blocked(*args,**kwargs):
        attempts.append('FORBIDDEN_NATIVE_ENTRYPOINT')
        raise RuntimeError('ISOLATED_UNKNOWN_GUROBI_NATIVE_FORBIDDEN')
    try:
        for key in methods:setattr(gp.Model,key,blocked)
        yield attempts
    finally:
        for key,value in methods.items():setattr(gp.Model,key,value)


def reclassify_initial(arguments,state):
    """Only origin classification changes; preserve the opaque Environment."""
    active={row['uid'] for row in state['running']+state['pending']}
    result=dict(arguments);changed=[]
    def project(request):
        if request.uid not in active:return request
        metadata=deepcopy(request.metadata)
        if metadata.get('origin_unknown'):changed.append(request.uid)
        metadata.update(original_PR223_origin_unknown=metadata.get('origin_unknown'),
            origin_unknown=False,cc4_eligible=False,
            isolated_initial_classification='PUBLIC_AT_MIDNIGHT_KNOWN')
        return replace(request,metadata=metadata)
    result['requests']=[project(r) for r in arguments['requests']]
    result['running']=[(project(r),site,start) for r,site,start in arguments['running']]
    roster={r.uid for r,_,_ in result['running']}|{r.uid for r in result['requests'] if r.submit<=arguments['begin']}
    if roster!=active:raise ValueError('ISOLATED_INITIAL_UID_ROSTER_DRIFT')
    if len(roster)!=len(result['running'])+sum(r.submit<=arguments['begin'] for r in result['requests']):
        raise ValueError('ISOLATED_DUPLICATE_INITIAL_UID')
    if any(r.uid in set(state['excluded_44uids']) for r in result['requests']):
        raise ValueError('ISOLATED_COMPLETED_UID_RESUBMITTED')
    return result,dict(initial_Known=len(active),initial_Running=len(result['running']),
        initial_Running_GPU=sum(r.gpu for r,_,_ in result['running']),
        initial_Pending=sum(r.submit<=arguments['begin'] for r in result['requests']),
        reclassified_initial_Unknown=len(changed),reclassified_UIDs=sorted(changed),
        future_Unknown=sum(r.submit>arguments['begin'] for r in result['requests']),
        initial_forecast_debits=0,private_Environment_identity_preserved=result['environment'] is arguments['environment'])


class RankingOnlyPolicy(CurrentEventSensitivityPolicy):
    """Both rankings consume exactly the same candidate builder and guards."""
    def __init__(self,*args,ranking,**kwargs):
        if ranking not in ('C0','C1'):raise ValueError('ISOLATED_C0_OR_C1_REQUIRED')
        super().__init__(*args,basic=False,runtime_repair=False,**kwargs)
        self.ranking=ranking;self.candidate_events=[]
        self.spec.update(isolated_scope=SCOPE,ranking_variant=ranking,
            common_candidate_algorithm='CURRENT_GPU_RACK_SOURCE_DATA_ELECTRICAL_V1',
            historical_Known_exact_optimized_execution_claim=False,
            new_site_or_data_authority=False)
        self.sha=digest(self.spec)

    def feasible_candidates(self,m,receipt,now,reservations):
        require_tracking_public(m)
        if m.get('origin_unknown') is not True:raise ValueError('ISOLATED_UNKNOWN_ONLY')
        if self.current is None or self.current[0]!=now or now%900:raise ValueError('ISOLATED_CURRENT_TICK_REQUIRED')
        source=m.get('reference_site',m.get('source_site'))
        sites=sorted(set(m['compatible_sites']))
        if len(sites)>12 or any(s not in self.packet.sites for s in sites):raise ValueError('ISOLATED_SOURCE_SITES_REQUIRED')
        eligible=(m.get('state')=='PENDING' and m['submit_seconds']<=now
            and now>=self._earliest_event(m,receipt)
            and now in set(m.get('representation_starts_seconds') or ()))
        end=now+max(m['t50_seconds'],1e-9)
        hard=(m.get('hard_latest_start_seconds') is not None and now>m['hard_latest_start_seconds']
            or m.get('completion_deadline_seconds') is not None and end>m['completion_deadline_seconds'])
        base=np.array([self.current[1][s] for s in self.packet.sites],float)
        rows=[];slot=int((now-self.reference.begin)//900)
        for site in sites:
            reason=None;peak=None;bad=[]
            if not eligible:reason='SOURCE_START_ELIGIBILITY'
            elif hard:reason='ORIGINAL_HARD_WINDOW'
            elif m['gpu']>max(self.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
            elif base[self.packet.sites.index(site)]+m['gpu']>self.packet.capacities[site]:reason='CURRENT_GPU_CAPACITY'
            elif site!=source:
                # Source preplace permission alone is not a data-ready receipt.
                if m.get('can_prestart_place') is not True:reason='SOURCE_PREPLACEMENT_AUTHORITY_MISSING'
                else:
                    data=m.get('preplacement_data') or {};sha=data.get('source_sha','')
                    at=data.get('observed_at_seconds',math.inf);ready=data.get('ready_at_seconds',{}).get(site,math.inf)
                    if (len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha)
                            or not math.isfinite(float(at)) or at>now
                            or site not in data.get('authorized_destinations',[])
                            or not math.isfinite(float(ready)) or ready>now):
                        reason='SOURCE_DATA_WAN_PREPARATION_NOT_OBSERVED_READY'
            held,_=self._admission_hold(site,now,end,m['gpu'])
            if reason is None:reason=self._admission_conflict(reservations,held,m['uid'])
            if reason is None:
                candidate=base.copy();candidate[self.packet.sites.index(site)]+=m['gpu']
                peak,bad=self.packet._at_slot(slot,self._grid_delta(slot,candidate,now))
                if bad:reason='CURRENT_OBSERVED_'+bad[0]['reason']
            rows.append(dict(site=site,feasible=reason is None,reason=reason,grid_peak=peak,
                current_GPU_feasible=bool(base[self.packet.sites.index(site)]+m['gpu']<=self.packet.capacities[site]),
                rack_feasible=bool(m['gpu']<=max(self.packet.rack_compatibility[site])),
                electrical_checked=peak is not None,electrical_pass=peak is not None and not bad,
                grid_violations=bad,segments=held,source_reference_site=source))
        event=dict(uid=m['uid'],time_seconds=now,start_eligible=eligible and not hard,gpu=m['gpu'],
            observed_GPU_by_site=dict(self.current[1]),compatible_sites=sites,
            candidates=rows,candidate_set_sha=digest(rows),private_future_reads=0,
            future_Known_reservation_veto=False,all_line_phase_electrical_rows=True)
        self.candidate_events.append(deepcopy(event))
        return event

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        began=perf_counter();event=self.feasible_candidates(metadata,receipt,now,reservations)
        feasible=[row for row in event['candidates'] if row['feasible']]
        source=metadata.get('reference_site',metadata.get('source_site'))
        def key(row):
            # C0 inherits the reference's sorted-site tie rule. Electrical
            # quantities are only hard guards, never its objective.
            blind=(row['site']!=source,row['site'])
            return blind if self.ranking=='C0' else (row['grid_peak'],*blind)
        rejected=[dict(site=r['site'],reason=r['reason']) for r in event['candidates'] if not r['feasible']]
        for row in sorted(feasible,key=key):
            if reserve:
                ok,reason=reservations.reserve(metadata['uid'],row['segments'],replace=True)
                if not ok:rejected.append(dict(site=row['site'],reason=reason));continue
                self.assignments[metadata['uid']]=service_integral(self.packet.sites,row['segments'],self.reference.begin)/4
            decision=dict(uid=metadata['uid'],action='START' if row['site']==source else 'PREPLACE',
                site=row['site'],start_seconds=now,nominal_end_seconds=now+max(metadata['t50_seconds'],1e-9),
                segments=row['segments'],status='ISOLATED_'+self.ranking+'_RANKED_SITE',
                additional_start_delay_seconds=0,source_reference_start_seconds=_receipt(receipt)['reference_start_seconds'],
                tracking=dict(grid_peak=row['grid_peak'],all_line_phase_rows=True),candidate_set_sha=event['candidate_set_sha'])
            return self._record(metadata,now,decision,began,len(event['candidates']),rejected)
        return self._record(metadata,now,dict(uid=metadata['uid'],action='QUEUE',status='NO_COMMON_FEASIBLE_SITE',
            reason='NO_COMMON_FEASIBLE_SITE',candidate_set_sha=event['candidate_set_sha']),began,len(event['candidates']),rejected)


class IsolatedReferenceController(CurrentEventJobEventController):
    """Same CurrentEvent operator, with the actual historical Known fallback.

The old original commands remain immutable. Effective execution references
are an explicitly separate ledger used by the existing corrective operator.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.original=original_driver();self.historical_commands=deepcopy(self.known_schedule)
        self.effective_references={};self.known_reference_events=[];self._source_known=False

    def _reference_decision(self,uid,now):
        if self.metadata[uid]['origin_unknown']:
            return deepcopy(self.policy.last_selection.get(uid,dict(uid=uid,action='QUEUE',status='COMMON_SELECTOR_REQUIRED')))
        decision=self.original.JobEventController._reference_decision(self,uid,now)
        return decision if self._source_known else self._guard_known(uid,now,decision)

    def _known_decision(self,uid,now):
        self._source_known=True
        try:decision=self.original.JobEventController._known_decision(self,uid,now)
        finally:self._source_known=False
        return self._guard_known(uid,now,decision)

    def _guard_known(self,uid,now,decision):
        if decision['action']=='QUEUE' or decision['start_seconds']>now:return decision
        if self.metadata[uid]['state']!='PENDING':return dict(uid=uid,action='QUEUE',status='PENDING_KNOWN_REQUIRED')
        reference=dict(site=decision['site'],start_seconds=decision['start_seconds'],
            historical_command_sha=digest(self.historical_commands.get(uid)),
            reference_contract='PR223_ACTUAL_REFERENCE_FALLBACK_NOT_OPTIMIZED_PLAN_EXECUTION')
        self.effective_references[uid]=reference
        self.known_reference_events.append(dict(uid=uid,time_seconds=now,source_decision=deepcopy(decision),
            effective_reference=deepcopy(reference),historical_command_modified=False))
        correction=self.corrective_commands.get(uid)
        if correction:
            if now<correction['ready_at_seconds']:return dict(uid=uid,action='QUEUE',status='KNOWN_DATA_TRANSFER_PREPARATION_IN_PROGRESS')
            decision=dict(decision,site=correction['actual_site'],start_seconds=now,action='PREPLACE')
        use=self.reservations.current_gpu_use(now,exclude=uid)
        if use[decision['site']]+self.requests[uid].gpu>self.ledger.capacities[decision['site']]:
            # The inherited implementation reads this separate execution
            # reference; known_schedule and policy.reference stay unchanged.
            prior=self.planning_commands
            self.planning_commands={**self.historical_commands,uid:reference}
            try:result=super()._corrective_decision(uid,now,use)
            finally:self.planning_commands=prior
            for row in self.corrective_audit:
                if row.get('uid')==uid:row.update(command_scope=reference['reference_contract'],
                    historical_planning_command_sha=reference['historical_command_sha'])
            return result
        return decision

    def admit(self,now):
        if now%900:return []
        if digest(self.known_schedule)!=self.frozen_known_sha:raise ValueError('ISOLATED_HISTORICAL_COMMAND_DRIFT')
        self.policy.require_bindings(self.policy.bindings)
        original=list(self.pending);remaining=[];starts=[]
        # PR223 B3 scans the original (submit_seconds, UID) queue. The D0
        # origin reclassification never creates a new Known-first priority.
        for row in sorted(original):
            uid=row[1];self.pending=[row];self.decisions.pop(uid,None)
            self.policy.observe(now,self.reservations.current_gpu_use(now,exclude=uid),self.metadata)
            one=JobEventController.admit(self,now);starts.extend(one);remaining.extend(self.pending)
            if one and uid in self.corrective_commands:
                self.corrective_commands[uid].update(actual_start_seconds=now)
                for entry in self.corrective_audit:
                    if entry.get('uid')==uid and entry.get('command_type')=='ACTUAL_CORRECTIVE_COMMAND':entry['actual_start_seconds']=now
        self.pending=remaining;heapq.heapify(self.pending)
        return starts

    def snapshot(self,now):
        result=JobEventController.snapshot(self,now)
        result['isolated_reference_state']=dict(scope=SCOPE,original_driver=record(ORIGINAL),
            historical_planning_commands_sha=self.frozen_known_sha,
            exact_optimized_Known_execution_claim=False,new_D0_plan_used=False,
            effective_Actual_reference_commands=deepcopy(self.effective_references),
            known_reference_events=deepcopy(self.known_reference_events),
            actual_corrective_commands=deepcopy(self.corrective_commands),corrective_audit=deepcopy(self.corrective_audit),
            future_Known_speculative_GPU_veto=False,Actual_global_MILP_calls=0)
        return result


def prepare_source():
    """Prepare original public contracts, then isolate private truth in driver."""
    from .production_case import STATIC
    from .planning_inputs import prepare_planning
    from .actual_validation import prepare_actual
    from .dday_initialization import load_dday_state
    freeze=read(BASE/'PLANNING_FREEZE.json');a=read(BASE/'A2/A_RESULT.json')
    if record(BASE/'A2/A_RESULT.json')['sha256']!='5fdef059bd52cbc1cd4cdca537e24473e0efd96001c012e7ac8303bb45f44b73':raise ValueError('PR223_A2_BYTES_DRIFT')
    if record(BASE/M2_REL)['sha256']!=M2_SHA:raise ValueError('PR223_M2_BYTES_DRIFT')
    mess=read(BASE/M2_REL)
    if digest({k:v for k,v in mess.items() if k!='plan_sha'})!=mess['plan_sha']:raise ValueError('PR223_M2_PLAN_SEAL_DRIFT')
    original_driver()
    with STATIC.open('rb') as stream:data=pickle.load(stream)
    stats=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/QOS_EMPIRICAL_STATS_STRICT.json')
    provider_sha=freeze['QoS_receipts']['provider_sha']
    prepared=prepare_planning(RAW,data,source_freeze=freeze['source_freeze'],strict_stats=stats,
        case_sha=freeze['case_sha'],provider_sha=provider_sha)
    if prepared['qos_provider'].export_ledger()!=freeze['QoS_receipts']['receipts']:
        raise ValueError('PR223_ORIGINAL_ISSUED_QOS_RECEIPTS_DRIFT')
    actual=prepare_actual(RAW,source_freeze=freeze['source_freeze'],strict_stats=stats,
        case_sha=freeze['case_sha'],provider_sha=provider_sha,initial_state_freeze=INITIAL,
        planning_provider=prepared['qos_provider'],planning_known_receipts=prepared['known_receipts'],arm='B3')
    state=load_dday_state(INITIAL,arm='B3')
    args,classification=reclassify_initial(actual['arguments'],state)
    if (classification['initial_Known'],classification['initial_Running'],classification['initial_Running_GPU'],
            classification['initial_Pending'],classification['future_Unknown'],classification['reclassified_initial_Unknown'])!=(1624,324,472,1300,696,78):
        raise ValueError('ISOLATED_REAL_POPULATION_DRIFT')
    issue=actual['issue_epoch_seconds']
    from .known_commands import compile_known_commands
    commands=compile_known_commands(a['selected_jobs'],slot_zero_seconds=issue)
    audit=dict(scope=SCOPE,original_initial=record(INITIAL),initial_semantic_sha=state['common_initial_state_sha'],
        historical_planning_freeze=record(BASE/'PLANNING_FREEZE.json'),A2=record(BASE/'A2/A_RESULT.json'),
        M2=record(BASE/M2_REL),MESS_plan_sha=mess['plan_sha'],original_driver=record(ORIGINAL),
        historical_source_freeze=freeze['source_freeze'],classification=classification,
        source_issue_seconds=issue,evaluation_begin_seconds=args['begin'],end_seconds=args['begin']+16*900,
        original_initial_sites_elapsed_GPU_preserved=True,prior_completed_preserved=len(state['historical_completed']),
        historical_completed_44_inactive=True,Known_execution_contract='PR223_ORIGINAL_REFERENCE_QUEUE_AND_PRE_DDAY_FALLBACK',
        historical_exact_Known_execution_certified=False,D0_A1_used=False,prefix_gate_used=False,
        MESS_fixed=True,Native_calls=0)
    return dict(arguments=args,actual=actual,initial=state,freeze=freeze,aidc=a,mess=mess,
        commands=commands,audit=audit,data=data)


def prepare_packet(source):
    from .production_case import ProductionPhysicalContext,planning_power,ARCHIVE
    from .sensitivity_policy import build_grid_packet
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage,voltage_for
    from .unified_contract import BINDING_FIELDS
    native=read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json');projection=read(ARCHIVE/'inputs/B2/2025-05-01/NATIVE_INPUT.json')
    bundle=deepcopy(native)
    for key in ('electrical_certificate','grid_outputs','route_table'):bundle[key]=deepcopy(projection[key])
    physical=ProductionPhysicalContext(source['freeze']['source_freeze'],read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),bundle)
    power,idle,swing,power_receipts=planning_power(bundle,physical.certificate)
    voltage=voltage_for(Stage.A2)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),voltage.lower_squared,voltage.upper_squared,
        True,stage=Stage.A2,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    freeze=source['freeze'];args=source['arguments'];a=source['aidc'];sites=tuple(sorted(args['capacities']))
    bindings={key:freeze.get(key) for key in BINDING_FIELDS}
    bindings.update(physical_sha=digest(dict(electrical=bundle['electrical_certificate'],thermal=physical.thermal)),
        time_axis_sha=digest(dict(begin=args['begin'],slots=16,step_seconds=900)),
        interface_sha=digest(dict(scope=SCOPE,Known='PR223_REFERENCE_FALLBACK',Unknown='RANKING_ONLY',MESS=source['mess']['plan_sha'])))
    known=np.array([a['known_site_GPU'][s] for s in sites],float).T
    unknown=np.array([a['nominal_site_GPU'][s] for s in sites],float).T
    p=np.array([a['AIDC_P_by_site'][s] for s in sites],float).T
    q=np.array([a['AIDC_Q_by_site'][s] for s in sites],float).T
    packet=build_grid_packet(physical.coefficients,power,swing,args['capacities'],a,source['mess'],authority,bindings,
        begin_seconds=args['begin'],known_gpu=known,power_factor=args['power_model'].power_factor,
        mess_validation=dict(plan_sha=source['mess']['plan_sha'],frozen_execution_validated=True),
        rack_compatibility={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in sites})
    reference=TrackingReference(known,unknown,idle*np.array([args['capacities'][s] for s in sites])+swing*(known+unknown),p,q,
        sites=sites,begin=args['begin'],commands=source['commands'],identity=dict(scope=SCOPE,
        C1_Power_Model_SHA=args['power_model'].authority_sha,historical_A2_anchor=a['aidc_anchor']))
    source['packet'],source['reference'],source['bindings']=packet,reference,bindings
    return source


def _csv(path,rows,fields):
    with Path(path).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})


def run_variant(source,label,output,*,slots=16):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    # Deep copy public and simulator state only in this private runner. It is
    # never attached to the policy/controller. Both runs receive the same bank.
    args=deepcopy(source['arguments']);args['end']=args['begin']+slots*900
    args['weather']=args['weather'][:slots]
    args['requests']=[r for r in args['requests'] if r.submit<args['end']]
    policy=RankingOnlyPolicy(source['reference'],source['packet'],ranking=label,bindings=source['bindings'],
        expected_bindings=source['bindings'],evidence_scope=SCOPE,
        source_identity=dict(study_case_sha=digest(source['audit']),historical_case_sha=source['freeze']['case_sha']))
    _bind_driver_current_c1(policy,args)
    policy.save(output/'FROZEN_POLICY.json')
    args.update(arm='B3',frozen_policy=policy,known_schedule=source['commands'],expected_bindings=source['bindings'])
    started=perf_counter();result=run_actual(**args,controller_class=IsolatedReferenceController)
    wall=perf_counter()-started
    np.savez_compressed(output/'ACTUAL_GPU_PQ.npz',sites=np.array(result['sites']),
        slot_start_seconds=np.arange(args['begin'],args['end'],900),GPU=result['occupancy_GPU'],
        compute_GPU=result['compute_occupancy_GPU'],**{k:result['physical'][k] for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')})
    for name,key in (('JOB_EVENT_LEDGER.json','job_event_ledger'),('QOS_ACTUAL_LEDGER.json','qos_ledger'),
        ('QOS_BUDGET_LEDGER.json','qos_budget_ledger'),('QUEUE_LEDGER.json','queue_ledger'),
        ('CC4_DEPLETION_LEDGER.json','cc4_depletion_ledger'),('PHYSICAL_RESERVATION_LEDGER.json','reservation_ledger')):
        write(output/name,result[key])
    state=result['carryout']['controller']['isolated_reference_state'];write(output/'KNOWN_REFERENCE_AND_CORRECTIVE_LEDGER.json',state)
    write(output/'UNKNOWN_CANDIDATE_LEDGER.json',policy.candidate_events)
    write(output/'UNKNOWN_DECISION_LEDGER.json',policy.audit)
    # Save public episode state, excluding the private remaining-service bank.
    write(output/'PUBLIC_EPISODE_STATE.json',result['carryout']['controller'])
    debit=[row['uid'] for row in result['cc4_depletion_ledger']]
    if len(debit)!=len(set(debit)):raise ValueError('ISOLATED_DUPLICATE_FORECAST_DEBIT')
    if any(row.get('uid') in {r['uid'] for r in source['initial']['running']+source['initial']['pending']} for row in result['cc4_depletion_ledger']):
        raise ValueError('ISOLATED_INITIAL_KNOWN_FORECAST_DEBIT')
    metrics=dict(policy=label,status='EXECUTED_16_SLOT_DIAGNOSTIC' if slots==16 else 'EXECUTED_FIRST_EVENT_CHECK',
        scope=SCOPE,slots=slots,begin_seconds=args['begin'],end_seconds=args['end'],
        diagnostic_case_sha=digest(source['audit']),historical_case_sha=source['freeze']['case_sha'],
        MESS_plan_sha=source['mess']['plan_sha'],policy_sha=policy.sha,receipt=result['receipt'],
        controller_P50_seconds=float(np.percentile(policy.times,50)) if policy.times else None,
        controller_P95_seconds=float(np.percentile(policy.times,95)) if policy.times else None,
        controller_max_seconds=max(policy.times,default=None),Actual_wall_seconds=wall,
        future_private_controller_reads=0,forecast_once_debit=True,global_MILP_calls=0,
        Native_calls=0,Fresh_AC='NOT_RUN',new_D0_A1_or_Full96_certificate=False)
    write(output/'ACTUAL_RESULT.json',metrics)
    return result,policy,metrics


def run_comparison(output,*,first_event=True):
    output=Path(output)
    if (output/'COMPARISON_COMPLETE.json').exists():raise FileExistsError('ISOLATED_COMPARISON_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True,exist_ok=True)
    with no_native() as attempts:
        code_files=[ROOT/'v42_integration'/name for name in ('isolated_unknown.py','actual.py','actual_validation.py',
            'aidc_sensitivity_runtime.py','aidc_resource_bridge.py','qos.py')]+[ROOT/'tools/run_v42_isolated_unknown.py']
        code_receipts=[record(path) for path in code_files]
        write(output/'ISOLATED_EXECUTED_CODE_SOURCE.json',dict(scope=SCOPE,files=code_receipts,
            no_existing_planning_source_changed=True,Native_calls=0))
        source=prepare_packet(prepare_source())
        write(output/'PR223_DIAGNOSTIC_PREPARED_SOURCE.json',source['audit'])
        args=source['arguments'];public=[dict(uid=r.uid,submit=r.submit,gpu=r.gpu,q50=r.q50,
            compatible=r.compatible,source_site=r.source_site,metadata=r.metadata) for r in args['requests']]
        same=dict(scope=SCOPE,diagnostic_case_sha=digest(source['audit']),public_request_sha=digest(public),
            initial_running_sha=digest([dict(uid=r.uid,site=s,start=t,gpu=r.gpu,q50=r.q50,metadata=r.metadata) for r,s,t in args['running']]),
            historical_Known_commands_sha=digest(source['commands']),Known_reference_engine=record(ORIGINAL),
            initial_semantic_sha=source['initial']['common_initial_state_sha'],CC4=source['freeze']['cc4_sha'],
            runtime=source['freeze']['runtime_sha'],Original_C1=args['power_model'].authority_sha,
            fixed_MESS_plan_sha=source['mess']['plan_sha'],policy_difference='UNKNOWN_SITE_RANKING_ONLY',
            candidate_algorithm='SHARED_CURRENT_GPU_RACK_SOURCE_DATA_ELECTRICAL',
            candidate_set_equality_scope='SAME_OBSERVED_STATE;DIVERGENT_POLICIES_MAY_CREATE_LATER_STATE_DIFFERENCES',
            public_Known=1624,future_Unknown=696,no_source_authority_added=True,Native_calls=0)
        write(output/'COMMON_RUN_INPUTS.json',same)
        future=[r for r in args['requests'] if r.submit>args['begin']]
        first=min(future,key=lambda r:(r.submit,r.uid))
        first_tick=900*math.ceil(first.submit/900)
        write(output/'FIRST_LEGAL_UNKNOWN_EVENT.json',dict(uid=first.uid,submit_seconds=first.submit,
            first_legal_control_seconds=first_tick,forced_unknowns_created=0))
        if first_event:
            first_slots=max(1,int((first_tick-args['begin'])/900)+1)
            for label in ('C0','C1'):
                first_result,_,_=run_variant(source,label,output/'FIRST_EVENT'/label,slots=first_slots)
                if (first_result['receipt']['capacity_violations'] or first_result['receipt']['dropped_jobs']
                        or first_result['receipt']['future_duration_controller_reads']
                        or first_result['receipt']['future_completion_controller_reads']):
                    raise ValueError('FIRST_LEGAL_EVENT_GATE_FAILED')
        variants={label:run_variant(source,label,output/label) for label in ('C0','C1')}
        comparisons=[];funnel=[];allocations={};grid=[];corrective=[]
        for label,(result,policy,metrics) in variants.items():
            unknown=[r for r in result['queue_ledger'] if r['origin_unknown']]
            allocations[label]={r['job_uid']:r for r in unknown}
            events=policy.candidate_events
            active={e['uid'] for e in events if e['start_eligible']}
            compatible={e['uid'] for e in events if e['compatible_sites']}
            multi={e['uid'] for e in events if len(e['compatible_sites'])>=2}
            gpu={e['uid'] for e in events if any(r['current_GPU_feasible'] and r['rack_feasible'] for r in e['candidates'])}
            hard={e['uid'] for e in events if any(r['electrical_pass'] for r in e['candidates'])}
            counts=dict(actual_submitted_Unknown=len(unknown),start_eligible_UIDs=len(active),
                currently_GPU_available_UIDs=len(gpu),compatible_ge1_UIDs=len(compatible),compatible_ge2_UIDs=len(multi),
                electrical_hard_pass_UIDs=len(hard),executed_UIDs=sum(r['admitted_time'] is not None for r in unknown),
                queue_UIDs=sum(r['admitted_time'] is None for r in unknown),
                capacity_rejected_UIDs=len({e['uid'] for e in events if any(r['reason']=='CURRENT_GPU_CAPACITY' for r in e['candidates'])}),
                electrical_rejected_UIDs=len({e['uid'] for e in events if any(str(r['reason']).startswith('CURRENT_OBSERVED_') for r in e['candidates'])}),
                authority_WAN_rejected_UIDs=len({e['uid'] for e in events if any(str(r['reason']).startswith('SOURCE_') and r['reason']!='SOURCE_START_ELIGIBILITY' for r in e['candidates'])}))
            funnel.extend(dict(policy=label,metric=k,unit='UID',value=v) for k,v in counts.items())
            funnel.append(dict(policy=label,metric='electrical_hard_pass_candidate_evaluations',unit='candidate-evaluation',
                value=sum(r['electrical_pass'] for e in events for r in e['candidates'])))
            allocation_rows=[]
            for event in events:
                realized=allocations[label][event['uid']]
                decision=next((r['decision'] for r in policy.audit if r['uid']==event['uid'] and r['time_seconds']==event['time_seconds']),{})
                allocation_rows.append(dict(policy=label,**event,selected_site=decision.get('site'),decision_action=decision.get('action'),
                    actual_site=realized.get('site'),actual_start_seconds=realized.get('admitted_time'),
                    observed_completion_seconds=realized.get('completion_observed_time')))
            _csv(output/(label+'_UNKNOWN_ALLOCATION_EVENTS.csv'),allocation_rows,
                ['policy','uid','time_seconds','gpu','start_eligible','compatible_sites','observed_GPU_by_site','candidate_set_sha',
                 'selected_site','decision_action','actual_site','actual_start_seconds','observed_completion_seconds','candidates'])
            corrective.extend(dict(policy=label,**row) for row in result['carryout']['controller']['isolated_reference_state']['corrective_audit'])
            cols=[source['packet'].control_names.index('aidc_load_kw['+s+']') for s in result['sites']]
            for t in range(16):
                pq=result['physical'];delta=(pq['PCC_P_kw'][t]-source['packet'].controls[t,cols])/source['packet'].p_slope[t]
                peak,bad=source['packet']._at_slot(t,delta)
                packet=source['packet'];coefficient=packet.coefficients[t];control=packet.controls[t].copy()
                control[cols]+=delta*packet.p_slope[t]
                fp=coefficient.flow_p_constant+coefficient.flow_p_matrix@control
                fq=coefficient.flow_q_constant+coefficient.flow_q_matrix@control
                line=(fp[:,None]*packet.cos+fq[:,None]*packet.sin)/packet.ap[t][:,None]
                line+=((packet.correction[t]@(control-coefficient.anchor))+packet.bias[t])[:,None]
                critical,face=np.unravel_index(np.argmax(line[packet.line_indices]),line[packet.line_indices].shape)
                branch=packet.branch_names[packet.line_indices[critical]]
                voltage=coefficient.voltage_constant+coefficient.voltage_matrix.T@control
                grid.append(dict(policy=label,slot=t,start_seconds=args['begin']+900*t,max_phase_line_loading=peak,
                    critical_branch_phase=branch,critical_polygon_face=int(face),
                    voltage_min_pu=float(np.sqrt(max(0.,voltage.min()))),voltage_max_pu=float(np.sqrt(max(0.,voltage.max()))),
                    violation_count=len(bad),violations=bad,affine_approximation_only=True,Fresh_AC_status='NOT_RUN'))
                for j,site in enumerate(result['sites']):comparisons.append(dict(policy=label,slot=t,site=site,
                    GPU=result['occupancy_GPU'][t,j],compute_GPU=result['compute_occupancy_GPU'][t,j],
                    IT_kw=pq['IT_kw'][t,j],PCC_P_kw=pq['PCC_P_kw'][t,j],PCC_Q_kvar=pq['PCC_Q_kvar'][t,j]))
        changed=[uid for uid in allocations['C0'].keys()&allocations['C1'].keys()
            if allocations['C0'][uid]['site']!=allocations['C1'][uid]['site']]
        for label in ('C0','C1'):
            funnel.append(dict(policy=label,metric='C0_C1_different_site_UIDs',unit='UID',value=len(changed)))
            # Changed compute GPUh comes from exact observed start/completion
            # intervals, clipped to the 4-hour comparison interval.
            byuid={r.uid:r for r in args['requests']}
            gpu_h=sum(byuid[u].gpu*max(0.,min(args['begin']+14400,allocations[label][u].get('completion_observed_time') or args['begin']+14400)
                -max(args['begin'],allocations[label][u]['admitted_time'] or args['begin']+14400))/3600 for u in changed)
            funnel.append(dict(policy=label,metric='Changed_compute_GPUh',unit='GPUh',value=gpu_h))
        _csv(output/'UNKNOWN_EVENT_ELIGIBILITY_FUNNEL.csv',funnel,['policy','metric','unit','value'])
        _csv(output/'KNOWN_CORRECTIVE_EVENTS.csv',corrective,['policy','uid','trigger_seconds','original_planned_site',
            'original_planned_start_seconds','actual_site','actual_start_seconds','ready_at_seconds','GPU_capacity_conflict',
            'status','reason','rejected_candidates','command_scope','historical_planning_command_sha','qos_preparation_budget_used_seconds'])
        _csv(output/'C0_C1_ACTUAL_GPU_PQ_COMPARISON.csv',comparisons,['policy','slot','site','GPU','compute_GPU','IT_kw','PCC_P_kw','PCC_Q_kvar'])
        _csv(output/'C0_C1_GRID_LOADING_COMPARISON.csv',grid,['policy','slot','start_seconds','max_phase_line_loading',
            'critical_branch_phase','critical_polygon_face','voltage_min_pu','voltage_max_pu','violation_count',
            'violations','affine_approximation_only','Fresh_AC_status'])
        result=dict(status='EXECUTED',scope=SCOPE,Native_calls=0,blocked_native_attempts=attempts,
            real_16_slot_replay=True,changed_site_UIDs=len(changed),changed_UIDs=changed,
            policies={label:v[2] for label,v in variants.items()},new_D0_or_Full96_certificate=False,
            C_REF_is_historical_not_C0=True,Fresh_AC='NOT_RUN_PENDING_SUPERVISOR_GATE')
        if any(record(rec['path'])!=rec for rec in code_receipts):raise ValueError('ISOLATED_EXECUTED_SOURCE_BYTES_CHANGED')
        write(output/'COMPARISON_COMPLETE.json',result)
        return result
