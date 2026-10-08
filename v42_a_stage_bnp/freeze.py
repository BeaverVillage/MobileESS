import hashlib,subprocess,zipfile
from pathlib import Path
from v42_pr134_b1.common import read,record,atomic,sha
from .policy import ROOT,OUT,STATIC,POLICY
def freeze():
    if (OUT/'INTEGER_SOURCE_FREEZE.json').exists():raise PermissionError('INTEGER_SOURCE_ALREADY_FROZEN')
    old=read(OUT/'PRACTICAL_SOURCE_FREEZE.json');sources=[Path(r['path']) for r in old['source_files']]
    sources+=list((ROOT/'v42_a_stage_practical').glob('*.py'))+list((ROOT/'v42_a_stage_bnp').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_bnp.py',ROOT/'tests/test_v42_a_stage_integer_model.py',ROOT/'tests/test_v42_a_stage_global_bounds.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources));head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True);blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()}
    for p in sources:
        if p.is_relative_to(ROOT):
            rel=p.relative_to(ROOT).as_posix();b=p.read_bytes();h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
            if h!=blobs.get(rel):h=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if h!=blobs.get(rel):raise PermissionError('UNCOMMITTED_SOURCE:'+rel)
    gates=[Path(r['path']) for r in old['gate_receipts']]+[OUT/n for n in ('INTEGER_BUILD_VERIFICATION.json','P1_INTEGER_ENTRY_GATE.json','INTEGER_TESTS.json')]
    if not all(read(p).get('PASS') is True for p in gates):raise PermissionError('INTEGER_PRE_RUN_GATE_FAIL')
    archive=STATIC/('INTEGER_EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    atomic(OUT/'INTEGER_SOURCE_FREEZE.json',dict(PASS=True,schema=POLICY['schema'],git_head=head,execution_sources={str(p):sha(p) for p in sources},
        source_files=[record(p) for p in sources],source_archive=record(archive),gate_receipts=[record(p) for p in gates],
        policy=POLICY,deadline=read(OUT/'OVERNIGHT_START.json'),full_domain_gap_requires_independent_integer_primal=True))
    from .execution import verify
    verify();print('INTEGER_SOURCE_FROZEN',head,len(sources),flush=True)
if __name__=='__main__':freeze()
