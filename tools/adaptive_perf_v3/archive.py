"""Additive artifact archive with exact Git blob verification, no source changes."""
import subprocess
from tools.adaptive_perf_v3.bootstrap import *
SCOPES=('tools/adaptive_compact_joint','tools/adaptive_perf_v3','tools/global_local_multistart1800','docs/v42_b2_adaptive_compact_joint',
    'docs/v42_b2_adaptive_compact_joint_fresh1800','docs/v42_b2_adaptive_perf_v3','docs/v42_b2_global_local_multistart_dual1800')
def git(*args):return subprocess.check_output(['git',*args],cwd=DEVELOPMENT_ROOT)
def main():
    configure();full_guard();assert read(DOCS/'FINAL_INDEPENDENT_REVIEW.json')['PASS'];assert git('rev-parse','HEAD').decode().strip()==BASE
    index=DOCS/'DELIVERY_ARTIFACT_INDEX.json';indexrel=index.relative_to(DEVELOPMENT_ROOT).as_posix()
    for scope in SCOPES:
        attrs=DEVELOPMENT_ROOT/scope/'.gitattributes'
        if not attrs.exists():attrs.write_text('* -text whitespace=-blank-at-eol,-blank-at-eof,cr-at-eol\n',encoding='utf-8')
    paths=sorted({p.relative_to(DEVELOPMENT_ROOT).as_posix() for scope in SCOPES for p in (DEVELOPMENT_ROOT/scope).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=index})
    for offset in range(0,len(paths),24):git('add','-f','--',*paths[offset:offset+24])
    statuses=git('diff','--cached','--name-status').decode().splitlines()
    assert all(line.startswith('A\t') and any(line.split('\t')[1].startswith(scope+'/') for scope in SCOPES) for line in statuses)
    objects={}
    for line in git('ls-files','--stage','--',*SCOPES).decode().splitlines():
        first,path=line.split('\t',1)
        if path==indexrel:continue
        blob=first.split()[1];raw=git('cat-file','blob',blob);assert raw==(DEVELOPMENT_ROOT/path).read_bytes()
        assert len(raw)<100*1024**2,'GITHUB_SINGLE_BLOB_LIMIT'
        objects[path]=dict(git_blob=blob,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    state=read(DOCS/'FINAL_STATE.json');write(index,dict(PASS=True,base=BASE,scopes=SCOPES,all_additive=True,exact_staged_blob_bytes=True,self_excluded=True,
        audited_files=len(objects),objects=objects,prior_sources_Raw_ledgers_SHA_preserved=True,independent_audit=record(DOCS/'FINAL_INDEPENDENT_REVIEW.json'),
        BEST_GLOBAL_UB=state['BEST_GLOBAL_UB']['UB'],BEST_MOVING_FEASIBLE_UB=state['BEST_MOVING_FEASIBLE_UB']['UB'],Global_LB=GLOBAL_LB,
        same_fresh_Native=state['Native_used'],Native_limit=1800,budget_reset=False))
    git('add','-f','--',indexrel);full_guard();print(json.dumps(dict(PASS=True,files=len(objects)+1,bytes=sum(a['bytes'] for a in objects.values()))),flush=True)
if __name__=='__main__':main()
