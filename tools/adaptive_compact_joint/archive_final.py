"""Stage only additive research artifacts and verify exact Git blob bytes."""
import subprocess,hashlib
from tools.adaptive_compact_joint.fresh_adapter import *

SCOPES=('tools/adaptive_compact_joint','tools/global_local_multistart1800','docs/v42_b2_adaptive_compact_joint','docs/v42_b2_adaptive_compact_joint_fresh1800','docs/v42_b2_global_local_multistart_dual1800')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    guard();assert read(DOCS/'FINAL_INDEPENDENT_REVIEW.json')['PASS']
    assert git('rev-parse','HEAD').decode().strip()==BASE
    files=[p for scope in SCOPES for p in (ROOT/scope).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    for scope in SCOPES:
        attrs=ROOT/scope/'.gitattributes'
        if not attrs.exists():attrs.write_text('* -text whitespace=-blank-at-eol,-blank-at-eof,cr-at-eol\n',encoding='utf-8');files.append(attrs)
    index=DOCS/'DELIVERY_ARTIFACT_INDEX.json';files=[p for p in files if p!=index]
    paths=sorted(set(p.relative_to(ROOT).as_posix() for p in files))
    for offset in range(0,len(paths),24):git('add','-f','--',*paths[offset:offset+24])
    statuses=git('diff','--cached','--name-status').decode().splitlines();assert all(line.startswith('A\t') and any(line.split('\t')[1].startswith(scope+'/') for scope in SCOPES) for line in statuses)
    staged=git('ls-files','--stage','--',*SCOPES).decode().splitlines();objects={}
    for line in staged:
        first,path=line.split('\t',1);blob=first.split()[1];raw=git('cat-file','blob',blob);assert raw==(ROOT/path).read_bytes()
        objects[path]=dict(git_blob=blob,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    write(index,dict(PASS=True,baseline=BASE,scopes=SCOPES,all_additive=True,exact_staged_blob_bytes=True,
        audited_files=len(objects),objects=objects,self_excluded=True,source_and_policy_seals_unchanged=True,
        audit=record(DOCS/'FINAL_INDEPENDENT_REVIEW.json'),best_UB=INITIAL_UB,Global_LB=GLOBAL_LB,new_fresh_Native=read(DOCS/'FINAL_STATE.json')['fresh_Native_used']))
    git('add','-f','--',index.relative_to(ROOT).as_posix());guard()
    print(json.dumps(dict(PASS=True,staged_files=len(objects)+1,additions_only=True)))

if __name__=='__main__':main()
