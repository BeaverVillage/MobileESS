"""Confirm alpha=0 witness without changing any source/control parameter."""
import numpy as np,json
from forensic import HERE,OLD,Model,read,save
def main():
    m=Model(HERE/'independent_alpha_zero');t=37
    for k in range(t+1):m.slot(0.,k)
    s,v,*_=m.measure();d=m.d;P=Q=0.;max_base_p=max_base_q=0.
    for r in m.loads:
        d.Loads.Name(r['load']);max_base_p=max(max_base_p,abs(d.Loads.kW()));max_base_q=max(max_base_q,abs(d.Loads.kvar()));pq=np.array(d.CktElement.Powers()).reshape(-1,2).sum(axis=0);P+=pq[0];Q+=pq[1]
    pv_on=0
    for name in d.Generators.AllNames():d.Generators.Name(name);pv_on+=int(d.CktElement.Enabled())
    AP=AQ=0.
    for r in m.aidcs:
        d.Loads.Name('op8500_'+r['location_id'].lower());pq=np.array(d.CktElement.Powers()).reshape(-1,2).sum(axis=0);AP+=pq[0];AQ+=pq[1]
    caps=m.caps();sources=m.sources()
    d.Vsources.First();source_power=np.array(d.CktElement.Powers()).reshape(-1,2).sum(axis=0)
    with np.load(OLD/'screen/alpha_0.00/B0_ALL_PHASE_ARRAYS.npz') as z:err=float(abs(v-z['voltage_pu'][t]).max())
    assert max_base_p==max_base_q==P==Q==0 and pv_on==0 and err<1e-10 and s['Vmax_pu']>1.05+1e-9
    result=dict(status='ALPHA_ZERO_OVERVOLTAGE_INDEPENDENTLY_REPRODUCED',alpha=0.,slot=t,metrics=s,voltage_array_max_abs_error_vs_immutable_alpha_zero=err,native_loads=2354,native_scheduled_P_kw_max_abs=max_base_p,native_scheduled_Q_kvar_max_abs=max_base_q,native_physical_total_P_kw=float(P),native_physical_total_Q_kvar=float(Q),enabled_PV_generators=pv_on,AIDC_physical_P_kw=float(AP),AIDC_physical_Q_kvar=float(AQ),total_capacitor_physical_injection_kvar=sum(c['physical_injected_kvar'] for c in caps),source_delivered_P_kw=float(-source_power[0]),source_delivered_Q_kvar=float(-source_power[1]),capacitors=caps,source=sources,regulators=m.regs(),native_source_regulator_capacitor_parameter_changes=0,B1_B2_B3_runs=0,explicit_snapshot_solves=38,interpretation='Background demand and PV are exactly zero; unchanged AIDC and native shunts/source/controls remain. This is not a zero-total-injection feeder. Together with the preserved full grid, this independently supports background scaling alone being insufficient on that grid; no universal off-grid impossibility claim.')
    save(HERE/'INDEPENDENT_ALPHA_ZERO_CONFIRMATION.json',result);d.Basic.ClearAll();print(json.dumps({k:result[k] for k in ['status','native_physical_total_P_kw','native_physical_total_Q_kvar','AIDC_physical_P_kw','total_capacitor_physical_injection_kvar','source_delivered_Q_kvar']}))
if __name__=='__main__':main()
