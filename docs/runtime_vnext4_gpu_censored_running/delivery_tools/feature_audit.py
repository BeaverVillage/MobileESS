"""Document event-time checks separately from unobserved request-version authority."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent/'runtime_vnext_causal_tail'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    issues=pd.read_csv(BASE/'ISSUES.csv');issues['new_fit']=issues.role.ne('TRAIN');issues['Pending_R0_available']=issues.role.eq('MAY_HISTORICAL');issues.to_csv(ROOT/'EXACT_SPLITS.csv',index=False)
    jobs=pd.read_parquet(BASE/'JOB_MEMBERSHIP.parquet');rows=[]
    for row in issues[issues.new_fit].itertuples():
        t=pd.Timestamp(row.issue_time);key=t.strftime('%Y%m%dT%H%M');raw=pd.read_parquet(BASE/'predictions/LGBM_180_14'/(key+'.parquet'));raw=raw[raw.state.eq('RUNNING')]
        q=raw.merge(jobs[['row_id','job_id','submit_time','start_time']],on='row_id',suffixes=('','_authority'),validate='many_to_one')
        assert q.submit_time.le(t).all() and q.start_time.le(t).all()
        assert np.array_equal(q.elapsed_seconds,(t-q.start_time).dt.total_seconds())
        p=read(BASE/'fits/LGBM_180_14'/key/'RUNNING/preprocessing.json');assert pd.Timestamp(p['latest_end'])<t
        portable=ROOT/'preprocessing'/(key+'.pkl.gz')
        rows.append({'issue_time':str(t),'role':row.role,'query_N':len(raw),'submit_start_not_after_issue':True,'elapsed_computed_from_known_start_and_issue':True,'R1_preprocessing_latest_mature_end':p['latest_end'],'R1_preprocessing_source_sha256':p['artifact_sha256'],'portable_preprocessing_sha256':sha(portable),'request_version_available_time':'UNOBSERVED','authority':'D1_SCHEDULER_REQUEST_STATE_PROXY_V1'})
    pd.DataFrame(rows).to_csv(ROOT/'FEATURE_AVAILABILITY_LEDGER.csv',index=False)
    with (ROOT/'FEATURE_AVAILABILITY_AUDIT.json').open('x',encoding='utf-8') as f:
        json.dump({'event_time_checks_PASS':True,'operational_feature_availability_certified':False,'issues':len(rows),'request_proxy_authorized':True,'provenance':'UNVERIFIED/UNOBSERVED','historical_exactness':False,'immutability':False,'zero_change_claimed':False,'feature_availability_time':'Not fabricated. Event time validated; request first-observation/version time unobserved. Scheduler-visible availability is the user-authorized proxy assumption.','source_job_catalog_sha256':sha(BASE/'JOB_MEMBERSHIP.parquet'),'query_features':'fixed nine parent scheduler proxies + log1p(elapsed_seconds)','preprocessing':'59 exact portable exports; parent query matrices verified bit-exact in PREPROCESSING_BRIDGE'},f,indent=2)
    print('FEATURE_EVENT_TIME_AUDIT_PASS',len(rows))
if __name__=='__main__':main()
