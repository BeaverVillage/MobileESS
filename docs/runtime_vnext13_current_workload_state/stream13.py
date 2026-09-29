"""Offline archive adapter and time-gated dispatcher, separate from state engine."""
from common13 import *
from state13 import FIELDS,State

def build_stream(frame,cutoff):
    # One-time adapter: endpoint timestamps schedule events, never enter requests.
    frame=frame.sort_values(['submit_time','job_id'],kind='stable').reset_index(drop=True)
    assert frame.job_id.is_unique
    requests=frame[['job_id','submit_time']+list(FIELDS)].copy()
    requests['prediction_time']=requests.pop('submit_time').astype('int64')//10**9
    requests.to_parquet(LOCAL/'REQUESTS.parquet',index=False)
    times=[];kinds=[];rows=[];audit={}
    for code,col in enumerate(['submit_time','start_time','end_time']):
        mask=frame[col].notna() & frame[col].ge(frame.submit_time) & frame[col].lt(cutoff)
        audit[col]=dict(emitted=int(mask.sum()),missing=int(frame[col].isna().sum()),
                       before_submit=int(frame[col].lt(frame.submit_time).sum()),
                       beyond_information_cutoff=int(frame[col].ge(cutoff).sum()))
        ts=frame.loc[mask,col].astype('int64').to_numpy()
        assert (ts%10**9==0).all(),'Fractional timestamp requires new preregistration'
        times.append(ts//10**9);kinds.append(np.full(len(ts),code,dtype='int8'));rows.append(np.flatnonzero(mask))
    t=np.concatenate(times);k=np.concatenate(kinds);r=np.concatenate(rows)
    order=np.lexsort((r,k,t))
    np.savez_compressed(LOCAL/'EVENT_SCHEDULE.npz',time=t[order],kind=k[order],row=r[order])
    audit['end_before_start']=int(frame.end_time.lt(frame.start_time).sum())
    write('ARCHIVE_EVENT_ADAPTER_AUDIT.json',dict(time=now(),counts=audit,events=len(t),requests=len(requests),
        scope='Pre-April positive-requested-GPU trace subset, not full physical cluster',
        end_rule='END is independently scheduled when end>=submit; terminates pending or running. Later START on a terminal identity is ignored. No START selection uses end_time.',
        payload_fields=list(FIELDS),outcome_fields_in_engine=False))

class Stream:
    def __init__(self):
        schedule=np.load(LOCAL/'EVENT_SCHEDULE.npz')
        self.times=schedule['time'];self.kinds=schedule['kind'];self.rows=schedule['row']
        f=pd.read_parquet(LOCAL/'REQUESTS.parquet')
        self.ids=f.job_id.astype(str).tolist();self.query_times=f.prediction_time.to_numpy()
        self.requests=f[list(FIELDS)].to_dict('records');self.cursor=0
    def event(self,index):
        code=int(self.kinds[index]);row=int(self.rows[index])
        e=dict(time=int(self.times[index]),kind=('SUBMIT','START','END')[code],job_id=self.ids[row])
        if code==0:e['request']=self.requests[row]
        return e
    def advance(self,state,t,intervention=None):
        # The schedule gates delivery. No future event payload is deserialized.
        boundary=int(np.searchsorted(self.times,t,side='left'))
        assert boundary>=self.cursor
        for i in range(self.cursor,boundary):
            e=self.event(i)
            if intervention is not None:e=intervention(e,i)
            state.apply(e,t)
        self.cursor=boundary

class PerturbedFutureStream:
    """Lazy all-suffix intervention. Every future timestamp moves +1 year;
    every future identity/type/payload is poisoned. Prefix events are identical.
    Lazy representation avoids copying ~1M events for each of 1,024 tests.
    """
    def __init__(self,source,t,cursor):
        self.source=source;self.cut=int(np.searchsorted(source.times,t,'left'))
        self.threshold=t;self.cursor=cursor;self.future_payload_reads=0
    def event(self,i):
        if i>=self.cut:
            self.future_payload_reads+=1
            raise AssertionError('Poisoned future payload read')
        return self.source.event(i)
    def advance(self,state,t):
        assert t==self.threshold
        # All transformed suffix times >=threshold+365d; no suffix delivery.
        boundary=self.cut
        for i in range(self.cursor,boundary):state.apply(self.event(i),t)
        self.cursor=boundary

def value_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame,index=False).to_numpy().tobytes()).hexdigest()
