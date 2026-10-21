"""Independent fixed final-slot loss/rating readback on the saved S1 states."""
import re
import numpy as np
from . import correction as c
from . import correction_svr_run as runner
from .correction_svr_implicit import source_svr
from .correction_time100 import clock_class
from .correction_svr import RUN,SV,save,table,BETAS
from .audit import read

def main():
    c.priority();runner.seal_s0();rows=[];checks=[]
    for config in ('S1_03','S1_06','S1_12'):
        module=source_svr();module._BUS=re.compile(r'^[a-zA-Z0-9_\-]+(?:\.[0-3])*$')
        runner.source_svr=lambda:module;c.clock_class=clock_class;runner.Instrumented.configuration=config
        e=runner.Instrumented('LOSS_READBACK_'+config,'ACTUAL');e.capture=False
        for beta in BETAS:
            p=RUN/f'TIME_{beta:.2f}_ACTUAL_{config}';archive=np.load(p/'AC_FULL.npz')
            states=read(p/'STATES.json');slot=119
            e.apply('ACTUAL',slot,beta);e.restore_control_state(states[slot]);e.d.Solution.ControlMode(-1);e.d.Solution.Solve()
            data=e.measurement_arrays();idx=np.flatnonzero(archive['event_slot']==slot)[-1]
            dv=float(np.max(abs(data['node_voltage_pu']-archive['node_voltage_pu'][idx])))
            di=float(np.max(abs(data['line_rho']-archive['line_rho'][idx])))
            assert max(dv,di)<1e-8,(config,beta,dv,di)
            # Restore AUTO policy for the inherited readback guard, without
            # another solve/action. This is a fixed-state diagnostic context.
            e.d.Solution.ControlMode(2);measurement=e.bank.measure()
            for device in measurement['devices']:
                for phase in device['phases']:
                    terminals=phase['terminals'];loss=sum(t['P_into_kw'] for t in terminals)
                    assert abs(loss-phase['losses_kw'])<1e-7 and loss>=-1e-8
                    rows.append(dict(configuration=config,beta_BG=beta,evaluation_slot=95,bank=device['id'],phase=phase['phase'],
                        measured_losses_kw=phase['losses_kw'],terminal_P_sum_kw=loss,tap=phase['tap'],
                        max_kva_rho=max(t['apparent_loading_pu'] for t in terminals),max_current_rho=max(t['current_loading_pu'] for t in terminals),
                        hardware_PASS=device['hardware_PASS'],measurement_scope='INDEPENDENT_FIXED_FINAL_SLOT_MATCHED_TO_SAVED_TIME_STATE'))
            checks.append(dict(configuration=config,beta_BG=beta,max_abs_voltage_error=dv,max_abs_line_rho_error=di,PASS=True))
    table('INDEPENDENT_NEW_SVR_FINAL_SLOT_LOSSES.csv',rows)
    save('INDEPENDENT_NEW_SVR_LOSS_CERTIFICATION.json',dict(PASS=True,checks=checks,
        operating_point_probes=len(checks),new_SVR_loss_readbacks=len(rows),no_daylong_asset_loss_claim=True,
        full_TIME_power_balance='Every native event already records whole-network losses including new transformers; this independent audit isolates asset losses at final-slot matched states',
        Native_optimizer_calls=0))
    print('INDEPENDENT NEW SVR LOSS READBACK PASS',flush=True)

if __name__=='__main__':main()
