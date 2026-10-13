"""Explicit empirical research QoS, causal reference and immutable budgets.

TRAIN execution labels are accepted only here. Controllers receive observed
metadata and frozen nominal predictions; no realized duration/completion API is
exposed. Unverified historical accounting remains descriptive evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Iterable, Mapping

POLICY_ID = "EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1"
SLOT_SECONDS = 900
MIN_COHORT_UIDS = 100
MAX_BUDGET_SECONDS = 3600
TRAIN_CUTOFF = "2025-01-01T00:00:00+00:00"
SUPPORTED_REQUEST_PROVENANCES = frozenset({"SUBMISSION_VERSION_VERIFIED", "OBSERVED_EVENT_VERSION_VERIFIED"})
BUCKET_DEFINITION = {"GPU": ["1", "2-4", "5-16", "17-64", "65+"],
                     "requested_walltime": ["<=1h", "1-4h", "4-24h", ">24h"]}


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, ensure_ascii=False).encode()).hexdigest()


def _seconds(value):
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        result = parsed.timestamp()
    if not math.isfinite(result):
        raise ValueError("FINITE_SECONDS_REQUIRED")
    return result


def _bool(value):
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise ValueError("EXPLICIT_PROTECTION_REQUIRED")


def gpu_bucket(gpu):
    if not math.isfinite(float(gpu)) or int(gpu) != float(gpu) or gpu <= 0:
        raise ValueError("POSITIVE_WHOLE_GPU_REQUIRED")
    return "1" if gpu <= 1 else "2-4" if gpu <= 4 else "5-16" if gpu <= 16 else "17-64" if gpu <= 64 else "65+"


def walltime_bucket(seconds):
    if not math.isfinite(float(seconds)) or seconds <= 0:
        raise ValueError("REQUESTED_WALLTIME_REQUIRED")
    return "<=1h" if seconds <= 3600 else "1-4h" if seconds <= 14400 else "4-24h" if seconds <= 86400 else ">24h"


def cohort_keys(qos, protected, partition, gpu, requested_walltime_seconds):
    """Frozen PR75 bucket boundaries; never pool QoS/protection classes."""
    g, w = gpu_bucket(gpu), walltime_bucket(requested_walltime_seconds)
    return ((qos, protected, partition, g, w), (qos, protected, g, w),
            (qos, protected, w), (qos, protected))


@dataclass(frozen=True)
class CohortStatistic:
    level: int
    key: tuple
    n_unique_uids: int
    q90_higher_z: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TrainingStatistics:
    cutoff_seconds: float
    source_sha: str
    cohorts: tuple[CohortStatistic, ...]
    accepted_uids: tuple[str, ...]
    input_rows: int
    exclusions: dict
    descriptive_only: bool = False
    provenance_note: str = "VERIFIED_REQUEST_AND_OBSERVATION_ONLY"

    @classmethod
    def from_records(cls, records: Iterable[Mapping], *, source_sha: str,
                     cutoff=TRAIN_CUTOFF, descriptive_only=False,
                     supported_request_provenances=SUPPORTED_REQUEST_PROVENANCES):
        """Deduplicate identical job-day rows; reject every conflicting UID.

        Descriptive mode accepts PR75 final-accounting proxies, explicitly
        records the missing provenance and cannot be passed to an issuer.
        """
        cutoff_s = _seconds(cutoff)
        exclusions = Counter()
        unique = {}
        conflicts = set()
        count = 0
        for record in records:
            count += 1
            uid = str(record.get("uid", record.get("id", record.get("job_uid", ""))))
            if not uid or uid in {"None", "nan"}:
                exclusions["MISSING_UID"] += 1
                continue
            try:
                submit = _seconds(record.get("submit_seconds", record.get("submit_time")))
                start = _seconds(record.get("start_seconds", record.get("start_time")))
                end = _seconds(record.get("end_seconds", record.get("end_time")))
            except (ValueError, TypeError):
                exclusions["INCOMPLETE_CENSORED_OR_INVALID_TIME"] += 1
                continue
            if not submit <= start < end:
                exclusions["INVALID_TIME_ORDER_OR_ZERO_RUNTIME"] += 1
                continue
            if not end < cutoff_s:
                exclusions["NOT_COMPLETED_BEFORE_CUTOFF"] += 1
                continue
            if record.get("censored") in {True, "True"} or record.get("completed") in {False, "False"}:
                exclusions["CENSORED_OR_INCOMPLETE"] += 1
                continue
            provenance = record.get("request_provenance")
            observed = record.get("observed_at_seconds", record.get("observed_at"))
            if not descriptive_only:
                if provenance not in supported_request_provenances:
                    exclusions["UNSUPPORTED_REQUEST_PROVENANCE"] += 1
                    continue
                try:
                    observed = _seconds(observed)
                except (ValueError, TypeError):
                    exclusions["MISSING_OBSERVATION_TIME"] += 1
                    continue
                if not end <= observed < cutoff_s:
                    exclusions["COMPLETION_NOT_OBSERVED_BEFORE_CUTOFF"] += 1
                    continue
            try:
                protected = _bool(record.get("protected"))
                gpu = float(record.get("gpu", record.get("requested_GPU")))
                wall = float(record.get("requested_walltime_seconds"))
                qos, partition = str(record["qos"]), str(record["partition"])
                if not qos or not partition:
                    raise ValueError("COHORT_METADATA_REQUIRED")
                keys = cohort_keys(qos, protected, partition, gpu, wall)
            except (ValueError, TypeError, KeyError):
                exclusions["INVALID_OR_MISSING_COHORT_METADATA"] += 1
                continue
            z = (start-submit)/max(end-start, SLOT_SECONDS)
            signature = (submit, start, end, keys)
            if uid in unique:
                exclusions["DUPLICATE_UID_ROW"] += 1
                if unique[uid][0] != signature:
                    conflicts.add(uid)
                continue
            unique[uid] = (signature, z, keys)
        for uid in conflicts:
            del unique[uid]
        exclusions["CONFLICTING_UID_EXCLUDED"] = len(conflicts)
        groups = defaultdict(list)
        for _, z, keys in unique.values():
            for level, key in enumerate(keys):
                groups[level, key].append(z)
        cohorts = []
        for (level, key), values in sorted(groups.items(), key=lambda pair: repr(pair[0])):
            values.sort()
            # numpy empirical method='higher': ceil(q*(N-1)).
            q90 = values[math.ceil(.9*(len(values)-1))]
            cohorts.append(CohortStatistic(level, key, len(values), q90))
        return cls(cutoff_s, source_sha, tuple(cohorts), tuple(sorted(unique)), count,
                   dict(exclusions), descriptive_only,
                   "PR75_FINAL_ACCOUNTING_PROXY_REQUEST_VERSION_AND_OBSERVATION_UNVERIFIED"
                   if descriptive_only else "VERIFIED_REQUEST_AND_OBSERVATION_ONLY")

    def select(self, job):
        if self.descriptive_only:
            raise ValueError("DESCRIPTIVE_STATS_HAVE_NO_QOS_AUTHORITY")
        if job.protected is None or job.requested_walltime_seconds is None or not job.partition:
            return None
        indexed = {(row.level, row.key): row for row in self.cohorts}
        for level, key in enumerate(cohort_keys(job.qos, job.protected, job.partition,
                                              job.gpu, job.requested_walltime_seconds)):
            cohort = indexed.get((level, key))
            if cohort is not None and cohort.n_unique_uids >= MIN_COHORT_UIDS:
                return cohort
        return None

    @property
    def sha(self):
        return _sha(self.to_dict())

    def to_dict(self, *, include_uids=False):
        result = dict(policy_id=POLICY_ID, cutoff_seconds=self.cutoff_seconds,
                      source_sha=self.source_sha, bucket_definition=BUCKET_DEFINITION,
                      quantile=.9, quantile_method="higher", normalization="W/max(T,900)",
                      minimum_cohort_unique_uids=MIN_COHORT_UIDS,
                      input_rows=self.input_rows, accepted_unique_uids=len(self.accepted_uids),
                      accepted_uid_sha=_sha(self.accepted_uids), exclusions=self.exclusions,
                      descriptive_only=self.descriptive_only, provenance_note=self.provenance_note,
                      cohorts=[row.to_dict() for row in self.cohorts])
        if include_uids:
            result["uids"] = list(self.accepted_uids)
        return result


@dataclass(frozen=True)
class ObservedJob:
    uid: str
    submit_seconds: float
    event_seconds: float
    reference_start_seconds: float
    t50_seconds: float
    qos: str = "normal"
    protected: bool | None = False
    batch_eligible: bool | None = None
    partition: str = ""
    gpu: int = 1
    requested_walltime_seconds: float | None = 3600
    origin_unknown: bool = False
    is_observed: bool = True
    state: str = "PENDING"
    release_seconds: float | None = None
    hard_earliest_start_seconds: float | None = None
    hard_latest_start_seconds: float | None = None
    completion_deadline_seconds: float | None = None
    representation_starts_seconds: tuple = ()
    nominal_service_seconds: float | None = None
    provider_sha: str = ""
    reference_sha: str = ""

    def __post_init__(self):
        if not self.uid or not self.is_observed or self.submit_seconds > self.event_seconds:
            raise ValueError("INDIVIDUAL_NOT_YET_SUBMITTED")
        times = (self.submit_seconds, self.event_seconds, self.reference_start_seconds, self.t50_seconds)
        if not all(math.isfinite(float(value)) for value in times) or self.t50_seconds < 0:
            raise ValueError("FINITE_NOMINAL_SECONDS_REQUIRED")
        if self.reference_start_seconds < self.submit_seconds:
            raise ValueError("IMPOSSIBLE_REFERENCE_START")
        if self.state not in {"PENDING", "RUNNING", "COMPLETED"}:
            raise ValueError("OBSERVED_STATE_REQUIRED")
        gpu_bucket(self.gpu)
        if self.requested_walltime_seconds is not None:
            walltime_bucket(self.requested_walltime_seconds)
        if (self.protected is not None and type(self.protected) is not bool) or self.batch_eligible not in (True, False, None):
            raise ValueError("EXPLICIT_ACTION_ELIGIBILITY_REQUIRED")
        for name in ("release_seconds", "hard_earliest_start_seconds", "hard_latest_start_seconds",
                     "completion_deadline_seconds", "nominal_service_seconds"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(float(value)):
                raise ValueError("FINITE_CONTRACT_SECONDS_REQUIRED")
        if self.nominal_service_seconds is not None and self.nominal_service_seconds < 0:
            raise ValueError("NEGATIVE_NOMINAL_SERVICE")
        if any(not math.isfinite(float(t)) or float(t)/SLOT_SECONDS != math.floor(float(t)/SLOT_SECONDS)
               for t in self.representation_starts_seconds):
            raise ValueError("CONTROL_GRID_REPRESENTATION_REQUIRED")

    @property
    def authority_sha(self):
        value = asdict(self)
        # State/events advance without granting another research budget.
        for name in ("event_seconds", "state", "origin_unknown", "is_observed"):
            value.pop(name)
        return _sha(value)


@dataclass(frozen=True)
class BudgetReceipt:
    uid: str
    case_sha: str
    policy_id: str
    stats_sha: str
    provider_sha: str
    reference_sha: str
    authority_sha: str
    issued_at_seconds: float
    reference_start_seconds: float
    reference_wait_seconds: float
    t50_seconds: float
    empirical_wait_seconds: float | None
    budget_seconds: int
    latest_start_seconds: float
    allowed_starts_seconds: tuple
    cohort_level: int | None
    cohort_n: int
    q90_higher_z: float | None
    status: str
    reasons: tuple
    origin_unknown: bool
    is_observed: bool
    batch_eligible: bool | None
    state_at_issue: str
    hard_contract: dict
    hard_contract_sha: str

    @property
    def s0(self):
        return self.reference_start_seconds

    def to_dict(self):
        return asdict(self)


class QoSWindowProvider:
    def __init__(self, stats: TrainingStatistics, *, case_sha: str, provider_sha: str,
                 receipts=None):
        if stats.descriptive_only:
            raise ValueError("DESCRIPTIVE_STATS_HAVE_NO_QOS_AUTHORITY")
        if not case_sha or not provider_sha:
            raise ValueError("QOS_CASE_PROVIDER_SHA_REQUIRED")
        self.stats, self.case_sha, self.provider_sha = stats, case_sha, provider_sha
        self.receipts = {}
        for uid, value in (receipts or {}).items():
            if isinstance(value, BudgetReceipt):
                receipt = value
            else:
                payload = dict(value)
                digest = payload.pop("receipt_sha", None)
                if digest != _sha(payload):
                    raise ValueError("QOS_RELOAD_RECEIPT_SHA_MISMATCH")
                payload.update(allowed_starts_seconds=tuple(payload["allowed_starts_seconds"]),
                               reasons=tuple(payload["reasons"]))
                receipt = BudgetReceipt(**payload)
            if (receipt.uid != uid or receipt.case_sha != case_sha or receipt.stats_sha != stats.sha
                    or receipt.provider_sha != provider_sha or receipt.policy_id != POLICY_ID
                    or receipt.budget_seconds not in range(0, MAX_BUDGET_SECONDS+1, SLOT_SECONDS)
                    or receipt.latest_start_seconds != receipt.reference_start_seconds+receipt.budget_seconds):
                raise ValueError("QOS_RELOAD_AUTHORITY_MISMATCH")
            self.receipts[uid] = receipt

    def issue(self, job: ObservedJob):
        if job.provider_sha and job.provider_sha != self.provider_sha:
            raise ValueError("FROZEN_PROVIDER_MISMATCH")
        if job.uid in self.receipts:
            receipt = self.receipts[job.uid]
            if receipt.authority_sha != job.authority_sha:
                raise ValueError("EXISTING_QOS_BUDGET_AUTHORITY_CHANGED")
            return receipt
        cohort = self.stats.select(job)
        wait0 = job.reference_start_seconds-job.submit_seconds
        empirical = None if cohort is None else cohort.q90_higher_z*max(job.t50_seconds, SLOT_SECONDS)
        reasons = []
        if job.protected is not False or job.qos not in {"normal", "standby"}:
            reasons.append("PROTECTION_UNCONFIRMED" if job.protected is None else "PROTECTED_OR_INELIGIBLE_QOS")
        if job.batch_eligible is not True:
            reasons.append("BATCH_ELIGIBILITY_UNCONFIRMED" if job.batch_eligible is None else "NOT_BATCH_ELIGIBLE")
        if cohort is None:
            reasons.append("UNSUPPORTED_COHORT")
        if empirical is not None and wait0 > empirical:
            reasons.append("BASELINE_QOS_EXCESS")
        budget = 0 if reasons else SLOT_SECONDS*math.floor(min(max(0., empirical-wait0), MAX_BUDGET_SECONDS)/SLOT_SECONDS)
        latest = job.reference_start_seconds+budget
        starts = self._window(job, latest)
        if not starts:
            reasons.append("EMPTY_AUTHORIZED_WINDOW")
        contract = {name: getattr(job, name) for name in ("release_seconds", "hard_earliest_start_seconds",
            "hard_latest_start_seconds", "completion_deadline_seconds", "representation_starts_seconds",
            "nominal_service_seconds", "provider_sha", "reference_sha", "batch_eligible",
            "qos", "protected", "partition", "gpu", "requested_walltime_seconds")}
        receipt = BudgetReceipt(job.uid, self.case_sha, POLICY_ID, self.stats.sha, self.provider_sha,
            job.reference_sha, job.authority_sha, job.event_seconds, job.reference_start_seconds,
            wait0, job.t50_seconds, empirical, budget, latest, starts,
            None if cohort is None else cohort.level, 0 if cohort is None else cohort.n_unique_uids,
            None if cohort is None else cohort.q90_higher_z,
            "EMPTY_AUTHORIZED_WINDOW" if not starts else reasons[0] if reasons else "AUTHORIZED", tuple(reasons),
            job.origin_unknown, True, job.batch_eligible, job.state, contract, _sha(contract))
        self.receipts[job.uid] = receipt
        return receipt

    @staticmethod
    def _window(job, latest, interruption_seconds=0):
        if interruption_seconds < 0 or not math.isfinite(interruption_seconds):
            raise ValueError("NONNEGATIVE_INTERRUPTION_REQUIRED")
        lower = max(job.submit_seconds, job.event_seconds,
                    job.release_seconds if job.release_seconds is not None else -math.inf,
                    job.hard_earliest_start_seconds if job.hard_earliest_start_seconds is not None else -math.inf)
        upper = min(latest, job.hard_latest_start_seconds if job.hard_latest_start_seconds is not None else math.inf)
        if job.completion_deadline_seconds is not None:
            service = job.t50_seconds if job.nominal_service_seconds is None else job.nominal_service_seconds
            upper = min(upper, job.completion_deadline_seconds-service-interruption_seconds)
        # The model's finite representation is a ceiling, never permission.
        return tuple(sorted(set(t for t in job.representation_starts_seconds if lower <= t <= upper)))

    def allowed_starts(self, job, receipt=None, *, interruption_seconds=0):
        receipt = self.issue(job) if receipt is None else receipt
        if receipt.case_sha != self.case_sha or receipt.uid != job.uid or receipt.authority_sha != job.authority_sha:
            raise ValueError("QOS_WINDOW_AUTHORITY_MISMATCH")
        # Same B funds starts and all migration pause components.
        latest = receipt.reference_start_seconds+max(0, receipt.budget_seconds-interruption_seconds)
        if interruption_seconds > receipt.budget_seconds:
            return ()
        return self._window(job, latest, interruption_seconds)

    def export_ledger(self):
        return {uid: dict(receipt.to_dict(), receipt_sha=_sha(receipt.to_dict()))
                for uid, receipt in sorted(self.receipts.items())}

    def to_dict(self):
        return dict(policy_id=POLICY_ID, case_sha=self.case_sha, stats_sha=self.stats.sha,
                    provider_sha=self.provider_sha, receipts=self.export_ledger(),
                    research_budget_cap_seconds=MAX_BUDGET_SECONDS, slot_seconds=SLOT_SECONDS,
                    nominal_provider_frozen=True, retrospective_labels_in_controller=False)


def receipt_slot_domain(receipt: BudgetReceipt, *, axis_origin_seconds=0., axis_start_slot=0):
    """Explicit seconds->native slot-axis mapping; never assume [24,120)."""
    slots = []
    for seconds in receipt.allowed_starts_seconds:
        position = (seconds-axis_origin_seconds)/SLOT_SECONDS+axis_start_slot
        if not math.isfinite(position) or position != math.floor(position):
            raise ValueError("QOS_NATIVE_AXIS_NOT_ALIGNED")
        slots.append(int(position))
    return tuple(slots)


def bind_native_job(native_job, receipt: BudgetReceipt, *, axis_origin_seconds,
                    axis_start_slot=0, additional_start_delay_seconds=0):
    """Bind the issuer to the original A-domain dataclass and FULL validator.

    A RUNNING native Job represents remaining service at its event boundary;
    preserving that origin is continuation, not permission to restart history.
    Its actual historical start and already incurred delay remain in ledgers.
    """
    if native_job.uid != receipt.uid:
        raise ValueError("NATIVE_QOS_UID_MISMATCH")
    if not 0 <= additional_start_delay_seconds <= receipt.budget_seconds:
        raise ValueError("QOS_SHARED_BUDGET_EXCEEDED")
    starts = receipt_slot_domain(receipt, axis_origin_seconds=axis_origin_seconds,
                                 axis_start_slot=axis_start_slot)
    if native_job.state == "RUNNING":
        starts = (native_job.reference_start,)
        reference_start=native_job.reference_start
    else:
        reference=(receipt.reference_start_seconds-axis_origin_seconds)/SLOT_SECONDS+axis_start_slot
        if reference!=int(reference):raise ValueError('CAUSAL_REFERENCE_NATIVE_CONTROL_GRID')
        reference_start=int(reference)
    return replace(native_job, qos_policy_id=receipt.policy_id,
                   qos_receipt_sha=_sha(receipt.to_dict()), qos_allowed_starts=starts,
                   qos_budget_seconds=receipt.budget_seconds,
                   reference_start=reference_start,
                   qos_start_delay_seconds=additional_start_delay_seconds,
                   is_observed=receipt.is_observed)


@dataclass
class CausalReferenceScheduler:
    """Grid-blind strict FIFO shadow using PR125 Request and nominal Q50.

    Reservations release at nominal grid boundaries. Realized completion events
    are never inputs. Only already submitted requests may enter this shadow.
    """
    capacities: dict
    reference_sha: str
    reservations: dict = field(default_factory=dict)
    assigned: dict = field(default_factory=dict)
    last_event_seconds: float = -math.inf
    last_pending_start_seconds: float = -math.inf

    def __post_init__(self):
        if not self.reference_sha or not self.capacities or any(type(c) is not int or c <= 0 for c in self.capacities.values()):
            raise ValueError("REFERENCE_CAPACITY_AND_SHA_REQUIRED")
        self.reservations = {s: list(self.reservations.get(s, [])) for s in sorted(self.capacities)}

    def observe_running(self, request, *, site, start_seconds, event_seconds, elapsed_compute_seconds):
        """Observed initial occupancy retains its immutable historical start."""
        if request.submit > event_seconds or site not in request.compatible or site not in self.capacities:
            raise ValueError("OBSERVED_RUNNING_AUTHORITY_REQUIRED")
        if (not all(math.isfinite(x) for x in (start_seconds, event_seconds, elapsed_compute_seconds, request.q50))
                or start_seconds > event_seconds or elapsed_compute_seconds < 0 or request.q50 < 0
                or request.gpu <= 0 or int(request.gpu) != request.gpu):
            raise ValueError("INVALID_RUNNING_HISTORY")
        if request.uid in self.assigned:
            raise ValueError("DUPLICATE_REFERENCE_UID")
        if event_seconds < self.last_event_seconds:
            raise ValueError("NONCAUSAL_REFERENCE_EVENT")
        if request.source_site is not None and request.source_site != site:
            raise ValueError("RUNNING_SOURCE_SITE_CHANGED")
        if request.gpu + sum(g for a, b, g in self.reservations[site] if a <= event_seconds < b) > self.capacities[site]:
            raise ValueError("RUNNING_INITIAL_CAPACITY_UNAVAILABLE")
        remaining = max(0., request.q50-elapsed_compute_seconds)
        end = SLOT_SECONDS*math.ceil((event_seconds+remaining)/SLOT_SECONDS)
        # A currently observed RUNNING gang remains hard at this control
        # boundary even when the nominal predictor has expired. This is a
        # reservation of the current grid slot, not invented compute service.
        end = max(end, SLOT_SECONDS*(math.floor(event_seconds/SLOT_SECONDS)+1))
        self.reservations[site].append((event_seconds, end, request.gpu))
        self.assigned[request.uid] = dict(uid=request.uid, reference_start_seconds=start_seconds,
            reference_site=site, nominal_release_seconds=end, origin="OBSERVED_RUNNING", reference_sha=self.reference_sha)
        self.last_event_seconds = event_seconds
        return self.assigned[request.uid]

    def submit(self, request, *, event_seconds):
        if request.submit > event_seconds:
            raise ValueError("INDIVIDUAL_NOT_YET_SUBMITTED")
        if event_seconds < self.last_event_seconds:
            raise ValueError("NONCAUSAL_REFERENCE_EVENT")
        if request.uid in self.assigned:
            prior = self.assigned[request.uid]
            if prior.get("request_sha") != _sha(asdict(request)):
                raise ValueError("REFERENCE_REQUEST_CHANGED")
            return prior
        if not math.isfinite(request.q50) or request.q50 < 0 or request.gpu <= 0 or int(request.gpu) != request.gpu:
            raise ValueError("NOMINAL_REFERENCE_REQUEST_REQUIRED")
        self.last_event_seconds = event_seconds
        eligible = sorted(s for s in request.compatible if s in self.capacities and request.gpu <= self.capacities[s]
                          and (request.source_site is None or request.source_site == s))
        earliest = SLOT_SECONDS*math.ceil(max(event_seconds, request.submit, self.last_pending_start_seconds)/SLOT_SECONDS)
        candidates = sorted({earliest} | {b for s in eligible for a, b, g in self.reservations[s] if b >= earliest})
        def fits(site, start):
            end = SLOT_SECONDS*math.ceil((start+request.q50)/SLOT_SECONDS)
            checkpoints = {start} | {a for a, b, g in self.reservations[site] if start < a < end}
            return all(request.gpu+sum(g for a, b, g in self.reservations[site] if a <= t < b) <= self.capacities[site]
                       for t in checkpoints)
        selected = next(((t, s) for t in candidates for s in eligible if fits(s, t)), None)
        if selected is None:
            raise ValueError("CAUSAL_REFERENCE_CAPACITY_UNAVAILABLE")
        start, site = selected
        release = SLOT_SECONDS*math.ceil((start+request.q50)/SLOT_SECONDS)
        self.reservations[site].append((start, release, request.gpu))
        self.last_pending_start_seconds = start
        receipt = dict(uid=request.uid, reference_start_seconds=start, reference_site=site,
                       nominal_release_seconds=release, origin="CAUSAL_REFERENCE_START",
                       reference_sha=self.reference_sha, request_sha=_sha(asdict(request)),
                       grid_reads=0, realized_completion_reads=0, solver_calls=0)
        self.assigned[request.uid] = receipt
        return receipt

    def submit_batch(self, requests, *, event_seconds):
        return [self.submit(r, event_seconds=event_seconds) for r in sorted(requests, key=lambda r: (r.submit, r.uid))]

    def to_dict(self):
        value = asdict(self)
        for name in ("last_event_seconds", "last_pending_start_seconds"):
            if not math.isfinite(value[name]):
                value[name] = None
        return value

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        for name in ("last_event_seconds", "last_pending_start_seconds"):
            if value.get(name) is None:
                value[name] = -math.inf
        return cls(**value)
