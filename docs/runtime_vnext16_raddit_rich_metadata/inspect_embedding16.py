from common16 import *
import pyarrow.parquet as pq
paths=sorted((RAD/'data/encrypted_embeddings').glob('*.parquet'))
found=[]
for p in paths:
    f=pq.ParquetFile(p)
    if 'enc_embedding_int8' not in f.schema_arrow.names:continue
    if not found:
        a=next(f.iter_batches(batch_size=32,columns=['enc_embedding_int8'])).column(0)
        x=np.asarray(a.to_pylist())
        print('FIRST',p,'shape',x.shape,'range',x.min(),x.max(),flush=True)
    found.append(dict(path=str(p),rows=f.metadata.num_rows,bytes=p.stat().st_size))
write('EMBEDDING_LAYOUT_AUDIT.json',dict(time=now(),chunks=found,sample_shape=x.shape,sample_min=int(x.min()),sample_max=int(x.max()),
    interpretation='Stored numeric coordinates directly consumed by public semantic_search.py; no inverse/private transform. Coordinates have no verified future regeneration contract.'))
print('CHUNKS',len(found),sum(r['rows'] for r in found),flush=True)
