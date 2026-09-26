"""New Actual namespace; frozen DA and full chronological shell QSAFE preserved."""
import sys,traceback
from pathlib import Path
import b3_actual_shell as shell
import actual_energy_exception as exception
exception.install()
shell.w.H=shell.BASE/'actual_B3_energy_exception_20260914'
base_save=shell.save
def save(p,value):
    p=Path(p)
    if p==shell.w.H/'RULE_FREEZE.json':
        value=dict(value,energy_floor_exception=exception.RULE)
        value['source_files']=list(value['source_files'])+[shell.w.rec(Path(__file__)),shell.w.rec(Path(exception.__file__))]
    if p.name=='COMPLETE.json':
        value=dict(value,acceptance_rule=exception.RULE,original_440kWh_compliance_claimed=False)
    return base_save(p,value)
shell.save=save;shell.w.save=save
if __name__=='__main__':
    try:
        shell.main()
        audit=shell.w.read(shell.w.H/'B3/FINAL_ACTUAL/ACTUATOR.json')['independent_audit']
        result=shell.w.read(shell.w.H/'B3/COMPLETE.json')
        status=exception.RULE['acceptance_status'] if audit['user_accepted_exception'] else 'PASS'
        save(shell.w.H/'USER_ACCEPTED_COMPLETE.json',dict(status=status,AC_feasible=result['AC_feasible'],independent_replay_PASS=result['independent_replay_PASS'],operating_440kWh_floor_feasible=audit['operating_440kWh_floor_feasible'],energy_floor_exceptions=audit['energy_floor_exceptions'],result=shell.w.rec(shell.w.H/'B3/COMPLETE.json'),new_optimization_calls=0))
        shell.w.state(status=status,stage='B3_ACTUAL_COMPLETE')
    except BaseException as error:
        save(shell.w.H/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()))
        shell.w.state(status='FAILED',stage='B3_ACTUAL_ENERGY_EXCEPTION_FAILURE')
        raise
