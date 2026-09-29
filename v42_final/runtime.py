"""Only frozen Q50 inference is exposed. No model/calibration fit API."""
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from .common import require,read,sha


def timestamp(value):
    if isinstance(value,(int,float)):return float(value)
    d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    require(d.tzinfo is not None,'TIMEZONE_REQUIRED')
    return d.timestamp()


class FrozenQ50:
    def __init__(self,bundle=None):
        from .inference.hazard import Hazard
        self.root=Path(bundle) if bundle else Path(__file__).parent/'runtime_bundle'
        self.integrity=read(self.root/'INTEGRITY.json')
        for r in self.integrity['files']:require(sha(self.root/r['relative'])==r['sha256'],'FROZEN_PROVIDER_SHA')
        for r in self.integrity['inference_source_extraction']:
            require(sha(Path(__file__).parent/'inference'/Path(r['path']).name)==r['sha256'],'FROZEN_INFERENCE_CODE_SHA')
        self.model=Hazard.load(self.root/'model');self.prep=read(self.root/'preprocessing.json')
        self.state=read(self.root/'calibration_state.json')
        require(self.state['family']=='ISOTONIC' and self.state['mode']=='ROLLING14','EXACT_SELECTED_FAMILY')
        self.available=timestamp(self.state['day'])
        require(timestamp(self.state['max_completion_used'])<self.available,'CALIBRATION_CAUSALITY')

    def parameters(self,records):
        from .inference.features import engineer,FORBIDDEN
        forbidden=FORBIDDEN|{'event','censored','duration_lower','duration_upper','completion_time','actual_remaining','state_at_issue','known_running_start','elapsed_seconds'}
        require(len(records)>0,'NONEMPTY_REQUEST_BATCH')
        require(all(not forbidden.intersection(r) for r in records),'FUTURE_OR_STATE_FEATURE')
        return self.model.parameters(engineer(records,self.prep['categorical_mappings']),threads=1)

    def q50_parameters(self,parameters,state=None):
        from .inference.calibration import ProbabilityMap,maps_quantiles
        state=self.state if state is None else state
        require(state['family']=='ISOTONIC' and state['mode']=='ROLLING14','SELECTED_STATE_FAMILY')
        groups=np.digitize(np.exp(self.model.logsf(parameters,14400,'LAST_RATE')),state['bounds'],right=True)
        result=np.empty(len(parameters))
        for g in np.unique(groups):
            mask=groups==g;mapping=ProbabilityMap(state['groups'].get(str(int(g)),state['pooled']))
            result[mask]=maps_quantiles(self.model,parameters[mask],mapping,'LAST_RATE',(.5,))[:,0]
        require(np.isfinite(result).all() and (result>=0).all(),'FINITE_NONNEGATIVE_Q50_SECONDS')
        return result

    def predict_batch(self,records,*,submit_times,event_time):
        event=timestamp(event_time)
        require(event>=self.available,'EVENT_BEFORE_FROZEN_PROVIDER_AVAILABLE')
        require(len(records)==len(submit_times) and all(timestamp(t)<=event for t in submit_times),'INDIVIDUAL_NOT_YET_SUBMITTED')
        return self.q50_parameters(self.parameters(records))

    def predict_total(self,record,*,submit_time,event_time):
        return float(self.predict_batch([record],submit_times=[submit_time],event_time=event_time)[0])
