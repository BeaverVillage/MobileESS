"""Lossless per-row raw audit storage with shared historical rows.

The manifest records the SHA and length of the original complete JSON bytes.
Only the per-candidate trajectory token is factored out of historical rows.
All physical measurements, queue events, checks and verdicts are retained.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse,hashlib,inspect,json,linecache,os,re,textwrap,uuid,zlib
from unittest.mock import patch

SCHEMA='V44_EXACT_RAW_ROW_CHUNKS_V1'
MARKER=b'"frozen_trajectory_SHA":null'

class ChunkStore:
    def __init__(self,root):
        self.root=Path(root).resolve();self.chunks=self.root/'RAW_CHUNKS_V1'
        self.chunks.mkdir(parents=True,exist_ok=True)
        self.counts=dict(new_chunks=0,reused_chunks=0,new_compressed_bytes=0,manifest_bytes=0,
            logical_raw_bytes=0)

    def chunk_path(self,key):
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('RAW_CHUNK_ID_INVALID')
        return self.chunks/key[:2]/(key+'.z')

    def get(self,key,size):
        p=self.chunk_path(key)
        p.resolve().relative_to(self.chunks.resolve())
        raw=zlib.decompress(p.read_bytes())
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=key:raise ValueError('RAW_CHUNK_CONTENT_DRIFT')
        return raw

    def put(self,raw):
        key=hashlib.sha256(raw).hexdigest();p=self.chunk_path(key);size=len(raw)
        if p.exists():
            # Full byte equality already proves the existing chunk has this key.
            if zlib.decompress(p.read_bytes())!=raw:raise ValueError('RAW_CHUNK_CONTENT_DRIFT')
            self.counts['reused_chunks']+=1
        else:
            p.parent.mkdir(parents=True,exist_ok=True);data=zlib.compress(raw,3)
            temporary=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(data)
                try:os.link(temporary,p)
                except FileExistsError:
                    if zlib.decompress(p.read_bytes())!=raw:raise ValueError('RAW_CHUNK_CONTENT_DRIFT')
                    self.counts['reused_chunks']+=1
                else:
                    self.counts['new_chunks']+=1;self.counts['new_compressed_bytes']+=len(data)
            finally:temporary.unlink(missing_ok=True)
        return dict(sha256=key,bytes=size)

    def write(self,path,rows,encoding,canonical):
        path=Path(path).resolve();path.relative_to(self.root)
        if not path.name.endswith('_MANIFEST.json'):raise ValueError('RAW_MANIFEST_PATH_REQUIRED')
        descriptors=[];tokens=[];raw_hash=hashlib.sha256();raw_hash.update(b'[');raw_size=1
        for i,row in enumerate(rows):
            token=None
            if isinstance(row,dict) and 'frozen_trajectory_SHA' in row and all(isinstance(k,str) for k in row):
                raw=encoding.canonical_list([dict(row,frozen_trajectory_SHA=None)],canonical)[1:-1].encode('utf-8')
                if raw.count(MARKER)==1:token=canonical(row['frozen_trajectory_SHA']).encode('utf-8')
                else:raw=encoding.canonical_list([row],canonical)[1:-1].encode('utf-8')
            else:raw=encoding.canonical_list([row],canonical)[1:-1].encode('utf-8')
            if i:raw_hash.update(b',');raw_size+=1
            if token is None:raw_hash.update(raw);raw_size+=len(raw)
            else:
                cut=raw.index(MARKER)+len(MARKER)-4
                view=memoryview(raw)
                raw_hash.update(view[:cut]);raw_hash.update(token);raw_hash.update(view[cut+4:])
                raw_size+=len(raw)+len(token)-4
            descriptor=self.put(raw)
            if token is not None:
                text=token.decode('utf-8')
                if text not in tokens:tokens.append(text)
                descriptor['trajectory_token']=tokens.index(text)
            descriptors.append(descriptor)
        suffix=b']'+os.linesep.encode('ascii');raw_hash.update(suffix);raw_size+=len(suffix)
        manifest=dict(schema=SCHEMA,layout='COMPLETE_RAW_RECONSTRUCTABLE_FROM_SHARED_ROWS',
            raw_sha256=raw_hash.hexdigest(),raw_bytes=raw_size,encoding='utf-8',newline=os.linesep,
            trajectory_tokens=tokens,rows=descriptors)
        data=json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')+b'\n'
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:temporary.write_bytes(data);os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
        self.counts['manifest_bytes']+=len(data);self.counts['logical_raw_bytes']+=raw_size
        return manifest

    def restore(self,path):
        path=Path(path).resolve();path.relative_to(self.root)
        manifest=json.loads(path.read_text(encoding='utf-8'))
        if manifest['schema']!=SCHEMA:raise ValueError('RAW_MANIFEST_SCHEMA_REQUIRED')
        parts=[]
        for row in manifest['rows']:
            raw=self.get(row['sha256'],row['bytes'])
            if 'trajectory_token' in row:
                if raw.count(MARKER)!=1:raise ValueError('RAW_TEMPLATE_MARKER_DRIFT')
                raw=raw.replace(MARKER,b'"frozen_trajectory_SHA":'+manifest['trajectory_tokens'][row['trajectory_token']].encode('utf-8'),1)
            parts.append(raw)
        data=b'['+b','.join(parts)+b']'+manifest['newline'].encode('ascii')
        if len(data)!=manifest['raw_bytes'] or hashlib.sha256(data).hexdigest()!=manifest['raw_sha256']:
            raise ValueError('RAW_MANIFEST_RECONSTRUCTION_DRIFT')
        return data


def adapt(function,encoding,store,original):
    prepared=original(function,encoding)
    source=textwrap.dedent(inspect.getsource(prepared))
    changes={
        "'_SLOTS.json'":"'_SLOTS_MANIFEST.json'",
        "'VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json'":"'VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS_MANIFEST.json'",
        "_r035_write(path,_r029_encode(self.rows)+'\\n',encoding='utf8')":"_r037_write(path,self.rows)",
        "_r035_write(events,_r029_encode(self.events)+'\\n',encoding='utf8')":"_r037_write(events,self.events)",
    }
    for old,new in changes.items():
        if source.count(old)!=1:raise ValueError('R037_PERSIST_STORAGE_BOUNDARY_DRIFT:'+old)
        source=source.replace(old,new)
    # Explicitly identify the format in the physical audit summary.
    old='self.result=dict(schema=VERSION,'
    if source.count(old)!=1:raise ValueError('R037_AUDIT_LAYOUT_BOUNDARY_DRIFT')
    source=source.replace(old,"self.result=dict(raw_storage_layout='V44_EXACT_RAW_ROW_CHUNKS_V1',schema=VERSION,")
    filename=__file__+'.persist.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(prepared.__globals__,_r037_write=lambda p,rows:store.write(p,rows,encoding,prepared.__globals__['canonical']))
    exec(compile(source,filename,'exec'),ns);return ns[prepared.__name__]


@contextmanager
def install(root):
    from v44_recovery_r029 import current_ac_performance as performance
    original=performance.audit_writer;active=[None]
    previous_scope=performance.current_probe_scope
    def factory(function,encoding):
        if active[0] is None:active[0]=ChunkStore(root)
        return adapt(function,encoding,active[0],original)
    @contextmanager
    def observed(oracle,rows,encoding):
        with previous_scope(oracle,rows,encoding) as stats:yield stats
        request=performance._actual_request.get()
        if request and active[0] is not None:
            from v44.common import atomic,read,now
            case=Path(request['case_root'])
            legacy=case/'R035_EXACT_RAW_STORAGE.json'
            if legacy.exists():
                value=read(legacy);value.update(raw_paths_and_bytes_unchanged=False,
                    superseded_by_r037_manifest_layout=True,original_raw_bytes_reconstructable=True)
                atomic(legacy,value)
            atomic(case/'R037_ROW_SHARED_RAW_STORAGE.json',dict(UTC=now(),schema=SCHEMA,
                counts=active[0].counts,complete_raw_reconstructable_byte_exact=True,
                physical_checks_removed=0,independent_Fresh_layout_changed=False))
    with patch.object(performance,'audit_writer',factory),patch.object(performance,'current_probe_scope',observed):yield active


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--export',type=Path,required=True)
    a=p.parse_args();data=ChunkStore(a.root).restore(a.manifest)
    with a.export.open('xb') as output:output.write(data)
