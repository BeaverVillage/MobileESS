"""Read-only source/authority audit and portable frozen preprocessing export."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,os,pickle,sys,zipfile
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'runtime_vnext_causal_tail'
ORIGINAL=Path(os.environ.get('RUNTIME_VNEXT_AUTHORITY_ROOT','D:/ChatGPT/Mobile ESS 2/runtime_vnext_causal_tail_pr'))
RAW=Path(os.environ.get('KESTREL_RAW_ZIP','C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip'))
JOBS=Path(os.environ.get('RUNTIME_JOBS_PARQUET',str(ORIGINAL/'docs/runtime_vnext_causal_tail/cache/JOBS.parquet')))

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(ok,message):
    if not ok:raise AssertionError(message)
def save(name,value):
    with (ROOT/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False,default=str)

def transform(frame,artifact):
    rows=frame.to_dict('records');numeric=np.zeros((len(rows),len(artifact.numeric_columns)),float)
    for i,row in enumerate(rows):
        for k,column in enumerate(artifact.numeric_columns):
            value=row.get(column)
            if value is None or value=='':continue
            try:numeric[i,k]=float(value)
            except (ValueError,TypeError):pass
    parts=[numeric]
    normalize=lambda value:None if value is None or value=='' else str(value)
    if artifact.categorical_columns and artifact.encoder is not None and artifact.svd is not None and artifact.svd_components>0:
        matrix=[[normalize(row.get(c)) for c in artifact.categorical_columns] for row in rows]
        parts.append(np.asarray(artifact.svd.transform(artifact.encoder.transform(matrix)),float))
    if artifact.target_encoded_columns:
        columns=[]
        for c in artifact.target_encoded_columns:
            lookup=artifact.target_encoding.get(c,{})
            columns.append([lookup.get(normalize(r.get(c)) or '',artifact.target_encoding_default) for r in rows])
        parts.append(np.column_stack(columns))
    return np.column_stack(parts)

def main():
    need(not (ROOT/'PREPARATION.json').exists(),'ALREADY_PREPARED')
    expected=json.loads((BASE/'PREPARATION_COMPLETE.json').read_text(encoding='utf-8'))
    need(sha(RAW)==expected['archive_sha256'],'RAW_ARCHIVE_DRIFT');need(sha(JOBS)==expected['jobs_sha256'],'JOB_CACHE_DRIFT')
    j=pd.read_parquet(JOBS);inventory=[];allstates={};rows=0;gpu_missing=0
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(n for n in z.namelist() if n.endswith('.parquet')):
            with z.open(name) as stream:f=pq.read_table(stream,columns=['submit_time','start_time','end_time','gpus_requested','state_simple'],use_threads=False).to_pandas()
            gp=f[pd.to_numeric(f.gpus_requested,errors='coerce').gt(0)&pd.to_datetime(f.submit_time,utc=True).lt(pd.Timestamp('2025-06-01',tz='UTC'))]
            counts={str(k):int(v) for k,v in gp.state_simple.value_counts(dropna=False).items()}
            for k,v in counts.items():allstates[k]=allstates.get(k,0)+v
            rows+=len(f);gpu_missing+=int(gp.end_time.isna().sum())
            inventory.append(dict(member=name,raw_N=len(f),GPU_preJune_N=len(gp),GPU_preJune_missing_end=int(gp.end_time.isna().sum()),GPU_preJune_states=counts))
    datacard=RAW.parent/'datacard.md'
    save('CENSORING_AUTHORITY.json',dict(time=pd.Timestamp.now(tz='UTC').isoformat(),R3_status='BLOCKED_AUTHORITY',
        archive_sha256=sha(RAW),raw_rows=rows,partitions=len(inventory),GPU_preJune_rows=len(j),GPU_preJune_missing_end=gpu_missing,
        GPU_preJune_missing_start=int(j.start_time.isna().sum()),GPU_preJune_invalid_completed_labels=int((~j.label_valid).sum()),GPU_preJune_states=allstates,inventory=inventory,
        local_datacard_sha256=sha(datacard),official_source='https://data.nlr.gov/submissions/302',
        observed_fields=['submit_time','start_time','end_time','state_simple'],missing_authorities=['historical as-of census completeness','outcome-independent inclusion/retention rule','first-observation timestamp','snapshot/version/ingestion history'],
        verdict='Observed final extract supports retrospective time masking only. It does not establish every then-active Job was included independently of later completion. This is missing proof, not demonstrated completion bias.',
        dependency='XGBoost3.2.0 AFT is installed, but available API cannot supply missing population authority.',
        required_to_unblock='Timestamped complete historical job snapshots or independently verified full event census with inclusion/retention rules, observation cutoff and issue-time request-feature provenance.',
        right_censored_model_fitted=False,fabricated_censored_rows=0))
    # Export only the already-fitted preprocessing, not the MoE runtime model.
    sys.path.insert(0,str(ORIGINAL/'.runtime_deps'))
    s=importlib.util.spec_from_file_location('frozen_common_export',ORIGINAL/'docs/runtime_vnext_causal_tail/common.py')
    common=importlib.util.module_from_spec(s);s.loader.exec_module(common);model=common.exact_moe();proof=[]
    columns=common.MOE_FEATURES
    for row in pd.read_csv(BASE/'ISSUES.csv').query("role != 'TRAIN'").itertuples():
        t=pd.Timestamp(row.issue_time);key=t.strftime('%Y%m%dT%H%M');source=ORIGINAL/'docs/runtime_vnext_causal_tail/fits/MOE_180_14'/key/'moe.pkl.gz'
        receipt=json.loads((BASE/'fits/MOE_180_14'/key/'PREDICTION_RECEIPT.json').read_text(encoding='utf-8'))
        need(sha(source)==receipt['model_files']['moe.pkl.gz'],'PREPROCESSOR_AUTHORITY_DRIFT')
        with gzip.open(source,'rb') as f:artifact,_=pickle.load(f)
        portable=SimpleNamespace(**{k:v for k,v in vars(artifact).items() if k!='routing'})
        q=pd.read_parquet(BASE/'predictions/LGBM_180_14'/(key+'.parquet'));q=q[q.state.eq('RUNNING')]
        a=model._transform_rows(q[columns].to_dict('records'),artifact);b=transform(q[columns],portable)
        need(np.array_equal(a,b,equal_nan=True),'PORTABLE_TRANSFORM_NOT_EXACT')
        path=ROOT/'preprocessing'/(key+'.pkl.gz');path.parent.mkdir(exist_ok=True)
        with gzip.open(path,'wb',compresslevel=6) as f:pickle.dump(portable,f,protocol=5)
        proof.append(dict(issue_time=str(t),source_checkpoint_sha256=sha(source),portable_sha256=sha(path),N_query=len(q),columns=a.shape[1],query_matrix_bit_exact=True))
    save('PREPROCESSING_BRIDGE.json',dict(PASS=True,issues=proof,original_preprocessor_unchanged=True,export='SimpleNamespace containing original sklearn encoder/SVD and numeric/target-encoding metadata; routing unused by transform'))
    save('PREPARATION.json',dict(time=pd.Timestamp.now(tz='UTC').isoformat(),jobs_path=str(JOBS),jobs_sha256=sha(JOBS),raw_zip=str(RAW),raw_sha256=sha(RAW),
        parent_job_membership_sha256=sha(BASE/'JOB_MEMBERSHIP.parquet'),preprocessing_bridge_sha256=sha(ROOT/'PREPROCESSING_BRIDGE.json'),censoring_authority_sha256=sha(ROOT/'CENSORING_AUTHORITY.json'),R3_status='BLOCKED_AUTHORITY'))
    print('PREPARED',len(proof),'portable preprocessors; R3 BLOCKED_AUTHORITY',flush=True)

if __name__=='__main__':main()
