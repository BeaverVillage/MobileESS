"""CPU research provider; inference never reads completion truth or job-ID tables."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import hashlib,json,math
import numpy as np
from features8 import engineer,FORBIDDEN,BASE_RESOURCE
from distribution9 import Distribution

def stamp(value):
    t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return t.astimezone(timezone.utc)
def residual_delta(values):
    a=np.asarray(values,float)
    if len(a)<200:return 0.
    k=min(math.ceil(.9*(len(a)+1)),len(a))-1
    return float(np.partition(a,k)[k])
class RuntimeProvider:
    def __init__(self,bundle=None,*,allow_research=False):
        self.root=Path(bundle) if bundle else Path(__file__).resolve().parent
        if not allow_research:raise PermissionError('KESTREL_TRACE_PROXY_RESEARCH_OPT_IN_REQUIRED')
        integrity=json.loads((self.root/'BUNDLE_INTEGRITY.json').read_text(encoding='utf-8'))
        for r in integrity['files']:
            if hashlib.sha256((self.root/r['relative']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('PROVIDER_INTEGRITY_FAILURE')
        self.contract=json.loads((self.root/'runtime_contract.json').read_text(encoding='utf-8'))
        self.prep=json.loads((self.root/'preprocessing.json').read_text(encoding='utf-8'))
        self.model=Distribution.load(self.root/'model')
        self.input_columns=BASE_RESOURCE+['requested_seconds','array_index']+list(self.prep['categorical_mappings'])
        self.residuals=[(stamp(r['end_time']),float(r['residual'])) for r in self.contract['initial_residuals']]
        self.available=stamp(self.contract['available_from']);self.last_event=self.available
    def _rows(self,records):
        if not records:raise ValueError('EMPTY_BATCH')
        for r in records:
            if not isinstance(r,dict):raise TypeError('JOB_MAPPING_REQUIRED')
            if (FORBIDDEN|{'event','censored','duration_lower','duration_upper','label_valid'}).intersection(r):raise ValueError('FORBIDDEN_OUTCOME_OR_FUTURE_INPUT')
        return [{k:r.get(k) for k in self.input_columns} for r in records]
    def _time(self,event_time,records=()):
        t=self.available if event_time is None else stamp(event_time)
        if t<self.available:raise ValueError('EVENT_BEFORE_MODEL_AVAILABLE')
        for r in records:
            if r.get('submit_time') is not None and stamp(r['submit_time'])>t:raise ValueError('EVENT_BEFORE_SUBMISSION')
        return t
    def _delta(self,event_time):
        mode=self.contract['calibration_mode']
        if mode=='NONE':return 0.
        if mode=='STATIC14':return float(self.contract['static_delta'])
        t=event_time.replace(hour=0,minute=0,second=0,microsecond=0);lo=t-timedelta(days=int(mode.replace('ROLLING','')))
        return residual_delta([r for end,r in self.residuals if lo<=end<t])
    def parameters(self,records):
        x=engineer(self._rows(records),self.prep['categorical_mappings'])
        return self.model.parameters(x)
    def predict_batch(self,records,event_time=None):
        t=self._time(event_time,records);par=self.parameters(records);return self.model.quantiles(par,self._delta(t),quantiles=(.5,.9))
    def predict_total(self,job_record,event_time=None):
        t=self._time(event_time,[job_record]);p=self.predict_batch([job_record],t)[0]
        return dict(q50_total_seconds=float(p[0]),q90_total_seconds=float(p[1]),distribution_metadata=dict(family=self.model.meta['kind'],
            arm=self.model.meta['arm'],calibration_mode=self.contract['calibration_mode'],shift_seconds=self._delta(t),conditional_method='log S(e+r)-log S(e)',
            unknown_category_code=0,walltime_cap=False),model_version=self.contract['model_version'],feature_contract_version=self.contract['feature_contract_version'],
            provenance_mode='Kestrel_trace_proxy',STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,job_id_used=False,online_refit_required=False)
    def predict_remaining(self,job_record,elapsed_seconds,event_time=None):
        if not isinstance(elapsed_seconds,(int,float)) or not math.isfinite(elapsed_seconds) or elapsed_seconds<0:raise ValueError('INVALID_ELAPSED')
        t=self._time(event_time,[job_record]);par=self.parameters([job_record])
        q,s,logs=self.model.remaining(par,elapsed_seconds,self._delta(t))
        return dict(q50_remaining_seconds=float(q[0,0]),q90_remaining_seconds=float(q[0,1]),survival_probability=float(s[0]),
            log_survival_probability=float(logs[0]),model_version=self.contract['model_version'],provenance_mode='Kestrel_trace_proxy',
            conditional_inference=True,remaining_model_refit=False)
    def observe_completed(self,job_record,runtime_seconds,completion_time):
        # Explicit completion-observer API; outcomes never pass into predict_* or X.
        t=self._time(completion_time,[job_record])
        if job_record.get('submit_time') is None:raise ValueError('RESIDUAL_SUBMISSION_TIME_REQUIRED')
        if stamp(job_record['submit_time'])<stamp(self.prep['fit_cutoff']):raise ValueError('IN_TRAINING_RESIDUAL_FORBIDDEN')
        if t<self.last_event:raise ValueError('OUT_OF_ORDER_COMPLETION')
        if not math.isfinite(runtime_seconds) or runtime_seconds<0:raise ValueError('INVALID_RUNTIME_OBSERVATION')
        base=self.model.quantiles(self.parameters([job_record]),quantiles=(.9,))[0,0]
        self.residuals.append((t,float(runtime_seconds-base)));self.last_event=t
        return dict(model_refitted=False,residual_observed=True,eligible_after_UTC_day=str((t+timedelta(days=1)).date()))
    def running_action(self,job_record,elapsed_seconds,planned_total_seconds,event_time=None,still_running=True,control_interval_seconds=900):
        if not math.isfinite(planned_total_seconds) or planned_total_seconds<0 or control_interval_seconds<=0:raise ValueError('INVALID_RESERVATION')
        remaining=self.predict_remaining(job_record,elapsed_seconds,event_time) if still_running else None
        overrun=bool(still_running and elapsed_seconds>=planned_total_seconds)
        return dict(OVERRUN=overrun,retain_GPU=bool(still_running),terminate_job=False,migration_recommendation='STAY',
            reservation_extend_seconds=control_interval_seconds if overrun else 0,conditional_remaining=remaining,future_end_read=False)
