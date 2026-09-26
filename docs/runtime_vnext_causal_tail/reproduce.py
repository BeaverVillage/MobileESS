"""Reproduce two historical authorities without running any downstream system."""
from common import *
import argparse,pyarrow.parquet as pq,lightgbm as lgb,xgboost,sklearn,scipy

def modern():
 rows=[]
 for day in pd.date_range('2025-05-01','2025-05-31').strftime('%Y-%m-%d'):
  snapshot=Path('D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4')/day/'B0/dayahead/ml/ML_SNAPSHOT.json'
  receipt=json.loads(snapshot.read_text(encoding='utf-8'))
  model=Path(receipt['model']['path']);prepath=Path(receipt['preprocessing']['path']);d=json.loads(prepath.read_text(encoding='utf-8'))
  require(sha(model)==receipt['model']['sha256'] and sha(prepath)==receipt['preprocessing']['sha256'],'MODERN_ARTIFACT_DRIFT')
  cols=['id','submit_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos']
  snap=SNAP/day/'V37_R4A_D1_SNAPSHOT.parquet'
  f=normalize(pq.read_table(snap,columns=cols,filters=[('state_at_issue','==','PENDING')]).to_pandas())
  pre=Preprocess(d['cutoff']);pre.__dict__.update(d)
  m=lgb.Booster(model_str=gzip.decompress(model.read_bytes()).decode('utf-8'))
  q=m.predict(pre.transform(f),num_threads=1);expected=np.array([receipt['PENDING_JOB_Q90_SECONDS'][j] for j in f.job_id])
  require(np.array_equal(q,expected),'MODERN_Q90_NOT_EXACT')
  require((f.submit_time<=pd.Timestamp(receipt['issue_time'])).all(),'MODERN_FUTURE_SUBMIT')
  pd.DataFrame(dict(job_id=f.job_id,Q90_seconds=q,day=day)).to_parquet(ROOT/'baseline'/f'modern_{day}.parquet',index=False)
  rows.append(dict(day=day,N=len(f),max_difference=float(np.max(abs(q-expected))) if len(q) else 0,
   model_sha256=sha(model),preprocessing_sha256=sha(prepath),snapshot_sha256=sha(snap),training_N=receipt['runtime_training_N'],
   training_membership_hash=receipt['runtime_training_membership_hash']))
  print('MODERN exact',day,len(f),flush=True)
 dump('MODERN_BASELINE_REPRODUCTION.json',dict(time=now(),PASS=True,model='ROLLING_Q90_TRACK_P_L2',days=rows,
  request_version_provenance='UNVERIFIED_D1_SCHEDULER_REQUEST_STATE_PROXY_V1',outcome_labels_read=False,production_imported=False))

def legacy():
 require(xgboost.__version__=='3.2.0','EXACT_XGBOOST_VERSION')
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=HPC).decode().strip()=='218d75f56b783ebfd698100f9406cfb46fa04c01','HPCODA_COMMIT')
 source=LEGACY/'kestrel_preissue_normalized.parquet';expected=LEGACY/'window_predictions/1742652000.parquet'
 require(sha(source)=='2a8cf4ac8f86a30d0a7dcf999e2064316b556194f8bbc291f09cc85a2d7e101f','LEGACY_SOURCE_HASH')
 require(sha(expected)=='7d11dbd0150c925e1a1987476b7f8a0a253b5e454d5fab8e32d3590b040f3d2a','LEGACY_EXPECTED_HASH')
 # Execute the archived ML-only module with explicit minimal original constants.
 import types
 module=types.ModuleType('legacy_replay');src=(ROOT/'authority/moe_runtime_original.py').read_text(encoding='utf-8')
 start=src.index('from .contracts import (');end=src.index('\n)',start)+2
 src=src[:start]+src[end:]
 module.__dict__.update(QUERY_FEATURE_FIELDS=tuple(MOE_FEATURES),FORBIDDEN_QUERY_FIELDS=frozenset(['start_time','end_time','runtime_seconds','job_state']),
  RECIPE_CONTRACT=dict(n_windows=120,test_window_hours=6,training_lookback_days=120,enable_power_users=False,time_decay_rate=.05,objective='reg:absoluteerror'),SLOT_SECONDS=900)
 exec(compile(src,'archived_moe_runtime','exec'),module.__dict__)
 rows=pq.read_table(source).to_pylist();require(all(r['end_time']<pd.Timestamp('2025-04-01',tz='UTC') for r in rows),'LEGACY_CACHE_FUTURE')
 attempt=f'legacy_arrow_numpy{np.__version__}_sklearn{sklearn.__version__}_scipy{scipy.__version__}'
 start=time.perf_counter();got,entries,equiv=module.run_windows(rows,[pd.Timestamp(1742652000,unit='s',tz='UTC').to_pydatetime()],ROOT/'baseline'/attempt,label='Runtime-vNext exact PR27 replay')
 ref=pd.read_parquet(expected);require(got.job_id.tolist()==ref.job_id.tolist(),'LEGACY_JOB_ORDER')
 delta=abs(got.point_runtime_seconds.to_numpy()-ref.point_runtime_seconds.to_numpy())
 dump(f'baseline/{attempt}/comparison.json',dict(N=len(got),max_difference=float(delta.max()),numpy=np.__version__,sklearn=sklearn.__version__,scipy=scipy.__version__,xgboost=xgboost.__version__))
 require(np.array_equal(got.point_runtime_seconds,ref.point_runtime_seconds),'LEGACY_PREDICTION_DRIFT')
 require(equiv['PASS'],'LEGACY_ADAPTER_DRIFT')
 dump('MOE_BASELINE_REPRODUCTION.json',dict(time=now(),PASS=True,N=len(got),max_difference=float(delta.max()),seconds=time.perf_counter()-start,
  source_sha256=sha(source),reference_sha256=sha(expected),entries=entries,adapter=equiv,pooled_correction_seconds=Q_OLD,
  pooled_correction_available_no_earlier_than='2025-04-01T08:00:00Z',calibration_reestimated=False,raw_source_all_jobs=True))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('which',choices=['modern','legacy']);a=p.parse_args();(ROOT/'baseline').mkdir(exist_ok=True)
 globals()[a.which]()
