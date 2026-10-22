"""Finite prestart-only dependent jobs. Never launches a campaign/optimizer."""
import sys,subprocess,time
from .static_common import *

def run():
    init();start=time.perf_counter();stages=[]
    for name in ('SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json',
                 'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json','IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json',
                 'ORIGINAL_STATIC_PRESOLVE_MESS8.json'):
        while not (OUT/name).exists():guard(start);time.sleep(3)
        if read(OUT/name).get('PASS') is not True:raise ValueError('PREPARATION_DEPENDENCY_FAILED:'+name)
    for module in ('static_verify','static_execution native0','static_transport_verify','static_fixtures','static_report'):
        args=module.split();command=[sys.executable,'-X','utf8','-m','v2_add_preflight.'+args[0],*args[1:]]
        path=RUN/(args[0]+('_'+args[1] if len(args)>1 else '')+'_sequence.log')
        print('PRESTART ONLY',module,flush=True)
        with path.open('w',encoding='utf-8') as f:result=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        stages.append(dict(module=module,exitcode=result.returncode,log=record(path)))
        put('FINITE_PRESTART_SEQUENCE.json',dict(stages=stages,official_campaign_executed=False,Native_optimization_calls=0))
        if result.returncode:raise RuntimeError('PRESTART_STAGE_FAILED:'+module)

if __name__=='__main__':run()
