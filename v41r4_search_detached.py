"""Same WMI detachment proof, bound to the corrected-search campaign."""
import sys
import v41r4_detached as base
from v41r4_search_runtime import MAY_RUN,MAY_OUT,LOGS
from v41r4_search_budget import adapted

base.MAY_RUN=MAY_RUN;base.MAY_OUT=MAY_OUT;base.LOGS=LOGS
spawn=adapted(base.spawn,[("str(ROOT/'v41r4_detached.py')","str(ROOT/'v41r4_search_detached.py')")])
worker=adapted(base.worker,[("    if kind=='campaign_v2':\n        from v41r4_campaign_v2 import main\n    else:\n        from v41r4_campaign import main",'    from v41r4_search_campaign import main')])

if __name__=='__main__':
    op=sys.argv[1]
    if op=='spawn':spawn(sys.argv[2])
    elif op=='worker':worker(sys.argv[2],sys.argv[3])
    elif op=='verify':base.verify(sys.argv[2])
