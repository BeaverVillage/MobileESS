from common import *
import pyarrow.parquet as pq
import ast,os
h=pd.read_parquet(R1/'.local/HISTORIC_SHARED_METADATA.parquet');e=pd.read_parquet(R1/'.local/EMBEDDING_SHARED_METADATA.parquet')
members=pd.read_parquet(R1/'.local/HISTORIC_RAW_MEMBERSHIP_NEGATIVE_LEDGER.parquet').sort_values('historic_row')
member=members.embedding_count.notna().to_numpy();unique=members.embedding_count.eq(1).to_numpy();amb=member&~unique
assert member.sum()==1780972 and unique.sum()==1775514 and amb.sum()==5458
rules=[];enrichment=[]
def candidate(name,keep,support='DESCRIPTIVE_ONLY_NO_EXPORT_AUTHORITY'):
    keep=np.asarray(keep,dtype=bool)
    rules.append(dict(rule=name,historic_kept=int(keep.sum()),historic_removed=int((~keep).sum()),equals_embedding_count=int(keep.sum())==1780972,source_support=support,membership_exact_match=bool(np.array_equal(keep,member)),status='DIAGNOSTIC_NOT_APPROVED'))
    for label,mask in [('UNIQUE_RAW',unique),('AMBIGUOUS_RAW',amb),('NO_RAW_MEMBER',~member)]:enrichment.append(dict(rule=name,population=label,rows=int(mask.sum()),satisfying=int((keep&mask).sum()),fraction=float(keep[mask].mean())))
for c in ['wallclock_used_sec','avg_power_per_node']:candidate(c+' nonnull',h[c].notna())
candidate('wallclock_used_sec positive',h.wallclock_used_sec.gt(0));candidate('avg_power_per_node positive',h.avg_power_per_node.gt(0))
candidate('non-null end',h.end_time.ne(np.iinfo(np.int64).min));candidate('submit <= start <= end',(h.submit_time<=h.start_time)&(h.start_time<=h.end_time))
candidate('observed raw-member submit envelope',(h.submit_time>=h.loc[member,'submit_time'].min())&(h.submit_time<=h.loc[member,'submit_time'].max()),'Observed range only; NOT an independently declared export date filter')
pf=pq.ParquetFile(RAD/'data/historic_job_trace.parquet');cats=[]
for c in ['script','submit_line','name','job_type','user','account','qos','partition']:
    d=pf.read(columns=[c]).to_pandas()[c];candidate(c+' not null',d.notna())
    candidate(c+' nonempty string',d.notna()&d.astype('string').str.strip().ne('').fillna(False))
    if c in ['partition','qos','job_type']:
        tmp=pd.DataFrame({'category':d,'population':np.where(unique,'UNIQUE_RAW',np.where(amb,'AMBIGUOUS_RAW','NO_RAW_MEMBER'))})
        for (cat,pop),count in tmp.groupby(['category','population'],dropna=False).size().items():cats.append(dict(field=c,category=cat,population=pop,count=int(count)))
for c in ['nodes_req','processors_req']:
    d=pf.read(columns=[c]).to_pandas()[c];candidate(c+' positive',d.gt(0))
rules.append(dict(rule='CPU/GPU restriction',historic_kept=None,historic_removed=None,equals_embedding_count=None,source_support='historic schema has no explicit GPU count/CPU-exclusive flag; sanitized partition tokens lack authority',membership_exact_match=None,status='NOT_TESTABLE_NO_DIRECT_RESOURCE_TYPE'))
table('SUBSET_FILTER_CANDIDATES.csv',rules);table('SUBSET_MEMBERSHIP_ENRICHMENT.csv',enrichment);table('SUBSET_CATEGORY_COUNTS.csv',cats)
months=pd.to_datetime(h.submit_time,unit='us').dt.strftime('%Y-%m');mdf=pd.DataFrame({'month':months,'population':np.where(unique,'UNIQUE_RAW',np.where(amb,'AMBIGUOUS_RAW','NO_RAW_MEMBER'))})
table('SUBSET_MONTH_COUNTS.csv',[dict(month=m,population=p,count=int(n)) for (m,p),n in mdf.groupby(['month','population']).size().items()])
# All available shared non-vector fields were exhausted in R1; quantify unresolved multiplicities.
keys=['submit_time','end_time','wallclock_used_sec','avg_power_per_node'];g=e.groupby(keys,sort=False).size();sizes=g[g>1].value_counts().sort_index()
table('AMBIGUOUS_MAPPING_FORENSIC.csv',[dict(rows_per_group=int(size),ambiguous_groups=int(n),embedding_rows=int(size*n),historic_rows=int(size*n),shared_fields_tested='submit_time,start_time,end_time,wallclock_used_sec,avg_power_per_node',exact_disambiguation_possible=False,unresolved_rows=int(size*n),row_order_used=False,notes='R1 full-five-field group count equals EKEY2 duplicate-group count; no other shared non-vector metadata') for size,n in sizes.items()])
# Inventory-driven filesystem search, with a current traversal to identify forgotten additions.
inventory=pd.read_csv(V14/'RAW_SOURCE_INVENTORY.csv',dtype=str,keep_default_na=False);known=set(str(Path(r.directory)/r.filename) for r in inventory.itertuples())
pattern=re.compile(r'job_strings|embeddings_.*\.npy|historic_job_trace|encrypted_embeddings|crosswalk|row_id|source_row|mapping|manifest|metadata|export|subset|filter|timezone|int8|Linq|Mistral',re.I)
found=[];visited=0;newpaths=[]
for directory,dirs,files in os.walk(RAW,followlinks=False):
    dirs[:]=[d for d in dirs if d!='.git']
    for name in files:
        p=Path(directory)/name;visited+=1
        if str(p) not in known:newpaths.append(str(p))
        if pattern.search(str(p)):
            st=Path('\\\\?\\'+str(p)).lstat();found.append(dict(path=str(p),search_type='FILENAME',bytes=st.st_size,content_evidence='NOT_AUTHORITY_BY_FILENAME',notes='Known distributed historic/chunk' if 'historic_job_trace' in name or 'encrypted_embeddings' in str(p) else 'Potential intermediate; inspect content if text metadata'))
docs=read(V14/'LOCAL_AUTHORITY_SEARCH.json')['inspected_files'];seen=set();textfiles=0
for r in docs:
    p=Path(r['path'])
    if str(p) in seen or not p.is_file() or p.suffix.lower() not in ['.py','.md','.txt','.json','.yaml','.yml','.toml','.sql','.ipynb']:continue
    seen.add(str(p))
    if p.stat().st_size>20_000_000:continue
    try:
        s=p.read_text(encoding='utf-8-sig',errors='replace')
        if p.suffix=='.ipynb':
            nb=json.loads(s);parts=[]
            for c in nb.get('cells',[]):
                parts.append(''.join(c.get('source',[])))
                for o in c.get('outputs',[]):
                    parts.append(''.join(o.get('text',[])))
                    for mime,val in o.get('data',{}).items():
                        if mime.startswith('text/'):parts.append(''.join(val) if isinstance(val,list) else str(val))
            s='\n'.join(parts)
        textfiles+=1;hits=[line[:500] for line in s.splitlines() if pattern.search(line)]
        if hits:found.append(dict(path=str(p),search_type='TEXT_CONTENT',bytes=p.stat().st_size,content_evidence='\n'.join(hits[:8]),notes='Content lead only; no original export found without direct supporting code/document'))
    except (OSError,ValueError):continue
table('LOCAL_INTERMEDIATE_ARTIFACT_SEARCH.csv',found)
write('LOCAL_SEARCH_RECEIPT.json',dict(root=str(RAW),nested_root=str(RAW/'데이터 센터'),filesystem_files_outside_dotgit=visited,new_paths_since_V14=newpaths,content_files_scanned=textfiles,matched_entries=len(found),dotgit_scope='Handled separately by Git fsck/history; no .git mutation',source_inventory=rec(V14/'RAW_SOURCE_INVENTORY.csv')))
v42=REPO.parent/'v42_integrated_pr';paths=[v42/'v42/runtime_provider_contract.py',v42/'v42/policy.py',v42/'v42/response_policy.py'];classes={}
for p in paths:
    tree=ast.parse(p.read_text(encoding='utf-8'))
    for n in tree.body:
        if isinstance(n,ast.ClassDef) and n.name in ['SubmissionRuntimeRequest','Arrival','ObservedJob']:classes[n.name]=[x.target.id for x in n.body if isinstance(x,ast.AnnAssign) and isinstance(x.target,ast.Name)]
inputs=['user','account','partition','job_type','name','qos','submit_line','script']
table('NEW_JOB_SEMANTIC_INPUT_GAP.csv',[dict(field=c,required_by_raddit=True,available_in_v42=c in ['partition','qos'],available_in_raw_arrival_event=c in classes['Arrival'],privacy_sanitization_issue='Potential identifying/sensitive command or script content; submit-time capture and stable transform policy required' if c not in ['partition','qos'] else 'Scheduler token authority/version required',could_be_added_without_future_info='CONDITIONAL_SUBMIT_DERIVED_CLASSIFIER' if c=='job_type' else 'YES_IF_CAPTURED_AT_ACCEPTED_SUBMISSION',authority='Static V42 SubmissionRuntimeRequest whitelist and Arrival/ObservedJob dataclasses',notes='workload_class is not proven equivalent to RADDiT job_type. No interface changed.' if c=='job_type' else 'Archive hash availability is not original semantic text availability and not an accepted-submission event receipt.') for c in inputs])
write('V42_READONLY_INTERFACE_RECEIPT.json',dict(files=[rec(p) for p in paths],classes=classes,executed=False,raw_arrival_definition='Existing V42 policy.Arrival dataclass, not a decoded April/May trace'))
source_paths=[RAD/'energy_aware_scheduling/scripts/embed_job_scripts.py',RAD/'energy_aware_scheduling/scripts/prep_for_embedding.py',RAD/'energy_aware_scheduling/requirements.txt']
write('EMBEDDING_PIPELINE_REPRODUCIBILITY.json',dict(PUBLIC_LLM_PIPELINE_REPRODUCIBLE=False,DISTRIBUTED_VECTOR_TRANSFORM_REPRODUCIBLE=False,model_name='Linq-AI-Research/Linq-Embed-Mistral',model_revision=None,tokenizer_revision=None,transformers_version=None,quanto_version=None,requirements='Package names only, no version pins in inspected requirements',qint8='Public code: QuantizedModelForCausalLM.quantize(model, weights=qint8, exclude=lm_head); this quantizes model weights, not a proven distributed vector encryption/int8 export',pooling='last non-padding token',normalization='L2 dim=1',max_length=2048,truncation=True,batch_size=2,public_output='embeddings_{batch_number}.npy',distributed_output='enc_embedding_int8 in 40000-row Parquet chunks',distributed_transform='UNRESOLVED',model_downloaded=False,reembedding_rows=0,public_render_outcome_free=True,source=[rec(p) for p in source_paths]))
print('subset rules',len(rules),'count matches',sum(r.get('equals_embedding_count') is True for r in rules),'ambiguous rows',sum(int(a*b) for a,b in sizes.items()),'local entries',len(found),'text files',textfiles,'new paths',len(newpaths))
