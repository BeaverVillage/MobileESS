"""Readback binding and baseline witness audit; never invoke optimization."""
from electrical_engine import *
from numerical_coefficients import Coefficients,AX,BRANCHES
from full_electrical_rows import evaluate_grid

def main():
    frozen_check()
    e=Engine(H/'binding_readback/runtime');e.inputs(31)
    ports=electrical_port_contract()['control_axis'];by={(r['PCC_role'],r['location_id']):r for r in e.inv}
    with np.load(H/'B0_REPLAY/ANCHORS.npz') as z:xx=z['x'].copy()
    rows=[]
    for port in ports:
        j=port['axis'];loc=port.get('location_id',port['logical']);inv=by[port['role'],loc]
        element=('op8500_'+port['logical'].lower()) if j<12 else ('np8500_mess_'+port['logical'].lower())
        d=e.d;d.Circuit.SetActiveElement('Transformer.'+inv['transformer'])
        buses=d.CktElement.BusNames();phases=d.CktElement.NumPhases()
        assert phases==3 and buses[0].lower()==inv['host_bus'].lower()+'.1.2.3' and buses[1].lower()==inv['PCC_bus'].lower()+'.1.2.3'
        d.Transformers.Name(inv['transformer']);ratings=[]
        for winding in (1,2):d.Transformers.Wdg(winding);ratings.append(d.Transformers.kVA())
        assert ratings==[inv['rating_kva']]*2
        signed=[]
        for sign in (-1,1):
            x=xx[31].copy();x[j]+=10*sign;e.controls(x);d.Loads.Name(element)
            p,q=d.Loads.kW(),d.Loads.kvar();bus=d.CktElement.BusNames()[0]
            expected=(x[j],PF_TAN*x[j]) if j<12 else (-x[12+(j-12)%24],-x[36+(j-12)%24])
            assert np.allclose([p,q],expected,rtol=0,atol=1e-10)
            assert bus.lower()==inv['PCC_bus'].lower()+'.1.2.3' and d.CktElement.NumPhases()==3
            signed.append(dict(delta=sign*10.,readback_P_kw=p,readback_Q_kvar=q,expected=list(expected),bus=bus))
        rows.append(dict(**port,transformer=inv['transformer'],rating_kVA=ratings,actual_PCC_bus=bus,readback_element='Load.'+element,phases=phases,signed_readback=signed,status='PASS'))
    for i in range(1,13):
        a=by['AIDC',f'AIDC{i:02}'];m=by['MESS',f'AIDC{i:02}']
        assert a['host_bus']==m['host_bus'] and a['PCC_bus']!=m['PCC_bus'] and a['transformer']!=m['transformer']
    e.close()
    save(H/'ALL_60_CONTROL_COLUMN_BINDING_AUDIT.json',dict(status='PASS',columns=60,AIDC_P=12,MESS_P=24,MESS_Q=24,independent_AIDC_Q=0,fixed_PF_TAN=PF_TAN,AIDC_and_MESS_independent_branches=True,rows=rows))
    save(H/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json',dict(status='PASS',services=[dict(service=rows[12+j]['logical'],location=rows[12+j]['location_id'],host=rows[12+j]['host'],PCC=rows[12+j]['PCC'],transformer=rows[12+j]['transformer'],P_column=12+j,Q_column=36+j,P_control=NAMES[12+j],Q_control=NAMES[36+j],positive_sign='Injection; OpenDSS diagnostic load P/Q is negative',signed_exact_validation_slots=[0,31,48,72,95]) for j in range(24)]))
    print('ALL_60_COLUMN_READBACK_PASS',flush=True)
    linear=evaluate_grid(Coefficients(),xx,AX['nodes']);slots=read(H/'B0_REPLAY/SLOTS.json')
    exact=max(slots,key=lambda r:r['max_phase_line_loading_pu']);axis=linear['critical_line_axis'];label=AX['line'][axis]
    assert linear['status']=='PASS' and linear['critical_line']==BRANCHES[axis]
    assert linear['critical_slot']==exact['slot'] and axis==exact['line_axis'] and label==exact['line_witness']
    assert abs(linear['rho_max']-exact['max_phase_line_loading_pu'])<=1e-10
    parts=label.split('|');bus=parts[2].split('.')[0].lower()
    phase=AX['native_secondary_bus_primary_phase'].get(bus)
    assert phase is not None,('Witness primary phase needs topology resolution',label)
    save(H/'P1_EXACT_B0_WITNESS_BINDING.json',dict(status='PASS',optimizer_P1=linear['rho_max'],exact_AC_max_line_loading=exact['max_phase_line_loading_pu'],absolute_difference=abs(linear['rho_max']-exact['max_phase_line_loading_pu']),optimizer_branch=linear['critical_line'],physical_axis=axis,physical_label=label,slot_zero_based=exact['slot'],slot_one_based=exact['slot']+1,time_start=f"{exact['slot']//4:02}:{(exact['slot']%4)*15:02}",line_element=parts[0],terminal=parts[1],bus_connection=parts[2],conductor=parts[3],native_primary_phase=phase,phase_resolution='Frozen native load/secondary-to-primary topology inventory; not inferred from spelling',all_96_linear_grid_baselines=linear))
    print('P1_EXACT_WITNESS_PASS',flush=True)
if __name__=='__main__':main()
