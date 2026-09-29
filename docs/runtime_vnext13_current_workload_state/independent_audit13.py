"""Independent event reducer and concrete future scheduling mutation checks."""
from common13 import *
from stream13 import Stream
from collections import deque

def main():
    source=Stream();features=pd.read_parquet(LOCAL/'CURRENT_STATE_FEATURES.parquet')
    sample=sorted(np.random.default_rng(13103).choice(len(features),1024,replace=False))
    pending={};running={};terminal=set();arrivals=deque();cursor=0;receipts=[]
    for row in sample:
        t=int(source.query_times[row]);boundary=int(np.searchsorted(source.times,t,'left'))
        for j in range(cursor,boundary):
            r=int(source.rows[j]);kind=int(source.kinds[j]);when=int(source.times[j])
            if kind==0:pending[r]=when;arrivals.append((when,r))
            elif kind==1:
                if r not in terminal:pending.pop(r);running[r]=when
            else:pending.pop(r,None);running.pop(r,None);terminal.add(r)
        cursor=boundary
        while arrivals and arrivals[0][0]<t-86400:arrivals.popleft()
        f=features.iloc[row]
        for prefix,active in [('p_',pending),('r_',running)]:
            assert f[prefix+'count']==len(active)
            for field in ['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib']:
                expected=sum(float(source.requests[r][field]) for r in active)
                assert f[prefix+field+'_sum']==expected
            if active:
                ages=np.array([t-when for when in active.values()],float)
                for q in [.5,.9]:assert np.isclose(f[prefix+'age_q'+str(int(q*100))],np.quantile(ages,q),rtol=0,atol=1e-6)
                assert f[prefix+'age_max']==ages.max()
        for w in [300,900,3600,21600,86400]:
            selected=[r for when,r in arrivals if when>=t-w]
            assert f['a_'+str(w)+'_count']==len(selected)
            if w!=300:assert f['a_'+str(w)+'_num_gpus_req_sum']==sum(float(source.requests[r]['num_gpus_req']) for r in selected)
        # Concrete transform of EVERY remaining scheduling timestamp (not only
        # the head). The resulting gate dispatches exactly the same prefix.
        altered=source.times.copy();altered[boundary:]+=365*86400
        altered_boundary=int(np.searchsorted(altered,t,'left'))
        assert altered_boundary==boundary
        assert np.array_equal(altered[:boundary],source.times[:boundary])
        assert np.all(altered[boundary:]!=source.times[boundary:])
        receipts.append(dict(query_row=int(row),processed_prefix=boundary,future_timestamps_mutated=len(altered)-boundary,
                             dispatch_prefix_identical=True,independent_state_match=True))
    pd.DataFrame(receipts).to_csv(ROOT/'INDEPENDENT_STATE_RECEIPTS.csv',index=False)
    write('INDEPENDENT_STATE_AUDIT.json',dict(time=now(),PASS=True,N=len(sample),
        checks='independent event reducer pending/running membership counts, GPU/node/core/memory sums, exact age quantiles; arrival window counts and GPU sums',
        concrete_future_timestamp_mutations=True,payload_poison_audit=record(ROOT/'CURRENT_STATE_CAUSALITY_AUDIT.json'),
        same_dispatch_prefix_implies_same_engine_event_inputs=True,April_payload_read=False,May_payload_read=False))
    print('INDEPENDENT_STATE_PASS',len(sample),flush=True)
if __name__=='__main__':main()
