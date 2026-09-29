"""Frozen CPU callable research provider; no outcome observer, cache, or fitting."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math
import numpy as np
from features8 import engineer,FORBIDDEN,BASE_RESOURCE
from hazard10 import Hazard
from calibration10 import ProbabilityMap,maps_quantiles,maps_remaining

def stamp(value):
    t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return t.astimezone(timezone.utc)
class RuntimeProvider:
    def __init__(self,bundle=None,*,allow_research=False):
        self.root=Path(bundle) if bundle else Path(__file__).resolve().parent
        if not allow_research:raise PermissionError('KESTREL_TRACE_PROXY_RESEARCH_OPT_IN_REQUIRED')
        integrity=json.loads((self.root/'BUNDLE_INTEGRITY.json').read_text(encoding='utf-8'))
        for r in integrity['files']:
            if hashlib.sha256((self.root/r['relative']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('PROVIDER_INTEGRITY_FAILURE')
        self.contract=json.loads((self.root/'runtime_contract.json').read_text(encoding='utf-8'))
        self.prep=json.loads((self.root/'preprocessing.json').read_text(encoding='utf-8'))
        self.state=json.loads((self.root/'calibration_state.json').read_text(encoding='utf-8'))
        self.model=Hazard.load(self.root/'model')
        self.input_columns=BASE_RESOURCE+['requested_seconds','array_index']+list(self.prep['categorical_mappings'])
        self.available=stamp(self.contract['available_from'])
        self.continuation=self.contract['continuation'];self.bounds=self.state['bounds']
        self.conditioned=self.contract['risk_conditioned']
    def _rows(self,records):
        if not records:raise ValueError('EMPTY_BATCH')
        for r in records:
            if not isinstance(r,dict):raise TypeError('JOB_MAPPING_REQUIRED')
            if (FORBIDDEN|{'event','censored','duration_lower','duration_upper','label_valid','actual_long','actual_long_gt4h','actual_remaining','completion_time'}).intersection(r):raise ValueError('FORBIDDEN_OUTCOME_OR_FUTURE_INPUT')
        return [{k:r.get(k) for k in self.input_columns} for r in records]
    def _time(self,event_time,records=()):
        t=self.available if event_time is None else stamp(event_time)
        if t<self.available:raise ValueError('EVENT_BEFORE_MODEL_AVAILABLE')
        for r in records:
            if r.get('submit_time') is not None and stamp(r['submit_time'])>t:raise ValueError('EVENT_BEFORE_SUBMISSION')
        return t
    def parameters(self,records):
        x=engineer(self._rows(records),self.prep['categorical_mappings'])
        return self.model.parameters(x,threads=1)
    def risk_groups(self,par):
        risk=np.exp(self.model.logsf(par,14400,self.continuation))
        return risk,np.digitize(risk,self.bounds,right=True)
    def mapping(self,group):
        state=self.state['groups'].get(str(int(group)),self.state['pooled']) if self.conditioned else self.state['pooled']
        return ProbabilityMap(state)
    def quantiles_from_parameters(self,par,quantiles=(.5,.9)):
        risk,groups=self.risk_groups(par);out=np.zeros((len(par),len(quantiles)))
        for g in np.unique(groups):
            m=groups==g;out[m]=maps_quantiles(self.model,par[m],self.mapping(g),self.continuation,quantiles)
        return out
    def remaining_from_parameters(self,par,elapsed):
        elapsed=np.broadcast_to(np.asarray(elapsed,float),len(par))
        if np.any(~np.isfinite(elapsed)) or np.any(elapsed<0):raise ValueError('INVALID_ELAPSED')
        risk,groups=self.risk_groups(par);q=np.zeros((len(par),2));logs=np.zeros(len(par))
        for g in np.unique(groups):
            m=groups==g;q[m],logs[m]=maps_remaining(self.model,par[m],elapsed[m],self.mapping(g),self.continuation)
        return q,logs
    def predict_batch(self,records,event_time=None):
        self._time(event_time,records);return self.quantiles_from_parameters(self.parameters(records))
    def predict_total(self,job_record,event_time=None):
        self._time(event_time,[job_record]);par=self.parameters([job_record]);q=self.quantiles_from_parameters(par)[0];risk,groups=self.risk_groups(par)
        return dict(q50_total_seconds=float(q[0]),q90_total_seconds=float(q[1]),selected_tail_risk=dict(raw_p4=float(risk[0]),group=int(groups[0]),risk_calibration_used=self.conditioned),
            distribution_metadata=dict(family='piecewise_exponential_hazard',grid=self.contract['grid'],continuation=self.continuation,calibration_family=self.contract['family'],
                calibration_window=self.contract['mode'],calibration_state_frozen=True,conditional_method='S(e+r)/S(e)',positive_unbounded_tail=True,walltime_cap=False,unknown_category_code=0),
            model_version=self.contract['model_version'],calibration_version=self.contract['calibration_version'],provenance_mode='Kestrel_trace_proxy',
            STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,job_id_used=False,online_refit_required=False)
    def predict_remaining(self,job_record,elapsed_seconds,event_time=None):
        if not isinstance(elapsed_seconds,(int,float)) or not math.isfinite(elapsed_seconds) or elapsed_seconds<0:raise ValueError('INVALID_ELAPSED')
        self._time(event_time,[job_record]);q,logs=self.remaining_from_parameters(self.parameters([job_record]),elapsed_seconds)
        return dict(q50_remaining_seconds=float(q[0,0]),q90_remaining_seconds=float(q[0,1]),survival_probability_at_elapsed=float(np.exp(logs[0])),
            log_survival_probability_at_elapsed=float(logs[0]),model_version=self.contract['model_version'],calibration_version=self.contract['calibration_version'],
            provenance_mode='Kestrel_trace_proxy',conditional_inference=True,remaining_model_refit=False)
    def running_action(self,job_record,elapsed_seconds,planned_total_seconds,event_time=None,still_running=True,control_interval_seconds=900):
        if not math.isfinite(planned_total_seconds) or planned_total_seconds<0 or control_interval_seconds!=900:raise ValueError('INVALID_RESERVATION_OR_CONTROL_INTERVAL')
        remaining=self.predict_remaining(job_record,elapsed_seconds,event_time) if still_running else None
        overrun=bool(still_running and elapsed_seconds>=planned_total_seconds)
        return dict(OVERRUN=overrun,retain_GPU=bool(still_running),terminate_job=False,migration_recommendation='STAY',
            reservation_extend_seconds=900 if overrun else 0,conditional_remaining=remaining,future_end_read=False)

