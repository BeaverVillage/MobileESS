"""Annotate already completed endpoint order; zero new AC computations."""
import numpy as np
from .run_ac import REPORT,HIGH,read,rows,table,write,receipt,source_input,DAY


def run():
    prereg=read(REPORT/'precheck/PREREGISTRATION.json')
    raw=rows(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv');n=len(prereg['targets']);flat=raw[::n]
    data=dict(np.load(source_input('PLANNING',DAY)));ordered=[]
    qf=float(np.tan(np.arccos(.95)))
    for t in prereg['slots']:
        for j in range(12):
            p=float(data['source_mask_P_upper_bound_kw'][t,j])
            ordered.append((t,f'AIDC{j+1:02d}',-p,-p*qf,'known-source-mask relaxation NOT_QOS_CERTIFIED'))
        for j in range(12):
            for p,q in [(-450,-300),(-450,300),(450,-300),(450,300)]:
                ordered.append((t,f'STA{j+1:02d}',p,q,'single new 480V port instant corner'))
        for name in ('AIDC_RELAXATION','SIX_STA_INSTANT','JOINT_RELAXATION'):
            ordered.append((t,name,None,None,'simultaneous instantaneous bound; no 96 policy certificate'))
    ordered.append((int(flat[-1]['slot']),'SIX_STA_INSTANT',None,None,'Actual instantaneous same initial six ports'))
    assert len(ordered)==len(flat)==190
    output=[]
    for k,(r,(t,case,p,q,note)) in enumerate(zip(flat,ordered)):
        assert int(r['slot'])==t and r['case']==case
        output.append(dict(endpoint_order=k,source=r['source'],day=DAY,slot=t,case=case,
            delta_consumption_P_kw=p,delta_consumption_Q_kvar=q,annotation_basis='frozen producer loop order; no reconstructed actual current',
            scope=note,**{s:r[s] for s in ('rho_max','global_relief_rho','Vmin','Vmax','Vmax_node','voltage_violation_cells',
                'full_line_overload_cells','transformer_current_overload_cells','transformer_nameplate_overload_cells',
                'port_limits_PASS','endpoint_electrical_PASS','binding_line')}))
    table(REPORT/'PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.csv',output)
    failed=[r for r in output if r['endpoint_electrical_PASS']=='False']
    write(REPORT/'PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.json',dict(source=receipt(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv'),
        total_endpoints=190,failed_endpoints=len(failed),failed_corners=[dict(slot=r['slot'],site=r['case'],P=r['delta_consumption_P_kw'],
            Q=r['delta_consumption_Q_kvar'],Vmax=r['Vmax'],Vmax_node=r['Vmax_node']) for r in failed],
        all_failures_voltage_only=all(int(r['voltage_violation_cells'])>0 and int(r['full_line_overload_cells'])==0
            and int(r['transformer_current_overload_cells'])==0 and int(r['transformer_nameplate_overload_cells'])==0
            and r['port_limits_PASS']=='True' for r in failed),
        full_P450_Q300_rectangle_certified=False,ratings_enlarged=False,placement_retuned=False,
        actual_raw_endpoint_currents_unavailable=True,additional_AC_solves=0,Native_calls=0))
    return output

if __name__=='__main__':run()
