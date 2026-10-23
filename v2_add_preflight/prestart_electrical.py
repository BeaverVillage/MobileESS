"""Finite prestart electrical diagnostics; no optimization or campaign runs."""
from pathlib import Path
import csv,json
import numpy as np
from .prestart import OUT,RUN,ROOT,DOC,RUNTIME,read,sha,put,table,record,digest,INITIAL,resources

def prefix():
    cases=[RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03',RUNTIME/'correction_time100/TIME_2.00_PLANNING_B0']
    rows=[];certs=[]
    for folder in cases:
        rec=read(folder/'RECEIPT.json');events=read(folder/'EVENT_ROWS.json');clock=read(folder/'EVENTS.json')
        axes=read(folder/'AXES.json')
        with np.load(folder/'AC_FULL.npz') as z:v=z['node_voltage_pu'];slots=z['event_slot']
        actual='ACTUAL' in folder.name;lo=hi=0.
        for j,e in enumerate(events):
            end=events[j+1]['physical_seconds'] if j+1<len(events) and slots[j+1]==slots[j] else (int(slots[j])+1)*900
            duration=end-e['physical_seconds'];low=float(v[j].min());high=float(v[j].max())
            if low>=.95-1e-8 and high<=1.05+1e-8:continue
            scope='PREFIX' if actual and slots[j]<24 else 'EVALUATION'
            if scope=='PREFIX':lo+=duration*(low<.95-1e-8);hi+=duration*(high>1.05+1e-8)
            ce=next(x for x in clock[int(slots[j])]['events'] if x['absolute_seconds']==e['physical_seconds'])
            rows.append(dict(case=folder.name,scope=scope,slot=int(slots[j]),seconds=e['physical_seconds'],hold_end=end,duration_seconds=duration,
                Vmin=low,Vmax=high,min_node=axes['nodes'][int(v[j].argmin())],max_node=axes['nodes'][int(v[j].argmax())],
                numerical_iterations=ce['electrical_iterations'],control_iterations=ce['control_iterations'],converged=ce['solution_converged'],
                pending_devices=json.dumps([q['device'] for q in ce['pending_queue']]),
                BG_command_error_kw=e['BG_P_abs_error_kw'],PV_command_error_kw=e['PV_total_abs_error_kw'],
                interpretation='NATIVE_CONVERGED_PHYSICAL_HOLD_INTERVAL_NOT_SOLVER_ITERATION'))
        certs.append(dict(case=folder.name,receipt=record(folder/'RECEIPT.json'),prefix_low_seconds=lo,prefix_high_seconds=hi,
            first_solve=events[0],initial_state=rec['initial_state'],
            prior_history='NO_IEEE8500_HISTORY_BEFORE_2025_04_30_18AEST_IN_FROZEN_INPUTS',
            queue_initially_empty=True,causal_prefix_preserved=True,arbitrary_tap_warm_start_applied=False))
    table('PREFIX_AND_PLANNING_NATIVE_VIOLATIONS.csv',rows)
    return put('FINAL_ELECTRICAL_PRESTART_CERTIFICATION.json',dict(status='BLOCKED_INITIAL_OPERATION_HISTORY_AND_PREFIX_SECURITY',
        cases=certs,Actual_evaluation96_PASS=True,Actual_full120_PASS=False,Planning_TIME_events_PASS=False,
        root_cause='Cold all-bank tap/cap initialization followed by real delayed native actions and interacting control responses; causal predecessor state is absent.',
        model_dependent_PQ_cause='Measured command errors are in CSV; do not attribute converged violation holds to numerical iterations.',
        original24_prefix_inputs_cover='18AEST_to_midnight_only',earlier_native_history_reconstruction_certified=False,
        no_valid_history_inference_from_IEEE123=True,new_SVR_hardware_added=False,Source_P5_Delay_ratings_unchanged=True,
        May02_07_full120_security_certified=False))

def make_engine(tag,mode='STATIC'):
    from . import correction as c,correction_svr_run as runner
    from .correction_svr_implicit import source_svr
    from .correction_time100 import clock_class
    c.clock_class=clock_class;runner.source_svr=source_svr
    runner.RUN=RUN;runner.RUN.mkdir(exist_ok=True)
    class Candidate(runner.Instrumented):configuration='S1_03'
    engine=Candidate(tag,'ACTUAL','TIME');engine.mode=mode;engine.d.Solution.MaxIterations(100)
    return engine

def responses():
    resources();e=make_engine('LOCATION_SENSITIVITY');saved=RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03'
    states=read(saved/'STATES.json');mapping=list(csv.DictReader((DOC/'AIDC12_STA12_PCC_MAPPING.csv').open(encoding='utf-8')))
    from .correction_svr import graph,path_to
    parents,meta=graph(e);output=[];toprows=[];location=[]
    for slot in (31,74):
        t=slot+24;state=states[t];e.apply('ACTUAL',t,2.)
        base,a,_,_=e.measure('ACTUAL',t,2.,state=state,fixed=True,accounting=False)
        with np.load(saved/'AC_FULL.npz') as z:
            ix=np.flatnonzero(z['event_slot']==t)[-1]
            assert np.max(abs(a['line_rho']-z['line_rho'][ix]))<1e-8
        demands=dict(e.base_pcc);indices=np.flatnonzero(e.canonical);maxima={}
        for j in indices:
            el=e.line_axes[j]['element']
            if a['line_rho'][j]>maxima.get(el,(-1,-1))[0]:maxima[el]=(a['line_rho'][j],j)
        top=[j for _,j in sorted(maxima.values(),reverse=True)[:20]]
        for site in sorted(e.pccs):
            for direction,dp,dq in ([('P_PF095',-5.,-5.*np.tan(np.arccos(.95)))] if site.startswith('AIDC') else [('P',-5.,0.),('Q',0.,-5.)]):
                for s,(p,q) in demands.items():
                    e.d.Loads.Name(e.pccs[s]['element'].split('.',1)[1]);e.d.Loads.kW(p+(dp if s==site else 0));e.d.Loads.kvar(q+(dq if s==site else 0))
                point,b,_,_=e.measure('ACTUAL',t,2.,state=state,fixed=True,accounting=False)
                output.append(dict(site=site,eval_slot=slot,direction=direction,delta_P_kw=dp,delta_Q_kvar=dq,
                    base_slot_rho=base['rho_global'],perturbed_slot_rho=point['rho_global'],delta_loading_pp=100*(base['rho_global']-point['rho_global']),
                    base_binding=base['binding_line'],new_binding=point['binding_line'],phase=point['binding_physical_phase'],
                    snapshot_security_PASS=point['physics_PASS'],scope='FIXED_NATIVE_STATE_LOCAL_ONLY_NOT_JOB_OR_ROUTE_WITNESS'))
                for rank,j in enumerate(top):toprows.append(dict(site=site,eval_slot=slot,direction=direction,rank=rank+1,
                    line=e.line_axes[j]['element'],phase=e.line_axes[j]['physical_phase'],response_pp=100*float(a['line_rho'][j]-b['line_rho'][j])))
    for r in mapping:
        site=r['location_id'];bus=r['candidate_bus'].lower();e.d.Circuit.SetActiveBus(bus)
        path=path_to(bus,parents);r=dict(r);r.update(phases=json.dumps(e.d.Bus.Nodes()),MV_kV_LL=float(e.d.Bus.kVBase()*np.sqrt(3)),
            electrical_path=json.dumps(path,ensure_ascii=False),direct_AIDC_PCC_nameplate='IDEAL_MV_LOAD_NO_SEPARATE_HARDWARE_RATING' if site.startswith('AIDC') else '',
            GPU_capacity='',
            field_GIS_certified=False,roads_access_certified=False,initial_MESS=next((u for u,s in INITIAL.items() if s==site),''))
        for slot in (31,74):
            for x in [x for x in output if x['site']==site and x['eval_slot']==slot]:r[f"slot{slot}_{x['direction']}_delta_pp_per5"]=x['delta_loading_pp']
        location.append(r)
    # Direction invariants of all24 service IDs in the common proper transform.
    pairs=[]
    for i,a in enumerate(mapping):
        for b in mapping[i+1:]:
            errors=[]
            for axis in ('x','y'):
                expected=float(b[f'traffic_{axis}_km'])-float(a[f'traffic_{axis}_km'])
                observed=float(b[f'common_frame_{axis}_km'])-float(a[f'common_frame_{axis}_km'])
                if abs(expected)>.001:errors.append(np.sign(expected)!=np.sign(observed))
            pairs.append(dict(a=a['location_id'],b=b['location_id'],direction_PASS=not any(errors)))
    native=read(read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]['files']['native']['path'])
    for r in location:
        if r['role']=='AIDC':r['GPU_capacity']=native['capacities'][r['location_id']]
        else:r.update(secondary_V_LL=480,transformer_kVA=750,port_kVA=600,port_current_A=600/(np.sqrt(3)*.48),vehicle_P300_Q250_PCS400=True,occupancy_limit=1)
    table('AIDC12_PCC_LOCATION_AUDIT.csv',[r for r in location if r['role']=='AIDC'])
    table('STA12_LOCATION_AND_ELECTRICAL_RESPONSE.csv',[r for r in location if r['role']!='AIDC'])
    table('LOCATION_DIRECTION_PAIRS.csv',pairs);table('TWO_PEAK_LOCAL_PCC_SENSITIVITY.csv',output);table('TWO_PEAK_TOP20_PCC_RESPONSE.csv',toprows)
    put('LOCATION_AUDIT_SUMMARY.json',dict(all24_direction_pairs=len(pairs),direction_failures=sum(not p['direction_PASS'] for p in pairs),
        layout_error_km_min=min(float(r['geometry_error_layout_equivalent_km']) for r in mapping),layout_error_km_max=max(float(r['geometry_error_layout_equivalent_km']) for r in mapping),
        field_layout='UNVERIFIED_DIAGRAM_COORDINATES_NOT_GIS',C2_relocated=False,initial8_reselected=False,
        local_snapshots_reproduced_saved_TIME=True,local_AC_perturbations=len(output),MOVE_value='Destination response differences must be reduced by route unavailability/travel energy; no optimized MOVE benefit certified'))

def two_peak(register_only=False):
    from . import correction as c,correction_svr_run as runner
    from .correction_svr_implicit import source_svr
    from .correction_projection import project
    schedules=[dict(name='PRESTART_SPLIT_50_50_P',splits=[.5,.5],Q_support=0),
               dict(name='PRESTART_SPLIT_50_50_Q50',splits=[.5,.5],Q_support=50)]
    prereg=dict(configuration='S1_03',beta=2.,schedules=schedules,energy_per_unit_kWh=320,charge_slots=list(range(8,16)),
        discharge_windows=[list(range(27,35)),list(range(68,76))],initial8=INITIAL,selection='Finite development diagnostic preregistered before its AC; no final scenario or algorithm authority',
        mode='STAY_witness_only_optimizer_MOVE_domain_must_remain_free',Native_optimizer_calls=0)
    path=OUT/'TWO_PEAK_PREREGISTRATION.json'
    if path.exists():assert read(path)==prereg
    else:put(path.name,prereg)
    if register_only:return
    resources();runner.source_svr=source_svr;runner.RUN=RUN/'two_peak';runner.RUN.mkdir(exist_ok=True);runner.install('S1_03')
    def trajectory(s):
        p=np.zeros((96,8));q=p.copy();soc=np.full((97,8),760.)
        p[8:16]=320/.95/2
        for fraction,begin in zip(s['splits'],(27,68)):
            p[begin:begin+8]=-320*.95*fraction/2
            q[begin:begin+8]=-s['Q_support']
        for t in range(96):soc[t+1]=soc[t]+.25*(.95*np.maximum(p[t],0)-np.maximum(-p[t],0)/.95)
        assert soc.min()>=440 and soc.max()<=1080+1e-8 and np.max(abs(soc[-1]-760))<1e-8
        for a in np.arange(16)*2*np.pi/16:assert np.max(np.cos(a)*p+np.sin(a)*q)<=400*np.cos(np.pi/16)+1e-8
        return p,q,soc
    c.trajectory=trajectory;original=c.fingerprint
    c.fingerprint=lambda:dict(original(),prestart_code=record(Path(__file__)),preregistration=record(path))
    base,base_slots,_,_=project(RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03/RECEIPT.json')
    results=[];units=[];checks=[];slotsout=[]
    for schedule in schedules:
        _,r=c.run_case(2.,'ACTUAL',schedule=schedule);_,fr=c.run_case(2.,'ACTUAL',schedule=schedule,fresh=True)
        check=c.fresh_check(r,fr);assert check['PASS'];checks.append(check)
        s,slots,_,_=project(Path(r['archive_path']).parent/'RECEIPT.json');p,q,soc=trajectory(schedule)
        s.update(schedule=schedule['name'],baseline_rho=base['rho_objective'],improvement_pp=100*(base['rho_objective']-s['rho_objective']),
            certified_B3_result=False,optimizer_calls=0,initial_final_SOC=760,charge_kWh=float(np.maximum(p,0).sum()*.25),discharge_kWh=float(np.maximum(-p,0).sum()*.25))
        results.append(s)
        for slot in slots[24:]:slotsout.append(dict(schedule=schedule['name'],**slot))
        for u,(vehicle,site) in enumerate(INITIAL.items()):
            for t in range(96):units.append(dict(schedule=schedule['name'],vehicle=vehicle,site=site,slot=t,P_demand_kw=float(p[t,u]),Q_demand_kvar=float(q[t,u]),SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),route='ORIGINAL_STAY',travel_energy_kWh=0))
        table('TWO_PEAK_CONTROLLABILITY_ANALYSIS.csv',results);table('TWO_PEAK_SLOT_RESULTS.csv',slotsout);table('TWO_PEAK_UNIT_TRAJECTORIES.csv',units)
        put('TWO_PEAK_FRESH_CHECKS.json',checks)

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
