"""Conditional three-day source freeze, never authorizes a campaign."""
import hashlib,subprocess,zipfile
from time import time
from pathlib import Path
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_compact_rowgen.budget import Budget
from .policy import ROOT,OUT,STATIC,OVERNIGHT,DAYS,POLICY

def freeze():
    if (OUT/'CANARY_SOURCE_FREEZE.json').exists():raise PermissionError('CANARY_SOURCE_ALREADY_FROZEN')
    from .acceptance import final_acceptance
    acceptance,engine=final_acceptance();accepted=read(acceptance);integer=read(OVERNIGHT/'INTEGER_RESULT.json');budget=Budget()
    if not accepted.get('A1_accepted') or not integer.get('P1_accepted') or integer['global_gap']>.005 or budget.remaining()<5400:raise PermissionError('MAY19_A1_AND_90_MINUTES_REMAINING_REQUIRED')
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    atomic(OUT/'CONDITIONAL_CANARY_GATE.json',dict(PASS=True,May19_A1=record(acceptance),May19_engine=engine,
        May19_P1=record(OVERNIGHT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),remaining_seconds_at_trigger=budget.remaining(),
        minimum_seconds=5400,run_order=DAYS,original_deadline=budget.record,same_algorithm_no_retuning=True,full_campaign=False))
    old=read(OVERNIGHT/('CG_SOURCE_FREEZE.json' if engine=='WEIGHTED_CG' else 'LEX_CASE_SOURCE_FREEZE.json'));sources=[Path(r['path']) for r in old['source_files']]
    sources+=list((ROOT/'v42_a_stage_canary').glob('*.py'))+list((ROOT/'v42_a_stage_cg').glob('*.py'))+[ROOT/'v42_a_stage_lexfull/full_bounds.py',ROOT/'tests/test_v42_a_stage_full_bounds.py',ROOT/'tests/test_v42_a_stage_canary_guard.py',ROOT/'tests/test_v42_a_stage_weighted_cg.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources));head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True);blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()}
    for p in sources:
        if p.is_relative_to(ROOT):
            rel=p.relative_to(ROOT).as_posix();b=p.read_bytes();h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
            if h!=blobs.get(rel):h=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if h!=blobs.get(rel):raise PermissionError('UNCOMMITTED_CANARY_SOURCE:'+rel)
    gates=[Path(r['path']) for r in old['gate_receipts']]+[OUT/'CONDITIONAL_CANARY_GATE.json']
    if not all(read(p).get('PASS') is True for p in gates):raise PermissionError('CANARY_PRE_RUN_GATE_FAIL')
    archive=STATIC/('CANARY_EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    atomic(OUT/'CANARY_SOURCE_FREEZE.json',dict(PASS=True,schema=POLICY['schema'],git_head=head,execution_sources={str(p):sha(p) for p in sources},
        source_files=[record(p) for p in sources],source_archive=record(archive),gate_receipts=[record(p) for p in gates],policy=POLICY,deadline=budget.record))
    from .execution import verify
    verify();print('CANARY_SOURCE_FROZEN',head,len(sources),flush=True)
if __name__=='__main__':freeze()
