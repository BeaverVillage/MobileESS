"""Finite seven-day B0 preparation only: original daily sources, no optimizer."""
import math,time,json,copy
from datetime import datetime,timedelta,timezone
import numpy as np
from .full_common import *
from .full_physical import engine
from .full_jobs import prepare,baseline,conservation,save

AEST=timezone(timedelta(hours=10))
DAYROOT=RUN/'daily_r0'

def planning_inputs(day):
    from v43_arms.reference import project
    from .aidc_candidate import actual_c1
    native=read(day['files']['native']['path']);sites,caps,known,anon,selected,x,carry,cons=project(native)
    pp,pq,it=actual_c1(known+anon,sites,day,role='PLANNING')
    a=dict(PLANNING_AIDC_P_kw=pp,PLANNING_AIDC_Q_kvar=pq,PLANNING_AIDC_site=np.array(sites))
    b=background_totals(day,'PLANNING')
    for k in ('P','Q'):a['PLANNING_BG_'+k]=b[k]
    a['PLANNING_PV_P_kw']=b['PV'][:,None];a['PLANNING_PV_Q_kvar']=np.zeros_like(b['PV'][:,None])
    return a,dict(source_project=record(ROOT/'v43_arms/reference.py'),conservation=cons,selected_jobs=len(selected),
        rule='EXACT_PR189_R0_Q50',C1='Original daily Planning affine C1',old_electrical_anchor_reused=False)

def background_totals(day,role,observations=None):
    from v42_regcontrol.runner import background
    if role=='PLANNING':
        f=read(day['files']['planning_input']['path'])['forecast_inputs']['AEMO']
        b=background(f['timestamps_96'],f['demand_mw_96'],f['pv_mw_96'])
        pages=[(b,96)]
    else:
        obs=[observations.at(day['axis']['issue_seconds']+900*t,observed_now=day['axis']['issue_seconds']+900*t) for t in range(120)]
        pages=[]
        for first in (0,96):
            page=obs[first:first+96];padded=page+[page[-1]]*(96-len(page))
            stamps=[datetime.fromtimestamp(day['axis']['issue_seconds']+(first+t+1)*900,AEST).isoformat() for t in range(96)]
            b=background(stamps,[r['demand']['values']['demand_mw'] for r in padded],[r['pv']['values']['pv_mw'] for r in padded]);pages.append((b,len(page)))
    totals={k:[] for k in ('P','Q','PV')}
    for b,n in pages:
        for t in range(n):
            totals['P'].append(math.fsum(b.gross_p_kw_96[t].values()))
            totals['Q'].append(math.fsum(b.gross_q_kvar_96[t].values()))
            totals['PV'].append(math.fsum(b.pv_generation_kw_96[t].values()))
    return {k:np.asarray(v) for k,v in totals.items()}

def inputs(day):
    folder=DAYROOT/day['day'];folder.mkdir(parents=True,exist_ok=True)
    plan,planning_receipt=planning_inputs(day)
    args=prepare(day,'DAY_'+day['day'])
    if day['day']=='2025-05-01':
        led=read(RUN/'jobs/BASE/EVENTS.json');z=np.load(RUN/'jobs/BASE/PHYSICAL.npz');led.update(occupancy_GPU=z['GPU'],compute_occupancy_GPU=z['compute_GPU'])
    else:
        led=baseline(copy.deepcopy(args),day)
    jobcert,jobrows=conservation(led,args);table('DAY_'+day['day']+'_JOB_WORK.csv',jobrows)
    jobrec=save('DAY_'+day['day'],led)
    from .full_weather import actual_power,observations
    obs=observations(day,args['begin'],args['end'])
    p,q,it=actual_power(led['occupancy_GPU'],led['sites'],day)
    a=dict(plan,ACTUAL_AIDC_P_kw=p,ACTUAL_AIDC_Q_kvar=q,ACTUAL_AIDC_site=np.array(led['sites']))
    for role in ('PLANNING','ACTUAL'):
        b=background_totals(day,role,obs)
        for k in ('P','Q'):a[role+'_BG_'+k]=b[k]
        a[role+'_PV_P_kw']=b['PV'][:,None];a[role+'_PV_Q_kvar']=np.zeros_like(b['PV'][:,None])
    if day['day']=='2025-05-01':
        frozen=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz');errors={}
        for role in ('PLANNING','ACTUAL'):
            for k,u in [('P','kw'),('Q','kvar')]:errors[role+'_BG_'+k]=float(np.max(abs(a[role+'_BG_'+k]-np.sum(frozen[role+'_BG_'+k+'_'+u],axis=1))))
            errors[role+'_PV']=float(np.max(abs(a[role+'_PV_P_kw'][:,0]-np.sum(frozen[role+'_PV_P_kw'],axis=1))))
            for k,u in [('P','kw'),('Q','kvar')]:errors[role+'_AIDC_'+k]=float(np.max(abs(a[role+'_AIDC_'+k+'_'+u]-frozen[role+'_AIDC_'+k+'_'+u])))
        put('DAILY_R0_SOURCE_PRODUCER_MAY01_EQUIVALENCE.json',dict(PASS=max(errors.values())<1e-7,errors=errors,
            prior_electrical_anchor_max_error_kw=54.772397570525,prior_attempt_preserved=True))
        if max(errors.values())>=1e-7:raise ValueError('DAILY_SOURCE_PRODUCER_MAY01_MISMATCH')
    path=folder/'INPUTS.npz';np.savez_compressed(path,**a)
    receipt=dict(day=day['day'],inputs=record(path),source=SOURCE,files=day['files'],observations=obs.sources,
        B0_job_receipt=led['receipt'],independent_job_work=jobcert,job_artifacts=jobrec,planning_reference=planning_receipt,
        beta_BG=2.,SVR_actual=3,SVR_planning=0,MESS=8,GPU=780,initial_MESS=INITIAL,
        hardware=record(OUT/'IDC_ORIGINAL_PHYSICAL_CONTRACT.json'),alpha_BG_original_1_15_applied_once=True,
        route_traffic_changed=False,actual_initial_Tap_Cap='Frozen source; causal prior operating state NOT certified',
        weather_valid_observation_receipt=record(OUT/('WEATHER_VALID_OBSERVATIONS_'+day['day']+'.json')))
    (folder/'INPUT_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return a,receipt

def run(day,role,a,*,fresh=False):
    DAYROOT.mkdir(exist_ok=True)
    tag=day['day']+'_'+role+('_FRESH' if fresh else '');folder=DAYROOT/tag;folder.mkdir(exist_ok=True)
    if (folder/'RECEIPT.json').exists():return read(folder/'RECEIPT.json')
    e=engine(tag,role);e.inputs=a;e.sites=list(map(str,a['PLANNING_AIDC_site']))
    from .correction_time100 import clock_class
    Clock,e.queue=clock_class();e.clock=Clock('ACTUAL' if role=='ACTUAL' else 'DAYAHEAD',day['day']);e.clock.bind(e.d)
    e.bg={}
    for quantity,index in [('P',0),('Q',1)]:
        w=np.array([r['kw' if index==0 else 'kvar'] for r in e.loads]);w/=math.fsum(w)
        alloc=a[role+'_BG_'+quantity][:,None]*w
        j=int(w.argmax())
        for t in range(len(alloc)):alloc[t,j]+=a[role+'_BG_'+quantity][t]-math.fsum(alloc[t])
        e.bg[role+'_'+quantity]=alloc
    rows=[];events=[];states=[];slots=[];clock=[];data={k:[] for k in ('line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho')}
    start=time.perf_counter()
    for t in range(120 if role=='ACTUAL' else 96):
        guard(start);e.apply(role,t,2.);r,_,st,ports=e.measure(role,t,2.)
        rows.append(r);states.append(st);events.extend(e.event_rows);clock.append(e.last_events)
        for arr in e.event_arrays:
            for k in data:data[k].append(arr[k])
        slots.extend([t]*len(e.event_arrays))
        if t%40==0:print('DAILY TIME',tag,t,flush=True)
    e.check_parameters()
    np.savez_compressed(folder/'AC.npz',**{k:np.asarray(v) for k,v in data.items()},event_slot=np.array(slots))
    for name,value in [('ROWS',rows),('EVENTS',events),('STATES',states),('CLOCK',clock),('TRACE',e.trace)]:
        (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    offset=24 if role=='ACTUAL' else 0;settled=[]
    for t in range(offset,len(rows)):
        ii=max(i for i,slot in enumerate(slots) if slot==t);settled.append(ii)
    line=np.asarray(data['line_rho']);v=np.asarray(data['node_voltage_pu']);ev=np.asarray(slots)>=offset
    rho=float(line[settled][:,e.canonical].max());mv=float(line[settled][:,e.cmv].max());lv=float(line[settled][:,e.clv].max())
    duration={'low':0.,'high':0.};witness=[]
    # Each solved native state is held until the next physical queue event,
    # including the slot boundary. Numerical iteration indices are not time.
    for t,c in enumerate(clock):
        local=[r for r in events if r['slot']==t]
        for j,r in enumerate(local):
            until=local[j+1]['physical_seconds'] if j+1<len(local) else c['end_seconds']
            for kind,bad in [('low',r['Vmin']<.95-1e-8),('high',r['Vmax']>1.05+1e-8)]:
                if bad:duration[kind]+=max(0.,until-r['physical_seconds']);witness.append(dict(slot=t,kind=kind,seconds=r['physical_seconds'],until=until,Vmin=r['Vmin'],Vmax=r['Vmax']))
    table('TIME_VIOLATIONS_'+tag+'.csv',witness or [dict(slot='',kind='NONE',seconds=0,until=0,Vmin=float(v.min()),Vmax=float(v.max()))])
    receipt=dict(day=day['day'],role=role,fresh=fresh,full_TIME_PASS=all(r['physics_PASS'] for r in rows),
        evaluated_TIME_PASS=all(r['physics_PASS'] for r in rows[offset:]),rho_global=rho,rho_MV=mv,rho_LV=lv,MV_minus_LV=mv-lv,
        event_Vmin=float(v.min()),event_Vmax=float(v.max()),evaluation_event_Vmin=float(v[ev].min()),evaluation_event_Vmax=float(v[ev].max()),
        voltage_violation_seconds=duration,finite_AC_slots=len(rows),native_solves=len(events),original_lines=3703,Triplex=1177,
        original_parameters_PASS=True,initial_state=e.initial_state,Native_calls=0,wall_seconds=time.perf_counter()-start,
        files={p.name:record(p) for p in folder.iterdir() if p.is_file()})
    (folder/'RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DAILY DONE',tag,receipt['full_TIME_PASS'],rho,flush=True);return receipt

def main():
    init();resources();DAYROOT.mkdir(exist_ok=True);import psutil;psutil.Process().cpu_affinity([13]);reports=[]
    for day in read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days']:
        try:
            p=DAYROOT/day['day'];p.mkdir(parents=True,exist_ok=True)
            if (p/'INPUT_RECEIPT.json').exists():
                receipt=read(p/'INPUT_RECEIPT.json');z=np.load(p/'INPUTS.npz');a={k:z[k] for k in z.files}
            else:a,receipt=inputs(day)
            planning=run(day,'PLANNING',a);actual=run(day,'ACTUAL',a);fresh=run(day,'ACTUAL',a,fresh=True)
            aa=np.load(DAYROOT/(day['day']+'_ACTUAL')/'AC.npz');ff=np.load(DAYROOT/(day['day']+'_ACTUAL_FRESH')/'AC.npz')
            errors={k:float(np.max(abs(aa[k]-ff[k]))) for k in aa.files};eq=max(errors.values())<1e-9
            reports.append(dict(day=day['day'],input_receipt=receipt,planning=planning,actual=actual,fresh=fresh,independent_Fresh=eq,Fresh_max_errors=errors,
                scientific_PASS=planning['full_TIME_PASS'] and actual['full_TIME_PASS'] and fresh['full_TIME_PASS'] and eq and receipt['independent_job_work']['PASS']))
        except Exception as exc:
            import traceback
            diagnostic=dict(day=day['day'],scientific_PASS=False,error=repr(exc),traceback=traceback.format_exc())
            # A failed Actual source does not discard independently available
            # Planning96 inputs or manufacture an Actual pass.
            try:
                pa,pr=planning_inputs(day);diagnostic['planning']=run(day,'PLANNING',pa);diagnostic['planning_source']=pr
            except Exception as pe:diagnostic['planning_error']=repr(pe)
            reports.append(diagnostic)
            print('DAILY BLOCKED',day['day'],repr(exc),flush=True)
        put('MAY01_07_FULL_READINESS.json',dict(days=reports,same_candidate_all_days=True,official_campaign_started=False,
            all_dates_scientific_PASS=len(reports)==7 and all(r['scientific_PASS'] for r in reports),
            field_installation_status='FIELD_INSTALLATION_UNVERIFIED',beta_PCC_SVR_tuned_by_day=False))

if __name__=='__main__':main()
