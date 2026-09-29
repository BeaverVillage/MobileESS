from common10 import *
from calibration10 import *
from calibration_state10 import statuses
import numpy as np,pandas as pd
def main():
    weights=np.ones(len(CENTERS));positive=weights*expit(1.3*LOGITS-.8)
    models=[ProbabilityMap(),ProbabilityMap.fit(weights,positive,'ISOTONIC'),ProbabilityMap.fit(weights,positive,'LOGISTIC')]
    errors=[];score_errors=[]
    for m in models:
        assert m.audit(),m.state
        logs=-np.geomspace(1e-12,1e6,200);mapped=m.logsf(logs);inverse=m.inverse_logsf(mapped)
        err=float(np.max(abs(inverse-logs)/np.maximum(abs(logs),1e-8)));assert err<1e-5,(m.state['family'],err);errors.append(err)
        ls=-np.geomspace(1e-8,1e6,200);dh=np.geomspace(1e-12,100,200);exact=m.log_interval(ls,dh);assert np.isfinite(exact).all() and (exact<=0).all()
        # Independent finite-difference probability oracle on numerically resolvable cases.
        left=-np.linspace(.01,10,100);delta=np.full(100,.01);direct=np.log(np.exp(m.logsf(left))-np.exp(m.logsf(left-delta)))
        difference=float(np.max(abs(direct-m.log_interval(left,delta))));assert difference<1e-9;score_errors.append(difference)
    pool=pd.DataFrame(dict(submit_time=pd.to_datetime(['2025-01-01']*3,utc=True),start_time=pd.to_datetime(['2025-01-01','2025-01-01',None],utc=True),
        end_time=pd.to_datetime(['2025-01-02','2025-01-10',None],utc=True),event=[True,True,False],runtime_seconds=[86400.,9*86400.,np.nan],
        observation_cutoff=pd.to_datetime(['2025-02-01']*3,utc=True)))
    known,target,completed=statuses(pool,'2025-01-03T00Z','ROLLING14')
    assert completed.tolist()==[True,False,False] and not known[2].any()
    changed=pool.copy();changed.loc[1,'runtime_seconds']=1e20;changed.loc[1,'end_time']=pd.Timestamp('2026-01-01T00Z')
    kk,tt,cc=statuses(changed,'2025-01-03T00Z','ROLLING14');assert np.array_equal(known,kk) and np.array_equal(target,tt)
    write('CALIBRATION_MATH_CAUSALITY_TEST.json',dict(time=now(),PASS=True,monotone_all_families=True,max_inverse_relative_error=max(errors),
        max_log_interval_oracle_error=max(score_errors),extreme_log_survival=1000000,no_score_probability_floor=True,
        future_event_mutation_invariant=True,pending_has_no_landmark_label=True))
    print('CALIBRATION_MATH_CAUSALITY_PASS',max(errors),max(score_errors))
if __name__=='__main__':main()
