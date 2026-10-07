import subprocess,zipfile,hashlib
from pathlib import Path
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import ROOT,OUT,STATIC
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_cg.execution import verify as cg_verify

def verify():
    f=read(OUT/'PRIMAL_SOURCE_FREEZE.json')
    if not f.get('PASS'):raise PermissionError('PRIMAL_SOURCE_GATE_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('PRIMAL_SOURCE_DRIFT:'+p)
    for r in f['gate_receipts']:
        if record(r['path'])!=r or not read(r['path']).get('PASS'):raise PermissionError('PRIMAL_GATE_DRIFT')
    cg_verify();return f

def freeze():
    if (OUT/'PRIMAL_SOURCE_FREEZE.json').exists():raise PermissionError('PRIMAL_SOURCE_ALREADY_FROZEN')
    old=cg_verify();budget=Budget();budget.remaining()
    sources=[Path(r['path']) for r in old['source_files']]+list((ROOT/'v42_a_stage_primal').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_primal_proposals.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources));head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True);blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()}
    for p in sources:
        if p.is_relative_to(ROOT):
            b=p.read_bytes();h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
            if h!=blobs.get(p.relative_to(ROOT).as_posix()):h=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if h!=blobs.get(p.relative_to(ROOT).as_posix()):raise PermissionError('UNCOMMITTED_PRIMAL_SOURCE:'+str(p))
    gates=[Path(r['path']) for r in old['gate_receipts']]+[OUT/'PRIMAL_ENTRY_GATE.json',OUT/'PRIMAL_PROPOSALS.json']
    if not all(read(p).get('PASS') for p in gates):raise PermissionError('PRIMAL_PRE_RUN_GATE_REQUIRED')
    archive=STATIC/('PRIMAL_EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    atomic(OUT/'PRIMAL_SOURCE_FREEZE.json',dict(PASS=True,schema='PRIMAL_ONLY_ORIGINAL_INTEGER_FIX_REPAIR_V1',git_head=head,
        execution_sources={str(p):sha(p) for p in sources},source_files=[record(p) for p in sources],source_archive=record(archive),
        gate_receipts=[record(p) for p in gates],deadline=budget.record,no_global_bound_from_repair_queries=True))
    verify();print('PRIMAL_SOURCE_FROZEN',head,len(sources),flush=True)
if __name__=='__main__':freeze()
