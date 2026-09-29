"""Full-stream, four-process restart audit (no fitting, no April/May data)."""
from common12 import *
from regime12 import ReplayState,completed
import subprocess

def queries():
    f=pd.read_parquet(V9/'.local/PREAPRIL_SOURCE.parquet')
    q=f[['job_id','submit_time','partition','qos','requested_seconds','num_gpus_req']].rename(columns={'submit_time':'prediction_time'})
    q=q.sort_values(['prediction_time','job_id'],kind='stable').reset_index(drop=True)
    return f,q

def part(i):
    f,q=queries();chunks=np.array_split(np.arange(len(q)),4);sub=q.iloc[chunks[i]].reset_index(drop=True)
    cutoff=pd.Timestamp(read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['final_information_cutoff'])
    events=completed(f,cutoff);path=LOCAL/'full_replay_state'
    if i==0:state=ReplayState(events.iloc[:0],read(ROOT/'FROZEN_TRAIN_PRIOR.json'))
    else:state=ReplayState.load(path)
    time=sub.prediction_time.max();add=events[events.end_time.lt(time)&~events.job_id.isin(state.history.job_id)]
    state.append_completed(add,time)
    out=state.predict(sub);out.insert(0,'job_id',sub.job_id)
    out.to_parquet(LOCAL/f'full_replay_part{i}.parquet',index=False)
    state.save(path)
    print(now(),'FULL_REPLAY_PART_DONE',i,len(sub),len(state.history),flush=True)

def main():
    for i in range(4):subprocess.run([sys.executable,'-B',str(ROOT/'full_replay12.py'),'--part',str(i)],check=True)
    original=pd.read_parquet(LOCAL/'REGIME_FEATURES.parquet');start=0;h=hashlib.sha256()
    for i in range(4):
        replay=pd.read_parquet(LOCAL/f'full_replay_part{i}.parquet');ref=original.iloc[start:start+len(replay)].reset_index(drop=True)
        pd.testing.assert_frame_equal(ref,replay,check_exact=True)
        h.update(pd.util.hash_pandas_object(replay.drop(columns='job_id'),index=False).values.tobytes());start+=len(replay)
    assert start==len(original)
    original_hash=read(ROOT/'REGIME_CAUSALITY_AUDIT.json')['feature_values_sha256']
    assert h.hexdigest()==original_hash
    write('FULL_STREAM_REPLAY_AUDIT.json',dict(time=now(),PASS=True,N=len(original),separate_processes=4,
        chronological_materialization_hash=original_hash,chunked_restarted_hash=h.hexdigest(),exact_float_equality=True,
        scope='Every pre-April prediction row and every232 feature; fresh Python process plus restored state for each chunk'))
    print(now(),'FULL_STREAM_REPLAY_PASS',len(original),flush=True)

if __name__=='__main__':
    if len(sys.argv)>1:part(int(sys.argv[2]))
    else:main()
