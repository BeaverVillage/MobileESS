import numpy as np

def control_state(d,t,expected_source,expected_vreg):
    regs=[];caps=[]
    for name in d.RegControls.AllNames():
        d.RegControls.Name(name);tf=d.RegControls.Transformer();tap=d.RegControls.TapNumber();vreg=d.RegControls.ForwardVreg();band=d.RegControls.ForwardBand();ratio=float(d.Properties.Value('ptratio'));enabled=d.CktElement.Enabled();w=d.RegControls.TapWinding()
        d.Transformers.Name(tf);d.Transformers.Wdg(w);regs.append(dict(name=name,transformer=tf,tap_number=tap,tap_pu=d.Transformers.Tap(),Vreg=vreg,band=band,PT_ratio=ratio,enabled=enabled,min_tap=d.Transformers.MinTap(),max_tap=d.Transformers.MaxTap()))
    for name in d.Capacitors.AllNames():
        d.Capacitors.Name(name);en=d.CktElement.Enabled();states=list(d.Capacitors.States());kv=d.Capacitors.kV();kvar=d.Capacitors.kvar()
        q=float(-np.asarray(d.CktElement.Powers()).reshape(-1,2)[:,1].sum()) if en else 0.
        caps.append(dict(name=name,enabled=en,step_states=states,effective_ON=en and any(states),nameplate_kvar=kvar,nominal_kV=kv,physical_injected_kvar=q))
    ctrls=[]
    for name in d.CapControls.AllNames():d.CapControls.Name(name);ctrls.append(dict(name=name,enabled=d.CktElement.Enabled(),capacitor=d.CapControls.Capacitor()))
    d.Vsources.First();source=d.Vsources.PU()
    assert source==expected_source
    assert all(r['Vreg']==expected_vreg and r['band']==2 and r['PT_ratio']==60 and r['enabled'] for r in regs)
    assert all(c['enabled']==(c['name']!='capbank3') for c in caps) and all(c['enabled'] for c in ctrls)
    return dict(slot=t,source_pu=source,regulators=regs,capacitors=caps,capcontrols=ctrls,control_iterations=d.Solution.ControlIterations(),powerflow_iterations=d.Solution.Iterations())
