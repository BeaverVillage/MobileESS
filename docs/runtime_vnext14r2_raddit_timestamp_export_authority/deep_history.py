from common import *
import pyarrow.parquet as pq
commits=git('rev-list','--all',cwd=RAD).splitlines();blobs={};versions={}
dates={c:git('show','-s','--format=%cI',c,cwd=RAD) for c in commits}
for c in commits:
    for line in git('ls-tree','-r','-l',c,cwd=RAD).splitlines():
        meta,path=line.split('\t');mode,typ,oid,size=meta.split()
        if typ!='blob':continue
        if Path(path).suffix in ['.py','.ipynb','.md','.sql','.toml','.yaml','.yml','.json','.txt'] or path.endswith('.gitattributes'):
            blobs.setdefault(oid,dict(size=int(size),refs=[]))['refs'].append(dict(commit=c,path=path))
        if path=='data/historic_job_trace.parquet' or re.match(r'data/encrypted_embeddings/chunk_\d+\.parquet$',path):versions.setdefault((path,oid),[]).append(c)
fsck=subprocess.run(['git','fsck','--unreachable','--no-reflogs','--connectivity-only'],cwd=RAD,capture_output=True,text=True)
unreachable=[]
for line in fsck.stdout.splitlines():
    m=re.match(r'unreachable (\w+) (\w+)',line)
    if m:
        typ,oid=m.groups();size=int(git('cat-file','-s',oid,cwd=RAD));unreachable.append(dict(type=typ,oid=oid,size=size))
        if typ=='blob' and size<10_000_000:
            # Content inspection is bounded and excludes opaque binary/model payload.
            b=subprocess.check_output(['git','cat-file','blob',oid],cwd=RAD)
            if b'\x00' not in b[:4096]:blobs.setdefault(oid,dict(size=size,refs=[dict(commit='UNREACHABLE',path='UNKNOWN_UNREACHABLE_BLOB')]))
terms=['encrypted_embeddings','enc_embedding_int8','job_strings','historic_job_trace','submit_time','FixedOffset','tz_localize','tz_convert','timezone','to_parquet','40000','4096']
commands={}
for term in terms:commands['git log --all --full-history -S '+term]=git('log','--all','--full-history','--format=%H %cI %s','-S',term,'--','*.py','*.ipynb','*.md','*.json','*.yaml','.gitattributes',cwd=RAD)
commands['git log --all --oneline --decorate']=git('log','--all','--oneline','--decorate',cwd=RAD)
commands['git log --all --full-history --stat']=git('log','--all','--full-history','--stat',cwd=RAD)
commands['git log --all --name-status --find-renames']=git('log','--all','--format=%H %cI %s','--name-status','--find-renames',cwd=RAD)
commands['git fsck --unreachable --no-reflogs --connectivity-only']=dict(returncode=fsck.returncode,stdout=fsck.stdout,stderr=fsck.stderr)
commands['git grep -n -I -E export terms HEAD']=subprocess.run(['git','grep','-n','-I','-E','enc_embedding_int8|tz_localize|tz_convert|40_?000|to_parquet|write_parquet','HEAD','--','*.py','*.md'],cwd=RAD,capture_output=True,text=True).stdout
commands['git diff initial..HEAD source names']=git('diff','--stat','0c71fa5b76b2b85a6b45059f988fd24599263b8d','HEAD','--','*.py','*.ipynb','*.md','.gitattributes',cwd=RAD)
pattern=re.compile(r'enc_embedding|encrypt|embedding_int8|\bint8\b|quantiz|\bscale\b|chunk_000|40_?000|to_parquet|write_parquet|tz_localize|tz_convert|FixedOffset|timezone|datetime64|submit_time|end_time|historic_job_trace|job_strings|dropna|drop_null|concat|\.npy|filter',re.I)
evidence=[];sources=[];notebook_cells=0;outputs_inspected=0;images_skipped=0
for oid,info in blobs.items():
    if info['size']>30_000_000:continue
    text=git('cat-file','blob',oid,cwd=RAD);path=info['refs'][0]['path'];relevant=[]
    if path.endswith('.ipynb'):
        try:nb=json.loads(text)
        except Exception:continue
        for ci,cell in enumerate(nb.get('cells',[])):
            notebook_cells+=1;code=''.join(cell.get('source',[]));parts=[('SOURCE_CELL',code)]
            for out in cell.get('outputs',[]):
                outputs_inspected+=1
                if 'text' in out:parts.append(('STORED_OUTPUT_TEXT',''.join(out['text'])))
                for mime,val in out.get('data',{}).items():
                    if mime.startswith('text/') or mime=='application/json':parts.append(('STORED_OUTPUT_'+mime,''.join(val) if isinstance(val,list) else json.dumps(val) if isinstance(val,dict) else str(val)))
                    elif mime.startswith('image/'):images_skipped+=1
            for typ,body in parts:
                lines=body.splitlines();hit=[i for i,l in enumerate(lines) if pattern.search(l)]
                if not hit:continue
                excerpts=[]
                for i in hit[:12]:excerpts.extend(lines[max(0,i-1):min(len(lines),i+2)])
                snippet='\n'.join(dict.fromkeys(excerpts))[:6000]
                row=dict(notebook=path,cell_index=ci,execution_count=cell.get('execution_count'),relevant_code_or_output=snippet,authority_type=typ,supports_timezone=bool(re.search(r'FixedOffset|timezone|tz_localize|tz_convert|datetime64|[+-]0[67]:00',snippet,re.I)),supports_subset=bool(re.search(r'filter|dropna|shape|rows|drop_null',snippet,re.I)),supports_export=bool(re.search(r'to_parquet|write_parquet|40_?000|enc_embedding_int8',snippet,re.I)),notes=f'blob {oid}; {len(info["refs"])} historical references; keyword support is a lead, not export authority',commit=info['refs'][0]['commit'])
                evidence.append(row)
        sources.append(dict(blob=oid,refs=info['refs'],kind='notebook',raw_bytes=info['size']))
    else:
        lines=[dict(line=i+1,text=l[:1600]) for i,l in enumerate(text.splitlines()) if pattern.search(l)]
        sources.append(dict(blob=oid,refs=info['refs'],kind='source',hits=lines))
table('NOTEBOOK_PROVENANCE_EVIDENCE.csv',evidence)
lfs=[]
for (path,oid),cs in versions.items():
    size=int(git('cat-file','-s',oid,cwd=RAD));pointer=git('cat-file','blob',oid,cwd=RAD) if size<2048 else ''
    lm=re.search(r'oid sha256:(\w+)',pointer);sm=re.search(r'^size (\d+)',pointer,re.M)
    p=RAD/path;footer=pq.ParquetFile(p) if p.is_file() and p.stat().st_size>2048 else None
    current_blob=git('rev-parse','HEAD:'+path,cwd=RAD)
    lfs.append(dict(path=path,commit=min(cs,key=lambda c:dates[c]),lfs_oid=lm.group(1) if lm else None,size=int(sm.group(1)) if sm else size,first_seen=min(dates[c] for c in cs),last_seen=max(dates[c] for c in cs),schema_if_available=str(footer.schema_arrow) if footer and oid==current_blob else None,row_count_if_available=footer.metadata.num_rows if footer and oid==current_blob else None,notes=f'Git blob {oid}; present in {len(cs)} reachable commits; no historical payload download; current footer reused only for current blob',git_blob=oid))
table('LFS_VERSION_LINEAGE.csv',lfs)
write('GIT_DEEP_SEARCH_RECEIPT.json',dict(head=git('rev-parse','HEAD',cwd=RAD),refs=git('show-ref',cwd=RAD),tags=git('tag','-l',cwd=RAD),commits=len(commits),source_blobs=len(blobs),notebook_cells_inspected=notebook_cells,stored_outputs_inspected=outputs_inspected,image_output_mime_blocks_not_decoded=images_skipped,unreachable_objects=unreachable,lfs_paths=len(set(x['path'] for x in lfs)),lfs_versions=len(lfs),commands=commands,source_hits=sources))
print('commits',len(commits),'blobs',len(blobs),'notebookcells',notebook_cells,'outputs',outputs_inspected,'evidence',len(evidence),'unreachable',len(unreachable),'LFSversions',len(lfs))
for row in evidence:
    if row['authority_type']!='SOURCE_CELL' and row['supports_timezone']:print(row['notebook'],row['cell_index'],row['relevant_code_or_output'][:1000].replace('\n',' | '))
