"""Only the authorized May-04 B0/B1 pilot, never a campaign."""
import math,os,time,traceback
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41r2.authority import OUT,DAY
from dayahead.v41.execution import dayahead,actual,science
from v41r2_acceptance import coefficient_gate,critical

prior=read(OUT/'DRAFT01_INVALIDATION.json')
charge=math.ceil(prior['process_elapsed_upper_bound_seconds'])+2
remaining=1800-charge
assert remaining>0
os.environ['V41_FO_ACCEPTANCE']='1'
os.environ['V41_FO_ACCEPTANCE_SECONDS']=str(remaining)
write_json(OUT/'V41R2_OPTIMIZATION_BUDGET.json',dict(total_hard_cap_seconds=1800,
    invalidated_attempt_conservative_seconds=charge,remaining_seconds=remaining,
    allowance_reason='Full prior Python process wall time rounded up plus 2 seconds shutdown; no prior accepted search improvements',
    unrelated_electrical_Fresh_Actual_excluded=True,source=science()))
try:
    coefficient_gate();critical()
    print('COEFFICIENT_AND_CRITICAL_PASS',flush=True)
    for policy in ['B0','B1']:
        print('START_DAYAHEAD',policy,flush=True)
        print('DAYAHEAD_FRESH_PASS',policy,dayahead(DAY,policy)['status'],flush=True)
    for policy in ['B0','B1']:
        print('START_ACTUAL',policy,flush=True)
        print('ACTUAL_PASS',policy,actual(DAY,policy)['status'],flush=True)
    write_json(OUT/'V41R2_PILOT_EXECUTION.json',dict(status='PASS',day=DAY,policies=['B0','B1'],Full_May_started=False))
except BaseException as e:
    write_json(OUT/'V41R2_PILOT_EXECUTION.json',dict(status='FAIL',error=repr(e),traceback=traceback.format_exc(),Full_May_started=False))
    raise
