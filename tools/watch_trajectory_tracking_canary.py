"""Owned hidden process tree only; 1200s and memory gates, no scheduler."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.partial_canary import resource_snapshot


def main(output,prior_a1=None,prior_wall=0):
    output=output.resolve();output.relative_to(ROOT);output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,V42_TRACKING_WATCH_PID=str(os.getpid()))
    with (output/'STDOUT.log').open('w',encoding='utf8') as out,(output/'STDERR.log').open('w',encoding='utf8') as err:
        args=[sys.executable,'-u','-m','v42_integration.tracking_canary','--output',str(output)]
        if prior_a1 is not None:args+=['--prior-a1',str(prior_a1.resolve()),'--prior-wall',str(prior_wall)]
        child=subprocess.Popen(args,
            cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        began=time.perf_counter();samples=[];stop=None
        while child.poll() is None:
            time.sleep(2)
            if child.poll() is not None:break
            mem=resource_snapshot()['memory']
            try:
                owned=[psutil.Process(child.pid)]+psutil.Process(child.pid).children(recursive=True)
                infos=[p.memory_info() for p in owned];rss=sum(i.rss for i in infos)
                private=sum(getattr(i,'private',0) for i in infos)
            except psutil.NoSuchProcess:continue
            elapsed=time.perf_counter()-began
            samples.append(dict(elapsed_seconds=elapsed,RSS_bytes=rss,Private_Commit_bytes=private,
                AvailableMBytes=mem['AvailableMBytes'],Commit_percent=mem['PercentCommittedBytesInUse']))
            if elapsed+prior_wall>=1200:stop='CUMULATIVE_CANARY_1200S_WALL_LIMIT'
            elif mem['AvailableMBytes']<6144 or mem['PercentCommittedBytesInUse']>=75 or rss>12*2**30:stop='RAM_COMMIT_GATE'
            if stop:
                for p in reversed(owned):
                    try:p.kill()
                    except psutil.NoSuchProcess:pass
                break
        code=child.wait()
    receipt=dict(owned_pid=child.pid,exit_code=code,wall_seconds=time.perf_counter()-began,
        cumulative_execution_wall_seconds=prior_wall+time.perf_counter()-began,
        prior_execution_wall_seconds=prior_wall,stop_reason=stop,external_processes_killed=0,auto_retry=False,samples=samples)
    (output/'WATCHDOG_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prior-a1',type=Path);parser.add_argument('--prior-wall',type=float,default=0)
    args=parser.parse_args();main(args.output,args.prior_a1,args.prior_wall)
