"""Source-equivalent IDC winding candidate, separate from the sealed DY case."""
import types,csv
import numpy as np
from .may01_common import *
from .may01_voltage import engine,transformer

def run():
    init();import psutil;psutil.Process().cpu_affinity([13])
    prereg=OUT/'SOURCE_YY_PORT_PREREGISTRATION.json'
    if not prereg.exists():
        source=read(OUT/'ALL24_PORT_ELECTRICAL_READBACK.json')['original_V44_IDC_transformer']
        put(prereg.name,dict(candidate='H0_SOURCE_YY',SVR_banks=3,Source_P5_unchanged=True,
            IDC_connection='Original V44 Wye/Wye',LV_LL_kV=.48,MV_LL_kV=12.47,
            nameplate_kVA=750,normal_emergency_limit_kVA=750,port_kVA=600,
            original_source_default_normal_emergency_kVA=[825,1125],
            tightened_new_port_normal_limits_preserved_from_DY_design=True,
            R_pct_each=[.8,.2],XHL_pct=5.75,Rneut_each=[-1,-1],tap_each=[1,1],
            no_load_loss_pct=0,imag_pct=0,original_winding_readback=source,
            reason='Test exact original V44 IDC winding parameters at IEEE8500 MV voltage; no fitted impedance or tap',
            frozen_before_sourceYY_operating_AC=True,schedules=['ZERO','P_ONLY','Q50','TWO_MOVE'],
            original_DY_reference_and_all_H0_H4_results_preserved=True,
            no_selection_without_Planning_Prefix_Actual_and_grid_rebinding=True))
    from . import full_days
    from .may01_witness import pilots
    from .may01_pq import validator
    q=pilots();p=[dict(r,Q_demand_kvar=0.) for r in q]
    move=list(csv.DictReader((OUT/'FINITE_TWO_MOVE_UNIT_TRAJECTORY.csv').open(encoding='utf-8')))
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    with np.load(PRIOR/'daily_r0/2025-05-01/INPUTS.npz') as z:a={k:z[k] for k in z.files}
    results=[]
    for label,rows in [('ZERO',[]),('P_ONLY',p),('Q50',q),('TWO_MOVE',move)]:
        loads={}
        for r in rows:
            s=r.get('site',INITIAL[r['vehicle']]);t=int(r['slot'])
            if s=='TRANSIT':continue
            old=loads.get((s,t),(0.,0.));loads[s,t]=(old[0]+float(r['P_demand_kw']),old[1]+float(r['Q_demand_kvar']))
        folder=RUN/'source_yy'/label;folder.mkdir(parents=True,exist_ok=True)
        def selected(tag,role):
            e=engine('SOURCE_YY_'+label+'_'+tag,role,'H0_SOURCE_YY');apply=e.apply
            if not (OUT/'SOURCE_YY_ALL24_HARDWARE_READBACK.json').exists():
                ports=[]
                for item in e.port_meta:
                    s=item['site'];name='full_mobile_'+s.lower() if s.startswith('IDC') else 'high_mv_'+s.lower()
                    ports.append(dict(site=s,transformer=transformer(e.d,name),port=item))
                put('SOURCE_YY_ALL24_HARDWARE_READBACK.json',dict(ports=ports,source_readback=record(OUT/'ALL24_PORT_ELECTRICAL_READBACK.json'),field_status='FIELD_INSTALLATION_UNVERIFIED'))
            def scheduled(role,t,beta,mess=None,aidc_delta=None):
                return apply(role,t,beta,{s:pq for (s,k),pq in loads.items() if k==t-24} if t>=24 else {},aidc_delta)
            e.apply=scheduled;return e
        fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,
            engine=selected,table=lambda n,r:table('SOURCE_YY_'+label+'_'+n,r)),argdefs=full_days.run.__defaults__)
        fn.__kwdefaults__=full_days.run.__kwdefaults__
        planning=fn(day,'PLANNING',a) if label=='ZERO' else None
        actual=fn(day,'ACTUAL',a);fresh=fn(day,'ACTUAL',a,fresh=True)
        with np.load(actual['files']['AC.npz']['path']) as aa,np.load(fresh['files']['AC.npz']['path']) as ff:
            errors={k:float(np.max(abs(aa[k]-ff[k]))) if aa[k].shape==ff[k].shape else None for k in aa.files}
        same=all(v is not None and v<1e-9 for v in errors.values())
        results.append(dict(schedule=label,planning=planning,actual=actual,fresh=fresh,independent_Fresh_PASS=same,Fresh_errors=errors,
            source_vehicle_validator=validator(rows) if rows and label!='TWO_MOVE' else read(OUT/'FINITE_TWO_MOVE_SOURCE_VALIDATOR.json')['validator'] if label=='TWO_MOVE' else dict(PASS=True),
            full_TIME_PASS=actual['full_TIME_PASS'] and fresh['full_TIME_PASS'] and same,
            evaluated_TIME_PASS=actual['evaluated_TIME_PASS'] and fresh['evaluated_TIME_PASS'] and same))
        put('SOURCE_YY_PORT_TIME_COMPARISON.json',dict(candidate='H0_SOURCE_YY',cases=results,complete=len(results)==4,
            source_winding_parameters_reused=True,Primary_selected=False,Planning_TIME_safe=False,
            sealed_DY_grid_coefficients_applicable_to_YY=False,additional_SVR_banks=0,Native_calls=0))
    print('SOURCE YY COMPLETE',len(results),flush=True)

def port_envelope():
    init();import psutil,copy
    psutil.Process().cpu_affinity([13]);start=__import__('time').perf_counter()
    e=engine('SOURCE_YY_PORT_ENVELOPE','ACTUAL','H0_SOURCE_YY');e.mode='STATIC'
    frames=read(RUN/'source_yy/ZERO/2025-05-01_ACTUAL/TRACE.json')
    frame=next(f for f in frames if f['physical_seconds']==44134.)
    state=copy.deepcopy(e.initial_state)
    for c in frame['controls']:state['taps'][c['transformer']][c['winding']-1]=c['tap']
    state['capacitors']=frame['capacitors'];rows=[]
    for s in sorted(e.pccs):
        if s.startswith('AIDC'):continue
        for p,q in [(0,0),(-300,-250),(-300,0),(-300,250),(0,-250),(0,250),(300,-250),(300,0),(300,250),(-150,-125),(-150,125),(150,-125),(150,125)]:
            guard(start);e.apply('ACTUAL',49,2.,mess={s:(p,q)})
            r,a,_,ports=e.measure('ACTUAL',49,2.,state=state,fixed=True)
            e.d.Circuit.SetActiveBus(e.pccs[s]['bus']);v=np.asarray(e.d.Bus.puVmagAngle())[::2][:3]
            port=next(x for x in ports if x['site']==s)
            rows.append(dict(hardware='H0_SOURCE_YY',site=s,P_injection_kw=-p,Q_injection_kvar=-q,
                local_Vmin=float(v.min()),local_Vmax=float(v.max()),whole_Vmin=r['Vmin'],whole_Vmax=r['Vmax'],
                local_voltage_PASS=bool(v.min()>=.95-1e-8 and v.max()<=1.05+1e-8),
                current_loading=port['current_loading'],kVA_loading=port['interface_loading'],
                thermal_PASS=port['current_loading']<=1 and port['interface_loading']<=1,
                converged=r['converged'],instantaneous_only=True,whole_day_SOC_certified=False))
    table('SOURCE_YY_ALL24_INSTANTANEOUS_PQ_SECURITY.csv',rows)
    put('SOURCE_YY_ALL24_PORT_ENVELOPE.json',dict(ports=24,cases=len(rows),
        all_port_thermal_PASS=all(x['thermal_PASS'] for x in rows),
        all_local_voltage_PASS=all(x['local_voltage_PASS'] for x in rows),
        voltage_failing_cases=sum(not x['local_voltage_PASS'] for x in rows),
        arbitrary_PQ_box_daily_certified=False,actual120_schedule_certificate='Separate finite schedule TIME/Fresh only',
        optimizer_must_obey_voltage_domain_and_independent_Fresh=True))
    print('SOURCE YY PORT ENVELOPE',len(rows),flush=True)

if __name__=='__main__':
    import sys
    port_envelope() if len(sys.argv)>1 and sys.argv[1]=='ports' else run()
