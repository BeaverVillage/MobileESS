"""Development candidate: eliminate native LDC tap hysteresis with its deadband.

No tap is set, scheduled, estimated as a decision, or added to a solver.
For a settled, unsaturated original RegControl, Vc=V/PT+Z*I_into/CT.
Thus |V|²=PT²|Vc|²+2PT/CT Re(conj(Z)*S_delivered)
          -PT²/CT² |Z|²|I|².
Use both physical deadband endpoints and the existing finite winding-current
limit. Relative downstream voltage remains a local response approximation;
this candidate is NOT an unconditional nonlinear certificate. Release requires
separate reoptimization and independent full-day Forecast diagnostics.
"""
import numpy as np

VERSION='V42_NATIVE_LDC_DEADBAND_INTERVAL_DEVELOPMENT_V1'

def descriptors(engine,branches,nodes,inventory,thermal):
    names=tuple(f'{b.branch_id}::{b.phase}' for b in branches)
    currents={r['branch_phase'].lower():r for r in thermal['rows']}
    controlled={'transformer.'+r['transformer'].lower() for r in inventory['regulators']}
    adjacency={}
    for b in branches:adjacency.setdefault((b.parent_bus.lower(),b.phase.lower()),[]).append(b)
    result=[]
    for regulator in inventory['regulators']:
        if regulator['name'] not in ('creg4a','creg4b','creg4c'):continue
        element='transformer.'+regulator['transformer'].lower()
        branch=next(b for b in branches if b.branch_id.lower()==element)
        phase=branch.phase.lower();suffix={'a':'1','b':'2','c':'3'}[phase]
        reference=branch.child_bus.lower()+'.'+suffix
        engine.Circuit.SetActiveBus(branch.child_bus)
        base_V=1000*float(engine.Bus.kVBase())
        if not base_V>0:raise ValueError('LDC_REFERENCE_BASE_UNAVAILABLE')
        props=regulator['resolved_properties'];pt=float(props['PTRatio']);ct=float(props['CTPrim'])
        rr=float(props['R']);xx=float(props['X']);vreg=float(props['VReg']);band=float(props['Band'])
        if min(pt,ct,vreg,band)<=0 or min(rr,xx)<0:raise ValueError('UNSUPPORTED_ORIGINAL_LDC_CONTRACT')
        engine.Transformers.Name(regulator['transformer']);engine.Transformers.Wdg(1);kv1=engine.Transformers.kV()
        engine.Transformers.Wdg(regulator['winding']);kv2=engine.Transformers.kV()
        winding_max=float(currents[(element+'::'+branch.phase).lower()]['NormalAmps'])*kv1/kv2
        pending=[branch.child_bus.lower()];seen=set()
        while pending:
            bus=pending.pop()
            if bus in seen:continue
            seen.add(bus)
            for child in adjacency.get((bus,phase),[]):
                if child.branch_id.lower() not in controlled:pending.append(child.child_bus.lower())
        affected=[i for i,node in enumerate(nodes) if node.rsplit('.',1)[-1]==suffix and node.rsplit('.',1)[0] in seen]
        # Fixed capacitors remain voltage-dependent: Q=-C|V|². The old absolute
        # voltage response can therefore contaminate the apparent LDC flow
        # sensitivity. Remove that affine component and use its physical
        # .95²/.1.05² operating bounds, independently of any diagnostic day.
        pending=[branch.child_bus.lower()];whole=set()
        while pending:
            bus=pending.pop()
            if bus in whole:continue
            whole.add(bus)
            pending.extend(b.child_bus.lower() for b in adjacency.get((bus,phase),[]))
        caps=[]
        for name in engine.Capacitors.AllNames():
            engine.Capacitors.Name(name);engine.Circuit.SetActiveElement('Capacitor.'+name)
            bus=engine.CktElement.BusNames()[0];parent=bus.split('.')[0].lower()
            if parent not in whole:continue
            phases=int(engine.CktElement.NumPhases());order=engine.CktElement.NodeOrder()[:engine.CktElement.NumConductors()]
            if int(suffix) not in order:continue
            if str(engine.Properties.Value('Conn')).lower()!='wye':raise ValueError('LDC_DELTA_CAPACITOR_BOUND_NOT_IMPLEMENTED')
            if tuple(engine.Capacitors.States())!=(1,):raise ValueError('LDC_FIXED_ON_CAPACITOR_REQUIRED')
            engine.Circuit.SetActiveBus(parent);nodebase=1000*engine.Bus.kVBase()
            nominal=1000*engine.Capacitors.kV()/(3**.5 if phases==3 else 1)
            caps.append(dict(name=name,node_index=nodes.index(parent+'.'+suffix),
                kvar_at_node_1pu=engine.Capacitors.kvar()/phases*(nodebase/nominal)**2))
        result.append(dict(controller=regulator['name'],reference_node=reference,reference_index=nodes.index(reference),
            affected_indices=affected,branch_index=names.index(element+'::'+branch.phase),base_V=base_V,
            PT=pt,CT=ct,R=rr,X=xx,Vreg=vreg,Band=band,winding_current_upper_A=winding_max,
            original_tap_min=regulator['min_tap'],original_tap_max=regulator['max_tap'],
            voltage_dependent_fixed_capacitors=caps,
            validity='settled original LDC sensing inside physical deadband; unsaturated control; local relative voltage/flow approximation'))
    return result

def project(row,contracts):
    lower=np.asarray(row['voltage_constant']).copy();upper=lower.copy()
    ml=np.asarray(row['voltage_matrix']).copy();mu=ml.copy()
    for c in contracts:
        k=c['branch_index'];ref=c['reference_index'];a=c['affected_indices'];scale=c['base_V']**2
        # Parent-side flow is used as the local response of delivered power.
        # Winding losses and relative-voltage nonlinear errors must be measured
        # in development; no empirical offset is added to disguise them.
        factor=2*c['PT']/(c['CT']*scale)*1000
        qp=float(row['flow_q_constant'][k]);qpm=row['flow_q_matrix'][k].copy()
        qm=qp;qmm=qpm.copy()
        for cap in c.get('voltage_dependent_fixed_capacitors',[]):
            i=cap['node_index'];w=cap['kvar_at_node_1pu']
            qp+=w*(row['voltage_constant'][i]-.95**2);qpm+=w*row['voltage_matrix'][:,i]
            qm+=w*(row['voltage_constant'][i]-1.05**2);qmm+=w*row['voltage_matrix'][:,i]
        flow_upper=factor*(c['R']*row['flow_p_constant'][k]+c['X']*qp)
        flow_lower=factor*(c['R']*row['flow_p_constant'][k]+c['X']*qm)
        flow_matrix_upper=factor*(c['R']*row['flow_p_matrix'][k]+c['X']*qpm)
        flow_matrix_lower=factor*(c['R']*row['flow_p_matrix'][k]+c['X']*qmm)
        difference=row['voltage_constant'][a]-row['voltage_constant'][ref]
        relative_slope=row['voltage_matrix'][:,a]-row['voltage_matrix'][:,ref,None]
        upper[a]=(c['PT']*(c['Vreg']+c['Band']/2))**2/scale+flow_upper+difference
        lower[a]=(c['PT']*(c['Vreg']-c['Band']/2))**2/scale+flow_lower+difference-(c['PT']/c['CT'])**2*(c['R']**2+c['X']**2)*c['winding_current_upper_A']**2/scale
        ml[:,a]=relative_slope+flow_matrix_lower[:,None];mu[:,a]=relative_slope+flow_matrix_upper[:,None]
    # Both endpoint faces are enforced, with exactly the original .95²/1.05².
    return dict(row,voltage_constant=np.r_[lower,upper],voltage_matrix=np.c_[ml,mu])
