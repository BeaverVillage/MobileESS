"""Package final research evidence without modifying preserved ancestors."""
from pathlib import Path
import hashlib,json,shutil,csv,gzip

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/v42_experimental_flex_qos_20261014'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def record(path):
    path=Path(path);return dict(path=str(path),bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def package():
    DOCS.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in sorted((ROOT/'audit').rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.name=='PACKAGE_INDEX.json':continue
        if path.suffix not in {'.json','.csv','.md','.py','.txt','.gz','.xml','.npz'}:continue
        target=DOCS/'evidence'/path.relative_to(ROOT/'audit')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        compressed=path.suffix in {'.json','.csv','.txt','.xml'} and path.stat().st_size>2_000_000
        if compressed:
            target=target.with_suffix(target.suffix+'.gz')
            with path.open('rb') as original,target.open('wb') as out:
                with gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0) as packed:shutil.copyfileobj(original,packed)
            uncompressed=target.with_suffix('')
            if uncompressed.is_file():uncompressed.unlink()
        rows.append(dict(source=str(path),packaged=str(target.relative_to(DOCS)),
            bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            compression='GZIP_LOSSLESS' if compressed else None,
            packaged_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    write(DOCS/'PACKAGE_INDEX.json',dict(artifacts=rows,count=len(rows),
        originals_modified=False,copy_integrity_PASS=all(
            hashlib.sha256(gzip.decompress((DOCS/r['packaged']).read_bytes()) if r['compression'] else (DOCS/r['packaged']).read_bytes()).hexdigest()==r['sha256'] for r in rows)))
    return rows

if __name__=='__main__':print(json.dumps(dict(packaged=len(package()))))
