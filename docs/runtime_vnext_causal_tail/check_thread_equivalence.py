"""Pre-evaluation compute-only check: full causal training predictions and tree identity."""
from experiment import *

def main():
 require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'THREAD_CHECK_MUST_PRECEDE_EVALUATION_FREEZE')
 t=pd.Timestamp('2025-03-22T08:00Z');train=member('120',t);q=query(t);model=exact_moe()
 source=ROOT/'fits/MOE_120_current_decay/20250322T0800/moe.pkl.gz'
 with gzip.open(source,'rb') as stream:art,_=pickle.load(stream)
 x=model._transform_rows(train[MOE_FEATURES].to_dict('records'),art);xp=model._transform_rows(q[MOE_FEATURES].to_dict('records'),art)
 result=[];pred=[];tree=[]
 for threads in [1,4]:
  start=time.perf_counter();m=lgb.LGBMRegressor(objective='quantile',alpha=.9,**{**FIXED,'n_jobs':threads}).fit(x,train.runtime_seconds).booster_
  seconds=time.perf_counter()-start;p=m.predict(x,num_threads=threads);v=m.predict(xp,num_threads=threads)
  tree.append(m.dump_model()['tree_info']);pred.append((p,v));result.append(dict(threads=threads,fit_seconds=seconds,training_prediction_sha256=hashlib.sha256(p.tobytes()).hexdigest(),query_prediction_sha256=hashlib.sha256(v.tobytes()).hexdigest()))
 equal=tree[0]==tree[1] and np.array_equal(pred[0][0],pred[1][0]) and np.array_equal(pred[0][1],pred[1][1])
 dump('THREAD_EQUIVALENCE.json',dict(time=now(),PASS=bool(equal),same_all_trees=tree[0]==tree[1],N_training=len(train),N_queries=len(q),
  runs=result,training_membership_sha256=ids(train.job_id),evaluation_labels_read=False,validation_loss_computed=False))
 print('THREAD_EQUIVALENCE',equal,result,flush=True)

if __name__=='__main__':main()
