from common import *
h=pd.read_parquet(LOCAL/'HISTORIC_SHARED_METADATA.parquet');e=pd.read_parquet(LOCAL/'EMBEDDING_SHARED_METADATA.parquet')
l=pd.read_parquet(LOCAL/'EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet');u=l[l.holdout_consistent.eq(True)].sort_values('embedding_global_row')
keys=['submit_time','end_time','wallclock_used_sec','avg_power_per_node']
hg=h.groupby(keys,sort=False).size().rename('historic_count').reset_index()
eg=e.groupby(keys,sort=False).size().rename('embedding_count').reset_index()
m=hg.merge(eg,on=keys,how='inner',validate='one_to_one')
assert (m.historic_count==m.embedding_count).all()
membership=h[['historic_row','job_id']+keys].merge(eg,on=keys,how='left',validate='many_to_one')
membership=membership[['historic_row','job_id','embedding_count']]
membership['status']=np.where(membership.embedding_count.isna(),'NO_RAW_METADATA_KEY_IN_EMBEDDING','RAW_METADATA_SET_MEMBER_ONLY_NOT_AUTHORIZED')
membership.to_parquet(LOCAL/'HISTORIC_RAW_MEMBERSHIP_NEGATIVE_LEDGER.parquet',index=False)
order=read(ROOT/'EMBEDDING_ORDER_AUDIT.json')
# Fenwick counts all out-of-order pairs, distinct from adjacent descents.
tree=[0]*(len(h)+2);inversions=0;seen=0
for row in u.historic_row.to_numpy(dtype=np.int64):
    pos=int(row)+1;j=pos;leq=0
    while j:leq+=tree[j];j-=j&-j
    inversions+=seen-leq;seen+=1
    while pos<len(tree):tree[pos]+=1;pos+=pos&-pos
order['total_pair_inversions_unique_raw_candidates']=inversions
order['matched_key_multiplicity_identical']=True
for prev,cur in zip(order['chunk_boundaries'][:-1],order['chunk_boundaries'][1:]):
    cur['historic_delta_from_previous_chunk_last_unique']=cur['first_historic']-prev['last_historic']
    cur['embedding_delta_from_previous_chunk_last_unique']=cur['first_embedding']-prev['last_embedding']
order['monotonic_chunk_boundary_transitions']=sum(c.get('historic_delta_from_previous_chunk_last_unique',0)>0 for c in order['chunk_boundaries'][1:])
order['gap_statistics_scope']='Positive adjacent differences among unique raw candidates only; reordered sequence gaps overlap and are not missing-row counts.'
write('EMBEDDING_ORDER_AUDIT.json',order)
print('all-pair inversions',inversions,'monotonic boundaries',order['monotonic_chunk_boundary_transitions'])
