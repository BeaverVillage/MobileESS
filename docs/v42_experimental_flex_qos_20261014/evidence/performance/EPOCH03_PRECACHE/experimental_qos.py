"""Preregistered research contracts; source observations remain separate.

E0 delegates the strict empirical issuer. E1/E2 grant explicitly assumed
additional delay caps, never observed Kestrel SLAs. No future population is
required to decide an observed job's participation.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
import hashlib
import json
import math

from .qos import BudgetReceipt, ObservedJob, QoSWindowProvider, bind_native_job

POLICY_ID = 'V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1'
FROZEN_SEED = POLICY_ID + '::PARTICIPATION_PREREGISTERED_20261014_01'
SLOT_SECONDS = 900
SCENARIOS = {'E0': {'name': 'SOURCE_ONLY_BASELINE', 'normal': 0, 'standby': 0},
             'E1': {'name': 'MODERATE_FLEXIBLE_CONTRACT', 'normal': 1800, 'standby': 3600},
             'E2': {'name': 'EXPANDED_FLEXIBLE_CONTRACT', 'normal': 3600, 'standby': 7200}}
PARTICIPATION = {'FLEX20': 20, 'FLEX30': 30, 'FLEX40': 40}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def participation_for(uid, episode_id=None, *, seed=FROZEN_SEED):
    if not uid or not seed:
        raise ValueError('PREREGISTERED_PUBLIC_IDENTITY_AND_SEED_REQUIRED')
    episode = str(episode_id) if episode_id is not None else str(uid)
    value = digest(dict(rule='UID_EPISODE_SHA256_THRESHOLD_V1', seed=seed,
                        uid=str(uid), episode_id=episode))
    numerator = int(value, 16)
    return dict(uid=str(uid), episode_id=episode, membership_sha=value,
                score=numerator / 2**256,
                membership={key: numerator*100 < percent*2**256
                            for key, percent in PARTICIPATION.items()},
                identity_scope='PUBLIC_UID_EPISODE_ONLY_NO_ORIGIN_STATE_CASE_OR_PERFORMANCE',
                episode_identity='PUBLIC_EPISODE' if episode_id is not None else 'UID_FALLBACK')


@dataclass(frozen=True)
class ExperimentalStatistics:
    manifest: dict

    @property
    def sha(self):
        return digest(self.manifest)

    def to_dict(self):
        return deepcopy(self.manifest)


@dataclass(frozen=True)
class ExperimentalBudgetReceipt(BudgetReceipt):
    scenario: str
    participation: str
    episode_id: str
    membership_sha: str
    participation_score: float
    participant: bool
    eligible_for_contract: bool
    contract_cap_seconds: int
    source_observed_metadata: dict
    model_metadata: dict
    source_context: dict
    assumption_sha: str
    policy_spec_sha: str
    contract_is_observed_SLA: bool


class ExperimentalQoSProvider:
    def __init__(self, strict_provider: QoSWindowProvider, *, scenario='E1', participation='FLEX30',
                 seed=FROZEN_SEED, case_sha=None, provider_sha=None, receipts=None):
        if scenario not in SCENARIOS or participation not in PARTICIPATION or not seed:
            raise ValueError('PREREGISTERED_EXPERIMENTAL_SCENARIO_REQUIRED')
        self.strict = strict_provider
        self.scenario, self.participation, self.seed = scenario, participation, seed
        self.case_sha = case_sha or strict_provider.case_sha
        self.provider_sha = provider_sha or strict_provider.provider_sha
        self.contexts, self.receipts, self._sealed = {}, {}, {}
        spec = dict(policy_id=POLICY_ID, scenario=scenario, **SCENARIOS[scenario],
                    participation=participation, participation_percent=PARTICIPATION[participation],
                    seed=seed, membership_rule='UID_EPISODE_SHA256_THRESHOLD_V1',
                    default_missing_metadata='ASSUMED_NORMAL_BATCH',
                    source_protected_high_urgent_preserved=True, explicit_nonbatch_preserved=True,
                    additional_delay_is_observed_SLA=False, checkpoint_period_seconds=1800,
                    maximum_migrations=1, shared_delay_interruption_budget=True,
                    source_strict_statistics_sha=strict_provider.stats.sha,
                    old_empirical_3600_cap_unchanged=True,
                    new_native_domain_requires_new_case=True,
                    execution_reference='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',
                    original_issue_reference_and_budget_immutable=True,
                    unavoidable_capacity_wait_is_not_intentional_delay=True,
                    cumulative_consumed_budget_never_regranted=True)
        self.stats = strict_provider.stats if scenario == 'E0' else ExperimentalStatistics(spec)
        self.spec = spec
        if scenario == 'E0':
            if (self.case_sha, self.provider_sha) != (strict_provider.case_sha, strict_provider.provider_sha):
                raise ValueError('E0_STRICT_PROVIDER_IDENTITY_MUST_REMAIN_UNCHANGED')
            if receipts is not None:
                raise ValueError('E0_RELOAD_THROUGH_UNCHANGED_STRICT_PROVIDER')
            self.receipts = strict_provider.receipts
            return
        for uid, value in (receipts or {}).items():
            payload = deepcopy(value.to_dict() if isinstance(value, ExperimentalBudgetReceipt) else value)
            claimed = payload.pop('receipt_sha', digest(payload) if isinstance(value, ExperimentalBudgetReceipt) else None)
            if claimed != digest(payload):
                raise ValueError('EXPERIMENTAL_RECEIPT_SHA_MISMATCH')
            payload.update(allowed_starts_seconds=tuple(payload['allowed_starts_seconds']), reasons=tuple(payload['reasons']))
            rec = ExperimentalBudgetReceipt(**payload)
            self._validate_receipt(rec)
            if uid != rec.uid:
                raise ValueError('EXPERIMENTAL_RECEIPT_UID_MISMATCH')
            self.receipts[uid] = rec
            self.contexts[uid] = deepcopy(rec.source_context)
            self._sealed[uid] = digest(rec.to_dict())

    def register_observed(self, uid, *, episode_id=None, source_authority=None):
        """Store context for an already observed UID; issue/select occur later."""
        from .actual import _require_public_metadata
        context = dict(episode_id=None if episode_id is None else str(episode_id),
                       source_authority=deepcopy(source_authority or {}))
        _require_public_metadata(context)
        if not uid:
            raise ValueError('PUBLIC_OBSERVED_UID_REQUIRED')
        if uid in self.contexts and digest(context) != digest(self.contexts[uid]):
            raise ValueError('EXPERIMENTAL_OBSERVED_CONTEXT_CHANGED')
        self.contexts[uid] = context

    @staticmethod
    def _derive(job, context):
        authority = context['source_authority']
        verified = set(authority.get('verified_fields', ()))
        if verified and not authority.get('source_sha'):
            raise ValueError('VERIFIED_FIELD_SOURCE_SHA_REQUIRED')
        if set(verified) - {'qos', 'protected', 'batch_eligible'}:
            raise ValueError('SUPPORTED_PUBLIC_QOS_FIELDS_REQUIRED')
        if authority.get('observed_at_seconds', job.event_seconds) > job.event_seconds:
            raise ValueError('FUTURE_SOURCE_QOS_AUTHORITY')
        explicit_protected = job.protected is True or str(job.qos).lower() in {'high', 'urgent', 'protected'}
        explicit_nonbatch = job.batch_eligible is False
        source_qos = str(job.qos).lower()
        if ('qos' in verified and source_qos not in {'normal','standby','high','urgent','protected'}
                or 'protected' in verified and job.protected is None
                or 'batch_eligible' in verified and job.batch_eligible is None):
            raise ValueError('SOURCE_VERIFIED_FIELD_VALUE_REQUIRED')
        modeled_qos = source_qos if 'qos' in verified and source_qos in {'normal', 'standby'} else 'normal'
        source_classes = []
        if 'qos' in verified:
            source_classes.append('SOURCE_VERIFIED_QOS')
        if 'protected' in verified and job.protected is True:
            source_classes.append('SOURCE_VERIFIED_PROTECTED')
        if not verified:
            source_classes.append('UNSUPPORTED_REQUEST_METADATA')
        eligible = not explicit_protected and not explicit_nonbatch
        assumptions = ['ASSUMED_EXPERIMENTAL_ADDITIONAL_DELAY_CAP']
        if eligible:
            assumptions += ['ASSUMED_EXPERIMENTAL_BATCH_CONTRACT', 'ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT']
        if modeled_qos != source_qos or job.protected is None or job.batch_eligible is None:
            assumptions.append('MISSING_METADATA_DEFAULT_ASSUMED_NORMAL_BATCH')
        if explicit_protected:
            modeled_qos = source_qos if source_qos in {'high', 'urgent'} else 'protected'
        return dict(qos=modeled_qos, protected=explicit_protected,
                    batch_eligible=not explicit_nonbatch,
                    eligible_for_contract=eligible, source_classes=source_classes,
                    assumption_classes=assumptions, raw_fields_unmodified=True,
                    protection_is_modeled_from_source_or_explicit_assumption=True,
                    contract_is_observed_SLA=False)

    def _validate_receipt(self, receipt):
        if (receipt.policy_id != POLICY_ID or receipt.scenario != self.scenario
                or receipt.participation != self.participation or receipt.case_sha != self.case_sha
                or receipt.provider_sha != self.provider_sha or receipt.stats_sha != self.stats.sha
                or receipt.policy_spec_sha != self.stats.sha or receipt.contract_is_observed_SLA):
            raise ValueError('EXPERIMENTAL_RECEIPT_AUTHORITY_MISMATCH')
        membership = participation_for(receipt.uid, receipt.source_context['episode_id'], seed=self.seed)
        model = receipt.model_metadata
        source = deepcopy(receipt.source_observed_metadata)
        source['representation_starts_seconds'] = tuple(source['representation_starts_seconds'])
        observed = ObservedJob(**source)
        expected_model = self._derive(observed, receipt.source_context)
        if (receipt.uid != observed.uid or receipt.authority_sha != observed.authority_sha
                or receipt.reference_start_seconds != observed.reference_start_seconds
                or receipt.t50_seconds != observed.t50_seconds or model != expected_model
                or receipt.eligible_for_contract != model['eligible_for_contract']
                or receipt.allowed_starts_seconds != QoSWindowProvider._window(observed,receipt.latest_start_seconds)
                or receipt.hard_contract_sha != digest(receipt.hard_contract)):
            raise ValueError('EXPERIMENTAL_RECEIPT_PUBLIC_SOURCE_OR_MODEL_MISMATCH')
        cap = SCENARIOS[self.scenario].get(model['qos'], 0)
        expected = cap if receipt.eligible_for_contract and receipt.participant else 0
        if (receipt.membership_sha != membership['membership_sha']
                or receipt.participation_score != membership['score']
                or receipt.participant != membership['membership'][self.participation]
                or receipt.contract_cap_seconds != cap or receipt.budget_seconds != expected
                or receipt.latest_start_seconds != receipt.reference_start_seconds+expected
                or receipt.assumption_sha != digest(dict(spec=self.stats.sha, source=receipt.source_observed_metadata,
                                                         context=receipt.source_context, model=model))):
            raise ValueError('EXPERIMENTAL_RECEIPT_CONTRACT_OR_MEMBERSHIP_MISMATCH')

    def _check_seal(self, receipt):
        if self._sealed.get(receipt.uid) != digest(receipt.to_dict()):
            raise ValueError('EXPERIMENTAL_RECEIPT_MUTATION_OR_FOREIGN_RECEIPT')

    def issue(self, job: ObservedJob, *, episode_id=None, source_authority=None):
        if self.scenario == 'E0':
            return self.strict.issue(job)
        if episode_id is not None or source_authority is not None:
            self.register_observed(job.uid, episode_id=episode_id, source_authority=source_authority)
        context = deepcopy(self.contexts.get(job.uid, dict(episode_id=None, source_authority={})))
        if job.provider_sha and job.provider_sha != self.provider_sha:
            raise ValueError('FROZEN_PROVIDER_MISMATCH')
        if job.uid in self.receipts:
            receipt = self.receipts[job.uid]
            self._check_seal(receipt)
            if receipt.authority_sha != job.authority_sha or digest(context) != digest(receipt.source_context):
                raise ValueError('EXISTING_EXPERIMENTAL_BUDGET_AUTHORITY_CHANGED')
            return receipt
        model = self._derive(job, context)
        member = participation_for(job.uid, context['episode_id'], seed=self.seed)
        participant = member['membership'][self.participation]
        cap = SCENARIOS[self.scenario].get(model['qos'], 0)
        budget = cap if model['eligible_for_contract'] and participant else 0
        source = asdict(job)
        contract = {key: source[key] for key in ('release_seconds','hard_earliest_start_seconds','hard_latest_start_seconds',
            'completion_deadline_seconds','representation_starts_seconds','nominal_service_seconds','provider_sha',
            'reference_sha','batch_eligible','qos','protected','partition','gpu','requested_walltime_seconds')}
        latest = job.reference_start_seconds+budget
        starts = QoSWindowProvider._window(job, latest)
        reasons = tuple(reason for predicate, reason in (
            (not model['eligible_for_contract'], 'SOURCE_PROTECTED_OR_EXPLICIT_NONBATCH'),
            (not participant, 'NOT_SELECTED_PREREGISTERED_PARTICIPATION'),
            (not starts, 'EMPTY_AUTHORIZED_WINDOW')) if predicate)
        status = reasons[0] if reasons else 'EXPERIMENTAL_CONTRACT_AUTHORIZED'
        receipt = ExperimentalBudgetReceipt(uid=job.uid,case_sha=self.case_sha,policy_id=POLICY_ID,
            stats_sha=self.stats.sha,provider_sha=self.provider_sha,reference_sha=job.reference_sha,
            authority_sha=job.authority_sha,issued_at_seconds=job.event_seconds,
            reference_start_seconds=job.reference_start_seconds,reference_wait_seconds=job.reference_start_seconds-job.submit_seconds,
            t50_seconds=job.t50_seconds,empirical_wait_seconds=None,budget_seconds=budget,
            latest_start_seconds=latest,allowed_starts_seconds=starts,cohort_level=None,cohort_n=0,q90_higher_z=None,
            status=status,reasons=reasons,origin_unknown=job.origin_unknown,is_observed=job.is_observed,
            batch_eligible=job.batch_eligible,state_at_issue=job.state,hard_contract=contract,
            hard_contract_sha=digest(contract),scenario=self.scenario,participation=self.participation,
            episode_id=member['episode_id'],membership_sha=member['membership_sha'],participation_score=member['score'],
            participant=participant,eligible_for_contract=model['eligible_for_contract'],contract_cap_seconds=cap,
            source_observed_metadata=source,model_metadata=model,source_context=context,
            assumption_sha=digest(dict(spec=self.stats.sha,source=source,context=context,model=model)),
            policy_spec_sha=self.stats.sha,contract_is_observed_SLA=False)
        self._validate_receipt(receipt)
        self.receipts[job.uid], self.contexts[job.uid] = receipt, context
        self._sealed[job.uid] = digest(receipt.to_dict())
        return receipt

    def allowed_starts(self, job, receipt=None, *, interruption_seconds=0):
        if self.scenario == 'E0':
            return self.strict.allowed_starts(job, receipt, interruption_seconds=interruption_seconds)
        receipt = self.issue(job) if receipt is None else receipt
        self._check_seal(receipt)
        if receipt.uid != job.uid or receipt.authority_sha != job.authority_sha:
            raise ValueError('EXPERIMENTAL_WINDOW_AUTHORITY_MISMATCH')
        if not math.isfinite(interruption_seconds) or interruption_seconds < 0:
            raise ValueError('NONNEGATIVE_INTERRUPTION_REQUIRED')
        if interruption_seconds > receipt.budget_seconds:
            return ()
        return QoSWindowProvider._window(job, receipt.reference_start_seconds+receipt.budget_seconds-interruption_seconds,
                                        interruption_seconds)

    def metadata_overlay(self, job, receipt=None, *, state=None):
        if self.scenario == 'E0':
            return {}
        receipt = self.issue(job) if receipt is None else receipt
        self._check_seal(receipt)
        current_state = job.state if state is None else state
        if current_state not in {'PENDING','RUNNING','COMPLETED'}:
            raise ValueError('OBSERVED_STATE_REQUIRED')
        model = deepcopy(receipt.model_metadata)
        eligible = receipt.participant and receipt.eligible_for_contract
        return dict(qos=model['qos'],protected=model['protected'],batch_eligible=model['batch_eligible'],
            can_prestart_place=eligible and current_state=='PENDING',
            Can_TimeShift=eligible and current_state=='PENDING' and receipt.budget_seconds>0,
            Can_Preplace=eligible and current_state=='PENDING',
            Can_Checkpoint_Migrate=eligible and current_state=='RUNNING',
            experimental_contract=dict(policy_id=POLICY_ID,scenario=self.scenario,participation=self.participation,
                participant=receipt.participant,eligible_for_contract=receipt.eligible_for_contract,
                budget_seconds=receipt.budget_seconds,contract_cap_seconds=receipt.contract_cap_seconds,
                assumption_sha=receipt.assumption_sha,source_classes=model['source_classes'],
                assumption_classes=model['assumption_classes'],contract_is_observed_SLA=False,
                checkpoint_capability='ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT' if eligible else 'NOT_AUTHORIZED',
                physical_migration_packet_required=True,maximum_migrations=1,checkpoint_period_seconds=1800),
            source_observed_qos_metadata=deepcopy(receipt.source_observed_metadata))

    def execution_window(self, job, receipt=None, *, causal_reference_start_seconds,
                         event_seconds, consumed_budget_seconds=0, interruption_seconds=0,
                         reference_proof=None, state=None):
        """Candidate-local window; current physical queue wait cannot renew B.

        The common issuer receipt is never changed. A live controller supplies
        an observed grid-blind feasible reference and cumulative burden before
        this candidate. The returned full B funds the previous burden and the
        candidate's new delay/interruption; remaining B limits this window.
        """
        receipt = self.issue(job) if receipt is None else receipt
        if self.scenario == 'E0':
            document = receipt.to_dict()
            document['allowed_starts_seconds'] = self.strict.allowed_starts(
                replace(job,event_seconds=event_seconds),receipt,
                interruption_seconds=consumed_budget_seconds)
            return document
        self._check_seal(receipt)
        if receipt.uid != job.uid or receipt.authority_sha != job.authority_sha:
            raise ValueError('EXPERIMENTAL_WINDOW_AUTHORITY_MISMATCH')
        current_state = job.state if state is None else state
        if current_state not in {'PENDING','RUNNING','COMPLETED'}:
            raise ValueError('OBSERVED_STATE_REQUIRED')
        values = (causal_reference_start_seconds,event_seconds,consumed_budget_seconds,interruption_seconds)
        if (not all(math.isfinite(float(v)) for v in values) or consumed_budget_seconds<0 or interruption_seconds<0
                or causal_reference_start_seconds<max(job.submit_seconds,event_seconds)
                or causal_reference_start_seconds%SLOT_SECONDS):
            raise ValueError('OBSERVED_CAUSAL_EXECUTION_REFERENCE_REQUIRED')
        from .actual import _require_public_metadata
        proof = deepcopy(reference_proof or {})
        _require_public_metadata(proof)
        if (proof.get('kind')!='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1'
                or proof.get('uid')!=job.uid or proof.get('observed_at_seconds')!=event_seconds
                or proof.get('reference_start_seconds')!=causal_reference_start_seconds):
            raise ValueError('OBSERVED_REFERENCE_PROOF_REQUIRED')
        remaining = max(0,receipt.budget_seconds-consumed_budget_seconds-interruption_seconds)
        latest = causal_reference_start_seconds+remaining
        # Past burden is already reflected in the current absolute clock.
        # Only a proposed future interruption extends this candidate's finish.
        starts = () if consumed_budget_seconds+interruption_seconds>receipt.budget_seconds else QoSWindowProvider._window(
            replace(job,event_seconds=event_seconds),latest,interruption_seconds)
        starts = tuple(t for t in starts if t>=causal_reference_start_seconds)
        document = receipt.to_dict()
        document.update(reference_start_seconds=causal_reference_start_seconds,
            original_reference_start_seconds=receipt.reference_start_seconds,
            allowed_starts_seconds=starts,latest_start_seconds=latest,
            budget_seconds=receipt.budget_seconds,remaining_budget_seconds=remaining,
            cumulative_burden_prior_seconds=consumed_budget_seconds,
            proposed_interruption_seconds=interruption_seconds,
            execution_reference_advance_seconds=causal_reference_start_seconds-receipt.reference_start_seconds,
            unavoidable_queue_wait_seconds=(max(0,causal_reference_start_seconds-receipt.reference_start_seconds-consumed_budget_seconds)
                                            if current_state=='PENDING' else 0),
            issuer_receipt_sha=self._sealed[receipt.uid],reference_proof=proof,reference_proof_sha=digest(proof),
            window_is_candidate_local_not_new_budget=True)
        document['execution_window_sha'] = digest(document)
        return document

    def export_ledger(self):
        if self.scenario == 'E0':
            return self.strict.export_ledger()
        for receipt in self.receipts.values():
            self._check_seal(receipt)
        return {uid:dict(receipt.to_dict(),receipt_sha=digest(receipt.to_dict()))
                for uid,receipt in sorted(self.receipts.items())}

    def to_dict(self):
        if self.scenario == 'E0':
            return self.strict.to_dict()
        return dict(policy_id=POLICY_ID,scenario=self.scenario,participation=self.participation,
                    case_sha=self.case_sha,stats_sha=self.stats.sha,provider_sha=self.provider_sha,
                    research_budget_cap_seconds=max(SCENARIOS[self.scenario][key] for key in ('normal','standby')),
                    slot_seconds=SLOT_SECONDS,manifest=deepcopy(self.spec),receipts=self.export_ledger(),
                    raw_qos_unmodified=True,contract_is_observed_SLA=False,source_only_E0_unchanged=True)


def bind_experimental_native_job(native_job, receipt, *, axis_origin_seconds, axis_start_slot=0,
                                 additional_start_delay_seconds=0, source_can_prestart_place=False,
                                 assumed_checkpoint_authorized=False, migration_physical_authority_sha=''):
    """New contract adapter with explicit120min cap; common validator unchanged."""
    bound = bind_native_job(native_job,receipt,axis_origin_seconds=axis_origin_seconds,
                            axis_start_slot=axis_start_slot,
                            additional_start_delay_seconds=additional_start_delay_seconds)
    if not isinstance(receipt, ExperimentalBudgetReceipt):
        return bound
    if receipt.policy_id != POLICY_ID or receipt.budget_seconds>max(SCENARIOS[receipt.scenario][key] for key in ('normal','standby')):
        raise ValueError('EXPERIMENTAL_NATIVE_CONTRACT_CAP')
    model = receipt.model_metadata
    participating = receipt.participant and receipt.eligible_for_contract
    initial_sites = bound.initial_sites
    if bound.state=='PENDING' and not participating and not source_can_prestart_place:
        initial_sites = (bound.reference_site,)
    if assumed_checkpoint_authorized and not migration_physical_authority_sha:
        raise ValueError('EXPLICIT_MIGRATION_PHYSICAL_AUTHORITY_REQUIRED')
    return replace(bound,qos=model['qos'],protected=model['protected'],batch_eligible=model['batch_eligible'],
                   initial_sites=initial_sites,checkpoint_authorized=bound.checkpoint_authorized or
                   (participating and assumed_checkpoint_authorized))
