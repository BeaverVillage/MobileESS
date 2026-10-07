"""Keep full CSVs locally and publish lossless hash-checked gzip payloads."""
import gzip,hashlib,shutil
from .common import *
def main():
    index=[]
    for day in DAYS:
        for suffix in ('OMITTED_OPTION_UNIVERSE','CERTIFICATE_OPTION_EFFECT'):
            p=OUT/(label(day)+'_'+suffix+'.csv');gz=p.with_suffix('.csv.gz')
            before=record(p)
            with p.open('rb') as f,gz.open('wb') as out:
                with gzip.GzipFile(filename='',fileobj=out,mode='wb',mtime=0,compresslevel=6) as compressed:shutil.copyfileobj(f,compressed,1024*1024)
            with gzip.open(gz,'rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
            if actual!=before['sha256']:raise ValueError('LOSSLESS_ARCHIVE_ROUNDTRIP')
            index.append(dict(required_artifact=p.name,local_full_CSV=before,lossless_repository_payload=record(gz),round_trip_PASS=True))
            print('LOSSLESS_ARCHIVE',p.name,gz.stat().st_size,flush=True)
    write('ARTIFACT_ARCHIVE_INDEX.json',dict(PASS=True,files=index,CSV_rows_not_truncated=True,lazy_option_blocks_not_sampled=True,restore='gzip.decompress(csv_gz_bytes); verify original SHA256 before use'))
if __name__=='__main__':main()
