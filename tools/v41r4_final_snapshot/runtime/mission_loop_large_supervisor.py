"""Independent-day V4 controller preserving live workers during repair adoption."""
import sys
from fast_prepare import ROOT
from v41r4_loop_runtime import MAY_RUN as RUN, MAY_OUT, LOGS
from v41r4_loop_budget import adapted
import mission_supervisor as prior
import v41r4_detached as detached

main=adapted(prior.main,[
    ('from v41r4_search_runtime import install_reports','from v41r4_loop_runtime import install_reports'),
    ("MAY_CAMPAIGN_RELEASE_V3.json","MAY_CAMPAIGN_RELEASE_V4.json"),
    ("script='mission_actual_worker.py' if phase.endswith('_AC') else ('mission_worker.py' if phase.startswith('B3_') else 'v41r4_search_worker.py')",
     "script='mission_loop_large_worker.py'"),
    ("ROOT/'logs/v41r4_may/search_time_v3'/day","ROOT/'logs/v41r4_may/loop_wall_v4'/day"),
    ("status='RUNNING',supervisor_pid=os.getpid()",
     "status=('RUNNING_WITH_ISOLATED_FAILURES' if errors else 'RUNNING'),supervisor_pid=os.getpid()"),
    ("assert day in p.cmdline() and phase in p.cmdline(),'ADOPT_PID_REUSED'",
     "assert day in p.cmdline() and phase in p.cmdline() and p.create_time()==adopted['created_at'],'ADOPT_PID_REUSED'"),
],dict(RUN=RUN,OUT=MAY_OUT/'mission',LOG=LOGS/'mission'))

detached.MAY_RUN=RUN;detached.MAY_OUT=MAY_OUT;detached.LOGS=LOGS
spawn=adapted(detached.spawn,[("str(ROOT/'v41r4_detached.py')","str(ROOT/'mission_loop_large_supervisor.py')")])
worker=adapted(detached.worker,[(
    "    if kind=='campaign_v2':\n        from v41r4_campaign_v2 import main\n    else:\n        from v41r4_campaign import main",
    '    from mission_loop_large_supervisor import main')])

if __name__=='__main__':
    if sys.argv[1]=='spawn':spawn('campaign')
    elif sys.argv[1]=='worker':worker(sys.argv[2],sys.argv[3])
    elif sys.argv[1]=='verify':detached.verify('campaign')
