"""Resume unchanged V4 science through the retained-archive path adapter."""
import sys
from fast_prepare import ROOT
from v41r4_loop_budget import adapted
from v41r4_loop_runtime import MAY_RUN, MAY_OUT, LOGS, install_reports
import v41r4_campaign as original
import v41r4_detached as detached

def main():
    from v41r4_loop_campaign import release
    install_reports()
    return adapted(original.main, [
        ("str(ROOT/'v41r4_worker.py')", "str(ROOT/'mission_loop_archive.py')"),
        ("str(ROOT/'v41r4_bootstrap')", "str(ROOT/'v41r4_search_bootstrap')")],
        dict(MAY_RUN=MAY_RUN, MAY_OUT=MAY_OUT, LOGS=LOGS, release=release))()

detached.MAY_RUN=MAY_RUN
detached.MAY_OUT=MAY_OUT
detached.LOGS=LOGS
spawn=adapted(detached.spawn, [("str(ROOT/'v41r4_detached.py')", "str(ROOT/'mission_loop_resume.py')")])
worker=adapted(detached.worker, [
    ("    if kind=='campaign_v2':\n        from v41r4_campaign_v2 import main\n    else:\n        from v41r4_campaign import main", "    from mission_loop_resume import main")])

if __name__=='__main__':
    if sys.argv[1]=='spawn': spawn('campaign')
    elif sys.argv[1]=='worker': worker(sys.argv[2],sys.argv[3])
    elif sys.argv[1]=='verify': detached.verify('campaign')
