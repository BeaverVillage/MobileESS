"""Check exact scoped staged or committed blob bytes against delivery manifest."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1];SCOPE=ROOT.relative_to(REPO).as_posix()
def git(*args,input=None):return subprocess.check_output(['git',*args],cwd=REPO,input=input)
def main(stage):
    m=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    expected={SCOPE+'/'+r['path']:r['sha256'] for r in m['files']}
    expected[SCOPE+'/DELIVERY_MANIFEST.json']=hashlib.sha256((ROOT/'DELIVERY_MANIFEST.json').read_bytes()).hexdigest()
    if stage=='staged':
        names=git('diff','--cached','--name-only','-z').decode().split('\0');assert set(filter(None,names))==set(expected),'UNEXPECTED_STAGED_SET'
        entries=git('ls-files','-s','-z','--',SCOPE).decode().split('\0')
    else:
        names=git('diff','--name-only','-z','1702abdd14db3ad6e5a63211459b9b99d6a8a054','HEAD').decode().split('\0');assert set(filter(None,names))==set(expected),'UNEXPECTED_COMMITTED_SET'
        entries=git('ls-tree','-r','-z','HEAD','--',SCOPE).decode().split('\0')
    blobs={}
    for entry in filter(None,entries):
        meta,name=entry.split('\t');parts=meta.split();blobs[name]=parts[1] if stage=='staged' else parts[2]
    assert set(blobs)==set(expected),'BLOB_SET_DIFF'
    paths=sorted(blobs);payload=('\n'.join(blobs[p] for p in paths)+'\n').encode();response=git('cat-file','--batch',input=payload);cursor=0
    for p in paths:
        end=response.index(b'\n',cursor);header=response[cursor:end].split();size=int(header[2]);begin=end+1;data=response[begin:begin+size];cursor=begin+size+1
        assert header[1]==b'blob' and hashlib.sha256(data).hexdigest()==expected[p],p
    assert cursor==len(response)
    print(json.dumps({'PASS':True,'stage':stage,'files':len(expected),'all_blob_bytes_match_delivery_manifest':True,'scope':SCOPE,'HEAD':git('rev-parse','HEAD').decode().strip()},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['staged','committed']);a=p.parse_args();main(a.stage)
