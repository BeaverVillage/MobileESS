from common13 import *
from stream13 import Stream,PerturbedFutureStream,value_hash
from state13 import State
import pickle,subprocess,time

def new_state():
    v=read(ROOT/'FROZEN_CATEGORY_VOCABULARY.json');return State(v['categories'],v['available_after'])
def equal(a,b):return np.array_equal(np.array(list(a.values()),float),np.array(list(b.values()),float),equal_nan=True)

def materialize(a=0,b=None,checkpoint=None,output='CURRENT_STATE_FEATURES.parquet',audit=False):
    source=Stream();b=len(source.ids) if b is None else b
    state=new_state()
    if checkpoint:
        state=State.load(LOCAL/'checkpoint.pkl');source.cursor=read(LOCAL/'cursor.json')['cursor']
    chosen=set()
    if audit:
        _,indices=np.unique(source.query_times,return_index=True)
        # Each chosen event follows a submission within24h, ensuring the past
        # positive-control mutation remains in an arrival summary.
        candidates=indices[1:][np.diff(source.query_times[indices])<=86400]
        chosen=set(np.random.default_rng(13013).choice(candidates,1024,replace=False).tolist())
    columns=read(ROOT/'CURRENT_STATE_FEATURE_CONTRACT.json')['columns']
    rows=np.empty((b-a,len(columns)),dtype='float64');receipts=[];start=time.perf_counter()
    for i in range(a,b):
        t=int(source.query_times[i]);d=source.requests[i]
        if i in chosen:snapshot=pickle.dumps(state,protocol=5);cursor=source.cursor
        source.advance(state,t);features=state.predict(d,t)
        if i in chosen:
            altered=pickle.loads(snapshot);intervention=PerturbedFutureStream(source,t,cursor)
            intervention.advance(altered,t);ff=altered.predict(d,t)
            assert equal(features,ff) and intervention.future_payload_reads==0
            past=pickle.loads(snapshot);oldcursor=source.cursor;source.cursor=cursor;changed=[]
            def change(e,index):
                if not changed and e['kind']=='SUBMIT':
                    e={**e,'request':{**e['request'],'num_gpus_req':float(e['request']['num_gpus_req'])+1}}
                    changed.append(index)
                return e
            source.advance(past,t,change);source.cursor=oldcursor;pf=past.predict(d,t)
            assert changed and not equal(features,pf)
            assert any(pf[k]!=features[k] for k in features if k.endswith('num_gpus_req_sum') and k.startswith('a_'))
            counts=np.bincount(source.kinds[intervention.cut:],minlength=3)
            receipts.append(dict(query_row=i,job_id=source.ids[i],time=t,unchanged=True,past_control_changed=True,
                future_SUBMIT=int(counts[0]),future_START=int(counts[1]),future_END=int(counts[2]),
                past_mutated_event=changed[0],future_payload_reads=0))
        rows[i-a]=[features[c] for c in columns]
        if (i-a+1)%25000==0:print(now(),'STATE',i+1,'of',b,'seconds',round(time.perf_counter()-start),flush=True)
    result=pd.DataFrame(rows,columns=columns);result.insert(0,'job_id',source.ids[a:b])
    result.to_parquet(LOCAL/output,index=False)
    state.save(LOCAL/'checkpoint.pkl');write(LOCAL/'cursor.json',dict(cursor=source.cursor,next_query=b,version=state.version))
    if audit:
        assert len(receipts)==1024
        pd.DataFrame(receipts).to_csv(ROOT/'FUTURE_INTERVENTION_RECEIPTS.csv',index=False)
        write('CURRENT_STATE_CAUSALITY_AUDIT.json',dict(time=now(),PASS=True,N=1024,
            random_seed=13013,intervention='all future/simultaneous SUBMIT/START/END timestamps shifted+365d; all suffix payloads poisoned lazily; replay from preceding query checkpoint',
            positive_control='mutate one actually observed SUBMIT GPU value before query; arrival GPU sum must change',
            future_suffix_representation='lazy universal transformation, not a sample of individual future events',
            FUTURE_SUBMIT_READS=0,FUTURE_START_READS=0,FUTURE_END_READS=0,CURRENT_JOB_FUTURE_EVENT_READS=0,
            schedule_scope='dispatcher compares scheduling timestamps only to withhold future payloads; state engine cannot access schedule',
            feature_values_sha256=value_hash(result),feature_file=record(LOCAL/output),
            event_counts=dict(state.processed),final_pending=len(state.pending),final_running=len(state.running)))
    print('MATERIALIZED',a,b,value_hash(result),flush=True)

def full_replay():
    original=pd.read_parquet(LOCAL/'CURRENT_STATE_FEATURES.parquet');n=len(original)
    pieces=[];receipts=[]
    for j,indices in enumerate(np.array_split(np.arange(n),4)):
        a=int(indices[0]);b=int(indices[-1])+1;out=f'restart_part{j}.parquet'
        args=[sys.executable,'-B',str(ROOT/'stage_a13.py'),'chunk',str(a),str(b),str(j),out]
        subprocess.run(args,check=True,cwd=ROOT)
        part=pd.read_parquet(LOCAL/out)
        pd.testing.assert_frame_equal(original.iloc[a:b].reset_index(drop=True),part,check_exact=True)
        pieces.append(part);receipts.append(dict(part=j,begin=a,end=b,N=len(part),hash=value_hash(part),fresh_process=True))
    joined=pd.concat(pieces,ignore_index=True)
    assert value_hash(original)==value_hash(joined)
    write('CURRENT_STATE_REPLAY_AUDIT.json',dict(time=now(),PASS=True,N=n,features=len(original.columns)-1,
        continuous_hash=value_hash(original),chunked_restored_hash=value_hash(joined),fresh_process_hash=value_hash(joined),
        chunks=receipts,multiprocess_parallel='NOT_RUN; chronological sequential fresh subprocesses test process isolation',
        state_checkpoint=record(LOCAL/'checkpoint.pkl'),dispatcher_cursor=record(LOCAL/'cursor.json')))

def forensic():
    source=Stream();state=new_state()
    summaries=[];pressure=[];composition=[]
    contracts=read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds']
    snapshots={};queries=[]
    for i in range(1,6):
        begin=int(pd.Timestamp(contracts[i-1]['VALID_submit_from']).timestamp())
        queries.extend([(begin-14*86400,i,'14d_before'),(begin,i,'before_VALID')])
    dummy={k:None for k in source.requests[0]}
    refresh=int(source.query_times[0])+3600
    for t,i,tag in sorted(queries):
        # Expire rolling buffers during long query-free historical gaps too.
        # Intermediate queries change no membership at the requested boundary.
        while refresh<t:
            source.advance(state,refresh);state.predict(dummy,refresh);refresh+=3600
        source.advance(state,t);snapshots[i,tag]=state.predict(dummy,t)
    for i in range(1,6):
        valid=data(i,'VALID');begin=int(valid.submit_time.min().timestamp())
        # Independent chronological snapshots at fixed fold boundary, not the
        # first VALID row if there is a gap in submissions.
        boundary=pd.Timestamp(contracts[i-1]['VALID_submit_from'])
        begin=int(boundary.timestamp())
        for tag,t in [('14d_before',begin-14*86400),('before_VALID',begin)]:
            f=snapshots[i,tag]
            for k,v in f.items():
                row=dict(fold=i,snapshot=tag,time=pd.Timestamp(t,unit='s',tz='UTC').isoformat(),feature=k,value=v)
                (composition if k.startswith('c_') else pressure).append(row)
        exact=valid[valid.event];runtime=exact.runtime_seconds
        q=dict(fold=i,VALID_N=len(valid),exact_N=len(exact),runtime_q50=float(runtime.median()),runtime_q90=float(runtime.quantile(.9)),
            gt4h_fraction=float((runtime>14400).mean()),gt12h_fraction=float((runtime>43200).mean()),
            before_arrival_24h_GPU=f['a_86400_num_gpus_req_sum'],before_pending_GPU=f['p_num_gpus_req_sum'],before_running_GPU=f['r_num_gpus_req_sum'])
        summaries.append(q)
    pd.DataFrame(summaries).to_csv(ROOT/'FOLD_CURRENT_STATE_SUMMARY.csv',index=False)
    pd.DataFrame(pressure).to_csv(ROOT/'FOLD_WORKLOAD_PRESSURE.csv',index=False)
    pd.DataFrame(composition).to_csv(ROOT/'FOLD_COMPOSITION_SHIFT.csv',index=False)
    for i in [1,4]:
        row=summaries[i-1]
        (ROOT/f'FOLD{i}_STATE_FORENSIC.md').write_text(f'''# Fold{i} state forensic

CURRENT_STATE_TRACKS_FOLD{i} = INCONCLUSIVE

직전24h 제출 requested GPU 합={row['before_arrival_24h_GPU']:.0f},
pending GPU={row['before_pending_GPU']:.0f}, running GPU={row['before_running_GPU']:.0f}.
다음 VALID exact runtime Q50={row['runtime_q50']:.0f}s,
Q90={row['runtime_q90']:.0f}s, >4h={row['gt4h_fraction']:.4%}.

FOLD_WORKLOAD_PRESSURE.csv와 FOLD_COMPOSITION_SHIFT.csv에 14일 전/직전의
모든 압력·구성값을 기록했다. 다섯 시기만의 기술적 비교로 incoming wave의
지속적 예측력을 확정할 수 없다. 완료된 작업의 runtime만 비교하므로 관측
cutoff의 completion-selection도 남는다. 이 결과로 feature나 gate를 바꾸지
않으며, 시간적 예측력은 고정된 Stage B 모델과 group ablation으로 판단한다.
''',encoding='utf-8')
    write('STAGE_A_VERDICT.json',dict(time=now(),PASS=True,CURRENT_STATE_CAUSALITY_PASS=True,
        CURRENT_STATE_REPLAY_DETERMINISTIC=True,CURRENT_STATE_TRACKS_FOLD1='INCONCLUSIVE',CURRENT_STATE_TRACKS_FOLD4='INCONCLUSIVE',
        feature_count=read(ROOT/'CURRENT_STATE_FEATURE_CONTRACT.json')['feature_count']))

def main():
    if len(sys.argv)>1 and sys.argv[1]=='chunk':
        materialize(int(sys.argv[2]),int(sys.argv[3]),checkpoint=int(sys.argv[4])>0,output=sys.argv[5]);return
    for r in read(ROOT/'PREREGISTRATION.json')['files']:assert sha(r['path'])==r['sha256']
    subprocess.run([sys.executable,'-B',str(ROOT/'test_state13.py')],check=True)
    if not (ROOT/'CURRENT_STATE_CAUSALITY_AUDIT.json').exists():materialize(audit=True)
    if not (ROOT/'CURRENT_STATE_REPLAY_AUDIT.json').exists():full_replay()
    forensic()
if __name__=='__main__':main()
