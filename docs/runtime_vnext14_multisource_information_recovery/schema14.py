"""Candidate second pass: Parquet footer/schema and ZIP directory metadata only."""
from common14 import *
import pyarrow.parquet as pq
import zipfile,re


def main():
    inventory=pd.read_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',keep_default_na=False)
    schemas=[];archives=[]
    for ix,row in inventory.iterrows():
        if row.dataset_family.startswith('NON_RUNTIME_') or row.dataset_family=='WEATHER':continue
        p=RAW_A/row.relative_path
        if p.suffix.lower()=='.parquet':
            item=dict(source_id=row.source_id,path=str(p),metadata_only=True)
            try:
                if row.size_bytes<200:
                    text=p.read_text(encoding='utf-8')
                    if text.startswith('version https://git-lfs.github.com/spec/v1'):
                        item.update(status='GIT_LFS_POINTER_ONLY',pointer=text);inventory.at[ix,'notes']='Git LFS pointer only; payload not present in this copy.'
                        schemas.append(item);continue
                pf=pq.ParquetFile(p);schema=pf.schema_arrow;names=schema.names
                item.update(status='FOOTER_READ',rows=pf.metadata.num_rows,row_groups=pf.num_row_groups,
                            fields=[dict(name=f.name,type=str(f.type)) for f in schema])
                inventory.at[ix,'schema_available']=True
                inventory.at[ix,'timestamp_columns']=';'.join(n for n in names if any(t in n.lower() for t in ['time','date','timestamp']))
                inventory.at[ix,'job_identifier_columns']=';'.join(n for n in names if any(t in n.lower() for t in ['job_id','jobid','row_id','array','step']))
                inventory.at[ix,'notes']='Parquet footer/schema/row count only; no runtime/outcome record content decoded.'
            except Exception as e:item.update(status='SCHEMA_UNAVAILABLE',error=str(e))
            schemas.append(item)
        elif p.suffix.lower()=='.zip':
            item=dict(source_id=row.source_id,path=str(p),metadata_only=True)
            try:
                with zipfile.ZipFile(p) as z:
                    members=[dict(name=i.filename,bytes=i.file_size,compressed_bytes=i.compress_size,crc32=i.CRC) for i in z.infolist() if not i.is_dir()]
                item.update(status='DIRECTORY_READ',members=members,member_count=len(members))
                # Central-directory signatures strengthen copy grouping without hashing GB payloads.
                item['directory_signature']=hashlib.sha256(json.dumps(members,sort_keys=True).encode()).hexdigest()
            except Exception as e:item.update(status='ARCHIVE_UNAVAILABLE',error=str(e))
            archives.append(item)
    inventory.to_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',index=False)
    write('RAW_SCHEMA_METADATA.json',dict(time=now(),schemas=schemas,archive_directories=archives,
        runtime_outcomes_decoded=False,May_runtime_labels_decoded=False))
    print('SCHEMA_FOOTERS',len(schemas),'ARCHIVE_DIRECTORIES',len(archives),flush=True)
    for r in schemas:
        if any(key in r['path'] for key in ['historic_job_trace','chunk_000','PUE.combined','outside.combined']):
            print(json.dumps(r,ensure_ascii=False),flush=True)
    for r in archives:
        if 'kestrel.job-anon.zip' in r['path'] or Path(r['path']).name=='dataset.zip':
            print('ARCHIVE',r['path'],r.get('member_count'),r.get('members',[])[:6],flush=True)


if __name__=='__main__':main()
