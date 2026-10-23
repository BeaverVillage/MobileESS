"""Finite Native0 preparation dependencies, never a campaign scheduler."""
import sys,subprocess,time
import psutil
from .stage_common import *

def after_raw_a1(pid):
    start=time.monotonic()
    try:owned=psutil.Process(pid);created=owned.create_time();command=owned.cmdline()
    except psutil.NoSuchProcess:owned=None
    if owned is not None:
        assert '-m' in command and command[command.index('-m')+1]=='v2_add_preflight.stage_aidc'
        while owned.is_running() and time.monotonic()-start<1800:
            try:
                if owned.create_time()!=created:break
            except psutil.NoSuchProcess:break
            time.sleep(2)
        if owned.is_running() and owned.create_time()==created:raise TimeoutError('OWN_A1_BUILD_STILL_ACTIVE')
    calls=[]
    for module,args in [('stage_a_canary',['A1'])]:
        output=WORK/(module+'_sequence.log')
        with output.open('w',encoding='utf-8') as stream:
            result=subprocess.run([sys.executable,'-B','-X','utf8','-u','-m','v2_add_preflight.'+module,*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        calls.append(dict(module=module,args=args,exit_code=result.returncode,log=record(output)))
        if result.returncode:break
    put('FINITE_STAGE_PREPARATION_SEQUENCE.json',dict(PASS=all(r['exit_code']==0 for r in calls),calls=calls,
        official_campaign_executed=False,solver_optimization_executed=False))

if __name__=='__main__':after_raw_a1(int(sys.argv[1]))
