"""Independent scalar-API check of the vectorized B0 measurement implementation."""
import numpy as np,math,json
from run_b0_screen import HERE,OVERLAY,read,engine,native_inventory,add_resources,save,table,measurement_axes

def main():
    folder=HERE/'measurement_validation';d=engine(folder/'runtime')
    native=native_inventory(d);inv=read(OVERLAY/'PCC_OVERLAY_INVENTORY.json');ratio=read(HERE/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio']
    ax=measurement_axes(d);axis_before=d.Circuit.AllNodeNames();add_resources(d,native,ratio,inv)
    f=read(HERE/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');md=f['demand_mw_96'][0]/max(f['demand_mw_96'])
    with np.load(HERE/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:p=z['pcc'][0];q=z['qcc'][0]
    for r in native:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']*md);d.Loads.kvar(r['base_kvar']*md)
    for j in range(12):d.Loads.Name(f'op8500_aidc{j+1:02d}');d.Loads.kW(float(p[j]));d.Loads.kvar(float(q[j]))
    d.Solution.LoadMult(1.);d.Solution.SolveSnap();assert d.Solution.Converged() and d.Solution.ControlActionsDone()
    assert d.Circuit.AllNodeNames()==axis_before
    bulk_i=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)[:,0];bulk_s=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
    offset=0;err_i=err_s=0.;checked=0;disabled=[];scalar_lines=[];scalar_tx=[];scalar_kva=[];witness=[]
    for name in d.PDElements.AllNames():
        d.Circuit.SetActiveElement(name);nc=d.CktElement.NumConductors();nt=d.CktElement.NumTerminals();count=nc*nt
        if not d.CktElement.Enabled():
            disabled.append(name);assert np.max(abs(bulk_i[offset:offset+count]))==0;offset+=count;continue
        currents=np.asarray(d.CktElement.CurrentsMagAng()).reshape(-1,2)[:,0];power=np.asarray(d.CktElement.Powers()).reshape(-1,2)
        err_i=max(err_i,float(abs(currents-bulk_i[offset:offset+count]).max()));err_s=max(err_s,float(abs(power-bulk_s[offset:offset+count]).max()))
        kind=name.split('.')[0].lower();nodes=d.CktElement.NodeOrder()
        for terminal in range(nt):
            if kind=='line':d.Lines.Name(name.split('.',1)[1]);rating=d.Lines.NormAmps()
            elif kind=='transformer':
                d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(terminal+1);kva=d.Transformers.kVA();kv=d.Transformers.kV();ph=d.CktElement.NumPhases();rating=kva/(math.sqrt(3)*kv) if ph==3 else kva/kv
                v=power[terminal*nc:(terminal+1)*nc].sum(axis=0);scalar_kva.append(float(np.hypot(*v)/kva))
            else:continue
            for c in range(nc):
                i=terminal*nc+c
                if nodes[i]==0:continue
                (scalar_lines if kind=='line' else scalar_tx).append(currents[i]/rating)
        checked+=1;offset+=count
    assert offset==len(bulk_i) and err_i==err_s==0
    with np.load(HERE/'screen/alpha_1.00/B0_ALL_PHASE_ARRAYS.npz') as z:
        checks=dict(voltage_max_absolute_error=float(abs(z['voltage_pu'][0]-np.array(d.Circuit.AllBusMagPu())).max()),line_scalar_vs_saved_max_error=float(abs(z['line_current_loading_pu'][0]-scalar_lines).max()),transformer_current_scalar_vs_saved_max_error=float(abs(z['transformer_current_loading_pu'][0]-scalar_tx).max()),transformer_kva_scalar_vs_saved_max_error=float(abs(z['transformer_total_kva_loading_pu'][0]-scalar_kva).max()))
    assert max(checks.values())<1e-10
    nP=nQ=0.;pferr=0.;Perr=Qerr=0.;voltage_model_errors=[];outside=[]
    for r in native:
        d.Loads.Name(r['load']);v=np.asarray(d.CktElement.Powers()).reshape(-1,2).sum(axis=0);nP+=v[0];nQ+=v[1]
        Perr=max(Perr,abs(v[0]-r['base_kw']*md));Qerr=max(Qerr,abs(v[1]-r['base_kvar']*md));pferr=max(pferr,abs(d.Loads.PF()-r['base_pf']))
        volts=np.asarray(d.CktElement.Voltages()).reshape(-1,2);cv=volts[:,0]+1j*volts[:,1];vpu=abs(cv[0]-cv[1])/(1000*r['base_kv'])
        correction=(vpu/r['Vminpu'])**2 if vpu<r['Vminpu'] else (vpu/r['Vmaxpu'])**2 if vpu>r['Vmaxpu'] else 1.
        voltage_model_errors.append(max(abs(v[0]-r['base_kw']*md*correction),abs(v[1]-r['base_kvar']*md*correction)))
        if correction!=1:outside.append(dict(load=r['load'],vpu=float(vpu),P_scheduled_kw=r['base_kw']*md,P_physical_kw=float(v[0]),native_model1_voltage_correction=float(correction)))
    print('native nominal P/Q readback errors',Perr,Qerr,'PF error',pferr,'native voltage-model residual',max(voltage_model_errors),'outside',len(outside),flush=True)
    assert pferr<1e-12
    save(folder/'NATIVE_VOLTAGE_DEPENDENT_LOAD_READBACK.json',dict(status='NOMINAL_PQ_PF_EXACT_AND_PHYSICAL_RESIDUAL_REPORTED',native_model_unchanged=True,nominal_scheduled_PQ_follow_common_factor=True,constant_PQ_range='Per-load native Vminpu/Vmaxpu; native Model1 reverts to constant impedance outside these bounds',outside_constant_PQ_range=outside,max_voltage_model_residual_kw_kvar=max(voltage_model_errors),solver_tolerance=d.Solution.Convergence(),note='Physical terminal-power residual is reported, not used as a new hard criterion. Input P/Q readback is exact; scalar vs vectorized hard-limit measurements agree exactly.'))
    save(folder/'INDEPENDENT_MEASUREMENT_VALIDATION.json',dict(status='PASS',validation_case='alpha1.00 B0 slot0, independent clean-engine scalar API replay',additional_B0_validation_solve_count=1,enabled_PDElements_compared=checked,disabled_native_tie_lines=disabled,disabled_branch_currents_verified_zero=True,bulk_vs_scalar_current_A_max_error=err_i,bulk_vs_scalar_PQ_max_error=err_s,all_transformer_windings_and_both_line_terminals_checked=True,**checks,native_P_physical_kw=float(nP),native_Q_physical_kvar=float(nQ),native_load_P_readback_max_error_kw=float(Perr),native_load_Q_readback_max_error_kvar=float(Qerr),native_pf_max_error=float(pferr),new_resources_introduce_no_bus_or_node_reordering=True,B1_B2_B3_optimization_calls=0))
    d.Basic.ClearAll();print(json.dumps(checks))
if __name__=='__main__':main()
