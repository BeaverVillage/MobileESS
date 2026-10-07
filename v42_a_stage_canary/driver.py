"""One requested date, immutable parent deadline and identical policies."""
import sys,gzip,pickle,traceback
from time import time
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_compact_rowgen.budget import Budget
from .policy import OUT,STATIC,DAYS
from .execution import verify
from .native import Native
from .prepare import prepare
from .phase import run as rowcol
from .integer import run as integer
from . import pricing,targeted

def run(day):
    verify();budget=Budget();budget.remaining();folder=OUT/day;folder.mkdir(parents=True,exist_ok=True)
    if day not in DAYS or (folder/'STARTED.json').exists():raise PermissionError('EXACTLY_ONE_REQUESTED_CANARY_PER_DAY')
    position=DAYS.index(day)
    for prior in DAYS[:position]:
        if not (OUT/prior/'RESULT.json').exists():raise PermissionError('REQUESTED_CANARY_ORDER_REQUIRED')
    atomic(folder/'STARTED.json',dict(PASS=True,day=day,immutable_deadline=budget.record,source=record(OUT/'CANARY_SOURCE_FREEZE.json')))
    engine=read(OUT/'CONDITIONAL_CANARY_GATE.json')['May19_engine']
    if engine=='ORIGINAL_OBJECTIVE_DIRECT':
        from .direct import Native as EngineNative
    else:EngineNative=Native
    started=time();native=EngineNative(budget,day);result=dict(day=day,A1_accepted=False,classification='A_NUMERICAL_INCONCLUSIVE')
    try:
        state=prepare(day);pricing.HISTORY=folder;targeted.HISTORY=folder
        state,x,expanded,priced=rowcol(native,state,day)
        result.update(integer(native,state,expanded,priced,day))
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    finally:
        result.update(wall_seconds=time()-started,parent_elapsed_wall_seconds=budget.accounted(),native_seconds=native.native_seconds,
            Work=sum(c.get('Work') or 0 for c in native.calls),native_calls=len(native.calls),
            peak_RSS_bytes=max((c.get('peak_RSS_bytes') or 0 for c in native.calls),default=0),
            retuning=False,parameter_sweep=False,production_Planning_Actual_Fresh=False)
        atomic(folder/'NATIVE_CALLS.json',dict(calls=native.calls));atomic(folder/'RESULT.json',result)
        print('CANARY_RESULT',day,result['classification'],result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run(sys.argv[1])
