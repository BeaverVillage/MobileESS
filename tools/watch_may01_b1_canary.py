"""One owned hidden worker; resource/stage timeout, no retry or external kill."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.partial_canary import resource_snapshot


def main(output,native0):
    output=output.resolve();output.relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-u','-m','v42_integration.partial_canary','--output',str(output)]
    if native0:args.append('--native0-only')
    env=dict(os.environ,V42_CANARY_SUPERVISOR_PID=str(os.getpid()))
    with (output/'CANARY_STDOUT.log').open('w',encoding='utf8') as stdout,(output/'CANARY_STDERR.log').open('w',encoding='utf8') as stderr:
        child=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        began=time.perf_counter();samples=[];stop=None
        while child.poll() is None:
            time.sleep(2)
            if child.poll() is not None:break
            memory=resource_snapshot()['memory'];elapsed=time.perf_counter()-began
            try:rss=psutil.Process(child.pid).memory_info().rss
            except psutil.NoSuchProcess:break
            path=output/'LIVE_STAGE.json';stage=json.loads(path.read_text()) if path.exists() else {}
            samples.append(dict(elapsed_seconds=elapsed,RSS_bytes=rss,AvailableMBytes=memory['AvailableMBytes'],
                Commit_percent=memory['PercentCommittedBytesInUse'],stage=stage.get('stage')))
            if elapsed>=900:stop='CANARY_900S_WALL_LIMIT'
            elif memory['AvailableMBytes']<6144 or memory['PercentCommittedBytesInUse']>=75 or rss>12*2**30:stop='RAM_COMMIT_PROTECTION'
            elif stage and elapsed-stage['stage_started_elapsed']>=stage['stage_cap_seconds']:stop='STAGE_WALL_LIMIT_'+stage['stage']
            if stop:
                child.kill();break
        code=child.wait()
    receipt=dict(pid=child.pid,exit_code=code,wall_seconds=time.perf_counter()-began,stop_reason=stop,
        samples=samples,external_workers_terminated=0,auto_retry=False)
    (output/'WATCHDOG_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native0-only',action='store_true');args=parser.parse_args()
    main(args.output,args.native0_only)
