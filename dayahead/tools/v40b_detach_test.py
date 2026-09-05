from pathlib import Path
import sys,time,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v39l.infrastructure import register_one_shot_task,run_task_from_terminating_shell,delete_task_registration,current_process_identity

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');args=parser.parse_args()
    output=ROOT/'DETACH_PROBE.json'
    if args.probe:
        payload={'state':'RUNNING','identity':current_process_identity(),'started_at':now_utc()};write(output,payload)
        time.sleep(8);write(output,{**payload,'state':'COMPLETE','completed_at':now_utc()});return
    name='MobileESS_V40B_Detach_Test_'+str(time.time_ns());cmd=ROOT/'DETACH_PROBE.cmd'
    cmd.write_text('@echo off\n'+f'cd /d "{REPO}"\n"{sys.executable}" "{Path(__file__).resolve()}" --probe\n',encoding='utf-8')
    if output.exists():output.rename(ROOT/f'DETACH_PROBE_previous_{time.time_ns()}.json')
    registration=register_one_shot_task(name,cmd)
    try:
        client=run_task_from_terminating_shell(name,ROOT/'DETACH_CLIENT.json');deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if output.exists() and read(output)['state']=='COMPLETE':break
            time.sleep(1)
        probe=read(output)
        assert probe['state']=='COMPLETE' and client['initiating_shell_exited']
        assert probe['identity']['parent_pid']!=client['launcher_pid']
        write(ROOT/'V40B_DETACHED_TEST.json',{'status':'PASS','DETACHED_CHILD_SURVIVES_PARENT_EXIT':'PASS','registration':registration,'client':client,'probe':probe})
        print('DETACHED_CHILD_SURVIVES_PARENT_EXIT PASS',flush=True)
    finally:delete_task_registration(name)

if __name__=='__main__':main()
