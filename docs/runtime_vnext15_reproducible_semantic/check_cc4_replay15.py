"""No fit: compare real stored CC4 state to future-facing record reconstruction."""
from common15 import *
sys.path.insert(0,str(REPO))
from v42.semantic_adapter import SemanticFeatureAdapter,historical_payload,SubmissionSemanticRecord
from v42.semantic_state import submission_state
from v42.semantic_integration import FrozenSemanticClusters

def main():
    adapter=SemanticFeatureAdapter.load(LOCAL/'cc4_adapter')
    path=LOCAL/'cc4_adapter/kmeans_centers.npy';clusters=FrozenSemanticClusters(path,sha(path))
    try:FrozenSemanticClusters(path,'0'*64)
    except ValueError as e:assert str(e)=='CLUSTER_BUNDLE_INTEGRITY_FAILURE'
    else:raise AssertionError('INVALID_DIGEST_ACCEPTED')
    g=pd.read_parquet(LOCAL/'GPU_SUBMISSION_METADATA.parquet').sort_values(['submit_time','id'])
    ledger=pd.read_csv(LOCAL/'CC4_DAY_LEDGER_PREAPRIL.csv');states=np.load(LOCAL/'CC4_SEMANTIC_STATES.npz')['values']
    candidates=np.flatnonzero(ledger.target_day.ge('2024-09-01')&ledger.preApril_maturity)
    ids=sorted(np.random.default_rng(1515).choice(candidates,size=12,replace=False));checks=[]
    for i in ids:
        issue=pd.Timestamp(ledger.iloc[i].issue_time);past=g[g.submit_time.lt(issue)&g.submit_time.ge(issue-pd.Timedelta(hours=72))]
        records=[SubmissionSemanticRecord(str(r['id']),str(r['submit_time']),str(r['submit_time']),historical_payload(r)) for r in past.to_dict('records')]
        actual,_,_=submission_state(adapter,records,str(issue),clusters)
        np.testing.assert_array_equal(actual,states[i])
        # Equality-at-issue and later records are rejected before accessing their poisoned payload.
        poison=SubmissionSemanticRecord('future',str(issue),str(issue),None)
        changed,_,_=submission_state(adapter,records+[poison],str(issue),clusters)
        np.testing.assert_array_equal(changed,actual)
        checks.append(dict(day=str(ledger.iloc[i].target_day),past_records=len(records),bitwise_state_parity=True,future_ignored=True))
    write('CC4_FUTURE_INTERFACE_PARITY.json',dict(time=now(),PASS=True,checks=checks,dimensions=201,
        historical_to_record_bitwise=True,stored_cluster_centers_callable=True,model_refits=0,
        cluster_centers=rec(path),scope='Replay of the same anonymized namespace; real-site identity alignment not asserted'))
    print('CC4 FUTURE INTERFACE PARITY PASS',len(checks),flush=True)

if __name__=='__main__':main()
