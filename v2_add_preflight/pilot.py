"""G3 electrical probes and limited 96-slot feasible witnesses; no optimizer."""
import json
import gzip
import math
import time
import numpy as np
import psutil
from .audit import DOC,read,save,table,sha
from .physical import Physical,RUNTIME
from .aidc_candidate import prepare


def b0_case(beta,role):
    rows=read(DOC/'B0_AC_ARCHIVE_RECEIPTS.json')
    return next(r for r in rows if r['beta_BG']==beta and r['role']==role and not r['case'].endswith('_FRESH'))


def small_probes():
    import csv
    names=['AIDC_MESS_SENSITIVITY.csv','NO_CONTROL_AC_NOISE.csv','STA_P300_Q250_AC_ENDPOINTS.csv']
    if all((DOC/n).exists() for n in names):
        lengths=[sum(1 for _ in csv.DictReader((DOC/n).open(encoding='utf-8'))) for n in names]
        if lengths==[576,4,104]:
            print('REUSE completed electrical/noise/endpoint probes',flush=True)
            return
    output=[];noise=[];endpoints=[]
    initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
    from pathlib import Path
    from .audit import ROOT
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    rt=json.loads(gzip.decompress(Path(day['files']['route_table']['path']).read_bytes()))
    stay=[r for r in rt['routes'] if r['origin_service_id']==r['destination_service_id'] and r['origin_service_id'] in initial.values()]
    assert len(stay)==8*96 and all(r['travel_slots_15min']==0 and r['connection_ready_slots_15min']==0 and r['energy_safe_kwh']==0 for r in stay)
    save('MESS8_SOURCE_STAY_ROUTE_AUDIT.json',dict(PASS=True,source_route_table=day['files']['route_table'],
        stay_rows_checked=len(stay),original_initial_sites=initial,ETA_slots=0,energy_safe_kwh=0,
        route_or_energy_regeneration=False,scope='stationary diagnostic only; future optimizer free to MOVE'))
    for beta in (1.,1.5):
        for role in ('PLANNING','ACTUAL'):
            receipt=b0_case(beta,role);base_rows=read(receipt['rows_path'])
            offset=24 if role=='ACTUAL' else 0
            t=max(range(offset,len(base_rows)),key=lambda t:base_rows[t]['rho_global'])
            state=read(receipt['states_path'])[t]
            e=Physical(f'G3_probe_{beta}_{role}');e.apply(role,t,beta)
            base,_,_,_=e.measure(role,t,beta,state=state)
            repeat,_,_,_=e.measure(role,t,beta,state=state)
            noise.append(dict(beta_BG=beta,role=role,slot=t-offset,
                global_repeat_noise_pp=100*(repeat['rho_global']-base['rho_global']),
                archived_reproduction_noise_pp=100*(base['rho_global']-base_rows[t]['rho_global'])))
            demands=dict(e.base_pcc)
            def point(changes,fixed=False):
                for site,(p,q) in demands.items():
                    dp,dq=changes.get(site,(0.,0.));e.d.Loads.Name(e.pccs[site]['element'].split('.',1)[1]);e.d.Loads.kW(p+dp);e.d.Loads.kvar(q+dq)
                return e.measure(role,t,beta,state=state,fixed=fixed,accounting=False)[0]
            for site in sorted(e.pccs):
                directions=[('P_PF095',5.,5.*math.tan(math.acos(.95)))] if site.startswith('AIDC') else [('P',5.,0.),('Q',0.,5.)]
                for kind,dp,dq in directions:
                    for sign in (-1,1):
                        for fixed in (True,False):
                            row=point({site:(sign*dp,sign*dq)},fixed)
                            output.append(dict(beta_BG=beta,role=role,slot=t-offset,site=site,
                                perturbation=kind,delta_demand_P_kw=sign*dp,delta_demand_Q_kvar=sign*dq,
                                controls='FIXED_BASE' if fixed else 'NATIVE_AUTO',
                                baseline_rho=base['rho_global'],controlled_rho=row['rho_global'],
                                delta_global_pp=100*(base['rho_global']-row['rho_global']),
                                new_binding=row['binding_line'],new_phase=row['binding_physical_phase'],
                                Vmin=row['Vmin'],Vmax=row['Vmax'],
                                status='ELECTRICAL_PERTURBATION_NOT_JOB_OR_SOC_FEASIBILITY'))
            if beta==1.5:
                for site in sorted(s for s in e.pccs if s.startswith('STA')):
                    for p in (-300.,300.):
                        for q in (-250.,250.):
                            row=point({site:(p,q)})
                            endpoints.append(dict(role=role,beta_BG=beta,site=site,P_kw=p,Q_kvar=q,
                                global_rho=row['rho_global'],Vmin=row['Vmin'],Vmax=row['Vmax'],
                                transformer_max=row['transformer_nameplate_max'],port_current_max=row['port_current_max'],
                                physics_PASS=row['physics_PASS'],scope='INSTANTANEOUS_SINGLE_VEHICLE_NO_SOC_CLAIM'))
                for p in (-300.,300.):
                    for q in (-250.,250.):
                        row=point({site:(p,q) for site in initial.values()})
                        endpoints.append(dict(role=role,beta_BG=beta,site='ALL8_INITIAL_STA',P_kw=p,Q_kvar=q,
                            global_rho=row['rho_global'],Vmin=row['Vmin'],Vmax=row['Vmax'],
                            transformer_max=row['transformer_nameplate_max'],port_current_max=row['port_current_max'],
                            physics_PASS=row['physics_PASS'],scope='INSTANTANEOUS_8_VEHICLES_NO_SOC_CLAIM'))
            print('G3 probes',beta,role,'complete',flush=True)
    table('AIDC_MESS_SENSITIVITY.csv',list(output[0]),output)
    table('NO_CONTROL_AC_NOISE.csv',list(noise[0]),noise)
    table('STA_P300_Q250_AC_ENDPOINTS.csv',list(endpoints[0]),endpoints)


def schedule(amplitude):
    # Same fixed diagnostic time bands as the historical C2 witness, battery
    # headroom recalculated for the unchanged V44 440/760/1080 kWh vehicle.
    p=np.zeros(96);p[8:16]=amplitude*(1080-760)/(.95*2)
    p[68:76]=-amplitude*(1080-760)*.95/2
    energy=np.zeros(97);energy[0]=760
    for t,x in enumerate(p):energy[t+1]=energy[t]+.25*(.95*x if x>=0 else x/.95)
    assert abs(energy[-1]-760)<1e-8 and min(energy)>=440-1e-8 and max(energy)<=1080+1e-8
    assert np.max(abs(p))<=300 and np.all(abs(p)<=400*math.cos(math.pi/16)+1e-8)
    return p,energy


def pilot_case(role,kind,amplitude,aidc,fresh=False):
    beta=1.5;tag=f'G3_beta1.50_{role}_{kind}_{amplitude:.2f}'
    source=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')
    if kind!='MESS_ONLY' and np.max(abs(aidc[role+'_P']-source[role+'_AIDC_P_kw']))>1e-8:
        tag+='_A'+sha(aidc[role+'_P'].tobytes()+aidc[role+'_Q'].tobytes())[:10]
    if fresh:tag+='_FRESH'
    folder=RUNTIME/'phase2'/tag;folder.mkdir(exist_ok=True,parents=True)
    if (folder/'RECEIPT.json').exists():return read(folder/'ROWS.json'),read(folder/'RECEIPT.json')
    e=Physical(tag);initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
    count=96 if role=='PLANNING' else 120;offset=24 if role=='ACTUAL' else 0
    p,soc=schedule(amplitude);rows=[];states=[];line=[];volts=[];start=time.perf_counter()
    for t in range(count):
        eval_t=t-offset
        mess={s:(float(p[eval_t]),0.) for s in initial.values()} if kind!='AIDC_ONLY' and eval_t>=0 else None
        delta=None
        if kind!='MESS_ONLY':
            ap=aidc[role+'_P'][t];aq=aidc[role+'_Q'][t]
            delta={s:(float(ap[j]-e.inputs[role+'_AIDC_P_kw'][t,j]),float(aq[j]-e.inputs[role+'_AIDC_Q_kvar'][t,j])) for j,s in enumerate(e.sites)}
        e.apply(role,t,beta,mess,delta)
        row,a,state,_=e.measure(role,t,beta,state=e.initial_state if t==0 else None)
        row.update(control=kind,amplitude=amplitude,fleet_P_kw=8*float(p[eval_t]) if mess else 0.,
            per_vehicle_SOC_kwh=float(soc[eval_t]) if eval_t>=0 else 760.,
            AIDC_delta_total_kw=float(sum(v[0] for v in (delta or {}).values())))
        rows.append(row);states.append(state);line.append(a['line_rho']);volts.append(a['node_voltage_pu'])
    np.savez_compressed(folder/'AC_FULL.npz',line_rho=np.stack(line),node_voltage_pu=np.stack(volts))
    (folder/'ROWS.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (folder/'STATES.json').write_text(json.dumps(states,indent=2),encoding='utf-8')
    r=dict(role=role,kind=kind,amplitude=amplitude,fresh=fresh,case=tag,
        physics_PASS=all(r['physics_PASS'] for r in rows),
        rho=max(r['rho_global'] for r in rows[offset:]),elapsed_s=time.perf_counter()-start,
        rows_path=str(folder/'ROWS.json'),states_path=str(folder/'STATES.json'),archive_path=str(folder/'AC_FULL.npz'),
        archive_sha256=sha((folder/'AC_FULL.npz').read_bytes()),new_solver_calls=0)
    (folder/'RECEIPT.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    print('G3',tag,'rho',r['rho'],'PASS',r['physics_PASS'],flush=True)
    return rows,r


def main():
    assert read(DOC/'PREFLIGHT_GATES.json')['G2']['status']=='COMPLETE'
    proc=psutil.Process()
    try:
        proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        cores=[i for i in proc.cpu_affinity() if i>=12]
        if cores:proc.cpu_affinity(cores[:1])
    except (AttributeError,psutil.AccessDenied):pass
    save('G3_DIAGNOSTIC_SCOPE.json',dict(experiment_id='V2_add',
        electrical_probe_beta=[1.,1.5],electrical_probe_size_kw_kvar=5.,
        full96_pilot_beta=1.5,full96_beta_reason='preregistered upper endpoint, not a Primary Scenario; no beta reselection',
        amplitudes=[.25,.5,1.],charge_slots=list(range(8,16)),discharge_slots=list(range(68,76)),
        pilot_schedule='fixed original C2 witness time bands, V44 battery limits; no optimality claim',
        AIDC='source planning feasible schedule plus bounded same-site actual job delays, all original constraints checked',
        actual_legacy_QoS='independently checked; rejected if original intentional budgets exceeded',
        MESS_route='stationary witness at eight pre-fixed original STA IDs; no forced STAY/MOVE in future optimizer',
        source_route_table_regeneration=False,long_solver=False))
    aidc=prepare()
    job_audit=read(DOC/'AIDC_FEASIBLE_CANDIDATE_AUDIT.json')
    small_probes()
    output=[];pilotrows=[];receipts=[];freshchecks=[]
    initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
    for role in ('PLANNING','ACTUAL'):
        baseline=read(DOC/'B0_CASE_SUMMARIES.json')['1.50'][role]['rho']
        role_results=[]
        for kind in ('AIDC_ONLY','MESS_ONLY','JOINT'):
            amplitudes=[0.] if kind=='AIDC_ONLY' else [.25,.5,1.]
            for amplitude in amplitudes:
                rows,r=pilot_case(role,kind,amplitude,aidc)
                receipts.append(r);role_results.append((rows,r));pilotrows.extend(rows)
                output.append(dict(beta_BG=1.5,role=role,control=kind,amplitude=amplitude,
                    baseline_rho=baseline,controlled_rho=r['rho'],delta_global_pp=100*(baseline-r['rho']),
                    physics_PASS=r['physics_PASS'],scope=(
                        'REFERENCE_REPLAY_NO_NONZERO_ACTUAL_JOB_WITNESS' if role=='ACTUAL' and kind=='AIDC_ONLY' and not job_audit['actual_job_changes'] else
                        'MESS_PLUS_UNCHANGED_AIDC_NOT_NONZERO_JOINT_WITNESS' if role=='ACTUAL' and kind=='JOINT' and not job_audit['actual_job_changes'] else
                        'LIMITED_FEASIBLE_PILOT_NOT_B1_B2_B3')))
        for kind in ('AIDC_ONLY','MESS_ONLY','JOINT'):
            valid=[(rs,r) for rs,r in role_results if r['kind']==kind and r['physics_PASS']]
            if not valid:continue
            rows,best=min(valid,key=lambda x:x[1]['rho'])
            fr,rr=pilot_case(role,kind,best['amplitude'],aidc,True);receipts.append(rr)
            a=np.load(best['archive_path']);b=np.load(rr['archive_path'])
            differences={k:float(np.max(abs(a[k]-b[k]))) for k in a.files}
            states_equal=read(best['states_path'])==read(rr['states_path'])
            freshchecks.append(dict(role=role,kind=kind,amplitude=best['amplitude'],
                maximum_array_differences=differences,control_states_identical=states_equal,
                PASS=max(differences.values())<1e-9 and states_equal and rr['physics_PASS']))
            assert freshchecks[-1]['PASS'],'Pilot independent fresh failed'
    table('FEASIBLE_96SLOT_CONTROL_PILOT.csv',list(pilotrows[0]),pilotrows)
    table('CONTROL_PILOT_GLOBAL_COMPARISON.csv',list(output[0]),output)
    save('CONTROL_PILOT_ARCHIVE_RECEIPTS.json',receipts);save('CONTROL_PILOT_FRESH_CHECKS.json',freshchecks)
    units=[]
    for amp in (.25,.5,1.):
        p,soc=schedule(amp)
        for unit,site in initial.items():
            for t in range(96):
                units.append(dict(amplitude=amp,vehicle=unit,slot=t,STA=site,P_demand_kw=float(p[t]),Q_kvar=0,
                    SOC_start_kwh=float(soc[t]),SOC_end_kwh=float(soc[t+1]),
                    route='SOURCE_SAME_SITE_STAY',ETA_slots=0,travel_energy_kwh=0.,occupancy=1,
                    port_connection_at_slot0='diagnostic initial connection blocked before nonzero slot8',PCS16_PASS=True))
    table('MESS8_PILOT_UNIT_TRAJECTORIES.csv',list(units[0]),units)
    status='COMPLETE_LIMITED_WITNESSES' if job_audit['actual_job_changes'] else 'PARTIAL_MESS_PASS_ACTUAL_AIDC_NONZERO_NOT_VERIFIED'
    g=read(DOC/'PREFLIGHT_GATES.json');g['G3'].update(status=status,
        full96_beta=1.5,fresh_pairs=len(freshchecks),all_Fresh_PASS=all(r['PASS'] for r in freshchecks),
        planning_job_witness_count=len(job_audit['planning_job_changes']),actual_job_witness_count=len(job_audit['actual_job_changes']),
        no_optimality_claim=True);save('PREFLIGHT_GATES.json',g)
    print('G3 COMPLETE',flush=True)


if __name__=='__main__':main()
