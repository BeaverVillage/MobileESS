"""Inference-only Kestrel trace research provider. No fit, job-ID cache, or outcomes."""
from pathlib import Path
from datetime import datetime
import json,hashlib,math
import numpy as np
from features8 import engineer,FORBIDDEN,BASE_RESOURCE
from model8 import Predictor,ordered

def running_proxy(planned_runtime_seconds,observed_elapsed_seconds,still_running,control_interval_seconds=900):
    for x in [planned_runtime_seconds,observed_elapsed_seconds,control_interval_seconds]:
        if not math.isfinite(x) or x<0:raise ValueError('INVALID_DURATION')
    if control_interval_seconds<=0:raise ValueError('POSITIVE_CONTROL_INTERVAL_REQUIRED')
    overrun=bool(still_running and observed_elapsed_seconds>=planned_runtime_seconds)
    return dict(remaining_runtime_proxy_seconds=max(planned_runtime_seconds-observed_elapsed_seconds,0) if still_running else 0.,OVERRUN=overrun,
      retain_GPU=bool(still_running),terminate_job=False,migration_recommendation='STAY',reservation_extend_seconds=control_interval_seconds if overrun else 0,
      future_end_read=False,walltime_as_expected_remaining=False)

class RuntimeProvider:
    def __init__(self,bundle=None,*,allow_research=False):
        self.root=Path(bundle) if bundle else Path(__file__).resolve().parent
        integrity=json.loads((self.root/'BUNDLE_INTEGRITY.json').read_text(encoding='utf-8'))
        for r in integrity['files']:
            if hashlib.sha256((self.root/r['relative']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('PROVIDER_INTEGRITY_FAILURE')
        if not allow_research:raise PermissionError('KESTREL_TRACE_PROXY_RESEARCH_OPT_IN_REQUIRED')
        self.contract=json.loads((self.root/'runtime_contract.json').read_text(encoding='utf-8'))
        self.prep=json.loads((self.root/'preprocessing.json').read_text(encoding='utf-8'));self.model=Predictor.load(self.root/'model')
        self.input_columns=BASE_RESOURCE+['requested_seconds','array_index']+list(self.prep['categorical_mappings'])
    def predict_batch(self,records):
        if not records:raise ValueError('EMPTY_BATCH')
        for r in records:
            if not isinstance(r,dict):raise TypeError('JOB_MAPPING_REQUIRED')
            if FORBIDDEN.intersection(r):raise ValueError('FORBIDDEN_OUTCOME_OR_FUTURE_INPUT')
        # Whitelist projection prevents hidden/unknown keys from entering preprocessing.
        rows=[{k:r.get(k) for k in self.input_columns} for r in records]
        x=engineer(rows,self.prep['categorical_mappings']);p=self.model.predict(x);p[:,1]+=self.contract['calibration_delta_seconds']
        return ordered(p)
    def predict_total(self,job_record,event_time=None):
        if event_time is not None:
            stamp=datetime.fromisoformat(str(event_time).replace('Z','+00:00'))
            if stamp.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
            if job_record.get('submit_time') is not None:
                submit=datetime.fromisoformat(str(job_record['submit_time']).replace('Z','+00:00'))
                if submit.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
                if submit>stamp:raise ValueError('EVENT_BEFORE_SUBMISSION')
        p=self.predict_batch([job_record])[0]
        return dict(q50_seconds=float(p[0]),q90_seconds=float(p[1]),model_version=self.contract['model_version'],feature_contract_version=self.contract['feature_contract_version'],
          provenance_mode='Kestrel_trace_proxy',STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,online_refit_required=False,
          job_id_used=False,prediction_unit='seconds',remaining_semantics='fixed total-minus-elapsed proxy, not conditional survival quantile')
