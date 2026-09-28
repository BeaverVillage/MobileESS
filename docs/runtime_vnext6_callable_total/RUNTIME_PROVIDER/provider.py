"""Frozen inference-only total runtime provider; contains no fitting or cache lookup."""
from pathlib import Path
from datetime import datetime
import json,hashlib,math
import numpy as np
import lightgbm as lgb

def _timestamp(value):
    t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return t

class RuntimeProvider:
    def __init__(self,bundle=None,*,allow_research=False):
        self.root=Path(bundle) if bundle else Path(__file__).resolve().parent
        self.contract=json.loads((self.root/'runtime_contract.json').read_text(encoding='utf-8'))
        integrity=json.loads((self.root/'BUNDLE_INTEGRITY.json').read_text(encoding='utf-8'))
        for row in integrity['files']:
            p=self.root/row['relative']
            if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('BUNDLE_HASH_MISMATCH')
        if not self.contract['optimizer_use_allowed'] and not allow_research:raise PermissionError('RUNTIME_PROVIDER_NOT_PROMOTED_RESEARCH_ONLY')
        # Python Unicode path handling avoids native LightGBM Windows fopen limitations.
        self.boosters=[lgb.Booster(model_str=(self.root/f'Q{q}.txt').read_text(encoding='utf-8')) for q in [50,90]]
        self.preprocess=json.loads((self.root/'preprocessing.json').read_text(encoding='utf-8'))
        self.bundle_hash=hashlib.sha256((self.root/'BUNDLE_INTEGRITY.json').read_bytes()).hexdigest()

    def _features(self,n):return np.full((n,1),self.preprocess['constant'],dtype=np.float64)

    def predict_array(self,n):
        if not isinstance(n,int) or n<1:raise ValueError('POSITIVE_BATCH_SIZE_REQUIRED')
        x=self._features(n);p=np.column_stack([b.predict(x,num_threads=1) for b in self.boosters])
        if self.contract['inverse_transform']=='expm1':p=np.expm1(p)
        p[:,1]+=self.contract['Q90_signed_calibration_delta_seconds']
        return np.maximum.accumulate(np.maximum(p,0),axis=1)

    def predict_total(self,job,event_time):
        if not isinstance(job,dict):raise TypeError('JOB_MAPPING_REQUIRED')
        t=_timestamp(event_time)
        forbidden={'start_time','end_time','runtime_seconds','actual_runtime','queue_wait','completion_status','utilization','state'}
        if forbidden.intersection(job):raise ValueError('FORBIDDEN_FUTURE_OR_STATE_FIELDS')
        if 'submit_time' in job and _timestamp(job['submit_time'])>t:raise ValueError('EVENT_BEFORE_SUBMISSION')
        p=self.predict_array(1)[0];w=job.get('requested_seconds',job.get('requested_walltime_seconds'))
        try:w=float(w) if w is not None else None
        except (TypeError,ValueError):w=None
        if w is not None and (not math.isfinite(w) or w<=0):w=None
        return dict(q50_seconds=float(p[0]),q90_seconds=float(p[1]),planned_runtime_seconds=float(p[1]),requested_walltime_seconds=w,
          model_version=self.contract['model_version'],feature_timestamp=t.isoformat(),
          feature_receipt=dict(feature_order=['constant_bias'],values=[1.],job_fields_consumed=[],job_id_used=False,
            request_version_sensitive_fields_consumed=[],source='DETERMINISTIC_CONSTANT',bundle_sha256=self.bundle_hash,
            request_metadata_echo_verified=False),fallback_reason='RESEARCH_ONLY_GATES_NOT_PASSED',optimizer_use_allowed=False)

def running_proxy(planned_runtime_seconds,observed_elapsed_seconds,still_running,control_interval_seconds=900):
    for x in [planned_runtime_seconds,observed_elapsed_seconds,control_interval_seconds]:
        if not math.isfinite(x) or x<0:raise ValueError('INVALID_DURATION')
    if control_interval_seconds==0:raise ValueError('POSITIVE_CONTROL_INTERVAL_REQUIRED')
    overrun=bool(still_running and observed_elapsed_seconds>=planned_runtime_seconds)
    return dict(remaining_runtime_proxy_seconds=max(planned_runtime_seconds-observed_elapsed_seconds,0) if still_running else 0.,
      OVERRUN=overrun,retain_GPU=bool(still_running),terminate_job=False,migration_recommendation='STAY',
      reservation_extend_seconds=control_interval_seconds if overrun else 0,
      reservation_until_elapsed_seconds=observed_elapsed_seconds+control_interval_seconds if overrun else planned_runtime_seconds if still_running else observed_elapsed_seconds,
      future_end_read=False,walltime_as_expected_remaining=False)
