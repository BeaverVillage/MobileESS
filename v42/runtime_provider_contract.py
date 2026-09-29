"""Unbound V42 runtime interface. No estimator, training or walltime fallback.

An external runtime authority must supply approved persisted model state before
an implementation can return a scheduling duration. Truth is not an input.
"""
from dataclasses import dataclass, field
from datetime import datetime
import math
from .semantic_adapter import SubmissionSemanticPayload, SubmissionSemanticRecord, VERSION

SUBMISSION_FEATURES=frozenset({'requested_seconds','num_gpus_req','num_nodes_req',
    'num_cores_req','requested_memory_mib','partition','qos','submit_hour','submit_dow'})

def instant(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return result

@dataclass(frozen=True)
class SubmissionRuntimeRequest:
    job_uid: str
    submit_time: str
    requested_seconds: float
    features: dict
    feature_observed_at: dict
    source_sha256: str
    request_version_authority: str = 'UNVERIFIED'
    semantic_payload: SubmissionSemanticPayload | None = field(default=None, repr=False)
    semantic_observed_at: str | None = None
    semantic_feature_version: str | None = None

    def validate(self,event_time):
        event=instant(event_time)
        if instant(self.submit_time)>event:raise ValueError('NOT_SUBMITTED')
        if not math.isfinite(self.requested_seconds) or self.requested_seconds<=0:
            raise ValueError('INVALID_REQUESTED_WALLTIME')
        if len(self.source_sha256)!=64:raise ValueError('SOURCE_HASH_REQUIRED')
        if set(self.features)-SUBMISSION_FEATURES:raise ValueError('UNAUTHORIZED_OR_TRUTH_FEATURE')
        if set(self.features)!=set(self.feature_observed_at):raise ValueError('FEATURE_AVAILABILITY_RECEIPT_REQUIRED')
        if any(instant(t)>event for t in self.feature_observed_at.values()):raise ValueError('FUTURE_FEATURE')
        if 'requested_seconds' in self.features and self.features['requested_seconds']!=self.requested_seconds:
            raise ValueError('REQUESTED_WALLTIME_MISMATCH')
        if self.semantic_payload is not None:
            if self.semantic_feature_version != VERSION or self.semantic_observed_at is None:
                raise ValueError('SEMANTIC_SUBMISSION_RECEIPT_REQUIRED')
            SubmissionSemanticRecord(self.job_uid,self.submit_time,self.semantic_observed_at,
                                     self.semantic_payload).validate(event_time)

    def semantic_record(self):
        if self.semantic_payload is None:return None
        return SubmissionSemanticRecord(self.job_uid,self.submit_time,self.semantic_observed_at,self.semantic_payload)

@dataclass(frozen=True)
class RuntimeEstimate:
    available: bool
    estimate_seconds: float | None
    model_version: str | None
    semantics: str
    feature_timestamp: str
    feature_availability_receipt: dict
    requested_seconds: float
    requested_walltime_role: str
    fallback_reason: str

class UnboundRuntimeProvider:
    """Explicitly unavailable; callers must stop, not reserve requested walltime."""
    def _missing(self,job,event_time,reason):
        job.validate(event_time)
        return RuntimeEstimate(False,None,None,'UNAVAILABLE_NO_QUANTILE_OR_SAFE_DURATION_CLAIM',
            event_time,dict(observed_at=dict(job.feature_observed_at),source_sha256=job.source_sha256,
                request_version_authority=job.request_version_authority),
            job.requested_seconds,'FEATURE_ONLY_NO_PREDICTION_NO_CAP_APPLIED',reason)

    def predict_total_runtime(self,job,issue_time):
        return self._missing(job,issue_time,'APRIL_UNKNOWN_TOTAL_RUNTIME_MODEL_UNAVAILABLE')

    def predict_remaining_runtime(self,job,elapsed_seconds,event_time):
        if not math.isfinite(elapsed_seconds) or elapsed_seconds<0:raise ValueError('INVALID_CAUSAL_ELAPSED')
        return self._missing(job,event_time,'NO_PRODUCTION_AUTHORIZED_SURVIVAL_CONDITIONED_REMAINING_MODEL')
