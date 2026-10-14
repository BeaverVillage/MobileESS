"""D0 public-state A inputs for the preserved complete native A formulation.

The legacy builder uses internal slots [24,120). Here that interval denotes
the D0 96-slot day. No earlier evaluation interval or old command is replayed.
This adapter never sees the simulator's future arrival/completion bank.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import dataclass,asdict,fields
from datetime import datetime,timezone
import math
from pathlib import Path

from .a_engine import ACase,PlanningGridContext,digest
from .dday_initialization import load_dday_state
from .may01_boundary_reconciliation import checked_json

D0_SCHEMA='D0_STATE_CONDITIONED_PLANNING_V1'
BACKLOG_SCHEMA='D0_KNOWN_BACKLOG_RESEARCH_V1'
NATIVE_OFFSET=24
SLOTS=96
MODEL='V10::T3_ISOTONIC_ROLLING14_calibrated'
INITIAL_SHA='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'
IDENTITY_FIELDS=('science_sha','case_sha','initial_state_sha','cc4_sha','runtime_sha')


def _sha(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _finite(value,*,nonnegative=True):
    return type(value) in (float,int) and math.isfinite(value) and (not nonnegative or value>=0)


def _sealed(value,field='contract_sha'):
    if not _sha(value.get(field)) or value[field]!=digest({k:v for k,v in value.items() if k!=field}):
        raise ValueError('D0_SEALED_AUTHORITY_DRIFT:'+field)


def _canonical(value):
    if isinstance(value,dict):
        if all(isinstance(k,str) for k in value):return {k:_canonical(v) for k,v in value.items()}
        return [[_canonical(k),_canonical(v)] for k,v in sorted(value.items(),key=lambda item:repr(item[0]))]
    if isinstance(value,(tuple,list)):return [_canonical(v) for v in value]
    return value


def input_fingerprint(data):
    return digest(_canonical(dict(bundle=data[0],jobs={u:asdict(j) for u,j in data[1].items()},
        bounds={u:asdict(b) for u,b in data[2].items()},resources=asdict(data[3]),raw=data[4],prep=data[7])))


def classify_d0_backlog(state,*,source_identity):
    begin=state['begin_epoch_seconds'];rows=[];seen=set()
    if not _finite(begin) or begin%900:raise ValueError('D0_PUBLIC_BOUNDARY_TIME_AXIS')
    if any(not _sha(source_identity.get(k)) for k in IDENTITY_FIELDS):raise ValueError('D0_SCIENCE_SOURCE_IDENTITY_REQUIRED')
    if source_identity['initial_state_sha']!=state['common_initial_state_sha']:
        raise ValueError('D0_APPROVED_INITIAL_SEMANTIC_DRIFT')
    for status,key in (('RUNNING','running'),('PENDING','pending')):
        for raw in state[key]:
            uid=raw['uid'];submit=raw['submit_seconds'];gpu=raw['gpu'];elapsed=raw['elapsed_compute_seconds'];q50=raw['q50']
            if uid in seen:raise ValueError('D0_INITIAL_UID_DUPLICATE')
            seen.add(uid)
            if (not _finite(submit) or submit>begin or type(gpu) is not int or gpu<=0
                    or not _finite(elapsed) or not _finite(q50) or q50<=0
                    or status=='PENDING' and elapsed!=0):
                raise ValueError('D0_PUBLIC_JOB_INPUT_INVALID:'+uid)
            if status=='RUNNING' and (raw['site'] not in state['capacities']
                    or not _finite(raw['observed_start_seconds']) or raw['observed_start_seconds']>begin
                    or begin-raw['observed_start_seconds']!=elapsed):
                raise ValueError('D0_RUNNING_SITE_ELAPSED_HISTORY_DRIFT:'+uid)
            meta=raw['metadata'];remaining=max(0.,q50-elapsed) if status=='RUNNING' else q50
            rows.append(dict(uid=uid,episode_id=raw['episode_id'],D0_status=status,D0_known=True,
                original_D1_origin_unknown=raw['origin_unknown'],reclassified_to_D0_known=raw['origin_unknown'],
                submit_seconds=submit,observed_at_seconds=begin,prior_wait_seconds=max(0.,begin-submit),
                fixed_running_site=raw['site'] if status=='RUNNING' else None,gpu=gpu,
                elapsed_compute_seconds=elapsed,Q50_total_seconds=q50,nominal_remaining_seconds=remaining,
                nominal_service_slots=math.ceil(remaining/900),Q50_expired_running=status=='RUNNING' and remaining==0,
                physical_GPU_at_D0=gpu if status=='RUNNING' else 0,
                physical_release_rule='OBSERVED_COMPLETION_ONLY',nominal_expiry_is_physical_completion=False,
                source_qos=meta.get('qos'),source_protected=meta.get('protected'),source_batch_eligible=meta.get('batch_eligible'),
                source_release_seconds=meta.get('release_seconds'),source_hard_earliest_start_seconds=meta.get('hard_earliest_start_seconds'),
                source_hard_latest_start_seconds=meta.get('hard_latest_start_seconds'),
                source_completion_deadline_seconds=meta.get('completion_deadline_seconds'),
                source_can_prestart_place=meta.get('can_prestart_place'),compatible_sites=deepcopy(raw['compatible_sites']),
                initial_source_member=raw.get('source_member'),initial_source_row=raw.get('source_row'),
                initial_source_row_sha=digest(raw),initial_semantic_sha=source_identity['initial_state_sha'],
                D0_science_sha=source_identity['science_sha'],D0_case_sha=source_identity['case_sha'],
                actual_future_completion_read=False,actual_remaining_runtime_read=False))
    completed={r.get('uid',r.get('job_uid')) for r in state.get('historical_completed',[])}
    if seen & completed:raise ValueError('D0_PRIOR_COMPLETED_REACTIVATED')
    counts=Counter(r['D0_status'] for r in rows)
    audit=dict(schema=D0_SCHEMA,status='PASS',scope='PUBLIC_D0_BACKLOG_INPUT_ONLY_NOT_A1_FULL_FEASIBILITY',
        identity=deepcopy(source_identity),issue_seconds=begin,slots=SLOTS,dt_seconds=900,
        initial_UIDs=len(rows),D0_known_UIDs=len(rows),running_UIDs=counts['RUNNING'],pending_UIDs=counts['PENDING'],
        initial_running_GPU=sum(r['physical_GPU_at_D0'] for r in rows),
        newly_D0_known_UIDs=sum(r['reclassified_to_D0_known'] for r in rows),
        newly_D0_known_running_UIDs=sum(r['reclassified_to_D0_known'] and r['D0_status']=='RUNNING' for r in rows),
        newly_D0_known_pending_UIDs=sum(r['reclassified_to_D0_known'] and r['D0_status']=='PENDING' for r in rows),
        prior_completed_UIDs_preserved=len(completed),future_unknown_UIDs_in_planning=0,
        Q50_expired_running_UIDs=sum(r['Q50_expired_running'] for r in rows),
        Q50_expired_running_GPU=sum(r['gpu'] for r in rows if r['Q50_expired_running']),
        private_future_used=False,Native_calls=0,Actual_calls=0,A1_FULL_feasible='NOT_RUN')
    return rows,audit


def validate_backlog_contract(contract,*,begin,end,identity):
    _sealed(contract)
    if (contract.get('schema')!=BACKLOG_SCHEMA or contract.get('issue_seconds')!=begin or contract.get('end_seconds')!=end
            or contract.get('initial_state_sha')!=identity['initial_state_sha']
            or contract.get('initial_backlog_optimization_authorized') is not True
            or contract.get('pending_source_compatible_placement_research_authorized') is not True
            or contract.get('site_scope')!='SOURCE_COMPATIBLE_ONLY'
            or contract.get('automatic_hard_deadline_extension') is not False
            or contract.get('source_protection_confirmed_by_research') is not False
            or contract.get('customer_SLA_claimed') is not False
            or contract.get('additional_intentional_delay_budget_seconds')!=0):
        raise ValueError('D0_EXPLICIT_BACKLOG_RESEARCH_CONTRACT_REQUIRED')
    return contract


def _hard_contract(raw,overrides):
    metadata=raw['metadata'];names=('release_seconds','hard_earliest_start_seconds','hard_latest_start_seconds','completion_deadline_seconds')
    contract={key:metadata.get(key) for key in names}
    supplied=overrides.get(raw['uid'],{})
    for key in names:
        if key in supplied:
            if contract[key] is not None and supplied[key]!=contract[key]:raise ValueError('D0_ORIGINAL_HARD_CONTRACT_REWRITE:'+raw['uid'])
            contract[key]=supplied[key]
        if contract[key] is not None and not _finite(contract[key]):raise ValueError('D0_NONFINITE_HARD_CONTRACT:'+raw['uid'])
    return contract


def compile_d0_known_data(initial_record,*,source_bundle,backlog_contract,source_identity,cc4_receipt,
        hard_contracts=None,evidence_scope='D0_ORIGINAL_SOURCE'):
    """Re-read the approved source; return unmaterialized complete-domain inputs.

    Native build/domain materialization and every solver call belong to the
    Supervisor's separately admitted operation. ``data[5:7]`` are empty here.
    """
    checked_json(initial_record);state=load_dday_state(initial_record['path'],arm='B1')
    if state['common_initial_state_sha']!=INITIAL_SHA:raise ValueError('D0_ORIGINAL_APPROVED_INITIAL_STATE_REQUIRED')
    native_records={record['sha256']:record for record in state['source_receipts']
        if Path(record['path']).name=='NATIVE_INPUT_TEMPLATE_B1.json'}
    if len(native_records)!=1:raise ValueError('D0_ORIGINAL_NATIVE_SOURCE_RECEIPT_REQUIRED')
    native_record=next(iter(native_records.values()))
    original_native=checked_json(native_record)
    comparable=deepcopy(source_bundle);projection_record=comparable.pop('D0_current_physical_projection',None)
    physical_merge=[]
    if projection_record is not None:
        expected_path=Path(native_record['path']).parents[2]/'inputs/B2'/original_native['day']/'NATIVE_INPUT.json'
        if Path(projection_record['path']).resolve()!=expected_path.resolve():
            raise ValueError('D0_ORIGINAL_DAY_PHYSICAL_PROJECTION_PATH_DRIFT')
        projection=checked_json(projection_record)
        for field in ('electrical_certificate','grid_outputs','route_table'):
            if digest(comparable.get(field))!=digest(projection[field]):
                raise ValueError('D0_APPROVED_CURRENT_PHYSICAL_FIELD_DRIFT:'+field)
            if field=='route_table' and any(original_native[field][key]!=projection[field][key] for key in ('sha256','bytes')):
                raise ValueError('D0_ORIGINAL_DAY_ROUTE_NUMERIC_AUTHORITY_DRIFT')
            physical_merge.append(dict(field=field,original_value_sha=digest(original_native[field]),
                current_value_sha=digest(projection[field]),source_record=deepcopy(projection_record)))
            comparable[field]=deepcopy(original_native[field])
    if digest(original_native)!=digest(comparable):
        raise ValueError('D0_ORIGINAL_NATIVE_SOURCE_BUNDLE_DRIFT')
    if source_bundle['capacities']!=state['capacities']:raise ValueError('D0_ORIGINAL_CAPACITY_DRIFT')
    rows,audit=classify_d0_backlog(state,source_identity=source_identity)
    if (len(rows),audit['running_UIDs'],audit['pending_UIDs'],audit['initial_running_GPU'])!=(1624,324,1300,472):
        raise ValueError('D0_APPROVED_324_472_1300_POPULATION_DRIFT')
    audit['original_native_source_record']=deepcopy(native_record)
    audit['exact_original_production_current_physical_merge']=physical_merge
    return _compile_d0_known_data(state,rows,audit,source_bundle,backlog_contract,source_identity,cc4_receipt,
        hard_contracts or {},initial_record,evidence_scope)


def _compile_d0_known_data(state,rows,audit,source_bundle,contract,identity,cc4_receipt,hard_contracts,initial_record,evidence_scope):
    from v42_job_capability import Job,Resources
    from v42_native.service import boundary
    import numpy as np
    begin=state['begin_epoch_seconds'];end=begin+SLOTS*900
    validate_backlog_contract(contract,begin=begin,end=end,identity=identity)
    _sealed(cc4_receipt,'forecast_receipt_sha')
    if (cc4_receipt.get('issue_seconds')!=begin or cc4_receipt.get('day_begin_seconds')!=begin
            or cc4_receipt.get('conditioned_on_initial_known') is not True
            or not _finite(cc4_receipt.get('forecast_source_available_seconds'))
            or cc4_receipt['forecast_source_available_seconds']>begin
            or cc4_receipt.get('actual_future_UIDs_used') is not False):
        raise ValueError('D0_CAUSAL_STATE_CONDITIONED_CC4_RECEIPT_REQUIRED')
    q50=np.asarray(cc4_receipt['Q50_GPUh'],float);q90=np.asarray(cc4_receipt['Q90_GPUh'],float)
    if q50.shape!=(24,) or q90.shape!=(24,) or not np.isfinite(q50).all() or not np.isfinite(q90).all() or np.any(q50<0) or np.any(q90<q50):
        raise ValueError('D0_FROZEN_CC4_MASS_AXIS')
    if cc4_receipt.get('cc4_sha')!=identity['cc4_sha'] or cc4_receipt.get('runtime_sha')!=identity['runtime_sha']:
        raise ValueError('D0_CC4_RUNTIME_SOURCE_IDENTITY_DRIFT')
    if not np.array_equal(q50,np.asarray(source_bundle['C0_Q50'],float)) or not np.array_equal(q90,np.asarray(source_bundle['C0_Q90'],float)):
        raise ValueError('D0_CC4_FROZEN_SOURCE_MASS_DRIFT')
    bundle=deepcopy(source_bundle);bundle['known_population']=[]
    bundle.update(schema=D0_SCHEMA,issue_time=datetime.fromtimestamp(begin,timezone.utc).isoformat(),
        C0_Q50=q50.tolist(),C0_Q90=q90.tolist(),D0_source_identity=deepcopy(identity),
        D0_internal_slot_offset=NATIVE_OFFSET,D0_prefix_evaluation=False)
    wan=bundle['WAN'];caps=state['capacities']
    racks={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in caps}
    if any(not limits or set(limits)!=set(state['rack_compatibility'][s]) for s,limits in racks.items()):
        raise ValueError('D0_ORIGINAL_RACK_COMPATIBILITY_DRIFT')
    resources=Resources(deepcopy(caps),racks,{(link,t+NATIVE_OFFSET):value for link,values in wan['link_capacity_bytes_15min'].items()
        for t,value in enumerate(values)}, {(p['source'],p['destination']):tuple(p['links']) for p in wan['paths']},
        NATIVE_OFFSET+SLOTS,wan['bytes_per_gpu'],{},{},{},restart_slots=1,max_active_transfers=wan['maximum_active_transfers'])
    jobs={};bounds={};raw={};windows={};receipts={};no_window=[];classification={r['uid']:r for r in rows}
    for status,key in (('RUNNING','running'),('PENDING','pending')):
        for original in state[key]:
            uid=original['uid'];metadata=original['metadata'];gpu=original['gpu'];elapsed=original['elapsed_compute_seconds']
            remaining=classification[uid]['nominal_remaining_seconds'];slots=math.ceil(remaining/900)
            compatible=tuple(s for s in original['compatible_sites'] if s in caps and gpu<=caps[s] and gpu<=max(racks[s]))
            if not compatible or (status=='RUNNING' and original['site'] not in compatible):raise ValueError('D0_SOURCE_GANG_SITE_RACK_INCOMPATIBLE:'+uid)
            hard=_hard_contract(original,hard_contracts)
            if status=='RUNNING':starts=(NATIVE_OFFSET,);site=original['site'];sites=(site,)
            else:
                source_representation=metadata.get('representation_starts_seconds',[])
                earliest=max(begin,original['submit_seconds'],hard['release_seconds'] or begin,hard['hard_earliest_start_seconds'] or begin)
                latest=min(end-900,hard['hard_latest_start_seconds'] if hard['hard_latest_start_seconds'] is not None else end-900)
                starts=tuple(NATIVE_OFFSET+t for t in range(SLOTS) if earliest<=begin+t*900<=latest
                    and begin+t*900 in source_representation
                    and (hard['completion_deadline_seconds'] is None or begin+t*900+remaining<=hard['completion_deadline_seconds']))
                if metadata.get('protected') is True or metadata.get('qos') in ('high','urgent'):
                    # The backlog study does not create an original protected
                    # customer's temporal or placement authorization.
                    original_starts=metadata.get('source_authorized_D0_starts_seconds',[])
                    original_sites=metadata.get('source_authorized_initial_sites',[])
                    starts=tuple(s for s in starts if begin+(s-NATIVE_OFFSET)*900 in original_starts)
                    compatible=tuple(s for s in compatible if s in original_sites)
                    if not compatible:starts=()
                site=compatible[0] if compatible else original['compatible_sites'][0];sites=compatible
                if not starts:no_window.append(uid)
            reference=starts[0] if starts else NATIVE_OFFSET
            # A research base queue window is not the source empirical QoS
            # budget or the optional later 60-minute intentional-delay policy.
            base_budget=max((s-reference)*900 for s in starts) if starts else 0.
            receipt=dict(uid=uid,policy_id=contract['policy_id'],issue_seconds=begin,origin_unknown=False,
                reference_start_seconds=begin+(reference-NATIVE_OFFSET)*900,
                allowed_starts_seconds=[begin+(s-NATIVE_OFFSET)*900 for s in starts],budget_seconds=base_budget,
                base_backlog_scheduling_window_seconds=base_budget,source_QoS_budget_seconds_preserved=0,
                additional_intentional_delay_budget_seconds=0,source_qos=metadata.get('qos'),source_protected=metadata.get('protected'),
                source_batch_eligible=metadata.get('batch_eligible'),hard_contract=hard,backlog_contract_sha=contract['contract_sha'],
                customer_SLA_claimed=False,automatic_hard_deadline_extension=False,source_protection_confirmed_by_research=False,
                D0_state_source_sha=digest(original),D0_science_sha=identity['science_sha'],D0_case_sha=identity['case_sha'],
                status='AUTHORIZED_D0_BASE_BACKLOG_WINDOW' if starts else 'NO_SOURCE_LEGAL_D0_START_WINDOW')
            receipt['receipt_sha']=digest(receipt);receipts[uid]=receipt;windows[uid]=starts
            record=dict(job_uid=uid,state=status,planning_eligible=slots>0,GPU_gang=gpu,V10_Q50_total_seconds=original['q50'],
                elapsed_seconds=elapsed,nominal_remaining_seconds=remaining,exact_service_seconds=remaining,service_slots=slots,
                planning_site=site,reference_start_if_authorized=reference,reference_end=reference+slots,
                risk_nominal_completion_issue_slot=reference+math.ceil((original['q50']-elapsed)/900) if status=='RUNNING' else reference+slots,
                runtime_authority=MODEL,duration_authority=MODEL,compatible_sites=list(sites),known_at_issue=True,
                issue_time=bundle['issue_time'],submit_time=datetime.fromtimestamp(original['submit_seconds'],timezone.utc).isoformat(),
                current_site_if_running=site if status=='RUNNING' else None,cohort=metadata.get('source_cohort_evidence',''),
                original_D1_origin_unknown=original['origin_unknown'],origin_unknown=False,
                can_timeshift=False,can_prestart_place=metadata.get('can_prestart_place'),can_checkpoint_migrate=False,
                D0_backlog_contract_sha=contract['contract_sha'],D0_source_row_sha=digest(original))
            raw[uid]=record;bundle['known_population'].append(record)
            classification[uid].update(legal_D0_start_seconds=receipt['allowed_starts_seconds'],D0_backlog_contract_sha=contract['contract_sha'],
                base_backlog_scheduling_window_seconds=base_budget,additional_intentional_delay_budget_seconds=0,
                original_hard_contract=hard,no_source_legal_D0_start_window=not starts,
                initial_source_path=initial_record['path'],initial_source_file_byte_sha=initial_record['sha256'],
                D0_CC4_forecast_receipt_sha=cc4_receipt['forecast_receipt_sha'],D0_runtime_sha=identity['runtime_sha'])
            if status=='RUNNING' and slots==0:
                resources.fixed_gpu[site,NATIVE_OFFSET]=resources.fixed_gpu.get((site,NATIVE_OFFSET),0)+gpu
            elif starts:
                jobs[uid]=Job(uid,status,NATIVE_OFFSET,NATIVE_OFFSET,reference,site,slots,gpu,
                    qos=metadata.get('qos') or 'UNCONFIRMED',protected=metadata.get('protected') is True,
                    initial_sites=sites,checkpoint_authorized=False,elapsed_seconds=elapsed,duration_authority=MODEL,
                    qos_policy_id=contract['policy_id'],qos_receipt_sha=receipt['receipt_sha'],qos_allowed_starts=starts,
                    qos_budget_seconds=base_budget,is_observed=True,batch_eligible=metadata.get('batch_eligible') is True)
                bounds[uid]=boundary(jobs[uid],starts,contract['contract_sha'],identity['runtime_sha'],H=NATIVE_OFFSET+SLOTS)
    bundle['reference']=dict(policy_id='D0_OBJECTIVE_REFERENCE_ONLY_NOT_FCFS_EXECUTION',
        rows=[dict(uid=uid,reference_start=job.reference_start,reference_site=job.reference_site) for uid,job in jobs.items()])
    prep=dict(classes={},domain_authority='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN',
        full_migration_domain_active=False,preserve_singleton_mixed_flow=(),D0_unmaterialized_domains=True,
        checkpoint_domain_scope='HOLD_UNTIL_SEPARATE_SOURCE_ACTION_AUTHORITY',
        all_initial_UIDs_preserved=True,complete_start_windows_defined=True,source_identity=deepcopy(identity))
    data=(bundle,jobs,bounds,resources,raw,{},{},prep)
    audit.update(initial_record=deepcopy(initial_record),evidence_scope=evidence_scope,backlog_contract_sha=contract['contract_sha'],
        cc4_forecast_receipt_sha=cc4_receipt['forecast_receipt_sha'],positive_remaining_native_jobs=len(jobs),
        no_legal_D0_start_window_UIDs=no_window,source_hard_deadlines_extended=False,
        status='PASS' if not no_window else 'NOT_CERTIFIED',domain_materialization='NOT_RUN',native_model_build='NOT_RUN',
        original_native_internal_slots=[NATIVE_OFFSET,NATIVE_OFFSET+SLOTS],D0_evaluation_slots=[0,SLOTS],
        old_six_hour_prefix_required=False,old_A1_A2_commands_used=False,Known_reference_used_as_FCFS=False,
        initial_fixed_Q50_expired_GPU=sum(resources.fixed_gpu.values()),
        nominal_Q50_is_not_actual_occupancy=True,achieved_reserve_forced_to_zero=False,
        equations='Known+Unknown_Q50+achieved_CC4_reserve+achieved_runtime_reserve<=capacity',
        source_Q50_scaled=False,source_CC4_scaled=False,full_remaining_service_tail_preserved=True)
    audit.update(rack_contract='NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_DUPLICATES_NOT_SUMMED',
        checkpoint_migration='HOLD_BASIC_PHASE_SOURCE_PUBLIC_CAPABILITY_UNCONFIRMED',
        unrestricted_original_migration_equivalence=False,
        native_domain_scope='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN')
    original_known={row['job_uid'] for row in source_bundle.get('known_population',[])}
    completed={row.get('uid',row.get('job_uid')) for row in state.get('historical_completed',[])}
    audit.update(D1_source_known_UIDs=len(original_known),D1_known_UIDs_already_completed_by_D0=len(original_known&completed),
        D0_active_known_change_vs_D1_source_count=len(rows)-len(original_known),
        future_Unknown_UID_bank_read=False,initial_Q50_expired_fixed_current_slot_GPU=sum(resources.fixed_gpu.values()))
    audit['a_input_sha']=input_fingerprint(data)
    return data,rows,audit,receipts,windows


@dataclass
class D0ACase(ACase):
    d0_input_audit: dict | None = None


def current_hard_runtime_overlap(bundle):
    """Original exposure of expired gangs already physically held at D0."""
    from v42_final.reserve import risk_exposure
    overlap=defaultdict(float)
    for row in bundle['known_population']:
        if row['state']=='RUNNING' and row['service_slots']==0:
            exposure=risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),
                row['planning_site'],bundle['runtime_survival_kernel'],[NATIVE_OFFSET])
            for key,value in exposure.items():overlap[key]+=bundle['runtime_reserve_gamma']*value
    return dict(overlap)


@dataclass
class D0PlanningGridContext(PlanningGridContext):
    current_hard_runtime_overlap_GPU: dict | None = None

    def bind(self,model,bundle,known,risk,*,stage):
        if bundle.get('schema')!=D0_SCHEMA or bundle.get('D0_internal_slot_offset')!=NATIVE_OFFSET:
            raise ValueError('D0_GRID_PUBLIC_STATE_COORDINATE_REQUIRED')
        overlap=current_hard_runtime_overlap(bundle)
        adjusted=dict(risk)
        for key,value in overlap.items():
            if key not in adjusted:raise ValueError('D0_CURRENT_RUNTIME_TARGET_AXIS_DRIFT')
            # Already observed physical occupancy is not a second uncertainty
            # reservation target. This is risk_exposure(current_hard_slot=24)
            # at the public boundary; all future original targets are intact.
            adjusted[key]=adjusted[key]-value
        self.current_hard_runtime_overlap_GPU=overlap
        result=super().bind(model,bundle,known,adjusted,stage=stage)
        self.planning_arrays['risk_original']=risk
        self.planning_arrays['current_hard_runtime_overlap_GPU']=overlap
        return result


def build_d0_native_model(case,*,build_admission):
    """Supervisor-only admitted Native0 full matrix construction (no optimize)."""
    if not isinstance(case,D0ACase) or case.d0_input_audit is None or case.d0_input_audit['status']!='PASS':
        raise ValueError('D0_A_INPUT_GATE_REQUIRED')
    if (case.d0_input_audit.get('a_input_sha')!=input_fingerprint(case.data)
            or case.data[0]['D0_source_identity']!=case.d0_input_audit['identity']):
        raise ValueError('D0_A_INPUT_SOURCE_OR_CASE_DRIFT')
    if (build_admission.get('status')!='PASS' or build_admission.get('operation')!='D0_A_NATIVE0_BUILD'
            or build_admission.get('case_sha')!=case.case_sha or build_admission.get('concurrent_heavy_solver') is not False):
        raise ValueError('D0_SUPERVISOR_NATIVE0_BUILD_ADMISSION_REQUIRED')
    if case.stage not in ('A1','A2') or case.arm not in ('B1','B3'):raise ValueError('D0_ORIGINAL_A_ARM_STAGE_REQUIRED')
    fixed_mess=case.grid.fixed_mess
    if case.stage=='A2' and (not fixed_mess or not all(k in fixed_mess for k in ('P_by_site','Q_by_site','routes','SOC','Mode','plan_sha'))):
        raise ValueError('D0_A2_COMPLETE_FIXED_MESS_REQUIRED')
    if fixed_mess and fixed_mess.get('plan_sha')!=digest({k:v for k,v in fixed_mess.items() if k!='plan_sha'}):
        raise ValueError('D0_FIXED_MESS_ANCHOR_SHA_DRIFT')
    if not isinstance(case.grid,D0PlanningGridContext):
        case.grid=D0PlanningGridContext(**{field.name:getattr(case.grid,field.name) for field in fields(PlanningGridContext)})
    from .a_engine import authorized_data
    from v42_root.native import build
    from v42_native.voltage import Stage
    from v42_two.contract import aidc_groups,passes
    data,domains=authorized_data(case)
    # The legacy geometry producer reports the full geometry it was given.
    # D0 basic-phase source actions exclude unconfirmed checkpoint rights;
    # preserve that scope rather than relabel it as the old unrestricted set.
    data[7]['full_migration_domain_active']=False
    data[7]['domain_authority']='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN'
    data[7]['checkpoint_domain_scope']='HOLD_UNTIL_SEPARATE_SOURCE_ACTION_AUTHORITY'
    class Context:
        folder=Path(case.output)
        def check(self):pass
        def progress(self,value):
            if case.progress:case.progress(value)
    Context.folder.mkdir(parents=True,exist_ok=True)
    stage=Stage.A2 if case.stage=='A2' else Stage.A1
    model,units,levels,controls,bindings=build(Context(),data,'F2-CRA',grid_context=case.grid,stage=stage)
    try:
        if [n for n,_ in levels]!=['rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes']:
            raise ValueError('D0_ORIGINAL_OBJECTIVE_LAYER_DRIFT')
        groups=aidc_groups(levels,units,data);ordered=passes(groups)
        receipt=dict(status='PASS',scope='D0_ORIGINAL_COMPLETE_NATIVE_MATRIX_NATIVE0_NOT_FULL_FEASIBLE',
            stage=case.stage,arm=case.arm,case_sha=case.case_sha,source_identity=case.d0_input_audit['identity'],
            input_MESS_anchor=fixed_mess['plan_sha'] if fixed_mess else None,
            rows=model.NumConstrs,columns=model.NumVars,nonzeros=model.NumNZs,Native_calls=0,
            A1_FULL_feasible='NOT_RUN',original_objective_layers=[n for n,_ in levels],
            original_P1_P2_passes=[dict(group=g,component=n,status='NOT_RUN') for g,n,_ in ordered],
            full_physical_domains=len(domains),domain_authority='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN',
            omitted_authorized_basic_native_options=0,unrestricted_original_migration_equivalence=False,
            Phase_I='NOT_RUN',pricing='FULL_BASIC_DOMAIN_MATERIALIZED_NO_OTHER_DOMAIN_PRICING_CERTIFICATE',
            original_electrical_rows_preserved=True,original_capacity_WAN_rack_rows_preserved=True,
            complete_remaining_service_and_carry_preserved=True,old_bound_or_point_transferred=False,
            reserve_achieved_is_solver_decision=True)
        receipt.update(current_hard_runtime_target_overlap_removed_GPU=sum(case.grid.current_hard_runtime_overlap_GPU.values()),
            current_hard_runtime_target_overlap_by_site=[dict(site=site,native_slot=t,GPU=value)
                for (site,t),value in sorted(case.grid.current_hard_runtime_overlap_GPU.items())],
            runtime_exposure_boundary_rule='EXCLUDE_OBSERVED_CURRENT_HARD_SLOT_ONLY',
            future_runtime_risk_coefficients_unchanged=True)
        return model,units,levels,controls,bindings,data,receipt
    except Exception:
        model.dispose();raise


def _export_d0_point(case,built,point,selected):
    import numpy as np
    from .a_seed import full_replay,value_at
    from v42_job_capability import Option,validate
    model,units,levels,controls,bindings,data,matrix_receipt=built
    replay=full_replay(model,point)
    if not replay['PASS']:raise ValueError('D0_ORIGINAL_FULL_ROW_POINT_REPLAY_FAIL')
    if set(selected)!=set(data[1]):raise ValueError('D0_SELECTED_FULL_SERVICE_UID_DROP')
    planned_gpu=dict(data[3].fixed_gpu)
    for uid,record in selected.items():
        option=dict(record);option['segments']=tuple(tuple(row) for row in option['segments'])
        option['wan']=tuple(tuple(row) for row in option.get('wan',()))
        validate(data[1][uid],Option(**option),data[2][uid],data[3])
        for site,start,end in option['segments']:
            for tick in range(start,end):planned_gpu[site,tick]=planned_gpu.get((site,tick),0.)+data[1][uid].gpu
    arrays=case.grid.planning_arrays;sites=tuple(data[3].capacities)
    error=max((abs(value_at(variable,point)-planned_gpu.get(key,0.)) for key,variable in arrays['known'].items()),default=0.)
    if error>1e-5:raise ValueError('D0_SELECTED_KNOWN_CURRENT_GPU_COUPLING_DRIFT')
    values=[[value_at(variable,point) for variable in row] for row in controls]
    p={site:[values[t][coefficient.control_names.index('aidc_load_kw['+site+']')]
        for t,coefficient in enumerate(case.grid.coefficients)] for site in sites}
    def site_matrix(family):return {site:[value_at(arrays[family][site,t+NATIVE_OFFSET],point) for t in range(SLOTS)] for site in sites}
    hold={uid:dict(site=record['planning_site'],gpu=record['GPU_gang'],elapsed_seconds=record['elapsed_seconds'],
        Q50_expired=True,physical_release_rule='OBSERVED_COMPLETION_ONLY',new_START_command=False)
        for uid,record in data[4].items() if record['state']=='RUNNING' and record['service_slots']==0}
    result=dict(FULL_feasible=True,FULL_max_residual=replay['FULL_max_residual'],FULL_point_replay=replay,
        selected_jobs=selected,initial_Q50_expired_physical_holds=hold,
        all_initial_UIDs_accounted_for=set(selected)|set(hold)==set(data[4]),
        initial_Q50_expired_GPU=sum(row['gpu'] for row in hold.values()),
        selected_Known_GPU_coupling_replay=dict(PASS=True,maximum_residual=error,includes_original_fixed_GPU=True),
        controls=values,AIDC_P_by_site=p,AIDC_Q_by_site={site:(np.asarray(values)*np.tan(np.arccos(.95))).tolist() for site,values in p.items()},
        anonymous_resource_envelope=[dict(slot_start=t*900.,slot_end=(t+1)*900.,site=site,
            gpu_capacity=max(0.,value_at(arrays['anonymous'][site,t+NATIVE_OFFSET],point)),
            source_variable=f'anonymous_GPU[{site},{t}]',carryout_end=86400.) for t in range(SLOTS) for site in sites],
        nominal_site_GPU=site_matrix('anonymous'),reserve_site_GPU=site_matrix('reserve'),known_site_GPU=site_matrix('known'),
        reserve_site_GPU_meaning='CC4_ARRIVAL_TARGET_DISTRIBUTION_NOT_CAPACITY_BACKED_ACHIEVED_RESERVE',
        achieved_CC4_reserve_site_GPU={site:[value_at(arrays['headroom']['CC4_achieved'][site,t+NATIVE_OFFSET],point) for t in range(SLOTS)] for site in sites},
        achieved_runtime_reserve_site_GPU={site:[value_at(arrays['headroom']['runtime_achieved'][site,t+NATIVE_OFFSET],point) for t in range(SLOTS)] for site in sites},
        runtime_reserve_target_site_GPU=site_matrix('risk'),
        CC4_reserve_shortfall_GPU_slots=value_at(arrays['headroom']['CC4_shortfall'],point),
        runtime_reserve_shortfall_GPU_slots=value_at(arrays['headroom']['runtime_shortfall'],point),resource_sites=list(sites),
        rho=value_at(dict(levels)['rho'],point),original_physical_PQ_mapping=True,Actual_future_UIDs_used=False,
        D0_issue_seconds=case.d0_input_audit['issue_seconds'],D0_internal_slot_offset=NATIVE_OFFSET,
        native_command_epoch_conversion='D0_issue_seconds+(native_start_slot-24)*900')
    for name,family,field in (('CC4_service','nominal','x'),('CC4_carryout','nominal','carryout'),
            ('CC4_reserve_service','reserve','x'),('CC4_reserve_carryout','reserve','carryout')):
        result[name]={str(key):value_at(variable,point) for key,variable in bindings['timing'][family][field].items()}
    result['aidc_anchor']=digest({k:result[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')})
    result['resource_distribution_sha']=digest({k:result[k] for k in ('nominal_site_GPU','reserve_site_GPU','known_site_GPU','resource_sites','CC4_reserve_service','CC4_reserve_carryout')})
    return result


def solve_d0_native_model(built,*,case,budget,cap_seconds):
    """One budgeted D0 pilot; later original P2 passes require certified P1.

    Full feasible incumbents and current-matrix objective closure are separate.
    The original matrix/domains remain in place if the bounded pilot times out.
    No reference queue or historical solution supplies the returned incumbent.
    """
    import json
    import numpy as np
    import gurobipy as gp
    from .a_seed import full_replay
    from v42_root.native import reconstruct
    from v42_two.contract import aidc_groups,passes,P1_EPS,COMPONENT_EPS,integer_certificate
    from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
    from v42_b3_joint.numerical_policy import apply_native_precision
    model,units,levels,controls,bindings,data,matrix_receipt=built
    if (not isinstance(case,D0ACase) or matrix_receipt.get('status')!='PASS' or matrix_receipt['case_sha']!=case.case_sha
            or matrix_receipt['source_identity']!=case.d0_input_audit['identity']
            or not _finite(cap_seconds) or cap_seconds<=0 or budget.remaining()<=0):
        raise ValueError('D0_NATIVE_PILOT_SOURCE_MATRIX_OR_BUDGET_GATE')
    output=Path(case.output);output.mkdir(parents=True,exist_ok=True)
    if (output/'A_RESULT.json').exists():raise FileExistsError('D0_EXISTING_A_RESULT_MUST_NOT_BE_OVERWRITTEN')
    policy=solver_policy(gp);apply_policy(model,policy,gp)
    numerical=apply_native_precision(model,day=data[0]['day'],stage=case.stage,component='ORIGINAL_P1')
    model.Params.OutputFlag=1;model.Params.LogFile=str(output/'NATIVE_SOLVER.log')
    remaining_before=budget.remaining();ordered=passes(aidc_groups(levels,units,data));trace=[]
    point=None;selected=None;p1_bound=None;p1_closed=False;completed=False
    prior_context=getattr(budget,'stage_context',None);had_context=hasattr(budget,'stage_context')
    try:
        for index,(group,name,expression) in enumerate(ordered):
            available=min(cap_seconds-(remaining_before-budget.remaining()),budget.remaining())
            if available<=.001 or index and not p1_closed:
                trace.append(dict(group=group,component=name,status='NOT_RUN',reason='P1_NOT_CERTIFIED_OR_PILOT_BUDGET_EXHAUSTED'))
                continue
            model.setObjective(expression,gp.GRB.MINIMIZE);model.update()
            budget.stage_context=dict(prior_context or {},D0_science_sha=case.d0_input_audit['identity']['science_sha'],
                D0_case_sha=case.d0_input_audit['identity']['case_sha'],stage_case_sha=case.case_sha,
                source_input_sha=case.d0_input_audit['a_input_sha'],component=name,
                bound_scope='CURRENT_COMPLETE_D0_FIXED_MESS_A_MATRIX_ONLY',old_bound_or_point_transferred=False)
            call=budget.solve(model,label='D0_'+case.stage+'_ORIGINAL_'+('P1' if index==0 else 'P2_'+name),cap=available)
            bound=float(model.ObjBound);bound=bound if math.isfinite(bound) else None
            candidate=None;candidate_selected=None;replay=None
            if model.SolCount:
                candidate=np.asarray(model.getAttr('X'),float);replay=full_replay(model,candidate)
                if replay['PASS']:
                    candidate_selected=reconstruct(units,data)
                    point=candidate;selected=candidate_selected
            objective=float(model.ObjVal) if model.SolCount else None
            closed=bool(replay and replay['PASS'] and (model.Status==gp.GRB.OPTIMAL if index==0 else integer_certificate(objective,bound)))
            trace.append(dict(group=group,component=name,status=int(model.Status),Native_call=call,
                incumbent=objective,valid_current_matrix_bound=bound,original_FULL_point_replay=replay,
                component_optimality_certified=closed,closure_scope='CURRENT_COMPLETE_D0_FIXED_MESS_A_MATRIX_ONLY'))
            if index==0:p1_bound=bound;p1_closed=closed
            if not closed:
                for later_group,later_name,_ in ordered[index+1:]:
                    trace.append(dict(group=later_group,component=later_name,status='NOT_RUN',reason='PREVIOUS_LEX_COMPONENT_NOT_CERTIFIED'))
                break
            if index<len(ordered)-1:
                epsilon=P1_EPS if index==0 else COMPONENT_EPS
                model.addConstr(expression<=objective+epsilon,name='D0_original_lex_lock_'+name)
                model.update()
            else:completed=True
    finally:
        if had_context:budget.stage_context=prior_context
        else:delattr(budget,'stage_context')
    result=dict(engine='v42_integration.d0_a_planning.solve_d0_native_model',stage=case.stage,arm=case.arm,
        case_sha=case.case_sha,source_identity=case.d0_input_audit['identity'],D0_input_sha=case.d0_input_audit['a_input_sha'],
        input_MESS_anchor=matrix_receipt['input_MESS_anchor'],
        FULL_feasible=False,global_gap_certified=False,old_LB_reused=False,old_point_reused=False,
        domain_scope='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN',
        unrestricted_original_migration_equivalence=False,
        lazy_pricing_calls=0,pricing_status='COMPLETE_BASIC_DOMAIN_MATERIALIZED_NO_OTHER_DOMAIN_PRICING_CERTIFICATE',
        Phase_I='UNRESOLVED_NO_FULL_PRIMAL' if point is None else 'ORIGINAL_FULL_ROWS_FEASIBLE_NO_ARTIFICIAL_POINT',
        P1_status='CERTIFIED_CURRENT_A_MATRIX' if p1_closed else 'NOT_CERTIFIED',
        P2_status='CERTIFIED_CURRENT_A_MATRIX' if completed else 'NOT_CERTIFIED',
        P2_calls=sum(row['component']!='rho' and 'Native_call' in row for row in trace),
        lexicographic_trace=trace,numerical_policy=numerical,solver_policy=policy,
        Native_used_seconds=remaining_before-budget.remaining(),requested_total_cap_seconds=cap_seconds,
        matrix=dict(rows=model.NumConstrs,columns=model.NumVars,nonzeros=model.NumNZs),
        original_model_not_replaced=True,FCFS_final_schedule_used=False,historical_prefix_gate_used=False,
        KnownOptimization_status='NOT_DEMONSTRATED' if point is None else 'FEASIBLE_CURRENT_D0_NATIVE_NOT_OPTIMAL',
        local_bound=p1_bound,global_gap_scope='D0_FIXED_MESS_A_ONLY_NOT_AIDC_MESS_JOINT')
    if point is not None:
        result.update(_export_d0_point(case,built,point,selected))
        result['global_gap_certified']=p1_closed
        result['KnownOptimization_status']='CURRENT_D0_P1_P2_CERTIFIED' if completed else 'FEASIBLE_CURRENT_D0_NATIVE_NOT_FULL_LEX_OPTIMAL'
        result['incumbent_source']='CURRENT_D0_COMPLETE_NATIVE_MATRIX'
        np.savez_compressed(output/'POINT.npz',point=point)
    (output/'A_RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
    return result


def write_d0_a_planning_audit(output,rows,audit,*,matrix_receipt=None,a_result=None):
    """Save new AIDC reports once, after the admitted experiment has ended."""
    import csv
    import json
    output=Path(output);paths=[output/'D0_KNOWN_BACKLOG_CLASSIFICATION.csv',output/'D0_KNOWN_CC4_PLANNING_AUDIT.json']
    if any(path.exists() for path in paths):raise FileExistsError('D0_EXISTING_PLANNING_REPORT_MUST_NOT_BE_OVERWRITTEN')
    report=deepcopy(audit);report['native0_matrix']=deepcopy(matrix_receipt) if matrix_receipt else dict(status='NOT_RUN')
    if a_result:
        if a_result.get('source_identity')!=audit['identity']:raise ValueError('D0_A_REPORT_CROSS_CASE_RESULT')
        report['A_stage']=dict(stage=a_result['stage'],stage_case_sha=a_result['case_sha'],
            FULL_feasible=a_result['FULL_feasible'],KnownOptimization_status=a_result['KnownOptimization_status'],
            P1_status=a_result['P1_status'],P2_status=a_result['P2_status'],
            global_gap_certified=a_result['global_gap_certified'],global_gap_scope=a_result['global_gap_scope'],
            Native_used_seconds=a_result['Native_used_seconds'],matrix=a_result['matrix'],
            rho=a_result.get('rho'),aidc_anchor=a_result.get('aidc_anchor'),
            resource_distribution_sha=a_result.get('resource_distribution_sha'),
            FULL_point_replay=a_result.get('FULL_point_replay'),old_result_transferred=False)
    else:report['A_stage']=dict(status='NOT_RUN',FULL_feasible='NOT_RUN',old_result_transferred=False)
    report.update(new_May01_Actual='NOT_RUN',Actual_fixture_results_are_not_real_D0_performance=True)
    output.mkdir(parents=True,exist_ok=True)
    with paths[0].open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else v for k,v in row.items()})
    paths[1].write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report
