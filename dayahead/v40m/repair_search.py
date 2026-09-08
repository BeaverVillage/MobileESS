"""Retry inventoried UNC files through Windows extended paths; no scope expansion."""
from .search import *

def run():
    source_path=OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet'
    before=record(source_path);sources=pd.read_parquet(source_path)
    census=read(OUT/'V40M_AUTHORITY_SOURCE_CENSUS.json')
    sightings=pd.read_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet')
    wanted={u for c in read(OUT/'V40M_72_BLOCKER_IDENTITY.json')['cases'] for u in c['all_UIDs']}
    cache={r.sha256:r.path for r in sources[sources.parsed & (sources.reason!='HASH_IDENTICAL_TO_PARSED_SOURCE')].itertuples()}
    repairs=[];newrows=[]
    for n,(i,r) in enumerate(sources[sources.reason=='READ_OR_PARSE_ERROR'].iterrows()):
        path=r.path
        if not path.startswith('\\\\wsl'):
            repairs.append({'path':path,'original_error':r.error,'disposition':'CORRUPT_HISTORICAL_TEST_FIXTURE_NOT_AUTHORITY' if 'pytest' in path.lower() else 'UNRESOLVED_READ_ERROR'})
            continue
        guard(path);extended=Path('\\\\?\\UNC\\'+path[2:])
        try:
            st=extended.stat()
            assert st.st_size==r.bytes and abs(st.st_mtime_ns-r.mtime_ns)<=1000
            raw=extended.read_bytes();h=hashlib.sha256(raw).hexdigest()
            sources.at[i,'sha256']=h
            if h in cache:
                sources.at[i,'reason']='HASH_IDENTICAL_TO_PARSED_SOURCE'
                sources.at[i,'canonical_path']=cache[h]
            else:
                cols,rows,why=parse_bytes(raw,Path(path).suffix.lower(),wanted)
                sources.at[i,'reason']=why;sources.at[i,'schema']=dumps(cols);sources.at[i,'matching_rows']=len(rows)
                for row in rows:
                    row.update(source_path=path,source_sha256=h,member=None,member_sha256=None,family=r.family)
                    row['disposition']=disposition(path,row['fields'],row['context'])
                    row['fields']=dumps(row['fields']);row['context']=dumps(row['context']);newrows.append(row)
                cache[h]=path
            sources.at[i,'parsed']=True;sources.at[i,'error']=None
            repairs.append({'path':path,'source_sha256':h,'original_error':r.error,'disposition':'EXTENDED_UNC_READ_RECOVERED'})
        except Exception as e:repairs.append({'path':path,'original_error':r.error,'disposition':'RETRY_FAILED','retry_error':repr(e)})
        if n%1000==0:print('UNC retry',n,'new sightings',len(newrows),flush=True)
    if newrows:sightings=pd.concat([sightings,pd.DataFrame(newrows)],ignore_index=True)
    sources.to_parquet(source_path,index=False)
    sightings.to_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet',index=False)
    for f in census['families']:
        rr=sources[sources.family==f['family']]
        f.update(parsed_files=int(rr.parsed.sum()),not_parsed_files=int((~rr.parsed).sum()),
           source_SHA256_count=int(rr.sha256.notna().sum()),reasons=dict(Counter(rr.reason)),
           inventory_sha256=digest(json.loads(rr.to_json(orient='records'))))
    census.update(search_results=record(source_path),typed_sightings=record(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet'),typed_sighting_count=len(sightings))
    write('V40M_AUTHORITY_SOURCE_CENSUS.json',census)
    write('V40M_UNC_PATH_RECOVERY.json',{'before':before,'after':record(source_path),'new_sightings':len(newrows),
        'counts':dict(Counter(x['disposition'] for x in repairs)),'repairs':repairs,'manifest_scope_changed':False})
    print('RECOVERED',Counter(x['disposition'] for x in repairs),'new sightings',len(newrows),flush=True)

if __name__=='__main__':run()
