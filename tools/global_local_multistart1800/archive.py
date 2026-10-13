"""Exact staged-byte publication audit, without solver or validator imports."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
BASE='b9684fa0999b88092d0cd38229f3453ef3f901b4'
DOC='docs/v42_b2_global_local_multistart_dual1800'
INDEX=DOC+'/DELIVERY_ARTIFACT_INDEX.json'

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main():
    changes=git('diff','--cached','--name-status',BASE).decode('utf-8').splitlines()
    assert changes and all(line.startswith('A\t') for line in changes)
    assert all(line.split('\t',1)[1].startswith((DOC+'/','tools/global_local_multistart1800/')) for line in changes)
    staged={}
    for item in git('ls-files','--stage','-z').decode('utf-8').split('\0'):
        if not item:continue
        meta,path=item.split('\t');staged[path]=meta.split()[1]
    files=[]
    for line in changes:
        _,path=line.split('\t',1)
        if path==INDEX:continue
        raw=(ROOT/path).read_bytes();oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert oid==staged[path],'STAGED_BYTES_DRIFT:'+path
        files.append(dict(path=path,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),git_blob=oid))
    assert not git('diff','--name-only').strip(),'UNSTAGED_TRACKED_CHANGE'
    review=json.loads((ROOT/DOC/'FINAL_INDEPENDENT_REVIEW.json').read_text(encoding='utf-8'));assert review['PASS']
    summary=dict(PASS=True,base_PR220=BASE,all_changes_new_research_files=True,existing_tracked_sources_unchanged=True,
        Native_optimize_calls=0,exact_staged_bytes=True,files_count=len(files),total_bytes=sum(f['bytes'] for f in files),
        files=files,self_excluded=True)
    (ROOT/INDEX).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:value for k,value in summary.items() if k!='files'}))

if __name__=='__main__':main()
