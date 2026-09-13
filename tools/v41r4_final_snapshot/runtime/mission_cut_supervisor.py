"""Four independent days; cut-enabled workers and repair of adopted failures."""
import sys,os,time,subprocess
from fast_prepare import ROOT,read
from v41r4_loop_runtime import MAY_RUN as RUN,MAY_OUT,LOGS
from v41r4_loop_budget import adapted
import mission_supervisor as prior
import v41r4_detached as detached

def recover_supported(day,phase,receipt,active,guard):
    if not receipt.exists() or read(receipt)['status']=='PASS':return
    error=read(receipt).get('error','')
    if phase in ('B2_DA','B3_DA') and error=="ValueError('DAYAHEAD_FRESH_PHYSICAL_VIOLATION')":
        args=['mission_cut_worker.py','resume',day,phase[:2]]
    elif phase=='B0_DA' and 'DataFrame.columns are different' in error and 'inferred_type' in error:
        args=['mission_empty_recover.py',day]
    else:return
    log=LOGS/day/(phase+'_recovery_'+str(time.time_ns())+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['V41R4_MAY_DATE']=day
    env['PYTHONPATH']=str(ROOT/'v41r4_search_bootstrap')+os.pathsep+str(ROOT)
    with log.open('x',encoding='utf-8') as f:
        p=subprocess.Popen([sys.executable,'-u',str(ROOT/args[0]),*args[1:]],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        with guard:active[day]=dict(day=day,phase=phase,worker_pid=p.pid,log=str(log),started_at=time.time(),recovery=True)
        p.wait();assert p.returncode==0,('RECOVERY_FAILED',str(log))

main=adapted(prior.main,[
    ('from v41r4_search_runtime import install_reports','from v41r4_loop_runtime import install_reports'),
    ('MAY_CAMPAIGN_RELEASE_V3.json','MAY_CAMPAIGN_RELEASE_V4.json'),
    ("script='mission_actual_worker.py' if phase.endswith('_AC') else ('mission_worker.py' if phase.startswith('B3_') else 'v41r4_search_worker.py')","script='mission_cut_worker.py'"),
    ("ROOT/'logs/v41r4_may/search_time_v3'/day","ROOT/'logs/v41r4_may/loop_wall_v4'/day"),
    ("status='RUNNING',supervisor_pid=os.getpid()","status=('RUNNING_WITH_ISOLATED_FAILURES' if errors else 'RUNNING'),supervisor_pid=os.getpid()"),
    ("assert day in p.cmdline() and phase in p.cmdline(),'ADOPT_PID_REUSED'","assert day in p.cmdline() and phase in p.cmdline() and p.create_time()==adopted['created_at'],'ADOPT_PID_REUSED'"),
    ("proc.wait();assert proc.returncode==0,('WORKER_FAILED',proc.returncode,str(log))","proc.wait();assert receipt.exists(),('WORKER_EXIT_WITHOUT_RECEIPT',proc.returncode,str(log))"),
    ("                    assert read(receipt)['status']=='PASS'","                    recover_supported(day,phase,receipt,active,guard)\n                    assert read(receipt)['status']=='PASS'"),
],dict(RUN=RUN,OUT=MAY_OUT/'mission',LOG=LOGS/'mission',recover_supported=recover_supported))

detached.MAY_RUN=RUN;detached.MAY_OUT=MAY_OUT;detached.LOGS=LOGS
spawn=adapted(detached.spawn,[("str(ROOT/'v41r4_detached.py')","str(ROOT/'mission_cut_supervisor.py')")])
worker=adapted(detached.worker,[("    if kind=='campaign_v2':\n        from v41r4_campaign_v2 import main\n    else:\n        from v41r4_campaign import main",'    from mission_cut_supervisor import main')])
if __name__=='__main__':
    if sys.argv[1]=='spawn':spawn('campaign')
    elif sys.argv[1]=='worker':worker(sys.argv[2],sys.argv[3])
    elif sys.argv[1]=='verify':detached.verify('campaign')
