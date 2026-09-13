"""Replace only the controller after verified recoveries, adopting live workers."""
import time,shutil,psutil
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_runtime import MAY_RUN,MAY_OUT,LOGS
from mission_cut_worker import verify_release

def main():
    verify_release()
    recovered=[('2025-05-11','B3'),('2025-05-13','B2'),('2025-05-17','B0')]
    for day,policy in recovered:assert read(MAY_OUT/day/f'PHASE_{policy}_DA.json')['status']=='PASS'
    evidence=MAY_OUT/'mission/AC_CUT_CONTROLLER_TAKEOVER';evidence.mkdir(exist_ok=False)
    state=read(MAY_RUN/'campaign_progress.json');old=psutil.Process(state['supervisor_pid'])
    assert 'mission_loop_large_supervisor.py' in ' '.join(old.cmdline())
    old.suspend()
    try:
        state=read(MAY_RUN/'campaign_progress.json');adopted=[]
        for row in state['active']:
            try:
                p=psutil.Process(row['worker_pid']);cmd=p.cmdline()
                assert row['day'] in cmd and row['phase'] in cmd
                adopted.append({**row,'created_at':p.create_time(),'cpu_at_adoption':sum(p.cpu_times()[:2])})
            except psutil.NoSuchProcess:
                assert (MAY_OUT/row['day']/f"PHASE_{row['phase']}.json").exists()
        assert len(adopted)<=4
        for name in ('campaign_progress.json','campaign_state.json','campaign_launch_receipt.json'):
            if (MAY_RUN/name).exists():shutil.copy2(MAY_RUN/name,evidence/name)
        write_json(evidence/'REPAIR.json',dict(status='PASS',max_cut_rounds=10,exit_on_first_pass=True,fail_on_exhaustion=True,
            inherited_cut_builder_reconnected=True,AIDC_route_optimization_reruns_for_cut_recovery=0,
            recovered=[record(MAY_OUT/d/f'PHASE_{p}_DA.json') for d,p in recovered],
            cut_release=record(MAY_OUT/'mission/AC_CUT_EXECUTION_RELEASE.json'),
            empty_table_test=record(MAY_OUT/'mission/EMPTY_TABLE_REGRESSION.json'),
            operational_helpers=[record(ROOT/n) for n in ('mission_cut_supervisor.py','mission_empty_recover.py','mission_empty_table.py','mission_cut_takeover.py')],
            previous_controller_pid=old.pid,adopted=adopted,scientific_workers_restarted=0,at=time.time()))
        write_json(MAY_OUT/'mission/SUPERVISOR_TAKEOVER.json',dict(state,active=adopted,takeover_at=time.time(),repair=record(evidence/'REPAIR.json')))
        old.terminate();old.wait(15)
        for row in adopted:
            if psutil.pid_exists(row['worker_pid']):assert psutil.Process(row['worker_pid']).create_time()==row['created_at']
            else:assert (MAY_OUT/row['day']/f"PHASE_{row['phase']}.json").exists()
        print('ADOPTED_WITHOUT_RESTART',[(r['day'],r['phase'],r['worker_pid']) for r in adopted],flush=True)
    except BaseException:
        if old.is_running():old.resume()
        raise
if __name__=='__main__':main()
