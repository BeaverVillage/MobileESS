from common import *
commits=git('rev-list','--all',cwd=RAD).splitlines();blobs={}
for c in commits:
    for line in git('ls-tree','-r',c,cwd=RAD).splitlines():
        meta,path=line.split('\t');mode,typ,oid=meta.split()
        if typ=='blob' and Path(path).suffix in ['.py','.ipynb','.md','.sql','.toml','.yaml','.yml','.json','.txt']:
            blobs.setdefault(oid,[]).append(dict(commit=c,path=path))
terms=re.compile(r'export|encrypt|enc_embedding|job_strings|historic_job_trace|tz_|timezone|cast\(|write_parquet|to_parquet|drop_null|dropna|filter\(|cpu.exclus|crosswalk|anonym|sanitiz|4096|40000',re.I)
sources=[];hits=[]
for oid,refs in blobs.items():
    size=int(git('cat-file','-s',oid,cwd=RAD))
    if size>30_000_000:continue
    s=git('cat-file','blob',oid,cwd=RAD)
    if refs[0]['path'].endswith('.ipynb'):
        try:s='\n'.join(''.join(c.get('source',[])) for c in json.loads(s)['cells'] if c.get('cell_type') in ['code','markdown'])
        except Exception:continue
    sources.append(dict(blob=oid,refs=refs,source=s))
    lines=[dict(line=i+1,text=l[:1000]) for i,l in enumerate(s.splitlines()) if terms.search(l)]
    if lines:hits.append(dict(blob=oid,refs=refs,lines=lines))
write('GIT_HISTORY_SOURCE_AUDIT.json',dict(head=git('rev-parse','HEAD',cwd=RAD),commits=len(commits),refs=git('show-ref',cwd=RAD),tags=git('tag','-l',cwd=RAD),source_blobs=len(sources),hits=hits,deleted=git('log','--all','--diff-filter=D','--summary',cwd=RAD),lfs_history=git('log','--all','--format=%H %aI %s','--','data/encrypted_embeddings','data/historic_job_trace.parquet',cwd=RAD)))
write('.local/HISTORICAL_SOURCE_TEXT.json',sources)
print('commits',len(commits),'sourceblobs',len(sources))
for h in hits:
    for l in h['lines']:
        if re.search(r'tz_|timezone|write_parquet|to_parquet|enc_embedding_int8|dropna|drop_null|filter\(',l['text'],re.I):print(h['refs'][0]['path'],h['blob'][:8],l['line'],l['text'][:260])
