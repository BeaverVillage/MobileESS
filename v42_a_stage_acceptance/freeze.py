import subprocess,zipfile
from pathlib import Path
from v42_pr134_b1.common import atomic,record,sha,read
from .policy import ROOT,OUT,STATIC,POLICY,BASE,OLD
from .budget import establish

def freeze():
    establish();p=OUT/'CONTINUATION_SOURCE_FREEZE.json'
    if p.exists():raise PermissionError('CONTINUATION_SOURCE_ALREADY_FROZEN')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    names=subprocess.check_output(['git','ls-files','*.py'],cwd=ROOT,text=True).splitlines()
    sources=[ROOT/n for n in names];archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip');archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for source in sources:z.write(source,source.relative_to(ROOT).as_posix())
    historical={str(q):sha(q) for q in OLD.rglob('*') if q.is_file()}
    atomic(OUT/'HISTORICAL_PR180_BYTE_PRESERVATION_START.json',dict(PASS=True,base=BASE,files=historical))
    atomic(p,dict(PASS=True,schema=POLICY['schema'],git_head=head,base=BASE,
        execution_sources={str(q):sha(q) for q in sources},source_archive=record(archive),
        budget=record(OUT/'CONTINUATION_BUDGET.json'),policy=POLICY,
        historical_PR180=record(OUT/'HISTORICAL_PR180_BYTE_PRESERVATION_START.json')))
    print('NEW_SOURCE_FROZEN',head,len(sources),flush=True)
if __name__=='__main__':freeze()
