"""May01 read-only causal voltage audit and preregistered equipment tests."""
import copy, math, re, time
import numpy as np
from .may01_common import *

def engine(tag, role='ACTUAL', hardware='H0'):
    from . import full_physical as fp, correction_svr_run as runner
    fp.RUN = RUN
    original_read=runner.read
    from . import correction_svr_implicit as implicit
    original_source=implicit.source_svr
    def syntax_only_source():
        module=original_source()
        # IEEE8500 contains native names such as regxfmr_190-8593. This
        # expands identifier validation only, without changing a bus or wire.
        module._BUS=re.compile(r'^[a-zA-Z0-9_\-]+(?:\.[0-3])*$')
        return module
    implicit.source_svr=syntax_only_source
    if hardware not in ('H0','H0_SOURCE_YY') and role=='ACTUAL':
        contract=read(OUT/'MAY01_HARDWARE_PREREGISTRATION.json')['contracts'][hardware]
        def selected(p):
            if Path(p).name=='SVR_CANDIDATE_PREREGISTRATION.json':
                return dict(contracts={'S1_03':contract})
            return original_read(p)
        runner.read=selected
    try:e = fp.engine('MAY01_' + tag, role)
    finally:
        runner.read=original_read;implicit.source_svr=original_source
    if hardware=='H0_SOURCE_YY':
        before=e.control_state();oldphase={(a['element'],a['terminal'],a['conductor']):a['physical_phase'] for a in e.line_axes}
        for j in range(1,13):
            e.d.Text.Command(f'edit Transformer.full_mobile_idc{j:02d} conns=[wye wye] %rs=[.8 .2] xhl=5.75 wdg=1 rneut=-1 wdg=2 rneut=-1')
        e.d.Text.Command('calcvoltagebases');e.d.Solution.ControlMode(-1);e.d.Solution.Solve();e.d.Solution.ControlMode(2)
        assert e.control_state()==before and not e.queue(e.d)
        from . import correction as c
        e.inventory=e._inventory();e._orient_original_lines();e._prepare_array_axes();e.orientation=c.independent_orientation(e)
        e.canonical,e.security,e.cmv,e.clv=c.masks(e.line_axes,e.orientation)
        e.all_mask=e.canonical;e.mv_mask=e.cmv;e.lv_mask=e.clv;e.triplex_mask=e.clv
        for a in e.line_axes:a['physical_phase']=oldphase[a['element'],a['terminal'],a['conductor']]
    return e

def preregister():
    from .correction_svr import graph,path_to,SV
    init(); assert (OUT/'MAY01_BASELINE_DIAGNOSIS_SEAL.json').exists()
    target=OUT/'MAY01_HARDWARE_PREREGISTRATION.json'
    if target.exists():return read(target)
    e=engine('PREREGISTRATION_GRAPH');parents,meta=graph(e)
    old=read(SV/'SVR_CANDIDATE_PREREGISTRATION.json')['contracts']['S1_03']
    used={u['cut_element'].lower() for u in old['units']}; additions=[]
    # Placement is frozen from existing May01 bad-node paths before candidate AC.
    for bus,reason in [('m1047534','IDC08 LV overvoltage MV ancestor'),
                       ('sx3312692a','Prefix undervoltage MV ancestor'),
                       ('190-8593','Prefix overvoltage upstream of original regulator')]:
        candidates=[]
        for edge in path_to(bus,parents):
            r=meta.get(edge['element'].lower())
            if not r or r['element'].lower() in used:continue
            if r['element'].lower().startswith('line.') and r['group']=='Primary' and r['nphase']==3 and r['node_order'][:3]==[1,2,3] and r['buses'][0].split('.')[0].lower()==edge['parent']:
                candidates.append((edge,r))
        assert candidates
        edge,r=candidates[-1];used.add(r['element'].lower());u=copy.deepcopy(old['units'][0]);j=len(additions)+4
        kv=12.47/math.sqrt(3)
        u.update(id=f'B{j:02d}',cut_element=r['element'],original_bus_spec=r['buses'][0],
            upstream_new_bus=f'v2may_svr_b{j:02d}',downstream_bus=edge['child'],sensed_bus=edge['child'],
            nominal_kv_ln=kv,sensed_kv_ln=kv,phase_kva=r['normal_amps']*kv,ctprim=r['normal_amps'],
            ptratio=kv*1000/120,remote_ptratio=kv*1000/120,selection_reason=reason,
            downstream_undervoltage_nodes=[],site_selection_S0_only=False)
        additions.append(u)
    contracts={'H0':old}
    h1=copy.deepcopy(old);h1['units']=h1['units'][:2]+[additions[0]];contracts['H1']=h1
    for i,name in enumerate(('H2','H3','H4'),1):
        c=copy.deepcopy(old);c['units']+=copy.deepcopy(additions[:i]);contracts[name]=c
    return put(target.name,dict(status='FROZEN_BEFORE_NEW_EQUIPMENT_OPERATING_AC',contracts=contracts,
        candidate_count=5,day='2025-05-01',beta=2.,P5_original_unchanged=True,
        source_hardware_model='Original V44 full-power serial regulator, inherited ratings/losses/delays',
        target_rule='Nearest unused original three-phase MV line ancestor of the sealed violation bus',
        test_order=['H0','H1','H2','H3','H4'],Planning='S0 unchanged; separate TIME check',
        initial_taps='1.0 original cold initial state, no invented history',
        automatic_selection_requires_all_Planning_Prefix_Actual_PQ_gates=True))

def run_candidates():
    init();preregister()
    from . import full_days
    import types
    with np.load(PRIOR/'daily_r0/2025-05-01/INPUTS.npz') as z:a={k:z[k] for k in z.files}
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    assert day['day']=='2025-05-01'
    out=[]
    for h in ('H0','H1','H2','H3','H4'):
        folder=RUN/'hardware'/h;folder.mkdir(parents=True,exist_ok=True)
        def selected(tag,role):return engine('CAND_'+h+'_'+tag,role,h)
        fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,
            engine=selected,table=lambda n,r:table(h+'_'+n,r)),argdefs=full_days.run.__defaults__)
        fn.__kwdefaults__=full_days.run.__kwdefaults__
        r=fn(day,'ACTUAL',a)
        out.append(dict(candidate=h,banks=len(read(OUT/'MAY01_HARDWARE_PREREGISTRATION.json')['contracts'][h]['units']),
            global_loading_percent=100*r['rho_global'],MV_percent=100*r['rho_MV'],LV_percent=100*r['rho_LV'],
            Vmin=r['event_Vmin'],Vmax=r['event_Vmax'],eval_Vmin=r['evaluation_event_Vmin'],eval_Vmax=r['evaluation_event_Vmax'],
            low_seconds=r['voltage_violation_seconds']['low'],high_seconds=r['voltage_violation_seconds']['high'],
            full_TIME_PASS=r['full_TIME_PASS'],evaluated_TIME_PASS=r['evaluated_TIME_PASS'],
            Planning_TIME_PASS=False,selected=False,receipt=record(folder/'2025-05-01_ACTUAL/RECEIPT.json')['path']))
        table('MAY01_SVR_HARDWARE_COMPARISON.csv',out)
    put('MAY01_HARDWARE_SELECTION.json',dict(selected=None,reason='No candidate satisfies original causal Prefix and separate Planning TIME gates',
        original_baseline_retained='H0',candidate_results=out,retuned_original_P5=False,full_DAY_certification=False))

def port_snapshot():
    init(); start=time.perf_counter()
    e=engine('PORT_SNAPSHOT');e.mode='STATIC'
    trace=read(PRIOR/'daily_r0/2025-05-01_ACTUAL/TRACE.json')
    frame=next(x for x in trace if x['physical_seconds']==44134.)
    state=copy.deepcopy(e.initial_state)
    for c in frame['controls']:state['taps'][c['transformer']][c['winding']-1]=c['tap']
    state['capacitors']=frame['capacitors']
    e.apply('ACTUAL',49,2.);row,a,_,_=e.measure('ACTUAL',49,2.,state=state,fixed=True)
    with np.load(PRIOR/'daily_r0/2025-05-01_ACTUAL/AC.npz') as z:
        events=read(PRIOR/'daily_r0/2025-05-01_ACTUAL/EVENTS.json')
        ix=next(i for i,x in enumerate(events) if x['physical_seconds']==44134.)
        voltage_error=float(np.max(abs(a['node_voltage_pu']-z['node_voltage_pu'][ix])))
    assert voltage_error<1e-7
    def bus(name):
        e.d.Circuit.SetActiveBus(name);v=np.asarray(e.d.Bus.Voltages()).reshape(-1,2)
        return v[:,0]+1j*v[:,1]
    mv=bus(e.pccs['IDC08']['mv_bus']);lv=bus(e.pccs['IDC08']['bus'])
    # OpenDSS delta/wye phase ordering here maps LV A/B/C to MV CA/AB/BC.
    predicted=np.roll(np.abs(mv[:3]-np.roll(mv[:3],-1)),1)/(12.47*1000)
    measured=np.abs(lv[:3])/(.48*1000/math.sqrt(3))
    alternatives=[dict(connection='Delta/grounded-Wye adopted research hardware',V_LV_phase_pu=measured.tolist(),
        ideal_delta_transfer_pu=predicted.tolist(),readback=transformer(e.d,'full_mobile_idc08'),
        unchanged_voltage_base=True)]
    for neutral,label in [(-1,'Source Wye/Wye Rneut=-1; neutral node0'),(0,'Wye/Wye Rneut=0 LV; neutral node0 engineering alternative')]:
        e.d.Text.Command('edit Transformer.full_mobile_idc08 conns=[wye wye] %rs=[.8 .2] xhl=5.75 wdg=1 rneut=-1 wdg=2 rneut='+str(neutral))
        e.apply('ACTUAL',49,2.);r,b,_,_=e.measure('ACTUAL',49,2.,state=state,fixed=True)
        alternatives.append(dict(connection=label,V_LV_phase_pu=(abs(bus(e.pccs['IDC08']['bus'])[:3])/(480/math.sqrt(3))).tolist(),
            all_node_Vmin=r['Vmin'],all_node_Vmax=r['Vmax'],readback=transformer(e.d,'full_mobile_idc08'),
            no_daily_TIME_certificate=True,adopted=False))
    put('IDC08_ZERO_OUTPUT_CAUSAL_SNAPSHOT.json',dict(slot=49,original_physical_seconds=44134.,
        existing_native_state_reconstructed_only_for_static_diagnosis=True,whole_voltage_replay_max_error=voltage_error,
        voltage_base_LV_LL_kV=.48,zero_MESS_output=True,
        delta_transfer_max_error=float(np.max(abs(predicted-measured))),MV_phase_pu=(abs(mv[:3])/(12470/math.sqrt(3))).tolist(),
        observed_phase_mapping='LV A/B/C <- MV CA/AB/BC',
        alternatives=alternatives,source_wye_requires_grounding_engineering_review=True,
        no_model_error_in_delta_voltage_base_or_nominal_rating=True,
        conclusion='Legitimate delta line-to-line transfer of unbalanced MV phasors; zero-output LV violation is real under the adopted hardware.',
        accepted_hardware_change=False))
    # Restore adopted equipment before the finite PQ readback; no original
    # feeder or STA transformer parameters are changed.
    e.d.Text.Command('edit Transformer.full_mobile_idc08 conns=[delta wye] %rs=[.5 .5] xhl=5.662375826453062 wdg=1 rneut=-1 wdg=2 rneut=0')
    cases=[]
    for s in sorted(e.pccs):
        if s.startswith('AIDC'):continue
        for p,q in [(0,0),(-300,-250),(-300,0),(-300,250),(0,-250),(0,250),(300,-250),(300,0),(300,250),(-150,-125),(-150,125),(150,-125),(150,125)]:
            guard(start)
            e.apply('ACTUAL',49,2.,mess={s:(p,q)})
            r,b,_,ports=e.measure('ACTUAL',49,2.,state=state,fixed=True)
            port=next(v for v in ports if v['site']==s)
            vv=abs(bus(e.pccs[s]['bus'])[:3])/(480/math.sqrt(3))
            cases.append(dict(site=s,P_injection_kw=-p,Q_injection_kvar=-q,local_Vmin=float(vv.min()),local_Vmax=float(vv.max()),
                whole_Vmin=r['Vmin'],whole_Vmax=r['Vmax'],local_voltage_PASS=bool(vv.min()>=.95-1e-8 and vv.max()<=1.05+1e-8),
                port_current_loading=port['current_loading'],port_kVA_loading=port['interface_loading'],
                port_thermal_PASS=port['current_loading']<=1 and port['interface_loading']<=1,
                all_transformer_current_max=r['transformer_current_max'],all_transformer_kVA_max=r['transformer_nameplate_max'],
                converged=r['converged'],instantaneous_only=True,day_schedule_SOC_certified=False))
    table('ALL24_PORT_INSTANTANEOUS_PQ_SECURITY.csv',cases)
    put('MAY01_ALL24_PORT_VOLTAGE_CERTIFICATION.json',dict(PASS=False,ports=24,readback_cases=len(cases),
        all_port_thermal_PASS=all(x['port_thermal_PASS'] for x in cases),
        all_instantaneous_local_voltage_PASS=all(x['local_voltage_PASS'] for x in cases),
        zero_output_IDC08_overvoltage_reproduced=True,instantaneous_box_not_daily_schedule=True,
        original_V44_connection_fully_equivalent=False,source_and_adopted_readbacks=record(OUT/'ALL24_PORT_ELECTRICAL_READBACK.json'),
        causal_snapshot=record(OUT/'IDC08_ZERO_OUTPUT_CAUSAL_SNAPSHOT.json'),
        no_arbitrary_Z_rating_or_Base_change=True,FIELD_INSTALLATION_UNVERIFIED=True))
    print('PORT SNAPSHOT',voltage_error,'PQ',len(cases),flush=True)

def transformer(d, name):
    d.Transformers.Name(name)
    out = dict(name=name, buses=list(d.CktElement.BusNames()), windings=[])
    out['node_order']=d.CktElement.NodeOrder();out['conductors']=d.CktElement.NumConductors()
    for w in (1, 2):
        d.Transformers.Wdg(w)
        out['windings'].append(dict(winding=w, kV=d.Transformers.kV(), kVA=d.Transformers.kVA(),
            delta=d.Transformers.IsDelta(), tap=d.Transformers.Tap(), R_pct=d.Transformers.R(),
            Rneut=d.Transformers.Rneut(), Xneut=d.Transformers.Xneut()))
    d.Circuit.SetActiveElement('Transformer.' + name)
    out['properties'] = {k: d.Properties.Value(k) for k in
        ('XHL', '%NoLoadLoss', '%Imag', 'Conns', 'kVs', '%Rs', 'Taps', 'NormHkVA', 'EmergHkVA','LeadLag')}
    for bus in out['buses']:
        d.Circuit.SetActiveBus(bus.split('.')[0])
        out.setdefault('bus_readback', []).append(dict(bus=bus, kV_base_LN=d.Bus.kVBase(),
            nodes=d.Bus.Nodes(), voltage_magnitude_angle=d.Bus.VMagAngle()))
    return out

def audit():
    init(); start=time.perf_counter()
    if (OUT/'MAY01_BASELINE_DIAGNOSIS_SEAL.json').exists():
        return read(OUT/'MAY01_BASELINE_DIAGNOSIS_SEAL.json')
    e=engine('ROOT_CAUSE_PORT_READBACK')
    from .correction_svr import graph, path_to, SV
    parents, meta=graph(e)
    source=read(OLD/'IDC_ORIGINAL_PHYSICAL_CONTRACT.json')
    import opendssdirect as odd
    d=odd.NewContext(); d.Text.Command('clear'); d.Text.Command('new circuit.source_audit basekv=4.16 pu=1 phases=3 bus1=149')
    d.Text.Command(re.sub(r'\r?\n~\s*', ' ', source['source_blocks']['IDC01']))
    d.Text.Command('set voltagebases=[4.16 .48]'); d.Text.Command('calcvoltagebases'); d.Text.Command('set controlmode=off'); d.Solution.Solve()
    original=transformer(d,'MESS_IDC01_TX')
    ports=[]
    for p in e.port_meta:
        s=p['site'];name=('full_mobile_'+s.lower()) if s.startswith('IDC') else ('high_mv_'+s.lower())
        ports.append(dict(site=s,port=p,transformer=transformer(e.d,name),source_equivalent_connection=False if s.startswith('IDC') else None))
    put('ALL24_PORT_ELECTRICAL_READBACK.json',dict(original_V44_IDC_transformer=original,ports=ports,
        original_source=source['source'],new_IDC_connection='delta/grounded-wye',
        arbitrary_impedance_or_base_retuning=False,field_status='FIELD_INSTALLATION_UNVERIFIED'))
    paths={};violations=[]; cases=[]
    for role in ('PLANNING','ACTUAL'):
        folder=PRIOR/'daily_r0'/('2025-05-01_'+role)
        axes=read(OLD/('FULL_AXES.json' if role=='ACTUAL' else 'GRID_AXES.json'))['nodes']
        events=read(folder/'EVENTS.json');clock=read(folder/'CLOCK.json');trace=read(folder/'TRACE.json')
        with np.load(folder/'AC.npz') as z: v=z['node_voltage_pu'];slots=z['event_slot']
        grouped={}
        for j,event in enumerate(events): grouped.setdefault(event['slot'],[]).append(j)
        for j,event in enumerate(events):
            guard(start)
            t=event['slot'];order=grouped[t];k=order.index(j)
            until=events[order[k+1]]['physical_seconds'] if k+1<len(order) else clock[t]['end_seconds']
            frame=next(f for f in trace if f['physical_seconds']==event['physical_seconds'])
            pending=frame['queue']
            for n in np.flatnonzero((v[j]<.95-1e-8)|(v[j]>1.05+1e-8)):
                node=axes[n];bus=node.rsplit('.',1)[0].lower()
                if bus not in paths:
                    paths[bus]=path_to(bus,parents) if bus in parents else []
                path_tx={x['element'].split('.',1)[1].lower() for x in paths[bus] if x['element'].lower().startswith('transformer.')}
                upstream=[r for r in frame['controls'] if r['transformer'].lower() in path_tx]
                group='IDC_480V' if node.startswith('full_mobile_idc') else ('STA_480V' if node.startswith('high_mv_sta') else 'ORIGINAL_OR_SVR')
                violations.append(dict(role=role,node=node,phase=node.rsplit('.',1)[1],scope='PREFIX24' if role=='ACTUAL' and t<24 else 'EVALUATION96',
                    slot=t,physical_seconds=event['physical_seconds'],until_seconds=until,duration_seconds=max(0,until-event['physical_seconds']),
                    pu=float(v[j,n]),kind='LOW' if v[j,n]<.95 else 'HIGH',node_group=group,path_bus_key=bus,
                    control_timing='INITIAL_BEFORE_FIRST_DELAY' if event['physical_seconds']<15 else ('NATIVE_ACTION_PENDING' if pending else 'NO_PENDING_ACTION'),
                    pending_queue=str(pending),upstream_taps=str({r['regcontrol']:r['tap'] for r in upstream}),
                    upstream_saturated=sum(r['at_lower'] or r['at_upper'] for r in upstream)))
        receipt=read(folder/'RECEIPT.json')
        cases.append(dict(role=role,receipt=record(folder/'RECEIPT.json'),full_TIME_PASS=receipt['full_TIME_PASS'],
            voltage_violation_seconds=receipt['voltage_violation_seconds'],Vmin=float(v.min()),Vmax=float(v.max())))
    table('MAY01_ALL_NODE_VOLTAGE_VIOLATIONS.csv',violations)
    put('MAY01_VIOLATION_UPSTREAM_PATHS.json',paths)
    put('MAY01_BASELINE_DIAGNOSIS_SEAL.json',dict(base=BASE,source=SOURCE,cases=cases,
        original_readbacks=record(OUT/'ALL24_PORT_ELECTRICAL_READBACK.json'),violations=record(OUT/'MAY01_ALL_NODE_VOLTAGE_VIOLATIONS.csv'),
        paths=record(OUT/'MAY01_VIOLATION_UPSTREAM_PATHS.json'),new_equipment_AC_before_seal=0,
        original_12_saturated_controls=0,physical_delays_unchanged=True,previous_history_certified=False))
    print('VOLTAGE AUDIT',len(violations),'node/event violations',flush=True)

if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='candidates':run_candidates()
    elif len(sys.argv)>1 and sys.argv[1]=='ports':port_snapshot()
    else:audit()
