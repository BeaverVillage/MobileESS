from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from v42_pr134_b1.common import read,record,atomic
from .authority import active

def wrapped(symbol,body,events,request=None):
    if symbol not in ('freeze_planning','fresh'):return body
    def execute(*args,**kwargs):
        from v42_voltage_control.authority import physical_permit
        from v42_voltage_control.integration import scenario_scope
        m=active();scenario=read(m['scenario']['path']);r=args[0]
        day,arm=r['day'],r['arm'];source=m['execution_SHA']
        if symbol=='freeze_planning':
            from .initial_context import reference
            result=body(*args,**kwargs)
            output=Path(args[3])
            freeze=output/'V42_DAYAHEAD_DECISION_FREEZE.json'
            if not freeze.is_file():raise PermissionError('SVR11_LITERAL_PLANNING_FREEZE_REQUIRED')
            events['freeze']=record(freeze)
            events['Planning']=reference(output,scenario,source,arm,day)
            return result
        output=Path(args[4])
        if 'Planning' not in events:raise PermissionError('SVR11_ACTUAL_REQUIRES_OWN_FROZEN_PLANNING')
        with physical_permit(arm,day,source,scenario,namespace='ACTUAL',design_receipt=m['hardware']):
            with scenario_scope(scenario,output/'SVR11',source_SHA=source,arm=arm,day=day,namespace='ACTUAL') as audit:
                result=body(*args,**kwargs)
        from .initial_context import independence
        isolation=independence(events['Planning'],audit,source,scenario,arm,day)
        if record(events['freeze']['path'])!=events['freeze']:
            raise PermissionError('SVR11_FIXED_DECISION_MUTATED_DURING_ACTUAL')
        atomic(output/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json',isolation)
        if not isolation['PASS']:raise PermissionError('SVR11_INDEPENDENT_CONTROL_STATE_FAILURE')
        events['Actual']=audit;events['Actual_PASS']=bool(audit.result['hardware_and_controller_PASS'])
        result['SVR11_Planning_AC_executed']=False;result['SVR11_Planning_AC_status']='NOT_EXECUTED'
        result['SVR11_Actual_PASS']=events['Actual_PASS']
        result['PASS']=bool(result['PASS'] and events['Actual_PASS'] and isolation['PASS'])
        events['Planning'].engine.Basic.ClearAll()
        result['SVR11_independence']=record(output/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json')
        return result
    return execute

@contextmanager
def scope():
    from v42_may_campaign_native90 import operations
    events={}
    with patch.object(operations,'freeze_planning',wrapped('freeze_planning',operations.freeze_planning,events)),patch.object(operations,'fresh',wrapped('fresh',operations.fresh,events)):
        yield events
