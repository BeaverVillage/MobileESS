"""Typed public D0 projection into the unchanged private event driver.

The private Environment is passed by identity and never inspected. The D0
base queue research window is separate from original empirical QoS rights.
This module does not run Actual or construct a future arrival bank.
"""
from copy import deepcopy
from dataclasses import dataclass,asdict,replace
import math
import json
from pathlib import Path

from .actual import _require_public_metadata
from .a_engine import digest
from .d0_a_planning import validate_backlog_contract
from .qos import BudgetReceipt,ObservedJob,QoSWindowProvider
from .may01_boundary_reconciliation import file_record,checked_json

POLICY='D0_OBSERVED_BACKLOG_BASE_WINDOW_ACTUAL_V1'
SOURCE_FIELDS=('qos','protected','batch_eligible','partition','requested_walltime_seconds',
    'release_seconds','hard_earliest_start_seconds','hard_latest_start_seconds','completion_deadline_seconds',
    'can_prestart_place','migration_capability','request_version_authority')


@dataclass(frozen=True)
class D0BacklogStatistics:
    contract_sha: str
    source_empirical_stats_sha: str

    @property
    def sha(self):return self.contract_sha

    def to_dict(self):return dict(policy_id=POLICY,D0_research_contract_sha=self.contract_sha,
        source_empirical_stats_sha=self.source_empirical_stats_sha,empirical_statistics_changed=False,
        base_queue_window_is_customer_SLA=False)


@dataclass(frozen=True)
class D0BudgetReceipt(BudgetReceipt):
    source_empirical_stats_sha: str
    source_empirical_budget_seconds: int
    base_backlog_scheduling_window_seconds: int
    additional_intentional_delay_budget_seconds: int
    backlog_contract_sha: str
    source_observed_metadata: dict
    contract_is_observed_SLA: bool
    research_base_window_is_source_QoS_extension: bool


class D0BacklogProvider:
    """D0 known backlog issuer; future observed Unknown keeps the strict issuer."""
    def __init__(self,source_provider,*,state,contract,identity,reference_sha):
        if not isinstance(source_provider,QoSWindowProvider):raise ValueError('D0_ORIGINAL_STRICT_SOURCE_PROVIDER_REQUIRED')
        self.begin=state['begin_epoch_seconds'];self.identity=deepcopy(identity)
        validate_backlog_contract(contract,begin=self.begin,end=self.begin+86400,identity=identity)
        if state['common_initial_state_sha']!=identity['initial_state_sha']:raise ValueError('D0_ACTUAL_PROVIDER_INITIAL_SOURCE_DRIFT')
        self.contract=deepcopy(contract);self.case_sha=identity['case_sha'];self.provider_sha=source_provider.provider_sha
        self.source_stats_sha=source_provider.stats.sha;self.stats=D0BacklogStatistics(contract['contract_sha'],self.source_stats_sha)
        self.reference_sha=reference_sha
        # No D-minus-1 receipts are copied, re-issued or used as D0 authority.
        self.strict=QoSWindowProvider(source_provider.stats,case_sha=self.case_sha,provider_sha=self.provider_sha)
        self.known={r['uid']:deepcopy(r) for name in ('running','pending') for r in state[name]}
        if len(self.known)!=len(state['running'])+len(state['pending']):raise ValueError('D0_INITIAL_KNOWN_UID_DUPLICATE')
        self.receipts={};self.contexts={};self._sealed={};self.audit=[]

    def register_observed(self,uid,*,episode_id=None,source_authority=None):
        value=dict(episode_id=episode_id,source_authority=deepcopy(source_authority or {}))
        _require_public_metadata(value)
        if uid in self.contexts and self.contexts[uid]!=value:raise ValueError('D0_OBSERVED_SOURCE_CONTEXT_DRIFT')
        self.contexts[uid]=value

    def _check_job(self,job,raw):
        if (job.origin_unknown is not False or job.gpu!=raw['gpu'] or job.submit_seconds!=raw['submit_seconds']
                or job.t50_seconds!=raw['q50'] or job.provider_sha!=self.provider_sha
                or job.reference_sha!=self.reference_sha or job.event_seconds<self.begin):
            raise ValueError('D0_KNOWN_PUBLIC_SOURCE_AUTHORITY_DRIFT')
        metadata=raw['metadata']
        for name in SOURCE_FIELDS:
            if hasattr(job,name) and getattr(job,name)!=metadata.get(name):
                raise ValueError('D0_SOURCE_QOS_OR_HARD_METADATA_CHANGED:'+name)

    def issue(self,job):
        if not isinstance(job,ObservedJob):raise ValueError('D0_PUBLIC_OBSERVED_JOB_REQUIRED')
        if self.strict.stats.sha!=self.source_stats_sha:raise ValueError('D0_ORIGINAL_EMPIRICAL_STATISTICS_DRIFT')
        if job.uid in self.receipts:
            receipt=self.receipts[job.uid]
            if receipt.authority_sha!=job.authority_sha or self._sealed[job.uid]!=digest(receipt.to_dict()):
                raise ValueError('D0_IMMUTABLE_OBSERVED_RECEIPT_DRIFT')
            return receipt
        raw=self.known.get(job.uid)
        if raw is None:
            if job.origin_unknown is not True or job.submit_seconds<self.begin:
                raise ValueError('D0_FUTURE_UNKNOWN_SOURCE_ROLE_REQUIRED')
            source=self.strict.issue(job)
            receipt=D0BudgetReceipt(**asdict(replace(source,stats_sha=self.stats.sha,policy_id=POLICY)),
                source_empirical_stats_sha=self.source_stats_sha,source_empirical_budget_seconds=source.budget_seconds,
                base_backlog_scheduling_window_seconds=0,additional_intentional_delay_budget_seconds=0,
                backlog_contract_sha=self.contract['contract_sha'],source_observed_metadata=asdict(job),
                contract_is_observed_SLA=False,research_base_window_is_source_QoS_extension=False)
        else:
            self._check_job(job,raw)
            running=raw['site'] is not None
            represented=tuple(raw['metadata']['representation_starts_seconds'])
            latest=self.begin if running else self.begin+85500
            starts=QoSWindowProvider._window(job,latest)
            starts=tuple(t for t in starts if t in represented and self.begin<=t<self.begin+86400)
            if job.protected is True or job.qos in ('high','urgent'):
                allowed=raw['metadata'].get('source_authorized_D0_starts_seconds',[])
                starts=tuple(t for t in starts if t in allowed)
            budget=int(max(0.,latest-job.reference_start_seconds))
            hard={name:getattr(job,name) for name in ('release_seconds','hard_earliest_start_seconds','hard_latest_start_seconds',
                'completion_deadline_seconds','representation_starts_seconds','nominal_service_seconds','provider_sha','reference_sha',
                'batch_eligible','qos','protected','partition','gpu','requested_walltime_seconds')}
            receipt=D0BudgetReceipt(uid=job.uid,case_sha=self.case_sha,policy_id=POLICY,stats_sha=self.stats.sha,
                provider_sha=self.provider_sha,reference_sha=job.reference_sha,authority_sha=job.authority_sha,
                issued_at_seconds=job.event_seconds,reference_start_seconds=job.reference_start_seconds,
                reference_wait_seconds=job.reference_start_seconds-job.submit_seconds,t50_seconds=job.t50_seconds,
                empirical_wait_seconds=None,budget_seconds=budget,latest_start_seconds=latest,allowed_starts_seconds=starts,
                cohort_level=None,cohort_n=0,q90_higher_z=None,status='D0_RESEARCH_BASE_WINDOW' if starts else 'EMPTY_SOURCE_HARD_WINDOW',
                reasons=('RESEARCH_BASE_QUEUE_WINDOW_ONLY','SOURCE_QOS_AND_PROTECTION_UNCONFIRMED_PRESERVED'),
                origin_unknown=False,is_observed=True,batch_eligible=job.batch_eligible,state_at_issue=job.state,
                hard_contract=hard,hard_contract_sha=digest(hard),source_empirical_stats_sha=self.source_stats_sha,
                source_empirical_budget_seconds=0,base_backlog_scheduling_window_seconds=budget,
                additional_intentional_delay_budget_seconds=0,backlog_contract_sha=self.contract['contract_sha'],
                source_observed_metadata={name:deepcopy(raw['metadata'].get(name)) for name in SOURCE_FIELDS},
                contract_is_observed_SLA=False,research_base_window_is_source_QoS_extension=False)
        self.receipts[job.uid]=receipt;self._sealed[job.uid]=digest(receipt.to_dict())
        self.audit.append(dict(uid=job.uid,case_sha=self.case_sha,D0_known=raw is not None,
            original_empirical_stats_sha=self.source_stats_sha,new_receipt_sha=self._sealed[job.uid],
            source_empirical_budget_seconds=receipt.source_empirical_budget_seconds,
            base_window_seconds=receipt.base_backlog_scheduling_window_seconds,customer_SLA_claimed=False,
            hard_deadline_extended=False,old_D1_receipt_reused=False))
        return receipt

    def allowed_starts(self,job,receipt=None,*,interruption_seconds=0):
        receipt=self.issue(job) if receipt is None else receipt
        if (receipt.uid!=job.uid or receipt.case_sha!=self.case_sha or receipt.authority_sha!=job.authority_sha
                or not math.isfinite(interruption_seconds) or interruption_seconds<0):
            raise ValueError('D0_BASE_WINDOW_RECEIPT_AUTHORITY_DRIFT')
        if interruption_seconds>receipt.budget_seconds:return ()
        window=QoSWindowProvider._window(job,receipt.latest_start_seconds-interruption_seconds,interruption_seconds)
        return tuple(t for t in window if t in receipt.allowed_starts_seconds)

    def export_ledger(self):
        return {uid:dict(receipt.to_dict(),receipt_sha=digest(receipt.to_dict())) for uid,receipt in sorted(self.receipts.items())}

    def to_dict(self):return dict(policy_id=POLICY,case_sha=self.case_sha,provider_sha=self.provider_sha,
        stats_sha=self.stats.sha,source_empirical_stats_sha=self.source_stats_sha,receipts=self.export_ledger(),
        source_statistics_unchanged=True,old_D1_receipts_used=False,customer_SLA_claimed=False)


@dataclass(frozen=True)
class D0DriverProjection:
    arguments: dict
    receipt: dict


def project_d0_driver_arguments(arguments,*,state,provider,evidence_scope='NAMED_NUMERIC_FIXTURE'):
    """Actual-only public metadata projection; private Environment stays opaque."""
    if not isinstance(provider,D0BacklogProvider):raise ValueError('D0_BACKLOG_PROVIDER_REQUIRED')
    begin=state['begin_epoch_seconds']
    if arguments['begin']!=begin or provider.begin!=begin:raise ValueError('D0_PRIVATE_DRIVER_PUBLIC_CLOCK_DRIFT')
    raw_running={r['uid']:r for r in state['running']};raw_pending={r['uid']:r for r in state['pending']}
    initial={**raw_running,**raw_pending};completed={r.get('uid',r.get('job_uid')) for r in state.get('historical_completed',[])}
    actual_running={r.uid:(site,start) for r,site,start in arguments.get('running',[])}
    if actual_running!={u:(r['site'],r['observed_start_seconds']) for u,r in raw_running.items()}:
        raise ValueError('D0_DRIVER_INITIAL_RUNNING_SITE_HISTORY_DRIFT')
    if evidence_scope.startswith('REAL') and (len(raw_running),len(raw_pending),sum(r['gpu'] for r in raw_running.values()))!=(324,1300,472):
        raise ValueError('D0_REAL_APPROVED_324_1300_472_REQUIRED')
    seen=set();reclassified=[]
    def projected(request):
        if request.uid in seen or request.uid in completed:raise ValueError('D0_DUPLICATE_OR_COMPLETED_DRIVER_UID')
        seen.add(request.uid);raw=initial.get(request.uid)
        if raw is None:
            if request.submit<begin:raise ValueError('D0_UNACCOUNTED_PREISSUE_DRIVER_UID')
            if request.metadata.get('origin_unknown') is not True:raise ValueError('D0_FUTURE_REQUEST_MUST_REMAIN_UNKNOWN')
            return request
        metadata=deepcopy(request.metadata);_require_public_metadata(metadata)
        if (request.submit!=raw['submit_seconds'] or request.gpu!=raw['gpu'] or request.q50!=raw['q50']
                or tuple(request.compatible)!=tuple(raw['compatible_sites'])):
            raise ValueError('D0_DRIVER_PUBLIC_REQUEST_CONTRACT_DRIFT')
        if (metadata.get('episode_id')!=raw['episode_id'] or metadata.get('elapsed_compute_seconds')!=raw['elapsed_compute_seconds']):
            raise ValueError('D0_DRIVER_EPISODE_OR_ELAPSED_DRIFT')
        for name in SOURCE_FIELDS:
            if metadata.get(name)!=raw['metadata'].get(name):raise ValueError('D0_DRIVER_SOURCE_METADATA_DRIFT:'+name)
        for name in ('reused_planning_qos_authority','reference_sha','reference_start_seconds','provider_sha'):
            metadata.pop(name,None)
        running=request.uid in raw_running
        metadata.update(origin_unknown=False,D0_original_D1_origin_unknown=raw['origin_unknown'],
            cc4_eligible=False,D0_classification_authority=provider.contract['contract_sha'],
            common_initial_state_sha=state['common_initial_state_sha'],dday_initialization_seconds=begin,
            initial_observed_state='RUNNING' if running else 'PENDING',state='RUNNING' if running else 'PENDING',
            episode_id=raw['episode_id'],elapsed_compute_seconds=raw['elapsed_compute_seconds'],
            reference_sha=provider.reference_sha,reference_start_seconds=begin,provider_sha=provider.provider_sha,
            nominal_service_seconds=max(0.,raw['q50']-raw['elapsed_compute_seconds']) if running else raw['q50'],
            representation_starts_seconds=tuple(raw['metadata']['representation_starts_seconds']),
            D0_base_queue_window_is_additional_intentional_delay=False)
        if raw['origin_unknown']:reclassified.append(request.uid)
        _require_public_metadata(metadata)
        return replace(request,metadata=metadata)
    running=[(projected(request),site,start) for request,site,start in arguments.get('running',[])]
    requests=[projected(request) for request in arguments['requests']]
    if {request.uid for request in requests if request.uid in initial}!=set(raw_pending):
        raise ValueError('D0_DRIVER_INITIAL_PENDING_ROSTER_DRIFT')
    if not set(initial)<=seen:raise ValueError('D0_DRIVER_INITIAL_UID_DROP')
    result=dict(arguments,running=running,requests=requests,qos_window_provider=provider)
    if result.get('environment') is not arguments.get('environment'):raise ValueError('D0_PRIVATE_ENVIRONMENT_REPLACED')
    return D0DriverProjection(result,dict(status='PASS',scope=evidence_scope,
        projected_initial_known_UIDs=len(initial),initial_running_UIDs=len(running),initial_pending_UIDs=len(raw_pending),
        initial_running_GPU=sum(request.gpu for request,_,_ in running),reclassified_D1_Unknown_to_D0_Known=len(reclassified),
        source_metadata_and_hard_contracts_changed=False,source_submit_q50_GPU_site_elapsed_changed=False,
        old_D1_planning_receipt_reuse=False,initial_CC4_depletion_eligible_UIDs=0,
        private_Environment_preserved_by_identity=True,private_environment_fields_read=False,
        future_requests_preserved_until_submit=True,Actual_engine_calls=0,Native_calls=0,
        real_May01_performance_certified=False))


def d0_actual_factory_gate(*,context,a_result,m2_result=None,actual_source_receipt=None):
    """Fail closed before private Actual preparation if the final chain is absent."""
    if not a_result or a_result.get('FULL_feasible') is not True:
        return dict(status='NOT_RUN',reason='CURRENT_D0_A_HAS_NO_ORIGINAL_FULL_PRIMAL',private_Actual_bank_read=False)
    if a_result.get('stage')!='A2' or m2_result is None:
        return dict(status='NOT_RUN',reason='CURRENT_D0_FINAL_A2_M2_NOT_AVAILABLE',private_Actual_bank_read=False)
    if actual_source_receipt is None:
        return dict(status='NOT_RUN',reason='D0_ACTUAL_SPECIFIC_SOURCE_VERSION_NOT_ADMITTED',private_Actual_bank_read=False)
    require_actual_source_authority(actual_source_receipt,context['manifest'])
    # Parent owns the exact original A2/M2 Source/Matrix/FULL gate. This module
    # never turns a caller's three flags into production admission.
    return dict(status='NOT_CERTIFIED',reason='SUPERVISOR_EXACT_FINAL_A2_M2_SOURCE_GATE_REQUIRED',
        private_Actual_bank_read=False,automatic_Actual_execution_authorized=False)


ACTUAL_MATERIAL_FILES=('d0_actual_inputs.py','d0_execution.py','actual.py','actual_validation.py',
    'aidc_sensitivity_runtime.py','aidc_resource_bridge.py','qos.py')


def build_actual_source_authority(manifest,*,output):
    """Actual code has its own revision; executed Planning identity is unchanged."""
    from .d0_case import require_case
    require_case(manifest)
    output=Path(output)
    if output.exists():raise FileExistsError('D0_ACTUAL_SOURCE_AUTHORITY_MUST_NOT_BE_OVERWRITTEN')
    document=dict(schema='D0_ACTUAL_SOURCE_VERSION_AUTHORITY_V1',status='PASS',
        scope='ACTUAL_CODE_SOURCE_BINDING_ONLY_NOT_FINAL_A2_M2_ADMISSION',
        planning_manifest_sha=manifest['manifest_sha'],planning_source_sha=manifest['source_sha'],
        planning_identity=deepcopy(manifest['identity']),planning_math_source_modified=False,
        material_actual_code=[file_record(Path(__file__).parent/name) for name in ACTUAL_MATERIAL_FILES],
        original_private_driver_retained=True,private_Environment_fields_read=False,
        historical_prefix_factory_used=False,customer_SLA_claimed=False,Native_calls=0,Actual_calls=0,
        final_A2_M2_handoff='NOT_RUN',real_May01_performance_certified=False)
    document['authority_sha']=digest(document)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return document


def require_actual_source_authority(document,manifest):
    from .d0_case import require_case
    require_case(manifest)
    if (document.get('schema')!='D0_ACTUAL_SOURCE_VERSION_AUTHORITY_V1'
            or document.get('status')!='PASS'
            or document.get('scope')!='ACTUAL_CODE_SOURCE_BINDING_ONLY_NOT_FINAL_A2_M2_ADMISSION'
            or document.get('authority_sha')!=digest({k:v for k,v in document.items() if k!='authority_sha'})
            or document.get('planning_manifest_sha')!=manifest['manifest_sha']
            or document.get('planning_source_sha')!=manifest['source_sha']
            or document.get('planning_identity')!=manifest['identity']
            or document.get('planning_math_source_modified') is not False
            or document.get('private_Environment_fields_read') is not False
            or document.get('Native_calls')!=0 or document.get('Actual_calls')!=0
            or document.get('real_May01_performance_certified') is not False):
        raise ValueError('D0_ACTUAL_CODE_PLANNING_SOURCE_BINDING_DRIFT')
    records=document.get('material_actual_code',[])
    expected={str((Path(__file__).parent/name).resolve()) for name in ACTUAL_MATERIAL_FILES}
    if {str(Path(record['path']).resolve()) for record in records}!=expected or len(records)!=len(expected):
        raise ValueError('D0_ACTUAL_MATERIAL_CODE_SCOPE_DRIFT')
    for record in records:
        actual=file_record(record['path'])
        if any(actual[k]!=record[k] for k in ('sha256','bytes')):raise ValueError('D0_ACTUAL_MATERIAL_CODE_BYTES_DRIFT')
    return dict(status='PASS',scope='ACTUAL_CODE_SOURCE_BINDING_ONLY',authority_sha=document['authority_sha'],
        final_A2_M2_admitted=False,private_Actual_bank_read=False)
