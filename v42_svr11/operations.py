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
            from v42_voltage_control.forecast import run_fresh
            output=Path(args[3]);folder=output.parent/'SOURCE'
            ops=read(Path(r['input_folder'])/'OPERATIONS.json')
            provenance=read(Path(ops['current_day_folder'])/'SOURCE_PROVENANCE.json')
            forecast=provenance['daily_sources']['aemo_forecast.json']
            with physical_permit(arm,day,source,scenario,namespace='DAYAHEAD',design_receipt=m['hardware']):
                with scenario_scope(scenario,output/'SVR11',source_SHA=source,arm=arm,day=day,namespace='DAYAHEAD') as audit:
                    result=run_fresh(day,arm,record(folder/'PLANNING_PHYSICAL.npz'),record(folder/'PLANNING_MESS.npz'),forecast,output/'FORECAST_FRESH')
            events['Planning']=audit;events['Planning_PASS']=bool(result['PASS'] and audit.result['hardware_and_controller_PASS'])
            return body(*args,**kwargs)
        output=Path(args[4])
        if 'Planning' not in events:raise PermissionError('SVR11_ACTUAL_REQUIRES_OWN_FROZEN_PLANNING')
        with physical_permit(arm,day,source,scenario,namespace='ACTUAL',design_receipt=m['hardware']):
            with scenario_scope(scenario,output/'SVR11',source_SHA=source,arm=arm,day=day,namespace='ACTUAL') as audit:
                result=body(*args,**kwargs)
        from v42_voltage_control.isolation import measured_independence
        isolation=measured_independence(events['Planning'],audit,source,scenario['scenario_SHA'],arm=arm,day=day)
        atomic(output/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json',isolation)
        if not isolation['PASS']:raise PermissionError('SVR11_INDEPENDENT_CONTROL_STATE_FAILURE')
        events['Actual']=audit;events['Actual_PASS']=bool(audit.result['hardware_and_controller_PASS'])
        result['SVR11_Planning_PASS']=events['Planning_PASS'];result['SVR11_Actual_PASS']=events['Actual_PASS']
        result['PASS']=bool(result['PASS'] and events['Planning_PASS'] and events['Actual_PASS'])
        result['SVR11_independence']=record(output/'PLANNING_ACTUAL_CONTROL_INDEPENDENCE_AUDIT.json')
        return result
    return execute

@contextmanager
def scope():
    from v42_may_campaign_native90 import operations
    events={}
    with patch.object(operations,'freeze_planning',wrapped('freeze_planning',operations.freeze_planning,events)),patch.object(operations,'fresh',wrapped('fresh',operations.fresh,events)):
        yield events
