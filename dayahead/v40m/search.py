"""Typed UID search with exact source keys and content hash deduplication."""
from .forensic import *
import gzip
import tarfile

TOKENS = ('job','actual','scheduler','kestrel','observation','execution','allocation','node',
 'partition','snapshot','manifest','receipt','lineage','binding','census','authority','freeze',
 'handoff','readme','datacard','source','contract','decision','segment','reference','placement')
TEXT = {'.json','.jsonl','.csv','.tsv','.txt','.md','.log','.yaml','.yml','.slurm','.out'}
TIME_SITE = re.compile(r'start|end|finish|site|aidc|node|partition|segment|active|migration|state|gpu|submit|authority|source|domain|case|day|baseline',re.I)

def safe_value(x):
    if hasattr(x,'tolist'):x=x.tolist()
    if isinstance(x,dict):return {str(k):safe_value(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [safe_value(v) for v in x]
    if isinstance(x,float) and not pd.notna(x):return None
    if isinstance(x,(datetime,pd.Timestamp)):return x.isoformat()
    return x

def uid_value(value):
    if isinstance(value,(str,int)) and not isinstance(value,bool):return str(value)
    return None

def inspect_json(node,wanted):
    found=[];allkeys=set()
    def walk(x,ptr='',context=None):
        context=dict(context or {})
        if isinstance(x,dict):
            allkeys.update(x)
            for k in ('day','date','case','case_id','baseline','authority_kind','domain','execution_domain'):
                if k in x and isinstance(x[k],(str,int)):context[k]=x[k]
            ids={uid_value(x[k]) for k in UID_KEYS & x.keys()} & wanted
            for uid in sorted(ids):
                fields={k:safe_value(v) for k,v in x.items() if k in UID_KEYS or TIME_SITE.search(k)}
                found.append({'uid':uid,'row_key':'json_pointer:'+ptr,'fields':fields,'context':context})
            for k,v in x.items():
                key=str(k).replace('~','~0').replace('/','~1')
                if str(k) in wanted:
                    fields=safe_value(v) if isinstance(v,dict) else {'value':safe_value(v)}
                    found.append({'uid':str(k),'row_key':'json_pointer:'+ptr+'/'+key,'fields':fields,'context':context})
                if isinstance(v,(dict,list)):walk(v,ptr+'/'+key,context)
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)):walk(v,ptr+'/'+str(i),context)
    walk(node)
    return sorted(allkeys),found

def parse_parquet(source,wanted):
    pf=pq.ParquetFile(source);cols=pf.schema_arrow.names
    ids=UID_KEYS & set(cols)
    if not ids:return cols,[],'PARQUET_SCHEMA_NO_UID_KEY'
    selected=[k for k in cols if k in UID_KEYS or TIME_SITE.search(k)]
    sightings=[];offset=0
    for batch in pf.iter_batches(batch_size=65536,columns=selected):
        frame=batch.to_pandas()
        mask=pd.Series(False,index=frame.index)
        for k in ids:mask |= frame[k].astype(str).isin(wanted)
        for i,r in frame.loc[mask].iterrows():
            fields={k:safe_value(v) for k,v in r.to_dict().items()}
            for uid in sorted({str(r[k]) for k in ids} & wanted):
                sightings.append({'uid':uid,'row_key':f'parquet_row_0based:{offset+int(i)};uid={uid}', 'fields':fields,'context':{}})
        offset+=len(frame)
    return cols,sightings,'PARQUET_TYPED_UID_ROWS_SEARCHED'

def parse_bytes(raw,suffix,wanted):
    if suffix=='.parquet':return parse_parquet(io.BytesIO(raw),wanted)
    text=raw.decode('utf-8-sig',errors='replace')
    if text.startswith('version https://git-lfs.github.com/spec/v1'):
        return [],[],'GIT_LFS_POINTER_CONTENT_NOT_AVAILABLE'
    if suffix=='.json':
        cols,rows=inspect_json(json.loads(text),wanted)
        return cols,rows,'JSON_FULL_TYPED_SEARCH'
    if suffix in ('.jsonl',):
        cols=set();rows=[]
        for n,line in enumerate(text.splitlines(),1):
            if not line.strip():continue
            k,r=inspect_json(json.loads(line),wanted);cols.update(k)
            for item in r:item['row_key']=f'line:{n}/'+item['row_key']
            rows.extend(r)
        return sorted(cols),rows,'JSONL_TYPED_SEARCH'
    if suffix in ('.csv','.tsv'):
        reader=csv.DictReader(io.StringIO(text),delimiter='\t' if suffix=='.tsv' else ',')
        cols=reader.fieldnames or [];ids=UID_KEYS & set(cols)
        if not ids:return cols,[],'DELIMITED_SCHEMA_NO_UID_KEY'
        rows=[]
        for n,r in enumerate(reader,2):
            for uid in sorted({r[k] for k in ids} & wanted):
                rows.append({'uid':uid,'row_key':f'csv_record_1based:{n-1};uid={uid}',
                    'fields':{k:v for k,v in r.items() if k and (k in UID_KEYS or TIME_SITE.search(k))},'context':{}})
        return cols,rows,'DELIMITED_TYPED_SEARCH'
    # Text hits are navigation evidence only and never become execution authority.
    rows=[]
    for n,line in enumerate(text.splitlines(),1):
        ids=set(re.findall(r'(?<![\d.])\d{5,12}(?![\d.])',line)) & wanted
        for uid in sorted(ids):rows.append({'uid':uid,'row_key':f'line:{n}',
            'fields':{'text_excerpt':line[:800]},'context':{'text_only':True}})
    return [],rows,'TEXT_UID_NAVIGATION_ONLY'

def reason(path):
    p=Path(path);low=str(p).lower();name=p.name.lower()
    if p.suffix.lower() not in TEXT | {'.parquet','.zip','.gz','.tgz','.tar'}:
        return 'NOT_PARSED_BINARY_CODE_OR_NONRECORD_FORMAT'
    if any(k in low for k in ('/models/','\\models\\','encrypted_embeddings')):
        return 'NOT_PARSED_MODEL_OR_ENCRYPTED_EMBEDDINGS_NOT_EXECUTION_RECORD'
    if 'gpt_troubleshooting_handoffs' in low and not any(k in name for k in
            ('job','aidc','kestrel','manifest','handoff','source','execution','allocation','freeze','receipt')):
        return 'NOT_PARSED_EARLY_CAMPAIGN_MOBILITY_ELECTRICAL_SOLVER_AUDIT_OUTSIDE_CASE_LINEAGE'
    if any(k in low for k in ('dataset312','h100b200','08_nlr_kestrel_h100')):
        return 'NOT_PARSED_EXPERIMENTAL_POWER_BENCHMARK_DIFFERENT_JOB_ID_DOMAIN'
    if p.suffix.lower()=='.parquet':return None
    if any(k in name for k in TOKENS):return None
    if any(k in low for k in ('kestrel','scheduler','handoff_results','exact_plot_source','troubleshooting_handoffs')):return None
    if p.suffix.lower() in ('.zip','.tgz','.tar'):return None
    return 'NOT_PARSED_NAME_OUTSIDE_JOB_AUTHORITY_OR_LINEAGE_CANDIDATES'

def disposition(path,fields,context):
    low=str(path).lower()
    if context.get('text_only'):return 'NAVIGATION_TEXT_NOT_AUTHORITY'
    if 'job-anon.zip' in low and 'parquet_row' not in low:
        return 'RAW_KESTREL_OBSERVATION_NOT_COUNTERFACTUAL_ADMISSION'
    if 'frozen_job_observations' in low:return 'DERIVED_RAW_OBSERVATION_VERIFY_AGAINST_ARCHIVE'
    if any(k in low for k in ('decision','planning','snapshot','placement','reference_compute')):
        return 'PLANNING_OR_SYNTHETIC_SNAPSHOT_NOT_ACTUAL_AUTHORITY'
    if any(k in low for k in ('v40i','v40h','v40j','v40k','site_audit')):
        return 'PRIOR_DIAGNOSTIC_OR_MODEL_ARTIFACT_NOT_NEW_AUTHORITY'
    if any(k in low for k in ('job_ledger','rack_ledger','job_gpu_contributions','segment')):
        return 'HISTORICAL_EXECUTION_CANDIDATE_REQUIRES_PRODUCER_AND_CASE_BINDING'
    return 'UNADJUDICATED_TYPED_UID_CANDIDATE'

def run():
    manifest=read(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json')
    assert sha(manifest['inventory']['path'])==manifest['inventory']['sha256']
    inventory=pd.read_parquet(manifest['inventory']['path']).to_dict('records')
    identity=read(OUT/'V40M_72_BLOCKER_IDENTITY.json')
    wanted={u for c in identity['cases'] for u in c['all_UIDs']}
    cache={};results=[];matches=[];members=[]
    # Search source families in the requested order, stable within each family.
    inventory.sort(key=lambda r:(r['family'],r['path']))
    for n,r in enumerate(inventory):
        p=guard(r['path']);entry={**r,'sha256':None,'parsed':False,'reason':reason(p)}
        if entry['reason']:
            results.append(entry);continue
        try:
            current=p.stat()
            if current.st_size!=r['bytes'] or abs(current.st_mtime_ns-r['mtime_ns'])>1000:
                raise ValueError('SOURCE_CHANGED_AFTER_MANIFEST_FREEZE')
            h=sha(p);entry['sha256']=h
            if h in cache:
                entry.update(parsed=True,reason='HASH_IDENTICAL_TO_PARSED_SOURCE',canonical_path=cache[h],matching_rows=None)
                results.append(entry);continue
            suffix=p.suffix.lower()
            if suffix=='.parquet':
                with p.open('rb') as f:prefix=f.read(50)
                if prefix.startswith(b'version https://git-lfs'):
                    cols,rows,why=[],[],'GIT_LFS_POINTER_CONTENT_NOT_AVAILABLE'
                else:cols,rows,why=parse_parquet(p,wanted)
            elif suffix in ('.zip','.tgz','.tar') or (suffix=='.gz' and p.name.endswith('.tar.gz')):
                rows=[];cols=[]
                if suffix=='.zip':
                    archive=zipfile.ZipFile(p)
                    listing=[(x.filename,x.file_size) for x in archive.infolist() if not x.is_dir()]
                    get=archive.read
                else:
                    archive=tarfile.open(p,'r:*')
                    listing=[(x.name,x.size) for x in archive.getmembers() if x.isfile()]
                    get=lambda name:archive.extractfile(name).read()
                with archive:
                    for name,size in listing:
                        if 'v40l' in name.lower():continue
                        m={'archive_path':str(p),'archive_sha256':h,'member':name,'bytes':size,'parsed':False}
                        ext=Path(name).suffix.lower()
                        if ext not in TEXT | {'.parquet'}:
                            m['reason']='ARCHIVE_MEMBER_NONRECORD_FORMAT';members.append(m);continue
                        if not ('job-anon' in str(p) or any(t in name.lower() for t in TOKENS)):
                            m['reason']='ARCHIVE_MEMBER_OUTSIDE_JOB_LINEAGE';members.append(m);continue
                        raw=get(name);mh=hashlib.sha256(raw).hexdigest();m['sha256']=mh
                        try:
                            mc,mr,mwhy=parse_bytes(raw,ext,wanted)
                            m.update(parsed=True,reason=mwhy,schema=mc,matching_rows=len(mr))
                            for row in mr:
                                row.update(source_path=str(p),source_sha256=h,member=name,member_sha256=mh,family=r['family'])
                                row['disposition']=disposition(p,row['fields'],row['context'])
                                matches.append(row)
                        except Exception as e:m.update(reason='MEMBER_PARSE_ERROR',error=repr(e))
                        members.append(m)
                why='ARCHIVE_MEMBER_CENSUS_AND_TYPED_SEARCH'
            else:
                raw=gzip.open(p,'rb').read() if suffix=='.gz' else p.read_bytes()
                cols,rows,why=parse_bytes(raw,'.jsonl' if suffix=='.gz' else suffix,wanted)
            entry.update(parsed=why!='GIT_LFS_POINTER_CONTENT_NOT_AVAILABLE',reason=why,schema=cols,matching_rows=len(rows))
            for row in rows:
                row.update(source_path=str(p),source_sha256=h,member=None,member_sha256=None,family=r['family'])
                row['disposition']=disposition(p,row['fields'],row['context'])
                matches.append(row)
            if entry['parsed']:cache[h]=str(p)
        except Exception as e:
            entry.update(parsed=False,reason='READ_OR_PARSE_ERROR',error=repr(e))
        results.append(entry)
        if n%500==0:
            print('search',n,'/',len(inventory),'matched rows',len(matches),'unique content',len(cache),flush=True)
    pd.DataFrame([{**r,'schema':dumps(r.get('schema',[]))} for r in results]).to_parquet(OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet',index=False)
    write('V40M_ARCHIVE_MEMBER_CENSUS.json',members)
    serialized=[{**r,'fields':dumps(r['fields']),'context':dumps(r['context'])} for r in matches]
    pd.DataFrame(serialized).to_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet',index=False)
    family_rows=[]
    for f,title in FAMILIES.items():
        rr=[r for r in results if r['family']==f]
        family_rows.append({'family':f,'title':title,'file_count':len(rr),'total_bytes':sum(r['bytes'] for r in rr),
          'parsed_files':sum(r['parsed'] for r in rr),'not_parsed_files':sum(not r['parsed'] for r in rr),
          'source_SHA256_count':sum(bool(r['sha256']) for r in rr),'reasons':dict(Counter(r['reason'] for r in rr)),
          'inventory_sha256':digest(rr)})
    write('V40M_AUTHORITY_SOURCE_CENSUS.json',{'created_at':now(),'search_manifest':record(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json'),
      'families':family_rows,'inventory_errors':manifest['inventory_errors'],
      'archive_members':record(OUT/'V40M_ARCHIVE_MEMBER_CENSUS.json'),'search_results':record(OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet'),
      'typed_sightings':record(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet'),'typed_sighting_count':len(matches),
      'coverage_claim':'All inventoried sources have parsed/not-parsed disposition. Exclusions/unavailable inputs are not evidence of absence.'})
    print('SEARCH COMPLETE',len(results),len(matches),'sightings',flush=True)

if __name__=='__main__':run()
