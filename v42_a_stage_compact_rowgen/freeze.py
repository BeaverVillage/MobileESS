"""Commit-bound actual checkout-byte source archive and scientific gate receipts."""
import hashlib,subprocess,zipfile
from pathlib import Path
from v42_pr134_b1.common import atomic,read,record,sha
from .policy import ROOT,OUT,STATIC,PR178,POLICY
from . import BASE
def freeze():
    if (OUT/'SOURCE_FREEZE.json').exists():raise PermissionError('SOURCE_ALREADY_FROZEN')
    old=read(PR178/'SOURCE_FREEZE.json');oldroot=Path(old['execution_sources'].__iter__().__next__()).parents[1]
    sources=[]
    for r in old['source_files']:
        p=Path(r['path']);sources.append(ROOT/p.relative_to(oldroot) if p.is_relative_to(oldroot) else p)
    sources+=list((ROOT/'v42_a_stage_compact_rowgen').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_compact_rowgen.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True)
    blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()};filtered=[]
    for p in sources:
        if not p.is_relative_to(ROOT):continue
        rel=p.relative_to(ROOT).as_posix();b=p.read_bytes()
        h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if h!=blobs.get(rel):
            h=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if h!=blobs.get(rel):raise PermissionError('UNCOMMITTED_SOURCE:'+rel)
            filtered.append(rel)
    gates=[OUT/n for n in ('BASE_IDENTITY.json','BUILD_VERIFICATION.json','EXACT_PROJECTION.json','FROZEN_BATCH_IDENTITY.json','QUALIFICATION_TESTS.json','OVERNIGHT_START.json')]
    gates += [Path(r['path']) for r in read(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/CANARY_EXECUTION_PERMIT.json')['gate_receipts'].values()]
    if not all(read(p).get('PASS') is True for p in gates):raise PermissionError('PRE_NATIVE_GATE_FAIL')
    archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    atomic(OUT/'SOURCE_FREEZE.json',dict(PASS=True,schema=POLICY['schema'],git_head=head,exact_base=BASE,
        source_files=[record(p) for p in sources],execution_sources={str(p):sha(p) for p in sources},source_archive=record(archive),
        gate_receipts=[record(p) for p in gates],legacy_checkout_filter_paths=filtered,
        solver_policy=record(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'),policy=record(OUT/'POLICY.json'),
        stage='A2_FROZEN64',P1_requires_additional_certified_zero_gate=True))
    from .execution import verify
    verify();print('OVERNIGHT_SOURCE_FROZEN',head,len(sources),flush=True)
if __name__=='__main__':freeze()
