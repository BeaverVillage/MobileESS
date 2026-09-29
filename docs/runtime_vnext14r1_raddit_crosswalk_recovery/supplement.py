from common import *
import ast
e=pd.read_parquet(LOCAL/'EMBEDDING_SHARED_METADATA.parquet');h=pd.read_parquet(LOCAL/'HISTORIC_SHARED_METADATA.parquet')
l=pd.read_parquet(LOCAL/'EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet')
u=l[l.holdout_consistent.eq(True)].sort_values('embedding_global_row')
idx=u.historic_row.to_numpy(dtype=np.int64);delta=np.diff(idx)
bound=[]
for chunk,g in u.groupby('embedding_chunk',sort=True):
    bound.append(dict(chunk=int(chunk),first_embedding=int(g.embedding_global_row.iloc[0]),last_embedding=int(g.embedding_global_row.iloc[-1]),first_historic=int(g.historic_row.iloc[0]),last_historic=int(g.historic_row.iloc[-1]),unique_rows=len(g)))
keys=['submit_time','end_time','wallclock_used_sec','avg_power_per_node']
members=h.merge(e[keys].drop_duplicates(),on=keys,validate='many_to_one').sort_values('historic_row')
member_ids=members.historic_row.to_numpy();missing=h[~h.historic_row.isin(member_ids)]
diagnostic=dict(EMBEDDING_ORDER_RELATION='UNPROVEN',reason='Exact raw-representation subset has unresolved timestamp authority and 5458 duplicate-key embedding rows. Do not assign duplicates by order.',unique_pair_rows=len(u),adjacent_inversions=int((delta<0).sum()),monotonic_increasing=bool((delta>0).all()),source_index_gap_count=int((delta>1).sum()),source_index_gap_sum=int((delta[delta>1]-1).sum()),duplicate_source_indices=int(pd.Series(idx).duplicated().sum()),raw_unique_direct_prefix=bool(np.array_equal(idx,u.embedding_global_row.to_numpy())),unique_index_offset_min=int((idx-u.embedding_global_row.to_numpy()).min()),unique_index_offset_max=int((idx-u.embedding_global_row.to_numpy()).max()),set_membership_historic_rows=len(members),set_missing_historic_rows=len(missing),set_member_min=int(member_ids.min()),set_member_max=int(member_ids.max()),set_membership_contiguous_suffix=bool(np.array_equal(member_ids,np.arange(len(h)-len(e),len(h)))),chunk_boundaries=bound)
write('EMBEDDING_ORDER_AUDIT.json',diagnostic)
floats={}
pairs=h.iloc[idx].reset_index(drop=True);ep=e.iloc[u.embedding_global_row.to_numpy()].reset_index(drop=True)
for c in ['wallclock_used_sec','avg_power_per_node']:
    a=pairs[c].to_numpy();b=ep[c].to_numpy();floats[c]=dict(rows=len(a),numeric_unequal=int((a!=b).sum()),binary_unequal=int((a.view('uint64')!=b.view('uint64')).sum()))
amb=l[l.diagnostic_status.eq('AMBIGUOUS')].embedding_global_row.to_numpy();amb_e=e.iloc[amb]
write('EXACT_SHARED_FIELD_SUPPLEMENT.json',dict(float64_bitwise=floats,ambiguous_embedding_rows=len(amb),distinct_ambiguous_all_five_field_keys=len(amb_e[['submit_time','start_time','end_time','wallclock_used_sec','avg_power_per_node']].drop_duplicates()),ambiguous_EKEY2_keys=len(amb_e[keys].drop_duplicates()),membership_missing_submit_min_us=int(missing.submit_time.min()),membership_missing_submit_max_us=int(missing.submit_time.max()),all_timestamp_null_sentinels={label:{c:int((d[c]==np.iinfo(np.int64).min).sum()) for c in ['submit_time','start_time','end_time']} for label,d in [('historic',h),('embedding',e)]}))
# Targeted read-only GitHub authority queries; no external communication or mutation.
public=[]
for endpoint in ['repos/NatLabRockies/raddit/issues?state=all&per_page=100','repos/NatLabRockies/raddit/pulls?state=all&per_page=100','repos/NatLabRockies/raddit/branches?per_page=100','repos/NatLabRockies/raddit/tags?per_page=100','repos/NatLabRockies/raddit/compare/ae1bf132addb41b469f3ef25a7626fe5ab06bc81...jdseng:main']:
    data=json.loads(subprocess.check_output(['gh','api',endpoint],cwd=REPO))
    if '/compare/' in endpoint:data={k:data[k] for k in ['status','ahead_by','behind_by','total_commits']}
    public.append(dict(url='https://api.github.com/'+endpoint,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),response=data))
write('PUBLIC_GITHUB_RECEIPTS.json',public)
pickaxes={}
for term in ['enc_embedding_int8','job_strings_','encrypted_embeddings','wallclock_used_sec']:
    pickaxes[term]=git('log','--all','--full-history','--format=%H %aI %s','-S',term,'--','*.py','*.md','*.ipynb',cwd=RAD)
write('GIT_PICKAXE_AND_LFS_AUDIT.json',dict(pickaxes=pickaxes,remote_heads=git('ls-remote','--heads','--tags','origin',cwd=RAD),lfs_pointer_history=git('log','--all','--format=%H %aI %s','--','data/encrypted_embeddings',cwd=RAD),current_lfs_payload_proof='V14 RADDIT_EMBEDDING_PROVENANCE_AUDIT.json: all 45 pointers match SHA256 payload; V14R1 revalidated raw size/mtime. Source timestamps/export filter absent from pointers.'))
v42=REPO.parent/'v42_integrated_pr/v42/runtime_provider_contract.py';s=v42.read_text(encoding='utf-8');tree=ast.parse(s)
allow=None
for n in tree.body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SUBMISSION_FEATURES' for t in n.targets):allow=sorted(ast.literal_eval(n.value.args[0]))
assert allow is not None
inputs=['script','submit_line','name','account','user','partition','qos','job_type']
write('NEW_JOB_SEMANTIC_CALLABILITY_AUDIT.json',dict(HISTORICAL_EMBEDDING_CROSSWALK_PROVEN=False,NEW_JOB_SEMANTIC_INPUT_AVAILABLE=False,NEW_JOB_EMBEDDING_PIPELINE_REPRODUCIBLE=False,read_only=True,source=dict(path=str(v42),sha256=sha(v42),lines=[10,11,19,34]),authorized_submission_features=allow,semantic_inputs=[dict(field=c,available_in_inspected_contract=c in allow) for c in inputs],missing_inputs=[c for c in inputs if c not in allow],pipeline='Public Linq-Embed-Mistral last-token L2 pipeline exists; model/tokenizer revision not pinned; distributed encrypted/int8 export transformation and coordinate-space authority absent. No inference performed.',scope='Current V42 SubmissionRuntimeRequest contract inspected statically; absence is not a claim about every possible future scheduler API.'))
print(json.dumps(clean({k:v for k,v in diagnostic.items() if k!='chunk_boundaries'})));print(floats)
