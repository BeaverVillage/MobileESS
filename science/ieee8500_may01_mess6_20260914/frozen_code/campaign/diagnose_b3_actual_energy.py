"""Read-only scientific replay diagnosis; write evidence only to a fresh directory."""
import copy,inspect,traceback
from bootstrap import *
import actual_binding as binding
R=H/'b3_actual_energy_diagnostic_20260914_v2'
R.mkdir(exist_ok=False)
original=binding.gating.replay
history=[]
def capture(commands,moves,initial_energy,initial_locations,project_command,**kwargs):
    save(R/'REPLAY_INPUTS.json',dict(commands=commands,moves=moves,initial_energy=initial_energy,initial_locations=initial_locations,projection=kwargs))
    def traced(*args,**kw):
        local=inspect.currentframe().f_back.f_locals
        context=dict(vehicle=local['vehicle'],slot=local['t'],command=copy.deepcopy(local['c']),starting=copy.deepcopy(local['starting']),location=local['location'],physical=local['physical'],allowed=local['allowed'],p_cmd=args[0],q_cmd=args[1],energy_before=args[2],projection=kw)
        try:
            row=project_command(*args,**kw);history.append(dict(**context,result=row));return row
        except BaseException as error:
            save(R/'FAILURE_WITNESS.json',dict(error=repr(error),**context,available_energy=args[2]-kw['travel_energy'],energy_shortfall=kw['e_min']-(args[2]-kw['travel_energy']),prior_vehicle_rows=[x for x in history if x['vehicle']==context['vehicle']]))
            raise
    return original(commands,moves,initial_energy,initial_locations,traced,**kwargs)
binding.gating.replay=capture
if __name__=='__main__':
    try:
        from dayahead.v41.data import SOURCE_REPO
        binding.replay_fleet(SOURCE_REPO,dict(day='2025-05-01',case='B3',final_PQ_source=str(H/'actual_B3/B3/FROZEN_MESS_COMMANDS.json')))
    except BaseException as error:
        save(R/'DIAGNOSTIC_RESULT.json',dict(status='REPRODUCED',error=repr(error),traceback=traceback.format_exc(),scheduling_optimization_calls=0,AC_calls=0,source_records=[record(H/'B3/FINAL_AUTHORITY.json'),record(H/'availability_gating.py'),record(H/'actual_binding.py'),record(ROOT/'dayahead/v40d_actual/mess_replay.py')]))
        w=read(R/'FAILURE_WITNESS.json');print({k:v for k,v in w.items() if k not in ('prior_vehicle_rows','command','starting')},flush=True)
