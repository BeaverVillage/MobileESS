"""Service-owned sequential shells, native budgets never auto-extended."""
import sys,os,subprocess,traceback,time
from fractions import Fraction as Q
import json
from .common import *

def frozen_sources():
    r=read(CASE/'EXECUTION_FREEZE.json')
    for x in r['files']:
        if sha(x['path'])!=x['sha256']:raise PermissionError('FROZEN_EXECUTION_SOURCE_DRIFT:'+x['path'])

def child(module,*args):
    frozen_sources();log=CASE/(module.rsplit('.',1)[-1]+'_'+('_'.join(args) or 'run')+'.stdout.log')
    with log.open('x',encoding='utf8') as f:
        p=subprocess.Popen([sys.executable,'-X','utf8','-m',module,*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        atomic(CASE/'CURRENT_CHILD.json',dict(module=module,args=args,process=process(p.pid),log=record(log),started=now()))
        code=p.wait()
    if code:raise RuntimeError('CHILD_FAILED:'+module+':'+str(code)+':'+str(log))

def run():
    frozen_sources();selected=None;trace=[]
    for shell in SHELLS:
        name=shell['name'];folder=CASE/name
        if not (folder/'COMPACT/COMPRESSION_VERIFICATION.json').exists():child('v42_pr134_may19.domain',name)
        if not read(folder/'INDEPENDENT_DOMAIN_INCLUSION.json')['PASS']:raise PermissionError('DOMAIN_GATE')
        census=read(folder/'CENSUS.json');s38=read(START/'CENSUS.json')
        increases={k:(census[k]/s38[k]-1) if s38[k] else 0 for k in ('cols','binary','rows','nnz')}
        if max(increases.values())>.01:
            atomic(CASE/'SIZE_CAP_REPORT.json',dict(shell=name,increases=increases,engineering_target_exceeded=True,
                   status='AWAIT_EXPLICIT_REPORT_BEFORE_SOLVE',scientific_validity_relaxed=False))
            # The user's 1% target is an engineering preference, not a science
            # acceptance gate. Wait only for this chat to deliver the required
            # report; no user approval, memory gate or solver change is requested.
            delivered=CASE/'SIZE_CAP_REPORT_DELIVERED.json'
            while not delivered.exists() or read(delivered).get('shell')!=name:time.sleep(.25)
        child('v42_pr134_may19.solve',name)
        r=read(folder/'RESULT.json');trace.append(dict(shell=name,result=r,increases=increases))
        atomic(CASE/'SHELL_TRACE.json',trace)
        if r['integer_witness_PASS']:
            selected=name;atomic(CASE/'SELECTED_DOMAIN.json',dict(shell=name,first_feasible_tested_shell=True,global_minimum_proven=False,
                  domain=record(folder/'SELECTED_DOMAIN_INPUT.json'),integer_result=record(folder/'RESULT.json')));break
        # No native infeasibility claim is inferred from TIME_LIMIT. An old valid
        # support ray is a ranking guide; its S38-expanded contradiction is unproven.
        proof=read(SUPPORT/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json')
        known={(x['site'],int(x['slot'])):Q(x['coefficient']) for x in proof['known_coefficients']}
        original={k:Q(x['exact_minimum_per_job']) for k,x in proof['all_class_minima'].items()};mins=dict(original)
        for row in read(folder/'SELECTED_DOMAIN_INPUT.json'):
            parts=json.loads(row['segments']);k=row['class_id']
            cost=int(row['GPU'])*sum((w for (s,t),w in known.items() for site,lo,hi in parts if s==site and lo<=t<hi),Q(0))
            mins[k]=min(mins[k],cost)
        delta=sum(((mins[k]-original[k])*int(proof['all_class_minima'][k]['count']) for k in mins),Q(0))
        margin=Q(proof['exact_positive_margin'])+delta;allowance=Q(proof['exact_original_checker_residual_allowance'])
        atomic(folder/'CONTINUATION_SUPPORT_ANALYSIS.json',dict(shell_unresolved=margin<=allowance,independent_integer_support_infeasibility_proven=margin>allowance,
            LP_infeasibility_claimed=False,exact_signed_support_margin=str(margin),exact_original_residual_allowance=str(allowance),
            no_verified_integer_witness=True,prior_support=record(SUPPORT/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json'),
            native_result=record(folder/'RESULT.json'),next_preregistered_shell_authorized=True,TIME_LIMIT_not_INFEASIBLE=True))
    if selected:
        child('v42_pr134_may19.production',selected)
        r=read(CASE/'PRODUCTION/RESULT.json');atomic(CASE/'FINAL_RESULT.json',dict(r,selected_shell=selected,trace=trace))
    else:atomic(CASE/'FINAL_RESULT.json',dict(classification='MAY19_PRESCREENING_UNRESOLVED',planned_shells_exhausted=True,trace=trace,
          integer_witness_PASS=False,full_physical_universe_insufficient_proven=False))

def main():
    CASE.mkdir(parents=True,exist_ok=True)
    if (CASE/'HOST.json').exists():raise PermissionError('NO_DUPLICATE_HOST')
    import psutil
    psutil.Process().nice(psutil.NORMAL_PRIORITY_CLASS)
    sys.stdout=(CASE/'HOST.stdout.log').open('x',encoding='utf8',buffering=1)
    sys.stderr=(CASE/'HOST.stderr.log').open('x',encoding='utf8',buffering=1)
    atomic(CASE/'HOST.json',dict(process=process(),UTC=now(),memory_guards=False,automatic_native_extension=False))
    try:run()
    except Exception as e:
        atomic(CASE/'HOST_ERROR.json',dict(error=str(e),traceback=traceback.format_exc(),UTC=now()))
        if not (CASE/'FINAL_RESULT.json').exists():
            atomic(CASE/'FINAL_RESULT.json',dict(classification='MAY19_PRESCREENING_UNRESOLVED',implementation_or_native_failure=True,
                 error=str(e),integer_feasibility_PASS=(CASE/'SELECTED_DOMAIN.json').exists(),automatic_retry=False))
        traceback.print_exc();return 1
    return 0
if __name__=='__main__':sys.exit(main())
