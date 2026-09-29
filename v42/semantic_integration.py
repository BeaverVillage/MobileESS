"""Feature availability is independent of model validation and scheduling authority."""
from dataclasses import replace
from .semantic_adapter import SubmissionSemanticCache, ENABLE_SUBMISSION_SEMANTICS
from .semantic_state import submission_state

class FrozenSemanticClusters:
    """Inference-only KMeans8 centers; require an independently frozen file digest."""
    def __init__(self,path,expected_sha256):
        import hashlib
        from pathlib import Path
        import numpy as np
        path=Path(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha256:
            raise ValueError('CLUSTER_BUNDLE_INTEGRITY_FAILURE')
        self.centers=np.load(path,allow_pickle=False)
        if self.centers.shape!=(8,32) or not np.isfinite(self.centers).all():
            raise ValueError('INVALID_CLUSTER_CENTERS')

    def predict(self,sem):
        import numpy as np
        x=np.asarray(sem)
        if x.ndim!=2 or x.shape[1]!=32 or not np.isfinite(x).all():
            raise ValueError('INVALID_CLUSTER_INPUT')
        return np.argmin(np.sum((x[:,None,:]-self.centers[None,:,:])**2,axis=2),axis=1)

class SemanticArrivalAdapter:
    """Existing validated runtime duration must already be present on policy Arrival."""
    def __init__(self,adapter,enabled=ENABLE_SUBMISSION_SEMANTICS):
        self.cache=SubmissionSemanticCache(adapter,enabled)

    def attach(self,runtime_request,arrival,event_time):
        runtime_request.validate(event_time);arrival.validate()
        if runtime_request.job_uid!=arrival.uid:raise ValueError('JOB_IDENTITY_MISMATCH')
        if not self.cache.enabled or runtime_request.semantic_payload is None:return arrival
        numeric=self.cache.on_submit(runtime_request.semantic_record(),event_time)
        return replace(arrival,semantic_features=numeric)

    def running(self,job_uid):return self.cache.running(job_uid)

def require_selected_model(selection,component):
    """Research flags and finite outputs are never proof of a validated model."""
    if component not in ('RUNTIME','CC4'):raise ValueError('UNKNOWN_COMPONENT')
    if not selection.get(component+'_SEMANTIC_MODEL_SELECTED',False):
        raise ValueError('SEMANTIC_MODEL_NOT_SELECTED')
    if not selection.get(component+'_ALL_FROZEN_GATES_PASS',False):
        raise ValueError('SEMANTIC_MODEL_GATE_FAILURE')

def cc4_augmented_input(base_features,adapter,observed_records,issue_time,*,
                        cluster_model=None,enabled=ENABLE_SUBMISSION_SEMANTICS):
    """Build research inputs only. Prediction/scheduling separately requires selection."""
    if not enabled:return base_features
    import numpy as np
    if np.asarray(base_features).ndim!=2:raise ValueError('CC4_SLOT_FEATURE_MATRIX_REQUIRED')
    state,_,_=submission_state(adapter,observed_records,issue_time,cluster_model)
    return np.concatenate([base_features,np.repeat(state[None,:],len(base_features),axis=0)],axis=1)
