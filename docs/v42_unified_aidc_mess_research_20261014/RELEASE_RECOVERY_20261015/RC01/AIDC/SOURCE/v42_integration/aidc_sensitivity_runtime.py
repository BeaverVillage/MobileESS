"""Causal signed-grid allocation and immutable research60 runtime control.

Historical tracking/frozen tables and the source TRAIN model are preserved.
No native solver or private completion API is available in this module.
"""
from copy import deepcopy
from dataclasses import asdict, fields, replace
from time import perf_counter
import math
import json
from pathlib import Path
import hashlib
import numpy as np

from .actual import JobEventController, ExecutionLedger, _require_public_metadata, run_actual
from .experimental_actual import ExperimentalJobEventController
from .experimental_qos import (ExperimentalQoSProvider, ExperimentalBudgetReceipt,
    ExperimentalStatistics, participation_for, FROZEN_SEED)
from .qos import QoSWindowProvider, ObservedJob, receipt_slot_domain, CausalReferenceScheduler
from v42_capacity.actual import Request
from .policy import digest, _receipt, migration_guard, ReservationLedger
from .reservation_state import ContractReservationLedger, union_job_segments
from .trajectory_tracking import TrackingReference, service_integral, require_tracking_public
from .frozen_unknown import _migration_capability
from .unified_contract import require_bindings
from v42_final.workload import ForecastBook

CONTRACT = 'V42_SIGNED_SENSITIVITY_RUNTIME60_V1'
MODE = 'CAUSAL_SIGNED_GRID_ALLOCATION'
DELAY_SECONDS = (0, 900, 1800, 2700, 3600)
SITE_ONLY_CONTRACT = 'V42_FROZEN_KNOWN_UNKNOWN_SITE_ONLY_V1'
CURRENT_EVENT_CONTRACT = 'V42_CURRENT_EVENT_SIGNED_ALLOCATION_CORRECTIVE_V1'


def grid_numeric_fingerprint(packet):
    """Every numeric array read by original scalar electrical rows."""
    fingerprint = hashlib.sha256()
    def add(name, value):
        array = np.asarray(value)
        fingerprint.update(name.encode()); fingerprint.update(str((array.shape,array.dtype.str)).encode())
        fingerprint.update(array.tobytes())
    for name in ('controls','p_slope','cos','sin','line_indices','transformer_indices'):
        add(name,getattr(packet,name))
    for name in ('ap','correction','bias'):
        for t,value in enumerate(getattr(packet,name)):
            add(name+str(t),value)
    for t,coefficient in enumerate(packet.coefficients):
        for name in ('voltage_constant','voltage_matrix','flow_p_constant','flow_p_matrix',
                'flow_q_constant','flow_q_matrix','current_constant','current_matrix','anchor','branch_limits'):
            add(str(t)+name,getattr(coefficient,name))
        fingerprint.update(digest(dict(ratings=list(coefficient.transformer_ratings),
            control_names=list(coefficient.control_names),branch_names=list(coefficient.branch_names))).encode())
    fingerprint.update(digest(dict(voltage_lower=packet.voltage_lower,voltage_upper=packet.voltage_upper,
        sites=list(packet.sites),branch_names=list(packet.branch_names),control_names=list(packet.control_names),
        pf=packet.pf)).encode())
    return fingerprint.hexdigest()


def build_boundary_completion_proof(source_file_record, *, bindings, begin_seconds, evidence_scope='REAL_NEW_U60'):
    """Read a frozen current-boundary observation only after Planning freeze."""
    begin_seconds = float(begin_seconds)
    record = deepcopy(source_file_record)
    path = Path(record['path']); payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record['sha256'] or len(payload) != record['bytes']:
        raise ValueError('BOUNDARY_COMPLETION_SOURCE_FILE_SHA_DRIFT')
    source = json.loads(payload)
    if evidence_scope.startswith('REAL'):
        from .dday_initialization import load_dday_state
        source = load_dday_state(path,arm='B1')
    if (source.get('common_initial_state_sha') != bindings['initial_state_sha']
            or digest({k:source[k] for k in source['initial_state_payload_keys']}) != bindings['initial_state_sha']
            or source['begin_epoch_seconds'] != begin_seconds
            or source['day_begin_epoch_seconds'] != begin_seconds):
        raise ValueError('BOUNDARY_COMPLETION_COMMON_STATE_OR_CLOCK_DRIFT')
    rows = []
    for raw in source['historical_completed']:
        if raw['origin_unknown'] is not False:
            continue
        if (raw.get('state','COMPLETED') != 'COMPLETED'
                or not math.isfinite(raw['observed_completion_seconds'])
                or raw['observed_completion_seconds'] > begin_seconds
                or raw['observed_control_release_seconds'] > begin_seconds):
            raise ValueError('BOUNDARY_COMPLETION_FUTURE_OR_NONCOMPLETED_OBSERVATION')
        rows.append(dict(uid=raw['job_uid'],state='COMPLETED',origin_unknown=False,
            observed_at_seconds=begin_seconds,observed_completion_seconds=raw['observed_completion_seconds'],
            observed_control_release_seconds=raw['observed_control_release_seconds'],source_row_sha=digest(raw)))
    rows.sort(key=lambda r:r['uid'])
    if len({r['uid'] for r in rows}) != len(rows):
        raise ValueError('BOUNDARY_COMPLETION_DUPLICATE_UID')
    proof = dict(schema='FROZEN_CURRENT_BOUNDARY_KNOWN_COMPLETION_PROOF_V1',
        common_case_sha=bindings['case_sha'],science_sha=bindings['science_sha'],
        source_initial_state_sha=bindings['initial_state_sha'],begin_seconds=begin_seconds,
        observed_at_seconds=begin_seconds,source_file_record=record,rows=rows,evidence_scope=evidence_scope,
        source_Dday_MODEL_ASSUMPTION=source.get('MODEL_ASSUMPTION',True),
        private_future_Actual_read=False,Planning_population_changed=False)
    proof['proof_sha'] = digest(proof)
    return proof


def require_boundary_completion_proof(proof, *, bindings, begin_seconds):
    if proof is None:
        raise ValueError('REAL_CURRENT_BOUNDARY_COMPLETION_PROOF_REQUIRED')
    if (proof.get('proof_sha') != digest({k:v for k,v in proof.items() if k!='proof_sha'})
            or proof.get('common_case_sha') != bindings['case_sha']
            or proof.get('science_sha') != bindings['science_sha']
            or proof.get('source_initial_state_sha') != bindings['initial_state_sha']
            or proof.get('begin_seconds') != begin_seconds or proof.get('observed_at_seconds') != begin_seconds):
        raise ValueError('BOUNDARY_COMPLETION_PROOF_SEAL_OR_BINDING_DRIFT')
    rebuilt = build_boundary_completion_proof(proof['source_file_record'],bindings=bindings,
        begin_seconds=begin_seconds,evidence_scope=proof['evidence_scope'])
    if rebuilt != proof:
        raise ValueError('BOUNDARY_COMPLETION_EXACT_UID_OBSERVATION_DRIFT')
    return proof


class Research60QoSProvider(ExperimentalQoSProvider):
    """Public UID participation; a separate assumed universal 60min policy.

    strict.stats is empirical evidence. stats identifies the frozen research
    policy; it does not assert an observed customer SLA.
    """
    def __init__(self, strict_provider, *, case_sha, frozen_spec, participation='FLEX30'):
        if (participation != 'FLEX30' or frozen_spec['max_start_delay_seconds'] != 3600
                or frozen_spec['source_training_sha'] != strict_provider.stats.sha
                or frozen_spec['customer_SLA_claim'] is not False
                or frozen_spec['reissue_on_retry'] is not False):
            raise ValueError('RESEARCH60_FROZEN_SOURCE_CONTRACT_REQUIRED')
        if case_sha == strict_provider.case_sha:
            raise ValueError('RESEARCH60_REQUIRES_DISTINCT_CASE')
        self.strict = strict_provider
        self.scenario, self.participation, self.seed = 'U60', participation, FROZEN_SEED
        self.case_sha, self.provider_sha = case_sha, strict_provider.provider_sha
        self.contexts, self.receipts, self._sealed = {}, {}, {}
        self.spec = deepcopy(frozen_spec)
        self.stats = ExperimentalStatistics(self.spec)
        self.policy_sha = digest(frozen_spec)
        self.source_training_sha = strict_provider.stats.sha

    def require_frozen_policy(self, expected_policy_sha=None):
        if (digest(self.spec) != self.policy_sha or self.stats.sha != self.policy_sha
                or self.strict.stats.sha != self.source_training_sha
                or (expected_policy_sha is not None and expected_policy_sha != self.policy_sha)):
            raise ValueError('RESEARCH60_FROZEN_POLICY_SHA_DRIFT')

    @staticmethod
    def _derive(job, context):
        model = ExperimentalQoSProvider._derive(job, context)
        if str(job.qos).lower() in {'interactive', 'urgent', 'high', 'protected'}:
            model['eligible_for_contract'] = False
            model['protected'] = True
            model['batch_eligible'] = False
        return model

    def issue(self, job, *, episode_id=None, source_authority=None):
        self.require_frozen_policy()
        _require_public_metadata(asdict(job))
        if not job.is_observed or job.submit_seconds > job.event_seconds:
            raise ValueError('RESEARCH60_OBSERVED_ISSUE_REQUIRED')
        if job.provider_sha and job.provider_sha != self.provider_sha:
            raise ValueError('FROZEN_PROVIDER_MISMATCH')
        if episode_id is not None or source_authority is not None:
            self.register_observed(job.uid, episode_id=episode_id, source_authority=source_authority)
        context = deepcopy(self.contexts.get(job.uid, dict(episode_id=None, source_authority={})))
        if job.uid in self.receipts:
            receipt = self.receipts[job.uid]
            self._check_seal(receipt)
            if receipt.authority_sha != job.authority_sha or digest(context) != digest(receipt.source_context):
                raise ValueError('RESEARCH60_IMMUTABLE_BUDGET_AUTHORITY_CHANGED')
            return receipt
        model = self._derive(job, context)
        member = participation_for(job.uid, context['episode_id'], seed=self.seed)
        participant = member['membership'][self.participation]
        cap = 3600 if model['eligible_for_contract'] else 0
        budget = cap if participant else 0
        source = asdict(job)
        contract = {key: source[key] for key in ('release_seconds', 'hard_earliest_start_seconds',
            'hard_latest_start_seconds', 'completion_deadline_seconds', 'representation_starts_seconds',
            'nominal_service_seconds', 'provider_sha', 'reference_sha', 'batch_eligible', 'qos',
            'protected', 'partition', 'gpu', 'requested_walltime_seconds')}
        latest = job.reference_start_seconds + budget
        starts = QoSWindowProvider._window(job, latest)
        reasons = tuple(reason for predicate, reason in (
            (not model['eligible_for_contract'], 'SOURCE_PROTECTED_OR_EXPLICIT_NONBATCH'),
            (not participant, 'NOT_SELECTED_PREREGISTERED_PARTICIPATION'),
            (not starts, 'EMPTY_AUTHORIZED_WINDOW')) if predicate)
        receipt = ExperimentalBudgetReceipt(uid=job.uid, case_sha=self.case_sha, policy_id=CONTRACT,
            stats_sha=self.stats.sha, provider_sha=self.provider_sha, reference_sha=job.reference_sha,
            authority_sha=job.authority_sha, issued_at_seconds=job.event_seconds,
            reference_start_seconds=job.reference_start_seconds,
            reference_wait_seconds=job.reference_start_seconds-job.submit_seconds,
            t50_seconds=job.t50_seconds, empirical_wait_seconds=None, budget_seconds=budget,
            latest_start_seconds=latest, allowed_starts_seconds=starts, cohort_level=None,
            cohort_n=0, q90_higher_z=None, status=reasons[0] if reasons else 'RESEARCH60_AUTHORIZED',
            reasons=reasons, origin_unknown=job.origin_unknown, is_observed=job.is_observed,
            batch_eligible=job.batch_eligible, state_at_issue=job.state, hard_contract=contract,
            hard_contract_sha=digest(contract), scenario=self.scenario, participation=self.participation,
            episode_id=member['episode_id'], membership_sha=member['membership_sha'],
            participation_score=member['score'], participant=participant,
            eligible_for_contract=model['eligible_for_contract'], contract_cap_seconds=cap,
            source_observed_metadata=source, model_metadata=model, source_context=context,
            assumption_sha=digest(dict(spec=self.stats.sha, source=source, context=context, model=model)),
            policy_spec_sha=self.stats.sha, contract_is_observed_SLA=False)
        self.receipts[job.uid], self.contexts[job.uid] = receipt, context
        self._sealed[job.uid] = digest(receipt.to_dict())
        return receipt

    def metadata_overlay(self, job, receipt=None, *, state=None):
        overlay = super().metadata_overlay(job, receipt, state=state)
        overlay['experimental_contract']['policy_id'] = CONTRACT
        overlay['experimental_contract']['source_training_sha'] = self.source_training_sha
        return overlay

    def to_dict(self):
        return dict(policy_id=CONTRACT, scenario=self.scenario, participation=self.participation,
            case_sha=self.case_sha, stats_sha=self.stats.sha, provider_sha=self.provider_sha,
            source_training_sha=self.source_training_sha, research_budget_cap_seconds=3600,
            slot_seconds=900, manifest=deepcopy(self.spec), receipts=self.export_ledger(),
            raw_qos_unmodified=True, contract_is_observed_SLA=False)


def conditional_remaining_runtime(metadata):
    """Public quantiles are forecasts, never exact completion guarantees."""
    elapsed = float(metadata.get('accumulated_compute_seconds', 0))
    q50 = float(metadata['t50_seconds'])
    q90 = metadata.get('experimental_prediction_Q90_seconds')
    return dict(total_Q50_seconds=q50, total_Q90_seconds=q90, elapsed_seconds=elapsed,
        conditional_remaining_Q90_seconds=None, conditional_provider_status='NOT_CERTIFIED',
        public_remaining_Q50_seconds=max(0., q50-elapsed),
        physical_remaining_runtime_seconds=None,
        physical_remaining_runtime_status='UNOBSERVED_RUNNING_RIGHT_CENSORED' if metadata.get('state')=='RUNNING' else 'NOT_A_COMPLETION_FORECAST',
        zero_Q50_remaining_is_physical_completion=False,
        running_hold_required=metadata.get('state') == 'RUNNING',
        quantile_is_completion_guarantee=False)


def known_initial_reconciliation(commands, initial_freeze, *, issue_seconds, begin_seconds):
    """Observe a boundary without moving commands or inventing prefix history."""
    rows = []
    for state, key in (('RUNNING', 'running'), ('PENDING', 'pending'), ('COMPLETED', 'historical_completed')):
        for observed in initial_freeze.get(key, []):
            if observed.get('origin_unknown') is not False:
                continue
            uid = observed.get('uid', observed.get('job_uid'))
            command = commands.get(uid)
            start = None if command is None else command['start_seconds']
            if command is None:
                status = 'SOURCE_REFERENCE_FALLBACK_NO_NATIVE_COMMAND'
            elif state == 'COMPLETED':
                status = 'OBSERVED_COMPLETED_NO_COMMAND_REISSUE'
            elif state == 'RUNNING':
                status = ('OBSERVED_RUNNING_PREFIX_MATCH' if observed['observed_start_seconds'] == start
                    and observed['site'] == command['site'] else 'OBSERVED_RUNNING_PLAN_MISMATCH_PRESERVE_OCCUPANCY')
            elif start < begin_seconds:
                status = 'PAST_START_NOT_OBSERVED_EXECUTED_BLOCKED'
            else:
                status = 'FUTURE_FROZEN_COMMAND_REPLAY_ELIGIBLE'
            rows.append(dict(uid=uid, state=state, status=status, plan_start_seconds=start,
                observed_start_seconds=observed.get('observed_start_seconds'),
                command_moved=False, unknown_allocator_used=False,
                observed_remaining_service='PRIVATE_SIMULATOR_PRESERVED' if state == 'RUNNING' else None))
    counts = {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})}
    return dict(issue_seconds=issue_seconds, begin_seconds=begin_seconds,
        issue_to_begin_seconds=begin_seconds-issue_seconds, rows=rows, counts=counts,
        status='NOT_CERTIFIED' if any('MISMATCH' in r['status'] or 'BLOCKED' in r['status'] for r in rows) else 'RECONCILED',
        prefix_replay_executed=False, future_completion_used=False, commands_sha=digest(commands),
        remedy='NEW_ISSUE_CAUSAL_PLANNING_WITH_FROZEN_PREFIX_EXECUTION_OR_BOUNDARY_CONSTRAINED_DOMAIN')


def known_planning_bridge(issue_jobs, *, issue_seconds, begin_seconds):
    """Issue-only domain recipe; a new A1 must optimize and certify this domain.

    Pending starts before Dday require causal prefix execution. Without it,
    this recipe restricts new pending commands to Dday; no Actual data is read.
    """
    rows = {}
    for uid, job in issue_jobs.items():
        state = getattr(job, 'state', None) or job['state']
        rows[uid] = dict(uid=uid, state_at_issue=state,
            earliest_new_pending_command_seconds=max(issue_seconds, begin_seconds) if state == 'PENDING' else None,
            running_site_and_elapsed='PRESERVE_ISSUE_OBSERVATION' if state == 'RUNNING' else None,
            remaining_service='FROZEN_PROVIDER_PUBLIC_PREDICTION', future_Dday_state_used=False)
    return dict(rows=rows, native_execution='NOT_RUN', new_A1_certified=False,
        future_Dday_snapshot_consumed=False, source_only_domain_sha=digest(rows))


def anonymous_cohort_residual(reference, metadata, now):
    """Exact original cohort marginals; residual work remains a soft forecast.

    The original model has separate hour/time and site/time marginals. Their
    canonical transportation product preserves both without inventing UIDs.
    Source x/CDF/carry are replayed before any residual can inform a guard.
    """
    from .q90_recourse import load_nominal_service
    z = np.zeros_like(reference.arrays['G_Unknown_Q50_Plan'])
    identity = reference.identity
    if not np.any(reference.arrays['G_Unknown_Q50_Plan']) and not np.any(identity.get('CC4_Q50', [])):
        return z, dict(status='ZERO_ANONYMOUS_FORECAST', hard_occupancy=False)
    required = ('CC4_Q50', 'CC4_Q90', 'CC4_service', 'CC4_carryout',
        'Timing_CDF_Q10', 'Timing_CDF_Q90', 'CC4_source_authority')
    if any(k not in identity for k in required):
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='SOURCE_COHORT_CDF_AUTHORITY_MISSING',
            safe_promotion_allowed=False, hard_occupancy=False)
    sites = reference.sites
    a = dict(resource_sites=list(sites), aidc_anchor=identity['CC4_source_authority']['aidc_anchor'],
        nominal_site_GPU={s:reference.arrays['G_Unknown_Q50_Plan'][:,j].tolist() for j,s in enumerate(sites)},
        known_site_GPU={s:reference.arrays['G_Known_Plan'][:,j].tolist() for j,s in enumerate(sites)},
        CC4_service=identity['CC4_service'], CC4_carryout=identity['CC4_carryout'])
    try:
        nominal = load_nominal_service(a, identity['CC4_Q50'], identity['Timing_CDF_Q10'],
            identity['Timing_CDF_Q90'], source_authority=identity['CC4_source_authority'])
    except ValueError as exc:
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason=str(exc),
            safe_promotion_allowed=False, hard_occupancy=False)
    book = ForecastBook(tuple(identity['CC4_Q50']), tuple(identity['CC4_Q90']), reference.begin)
    prefix = []
    for uid, m in sorted(metadata.items()):
        if m.get('origin_unknown') is not True:
            continue
        submit = m['submit_seconds']
        if submit < reference.begin:
            prefix.append(uid)
        elif submit <= now and submit < reference.begin+86400 and m.get('cc4_eligible', True):
            book.submit(uid, submit, now, m['gpu'], m['t50_seconds'])
    rows = [book.row(h, now) for h in range(24)]
    q50 = np.asarray(identity['CC4_Q50'], float)
    remaining = np.asarray([r['remaining_CC4_Q50_GPUh'] for r in rows])
    ratio = np.divide(remaining, q50, out=np.zeros(24), where=q50 > 0)
    x = np.asarray(nominal['x_GPUh'], float)
    carry = np.asarray(nominal['carryout_GPUh_by_hour'], float)
    site = reference.arrays['G_Unknown_Q50_Plan']
    site_total = site.sum(axis=1)
    weights = np.divide(site, site_total[:,None], out=np.zeros_like(site), where=site_total[:,None] > 0)
    # z[h,t,s] has both exact native marginals before residual depletion.
    cohort_site = 4*x[:,:,None]*weights[None,:,:]
    if not np.allclose(cohort_site.sum(axis=0), site, atol=1e-7, rtol=0):
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='COHORT_SITE_MARGINAL_DRIFT',
            safe_promotion_allowed=False, hard_occupancy=False)
    residual = (cohort_site*ratio[:,None,None]).sum(axis=0)
    residual_carry = carry*ratio
    mass = residual.sum()/4+residual_carry.sum()
    if abs(mass-remaining.sum()) > 1e-7:
        return z, dict(status='CONSERVATION_NOT_CERTIFIED', reason='RESIDUAL_COHORT_MASS_DRIFT',
            safe_promotion_allowed=False, hard_occupancy=False)
    return residual, dict(status='SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS', hard_occupancy=False,
        original_nominal_service_sha=nominal['nominal_service_sha'], original_forecast_mutated=False,
        residual_nominal_GPUh=float(remaining.sum()), residual_in_day_GPUh=float(residual.sum()/4),
        residual_carryout_GPUh=float(residual_carry.sum()), cohort_rows=rows,
        unique_Dday_observed_UIDs=sorted(book.submissions), prefix_Unknown_UIDs_separate=prefix,
        mathematical_site_cohort_coupling='CANONICAL_TRANSPORTATION_PRODUCT_PRESERVES_BOTH_NATIVE_MARGINALS',
        actual_physical_completion_or_future_UID_read=False, Q90_as_physical_occupancy=False)


class SignedSensitivityPolicy:
    frozen_schema = CONTRACT
    lookup_only = False
    controller_contract = CONTRACT
    execution_mode = MODE

    def __init__(self, reference, packet, *, bindings, expected_bindings, migration_authority=None,
                 runtime_repair=True, basic=False, evidence_scope='REAL_DIAGNOSTIC'):
        require_bindings(bindings, expected_bindings)
        reference.require_immutable()
        if packet.bindings != bindings or tuple(packet.sites) != reference.sites or packet.begin_seconds != reference.begin:
            raise ValueError('SIGNED_ALLOCATION_COMMON_AXIS_BINDING_DRIFT')
        self.reference, self.packet = reference, packet
        self.bindings = dict(bindings)
        self.migration_authority = deepcopy(migration_authority)
        self.runtime_repair, self.basic, self.evidence_scope = runtime_repair, basic, evidence_scope
        self.spec = dict(contract=CONTRACT, bindings=self.bindings, evidence_scope=evidence_scope,
            reference_target_sha=reference.sha, migration_authority_sha=digest(self.migration_authority),
            response_numeric_sha=grid_numeric_fingerprint(packet),
            C1_source_sha=reference.identity.get('C1_Power_Model_SHA'),
            current_power_model='EXACT_OBSERVED_ORIGINAL_C1_PCC_PQ',
            future_power_model='ORIGINAL_DMINUS1_C1_ENDPOINT_SECANT_PREDICTION',
            allocation_source_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            anonymous_residual_rule='EXACT_SOURCE_COHORT_TRANSPORT_FORECASTBOOK_DEPLETION_V1',
            ranking=['HARD_FEASIBILITY', 'ALL_LINE_PHASE_TIME_MAX_LOADING', 'CRITICAL_LOADING_HOURS',
                'Q90_RUNTIME_QUEUE_REBOUND_RISK', 'INTENTIONAL_DELAY', 'MIGRATION_COUNT', 'DETERMINISTIC_SITE_TIME'],
            candidates_seconds=list(DELAY_SECONDS), online_global_optimizer_calls=0, runtime_repair=runtime_repair,
            basic=basic, anonymous_CC4_hard_occupancy=False, conditional_remaining_provider='NOT_CERTIFIED')
        self.sha = digest(self.spec)
        self.audit, self.funnel, self.times = [], [], []
        self.assignments, self.last_selection = {}, {}
        self.current, self.metadata = None, {}
        self.boundary_completed_UIDs = set()
        self.diagnostics = []
        self._baseline_grid_cache = {}
        self.baseline_cache_hits, self.baseline_cache_misses = 0, 0
        self._c1_model, self._current_weather_provider = None, None
        self._selection_response_sha = None
        if evidence_scope.startswith('REAL') and not self.spec['C1_source_sha']:
            raise ValueError('REAL_FROZEN_C1_SOURCE_SHA_REQUIRED')

    @property
    def document(self):
        self.reference.require_immutable()
        return dict(schema=self.frozen_schema, spec=deepcopy(self.spec), policy_sha=self.sha,
            bindings=deepcopy(self.bindings), reference=dict(
                arrays={k:v.tolist() for k,v in self.reference.arrays.items()},
                sites=list(self.reference.sites), begin=self.reference.begin,
                commands=self.reference.commands, identity=deepcopy(self.reference.identity),
                target_sha=self.reference.sha), migration_authority=deepcopy(self.migration_authority))

    def save(self, path):
        Path(path).write_text(json.dumps(self.document, sort_keys=True, allow_nan=False), encoding='utf-8')

    @classmethod
    def load(cls, path, *, bindings):
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        require_bindings(d['bindings'], bindings)
        if d['schema'] != cls.frozen_schema or digest(d['spec']) != d['policy_sha']:
            raise ValueError('SIGNED_SERIALIZED_POLICY_SHA_DRIFT')
        if d['spec']['allocation_source_sha'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
            raise ValueError('SIGNED_ALLOCATION_CODE_SOURCE_DRIFT')
        r, a = d['reference'], d['reference']['arrays']
        reference = TrackingReference(a['G_Known_Plan'], a['G_Unknown_Q50_Plan'], a['IT_Plan'],
            a['PCC_P_Plan'], a['PCC_Q_Plan'], sites=r['sites'], begin=r['begin'],
            commands=r['commands'], identity=r['identity'])
        if reference.sha != r['target_sha']:
            raise ValueError('SIGNED_SERIALIZED_REFERENCE_SHA_DRIFT')
        if (reference.sha != d['spec']['reference_target_sha'] or
                digest(d['migration_authority']) != d['spec']['migration_authority_sha']):
            raise ValueError('SIGNED_SERIALIZED_REFERENCE_OR_MIGRATION_AUTHORITY_DRIFT')
        self = cls.__new__(cls)
        self.reference, self.packet, self.bindings = reference, None, dict(bindings)
        self.spec, self.sha = d['spec'], d['policy_sha']
        self.migration_authority = d['migration_authority']
        self.runtime_repair, self.basic = self.spec['runtime_repair'], self.spec['basic']
        self.evidence_scope = self.spec['evidence_scope']
        self.audit, self.funnel, self.times, self.diagnostics = [], [], [], []
        self.assignments, self.last_selection = {}, {}
        self.current, self.metadata = None, {}
        self.boundary_completed_UIDs = set()
        self._baseline_grid_cache = {}
        self.baseline_cache_hits, self.baseline_cache_misses = 0, 0
        self._c1_model, self._current_weather_provider = None, None
        self._selection_response_sha = None
        return self

    def bind_runtime_packet(self, packet):
        if packet.bindings != self.bindings or tuple(packet.sites) != self.reference.sites or packet.begin_seconds != self.reference.begin:
            raise ValueError('SIGNED_RUNTIME_PACKET_ANCHOR_DRIFT')
        if grid_numeric_fingerprint(packet) != self.spec['response_numeric_sha']:
            raise ValueError('SIGNED_RUNTIME_RESPONSE_NUMERIC_DRIFT')
        self.packet = packet
        return self

    def bind_observed_c1(self, model, *, current_weather_provider):
        """Late bind a source-pinned C1 callback and current-tick-only weather.

        The policy never receives or enumerates future Actual weather. The
        driver supplies a guarded callback after observing its current tick.
        """
        if (not model.authority_sha or not callable(current_weather_provider)
                or self.packet is None or model.capacities != self.packet.capacities
                or abs(model.power_factor-self.packet.pf) > 1e-12):
            raise ValueError('OBSERVED_ORIGINAL_C1_AUTHORITY_REQUIRED')
        expected = self.spec['C1_source_sha']
        if self.evidence_scope.startswith('REAL') and (not expected or model.authority_sha != expected):
            raise ValueError('REAL_ORIGINAL_C1_SOURCE_SHA_DRIFT')
        if expected is not None and model.authority_sha != expected:
            raise ValueError('FROZEN_C1_SOURCE_SHA_DRIFT')
        self._c1_model, self._current_weather_provider = model, current_weather_provider
        self._baseline_grid_cache.clear()
        return self

    def _current_weather(self, now):
        if self.current is None or self.current[0] != float(now):
            raise ValueError('ONLY_CURRENT_OBSERVED_WEATHER_ALLOWED')
        if self._current_weather_provider is None:
            if self.evidence_scope.startswith('REAL'):
                raise ValueError('REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED')
            return None
        weather = deepcopy(self._current_weather_provider(float(now)))
        _require_public_metadata(weather)
        return weather

    def _grid_delta(self, t, gpu, now):
        if t == int((now-self.reference.begin)//900) and self._c1_model is not None:
            weather = self._current_weather(now)
            exact = self._c1_model.recompute(np.asarray([gpu], float), self.packet.sites, [weather])
            cols = [self.packet.control_names.index('aidc_load_kw['+s+']') for s in self.packet.sites]
            return (exact['PCC_P_kw'][0]-self.packet.controls[t, cols])/self.packet.p_slope[t]
        if t == int((now-self.reference.begin)//900) and self.evidence_scope.startswith('REAL'):
            raise ValueError('REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED')
        return gpu-self.reference.arrays['G_Total_Plan'][t]

    def require_bindings(self, expected):
        require_bindings(self.bindings, expected)
        if digest(self.spec) != self.sha:
            raise ValueError('SIGNED_POLICY_SHA_DRIFT')
        self.reference.require_immutable()
        if (self.reference.sha != self.spec['reference_target_sha'] or
                digest(self.migration_authority) != self.spec['migration_authority_sha']):
            raise ValueError('SIGNED_REFERENCE_OR_MIGRATION_AUTHORITY_DRIFT')
        if self.packet is not None and self.packet.bindings != self.bindings:
            raise ValueError('SIGNED_RUNTIME_PACKET_ANCHOR_DRIFT')
        if (self.packet is not None and self.evidence_scope.startswith('REAL')
                and grid_numeric_fingerprint(self.packet) != self.spec['response_numeric_sha']):
            raise ValueError('SIGNED_RUNTIME_RESPONSE_NUMERIC_DRIFT')

    def observe(self, now, use, metadata):
        if self.current is None or self.current[0] != float(now) or self.current[1] != dict(use):
            self._baseline_grid_cache.clear()
        self.current = (float(now), dict(use))
        self.metadata = metadata

    def _public_future(self, reservations, exclude):
        """Per-UID union; Running forecasts are separate from hard holds."""
        hard = np.zeros_like(self.reference.arrays['G_Total_Plan'])
        expected = hard.copy()
        known = hard.copy()
        bookings = reservations.reservations
        plans = getattr(reservations, 'known_plans', {})
        uids = set(bookings) | set(plans) | set(self.metadata)
        for uid in uids:
            if uid == exclude or uid in self.boundary_completed_UIDs:
                continue
            booking = bookings.get(uid, {})
            rows = [] if booking.get('status') == 'RELEASED' else booking.get('segments', [])
            rows = rows + plans.get(uid, [])
            m = self.metadata.get(uid, {})
            if m.get('state') == 'COMPLETED':
                rows = []
            hard_profile = service_integral(self.packet.sites, rows, self.reference.begin)
            hard += hard_profile
            future_rows = rows
            if m.get('state') == 'RUNNING':
                remaining = max(0., m['t50_seconds']-m.get('accumulated_compute_seconds', 0))
                hold = max(remaining, 900-self.current[0]%900)
                future_rows = rows + [dict(resource='gpu:'+m['current_site'], begin=self.current[0],
                    end=self.current[0]+hold, quantity=m['gpu'])]
            elif m.get('state') == 'PENDING' and m.get('origin_unknown') is True and not rows:
                # Submitted work removed from its anonymous SUBMIT cohort can
                # still be waiting. Its public FCFS prediction is soft; it is
                # never inserted into a committed/hard reservation ledger.
                site = m.get('reference_site', m.get('source_site'))
                if site in self.packet.sites:
                    start = max(self.current[0], m['reference_start_seconds'])
                    future_rows = [dict(resource='gpu:'+site, begin=start,
                        end=start+max(m['t50_seconds'], 1e-9), quantity=m['gpu'])]
            expected_profile = service_integral(self.packet.sites, future_rows, self.reference.begin)
            expected += expected_profile
            if uid in plans or m.get('origin_unknown') is False:
                known += hard_profile
        slot = int((self.current[0]-self.reference.begin)//900)
        if 0 <= slot < 96:
            instant = np.array([self.current[1][s] for s in self.packet.sites], float)
            own = self.metadata.get(exclude, {})
            if own.get('state') == 'RUNNING':
                instant[self.packet.sites.index(own['current_site'])] -= own['gpu']
            hard[slot] = np.maximum(hard[slot], instant)
            expected[slot] = np.maximum(expected[slot], instant)
        self.last_hard_profile = hard
        anonymous, audit = anonymous_cohort_residual(self.reference, self.metadata, self.current[0])
        self.anonymous_residual_audit = audit
        # Current is exact observed physical C1; future anonymous demand is a
        # separate residual expectation and never enters reservations.feasible.
        if audit['status'] == 'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS':
            anonymous[:max(0, slot+1)] = 0
            expected += anonymous
        return expected, known

    def current_guard(self, metadata, segments, now, observed):
        # Execution-phase guards receive a fresh physical observation even
        # between control ticks; it is not a future candidate observation.
        if self.current is None or self.current[0] != float(now):
            self.observe(now, observed, self.metadata)
        slot = int((now-self.reference.begin)//900)
        if not 0 <= slot < 96:
            return 'CURRENT_GRID_SLOT_UNSUPPORTED'
        instant = np.array([observed[s] for s in self.packet.sites], float)
        if metadata.get('state') == 'RUNNING':
            instant[self.packet.sites.index(metadata['current_site'])] -= metadata['gpu']
        for seg in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            site = seg['resource'][4:]
            if metadata['gpu'] > max(self.packet.rack_compatibility[site]):
                return 'RACK_GANG_INCOMPATIBLE'
            if seg['begin'] <= now < seg['end']:
                instant[self.packet.sites.index(site)] += seg['quantity']
        if np.any(instant > [self.packet.capacities[s]+1e-9 for s in self.packet.sites]):
            return 'GPU_CAPACITY'
        _, bad = self.packet._at_slot(slot, self._grid_delta(slot, instant, now))
        return None if not bad else 'CURRENT_OBSERVED_'+bad[0]['reason']

    def _score(self, metadata, segments, now, baseline):
        if getattr(self, 'anonymous_residual_audit', {}).get('status') == 'CONSERVATION_NOT_CERTIFIED':
            return None, 'ANONYMOUS_FORECAST_CONSERVATION_NOT_CERTIFIED'
        profile = service_integral(self.packet.sites, segments, self.reference.begin)
        slot = int((now-self.reference.begin)//900)
        instant_base = np.asarray([self.current[1][s] for s in self.packet.sites], float)
        if metadata.get('state') == 'RUNNING':
            instant_base[self.packet.sites.index(metadata['current_site'])] -= metadata['gpu']
        instant_candidate = instant_base.copy()
        for row in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            if row['begin'] <= now < row['end']:
                instant_candidate[self.packet.sites.index(row['resource'][4:])] += row['quantity']
        # Exact original rows are cached only for the complete same baseline,
        # clock and response authority. A candidate changes only its own GPU
        # profile; untouched slots retain their original scores/violations.
        authority = (digest(self.packet.bindings), digest(self.packet.authority),
            self._selection_response_sha or grid_numeric_fingerprint(self.packet),
            tuple(c.coefficient_sha256 for c in self.packet.coefficients),
            self.packet.controls.tobytes(), self.packet.p_slope.tobytes(),
            self.packet.voltage_lower, self.packet.voltage_upper,
            tuple(self.packet.line_indices), tuple(self.packet.transformer_indices),
            None if self._c1_model is None else self._c1_model.authority_sha,
            digest(self._current_weather(now)), instant_base.tobytes())
        key = (float(now), slot, baseline.tobytes(), authority)
        cached = self._baseline_grid_cache.get(key)
        if cached is None:
            cached = {t:self.packet._at_slot(t, self._grid_delta(t, instant_base if t == slot else baseline[t], now))
                for t in range(max(0, slot), 96)}
            self._baseline_grid_cache[key] = cached
            self.baseline_cache_misses += 1
            if len(self._baseline_grid_cache) > 4:
                self._baseline_grid_cache.pop(next(iter(self._baseline_grid_cache)))
        else:
            self.baseline_cache_hits += 1
        peaks, violations, nonworsening = [], [], True
        for t in range(max(0, slot), 96):
            if t == slot or np.any(profile[t]):
                gpu = instant_candidate if t == slot else baseline[t]+profile[t]
                delta = self._grid_delta(t, gpu, now)
                peak, bad = self.packet._at_slot(t, delta)
            else:
                peak, bad = cached[t]
            peaks.append(peak)
            if bad:
                _, base_bad = cached[t]
                nonworsening = nonworsening and {r['reason'] for r in bad}.issubset({r['reason'] for r in base_bad})
                violations.extend(bad)
        if violations:
            self.diagnostics.append(dict(uid=metadata['uid'], time_seconds=now,
                status='BASELINE_SAME_VIOLATION_TYPE_NOT_SAFE_PASS' if nonworsening else 'HARD_GRID_REJECT',
                violations=violations, hard_feasible=False))
            return None, 'PREDICTED_'+violations[0]['reason']
        q90 = metadata.get('experimental_prediction_Q90_seconds')
        risk = max(0., float(metadata['t50_seconds'] if q90 is None else q90)-metadata['t50_seconds'])*metadata['gpu']/3600
        soft_over = float(np.maximum(baseline+profile-[self.packet.capacities[s] for s in self.packet.sites], 0).sum()/4)
        return dict(grid_peak=max(peaks, default=0.), loading_hours=sum(peaks)*.25,
            risk_GPUh=risk+soft_over, soft_prediction_capacity_risk_GPUh=soft_over,
            checked_grid_slots=len(peaks), Job_Q90_seconds=q90, profile=profile,
            affine_approximation_only=True, Fresh_AC_PASS_claimed=False), None

    def _record(self, m, now, decision, began, count, rejected):
        self._selection_response_sha = None
        elapsed = perf_counter()-began
        self.times.append(elapsed)
        decision.update(uid=m['uid'], policy_sha=self.sha, online_global_optimizer_calls=0,
            execution_mode=MODE, controller_contract=CONTRACT, candidate_count=count,
            decision_seconds=elapsed, rejected_candidates=rejected)
        self.last_selection[m['uid']] = deepcopy(decision)
        self.audit.append(dict(uid=m['uid'], time_seconds=now, state=m['state'], decision=deepcopy(decision)))
        return decision

    def select(self, metadata, receipt, now, reservations, *, reserve=True):
        began = perf_counter()
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if not metadata.get('is_observed', True) or metadata['submit_seconds'] > now:
            return self._record(metadata, now, dict(action='QUEUE', status='OBSERVATION_REQUIRED'), began, 0, [])
        if self.current is None or self.current[0] != now:
            raise ValueError('CURRENT_OBSERVATION_REQUIRED')
        if int(metadata['gpu']) != metadata['gpu'] or metadata['gpu'] <= 0:
            raise ValueError('WHOLE_GPU_GANG_REQUIRED')
        r = _receipt(receipt)
        self._selection_response_sha = grid_numeric_fingerprint(self.packet)
        baseline, _ = self._public_future(reservations, metadata['uid'])
        source = metadata.get('reference_site', metadata.get('source_site'))
        origin = math.ceil(max(now, r['reference_start_seconds'], metadata.get('release_seconds') or -math.inf,
            metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        allowed = set(r['allowed_starts_seconds'])
        starts = sorted({origin} | {r['reference_start_seconds']+d for d in DELAY_SECONDS
            if r['reference_start_seconds']+d >= now and r['reference_start_seconds']+d in allowed})
        rows, rejected, count = [], [], 0
        for site in sorted(set(metadata['compatible_sites'])):
            if site != source and (self.basic or metadata.get('can_prestart_place') is not True):
                rejected.append(dict(site=site, reason='PREPLACE_SOURCE_AUTHORITY'))
                continue
            for start in starts:
                count += 1
                if self.basic and (site != source or start != origin):
                    continue
                end = start+max(metadata['t50_seconds'], 1e-9)
                spend = max(metadata.get('additional_start_delay_seconds', 0), start-r['reference_start_seconds'], 0)
                reason = None
                queue_only = site == source and start == origin and origin > r['latest_start_seconds']
                if not queue_only and start not in allowed:
                    reason = 'SOURCE_START_WINDOW'
                if not queue_only and spend+metadata.get('cumulative_migration_interruption_seconds', 0) > r['budget_seconds']+1e-9:
                    reason = 'SHARED_QOS_BUDGET'
                if start > origin and metadata.get('Can_TimeShift') is not True:
                    reason = 'NO_TIME_SHIFT_AUTHORITY'
                if metadata['gpu'] > max(self.packet.rack_compatibility[site]):
                    reason = 'RACK_GANG_INCOMPATIBLE'
                if any(metadata.get(k) is not None and value > metadata[k] for k, value in (
                        ('hard_latest_start_seconds', start), ('completion_deadline_seconds', end))):
                    reason = 'HARD_WINDOW'
                segments = [dict(resource='gpu:'+site, begin=start, end=end, quantity=metadata['gpu'])]
                if reason is None and metadata.get('runtime_backfill_evaluation_seconds') == now and start == now:
                    ok, why = safe_backfill(metadata, now=now, site=site,
                        reservations=reservations, uid=metadata['uid'], evidence_scope=self.evidence_scope)
                    if not ok:
                        reason = 'BACKFILL_'+why
                if reason is None:
                    reason = reservations.feasible(segments, exclude=metadata['uid'])
                if reason is None:
                    reason = self.current_guard(metadata, segments, now, self.current[1])
                score = None
                if reason is None:
                    score, reason = self._score(metadata, segments, now, baseline)
                if reason:
                    rejected.append(dict(site=site, start_seconds=start, reason=reason))
                    continue
                burden = metadata.get('additional_start_delay_seconds', 0) if queue_only else spend
                key = (round(score['grid_peak'], 12), score['loading_hours'], score['risk_GPUh'], burden, 0, site, start)
                rows.append((key, dict(site=site, start_seconds=start, nominal_end_seconds=end,
                    segments=segments, additional_start_delay_seconds=burden,
                    action='PREPLACE' if site != source else 'DELAY' if start > origin else 'START',
                    status='SIGNED_MAX_LOADING_SELECTED',
                    tracking={k:v for k,v in score.items() if k != 'profile'}), score['profile']/4))
        for _, row, profile in sorted(rows, key=lambda x:x[0]):
            if reserve:
                ok, reason = reservations.reserve(metadata['uid'], row['segments'], replace=True)
                if not ok:
                    rejected.append(dict(site=row['site'], reason=reason))
                    continue
                metadata['additional_start_delay_seconds'] = max(metadata.get('additional_start_delay_seconds', 0), row['additional_start_delay_seconds'])
                self.assignments[metadata['uid']] = profile
            return self._record(metadata, now, row, began, count, rejected)
        return self._record(metadata, now, dict(action='QUEUE', status='NO_HARD_FEASIBLE_SIGNED_ACTION',
            reason=rejected[-1]['reason'] if rejected else 'NO_AUTHORIZED_ACTION'), began, count, rejected)

    def select_migration(self, metadata, receipt, now, reservations, *, checkpoint_at=None, reserve=True):
        began = perf_counter()
        self._selection_response_sha = grid_numeric_fingerprint(self.packet)
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        stages = dict(RUNNING=metadata.get('state') == 'RUNNING', CHECKPOINT=False,
            AUTHORITY=False, DESTINATION=False, REMAINING=False, WAN=False, GPU_RACK=False,
            BUDGET=False, SELECTED=False, COMPLETED=False)
        rejected, rows = [], []
        def stay(reason):
            self.funnel.append(dict(uid=metadata['uid'], time_seconds=now, reason=reason, **stages))
            return self._record(metadata, now, dict(action='STAY', status=reason, reason=reason), began, len(rows), rejected)
        elapsed = metadata.get('accumulated_compute_seconds', 0)
        if not stages['RUNNING']:
            return stay('NO_OBSERVED_RUNNING')
        if elapsed < 1800 or abs(elapsed%1800) > 1e-7 or checkpoint_at is None or checkpoint_at > now:
            return stay('NO_OBSERVED_CHECKPOINT')
        stages['CHECKPOINT'] = True
        if metadata.get('migration_count', 0):
            return stay('MAXIMUM_ONE_MIGRATION')
        if self.basic or metadata.get('Can_Checkpoint_Migrate') is not True:
            return stay('NO_CHECKPOINT_SOURCE_AUTHORITY')
        stages['AUTHORITY'] = True
        remaining = max(0., metadata['t50_seconds']-elapsed)
        if remaining <= 0:
            return stay('CONDITIONAL_REMAINING_NOT_CERTIFIED_RUNNING_HOLD')
        stages['REMAINING'] = True
        baseline, _ = self._public_future(reservations, metadata['uid'])
        stay_segments = [dict(resource='gpu:'+metadata['current_site'], begin=now, end=now+remaining, quantity=metadata['gpu'])]
        stay_score, _ = self._score(metadata, stay_segments, now, baseline)
        for destination in sorted(set(metadata['compatible_sites'])-{metadata['current_site']}):
            stages['DESTINATION'] = True
            cap = deepcopy(metadata.get('migration_capability') or _migration_capability(
                self.migration_authority, metadata['current_site'], destination, metadata['gpu']))
            if not cap:
                rejected.append(dict(site=destination, reason='NO_SOURCE_WAN_TRANSFER_RESTART_AUTHORITY'))
                continue
            stages['WAN'] = True
            m = dict(metadata, migration_capability=cap)
            migration, reason = migration_guard(m, receipt, now=now, accumulated_compute_seconds=elapsed,
                destination=destination, remaining_nominal_seconds=remaining, reservations=reservations, checkpoint_at=checkpoint_at)
            if migration is None:
                rejected.append(dict(site=destination, reason=reason))
                continue
            stages['BUDGET'] = True
            a, b = migration['times']['transfer_start'], migration['times']['transfer_end']
            migration['segments'].extend(dict(resource='wan:LINK::'+link, begin=a, end=b,
                quantity=cap['bandwidth_bytes_per_second']) for link in cap.get('route_links', []))
            reason = reservations.feasible(migration['segments'], exclude=metadata['uid'])
            if reason is None:
                reason = self.current_guard(metadata, migration['segments'], now, self.current[1])
            if reason:
                rejected.append(dict(site=destination, reason=reason))
                continue
            stages['GPU_RACK'] = True
            score, reason = self._score(metadata, migration['segments'], now, baseline)
            if reason:
                rejected.append(dict(site=destination, reason=reason))
                continue
            key = lambda s, burden: (round(s['grid_peak'], 12), s['loading_hours'], s['risk_GPUh'], burden)
            if stay_score is not None and key(score, migration['interruption_seconds']) >= key(stay_score, 0):
                rejected.append(dict(site=destination, reason='FEASIBLE_STAY_RANK_PREFERRED'))
                continue
            rows.append((key(score, migration['interruption_seconds']), destination, cap, migration, score))
        for _, destination, cap, migration, score in sorted(rows, key=lambda x:(x[0], x[1])):
            if reserve:
                ok, reason = reservations.reserve(metadata['uid'], migration['segments'], replace=True)
                if not ok:
                    rejected.append(dict(site=destination, reason=reason))
                    continue
                metadata['migration_capability'] = cap
            stages['SELECTED'] = True
            self.funnel.append(dict(uid=metadata['uid'], time_seconds=now,
                reason='FEASIBLE_MIGRATION_REPLACES_INFEASIBLE_STAY' if stay_score is None else 'SELECTED', **stages))
            return self._record(metadata, now, dict(action='CHECKPOINT_MIGRATE', status='SIGNED_MIGRATION_SELECTED',
                migration=migration, tracking={k:v for k,v in score.items() if k != 'profile'}), began, len(rows), rejected)
        return stay(rejected[-1]['reason'] if rejected else 'NO_DESTINATION')


class SiteOnlySensitivityPolicy(SignedSensitivityPolicy):
    """Historical diagnostic selector retained for exact evidence replay.

    The immutable historical Known plan is an input, never a new optimizer
    result. CC4 forecasts and future electrical rows do not enter this choice.
    """
    frozen_schema = SITE_ONLY_CONTRACT
    controller_contract = SITE_ONLY_CONTRACT
    execution_mode = 'FROZEN_KNOWN_CURRENT_UNKNOWN_SITE_ONLY'

    def __init__(self, reference, packet, *, bindings, expected_bindings,
                 basic=False, evidence_scope='REAL_HISTORICAL_PLAN_DIAGNOSTIC', source_identity=None,
                 site_authority=None):
        super().__init__(reference,packet,bindings=bindings,expected_bindings=expected_bindings,
            migration_authority=None,runtime_repair=False,basic=basic,evidence_scope=evidence_scope)
        self.spec.update(contract=SITE_ONLY_CONTRACT,active_scope='FROZEN_KNOWN_UNKNOWN_SITE_ONLY',
            source_identity=deepcopy(source_identity or {}),intentional_delay_seconds=0,
            site_authority=deepcopy(site_authority),site_authority_sha=digest(site_authority),
            candidates_seconds=[0],runtime_repair=False,migration=False,new_Known_optimization=False,
            current_power_model='EXACT_OBSERVED_ORIGINAL_C1_PCC_PQ',
            future_power_model='NOT_USED_BY_SITE_ONLY_DECISION',
            anonymous_residual_rule='NOT_USED_BY_SITE_ONLY_DECISION',
            ranking=['CURRENT_HARD_FEASIBILITY','CURRENT_ALL_LINE_PHASE_MAX_LOADING',
                'SOURCE_REFERENCE_SITE_TIE_PREFERENCE','DETERMINISTIC_SITE'],
            source_QoS_policy_sha=bindings['qos_sha'],research60_authority_active=False,
            max_candidate_sites=12,Known_commands_modified=False)
        self.sha=digest(self.spec)
        self.current_candidates=[]
        self.known_current_guards=[]

    def _study_site_authorized(self,metadata):
        authority=self.spec.get('site_authority')
        if authority is None:return False
        if (digest(authority)!=self.spec['site_authority_sha']
                or authority.get('schema')!='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1'
                or authority.get('interface_sha')!=self.bindings['interface_sha']
                or authority.get('study_case_sha')!=self.spec['source_identity'].get('study_case_sha')
                or authority.get('candidate_axis')!='SOURCE_COMPATIBLE_SITES_ONLY'
                or authority.get('intentional_delay_seconds')!=0 or authority.get('max_sites')!=12
                or authority.get('Known_commands_modified') is not False
                or authority.get('source_customer_SLA_claim') is not False):
            raise ValueError('SITE_ONLY_PUBLIC_STUDY_SITE_AUTHORITY_DRIFT')
        return metadata.get('origin_unknown') is True and metadata.get('state')=='PENDING'

    @classmethod
    def load(cls,path,*,bindings):
        self=super().load(path,bindings=bindings)
        if (self.spec.get('active_scope')!='FROZEN_KNOWN_UNKNOWN_SITE_ONLY'
                or self.spec.get('candidates_seconds')!=[0] or self.spec.get('intentional_delay_seconds')!=0
                or self.runtime_repair or self.spec.get('migration') or self.migration_authority is not None):
            raise ValueError('SITE_ONLY_FROZEN_SCOPE_DRIFT')
        self.current_candidates=[]
        self.known_current_guards=[]
        return self

    def _record(self,m,now,decision,began,count,rejected):
        result=super()._record(m,now,decision,began,count,rejected)
        result.update(execution_mode=self.execution_mode,controller_contract=SITE_ONLY_CONTRACT,
            intentional_delay_seconds=0,additional_start_delay_seconds=0,
            time_shift=False,runtime_repair=False,migration=False)
        self.last_selection[m['uid']]=deepcopy(result)
        self.audit[-1]['decision']=deepcopy(result)
        return result

    def _public_future(self,*args,**kwargs):
        raise ValueError('SITE_ONLY_FUTURE_FORECAST_OR_ELECTRICAL_LOOKAHEAD_FORBIDDEN')

    def _admission_hold(self, site, now, end, gpu):
        horizon=float(self.spec['source_identity'].get('Known_booking_horizon_seconds',self.reference.begin+86400))
        return [dict(resource='gpu:'+site,begin=now,end=max(end,horizon),quantity=gpu)], horizon

    def _admission_conflict(self, reservations, held, uid):
        conflict=reservations.feasible(held,exclude=uid)
        return ('UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING'
            if conflict and getattr(reservations,'known_plans',{}) else conflict)

    def _earliest_event(self,metadata,receipt):
        return max(receipt['reference_start_seconds'],metadata['submit_seconds'],
            metadata.get('release_seconds') or -math.inf,metadata.get('hard_earliest_start_seconds') or -math.inf)

    def current_guard(self,metadata,segments,now,observed):
        reason=super().current_guard(metadata,segments,now,observed)
        if metadata.get('origin_unknown') is False:
            candidate=np.asarray([observed[s] for s in self.packet.sites],float)
            for row in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
                if row['begin']<=now<row['end']:
                    candidate[self.packet.sites.index(row['resource'][4:])]+=row['quantity']
            witness=dict(uid=metadata['uid'],time_seconds=now,observed_GPU_by_site=dict(observed),
                candidate_GPU_by_site=dict(zip(self.packet.sites,candidate.tolist())),guard_reason=reason,
                immutable_source_rule=True,Unknown_allocator_used=False)
            if self._c1_model is not None:
                power=self._c1_model.recompute(candidate[None,:],self.packet.sites,[self._current_weather(now)])
                witness.update(PCC_P_kw=power['PCC_P_kw'][0].tolist(),PCC_Q_kvar=power['PCC_Q_kvar'][0].tolist())
            self.known_current_guards.append(witness)
        return reason

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        began=perf_counter();require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if metadata.get('state')!='PENDING' or metadata.get('is_observed',True) is not True or metadata['submit_seconds']>now:
            return self._record(metadata,now,dict(action='QUEUE',status='OBSERVED_PENDING_REQUIRED'),began,0,[])
        if self.current is None or self.current[0]!=now or now%900:
            raise ValueError('CURRENT_EXECUTABLE_CONTROL_OBSERVATION_REQUIRED')
        if metadata['gpu']<=0 or int(metadata['gpu'])!=metadata['gpu']:
            raise ValueError('WHOLE_GPU_GANG_REQUIRED')
        r=_receipt(receipt)
        earliest=self._earliest_event(metadata,r)
        if now<earliest:
            return self._record(metadata,now,dict(action='QUEUE',status='SOURCE_EVENT_NOT_EXECUTABLE_YET',
                reason='SOURCE_EVENT_NOT_EXECUTABLE_YET',earliest_executable_seconds=math.ceil(earliest/900)*900),began,0,[])
        # After a source FCFS start, waiting for observed capacity is an
        # unavoidable queue wait. It is not a discretionary future start.
        # The original representation and hard windows still bind that event.
        represented=metadata.get('representation_starts_seconds')
        if represented is None or now not in set(represented):
            return self._record(metadata,now,dict(action='QUEUE',status='SOURCE_REPRESENTATION_WINDOW',
                reason='SOURCE_REPRESENTATION_WINDOW'),began,0,[])
        end=now+max(metadata['t50_seconds'],1e-9)
        if ((metadata.get('hard_latest_start_seconds') is not None and now>metadata['hard_latest_start_seconds'])
                or (metadata.get('completion_deadline_seconds') is not None and end>metadata['completion_deadline_seconds'])):
            return self._record(metadata,now,dict(action='QUEUE',status='EMPTY_AUTHORIZED_HARD_WINDOW',
                reason='EMPTY_AUTHORIZED_HARD_WINDOW'),began,0,[])
        source=metadata.get('reference_site',metadata.get('source_site'))
        sites=sorted(set(metadata['compatible_sites']))
        if len(sites)>12 or any(s not in self.packet.sites for s in sites):
            raise ValueError('SITE_ONLY_MAX12_EXACT_SOURCE_COMPATIBLE_AXIS_REQUIRED')
        rows,rejected,count=[],[],0
        slot=int((now-self.reference.begin)//900)
        if not 0<=slot<96:
            return self._record(metadata,now,dict(action='QUEUE',status='CURRENT_GRID_SLOT_UNSUPPORTED'),began,0,[])
        base=np.asarray([self.current[1][s] for s in self.packet.sites],float)
        for site in sites:
            if site!=source and (self.basic or (metadata.get('can_prestart_place') is not True
                    and not self._study_site_authorized(metadata))):
                rejected.append(dict(site=site,reason='PREPLACE_SOURCE_AUTHORITY'));continue
            count+=1
            segments=[dict(resource='gpu:'+site,begin=now,end=end,quantity=metadata['gpu'])]
            reason=None
            if metadata['gpu']>max(self.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
            candidate=base.copy();candidate[self.packet.sites.index(site)]+=metadata['gpu']
            if reason is None and np.any(candidate>[self.packet.capacities[s] for s in self.packet.sites]):
                reason='GPU_CAPACITY_RUNNING_RETAINED'
            # No certified total-runtime upper bound is available. Keep the
            # offered gang through the entire declared study horizon when
            # testing firm bookings; Q50 only describes its nominal service.
            held,hold_end=self._admission_hold(site,now,end,metadata['gpu'])
            if reason is None:
                reason=self._admission_conflict(reservations,held,metadata['uid'])
            peak,bad=None,[];booking_conflict=None
            if reason=='UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING' or reason=='NO_CAPACITY':
                booking_conflict=deepcopy(getattr(reservations,'last_conflict',None))
            if reason is None:
                peak,bad=self.packet._at_slot(slot,self._grid_delta(slot,candidate,now))
                if bad:reason='CURRENT_OBSERVED_'+bad[0]['reason']
            witness=dict(uid=metadata['uid'],time_seconds=now,slot=slot,site=site,
                observed_GPU_by_site=dict(self.current[1]),candidate_GPU_by_site=dict(zip(self.packet.sites,candidate.tolist())),
                current_line_peak=peak,current_grid_violations=deepcopy(bad),hard_guard_reason=reason,
                coefficient_sha=self.packet.coefficients[slot].coefficient_sha256,
                current_C1_source_sha=self.spec['C1_source_sha'],future_grid_rows_evaluated=0,
                current_only=True,anonymous_CC4_hard_occupancy=False,
                unbounded_runtime_hold_end_seconds=hold_end,
                reservation_conflict=booking_conflict)
            if self._c1_model is not None:
                power=self._c1_model.recompute(candidate[None,:],self.packet.sites,[self._current_weather(now)])
                witness.update(candidate_PCC_P_kw=power['PCC_P_kw'][0].tolist(),
                    candidate_PCC_Q_kvar=power['PCC_Q_kvar'][0].tolist())
            self.current_candidates.append(witness)
            if reason:
                rejected.append(dict(site=site,start_seconds=now,reason=reason));continue
            decision=dict(site=site,start_seconds=now,nominal_end_seconds=end,segments=held,
                action='PREPLACE' if site!=source else 'START',status='SITE_ONLY_BASIC_SOURCE_SELECTED' if self.basic else 'SITE_ONLY_SIGNED_CURRENT_MAX_SELECTED',
                additional_start_delay_seconds=0,source_reference_start_seconds=r['reference_start_seconds'],
                unavoidable_queue_wait_seconds=max(0.,now-r['reference_start_seconds']),
                tracking=dict(grid_peak=peak,checked_grid_slots=1,checked_grid_slot=slot,
                    all_line_phase_rows=True,affine_approximation_only=True,Fresh_AC_PASS_claimed=False))
            rows.append(((peak,site!=source,site),decision))
        for _,decision in sorted(rows,key=lambda row:row[0]):
            if reserve:
                ok,reason=reservations.reserve(metadata['uid'],decision['segments'],replace=True)
                if not ok:
                    rejected.append(dict(site=decision['site'],reason=reason));continue
                self.assignments[metadata['uid']]=service_integral(self.packet.sites,decision['segments'],self.reference.begin)/4
            return self._record(metadata,now,decision,began,count,rejected)
        primary_reason=next((row['reason'] for row in rejected if row['site']==source),
            'NO_SOURCE_AUTHORIZED_SITE') if self.basic else (
            rejected[-1]['reason'] if rejected else 'NO_SOURCE_AUTHORIZED_SITE')
        return self._record(metadata,now,dict(action='QUEUE',status='NO_HARD_FEASIBLE_SITE_ONLY_ACTION',
            reason=primary_reason),began,count,rejected)

    def select_migration(self,metadata,receipt,now,reservations,**kwargs):
        return dict(uid=metadata['uid'],action='STAY',status='SITE_ONLY_MIGRATION_DISABLED')


class SiteOnlyReservationLedger(ContractReservationLedger):
    """Unknown nonpreemptive admission protects firm bookings without Q50 release."""
    def retain_running(self,uid,site,now,next_control,gpu):
        super().retain_running(uid,site,now,next_control,gpu)
        if self.owner.metadata.get(uid,{}).get('origin_unknown') is True:
            horizon=self.owner.policy.spec['source_identity'].get('Known_booking_horizon_seconds',
                self.owner.policy.reference.begin+86400)
            for row in self.reservations[uid]['segments']:
                if row['resource']=='gpu:'+site:
                    row['end']=max(row['end'],horizon)
            self.reservations[uid]['role']='UNKNOWN_OBSERVED_UNBOUNDED_BOOKING_UNTIL_COMPLETION'


class SiteOnlyJobEventController(JobEventController):
    """Original event simulator with frozen Known and a current site selector."""
    def __init__(self,*args,**kwargs):
        proof=kwargs.pop('boundary_completion_proof',None)
        policy=kwargs.get('frozen_policy')
        accepted_arms={'B1','B3'} if isinstance(policy,CurrentEventSensitivityPolicy) else {'B1'}
        if not isinstance(policy,SiteOnlySensitivityPolicy) or kwargs.get('arm') not in accepted_arms:
            raise ValueError('EXPLICIT_B1_SITE_ONLY_CONTROLLER_REQUIRED')
        super().__init__(*args,**kwargs)
        if digest(self.known_schedule)!=digest(policy.reference.commands):
            raise ValueError('SITE_ONLY_IMMUTABLE_KNOWN_COMMAND_SHA_DRIFT')
        self.frozen_known_sha=digest(self.known_schedule)
        self.provider_identity=(self.qos.case_sha,self.qos.provider_sha,self.qos.stats.sha)
        if self.provider_identity[0]!=policy.bindings['case_sha'] or self.provider_identity[2]!=policy.bindings['qos_sha']:
            raise ValueError('SITE_ONLY_SOURCE_QOS_IDENTITY_DRIFT')
        self.reservations=SiteOnlyReservationLedger(self,capacities=self.ledger.capacities,
            wan_capacities=kwargs.get('wan_capacities'))
        self.boundary_completed_UIDs=set();self.boundary_cancellations=[]
        self.boundary_completion_proof_sha=None
        if proof is not None:
            require_boundary_completion_proof(proof,bindings=policy.bindings,begin_seconds=policy.reference.begin)
            self.boundary_completed_UIDs={row['uid'] for row in proof['rows']}
            self.boundary_completion_proof_sha=proof['proof_sha']
            for uid in sorted(self.boundary_completed_UIDs&set(self.reservations.known_plans)):
                self.boundary_cancellations.append(dict(uid=uid,source_proof_sha=proof['proof_sha'],
                    cancelled_segments=self.reservations.known_plans.pop(uid),frozen_commands_modified=False))

    def submit(self,request,now):
        if request.uid in self.boundary_completed_UIDs:
            raise ValueError('BOUNDARY_COMPLETED_KNOWN_UID_RESUBMITTED')
        if hasattr(self.qos,'register_observed') and request.uid not in self.qos.contexts:
            self.qos.register_observed(request.uid,episode_id=request.metadata.get('experimental_participation_episode_id'),
                source_authority=request.metadata.get('source_qos_authority'))
        super().submit(request,now)
        # Preserve the source prestart-site authority. Participation in an
        # inactive QoS extension must not manufacture site permission.
        self.metadata[request.uid].update(can_prestart_place=request.metadata.get('can_prestart_place') is True,
            Can_TimeShift=False,Can_Checkpoint_Migrate=False)

    def _reference_decision(self,uid,now):
        if self.metadata[uid]['origin_unknown']:
            # The original zero-budget fallback must not bypass a grid/rack
            # rejection. Both C0 and C1 execute through the same site guard.
            return deepcopy(self.policy.last_selection.get(uid,
                dict(uid=uid,action='QUEUE',status='SITE_ONLY_SELECTOR_REQUIRED')))
        return super()._reference_decision(uid,now)

    def _known_decision(self,uid,now):
        command=self.known_schedule[uid]
        if command.get('execution_rule')=='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL':
            if not command['source_hard_window_valid'] or now not in set(self.metadata[uid]['representation_starts_seconds']):
                return dict(uid=uid,action='QUEUE',status='DDAY_KNOWN_SOURCE_HARD_OR_REPRESENTATION_WINDOW')
            if command['start_seconds']>now:
                return dict(uid=uid,action='START',site=command['site'],start_seconds=command['start_seconds'],
                    nominal_end_seconds=command['start_seconds']+max(self.requests[uid].q50,1e-9),
                    additional_start_delay_seconds=0,status='DDAY_KNOWN_FCFS_NOT_YET_RELEASED')
            return dict(uid=uid,action='START',site=command['site'],start_seconds=now,
                nominal_end_seconds=now+max(self.requests[uid].q50,1e-9),
                additional_start_delay_seconds=0,status='DDAY_OBSERVED_KNOWN_FCFS_EXECUTION',
                source_FCFS_release_seconds=command['start_seconds'],old_historical_command_executed=False)
        if command['start_seconds']<now:
            reason='PAST_START_NOT_OBSERVED_EXECUTED' if command['start_seconds']<self.policy.reference.begin else 'KNOWN_MISSED_FROZEN_COMMAND'
            self._event(uid,now,'KNOWN_COMMAND_EXECUTION_FAILED',reason=reason,
                plan_start_seconds=command['start_seconds'],command_retimed=False,unknown_selector_used=False)
            return dict(uid=uid,action='QUEUE',status=reason)
        return super()._known_decision(uid,now)

    def _policy_resource_guard(self,now,*,lookup_at=None,observed_use=None):
        self.policy.observe(now,self.ledger.physical(now) if observed_use is None else observed_use,self.metadata)
        return None,dict(observed_at_seconds=now,controller_contract=SITE_ONLY_CONTRACT,grid_safety_guaranteed=False)

    def admit(self,now):
        if digest(self.known_schedule)!=self.frozen_known_sha:
            raise ValueError('SITE_ONLY_IMMUTABLE_KNOWN_COMMAND_SHA_DRIFT')
        if (self.qos.case_sha,self.qos.provider_sha,self.qos.stats.sha)!=self.provider_identity:
            raise ValueError('SITE_ONLY_SOURCE_QOS_IDENTITY_DRIFT')
        if now%900:return []
        self.policy.require_bindings(self.policy.bindings)
        self.policy.observe(now,self.ledger.physical(now),self.metadata)
        for _,uid in sorted(self.pending):
            if uid in self.known_schedule and self.known_schedule[uid]['start_seconds']<now:
                self.decisions[uid]=self._known_decision(uid,now)
            elif self.metadata[uid]['origin_unknown']:
                # No future Unknown command exists in this mode. A blocked
                # current choice is freshly selected at its next event.
                self.decisions.pop(uid,None)
        # Public current Known queue has priority in both variants.
        # Keep the original (submit,UID) tuple and request metadata intact.
        original=list(self.pending)
        self.pending=sorted(row for row in original if not self.metadata[row[1]]['origin_unknown'])
        # Retain the original B1 deterministic scan: source submit/UID order,
        # with later eligible Known permitted after an earlier blocked row.
        # This is explicitly a priority/backfill rule, not global strict FIFO.
        starts=super().admit(now);known_pending=list(self.pending)
        self.pending=[row for row in original if self.metadata[row[1]]['origin_unknown']]
        starts+=super().admit(now)
        self.pending+=known_pending
        import heapq
        heapq.heapify(self.pending)
        for uid in starts:
            if self.metadata[uid]['origin_unknown']:
                reference=self.budgets[uid].reference_start_seconds
                self.audit[uid].update(intentional_delay_seconds=0.,
                    unavoidable_queue_seconds=max(0.,now-reference),source_reference_start_seconds=reference,
                    site_only=True)
            elif self.known_schedule.get(uid,{}).get('execution_rule')=='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL':
                release=self.known_schedule[uid]['start_seconds']
                self.audit[uid].update(intentional_delay_seconds=0.,unavoidable_queue_seconds=max(0.,now-release),
                    source_FCFS_release_seconds=release,diagnostic_Known_baseline=True)
        return starts

    def migration(self,uid,now,physical_checkpoint):
        self._event(uid,now,'RUNNING_STAY',reason='SITE_ONLY_ALL_MIGRATION_DISABLED',frozen_commands_modified=False)
        return None

    def snapshot(self,now):
        snapshot=super().snapshot(now)
        snapshot['site_only_state']=dict(contract=SITE_ONLY_CONTRACT,frozen_known_sha=self.frozen_known_sha,
            source_qos_identity=self.provider_identity,intentional_delay_seconds=0,migration=False,
            runtime_repair=False,new_Known_optimization=False,
            boundary_completion_proof_sha=self.boundary_completion_proof_sha,
            boundary_cancellations=self.boundary_cancellations)
        return snapshot


class CurrentEventExecutionLedger(ExecutionLedger):
    """Release physical GPU on observed completion; dispatch remains on-grid."""
    def complete(self,uid,end,event_time):
        super().complete(uid,end,event_time)
        self.jobs[uid]['release_control_time']=float(event_time)


class CurrentEventReservationLedger(ContractReservationLedger):
    """Current GPU commitments, with original temporal WAN constraints.

    A future Known planning command is recorded separately and is never an
    admission veto. Physical RUNNING holds are refreshed by the original
    event driver; a public quantile does not release them.
    """
    def current_gpu_use(self,now,*,exclude=None):
        use=self.owner.ledger.physical(now)
        if exclude in self.owner.ledger.jobs:
            job=self.owner.ledger.jobs[exclude]
            if job['latest_observed_state']=='RUNNING':
                use[job['current_site']]-=job['gpu']
        # Unstarted commitments at this instant occupy GPU independently of
        # Running. UID union prevents counting a started reservation twice.
        for uid,row in self.reservations.items():
            if uid==exclude or row.get('status')=='RELEASED':continue
            state=self.owner.metadata.get(uid,{}).get('state')
            if state in {'RUNNING','COMPLETED'}:continue
            for s in union_job_segments(row.get('segments',[])):
                if s['resource'].startswith('gpu:') and s['begin']<=now<s['end']:
                    use[s['resource'][4:]]+=s['quantity']
        return use

    def _fits(self,segments,*,exclude=None,envelope=None,scope='physical'):
        now=self.owner.policy.current[0] if self.owner.policy.current is not None else self.owner.policy.reference.begin
        use=self.current_gpu_use(now,exclude=exclude)
        offered={s:0. for s in use}
        for s in union_job_segments(segments):
            if s['resource'].startswith('gpu:') and s['begin']<=now<s['end']:
                offered[s['resource'][4:]]+=s['quantity']
        for site,quantity in offered.items():
            if use[site]+quantity>self.capacities['gpu:'+site]+1e-9:return 'NO_CAPACITY'
        non_gpu=[s for s in segments if not s['resource'].startswith('gpu:')]
        return ReservationLedger._fits(self,non_gpu,exclude=exclude,envelope=None,scope=scope)

    def snapshot(self):
        result=super().snapshot()
        result.update(future_Known_GPU_admission_veto=False,
            Known_plan_role='IMMUTABLE_PLANNING_COMMAND_NOT_CURRENT_PHYSICAL_OCCUPANCY',
            current_committed_GPU_separate_from_Running=True)
        return result


class CurrentEventSensitivityPolicy(SiteOnlySensitivityPolicy):
    """Active current-only Unknown selection and actual Known conflict repair."""
    frozen_schema=CURRENT_EVENT_CONTRACT
    controller_contract=CURRENT_EVENT_CONTRACT
    execution_mode='CURRENT_UNKNOWN_SIGNED_ALLOCATION_PENDING_KNOWN_CORRECTIVE'

    def __init__(self,*args,corrective_authority=None,runtime_repair=False,runtime_fixture_gate=None,**kwargs):
        super().__init__(*args,**kwargs)
        gate=deepcopy(runtime_fixture_gate)
        if runtime_repair and (not gate or gate.get('status')!='PASS'
                or gate.get('controller_contract')!=CURRENT_EVENT_CONTRACT
                or gate.get('basic_allocation_and_corrective_fixture_PASS') is not True):
            raise ValueError('RUNTIME_CONTROL_REQUIRES_VALIDATED_BASIC_FIXTURE')
        self.runtime_repair=bool(runtime_repair)
        self.spec.update(contract=CURRENT_EVENT_CONTRACT,active_scope='CURRENT_UNKNOWN_PENDING_KNOWN_CORRECTIVE',
            future_Known_speculative_GPU_veto=False,Unknown_runtime_upper_bound_required=False,
            earliest_start_authority='SOURCE_RELEASE_HARD_EARLIEST_REPRESENTATION_CURRENT_PHYSICAL',
            QoS_FCFS_reference_is_hard_earliest=False,
            corrective_authority=deepcopy(corrective_authority),corrective_authority_sha=digest(corrective_authority),
            runtime_repair=self.runtime_repair,runtime_fixture_gate=gate,runtime_fixture_gate_sha=digest(gate),
            absolute_SLA_guarantee=False,checkpoint_migration='HOLD',intentional_time_shift='HOLD')
        self.sha=digest(self.spec)

    @classmethod
    def load(cls,path,*,bindings):
        self=SignedSensitivityPolicy.load.__func__(cls,path,bindings=bindings)
        if (self.spec.get('active_scope')!='CURRENT_UNKNOWN_PENDING_KNOWN_CORRECTIVE'
                or self.spec.get('future_Known_speculative_GPU_veto') is not False
                or digest(self.spec.get('corrective_authority'))!=self.spec['corrective_authority_sha']
                or digest(self.spec.get('runtime_fixture_gate'))!=self.spec['runtime_fixture_gate_sha']):
            raise ValueError('CURRENT_EVENT_POLICY_AUTHORITY_DRIFT')
        self.current_candidates=[];self.known_current_guards=[]
        return self

    def _record(self,m,now,decision,began,count,rejected):
        result=SignedSensitivityPolicy._record(self,m,now,decision,began,count,rejected)
        result.update(execution_mode=self.execution_mode,controller_contract=CURRENT_EVENT_CONTRACT,
            intentional_delay_seconds=0,additional_start_delay_seconds=0,time_shift=False,
            runtime_repair=self.runtime_repair,migration=False,future_Known_speculative_GPU_veto=False,
            absolute_SLA_guarantee=False)
        bridge=getattr(self,'_resource_bridge',None)
        if bridge is not None:
            slot=int((now-bridge.begin)//900)
            if 0<=slot<96:
                result['planning_resource_advisory']=dict(
                    saved_Known_GPU_by_site=dict(zip(bridge.sites,bridge.matrices['known_site_GPU'][slot].tolist())),
                    saved_Unknown_Q50_GPU_by_site=dict(zip(bridge.sites,bridge.matrices['nominal_site_GPU'][slot].tolist())),
                    saved_achieved_CC4_reserve_by_site=dict(zip(bridge.sites,bridge.matrices['achieved_CC4_reserve_site_GPU'][slot].tolist())),
                    saved_achieved_runtime_reserve_by_site=dict(zip(bridge.sites,bridge.matrices['achieved_runtime_reserve_site_GPU'][slot].tolist())),
                    remaining_CC4_Q50_GPUh=sum(bridge.book.row(h,now)['remaining_CC4_Q50_GPUh'] for h in range(24)),
                    role='SOFT_PLANNING_CONTEXT_NOT_PHYSICAL_OCCUPANCY_OR_TARGET_POWER',
                    all_line_phase_current_max_loading_remains_primary_objective=True)
        self.last_selection[m['uid']]=deepcopy(result);self.audit[-1]['decision']=deepcopy(result)
        return result

    def _admission_hold(self,site,now,end,gpu):
        return [dict(resource='gpu:'+site,begin=now,end=math.floor(now/900)*900+900,quantity=gpu)],None

    def _earliest_event(self,metadata,receipt):
        # A FCFS/QoS comparison reference is not a source release authority.
        # Current feasible admission may precede it, on a legal source tick.
        return max([metadata['submit_seconds']]+[float(metadata[k]) for k in
            ('release_seconds','hard_earliest_start_seconds') if metadata.get(k) is not None])

    def _admission_conflict(self,reservations,held,uid):
        if not isinstance(reservations,CurrentEventReservationLedger):
            raise ValueError('CURRENT_EVENT_RESOURCE_LEDGER_REQUIRED')
        reason=reservations.feasible(held,exclude=uid)
        if reason is None and getattr(self,'_backfill_active',False):
            site=held[0]['resource'][4:]
            ok,reason=safe_backfill(self.metadata[uid],now=self.current[0],site=site,
                reservations=reservations,uid=uid,evidence_scope=self.evidence_scope)
            reservations.owner.backfill_audit.append(dict(uid=uid,time_seconds=self.current[0],site=site,
                feasible=ok,reason=reason,guaranteed_completion_claim=False,source_executable_event_required=True))
            return None if ok else reason
        return reason

    def current_guard(self,metadata,segments,now,observed):
        if hasattr(self,'_current_resource_ledger'):
            observed=self._current_resource_ledger.current_gpu_use(now,exclude=metadata['uid'])
        return super().current_guard(metadata,segments,now,observed)

    def corrective_allowed(self,metadata):
        if metadata.get('state')!='PENDING' or metadata.get('origin_unknown') is not False:return False
        if metadata.get('can_prestart_place') is True:return True
        authority=self.spec.get('corrective_authority')
        if authority is None:return False
        if (digest(authority)!=self.spec['corrective_authority_sha']
                or authority.get('schema')!='RESEARCH_PENDING_KNOWN_CORRECTIVE_AUTHORITY_V1'
                or authority.get('case_sha')!=self.bindings['case_sha']
                or authority.get('science_sha')!=self.bindings['science_sha']
                or authority.get('source_customer_permission_claim') is not False):
            raise ValueError('CURRENT_KNOWN_CORRECTIVE_RESEARCH_AUTHORITY_DRIFT')
        return metadata['uid'] in authority.get('authorized_UIDs',[])


class CurrentEventJobEventController(SiteOnlyJobEventController):
    """Preserve Planning commands; repair only observed PENDING GPU conflict."""
    def __init__(self,*args,resource_bridge=None,actual_identity=None,**kwargs):
        if not isinstance(kwargs.get('frozen_policy'),CurrentEventSensitivityPolicy):
            raise ValueError('EXPLICIT_CURRENT_EVENT_CONTROLLER_REQUIRED')
        super().__init__(*args,**kwargs)
        self.ledger=CurrentEventExecutionLedger(self.ledger.capacities)
        self.reservations=CurrentEventReservationLedger(self,capacities=self.ledger.capacities,
            wan_capacities=kwargs.get('wan_capacities'))
        for uid in self.boundary_completed_UIDs:self.reservations.known_plans.pop(uid,None)
        self.policy._current_resource_ledger=self.reservations
        if self.policy.evidence_scope.startswith('REAL') and resource_bridge is None:
            raise ValueError('REAL_CURRENT_EVENT_SAME_CASE_RESOURCE_BRIDGE_REQUIRED')
        if resource_bridge is not None:
            planned_identity=self.policy.spec['source_identity'].get('planning_identity')
            if self.policy.evidence_scope.startswith('REAL') and (planned_identity is None or any(
                    resource_bridge.identity[k]!=planned_identity.get(k) for k in resource_bridge.identity)):
                raise ValueError('RESOURCE_BRIDGE_FROZEN_PLANNING_STAGE_IDENTITY_REQUIRED')
            if actual_identity is None or any(resource_bridge.identity[k]!=actual_identity.get(k)
                    for k in resource_bridge.identity):
                raise ValueError('RESOURCE_BRIDGE_ACTUAL_STAGE_IDENTITY_REQUIRED')
            for key in ('science_sha','initial_state_sha','time_axis_sha','cc4_sha','runtime_sha'):
                if resource_bridge.identity[key]!=self.policy.bindings[key]:
                    raise ValueError('RESOURCE_BRIDGE_CURRENT_POLICY_IDENTITY_DRIFT:'+key)
            if (resource_bridge.source['aidc_anchor']!=self.policy.bindings['aidc_anchor']
                    or resource_bridge.begin!=self.policy.reference.begin
                    or set(resource_bridge.sites)!=set(self.ledger.capacities)):
                raise ValueError('RESOURCE_BRIDGE_CURRENT_CLOCK_SITE_ANCHOR_DRIFT')
            if any(self.ledger.capacities[s]!=resource_bridge.capacities[s] for s in resource_bridge.sites):
                raise ValueError('RESOURCE_BRIDGE_CURRENT_PHYSICAL_CAPACITY_DRIFT')
        self.resource_bridge=resource_bridge
        self.policy._resource_bridge=resource_bridge
        self.planning_commands=deepcopy(self.known_schedule)
        self.corrective_commands={};self.corrective_audit=[];self.known_actual_audit=[]
        self.conflict_attempts={};self.runtime_audit=[];self.backfill_audit=[]
        self._overrun_seen=set();self.released_since_control=[]
        if any(str(c.get('execution_rule','')).startswith('DETERMINISTIC_KNOWN')
                for c in self.known_schedule.values()):
            raise ValueError('DIAGNOSTIC_FCFS_MUST_NOT_BECOME_ACTIVE_KNOWN_PLAN')

    def submit(self,request,now):
        super().submit(request,now)
        # Unknown arrives once. The bridge owns its independent depletion
        # book, while the driver's ForecastBook remains an audit of the same
        # observation; neither book is a physical reservation.
        if self.resource_bridge is not None:
            self.resource_bridge.observe(self.metadata[request.uid],now)

    def _policy_resource_guard(self,now,*,lookup_at=None,observed_use=None):
        self.policy.observe(now,self.reservations.current_gpu_use(now),self.metadata)
        return None,dict(observed_at_seconds=now,controller_contract=CURRENT_EVENT_CONTRACT,
            grid_safety_guaranteed=False,current_committed_GPU_checked=True)

    def _preparation(self,uid,site,now):
        data=self.metadata[uid].get('preplacement_data') or {}
        sha=data.get('source_sha');observed=data.get('observed_at_seconds',math.inf)
        if (not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha)
                or not math.isfinite(float(observed)) or observed>now):
            return None,'SOURCE_DATA_PREPARATION_AUTHORITY_MISSING'
        if site not in data.get('authorized_destinations',[]):return None,'DATA_RESIDENCY_DESTINATION_NOT_AUTHORIZED'
        ready=data.get('ready_at_seconds',{}).get(site)
        if ready is not None and math.isfinite(float(ready)) and ready<=now:
            return dict(ready_at_seconds=now,transfer_seconds=0.,preparation_seconds=0.,wan_segments=[],
                source_sha=data['source_sha'],data_already_ready=True),None
        path=data.get('wan_path_by_destination',{}).get(site)
        # Original WAN capacity and migration authority are bytes/second.
        # Units are explicit; a GB/s quantity must never be charged as bytes/s.
        bandwidth=data.get('bandwidth_bytes_per_second');payload=data.get('payload_bytes');prepare=data.get('preparation_seconds')
        if (not path or any(v is None or not math.isfinite(float(v)) or v<0 for v in (payload,prepare))
                or bandwidth is None or not math.isfinite(float(bandwidth)) or bandwidth<=0):
            return None,'SOURCE_TRANSFER_TIME_WAN_AUTHORITY_MISSING'
        if payload<=0:return None,'SOURCE_TRANSFER_POSITIVE_DURATION_REQUIRED'
        duration=max(900.,math.ceil(float(payload)/float(bandwidth)/900)*900.)
        if 'wan:'+path not in self.reservations.capacities:return None,'NO_RESOURCE_AUTHORITY'
        segments=[dict(resource='wan:'+path,begin=now,end=now+duration,quantity=bandwidth),
            dict(resource='active:WAN',begin=now,end=now+duration,quantity=1)]
        reason=self.reservations.feasible(segments,exclude=uid)
        if reason:return None,reason
        return dict(ready_at_seconds=math.ceil((now+duration+float(prepare))/900)*900,
            transfer_seconds=duration,preparation_seconds=float(prepare),wan_segments=segments,
            source_sha=data['source_sha'],data_already_ready=False,wan_quantity_units='bytes_per_second'),None

    def _hard_window(self,uid,now):
        m=self.metadata[uid]
        if now not in set(m.get('representation_starts_seconds') or []):return 'SOURCE_REPRESENTATION_WINDOW'
        if now<max(m['submit_seconds'],m.get('release_seconds') or -math.inf,
                m.get('hard_earliest_start_seconds') or -math.inf):return 'SOURCE_RELEASE_WINDOW'
        if m.get('hard_latest_start_seconds') is not None and now>m['hard_latest_start_seconds']:return 'SOURCE_LATEST_START_WINDOW'
        if m.get('completion_deadline_seconds') is not None and now+self.requests[uid].q50>m['completion_deadline_seconds']:return 'SOURCE_COMPLETION_DEADLINE_RISK'
        return None

    def _known_decision(self,uid,now):
        m=self.metadata[uid];command=self.planning_commands[uid];planned=float(command['start_seconds'])
        if planned<self.policy.reference.begin:
            return dict(uid=uid,action='QUEUE',status='PAST_PLANNING_START_REQUIRES_SAME_CASE_BOUNDARY_REPLAY')
        if m['state']!='PENDING':return dict(uid=uid,action='QUEUE',status='PENDING_KNOWN_REQUIRED')
        receipt=self.budgets[uid]
        if planned not in receipt.allowed_starts_seconds:
            return dict(uid=uid,action='QUEUE',status='PLAN_OUTSIDE_AUTHORIZED_WINDOW')
        if now<planned:
            return dict(uid=uid,action='START',site=command['site'],start_seconds=planned,
                nominal_end_seconds=planned+max(self.requests[uid].q50,1e-9),additional_start_delay_seconds=0)
        reason=self._hard_window(uid,now)
        if reason:
            self._event(uid,now,'KNOWN_CORRECTIVE_QOS_RISK',reason=reason,Planning_command_changed=False)
            return dict(uid=uid,action='QUEUE',status=reason)
        use=self.reservations.current_gpu_use(now,exclude=uid);site=command['site'];gpu=m['gpu']
        if site not in self.requests[uid].compatible:return dict(uid=uid,action='QUEUE',status='PLAN_SITE_INCOMPATIBLE')
        correction=self.corrective_commands.get(uid)
        if correction is not None:
            if now<correction['ready_at_seconds']:
                return dict(uid=uid,action='QUEUE',status='KNOWN_DATA_TRANSFER_PREPARATION_IN_PROGRESS')
            site=correction['actual_site']
            # Recheck actual capacity and all current electrical rows after
            # real preparation. No GPU was created at transfer initiation.
            if use[site]+gpu>self.ledger.capacities[site]:
                return dict(uid=uid,action='QUEUE',status='CORRECTED_SITE_ACTUAL_GPU_CONFLICT')
        elif use[site]+gpu>self.ledger.capacities[site]:
            self.conflict_attempts.setdefault(uid,dict(first_conflict_seconds=now,planned_site=site))
            return self._corrective_decision(uid,now,use)
        elif now>planned and uid not in self.conflict_attempts:
            return dict(uid=uid,action='QUEUE',status='KNOWN_MISSED_UNOBSERVED_PLANNING_START')
        if site!=self.requests[uid].source_site and not self.policy.corrective_allowed(m):
            return dict(uid=uid,action='QUEUE',status='PLAN_SITE_NO_SOURCE_AUTHORITY')
        return dict(uid=uid,action='PREPLACE' if correction else 'START',site=site,start_seconds=now,
            nominal_end_seconds=now+max(self.requests[uid].q50,1e-9),plan_start_seconds=planned,
            additional_start_delay_seconds=max(0.,planned-receipt.reference_start_seconds)+(
                0 if correction is None else correction['qos_preparation_budget_used_seconds']),
            unavoidable_resource_wait_seconds=max(0.,now-planned-(0 if correction is None else
                correction['qos_preparation_budget_used_seconds'])),
            status='ACTUAL_CORRECTIVE_COMMAND' if correction else 'PLANNING_COMMAND')

    def _corrective_decision(self,uid,now,use):
        m=self.metadata[uid];command=self.planning_commands[uid];site=command['site']
        original=np.asarray([use[s] for s in self.policy.packet.sites],float)
        original[self.policy.packet.sites.index(site)]+=m['gpu']
        slot=int((now-self.policy.reference.begin)//900)
        original_peak,_=self.policy.packet._at_slot(slot,self.policy._grid_delta(slot,original,now))
        rows=[];rejected=[]
        if self.policy.corrective_allowed(m):
            for target in sorted(set(self.requests[uid].compatible)-{site}):
                reason=None
                if m['gpu']>max(self.policy.packet.rack_compatibility[target]):reason='RACK_GANG_INCOMPATIBLE'
                if use[target]+m['gpu']>self.ledger.capacities[target]:reason='CURRENT_GPU_CAPACITY'
                prep=None
                if reason is None:prep,reason=self._preparation(uid,target,now)
                used=0. if prep is None else prep['ready_at_seconds']-now
                qos_total=max(0.,command['start_seconds']-self.budgets[uid].reference_start_seconds)+used+m.get('cumulative_migration_interruption_seconds',0.)
                if reason is None and qos_total>self.budgets[uid].budget_seconds+1e-9:reason='SHARED_QOS_PREPARATION_BUDGET_EXCEEDED'
                if reason is None:reason=self._hard_window(uid,prep['ready_at_seconds'])
                candidate=np.asarray([use[s] for s in self.policy.packet.sites],float)
                candidate[self.policy.packet.sites.index(target)]+=m['gpu']
                peak,bad=self.policy.packet._at_slot(slot,self.policy._grid_delta(slot,candidate,now))
                if reason is None and bad:reason='CURRENT_OBSERVED_'+bad[0]['reason']
                if reason:rejected.append(dict(site=target,reason=reason));continue
                rows.append((peak,target,prep,used))
        else:rejected.append(dict(site=None,reason='PENDING_KNOWN_PREPLACEMENT_AUTHORITY_MISSING'))
        for peak,target,prep,used in sorted(rows,key=lambda r:(r[0],r[1])):
            if prep['wan_segments']:
                ok,reason=self.reservations.reserve(uid,prep['wan_segments'],replace=True)
                if not ok:rejected.append(dict(site=target,reason=reason));continue
            correction=dict(uid=uid,command_type='ACTUAL_CORRECTIVE_COMMAND',original_planned_site=site,
                original_planned_start_seconds=command['start_seconds'],actual_site=target,actual_start_seconds=None,
                trigger_seconds=now,reason='ACTUAL_RUNNING_GPU_CAPACITY_CONFLICT',GPU_capacity_conflict=True,
                original_grid_loading=original_peak,corrected_grid_loading=peak,all_line_phase_rows=True,
                qos_preparation_budget_used_seconds=used,shared_qos_budget_seconds=self.budgets[uid].budget_seconds,
                planning_command_sha=digest(command),planning_command_modified=False,
                source_customer_permission_claim=m.get('can_prestart_place') is True,**prep)
            self.corrective_commands[uid]=correction;self.corrective_audit.append(deepcopy(correction))
            self._event(uid,now,'KNOWN_CORRECTIVE_PREPLACEMENT',actual_site=target,
                ready_at_seconds=prep['ready_at_seconds'],Planning_command_changed=False)
            if prep['ready_at_seconds']>now:
                return dict(uid=uid,action='QUEUE',status='KNOWN_DATA_TRANSFER_PREPARATION_IN_PROGRESS')
            return self._known_decision(uid,now)
        self.corrective_audit.append(dict(uid=uid,trigger_seconds=now,original_planned_site=site,
            original_planned_start_seconds=command['start_seconds'],status='QUEUE',reason='NO_SAFE_CORRECTIVE_SITE',
            rejected_candidates=rejected,GPU_capacity_conflict=True,Running_jobs_preserved=True,
            planning_command_modified=False,QoS_risk_seconds=max(0.,now-command['start_seconds'])))
        return dict(uid=uid,action='QUEUE',status='NO_SAFE_CORRECTIVE_SITE',rejected_candidates=rejected)

    def admit(self,now):
        if now%900:return []
        if digest(self.known_schedule)!=self.frozen_known_sha:raise ValueError('CURRENT_EVENT_PLANNING_COMMAND_DRIFT')
        self.policy.require_bindings(self.policy.bindings)
        for uid,m in self.metadata.items():
            if (self.policy.runtime_repair and m['state']=='RUNNING' and m.get('accumulated_compute_seconds',0)>m['t50_seconds']
                    and uid not in self._overrun_seen):
                self._overrun_seen.add(uid);self.runtime_audit.append(dict(uid=uid,time_seconds=now,
                    event='OVERRUN_RUNNING_HOLD',elapsed_seconds=m['accumulated_compute_seconds'],
                    Q50_seconds=m['t50_seconds'],Running_gpu_preserved=True,actual_completion_read=False))
        original=list(self.pending);remaining=[];starts=[]
        order=sorted(original,key=lambda row:(self.metadata[row[1]]['origin_unknown'],row[0],row[1]))
        for row in order:
            uid=row[1];self.pending=[row];self.decisions.pop(uid,None)
            self.policy.observe(now,self.reservations.current_gpu_use(now,exclude=uid),self.metadata)
            if not self.metadata[uid]['origin_unknown'] and uid not in self.planning_commands:
                self.decisions[uid]=dict(uid=uid,action='QUEUE',status='SAME_CASE_KNOWN_PLANNING_COMMAND_MISSING')
            # Check each actual candidate destination, after current capacity
            # and source release, rather than assuming the source is selected.
            self.policy._backfill_active=bool(self.policy.runtime_repair and self.released_since_control
                and self.metadata[uid]['origin_unknown'])
            one=JobEventController.admit(self,now);starts.extend(one);remaining.extend(self.pending)
            if one:
                if uid in self.corrective_commands:
                    correction=self.corrective_commands[uid]
                    slot=int((now-self.policy.reference.begin)//900)
                    physical=np.asarray([self.ledger.physical(now)[s] for s in self.policy.packet.sites],float)
                    peak,_=self.policy.packet._at_slot(slot,self.policy._grid_delta(slot,physical,now))
                    correction.update(actual_start_seconds=now,grid_loading_after_actual_start=peak)
                    for entry in self.corrective_audit:
                        if entry.get('uid')==uid and entry.get('command_type')=='ACTUAL_CORRECTIVE_COMMAND':
                            entry.update(actual_start_seconds=now,grid_loading_after_actual_start=peak)
                if uid in self.planning_commands:
                    self.known_actual_audit.append(dict(uid=uid,original_command=deepcopy(self.planning_commands[uid]),
                        actual_site=self.audit[uid]['site'],actual_start_seconds=now,
                        actual_start_delay_seconds=now-self.planning_commands[uid]['start_seconds'],
                        start_delay_QoS_risk_seconds=max(0.,now-self.budgets[uid].latest_start_seconds),
                        corrective_command=deepcopy(self.corrective_commands.get(uid)),planning_command_modified=False))
        self.pending=remaining
        self.policy._backfill_active=False
        import heapq
        heapq.heapify(self.pending)
        self.released_since_control=[]
        if self.resource_bridge is not None:self.resource_bridge.snapshot(now,self.metadata,self.reservations)
        return starts

    def completion(self,uid,now):
        release=super().completion(uid,now);m=self.metadata[uid]
        self.reservations.release(uid,now)
        if uid in self.corrective_commands:
            self.corrective_commands[uid].update(completion_result='COMPLETED',observed_completion_seconds=now)
            for entry in self.corrective_audit:
                if entry.get('uid')==uid and entry.get('command_type')=='ACTUAL_CORRECTIVE_COMMAND':
                    entry.update(completion_result='COMPLETED',observed_completion_seconds=now)
        if self.policy.runtime_repair:
            elapsed=m['accumulated_compute_seconds'];self.runtime_audit.append(dict(uid=uid,time_seconds=now,
                event='RUNTIME_SHORT_COMPLETION' if elapsed<m['t50_seconds'] else 'OBSERVED_COMPLETION',
                elapsed_seconds=elapsed,Q50_seconds=m['t50_seconds'],release_control_seconds=release,
                physical_GPU_released_at_observed_completion=True,dispatch_legal_source_grid_preserved=True))
            self.released_since_control.append(uid)
        return release

    def snapshot(self,now):
        result=super().snapshot(now)
        for uid,correction in self.corrective_commands.items():
            correction['completion_result']='COMPLETED' if self.metadata[uid]['state']=='COMPLETED' else 'CARRY_'+self.metadata[uid]['state']
            for entry in self.corrective_audit:
                if entry.get('uid')==uid and entry.get('command_type')=='ACTUAL_CORRECTIVE_COMMAND':
                    entry['completion_result']=correction['completion_result']
        result['current_event_state']=dict(contract=CURRENT_EVENT_CONTRACT,status='FIXTURE_VALIDATED_ACTUAL_NOT_CERTIFIED',
            planning_commands=deepcopy(self.planning_commands),planning_commands_sha=self.frozen_known_sha,
            actual_corrective_commands=deepcopy(self.corrective_commands),corrective_audit=deepcopy(self.corrective_audit),
            Known_actual_audit=deepcopy(self.known_actual_audit),conflict_attempts=deepcopy(self.conflict_attempts),
            runtime_events=deepcopy(self.runtime_audit),backfill_results=deepcopy(self.backfill_audit),
            future_Known_speculative_GPU_veto=False,actual_global_MILP_calls=0,absolute_SLA_guarantee=False,
            checkpoint_migration_status='NOT_RUN',intentional_time_shift_status='NOT_RUN',
            resource_bridge=None if self.resource_bridge is None else self.resource_bridge.export())
        return result

    def restore(self,snapshot):
        raise ValueError('CURRENT_EVENT_CARRYOUT_RESTORE_NOT_CERTIFIED')


def run_current_event_actual(arguments,*,frozen_policy,resource_bridge,expected_bindings,handoff_gate):
    """Execute only after the supervisor certifies the same-case handoff.

    C0/C1 may produce different Actual Known corrective commands. Their
    immutable Planning commands and exogenous inputs must be identical.
    """
    if not isinstance(frozen_policy,CurrentEventSensitivityPolicy):
        raise ValueError('CURRENT_EVENT_FROZEN_POLICY_REQUIRED')
    if not handoff_gate or handoff_gate.get('status')!='PASS':
        raise ValueError('SAME_CASE_PLANNING_ACTUAL_HANDOFF_NOT_CERTIFIED')
    frozen_policy.require_bindings(expected_bindings)
    if resource_bridge is None:
        raise ValueError('SAVED_PLANNING_KNOWN_CC4_RESOURCE_BRIDGE_REQUIRED')
    if (handoff_gate.get('planning_commands_sha')!=digest(frozen_policy.reference.commands)
            or any(handoff_gate.get('identity',{}).get(k)!=resource_bridge.identity[k]
                for k in resource_bridge.identity)):
        raise ValueError('CURRENT_EVENT_HANDOFF_COMMAND_OR_IDENTITY_DRIFT')
    for key in ('science_sha','initial_state_sha','time_axis_sha','cc4_sha','runtime_sha'):
        if resource_bridge.identity[key]!=expected_bindings[key]:
            raise ValueError('RESOURCE_BRIDGE_ACTIVE_POLICY_IDENTITY_DRIFT:'+key)
    if resource_bridge.source['aidc_anchor']!=expected_bindings['aidc_anchor']:
        raise ValueError('RESOURCE_BRIDGE_ACTIVE_AIDC_ANCHOR_DRIFT')
    if arguments.get('carryout') is not None:
        raise ValueError('CURRENT_EVENT_CARRYOUT_RESTORE_NOT_CERTIFIED')
    if digest(arguments.get('known_schedule',frozen_policy.reference.commands))!=digest(frozen_policy.reference.commands):
        raise ValueError('CURRENT_EVENT_ORIGINAL_PLANNING_COMMAND_SHA_DRIFT')
    args=deepcopy(arguments)
    arm=args.get('arm','B1')
    if arm not in {'B1','B3'}:raise ValueError('CURRENT_EVENT_B1_OR_B3_EXPLICIT_ARM_REQUIRED')
    args.update(arm=arm,frozen_policy=frozen_policy,known_schedule=frozen_policy.reference.commands,
        expected_bindings=expected_bindings)
    _bind_driver_current_c1(frozen_policy,args)
    def controller(*a,**kw):
        return CurrentEventJobEventController(*a,resource_bridge=resource_bridge,
            actual_identity=handoff_gate['identity'],**kw)
    result=run_actual(**args,controller_class=controller)
    result['planning_actual_resource_bridge']=resource_bridge.export()
    result['receipt'].update(controller_contract=CURRENT_EVENT_CONTRACT,
        same_case_handoff_status=handoff_gate['status'],future_Known_speculative_GPU_veto=False,
        immutable_Known_planning_commands=True,Fresh_AC_status='NOT_RUN',May_performance_status='NOT_CERTIFIED')
    return result


def safe_backfill(metadata, *, now, site, reservations, uid, evidence_scope='REAL_DIAGNOSTIC'):
    """Q50/Q90 cannot prove completion before the next committed reservation."""
    peers = []
    for other, row in reservations.reservations.items():
        if other != uid and row.get('status') != 'RELEASED':
            peers.extend(row.get('segments', []))
    for other, rows in getattr(reservations, 'known_plans', {}).items():
        if other != uid:
            peers.extend(rows)
    starts = [s['begin'] for s in peers if s['resource'] == 'gpu:'+site and s['begin'] > now]
    next_booking = min(starts, default=None)
    if next_booking is None:
        return True, 'NO_FUTURE_COMMITTED_BOOKING'
    # The current real Runtime Provider has no validated finite deterministic
    # completion-bound registry. Arbitrary request metadata is not a provider
    # certificate; positive finite-bound witnesses remain named fixtures.
    if not evidence_scope.startswith('NAMED_'):
        return False, 'VALIDATED_NONPREEMPTIVE_RUNTIME_BOUND_PROVIDER_NOT_AVAILABLE'
    upper = metadata.get('source_runtime_upper_bound_seconds')
    authority = metadata.get('runtime_upper_bound_authority', {})
    if upper is None or not authority.get('source_sha') or authority.get('observed_at_seconds', math.inf) > now:
        return False, 'NO_SOURCE_CERTIFIED_RUNTIME_UPPER_BOUND'
    if not math.isfinite(float(upper)) or upper <= 0 or now+upper > next_booking:
        return False, 'UPPER_BOUND_CROSSES_COMMITTED_RESERVATION'
    segments = [dict(resource='gpu:'+site, begin=now, end=now+upper, quantity=metadata['gpu'])]
    reason = reservations.feasible(segments, exclude=uid)
    return reason is None, reason or 'SOURCE_UPPER_BOUND_FITS_COMMITTED_RESERVATION'


class SensitivityRuntimeController(JobEventController):
    _overlay = ExperimentalJobEventController._overlay

    def __init__(self, *args, **kwargs):
        policy = kwargs.get('frozen_policy')
        boundary_proof = kwargs.pop('boundary_completion_proof',None)
        boundary_begin = kwargs.pop('boundary_begin_seconds',None)
        if not isinstance(policy, SignedSensitivityPolicy) or policy.controller_contract != CONTRACT:
            raise ValueError('EXPLICIT_SIGNED_RUNTIME_CONTROLLER_REQUIRED')
        wan = dict(kwargs.get('wan_capacities') or {})
        for key, value in (policy.migration_authority or {}).get('wan_capacities', {}).items():
            if key in wan and wan[key] != value:
                raise ValueError('SOURCE_WAN_CAPACITY_DRIFT')
            wan[key] = value
        kwargs['wan_capacities'] = wan
        super().__init__(*args, **kwargs)
        if digest(self.known_schedule) != digest(policy.reference.commands):
            raise ValueError('SIGNED_FROZEN_KNOWN_COMMAND_SHA_DRIFT')
        self.reservations = ContractReservationLedger(self, capacities=self.ledger.capacities, wan_capacities=wan)
        self.frozen_known_sha = digest(self.known_schedule)
        self.qos.require_frozen_policy(policy.bindings['qos_sha'])
        self.repair_audit, self.backfill_audit, self.runtime_audit = [], [], []
        self.released_since_control = []
        self.known_start_attempts, self.known_resource_wait_eligible = {}, set()
        self.known_resource_wait_invalidated = {}
        self.boundary_completion_cancellations = []
        self.boundary_completed_UIDs = set()
        self.boundary_completion_proof_sha = None
        if boundary_proof is not None:
            if policy.evidence_scope.startswith('REAL') and not boundary_proof['evidence_scope'].startswith('REAL'):
                raise ValueError('REAL_BOUNDARY_COMPLETION_SOURCE_SCOPE_REQUIRED')
            require_boundary_completion_proof(boundary_proof,bindings=policy.bindings,
                begin_seconds=policy.reference.begin if boundary_begin is None else boundary_begin)
            self.boundary_completion_proof_sha = boundary_proof['proof_sha']
            self.boundary_completed_UIDs = {r['uid'] for r in boundary_proof['rows']}
            self.policy.boundary_completed_UIDs = set(self.boundary_completed_UIDs)
            for uid in sorted(self.boundary_completed_UIDs & set(self.reservations.known_plans)):
                cancelled = self.reservations.known_plans.pop(uid)
                record = dict(uid=uid,event='OBSERVED_BOUNDARY_COMPLETED_KNOWN_BOOKING_CANCELLED',
                    observed_at_seconds=boundary_proof['observed_at_seconds'],
                    source_proof_sha=boundary_proof['proof_sha'],cancelled_segments=cancelled,
                    frozen_known_schedule_sha=self.frozen_known_sha,frozen_commands_modified=False)
                self.boundary_completion_cancellations.append(record)
                self._event(uid,boundary_proof['observed_at_seconds'],record['event'],
                    source_proof_sha=boundary_proof['proof_sha'],frozen_known_schedule_sha=self.frozen_known_sha,
                    frozen_commands_modified=False)
        elif policy.evidence_scope == 'REAL_NEW_U60':
            raise ValueError('REAL_CURRENT_BOUNDARY_COMPLETION_PROOF_REQUIRED')

    def submit(self, request, now):
        if request.uid in self.boundary_completed_UIDs:
            raise ValueError('BOUNDARY_COMPLETED_KNOWN_UID_RESUBMITTED')
        if request.uid not in self.qos.contexts:
            self.qos.register_observed(request.uid, episode_id=request.metadata.get('experimental_participation_episode_id'),
                source_authority=request.metadata.get('source_qos_authority'))
        super().submit(request, now)
        self._overlay(request.uid, self.observed[request.uid].state)
        self.metadata[request.uid]['experimental_prediction_Q50_seconds'] = request.q50

    def _known_decision(self, uid, now):
        command = self.known_schedule[uid]
        if command['start_seconds'] < now:
            rule = self.qos.spec.get('known_execution_rule')
            attempt = self.known_start_attempts.get(uid)
            if (rule == 'ATTEMPT_AT_FROZEN_START_THEN_UNAVOIDABLE_RESOURCE_WAIT_SAME_SITE'
                    and uid in self.known_resource_wait_eligible and attempt is not None
                    and attempt['planned_start_seconds'] == command['start_seconds']
                    and attempt['site'] == command['site']
                    and attempt['known_schedule_sha'] == self.frozen_known_sha):
                receipt = self.budgets[uid]
                return dict(uid=uid, action=attempt['action'], site=command['site'],
                    start_seconds=now, nominal_end_seconds=now+max(self.requests[uid].q50,1e-9),
                    status='EXECUTE_FROZEN_KNOWN_AFTER_OBSERVED_RESOURCE_WAIT',
                    plan_start_seconds=command['start_seconds'],
                    additional_start_delay_seconds=max(0., command['start_seconds']-receipt.reference_start_seconds),
                    unavoidable_resource_wait_seconds=now-command['start_seconds'],
                    planned_attempt_receipt_sha=digest(attempt), frozen_command_retimed=False,
                    Known_allocator_used=False, budget_reissued=False)
            reason = ('PAST_START_NOT_OBSERVED_EXECUTED' if command['start_seconds'] < self.policy.reference.begin
                else 'KNOWN_MISSED_FROZEN_COMMAND')
            self._event(uid, now, 'KNOWN_COMMAND_EXECUTION_FAILED', reason=reason,
                plan_start_seconds=command['start_seconds'], unknown_selector_used=False, command_retimed=False)
            return dict(uid=uid, action='QUEUE', status=reason)
        return super()._known_decision(uid, now)

    def _policy_resource_guard(self, now, *, lookup_at=None, observed_use=None):
        self.policy.observe(now, self.ledger.physical(now) if observed_use is None else observed_use, self.metadata)
        return None, dict(observed_at_seconds=now, controller_contract=CONTRACT, grid_safety_guaranteed=False)

    def completion(self, uid, now):
        release = super().completion(uid, now)
        meta = self.metadata[uid]
        elapsed = meta.get('accumulated_compute_seconds', 0)
        self.runtime_audit.append(dict(uid=uid, time_seconds=now, event='OBSERVED_COMPLETION',
            elapsed_seconds=elapsed, total_Q50_seconds=meta['t50_seconds'],
            short=elapsed < meta['t50_seconds'], overrun=elapsed > meta['t50_seconds'],
            release_control_seconds=release, immediate_observed_completion=True,
            original_control_release_preserved=True))
        self.released_since_control.append(uid)
        return release

    def admit(self, now):
        self.qos.require_frozen_policy(self.policy.bindings['qos_sha'])
        if digest(self.known_schedule) != self.frozen_known_sha:
            raise ValueError('KNOWN_SCHEDULE_DRIFT')
        if now%900:
            return super().admit(now)
        self.policy.require_bindings(self.policy.bindings)
        use = self.ledger.physical(now)
        self.policy.observe(now, use, self.metadata)
        for _, uid in sorted(self.pending):
            if uid in self.known_schedule and self.known_schedule[uid]['start_seconds'] == now:
                decision = super()._known_decision(uid, now)
                if decision['action'] != 'QUEUE':
                    self.known_start_attempts[uid] = dict(uid=uid, planned_start_seconds=now,
                        observed_attempt_seconds=now, site=self.known_schedule[uid]['site'],
                        action=decision['action'], known_schedule_sha=self.frozen_known_sha,
                        receipt_sha=digest(self.budgets[uid].to_dict()),
                        validation='ORIGINAL_QOS_SITE_COMPATIBILITY_VALIDATED')
                    self._event(uid, now, 'KNOWN_FROZEN_START_ATTEMPT',
                        attempt_receipt_sha=digest(self.known_start_attempts[uid]))
            elif uid in self.known_schedule and self.known_schedule[uid]['start_seconds'] < now:
                # Cached commands blocked at their planned tick receive the
                # same exact-clock rule as first-time command dispatch.
                self.decisions[uid] = self._known_decision(uid, now)
        for uid, meta in self.metadata.items():
            if meta['state'] == 'RUNNING' and meta.get('accumulated_compute_seconds', 0) > meta['t50_seconds']:
                self.runtime_audit.append(dict(uid=uid, time_seconds=now, event='OVERRUN_RUNNING_HOLD',
                    gpu=meta['gpu'], site=meta['current_site'], running_gpu_protected=True,
                    conditional_remaining_Q90=None, conditional_provider_status='NOT_CERTIFIED'))
        if self.policy.runtime_repair:
            for _, uid in sorted(self.pending):
                meta = self.metadata[uid]
                decision = self.decisions.get(uid)
                if not decision or decision['action'] == 'QUEUE':
                    continue
                segments = decision.get('segments', [dict(resource='gpu:'+decision['site'],
                    begin=decision['start_seconds'], end=decision['nominal_end_seconds'], quantity=meta['gpu'])])
                reason = self.reservations.feasible(segments, exclude=uid)
                if reason is None:
                    reason = self.policy.current_guard(meta, segments, now, use)
                if reason:
                    known = not meta['origin_unknown']
                    self.repair_audit.append(dict(uid=uid, time_seconds=now, reason=reason,
                        event='KNOWN_FROZEN_CONFLICT_NO_REPAIR_AUTHORITY' if known else 'UNKNOWN_RESERVATION_REPAIR',
                        running_gpu_protected=True, known_command_modified=False, budget_reissued=False))
                    if known:
                        continue
                    self.reservations.release(uid, now)
                    self.decisions[uid] = dict(uid=uid, action='QUEUE', status='RUNTIME_REPAIR_REQUIRED', reason=reason)
                elif self.released_since_control and meta['origin_unknown'] and decision['start_seconds'] > now:
                    ok, why = safe_backfill(meta, now=now, site=decision['site'], reservations=self.reservations,
                        uid=uid, evidence_scope=self.policy.evidence_scope)
                    if now not in self.budgets[uid].allowed_starts_seconds:
                        ok, why = False, 'ORIGINAL_QOS_START_WINDOW'
                    self.backfill_audit.append(dict(uid=uid, time_seconds=now, reason=why,
                        eligible=ok, selected=False, next_reservation_protected=True, budget_reissued=False))
                    if ok:
                        self.reservations.release(uid, now)
                        meta['runtime_backfill_evaluation_seconds'] = now
                        self.decisions[uid] = dict(uid=uid, action='QUEUE', status='SAFE_BACKFILL_REEVALUATION')
        event_begin = len(self.events)
        result = super().admit(now)
        for event in self.events[event_begin:]:
            uid = event.get('uid')
            if uid in self.known_start_attempts and uid not in result and event.get('event') == 'QUEUED':
                if event.get('reason') in {'PHYSICAL_CAPACITY_RUNNING_RETAINED', 'NO_CAPACITY'}:
                    if uid not in self.known_resource_wait_invalidated:
                        self.known_resource_wait_eligible.add(uid)
                        self._event(uid, now, 'KNOWN_OBSERVED_RESOURCE_WAIT',
                            original_planned_start_seconds=self.known_schedule[uid]['start_seconds'],
                            running_jobs_evicted=False, known_site_changed=False, intentional_budget_renewed=False)
                else:
                    self.known_resource_wait_eligible.discard(uid)
                    self.known_resource_wait_invalidated[uid] = dict(time_seconds=now, reason=event.get('reason'))
                    self._event(uid, now, 'KNOWN_RESOURCE_WAIT_PERMISSION_INVALIDATED',
                        reason=event.get('reason'), later_capacity_release_cannot_restore_permission=True)
        for uid in result:
            if uid in self.known_resource_wait_eligible:
                planned = self.known_schedule[uid]['start_seconds']
                wait = max(0., now-planned)
                self.audit[uid].update(unavoidable_queue_seconds=wait,
                    unavoidable_resource_wait_seconds=wait,
                    frozen_planned_start_seconds=planned,
                    frozen_command_execution_attempt_sha=digest(self.known_start_attempts[uid]),
                    known_execution_rule=self.qos.spec.get('known_execution_rule'))
                self._event(uid, now, 'KNOWN_FROZEN_COMMAND_EXECUTED_AFTER_RESOURCE_WAIT',
                    original_planned_start_seconds=planned, actual_start_seconds=now,
                    unavoidable_resource_wait_seconds=wait, site=self.known_schedule[uid]['site'],
                    known_command_modified=False, intentional_budget_renewed=False)
        for row in self.backfill_audit:
            if row['time_seconds'] == now and row['uid'] in result:
                row['selected'] = True
        self.released_since_control = []
        return result

    def migration(self, uid, now, physical_checkpoint):
        self._overlay(uid, 'RUNNING')
        return super().migration(uid, now, physical_checkpoint)

    def snapshot(self, now):
        result = super().snapshot(now)
        result['tracking_state'] = dict(contract=CONTRACT, target_sha=self.policy.reference.sha,
            Known_schedule_sha=self.frozen_known_sha, online_global_optimizer_calls=0,
            assignments_GPUh={u:a.tolist() for u,a in self.policy.assignments.items()})
        result['runtime_repair_state'] = dict(repair=self.repair_audit, backfill=self.backfill_audit,
            runtime=self.runtime_audit, conditional_provider_status='NOT_CERTIFIED')
        result['known_frozen_execution_state'] = dict(start_attempt_receipts=self.known_start_attempts,
            observed_resource_wait_UIDs=sorted(self.known_resource_wait_eligible),
            invalidated_resource_wait_permissions=self.known_resource_wait_invalidated,
            planning_execution_rule=self.qos.spec.get('known_execution_rule', 'STRICT_FROZEN_TICK'),
            historical_unobserved_past_commands_rescued=False)
        result['known_boundary_completion_state'] = dict(proof_sha=self.boundary_completion_proof_sha,
            observed_completed_UIDs=sorted(self.boundary_completed_UIDs),
            runtime_booking_cancellations=self.boundary_completion_cancellations,
            frozen_known_schedule_sha=self.frozen_known_sha,frozen_commands_modified=False)
        return result

    def restore(self, snapshot):
        raise ValueError('UNIFIED_CONTINUATION_REQUIRES_SEPARATE_VERIFIED_PACKAGE')


def build_dday_known_fcfs_baseline(arguments,packet):
    """Current observed Known reference, independent of Unknown choice/truth.

    This is a declared diagnostic queue rule, not a new A1 optimum or a
    relabeling of an old Planning command. Public Q50 forecasts firm release;
    actual Running is only released by the original observed completion path.
    """
    begin=arguments['begin'];end=begin+86400
    capacities=arguments['capacities'];old_ref=arguments.get('reference')
    if begin!=packet.begin_seconds or set(capacities)!=set(packet.sites):
        raise ValueError('DDAY_KNOWN_CURRENT_SOURCE_AXIS_REQUIRED')
    running=sorted(arguments.get('running',[]),key=lambda row:(row[0].submit,row[0].uid))
    pending=sorted((r for r in arguments.get('requests',[]) if r.submit<=begin
        and r.metadata.get('origin_unknown') is False),key=lambda r:(r.submit,r.uid))
    public=dict(begin_seconds=begin,capacities=capacities,
        running=[dict(uid=r.uid,gpu=r.gpu,q50=r.q50,submit=r.submit,site=s,start=t,
            elapsed_compute_seconds=r.metadata.get('elapsed_compute_seconds',begin-t),origin_unknown=r.metadata.get('origin_unknown')) for r,s,t in running],
        pending=[dict(uid=r.uid,gpu=r.gpu,q50=r.q50,submit=r.submit,compatible=list(r.compatible),
            source_site=r.source_site,metadata=r.metadata) for r in pending])
    _require_public_metadata(public)
    sha=digest(dict(rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL',public=public))
    scheduler=CausalReferenceScheduler(dict(capacities),reference_sha=sha)
    for request,site,start in running:
        scheduler.observe_running(request,site=site,start_seconds=start,event_seconds=begin,
            elapsed_compute_seconds=request.metadata.get('elapsed_compute_seconds',begin-start))
    commands={};rows=[]
    for request in pending:
        raw=request.metadata
        prior={} if old_ref is None else old_ref.assigned.get(request.uid,{})
        site=request.source_site or prior.get('reference_site')
        eligible=[s for s in request.compatible if s in packet.sites and request.gpu<=capacities[s]
            and request.gpu<=max(packet.rack_compatibility[s])]
        if site is None:
            site=next(iter(sorted(eligible)),None)
        if site not in eligible:
            raise ValueError('DDAY_KNOWN_SOURCE_SITE_GANG_RACK_INCOMPATIBLE:'+request.uid)
        earliest=max(begin,request.submit,raw.get('release_seconds') or -math.inf,
            raw.get('hard_earliest_start_seconds') or -math.inf)
        # Pin the source site; this rule never selects a Known alternative.
        shadow=replace(request,compatible=(site,),source_site=site,submit=max(request.submit,earliest))
        assignment=scheduler.submit(shadow,event_seconds=begin) if earliest<=begin else None
        if assignment is None:
            # Source releases beyond DD00 remain causal public descriptors.
            # Do not advance the scheduler clock past later still-observed
            # queue entries: use a submit floor with the same current event.
            shadow=replace(shadow,submit=request.submit)
            scheduler.last_pending_start_seconds=max(scheduler.last_pending_start_seconds,math.ceil(earliest/900)*900)
            assignment=scheduler.submit(shadow,event_seconds=begin)
        start=assignment['reference_start_seconds'];nominal_end=start+max(request.q50,1e-9)
        invalid=((raw.get('hard_latest_start_seconds') is not None and start>raw['hard_latest_start_seconds'])
            or (raw.get('completion_deadline_seconds') is not None and nominal_end>raw['completion_deadline_seconds'])
            or start not in set(raw.get('representation_starts_seconds',[])))
        command=dict(start_seconds=start,site=site,execution_rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL',
            source_observed_at_seconds=begin,source_FCFS_baseline_sha=sha,
            historical_Planning_command_used=False,nominal_service_seconds=request.q50,
            source_hard_window_valid=not invalid,protected_segments=[dict(resource='gpu:'+site,
                begin=start,end=assignment['nominal_release_seconds'],quantity=request.gpu)])
        commands[request.uid]=command
        rows.append(dict(uid=request.uid,site=site,release_seconds=start,
            nominal_end_seconds=nominal_end,source_hard_window_valid=not invalid,
            original_submit_seconds=request.submit,baseline_queue_wait_seconds=start-request.submit,
            customer_SLA_claim=False,source_PrivateRuntime_or_future_completion_used=False))
    return dict(schema='DIAGNOSTIC_KNOWN_BASELINE_DDAY_OBSERVED_FCFS_V1',baseline_sha=sha,
        commands=commands,rows=rows,public_input=public,Known_priority=True,source_site_pinned=True,
        public_Q50_only=True,actual_service_preserved_by_private_original_driver=True,
        new_A1_optimality_claim=False,old_Planning_commands_executed=False,Native_calls=0)


def run_site_only_prefix_canary(arguments, *, reference, packet, bindings, output,
        slots=16, source_identity=None, study_bindings=None, site_authority=None,
        boundary_completion_proof=None, diagnostic=True,evidence_scope=None):
    """Independent C0/C1 Actual prefixes, using the literal same Known input.

    Inputs are already materialized source descriptors. No native A model,
    policy time-shift, reservation repair or migration is invoked here.
    """
    if not 1<=slots<96 or output is None:
        raise ValueError('SITE_ONLY_EXPLICIT_PREFIX_1_TO95_AND_OUTPUT_REQUIRED')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    require_bindings(bindings,bindings);reference.require_immutable()
    if packet.bindings!=bindings or digest(arguments.get('known_schedule',reference.commands))!=digest(reference.commands):
        raise ValueError('SITE_ONLY_SAME_PACKET_AND_IMMUTABLE_KNOWN_REQUIRED')
    if arguments['qos_window_provider'].case_sha!=bindings['case_sha'] or arguments['qos_window_provider'].stats.sha!=bindings['qos_sha']:
        raise ValueError('SITE_ONLY_ORIGINAL_SOURCE_PROVIDER_REQUIRED')
    begin=arguments.get('begin',reference.begin);end=begin+slots*900
    if begin!=reference.begin or arguments.get('carryout') is not None:
        raise ValueError('SITE_ONLY_SOURCE_INITIAL_BOUNDARY_REQUIRED')
    if study_bindings is not None:require_bindings(study_bindings,study_bindings)
    original_requests=[r for r in arguments.get('requests',[]) if r.submit<end]
    running=arguments.get('running',[])
    # This comparison receipt identifies the source input, not a new Known
    # certificate. Private realizations stay in the common simulator bank.
    same_input=dict(source_case_sha=bindings['case_sha'],source_qos_sha=bindings['qos_sha'],
        Known_commands_sha=digest(reference.commands),reference_target_sha=reference.sha,
        source_initial_state_sha=bindings['initial_state_sha'],runtime_sha=bindings['runtime_sha'],
        response_sha=bindings['response_sha'],source_identity=deepcopy(source_identity or {}),
        boundary_completion_proof_sha=None if boundary_completion_proof is None else boundary_completion_proof['proof_sha'],
        begin_seconds=begin,end_seconds=end,slots=slots,
        public_requests_sha=digest([dict(uid=r.uid,submit=r.submit,gpu=r.gpu,compatible=r.compatible,
            q50=r.q50,source_site=r.source_site,metadata=r.metadata) for r in original_requests]),
        initial_Running_sha=digest([dict(uid=r.uid,site=s,start=t,gpu=r.gpu,q50=r.q50,metadata=r.metadata) for r,s,t in running]),
        source_prestart_site_authority=deepcopy(site_authority),time_shift=False,runtime_repair=False,migration=False,
        new_Known_Native_calls=0,Actual_global_MILP_calls=0)
    same_input['same_input_sha']=digest(same_input)
    reconciliation=known_initial_reconciliation(reference.commands,dict(
        running=[dict(r.metadata,uid=r.uid,origin_unknown=r.metadata.get('origin_unknown'),site=s,observed_start_seconds=t) for r,s,t in running],
        pending=[dict(r.metadata,uid=r.uid,origin_unknown=r.metadata.get('origin_unknown')) for r in original_requests if r.submit<=begin]),
        issue_seconds=(source_identity or {}).get('issue_seconds',begin),begin_seconds=begin)
    if not diagnostic and (reconciliation['status']!='RECONCILED' or (source_identity or {}).get('exact_Known_stage_case_match') is not True):
        raise ValueError('SITE_ONLY_SAME_CASE_KNOWN_RECONCILIATION_REQUIRED_FOR_CERTIFICATION')
    variants,policies,metrics={},{},[]
    for label,basic in (('C0',True),('C1',False)):
        frozen=SiteOnlySensitivityPolicy(reference,packet,bindings=bindings,expected_bindings=bindings,
            basic=basic,evidence_scope=evidence_scope or ('REAL_CURRENT_SOURCE_DIAGNOSTIC' if diagnostic else 'REAL_SAME_SOURCE_CASE_SITE_ONLY'),
            source_identity=source_identity,site_authority=site_authority)
        path=output/(label+'_FROZEN_SITE_ONLY_POLICY.json');frozen.save(path)
        policy=SiteOnlySensitivityPolicy.load(path,bindings=bindings).bind_runtime_packet(packet)
        args=deepcopy(arguments);args['requests']=deepcopy(original_requests);args['running']=deepcopy(running)
        args.update(arm='B1',begin=begin,end=end,frozen_policy=policy,known_schedule=reference.commands,
            expected_bindings=bindings)
        args.pop('boundary_completion_proof',None)
        if args.get('weather') is not None:args['weather']=args['weather'][:slots]
        _bind_driver_current_c1(policy,args)
        def controller(*a,**kw):
            return SiteOnlyJobEventController(*a,boundary_completion_proof=deepcopy(boundary_completion_proof),**kw)
        began=perf_counter();result=run_actual(**args,controller_class=controller);wall=perf_counter()-began
        if result['carryout']['controller']['site_only_state']['frozen_known_sha']!=digest(reference.commands):
            raise ValueError('SITE_ONLY_POST_ACTUAL_KNOWN_COMMAND_SHA_DRIFT')
        unknown=[r for r in result['queue_ledger'] if r['origin_unknown']]
        started=[r for r in unknown if r['admitted_time'] is not None and r['admitted_time']>=begin
            and r['job_uid'] not in {item[0].uid for item in running}]
        known=[r for r in result['queue_ledger'] if not r['origin_unknown'] and r['admitted_time'] is not None and r['admitted_time']>=begin]
        peaks,bad=[],[]
        if result['physical'] is not None:
            cols=[packet.control_names.index('aidc_load_kw['+s+']') for s in packet.sites]
            for t in range(slots):
                delta=(result['physical']['PCC_P_kw'][t]-packet.controls[t,cols])/packet.p_slope[t]
                peak,violations=packet._at_slot(t,delta);peaks.append(peak);bad.extend(violations)
        metrics.append(dict(variant=label,same_input_sha=same_input['same_input_sha'],
            policy_sha=policy.sha,policy_file_sha=hashlib.sha256(path.read_bytes()).hexdigest(),
            executed_Unknown_starts=len(started),executed_Known_starts=len(known),
            current_Unknown_choices=len(policy.audit),controller_P50_seconds=float(np.percentile(policy.times,50)) if policy.times else None,
            controller_P95_seconds=float(np.percentile(policy.times,95)) if policy.times else None,
            controller_max_seconds=max(policy.times,default=0.),Actual_wall_seconds=wall,
            prefix_slot_average_signed_max_line_loading=max(peaks,default=0.),
            prefix_slot_average_signed_grid_violations=bad,
            actual_intentional_Unknown_delay_seconds=max((r['intentional_start_delay_seconds'] for r in result['qos_ledger']
                if next(q for q in result['queue_ledger'] if q['job_uid']==r['uid'])['origin_unknown']),default=0.),
            capacity_violations=result['receipt']['capacity_violations'],anonymous_physical_GPU=result['receipt']['anonymous_physical_GPU'],
            Native_calls=0,AC_calls=0,Full96=False,Fresh_AC_status='NOT_RUN',certification_promoted=False))
        result['site_only']=dict(same_input=same_input,source_identity=deepcopy(source_identity),
            study_bindings=deepcopy(study_bindings),execution_bindings=dict(bindings),
            source_QoS_provider_unchanged=True,original_Known_selected_jobs_unchanged=True,
            decisions=policy.audit,current_candidates=policy.current_candidates,metrics=metrics[-1],
            Known_current_electrical_guards=policy.known_current_guards,
            Known_reconciliation=reconciliation,diagnostic=diagnostic)
        from .sensitivity_policy import _json
        (output/(label+'_ACTUAL_PREFIX.json')).write_text(json.dumps(_json(result),ensure_ascii=False,
            sort_keys=True,allow_nan=False),encoding='utf8')
        variants[label]=result;policies[label]=policy
    old={r['job_uid']:r for r in variants['C0']['queue_ledger'] if r['origin_unknown'] and r['admitted_time'] is not None}
    new={r['job_uid']:r for r in variants['C1']['queue_ledger'] if r['origin_unknown'] and r['admitted_time'] is not None}
    changed=[u for u in sorted(set(old)&set(new)) if old[u]['site']!=new[u]['site']]
    requests={r.uid:r for r in original_requests}
    changed_nominal=sum(requests[u].gpu*requests[u].q50/3600 for u in changed)
    changed_executed=sum(requests[u].gpu*new[u]['accumulated_compute_seconds']/3600 for u in changed)
    def known_execution(result):
        rows=[]
        for uid,meta in sorted(result['carryout']['controller']['metadata'].items()):
            if meta['origin_unknown']:continue
            audit=next(r for r in result['queue_ledger'] if r['job_uid']==uid)
            episode=result['carryout']['controller']['episode_jobs'][uid]
            rows.append(dict(uid=uid,site=audit['site'],admitted_time=audit['admitted_time'],
                accumulated_compute_seconds=meta['accumulated_compute_seconds'],latest_state=audit['latest_state'],
                completion_observed_time=episode['completion_observed_time'],release_control_time=episode['release_control_time']))
        return rows
    known0,known1=known_execution(variants['C0']),known_execution(variants['C1'])
    same_known=digest(known0)==digest(known1)
    receipt=dict(schema=SITE_ONLY_CONTRACT,status='KNOWN_EXECUTION_FAIRNESS_FAIL' if not same_known else
        'EXECUTED_PREFIX_DIAGNOSTIC_NOT_CERTIFIED' if diagnostic else 'EXECUTED_SAME_CASE_PREFIX_AC_PENDING',
        same_input=same_input,source_identity=deepcopy(source_identity),study_bindings=deepcopy(study_bindings),
        execution_bindings=dict(bindings),Known_reconciliation=reconciliation,
        comparison=metrics,changed_executed_site_UIDs=changed,changed_nominal_GPUh=changed_nominal,
        changed_actual_prefix_compute_GPUh=changed_executed,additional_C1_admitted_UIDs=sorted(set(new)-set(old)),
        additional_C0_admitted_UIDs=sorted(set(old)-set(new)),Native_calls=0,AC_calls=0,
        same_actual_Known_execution=same_known,C0_actual_Known_execution_sha=digest(known0),
        C1_actual_Known_execution_sha=digest(known1),C0_Known_execution=known0,C1_Known_execution=known1,
        source_current_response='AUTO_CAUSAL_PREFIX_SIGNED_SECANTS_PLUS_LDC_INTERVAL',
        Full96_status='NOT_RUN',Fresh11SVR_AC_status='NOT_RUN',certification_promoted=False)
    (output/'SITE_ONLY_CANARY_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,
        sort_keys=True,allow_nan=False),encoding='utf8')
    return dict(receipt=receipt,results=variants,policies=policies,packet=packet)


def run_dday_known_site_only_canary(output, *, slots=16, shared_manifest=None):
    """Prepare strict May01 source and the declared current Known queue rule.

    The factory reads source inputs and the simulator bank, but that bank is
    never supplied to the controller or planning descriptors. No A1 model is
    constructed or optimized, and no historical certificate is transferred.
    """
    from .unified_contract import load_contracts,REPORT
    from .tracking_canary import reference_from_anchor,HISTORICAL_A1
    from .partial_canary import SOURCE_DIR,source_known_records
    from .production_case import build_integration_case,read,ARCHIVE
    from .m_engine import file_record
    shared=shared_manifest or load_contracts();study=shared['bindings']
    require_bindings(study,load_contracts()['bindings'])
    interface=read(REPORT/'UNIFIED_INTERFACE_CONTRACT.json')
    if (interface.get('policy')!='DDAY_DETERMINISTIC_KNOWN_UNKNOWN_SITE_ONLY'
            or interface.get('max_start_delay_seconds')!=0 or interface.get('new_Known_A_Heavy_authorized') is not False):
        raise ValueError('FROZEN_SITE_ONLY_ACTIVE_SHARED_CONTRACT_REQUIRED')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    began=perf_counter();setup=output/'ORIGINAL_STRICT_SOURCE_SETUP'
    case=build_integration_case(source_freeze=read(SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        strict_stats=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json',output=setup/'CASE',a_call_cap=0.,
        initial_state_freeze=SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
    strict=case.qos_provider
    records=source_known_records(strict,read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json'))
    a_case=case.make_a_case('B1','A1',case.initial_mess,setup/'DESCRIPTOR_ONLY_A1')
    anchor=read(HISTORICAL_A1)
    # The legacy numeric-anchor reader expects an experimental attribute.
    # This strict-source study issues no migration authority or E1 binding.
    case.experimental_migration_authority=None
    reference,packet,cc4=reference_from_anchor(case,a_case,records,anchor,setup)
    execution=dict(study,science_sha=case.science_sha,case_sha=case.case_sha,qos_sha=strict.stats.sha,
        aidc_anchor=anchor['aidc_anchor'],mess_anchor=case.initial_mess['plan_sha'],
        cc4_sha=cc4['prediction_sha'],runtime_sha=cc4['runtime_sha'],response_sha=packet.bindings['response_sha'],
        initial_state_sha=case.actual_gate['common_initial_state_sha'])
    require_bindings(execution,execution);packet.bindings=dict(execution)
    # The B3/A1 historical provider point is identified independently from
    # the active B1 controller study and current descriptor case.
    original_stage_case=digest(dict(parent=case.case_sha,arm=a_case.arm,stage='A1',
        MESS_anchor=case.initial_mess['plan_sha'],QoS=strict.stats.sha))
    historical_stage_case=digest(dict(parent=case.case_sha,arm=anchor.get('arm','B3'),stage='A1',
        MESS_anchor=case.initial_mess['plan_sha'],QoS=strict.stats.sha))
    args=dict(case.actual_arguments,qos_window_provider=strict)
    baseline=build_dday_known_fcfs_baseline(args,packet)
    identity=dict(study_case_sha=study['case_sha'],study_science_sha=study['science_sha'],
        strict_source_case_sha=case.case_sha,strict_source_science_sha=case.science_sha,
        historical_Known_stage_case_sha=anchor['case_sha'],reconstructed_original_Known_stage_case_sha=historical_stage_case,
        exact_historical_Known_stage_case_match=anchor['case_sha']==historical_stage_case,
        current_descriptor_A1_case_sha=original_stage_case,
        original_Known_arm=anchor.get('arm','B3'),active_controller_arm='B1',day='2025-05-01',
        Source_SHA=case.source_freeze['source_sha'],historical_Known_artifact=file_record(HISTORICAL_A1),
        historical_Known_selected_jobs_sha=digest(anchor['selected_jobs']),
        historical_Known_commands_sha=digest(reference.commands),source_strict_QoS_SHA=strict.stats.sha,
        current_Known_rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL',current_Known_baseline_sha=baseline['baseline_sha'],
        active_Known_commands_sha=digest(baseline['commands']),Known_booking_horizon_seconds=reference.begin+86400,
        issue_seconds=case.planning_slot_zero_seconds,source_Dday_MODEL_ASSUMPTION=True,
        historical_FULL_feasible_preserved=anchor['FULL_feasible'],historical_certificate_transferred=False,
        E1_FLEX30_or_Research60_projection_used=False,new_Known_MILP_plan_built=False,
        historical_Known_commands_executed=False,current_Dday_diagnostic_Known_baseline=True,Native_calls=0,AC_calls=0,
        source_preparation_wall_seconds=perf_counter()-began)
    authority=dict(schema='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1',
        study_case_sha=study['case_sha'],interface_sha=study['interface_sha'],max_sites=12,
        candidate_axis='SOURCE_COMPATIBLE_SITES_ONLY',intentional_delay_seconds=0,
        Known_commands_modified=False,source_customer_SLA_claim=False,
        authorized_state='OBSERVED_PENDING_UNKNOWN',GPU_rack_residency_hard_windows_preserved=True,
        source_metadata_can_prestart_place_modified=False,source_QoS_receipts_modified=False)
    historical_reference=reference
    reference=TrackingReference(*(historical_reference.arrays[k] for k in
        ('G_Known_Plan','G_Unknown_Q50_Plan','IT_Plan','PCC_P_Plan','PCC_Q_Plan')),
        sites=historical_reference.sites,begin=historical_reference.begin,commands=baseline['commands'],
        identity=dict(historical_reference.identity,active_Known_baseline_sha=baseline['baseline_sha'],
            current_Known_rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL',
            historical_numeric_anchor_only=True,historical_Known_commands_executed=False,
            G_Known_Plan_semantics='HISTORICAL_GRID_LINEARIZATION_ANCHOR_ONLY_NOT_CURRENT_KNOWN_EXECUTION'))
    (output/'DDAY_DIAGNOSTIC_KNOWN_FCFS_BASELINE.json').write_text(json.dumps(baseline,ensure_ascii=False,
        sort_keys=True,allow_nan=False),encoding='utf8')
    proof=build_boundary_completion_proof(case.actual_gate['initial_state_freeze'],bindings=execution,
        begin_seconds=reference.begin,evidence_scope='REAL_HISTORICAL_PLAN_DIAGNOSTIC')
    result=run_site_only_prefix_canary(args,reference=reference,packet=packet,bindings=execution,
        study_bindings=study,source_identity=identity,site_authority=authority,
        boundary_completion_proof=proof,output=output,slots=slots,diagnostic=True)
    result['source_case']=case;result['historical_reference']=historical_reference
    result['Known_baseline']=baseline
    return result


def run_frozen_known_site_only_canary(*args,**kwargs):
    raise ValueError('HISTORICAL_KNOWN_ACTUAL_COMMANDS_HOLD_USE_CURRENT_DDAY_KNOWN_BASELINE')


def run_sensitivity_actual(arguments, *, reference, packet, bindings, expected_bindings,
        known_schedule, migration_authority=None, runtime_repair=True, basic=False,
        evidence_scope='REAL_DIAGNOSTIC'):
    """Supervisor adapter; Full96/AC certification is not inferred from a run."""
    policy = SignedSensitivityPolicy(reference, packet, bindings=bindings,
        expected_bindings=expected_bindings, migration_authority=migration_authority,
        runtime_repair=runtime_repair, basic=basic, evidence_scope=evidence_scope)
    _bind_driver_current_c1(policy, arguments)
    result = coordinator_actual_runner(**arguments, arm='B1', frozen_policy=policy,
        known_schedule=known_schedule, expected_bindings=bindings)
    result['signed_sensitivity_runtime'] = dict(policy_sha=policy.sha,
        bindings=bindings, evidence_scope=evidence_scope, policy_audit=policy.audit,
        migration_funnel=policy.funnel, decision_seconds=policy.times,
        grid_diagnostics=policy.diagnostics, online_global_optimizer_calls=0,
        Fresh_AC_status='NOT_RUN', Full96_new_planning_status='NOT_CERTIFIED')
    return result


def coordinator_actual_runner(**arguments):
    """Consume the coordinator's reloaded policy and original Known commands."""
    policy = arguments.get('frozen_policy')
    boundary_proof = arguments.pop('boundary_completion_proof',None)
    if not isinstance(policy, SignedSensitivityPolicy) or policy.packet is None:
        raise ValueError('SIGNED_RUNTIME_PACKET_REQUIRED')
    policy.require_bindings(arguments['expected_bindings'])
    if digest(arguments.get('known_schedule', {})) != digest(policy.reference.commands):
        raise ValueError('SIGNED_FROZEN_KNOWN_COMMAND_SHA_DRIFT')
    if policy.evidence_scope.startswith('REAL'):
        running = {r.uid for r, _, _ in arguments.get('running', [])}
        begin = arguments.get('begin', policy.reference.begin)
        commands = arguments.get('known_schedule', {})
        pending = {r.uid for r in arguments.get('requests', []) if r.submit <= begin and r.uid not in running}
        missing_prefix = [uid for uid in pending if uid in commands and commands[uid]['start_seconds'] < begin]
        if missing_prefix:
            raise ValueError('KNOWN_BOUNDARY_RECONCILIATION_REQUIRED:'+str(len(missing_prefix)))
    _bind_driver_current_c1(policy, arguments)
    def current_boundary_controller(*args,**kwargs):
        return SensitivityRuntimeController(*args,boundary_completion_proof=boundary_proof,
            boundary_begin_seconds=arguments.get('begin',policy.reference.begin),**kwargs)
    return run_actual(**arguments, controller_class=current_boundary_controller)


def _bind_driver_current_c1(policy, arguments):
    model = arguments.get('power_model')
    if model is None:
        if policy.evidence_scope.startswith('REAL'):
            raise ValueError('REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED')
        return
    begin = arguments.get('begin', policy.reference.begin)
    weather = arguments.get('weather')
    def current_weather(now):
        if policy.current is None or policy.current[0] != now:
            raise ValueError('FUTURE_ACTUAL_WEATHER_QUERY_FORBIDDEN')
        slot = int((now-begin)//900)
        if weather is None or not 0 <= slot < len(weather):
            raise ValueError('CURRENT_ACTUAL_WEATHER_NOT_OBSERVED')
        return deepcopy(weather[slot])
    policy.bind_observed_c1(model, current_weather_provider=current_weather)


def require_final_a_authority(a_case, aidc, bindings):
    """Original FULL handoff plus the captured current native producer."""
    from .coordinator import _full_a
    _full_a(aidc)
    if (aidc.get('case_sha') != a_case.case_sha or aidc.get('stage') != a_case.stage
            or aidc.get('arm') != a_case.arm or aidc.get('FULL_point_replay',{}).get('PASS') is not True):
        raise ValueError('FINAL_A_CURRENT_NATIVE_CASE_AUTHORITY_REQUIRED')
    call = aidc.get('Native_call',{})
    context = call.get('stage_context',{})
    if (call.get('label') != a_case.stage+'_ORIGINAL_P1' or call.get('solver') != 'GUROBI'
            or call.get('error') is not None or context.get('native_case_sha') != a_case.case_sha
            or context.get('stage') != a_case.stage or context.get('arm') != a_case.arm):
        raise ValueError('FINAL_A_CURRENT_NATIVE_CALL_RECEIPT_REQUIRED')
    for key in ('science_sha','case_sha','qos_sha','physical_sha','time_axis_sha','cc4_sha','runtime_sha','response_sha','initial_state_sha','interface_sha'):
        if context.get('bindings',{}).get(key) != bindings[key]:
            raise ValueError('FINAL_A_NATIVE_CALL_SHARED_BINDING_DRIFT:'+key)
    if set(aidc['selected_jobs']) != set(a_case.data[1]):
        raise ValueError('FINAL_A_CURRENT_KNOWN_ROSTER_DRIFT')
    names = ('nominal_site_GPU','reserve_site_GPU','known_site_GPU','resource_sites','CC4_reserve_service','CC4_reserve_carryout')
    if any(name not in aidc for name in names) or aidc.get('resource_distribution_sha') != digest({k:aidc[k] for k in names}):
        raise ValueError('FINAL_A_RESOURCE_DISTRIBUTION_SHA_DRIFT')
    return aidc


def select_cc4_headroom_seed_choices(a_case, *, issue_seconds, pairs=21, output=None):
    """Same-reference/QoS full-service candidate, not a feasibility certificate.

    Paired same-site short jobs leave early anonymous CDF headroom without
    moving history, renewing budgets, or restricting the final native domain.
    """
    from v42_job_capability import Option, validate
    if (a_case.arm,a_case.stage) != ('B1','A1') or type(pairs) is not int or pairs < 1:
        raise ValueError('B1_A1_EXPLICIT_HEADROOM_SEED_REQUIRED')
    bundle,jobs,bounds,hardware = a_case.data[:4]
    docs = {u:(r.to_dict() if hasattr(r,'to_dict') else deepcopy(r)) for u,r in a_case.qos_receipts.items()}
    receipt_sha = digest(docs)
    sites = tuple(sorted(hardware.capacities))
    horizon = max(max(b.latest_completion for b in bounds.values()),
        max((t+1 for _,t in hardware.fixed_gpu),default=0),120)
    caps = np.asarray([hardware.capacities[s] for s in sites])
    occupancy = np.zeros((horizon,len(sites)))
    fixed = np.zeros_like(occupancy)
    issued, authorized_bounds, baseline = {}, {}, {}
    for uid,job in jobs.items():
        doc = docs[uid]; model = doc.get('model_metadata',{})
        starts = (job.reference_start,) if job.state == 'RUNNING' else tuple(a_case.window_slots[uid])
        issued[uid] = replace(job,qos_policy_id=doc['policy_id'],qos_receipt_sha=digest(doc),
            qos_allowed_starts=starts,qos_budget_seconds=float(doc['budget_seconds']),is_observed=True,
            batch_eligible=model.get('batch_eligible',doc.get('batch_eligible',False)),
            qos=model.get('qos',job.qos),protected=model.get('protected',job.protected))
        authorized_bounds[uid] = replace(bounds[uid],allowed_starts=starts)
        option = Option(job.reference_start,job.reference_site,
            ((job.reference_site,job.reference_start,job.reference_start+job.service_slots),))
        validate(issued[uid],option,authorized_bounds[uid],hardware)
        baseline[uid] = option
        occupancy[option.start:option.start+job.service_slots,sites.index(option.initial_site)] += job.gpu
    for (site,t),value in hardware.fixed_gpu.items():
        if 0 <= t < horizon:
            fixed[t,sites.index(site)] += value
    if np.any(occupancy+fixed > caps+1e-9):
        raise ValueError('BASELINE_NATIVE_INTERVAL_CAPACITY_REPLAY_FAILED')

    def eligible(uid,expected,new_start):
        job,doc = jobs[uid],docs[uid]
        if (job.state != 'PENDING' or job.reference_start != expected or job.service_slots != 3
                or doc.get('participant') is not True or doc.get('eligible_for_contract') is not True
                or new_start not in a_case.window_slots[uid]):
            return False
        spend = (new_start-job.reference_start)*900+job.qos_start_delay_seconds
        if spend > doc['budget_seconds'] or doc['reference_start_seconds'] != issue_seconds+expected*900:
            return False
        hard = doc['hard_contract']; start_seconds = issue_seconds+new_start*900
        nominal = hard.get('nominal_service_seconds')
        if nominal is None:
            nominal = doc['t50_seconds']
        if any(hard.get(k) is not None and start_seconds < hard[k] for k in ('release_seconds','hard_earliest_start_seconds')):
            return False
        if (hard.get('hard_latest_start_seconds') is not None and start_seconds > hard['hard_latest_start_seconds']
                or hard.get('completion_deadline_seconds') is not None and start_seconds+nominal > hard['completion_deadline_seconds']):
            return False
        option = Option(new_start,job.reference_site,((job.reference_site,new_start,new_start+job.service_slots),))
        validate(issued[uid],option,authorized_bounds[uid],hardware)
        return True

    first = {s:[] for s in sites}; second = {s:[] for s in sites}
    for uid,job in sorted(jobs.items(),key=lambda r:(r[1].submit,r[0])):
        if eligible(uid,24,28): first[job.reference_site].append(uid)
        if eligible(uid,27,30): second[job.reference_site].append(uid)
    choices,pair_receipts,used = {},[],set()
    for site in sites:
        for left in first[site]:
            if len(pair_receipts) >= pairs:
                break
            for right in second[site]:
                if right in used:
                    continue
                trial = occupancy.copy()
                for uid,start in ((left,28),(right,30)):
                    job = jobs[uid]; column = sites.index(site)
                    trial[job.reference_start:job.reference_start+job.service_slots,column] -= job.gpu
                    trial[start:start+job.service_slots,column] += job.gpu
                if np.any(trial+fixed > caps+1e-9):
                    continue
                occupancy = trial; used.update((left,right))
                for uid,start in ((left,28),(right,30)):
                    choices[uid] = asdict(Option(start,site,((site,start,start+jobs[uid].service_slots),)))
                pair_receipts.append(dict(first_UID=left,second_UID=right,site=site,
                    first_plan_start=28,second_plan_start=30,
                    first_frozen_reference_start=24,second_frozen_reference_start=27,
                    first_intentional_delay_seconds=3600,second_intentional_delay_seconds=2700,
                    first_budget_seconds=docs[left]['budget_seconds'],second_budget_seconds=docs[right]['budget_seconds'],
                    first_receipt_sha=digest(docs[left]),second_receipt_sha=digest(docs[right]),
                    source_service_slots=3,source_GPU_gangs=[jobs[left].gpu,jobs[right].gpu],
                    original_sites_preserved=True,whole_service_preserved=True))
                break
    lower = np.asarray(a_case.grid.timing_lower,float)
    hourly = np.asarray(bundle['C0_Q50'],float)
    cumulative = []
    for t in range(96):
        required = sum(hourly[h]*lower[min(t-4*h,len(lower)-1)] for h in range(24) if t>=4*h)
        free = float(np.maximum(caps-occupancy[24:25+t]-fixed[24:25+t],0).sum()/4)
        cumulative.append(dict(dday_slot=t,minimum_cumulative_CC4_GPUh=float(required),
            cumulative_free_capacity_GPUh=free,necessary_capacity_PASS=bool(free+1e-7>=required)))
    if digest({u:(r.to_dict() if hasattr(r,'to_dict') else r) for u,r in a_case.qos_receipts.items()}) != receipt_sha:
        raise ValueError('HEADROOM_SEED_IMMUTABLE_RECEIPT_DRIFT')
    enough = len(pair_receipts) == pairs
    result = dict(schema='CURRENT_CASE_SAME_REFERENCE_PARTICIPANT_HEADROOM_SEED_V1',
        bindings=getattr(a_case,'unified_bindings',None),native_case_sha=a_case.case_sha,
        override_plans=choices,selected_UIDs=sorted(choices),pair_receipts=pair_receipts,
        requested_pairs=pairs,selected_pairs=len(pair_receipts),same_site_pair_counts={s:sum(r['site']==s for r in pair_receipts) for s in sites},
        cumulative_capacity_audit=cumulative,all_necessary_CDF_capacity_PASS=all(r['necessary_capacity_PASS'] for r in cumulative),
        original_receipts_sha=receipt_sha,original_reference_and_budget_changed=False,
        source_service_amount_changed=False,physical_domain_options_pruned=False,
        Native_calls=0,models_built=0,Full_grid_and_CDF='NOT_CHECKED',
        status='NECESSARY_CAPACITY_WITNESS_FULL_NOT_CHECKED' if enough and all(r['necessary_capacity_PASS'] for r in cumulative)
            else 'INSUFFICIENT_AUTHORIZED_PAIRED_HEADROOM_FULL_NOT_CHECKED',
        native_interval_occupancy_GPU=occupancy.tolist(),site_axis=list(sites))
    if output is not None:
        Path(output).write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result


def audit_seed_grid_outer_box(a_case, override_plans=None, *, output=None):
    """Outward electrical enclosure from an already loaded original A grid.

    Anonymous GPU ranges over its entire physical site box. Individual row
    conflicts are necessary impossibility proofs for these fixed Known choices;
    a conflict-free box does not establish joint CC4/grid feasibility.
    """
    if (a_case.arm,a_case.stage) != ('B1','A1'):
        raise ValueError('B1_A1_SEED_GRID_AUDIT_REQUIRED')
    bundle,jobs,bounds,hardware = a_case.data[:4]
    grid = a_case.grid; overrides = override_plans or {}
    sites = tuple(sorted(hardware.capacities)); cap=np.asarray([hardware.capacities[s] for s in sites],float)
    known=np.zeros((96,len(sites)))
    for uid,job in jobs.items():
        choice=overrides.get(uid,dict(start=job.reference_start,initial_site=job.reference_site,
            segments=((job.reference_site,job.reference_start,job.reference_start+job.service_slots),)))
        if (choice['initial_site']!=job.reference_site or sum(b-a for _,a,b in choice['segments'])!=job.service_slots
                or choice['start'] not in a_case.window_slots[uid]):
            raise ValueError('SEED_GRID_COMPLETE_SOURCE_OPTION_REQUIRED:'+uid)
        for site,a,b in choice['segments']:
            a,b=max(a,24),min(b,120)
            if b>a:known[a-24:b-24,sites.index(site)] += job.gpu
    for (site,t),value in hardware.fixed_gpu.items():
        if 24<=t<120:known[t-24,sites.index(site)]+=value
    if np.any(known>cap):
        raise ValueError('SEED_GRID_PHYSICAL_BOX_EMPTY')
    mess=grid.fixed_mess
    if mess is None or any(float(v)!=0 for f in ('P_by_site','Q_by_site') for row in mess[f].values() for v in row):
        raise ValueError('SEED_GRID_ORIGINAL_MESS_OFF_REQUIRED')
    down=lambda x:np.nextafter(np.asarray(x,float),-np.inf)
    up=lambda x:np.nextafter(np.asarray(x,float),np.inf)
    def multiply(a,lo,hi):
        a=np.asarray(a,float)
        return down(np.minimum(a*lo,a*hi)),up(np.maximum(a*lo,a*hi))
    def dot(matrix,lo,hi,base):
        weights=np.asarray(matrix,float); lower=np.asarray(base,float).copy();upper=lower.copy()
        for k in range(weights.shape[1]):
            l,u=multiply(weights[:,k],lo[k],hi[k]);lower=down(lower+l);upper=up(upper+u)
        return lower,upper
    def plus(llo,lhi,rlo,rhi):return down(llo+rlo),up(lhi+rhi)
    conflicts=[];checked=0;slot_bounds=[]
    for t,c in enumerate(grid.coefficients):
        lo=[];hi=[]
        for name in c.control_names:
            site=name.split('[',1)[1][:-1]
            if name.startswith('aidc_load_kw'):
                j=sites.index(site);power=grid.power[site,t]
                if not (math.isfinite(power.slope) and power.slope>0 and math.isfinite(grid.swing_kw) and grid.swing_kw>0):
                    raise ValueError('POSITIVE_ORIGINAL_C1_GPU_SLOPE_REQUIRED')
                idle_lo,idle_hi=multiply(grid.idle_kw,cap[j],cap[j])
                active_lo,active_hi=multiply(grid.swing_kw,known[t,j],cap[j])
                it_lo,it_hi=plus(idle_lo,idle_hi,active_lo,active_hi)
                p_lo,p_hi=multiply(power.slope,it_lo,it_hi)
                lo.append(float(down(p_lo+power.intercept_kw)));hi.append(float(up(p_hi+power.intercept_kw)))
            elif name.startswith('mess_p_kw'):lo.append(float(mess['P_by_site'][site][t]));hi.append(lo[-1])
            elif name.startswith('mess_q_kvar') or name.startswith('mess_q_kw'):lo.append(float(mess['Q_by_site'][site][t]));hi.append(lo[-1])
            else:raise ValueError('UNKNOWN_ORIGINAL_GRID_CONTROL:'+name)
        lo,hi=np.asarray(lo),np.asarray(hi)
        def record(kind,index,bound_low,bound_high,limit,direction,branch=None,face=None):
            nonlocal checked
            checked+=1
            impossible=bound_high<limit if direction=='LOWER' else bound_low>limit
            if impossible:
                conflicts.append(dict(row_kind=kind,slot=t,row_index=int(index),branch=branch,face=face,
                    attainable_outer_lower=float(bound_low),attainable_outer_upper=float(bound_high),
                    original_limit=float(limit),required_sense=direction,
                    coefficient_sha=c.coefficient_sha256,
                    outward_bound_proven=True,anonymous_GPU_lower=0,
                    anonymous_GPU_upper_by_site=dict(zip(sites,(cap-known[t]).tolist()))))
        vl,vh=dot(c.voltage_matrix.T,lo,hi,c.voltage_constant)
        for n in range(len(vl)):
            record('voltage_lower',n,vl[n],vh[n],grid.authority.voltage_lower_squared,'LOWER')
            record('voltage_upper',n,vl[n],vh[n],grid.authority.voltage_upper_squared,'UPPER')
        il,ih=dot(c.current_matrix.T,lo,hi,c.current_constant)
        pl,ph=dot(c.flow_p_matrix,lo,hi,c.flow_p_constant)
        ql,qh=dot(c.flow_q_matrix,lo,hi,c.flow_q_constant)
        angles=2*np.pi*np.arange(16)/16;cos=np.cos(angles);sin=np.sin(angles)
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
        grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad
        bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(raw,axis=1)
        dl,dh=dot(correction,down(lo-c.anchor),up(hi-c.anchor),np.zeros(len(c.branch_names)))
        for b,name in enumerate(c.branch_names):
            if name.lower().startswith('transformer.'):
                record('transformer_current',b,il[b],ih[b],1.,'UPPER',branch=name)
            for f in range(16):
                lp,hp=multiply(cos[f],pl[b],ph[b]);lq,hq=multiply(sin[f],ql[b],qh[b])
                flow_lo,flow_hi=plus(lp,hp,lq,hq)
                if not name.lower().startswith('transformer.'):
                    rl,rh=down(1./ap[b]),up(1./ap[b])
                    products=np.asarray([flow_lo*rl,flow_lo*rh,flow_hi*rl,flow_hi*rh])
                    nl,nh=down(np.min(products)),up(np.max(products))
                    nl,nh=plus(nl,nh,dl[b],dh[b]);nl,nh=plus(nl,nh,bias[b],bias[b])
                    record('line_thermal_face',b,nl,nh,1.,'UPPER',branch=name,face=f)
                rating=c.transformer_ratings[b]
                if rating is not None:
                    record('transformer_kVA',b,flow_lo,flow_hi,float(rating)*math.cos(math.pi/16),'UPPER',branch=name,face=f)
        slot_bounds.append(dict(slot=t,known_GPU_by_site=dict(zip(sites,known[t].tolist())),
            anonymous_GPU_upper_by_site=dict(zip(sites,(cap-known[t]).tolist())),
            PCC_control_outer_lower=lo.tolist(),PCC_control_outer_upper=hi.tolist(),
            coefficient_sha=c.coefficient_sha256))
    result=dict(schema='ORIGINAL_FULL96_FIXED_KNOWN_ANONYMOUS_BOX_ROW_AUDIT_V1',
        bindings=getattr(a_case,'unified_bindings',None),native_case_sha=a_case.case_sha,
        override_plan_sha=digest(overrides),checked_rows=checked,conflicts=conflicts,slot_bounds=slot_bounds,
        outward_method='IEEE_NEXTAFTER_AT_EVERY_PRODUCT_AND_ACCUMULATION_NO_COEFFICIENT_DELETION',
        status='PROVEN_INDIVIDUAL_ROW_CONFLICT' if conflicts else 'NO_INDIVIDUAL_BOX_CONFLICT_JOINT_FEASIBILITY_NOT_CERTIFIED',
        Full_grid_CDF='NOT_CERTIFIED',Native_calls=0,models_built=0,Actual_bank_read=False)
    if output is not None:Path(output).write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result


def build_issue_only_dday_reference(records, native_data, *, issue_seconds, begin_seconds, namespace_sha):
    """NEW Dday study baseline, computed entirely from already observed jobs.

    It is a source-compatible modeled FCFS reference, not a reconstruction of
    observed Dday events or a relocation of an old command. Original source
    references remain in the audit. Q50 carry is a Planning forecast only.
    """
    bundle, jobs, bounds, hardware = native_data[:4]
    capacities = dict(hardware.capacities)
    racks = getattr(hardware, 'rack_limits', {s:(v,) for s,v in capacities.items()})
    rows = {r['job_uid']:r for r in bundle.get('known_population', [])}
    contract = dict(schema='ISSUE_ONLY_DDAY_FCFS_REFERENCE_V1', issue_seconds=issue_seconds,
        begin_seconds=begin_seconds, source_issue_records_sha=digest({u:asdict(j) for u,j in records.items()}),
        capacities=capacities, rack_compatibility=racks, native_known_UID_sha=digest(sorted(jobs)),
        science_namespace_sha=namespace_sha, Running='ISSUE_Q50_PROJECTED_CARRY_NOT_ACTUAL_COMPLETION',
        Pending='SOURCE_COMPATIBLE_FCFS_NOT_BEFORE_DDAY', future_Actual_reads=0,
        old_reference_retimed=False, customer_SLA_changed=False)
    reference_sha = digest(contract)
    scheduler = CausalReferenceScheduler(capacities, reference_sha=reference_sha)
    projected = []
    for uid, job in sorted(jobs.items()):
        if job.state != 'RUNNING':
            continue
        site = job.reference_site
        if site not in capacities:
            raise ValueError('SOURCE_RUNNING_SITE_AUTHORITY_REQUIRED:'+uid)
        remaining = max(0., job.service_slots*900-(begin_seconds-issue_seconds))
        if remaining:
            scheduler.reservations[site].append((begin_seconds, begin_seconds+remaining, records[uid].gpu))
        projected.append(dict(uid=uid, source_site=site, issue_remaining_Q50_seconds=job.service_slots*900,
            forecast_Dday_remaining_Q50_seconds=remaining, future_actual_completion_read=False,
            physical_release_claim=False))
    for site in capacities:
        fixed = getattr(hardware, 'fixed_gpu', {})
        native_begin = int((begin_seconds-issue_seconds)//900)
        for t in range(native_begin, getattr(hardware, 'control_end', native_begin+96)):
            quantity = fixed.get((site, t), 0)
            if quantity:
                scheduler.reservations[site].append((issue_seconds+t*900, issue_seconds+(t+1)*900, quantity))
    updated, assignments, difficulty = {}, {}, []
    for uid, source in sorted(records.items(), key=lambda item:(item[1].submit_seconds, item[0])):
        native = jobs.get(uid)
        if native is None or native.state == 'RUNNING':
            # Running history is a continuation, never a fresh Pending start.
            updated[uid] = replace(source, reference_sha=reference_sha)
            continue
        compatible = tuple(s for s in native.initial_sites
            if s in capacities and source.gpu <= max(racks[s]))
        if not compatible:
            raise ValueError('SOURCE_COMPATIBLE_WHOLE_GANG_REQUIRED:'+uid)
        request = Request(uid=uid, submit=source.submit_seconds, gpu=source.gpu,
            q50=source.t50_seconds, compatible=compatible, source_site=None)
        reference = scheduler.submit(request, event_seconds=begin_seconds)
        start = reference['reference_start_seconds']
        assignments[uid] = dict(reference, source_reference_start_seconds=source.reference_start_seconds,
            source_reference_sha=source.reference_sha, research_reference_wait_seconds=start-source.submit_seconds,
            source_submit_state_Q50_GPU_unchanged=True)
        if (source.hard_latest_start_seconds is not None and start > source.hard_latest_start_seconds
                or source.completion_deadline_seconds is not None and start+source.t50_seconds > source.completion_deadline_seconds):
            difficulty.append(dict(uid=uid, reason='ORIGINAL_HARD_DEADLINE_OR_LATEST_START'))
        updated[uid] = replace(source, reference_start_seconds=start, reference_sha=reference_sha)
    audit = dict(contract=contract, reference_sha=reference_sha, assignments=assignments,
        original_references={u:dict(reference_start_seconds=j.reference_start_seconds, reference_sha=j.reference_sha,
            authority_sha=j.authority_sha) for u,j in records.items()},
        projected_Running=projected, original_hard_window_difficulties=difficulty,
        new_baseline_pending_UIDs=len(assignments), future_Dday_snapshot_used=False,
        future_Unknown_UIDs_in_Planning=0, solver_calls=0, classification_changed=False,
        source_contract_status='EXPLICIT_NEW_STUDY_REFERENCE_MODEL_NOT_OBSERVED_SLA_OR_HISTORY')
    return updated, audit


def bind_unified_planning(case, issue_records, shared_manifest):
    """Connect issue-only research60 domains to original A1/M1/A2/M2 engines.

    No Actual request bank, future completion, native model or solver is read
    or invoked at binding. Empty post-Dday authorized Pending windows are
    explicitly rejected when a stage materializes; budgets are not renewed.
    """
    from .unified_contract import REPORT
    from .experimental_actual import prepare_conditional_arguments
    from .known_commands import compile_known_commands
    from .sensitivity_policy import build_grid_packet
    if case._consumed:
        raise ValueError('PLANNING_CASE_ALREADY_CONSUMED')
    shared = dict(shared_manifest['bindings'])
    spec = shared_manifest.get('qos_contract')
    if spec is None:
        spec = json.loads((REPORT/'TIME_SHIFT_60MIN_QOS_CONTRACT.json').read_text(encoding='utf-8'))
    if digest(spec) != shared['qos_sha']:
        raise ValueError('SHARED_RESEARCH60_POLICY_SHA_DRIFT')
    physical = shared_manifest.get('physical_contract')
    if physical is None:
        physical = json.loads((REPORT/'UNIFIED_PHYSICAL_AUTHORITY.json').read_text(encoding='utf-8'))
    records = {}
    issue = case.planning_slot_zero_seconds
    begin = issue+24*900
    for uid, value in issue_records.items():
        if not isinstance(value, ObservedJob):
            value = value.get('observed', value)
        job = value if isinstance(value, ObservedJob) else ObservedJob(**{
            f.name:value[f.name] for f in fields(ObservedJob) if f.name in value})
        _require_public_metadata(asdict(job))
        if (uid != job.uid or job.origin_unknown or not job.is_observed
                or job.event_seconds > issue or job.submit_seconds > issue):
            raise ValueError('ISSUE_ONLY_KNOWN_RECORDS_REQUIRED')
        records[uid] = job
    strict = case.qos_provider
    original_a, original_m = case.make_a_case, case.make_m_case
    seed = original_a('B1', 'A1', case.initial_mess, Path('.'))
    original_records = dict(records)
    records, reference_audit = build_issue_only_dday_reference(records, seed.data,
        issue_seconds=issue, begin_seconds=begin, namespace_sha=shared['science_sha'])
    provider = Research60QoSProvider(strict, case_sha=shared['case_sha'], frozen_spec=spec)
    for uid, job in records.items():
        provider.register_observed(uid)
        provider.issue(job)
    binding_audit = dict(source_known_UIDs=len(records), future_Actual_bank_read_at_binding=False,
        future_completion_read=False, Native_Optimize_calls=0, source_training_sha=strict.stats.sha,
        research_policy_sha=provider.stats.sha, issue_seconds=issue, begin_seconds=begin,
        original_issue_budgets_preserved=True, stage_domains={}, stage_handoffs=[])
    binding_audit['new_issue_only_Dday_reference'] = reference_audit
    materialized_grid = {}

    def make_a(arm, stage, mess, output):
        result = original_a(arm, stage, mess, output)
        jobs = result.data[1]
        if set(jobs)-set(records):
            raise ValueError('UNKNOWN_NOT_PRESENT_AT_PLANNING')
        windows, empty = {}, []
        for uid, job in jobs.items():
            if job.state == 'RUNNING':
                windows[uid] = (job.reference_start,)
            elif job.state == 'PENDING':
                allowed = receipt_slot_domain(provider.receipts[uid], axis_origin_seconds=issue)
                ceiling = result.data[2][uid].latest_completion-job.service_slots
                windows[uid] = tuple(s for s in allowed if issue+s*900 >= begin and s <= ceiling)
                if not windows[uid]:
                    empty.append(uid)
            else:
                raise ValueError('ORIGINAL_PLANNING_JOB_STATE_REQUIRED')
        domain = dict(stage=stage, arm=arm, known_UIDs=len(jobs),
            post_Dday_pending_domain_UIDs=sum(bool(windows[u]) for u, j in jobs.items() if j.state == 'PENDING'),
            empty_post_Dday_authorized_UIDs=empty, empty_post_Dday_authorized_count=len(empty),
            pending_starts_before_Dday=0, prefix_execution_certificate_supplied=False,
            late_old_commands_retimed=False, budgets_extended=False, future_Dday_state_used=False,
            fixed_mess_anchor=mess['plan_sha'], window_slots_sha=digest(windows),
            status='EMPTY_AUTHORIZED_BOUNDARY_DOMAIN' if empty else 'NEW_DOMAIN_BOUND_NATIVE_NOT_RUN')
        domain.update(original_completion_representation_ceilings_preserved=True,
            duration_service_authority_unchanged=True,
            unstarted_carried_pending_required_for_empty_UIDs=empty)
        binding_audit['stage_domains'][stage] = domain
        if empty:
            raise ValueError('EMPTY_POST_DDAY_AUTHORIZED_KNOWN_DOMAIN:'+str(len(empty)))
        result.qos_receipts = {u:provider.receipts[u] for u in jobs}
        result.window_slots = windows
        changed_jobs = {u:replace(j, reference_start=int((records[u].reference_start_seconds-issue)/900),
            reference_site=reference_audit['assignments'][u]['reference_site'])
            if j.state == 'PENDING' else j for u,j in jobs.items()}
        result.data = (result.data[0], changed_jobs)+tuple(result.data[2:])
        result.unified_bindings = dict(shared, aidc_anchor=case.reference_aidc['aidc_anchor'], mess_anchor=mess['plan_sha'])
        result.case_sha = digest(dict(shared_case_sha=shared['case_sha'], stage=stage, arm=arm,
            MESS_anchor=mess['plan_sha'], QoS=provider.stats.sha, boundary_domain_sha=digest(domain)))
        materialized_grid[stage] = result
        binding_audit['stage_handoffs'].append(dict(stage=stage, fixed_MESS_anchor=mess['plan_sha'],
            QoS_sha=provider.stats.sha, physical_sha=shared['physical_sha'], domain_sha=digest(domain)))
        return result

    def make_m(arm, stage, aidc, output):
        result = original_m(arm, stage, aidc, output)
        result.identity.update(qos_sha=provider.stats.sha, science_sha=shared['science_sha'],
            research_planning_case_sha=shared['case_sha'], physical_sha=shared['physical_sha'],
            response_sha=shared['response_sha'], time_axis_sha=shared['time_axis_sha'],
            aidc_anchor=aidc['aidc_anchor'])
        result.unified_bindings = dict(shared, aidc_anchor=aidc['aidc_anchor'])
        result.case_sha = digest(dict(identity=result.identity, stage=stage,
            shared_case_sha=shared['case_sha'], current_AIDC_anchor=aidc['aidc_anchor']))
        binding_audit['stage_handoffs'].append(dict(stage=stage, fixed_AIDC_anchor=aidc['aidc_anchor'],
            QoS_sha=provider.stats.sha, physical_sha=shared['physical_sha']))
        return result

    def prepare_actual():
        # Deferred closure: policy/file freeze occurs first in coordinator.
        base = dict(case.actual_arguments, qos_window_provider=strict)
        def modeled_reference_request(request):
            if request.uid not in records:
                return request
            raw = deepcopy(request.metadata)
            original = original_records[request.uid]
            raw['original_issue_reference_authority'] = dict(reference_sha=original.reference_sha,
                reference_start_seconds=original.reference_start_seconds, authority_sha=original.authority_sha)
            raw.update(reference_sha=records[request.uid].reference_sha,
                reference_start_seconds=records[request.uid].reference_start_seconds,
                representation_starts_seconds=records[request.uid].representation_starts_seconds)
            assignment = reference_audit['assignments'].get(request.uid)
            if assignment is not None:
                raw['original_modeled_source_site'] = request.source_site
                raw['study_baseline_site_is_observed_Kestrel_site'] = False
                return replace(request, metadata=raw, source_site=assignment['reference_site'])
            return replace(request, metadata=raw)
        base['requests'] = [modeled_reference_request(r) for r in base.get('requests', [])]
        base['running'] = [(modeled_reference_request(r), site, start) for r,site,start in base.get('running', [])]
        projected = prepare_conditional_arguments(base, records,
            scenario='U60', participation='FLEX30', case_sha=shared['case_sha'], existing_provider=provider)
        arguments = projected['arguments']
        arguments.pop('qos_window_provider')
        if case.evidence_kind == 'REAL_DATA':
            arguments['boundary_completion_proof'] = build_boundary_completion_proof(
                case.actual_gate['initial_state_freeze'],bindings=shared,begin_seconds=begin)
        return arguments, projected['projection_receipt']

    def factory(*, arm, aidc, mess, bindings, envelope, output, mess_validation):
        current = dict(shared, aidc_anchor=aidc['aidc_anchor'], mess_anchor=mess['plan_sha'])
        require_bindings(bindings, current)
        a = materialized_grid.get('A2' if arm == 'B3' else 'A1')
        if a is None:
            raise ValueError('FINAL_A_STAGE_DOMAIN_NOT_MATERIALIZED')
        if case.evidence_kind == 'REAL_DATA':
            require_final_a_authority(a,aidc,bindings)
        grid, hardware = a.grid, a.data[3]
        sites = tuple(sorted(hardware.capacities))
        known = np.asarray([aidc['known_site_GPU'][s] for s in sites], float).T
        unknown = np.asarray([aidc['nominal_site_GPU'][s] for s in sites], float).T
        p = np.asarray([aidc['AIDC_P_by_site'][s] for s in sites], float).T
        q = np.asarray([aidc['AIDC_Q_by_site'][s] for s in sites], float).T
        it = grid.idle_kw*np.asarray([hardware.capacities[s] for s in sites])+grid.swing_kw*(known+unknown)
        rebuilt = np.asarray([[grid.power[s,t].slope*it[t,j]+grid.power[s,t].intercept_kw
            for j, s in enumerate(sites)] for t in range(96)])
        if not np.allclose(p, rebuilt, rtol=0, atol=1e-7) or not np.allclose(q, p*np.tan(np.arccos(.95)), rtol=0, atol=1e-7):
            raise ValueError('FINAL_AIDC_EXACT_C1_PQ_DRIFT')
        commands = compile_known_commands(aidc['selected_jobs'], slot_zero_seconds=issue,
            migration_authority=case.experimental_migration_authority,
            gpu_by_uid={u:j.gpu for u,j in records.items()})
        reference = TrackingReference(known, unknown, it, p, q, sites=sites, begin=begin,
            commands=commands, identity=dict(bindings,
                lineage='NEW_U60_B1_A1_ONLY' if arm == 'B1' else 'NEW_U60_A1_M1_A2_M2_ONLY',
                final_known_stage='A1' if arm == 'B1' else 'A2',
                C1_Power_Model_SHA=physical['C1_power_sha'],
                CC4_service=aidc['CC4_service'], CC4_carryout=aidc['CC4_carryout'],
                CC4_Q50=list(a.data[0]['C0_Q50']), CC4_Q90=list(a.data[0]['C0_Q90']),
                Timing_CDF_Q10=list(grid.timing_lower), Timing_CDF_Q90=list(grid.timing_upper),
                CC4_source_authority=dict(model_id='LGBM_weighted_c1_s20260924',
                    prediction_sha=bindings['cc4_sha'], kernel_sha=digest(list(grid.kernel)),
                    timing_envelope_sha=digest(dict(lower=list(grid.timing_lower), upper=list(grid.timing_upper))),
                    aidc_anchor=aidc['aidc_anchor'], future_Actual_or_UID_inputs_used=False,
                    forecast_modifications=0),
                future_Actual_UIDs_or_completion_used=False))
        packet = build_grid_packet(grid.coefficients, grid.power, grid.swing_kw, hardware.capacities,
            aidc, mess, grid.authority, bindings, begin_seconds=begin, known_gpu=known,
            mess_validation=mess_validation, rack_compatibility=hardware.rack_limits)
        return SignedSensitivityPolicy(reference, packet, bindings=bindings, expected_bindings=current,
            migration_authority=case.experimental_migration_authority,
            evidence_scope='REAL_NEW_U60' if case.evidence_kind == 'REAL_DATA' else 'NAMED_UNIFIED_PLANNING_FIXTURE')

    case.make_a_case, case.make_m_case = make_a, make_m
    case.qos_provider = provider
    case.case_sha, case.science_sha = shared['case_sha'], shared['science_sha']
    case.unified_bindings = dict(shared, aidc_anchor=case.reference_aidc['aidc_anchor'],
        mess_anchor=case.initial_mess['plan_sha'])
    require_bindings(case.unified_bindings, case.unified_bindings)
    case.unified_actual_runner = coordinator_actual_runner
    case.prepare_research_actual_arguments = prepare_actual
    case.control_policy_factory = factory
    if not hasattr(case, 'experimental_migration_authority'):
        if case.evidence_kind == 'REAL_DATA':
            from .experimental_policy import load_experimental_migration_authority
            case.experimental_migration_authority = load_experimental_migration_authority()
        else:
            case.experimental_migration_authority = None
    case.research_contract_binding = dict(bindings=case.unified_bindings, issue_known_sha=digest(
        {u:asdict(j) for u,j in records.items()}), Known_issue_UIDs=len(records),
        boundary_bridge=binding_audit, future_Actual_request_bank_enumerated_at_Planning=False,
        Actual_public_request_projection='DEFERRED_UNTIL_AFTER_FINAL_POLICY_FREEZE',
        Native_Optimize_calls=0, new_Known_domain_required=True, source_contract_and_model_contract_separate=True)
    return case


def build_new_unified_case(output, *, shared_manifest=None, a_call_cap=10., m_stage_cap=30.):
    """Practical real-source factory; original Full96 physics, no solve here."""
    from .unified_contract import load_contracts
    from .production_case import build_integration_case, read, ARCHIVE
    from .partial_canary import SOURCE_DIR, source_known_records
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    shared = load_contracts() if shared_manifest is None else shared_manifest
    case = build_integration_case(source_freeze=read(SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        strict_stats=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json', output=output/'CASE',
        initial_state_freeze=SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json',
        a_call_cap=float(a_call_cap), m_stage_cap=float(m_stage_cap))
    records = source_known_records(case.qos_provider, read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json'))
    bind_unified_planning(case, records, shared)
    audit = case.research_contract_binding['boundary_bridge']
    (output/'ISSUE_ONLY_DDAY_KNOWN_REFERENCE.json').write_text(json.dumps(audit,
        sort_keys=True, allow_nan=False), encoding='utf-8')
    return case


def bind_current_event_planning(case,issue_records,shared_manifest,*,handoff_factory=None,
        basic=False,corrective_authority=None,runtime_repair=False,runtime_fixture_gate=None):
    """Active original A1/M1/A2/M2 binding with a current-event Actual hook.

    The legacy research binder supplies original Planning domains only. Its
    SignedSensitivityPolicy and Actual runner are replaced. A supervisor must
    provide independent source/initial-state handoff data; missing evidence
    fails before the deferred Actual request bank is projected.
    """
    from .followup_contract import require_planning_actual_handoff
    from .aidc_resource_bridge import PlanningActualResourceBridge
    bind_unified_planning(case,issue_records,shared_manifest)
    legacy_factory=case.control_policy_factory
    legacy_prepare=case.prepare_research_actual_arguments
    frozen={}

    def factory(**kwargs):
        aidc=kwargs['aidc']
        if aidc.get('FULL_feasible') is not True:raise ValueError('SAME_CASE_A1_NOT_CERTIFIED')
        template=legacy_factory(**kwargs)
        b=template.bindings
        source_sha=getattr(case,'source_freeze',{}).get('source_sha')
        if source_sha is None and case.evidence_kind!='REAL_DATA':source_sha=digest('NAMED_CURRENT_PLANNING_SOURCE')
        identity=dict(source_sha=source_sha,stage_case_sha=aidc['case_sha'],science_sha=b['science_sha'],
            initial_state_sha=b['initial_state_sha'],time_axis_sha=b['time_axis_sha'],cc4_sha=b['cc4_sha'],runtime_sha=b['runtime_sha'])
        authority=template.reference.identity['CC4_source_authority']
        bridge=PlanningActualResourceBridge(aidc,identity=identity,expected_identity=identity,
            capacities=template.packet.capacities,q50=template.reference.identity['CC4_Q50'],
            q90=template.reference.identity['CC4_Q90'],timing_lower=template.reference.identity['Timing_CDF_Q10'],
            timing_upper=template.reference.identity['Timing_CDF_Q90'],cc4_source_authority=authority,
            begin_seconds=template.reference.begin,required_site_count=12 if case.evidence_kind=='REAL_DATA' else len(template.packet.sites))
        unknown_authority=dict(schema='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1',
            interface_sha=b['interface_sha'],study_case_sha=b['case_sha'],candidate_axis='SOURCE_COMPATIBLE_SITES_ONLY',
            intentional_delay_seconds=0,max_sites=12,Known_commands_modified=False,
            source_customer_SLA_claim=False,source_customer_permission_claim=False,
            authority_scope='USER_AUTHORIZED_UNKNOWN_ALLOCATION_RESEARCH_CASE',Strict_Source_certificate=False,
            Known_corrective_permission_granted=False,Source_release_GPU_rack_grid_compatibility_preserved=True)
        policy=CurrentEventSensitivityPolicy(template.reference,template.packet,bindings=b,expected_bindings=b,
            basic=basic,evidence_scope='REAL_CURRENT_EVENT_NEW_U60' if case.evidence_kind=='REAL_DATA' else 'NAMED_CURRENT_PLANNING',
            source_identity=dict(planning_identity=identity,study_case_sha=b['case_sha']),
            site_authority=unknown_authority,corrective_authority=corrective_authority,
            runtime_repair=runtime_repair,runtime_fixture_gate=runtime_fixture_gate)
        case.research_contract_binding['Unknown_site_authority']=deepcopy(unknown_authority)
        case.research_contract_binding['Unknown_site_authority_sha']=digest(unknown_authority)
        frozen.update(a_result=deepcopy(aidc),planning_identity=identity,policy=policy,resource_bridge=bridge)
        return policy

    def certify_handoff():
        if not frozen:raise ValueError('FINAL_CURRENT_EVENT_A_STAGE_POLICY_NOT_FROZEN')
        if handoff_factory is None:raise ValueError('CURRENT_EVENT_SUPERVISOR_HANDOFF_FACTORY_REQUIRED')
        policy=frozen['policy']
        supplied=handoff_factory(aidc=frozen['a_result'],planning_identity=frozen['planning_identity'],
            frozen_policy=policy,resource_bridge=frozen['resource_bridge'])
        handoff=require_planning_actual_handoff(frozen['a_result'],frozen['planning_identity'],
            supplied['actual_identity'],policy.reference.commands,supplied['observed_state'],
            begin_seconds=policy.reference.begin,planning_slot_zero_seconds=case.planning_slot_zero_seconds)
        frozen['handoff']=handoff
        frozen['supplied']=dict(supplied,planning_identity=frozen['planning_identity'],
            planning_slot_zero_seconds=case.planning_slot_zero_seconds,resource_bridge=frozen['resource_bridge'])
        return frozen['supplied']

    def prepare_actual():
        certify_handoff()
        args,receipt=legacy_prepare()
        receipt.update(controller_contract=CURRENT_EVENT_CONTRACT,current_event_handoff_before_Actual_projection=True,
            diagnostic_FCFS_used=False,future_Known_speculative_GPU_veto=False)
        return args,receipt

    def coordinator_handoff(**kwargs):
        supplied=certify_handoff()
        if (digest(kwargs['aidc'])!=digest(frozen['a_result'])
                or digest(kwargs['commands'])!=digest(frozen['policy'].reference.commands)):
            raise ValueError('CURRENT_EVENT_FINAL_FROZEN_PLANNING_HANDOFF_DRIFT')
        return supplied

    def no_legacy_fallback(**kwargs):
        raise ValueError('CURRENT_EVENT_SUPERVISOR_SAVED_PLANNING_RUNNER_REQUIRED')

    case.control_policy_factory=factory
    case.prepare_research_actual_arguments=prepare_actual
    case.current_event_handoff_factory=coordinator_handoff
    case.unified_actual_runner=no_legacy_fallback
    case.research_contract_binding['active_Actual_controller']=CURRENT_EVENT_CONTRACT
    case.research_contract_binding['legacy_Actual_runner_active']=False
    case.research_contract_binding['independent_handoff_factory_configured']=handoff_factory is not None
    case.research_contract_binding['Current_Actual_global_MILP_calls']=0
    return case


def build_current_event_case(output,*,shared_manifest=None,a_call_cap=10.,m_stage_cap=30.,
        handoff_factory=None,basic=False,corrective_authority=None,runtime_repair=False,runtime_fixture_gate=None):
    """Explicit current research entry; historical factories remain reproducible."""
    from .followup_contract import load_followup_contracts
    from .production_case import build_integration_case,read,ARCHIVE
    from .partial_canary import SOURCE_DIR,source_known_records
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    shared=load_followup_contracts() if shared_manifest is None else shared_manifest
    case=build_integration_case(source_freeze=read(SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        strict_stats=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json',output=output/'CASE',
        initial_state_freeze=SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json',
        a_call_cap=float(a_call_cap),m_stage_cap=float(m_stage_cap))
    records=source_known_records(case.qos_provider,read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json'))
    return bind_current_event_planning(case,records,shared,handoff_factory=handoff_factory,basic=basic,
        corrective_authority=corrective_authority,runtime_repair=runtime_repair,runtime_fixture_gate=runtime_fixture_gate)


def run_b1_prefix_canary(case, final_aidc, *, slots=16, output=None, variants=('C0', 'C2', 'C3'), profile=False):
    """Execute one frozen B1 A1 on the same source boundary in each variant.

    The private Actual bank is consumed only after A1/policy freeze. A prefix
    never certifies Full96, and the source DD initial state remains a declared
    modeled study boundary rather than observed Kestrel placement.
    """
    from .mess_actual import consume_frozen_mess
    if not 0 < slots < 96 or int(slots) != slots:
        raise ValueError('EXPLICIT_PARTIAL_B1_PREFIX_REQUIRED')
    if final_aidc.get('FULL_feasible') is not True:
        raise ValueError('FINAL_B1_A1_FULL_FEASIBILITY_REQUIRED_BEFORE_ACTUAL')
    if not variants or any(v not in ('C0', 'C2', 'C3') for v in variants):
        raise ValueError('B1_PREFIX_BASIC_SIGNED_RUNTIME_VARIANTS_ONLY')
    if case.evidence_kind == 'REAL_DATA' and output is None:
        raise ValueError('B1_REAL_PREFIX_FROZEN_VARIANT_ARTIFACT_DIR_REQUIRED')
    mess = deepcopy(case.initial_mess)
    if any(abs(float(p)) > 1e-12 for field in ('P_by_site', 'Q_by_site') for row in mess[field].values() for p in row):
        raise ValueError('B1_PREFIX_REQUIRES_ORIGINAL_MESS_OFF')
    begin = case.planning_slot_zero_seconds+21600
    end = begin+int(slots)*900
    bindings = dict(case.unified_bindings, aidc_anchor=final_aidc['aidc_anchor'], mess_anchor=mess['plan_sha'])
    case.qos_provider.require_frozen_policy(bindings['qos_sha'])
    mess_receipt = consume_frozen_mess(mess, day_begin_seconds=begin, evidence_kind=case.evidence_kind)
    original_policy = case.control_policy_factory(arm='B1', aidc=final_aidc, mess=mess,
        bindings=bindings, envelope=(), output=output, mess_validation=mess_receipt)
    original_policy.require_bindings(bindings)
    if output is not None:
        output = Path(output); output.mkdir(parents=True, exist_ok=True)
        original_policy.save(output/'FROZEN_B1_A1_SIGNED_POLICY.json')
        frozen = SignedSensitivityPolicy.load(output/'FROZEN_B1_A1_SIGNED_POLICY.json', bindings=bindings)
        frozen.bind_runtime_packet(original_policy.packet)
        if frozen.document != original_policy.document:
            raise ValueError('B1_PREFIX_POLICY_RELOAD_DRIFT')
        original_policy = frozen
    # The method is explicitly deferred by the issue-only binder.
    arguments, projection = case.prepare_research_actual_arguments()
    arguments = dict(arguments, begin=begin, end=end)
    arguments['requests'] = [r for r in arguments['requests'] if r.submit < end]
    if arguments.get('weather') is not None:
        arguments['weather'] = arguments['weather'][:int(slots)]
    commands = deepcopy(original_policy.reference.commands)
    common = dict(bindings=bindings, Known_schedule_sha=digest(commands),
        source_initial_state_sha=bindings['initial_state_sha'], reference_target_sha=original_policy.reference.sha,
        frozen_provider_sha=case.qos_provider.policy_sha,
        boundary_completion_proof_sha=None if arguments.get('boundary_completion_proof') is None
            else arguments['boundary_completion_proof']['proof_sha'],
        observed_prefix_request_UID_sha=digest(sorted(r.uid for r in arguments['requests'])),
        prefix_begin_seconds=begin, prefix_end_seconds=end, prefix_slots=int(slots))
    initial_pending = {r.uid for r in arguments['requests'] if r.submit <= begin}
    initial_running = {r.uid:site for r,site,_ in arguments.get('running', [])}
    modeled_mismatch = dict(
        source_pending_with_past_frozen_command=sorted(u for u in initial_pending
            if u in commands and commands[u]['start_seconds'] < begin),
        source_running_site_differs_from_frozen_plan=sorted(u for u,s in initial_running.items()
            if u in commands and commands[u]['site'] != s))
    results, rows, component_profile = {}, [], None
    for variant in variants:
        policy = SignedSensitivityPolicy(original_policy.reference, original_policy.packet,
            bindings=bindings, expected_bindings=bindings,
            migration_authority=original_policy.migration_authority,
            basic=variant == 'C0', runtime_repair=variant == 'C3', evidence_scope=original_policy.evidence_scope)
        provider = deepcopy(case.qos_provider)
        variant_path = None
        if output is not None:
            variant_path = output/(variant+'_FROZEN_POLICY.json')
            policy.save(variant_path)
            reloaded = SignedSensitivityPolicy.load(variant_path,bindings=bindings)
            reloaded.bind_runtime_packet(policy.packet)
            if reloaded.document != policy.document:
                raise ValueError('B1_PREFIX_VARIANT_POLICY_RELOAD_DRIFT:'+variant)
            policy = reloaded
        if variant == 'C2' and profile:
            component_profile = _profile_prefix_observed_boundary(arguments, original_policy, deepcopy(provider), commands,
                output=None if output is None else output/'C2_OBSERVED_COLD_WARM_COMPONENT_PROFILE.json')
        began = perf_counter()
        result = coordinator_actual_runner(**deepcopy(arguments), arm='B1', qos_window_provider=provider,
            frozen_policy=policy, known_schedule=deepcopy(commands), expected_bindings=bindings)
        results[variant] = result
        admitted = [r for r in result['queue_ledger'] if r['admitted_time'] is not None and r['admitted_time'] >= begin]
        capacity_pass = bool(np.all(result['occupancy_GPU'] <= np.asarray([arguments['capacities'][s]
            for s in result['sites']])+1e-9))
        qos_pass = all(r['total_intentional_burden_seconds'] <= r['budget_seconds']+1e-9
            for r in result['qos_ledger'])
        deadline_pass = all(not r['actual_completion_deadline_excess_seconds']
            for r in result['qos_ledger'])
        conservation = getattr(policy, 'anonymous_residual_audit', {'status':'NO_ANONYMOUS_ALLOCATION_EVALUATION'})
        row = dict(variant=variant, same_input_sha=digest(common), capacity_PASS=capacity_pass,
            executed_frozen_policy_sha=policy.sha,
            frozen_policy_file_sha=None if variant_path is None else hashlib.sha256(variant_path.read_bytes()).hexdigest(),
            original_intentional_QoS_PASS=qos_pass,
            observed_completion_deadline_PASS=deadline_pass,
            admitted_Known_UIDs=sum(not r['origin_unknown'] for r in admitted),
            admitted_Unknown_UIDs=sum(r['origin_unknown'] for r in admitted),
            conservation_status=conservation['status'], wall_seconds=perf_counter()-began,
            decision_P50_seconds=float(np.percentile(policy.times,50)) if policy.times else None,
            decision_P95_seconds=float(np.percentile(policy.times,95)) if policy.times else None,
            Known_schedule_sha=result['carryout']['controller']['tracking_state']['Known_schedule_sha'],
            Native_calls=0, AC_calls=0, Full96='NOT_RUN', Fresh_AC='NOT_RUN')
        if row['Known_schedule_sha'] != common['Known_schedule_sha']:
            raise ValueError('B1_PREFIX_FROZEN_KNOWN_COMMAND_DRIFT')
        rows.append(row)
        if output is not None:
            (output/(variant+'_PREFIX_QUEUE.json')).write_text(json.dumps(result['queue_ledger'], allow_nan=False), encoding='utf-8')
            (output/(variant+'_PREFIX_EVENTS.json')).write_text(json.dumps(result['job_event_ledger'], allow_nan=False), encoding='utf-8')
            np.savez_compressed(output/(variant+'_PREFIX_ACTUAL.npz'), occupancy_GPU=result['occupancy_GPU'],
                PCC_P_kw=None if result['physical'] is None else result['physical']['PCC_P_kw'],
                PCC_Q_kvar=None if result['physical'] is None else result['physical']['PCC_Q_kvar'])
    receipt = dict(common, variants=rows, initial_source_model_deviations=modeled_mismatch,
        source_Dday_state='DECLARED_MODEL_ASSUMPTION_NOT_OBSERVED_KNOWN_QUEUE_REPLAY',
        Known_reference='NEW_ISSUE_ONLY_DDAY_FCFS_REFERENCE_V1',
        Known_reoptimized_at_Actual=False, future_Actual_UIDs_in_Planning=0,
        full96_release_eligible=all(r['capacity_PASS'] and r['original_intentional_QoS_PASS']
            and r['observed_completion_deadline_PASS']
            and r['conservation_status'] in {'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS', 'ZERO_ANONYMOUS_FORECAST'}
            and r['admitted_Known_UIDs'] > 0 and r['admitted_Unknown_UIDs'] > 0 for r in rows),
        Full96='NOT_RUN', Fresh_AC='NOT_RUN', Native_calls=0, AC_calls=0)
    receipt['status'] = 'PREFIX_ALLOCATION_CANARY_PASS_AC_PENDING' if receipt['full96_release_eligible'] else 'PREFIX_CANARY_NOT_PASSED'
    receipt['component_profile'] = component_profile
    if output is not None:
        (output/'B1_PREFIX_COMPARISON.json').write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding='utf-8')
    return dict(receipt=receipt, results=results, frozen_policy=original_policy)


def _profile_prefix_observed_boundary(arguments, original_policy, provider, commands, *, output):
    import heapq
    policy = SignedSensitivityPolicy(original_policy.reference, original_policy.packet,
        bindings=original_policy.bindings, expected_bindings=original_policy.bindings,
        migration_authority=original_policy.migration_authority, evidence_scope=original_policy.evidence_scope)
    c = SensitivityRuntimeController(arguments['capacities'],arm='B1',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=commands,reference=deepcopy(arguments.get('reference')),
        forecast=deepcopy(arguments.get('forecast')),wan_capacities=arguments.get('wan_capacities'),
        boundary_completion_proof=arguments.get('boundary_completion_proof'),boundary_begin_seconds=arguments['begin'])
    now = arguments['begin']
    running = sorted(arguments.get('running',[]),key=lambda r:(r[0].submit,r[0].uid))
    for request,site,start in running:
        if request.uid not in c.reference.assigned:
            c.reference.observe_running(request,site=site,start_seconds=start,event_seconds=now,
                elapsed_compute_seconds=request.metadata.get('elapsed_compute_seconds',now-start))
    for request,site,start in running:
        c.submit(request,now); c.pending.remove((request.submit,request.uid)); heapq.heapify(c.pending)
        c.ledger.start(request.uid,site,now,request.metadata.get('episode_id','OBSERVED:'+request.uid))
        c.ledger.jobs[request.uid]['start_time'] = start
        c.metadata[request.uid].update(state='RUNNING',current_site=site,
            accumulated_compute_seconds=request.metadata.get('elapsed_compute_seconds',now-start))
        c.reservations.retain_running(request.uid,site,now,now+900,request.gpu)
    for request in sorted(arguments['requests'],key=lambda r:(r.submit,r.uid)):
        if request.submit <= now and request.uid not in c.requests:
            c.submit(request,now)
    _bind_driver_current_c1(policy,arguments)
    policy.observe(now,c.ledger.physical(now),c.metadata)
    for _,uid in sorted(c.pending):
        m = c.metadata[uid]
        if not m['origin_unknown']:
            continue
        site = m.get('reference_site',m.get('source_site'))
        segment = [dict(resource='gpu:'+site,begin=now,end=now+max(m['t50_seconds'],1e-9),quantity=m['gpu'])]
        if site in policy.packet.sites and c.reservations.feasible(segment,exclude=uid) is None:
            return profile_observed_decision(policy,m,c.budgets[uid],now,c.reservations,output=output)
    result = dict(status='NO_OBSERVED_CURRENT_RESOURCE_ELIGIBLE_UNKNOWN',actions_executed=False,Native_calls=0,AC_calls=0)
    if output is not None:
        Path(output).write_text(json.dumps(result),encoding='utf-8')
    return result


def profile_observed_decision(policy, metadata, receipt, now, reservations, *, output=None):
    """Cold/warm exact observed candidate profiler; no replay or factory load."""
    import cProfile
    import pstats
    policy.require_bindings(policy.bindings)
    if policy.current is None or policy.current[0] != float(now) or metadata['submit_seconds'] > now:
        raise ValueError('PROFILE_CURRENT_PUBLIC_OBSERVATION_REQUIRED')
    groups = dict(original_affine_rows={'_at_slot'},
        exact_current_C1={'_grid_delta', 'recompute', '_current_weather', 'c1_exact'},
        public_forecast_and_cohort={'_public_future', 'anonymous_cohort_residual', 'load_nominal_service', 'row', 'service_integral'},
        hard_reservations={'feasible', '_fits', 'union_job_segments'},
        current_guard={'current_guard'},
        cache_identity_and_serialization={'digest', 'dumps', 'encode', 'iterencode', 'deepcopy', '_deepcopy_dict', '_deepcopy_list'},
        candidate_generation_and_scoring={'select', '_score', '_record'})
    rows = []
    policy._baseline_grid_cache.clear()
    for phase in ('COLD', 'WARM'):
        hits, misses = policy.baseline_cache_hits, policy.baseline_cache_misses
        profiler = cProfile.Profile(); began = perf_counter()
        profiler.enable()
        decision = policy.select(metadata, receipt, now, reservations, reserve=False)
        profiler.disable()
        stats = pstats.Stats(profiler)
        functions = [dict(file=file, line=line, function=name, primitive_calls=v[0], calls=v[1],
            exclusive_seconds=v[2], cumulative_seconds=v[3]) for (file,line,name),v in stats.stats.items()]
        components = {category:sum(r['exclusive_seconds'] for r in functions if r['function'] in names)
            for category,names in groups.items()}
        affine_calls = sum(r['calls'] for r in functions if r['function'] == '_at_slot')
        baseline_calls = (policy.baseline_cache_misses-misses)*(96-int((now-policy.reference.begin)//900))
        rows.append(dict(phase=phase, wall_seconds=perf_counter()-began, action=decision['action'],
            guard=decision.get('reason', decision['status']), candidate_count=decision['candidate_count'],
            baseline_cache_hits=policy.baseline_cache_hits-hits, baseline_cache_misses=policy.baseline_cache_misses-misses,
            original_affine_total_calls=affine_calls, baseline96_affine_calls=baseline_calls,
            candidate_changed_or_current_guard_affine_calls=affine_calls-baseline_calls,
            exclusive_component_seconds=components,
            unclassified_exclusive_seconds=stats.total_tt-sum(components.values()),
            top_functions=sorted(functions,key=lambda r:r['cumulative_seconds'],reverse=True)[:35]))
    result = dict(bindings=policy.bindings, uid=metadata['uid'], observed_at_seconds=now,
        evidence_scope=policy.evidence_scope, allocation_source_sha=policy.spec['allocation_source_sha'],
        rows=rows, profiler_overhead_included=True, actions_executed=False,
        future_actual_UID_or_weather_read=False, Native_calls=0, AC_calls=0,
        baseline96_and_changedslots_are_same_original_scalar_rows=True)
    if output is not None:
        Path(output).write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return result
