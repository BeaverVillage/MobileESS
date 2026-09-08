"""Document recoverable long-path metadata from the original census error list."""
from .search import *

def run():
    manifest=read(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json');rows=[];remaining=[]
    source_path=OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet';sources=pd.read_parquet(source_path)
    prior_addendum=OUT/'V40M_INVENTORY_RECOVERY_ADDENDUM.json'
    if prior_addendum.exists():
        previous={r['path'] for r in read(prior_addendum)['rows']}
        sources=sources[~sources.path.isin(previous)]
    sightings=pd.read_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet');new_sightings=[]
    wanted={u for c in read(OUT/'V40M_72_BLOCKER_IDENTITY.json')['cases'] for u in c['all_UIDs']}
    cache={r.sha256:r.path for r in sources[sources.parsed & (sources.reason!='HASH_IDENTICAL_TO_PARSED_SOURCE')].itertuples()}
    for e in manifest['inventory_errors']:
        p=e['path']
        if '[WinError 3]' not in e['reason']:
            remaining.append(e);continue
        guard(p);extended=Path('\\\\?\\'+p)
        try:
            root=next(r['path'] for r in manifest['roots'] if norm(p).startswith(norm(r['path'])+'\\'))
            files=[f for f in extended.rglob('*') if f.is_file() and 'v40l' not in str(f).lower()] if extended.is_dir() else [extended]
            for f in files:
                original=str(f)[4:];guard(original);st=f.stat()
                why=('NOT_PARSED_RECOVERED_POWER_BENCHMARK_METADATA_DIFFERENT_JOB_DOMAIN'
                     if any(x in original.lower() for x in ('dataset312','figshare31654879')) else reason(original))
                row={'path':original,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'root':root,'family':family(original),
                     'suffix':Path(original).suffix.lower(),'sha256':None,'parsed':False,'reason':why,'schema':'[]'}
                if why is None:
                    raw=f.read_bytes();h=hashlib.sha256(raw).hexdigest();row['sha256']=h
                    if h in cache:row.update(parsed=True,reason='HASH_IDENTICAL_TO_PARSED_SOURCE',canonical_path=cache[h])
                    else:
                        cols,found,status=parse_bytes(raw,Path(original).suffix.lower(),wanted)
                        row.update(parsed=True,reason=status,schema=dumps(cols),matching_rows=len(found))
                        for hit in found:
                            hit.update(source_path=original,source_sha256=h,member=None,member_sha256=None,family=row['family'])
                            hit['disposition']=disposition(original,hit['fields'],hit['context'])
                            hit['fields']=dumps(hit['fields']);hit['context']=dumps(hit['context']);new_sightings.append(hit)
                        cache[h]=original
                rows.append(row)
        except Exception as exc:remaining.append({**e,'retry_error':repr(exc)})
    addendum=write('V40M_INVENTORY_RECOVERY_ADDENDUM.json',{'created_at':now(),
        'original_manifest':record(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json'),'original_error_count':len(manifest['inventory_errors']),
        'recovered_file_count':len(rows),'recovered_bytes':sum(x['bytes'] for x in rows),'rows':rows,
        'remaining_inventory_errors':remaining,'scope_expansion':False,
        'reason':'Original error paths only; sizes recovered before excluding independent benchmark domains.'})
    if rows:sources=pd.concat([sources,pd.DataFrame(rows)],ignore_index=True)
    sources.to_parquet(source_path,index=False)
    if new_sightings:
        sightings=pd.concat([sightings,pd.DataFrame(new_sightings)],ignore_index=True).drop_duplicates(['source_path','row_key','uid'])
        sightings.to_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet',index=False)
    census=read(OUT/'V40M_AUTHORITY_SOURCE_CENSUS.json')
    for f in census['families']:
        rr=sources[sources.family==f['family']]
        f.update(file_count=len(rr),total_bytes=int(rr.bytes.sum()),parsed_files=int(rr.parsed.sum()),
            not_parsed_files=int((~rr.parsed).sum()),source_SHA256_count=int(rr.sha256.notna().sum()),
            reasons=dict(Counter(rr.reason)),inventory_sha256=digest(json.loads(rr.to_json(orient='records'))))
    census.update(search_results=record(source_path),inventory_errors=remaining,inventory_recovery_addendum=record(addendum),
                  typed_sightings=record(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet'),typed_sighting_count=len(sightings))
    write('V40M_AUTHORITY_SOURCE_CENSUS.json',census)
    print('INVENTORY RECOVERY',len(rows),'remaining',len(remaining),flush=True)

if __name__=='__main__':run()
