"""Counterfactual verification with no EventLog edits or other telemetry mutations."""
import numpy as np
from forensic import HERE,OLD,read,save,table,Model
def main():
    ws=read(HERE/'GLOBAL_WITNESSES_FULL.json');cases=read(HERE/'DIAGNOSTIC_PREREGISTRATION.json')['cases'];rows=[]
    for w in ws:
        a=w['alpha'];t=w['slot'];node=w['node'];kind=w['witness']
        with np.load(OLD/f'screen/alpha_{a:.2f}/B0_ALL_PHASE_ARRAYS.npz') as z:original=z['voltage_pu'][t].copy()
        for case in cases:
            folder=HERE/'diagnostic_no_instrumentation'/f'alpha_{a:.2f}'/f'{kind}_slot_{t:02d}'/case;m=Model(folder)
            for k in range(t+1):m.slot(a,k)
            pre,v,*_=m.measure();assert abs(v-original).max()<1e-10
            regs0=m.regs();caps0=m.caps();changes=m.modify(case);m.d.Solution.ControlMode(-1);m.solve()
            detail=dict(alpha=a,witness=kind,slot=t,native_witness_node=node,case=case,diagnostic_only=True,production_adoption=False,telemetry_setting_edits=0,native_pre_intervention_metrics=pre,native_accepted_regulators=regs0,native_accepted_capacitors=caps0,parameter_changes=changes,views={})
            for view in ['STATE_HELD','CONTROL_SETTLED']:
                error=None
                if view=='CONTROL_SETTLED':
                    m.d.Solution.ControlMode(0)
                    try:m.solve()
                    except Exception as ex:
                        if '#485' not in str(ex):raise
                        error=str(ex)
                status='CONTROL_ITERATION_LIMIT_EXCEEDED' if error or (view=='CONTROL_SETTLED' and not m.d.Solution.ControlActionsDone()) else 'CONVERGED'
                s,v,*_=m.measure();regs=m.regs();caps=m.caps();source=m.sources()
                if view=='STATE_HELD':
                    assert [r['accepted_tap_pu'] for r in regs]==[r['accepted_tap_pu'] for r in regs0]
                    assert [r['step_states'] for r in caps]==[r['step_states'] for r in caps0]
                z=dict(diagnostic_status=status,error=error,control_iterations=m.d.Solution.ControlIterations(),metrics=s,original_witness_voltage_pu=float(v[m.nodeidx[node]]),regulators=regs,capacitors=caps,source=source,root_to_original_witness_path=m.path(node,v,regs),all_overvoltage_frontiers=m.frontiers(v),event_log=m.d.Solution.EventLog() if error else [],pending_control_queue=m.d.CtrlQueue.Queue() if error else [])
                detail['views'][view]=z
                rows.append(dict(alpha=a,witness=kind,slot=t,native_witness_node=node,case=case,view=view,diagnostic_status=status,control_iterations=z['control_iterations'],original_witness_voltage_pu=z['original_witness_voltage_pu'],total_cap_injected_kvar=sum(r['physical_injected_kvar'] for r in caps),source_setpoint_pu=source[0]['setpoint_pu'],regulator_tap_numbers=[r['accepted_tap_number'] for r in regs],capacitor_effective_ON=[r['effective_ON'] for r in caps],**s))
            save(folder/'DIAGNOSTIC_RESULT.json',detail)
            np.savez_compressed(folder/('CONTROL_SETTLED_VOLTAGE.npz' if status=='CONVERGED' else 'UNSETTLED_LAST_ITERATE_VOLTAGE.npz'),node_names=np.array(m.nodes),voltage_pu=v,control_settled=np.array(status=='CONVERGED'))
            m.d.Basic.ClearAll()
        print(f'No telemetry edits: alpha {a:.2f} {kind} complete',flush=True)
    table(HERE/'COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.csv',rows);save(HERE/'COUNTERFACTUAL_NO_INSTRUMENTATION_COMPARISON.json',rows)
    save(HERE/'NO_INSTRUMENTATION_VERIFICATION_COMPLETION.json',dict(witness_conditions=10,comparisons=100,control_iteration_limit_cases=[{k:r[k] for k in ['alpha','witness','slot','case','view','control_iterations']} for r in rows if r['diagnostic_status']!='CONVERGED'],telemetry_setting_edits=0,production_adoptions=0))
if __name__=='__main__':main()
