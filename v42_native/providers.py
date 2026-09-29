"""Strict provider interfaces; no model, oracle, requested-walltime substitution."""
from dataclasses import dataclass
from typing import Protocol
from math import isfinite
from .contracts import require

FEATURES=frozenset(('requested_seconds','num_gpus_req','num_nodes_req','num_cores_req',
    'requested_memory_mib','partition','qos','submit_hour','submit_dow'))


@dataclass(frozen=True)
class JobRequest:
    uid:str
    submit_time:float
    features:dict
    observed_at:dict
    source_sha256:str

    def validate(self,event_time):
        require(self.submit_time<=event_time and len(self.source_sha256)==64,'SUBMISSION_LINEAGE')
        require(set(self.features)<=FEATURES and set(self.features)==set(self.observed_at),'UNAUTHORIZED_RUNTIME_FEATURE')
        require(all(t<=event_time for t in self.observed_at.values()),'FUTURE_RUNTIME_FEATURE')


@dataclass(frozen=True)
class Quantiles:
    q50:float|None
    q90:float|None
    model_version:str|None
    provenance:dict
    status:str='UNPROMOTED'

    def require_production(self,event_time):
        require(self.status=='PROMOTED' and self.model_version is not None,'RUNTIME_PROVIDER_UNPROMOTED')
        require(self.q50 is not None and self.q90 is not None and 0<self.q50<=self.q90 and isfinite(self.q90),'RUNTIME_QUANTILES')
        require(self.provenance.get('training_cutoff',float('inf'))<=event_time and self.provenance.get('frozen_at',float('inf'))<=event_time
            and len(self.provenance.get('artifact_sha256',''))==64 and self.provenance.get('optimizer_use_allowed') is True,'RUNTIME_PROVENANCE')


class RuntimeProvider(Protocol):
    def predict_total(self,job:JobRequest,event_time:float)->Quantiles:...
    def predict_remaining(self,job:JobRequest,elapsed_seconds:float,event_time:float)->Quantiles:...


class UnpromotedRuntime:
    def predict_total(self,job,event_time):
        job.validate(event_time)
        return Quantiles(None,None,None,{'source_sha256':job.source_sha256,'reason':'NO_PROMOTED_PERSISTED_PROVIDER'})
    def predict_remaining(self,job,elapsed_seconds,event_time):
        require(isfinite(elapsed_seconds) and elapsed_seconds>=0,'CAUSAL_ELAPSED')
        return self.predict_total(job,event_time)


@dataclass(frozen=True)
class FrozenCC4:
    q50:tuple
    q90:tuple
    frozen_at:float
    authority_sha256:str
    promoted:bool

    def validate(self,issue_time):
        require(self.promoted and self.frozen_at<=issue_time and len(self.authority_sha256)==64,'CC4_BASELINE_UNBOUND')
        require(len(self.q50)==len(self.q90)==24 and all(isfinite(a) and isfinite(b) and 0<=a<=b for a,b in zip(self.q50,self.q90)),'CC4_AXIS')
        return 'SAME_HOUR_NOMINAL_AND_UNCERTAINTY_ENVELOPE_NO_BACKLOG_SHIFT'
