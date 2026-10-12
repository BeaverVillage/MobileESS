"""Portable SHA256 artifact index and exact staged-byte checks; no solver."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
DOC='docs/v42_b2_integrated_primal1800_canary'
INDEX=DOC+'/DELIVERY_ARTIFACT_INDEX.json'
BASE='38d98b99d1ea5ce9021fe0d727ab80309910b63d'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main():
    changed=git('diff','--cached','--name-status',BASE).decode().splitlines()
    assert all(x.startswith('A\t') for x in changed)
    staged={}
    for line in git('ls-files','--stage','-z').decode().split('\0'):
        if not line:continue
        meta,path=line.split('\t');staged[path]=meta.split()[1]
    files=[]
    for line in changed:
        _,path=line.split('\t',1)
        assert path.startswith((DOC+'/','tools/integrated_primal1800/'))
        if path==INDEX:continue
        raw=(ROOT/path).read_bytes()
        oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert oid==staged[path], 'Staged bytes differ: '+path
        files.append(dict(path=path,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),git_blob=oid))
    seal=json.loads((ROOT/DOC/'EXECUTED_SOURCE_HASHES.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==value for path,value in seal.items())
    assert not git('diff','--name-only').strip(), 'Unstaged tracked changes remain.'
    payload=dict(PASS=True,base=BASE,Native_calls=0,existing_tracked_files_unchanged=True,
                 executed_native_source_bytes_unchanged=True,all_staged_artifact_bytes_exact=True,
                 files=files,files_count=len(files),total_bytes=sum(f['bytes'] for f in files),
                 self_excluded=True)
    (ROOT/INDEX).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k!='files'}))
if __name__=='__main__':main()
