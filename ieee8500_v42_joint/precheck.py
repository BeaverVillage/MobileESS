"""New selected 480V ports: bounded nonlinear AC endpoints, reused derivatives."""
import numpy as np
from pathlib import Path
import time
from .run_ac import *
from ieee8500_v42_high.engine import HighEngine
from ieee8500_v42_aemo.run_b0 import summary


def run():
    begin=time.perf_counter()
    if (REPORT/'precheck/RECEIPT.json').exists() or (REPORT/'AIDC_MESS_JOINT_PRECHECK.csv').exists():
        raise RuntimeError('COMPLETED_PRECHECK_MUST_BE_REUSED')
    configuration=read(REPORT/'SELECTED_RESEARCH_CONFIGURATION.json');mapping=Path(configuration['mapping']['path']);bg=configuration['bg']
    records=read(REPORT/'RUN_RECEIPT.json')['records']
    selected=next(r for r in records if r['source']=='PLANNING' and not r['controlled'])
    stage=REPORT/'ac'/selected['first']['tag'];axes=read(stage/'AC_AXES.json');base=dict(np.load(stage/'AC_96.npz'));states=read(stage/'CONTROL_STATES.json')
    data=dict(np.load(source_input('PLANNING','2025-05-01')));folder=REPORT/'precheck';folder.mkdir(exist_ok=True)
    groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    order=sorted(groups,key=lambda n:(-float(base['line_rho'][:,groups[n]].max()),n))
    targets=list(dict.fromkeys(order[:20]+[r['line'] for r in rows(REPORT/'CRITICAL_CORRIDOR_BASELINE.csv')]))
    slots=sorted(set([9,48,int(read(stage/'RECEIPT.json')['peak_slot'])]))
    prereg=dict(base=receipt(stage/'RECEIPT.json'),mapping=receipt(mapping),targets=targets,slots=slots,
        all_original_line_conductors_security_checked=True,duplicate_unit_PQ_derivatives=False,
        original_1783x7_derivatives='REUSED: FINAL_SEVEN_TIME_DERIVATIVES.npz; earlier baseline, selection heuristic only',
        scope_override=receipt(REPORT/'MAY01_EXECUTION_SCOPE_OVERRIDE.json'),
        STA_MV_corners='±450kW and ±300kvar, S600kVA/current721.688A/750kVATX may reject endpoint',
        STA_LV_corners='±5kW ±3kvar, S6kVA current27A, original CT/Triplex retained',
        AIDC_relaxation='same eligible-known source mask PF.95 only; QoS NOT_CERTIFIED; no extrapolated increase',
        simultaneous='six original initialSTA only; endpoints not SOC/route/96schedule performances',
        rejected_endpoint_policy='retain FAIL, never enlarge ratings or change P5 to pass',Native_calls=0)
    path=folder/'PREREGISTRATION.json'
    if path.exists():assert read(path)==prereg
    else:write(path,prereg)
    e=HighEngine('SELECTED_PRECHECK',bg,'M3',mapping,REPORT);sites=sorted(e.pccs);initial=list(read(HIGH/'SCHEDULE_PREREGISTRATION_CLARIFICATION.json')['initial_vehicle_locations'].values())
    finite=[];ports=[];counts=dict(base=0,fixed=0,automatic=0);qf=float(np.tan(np.arccos(.95)))
    def endpoint(t,case,changed,base_a,source,state):
        e.set_pcc(changed);a=e.settle('auto',state);counts['automatic']+=1;s=summary(e,a)
        rowsport=e.port_measurements();portpass=True
        for p in rowsport:
            mv=p['port_mode']=='MV_DEDICATED_480V';limit=450 if mv else 5;imax=600/(np.sqrt(3)*.48) if mv else 27;sm=600 if mv else 6
            PASS=abs(p['P_kw'])<=limit+1e-6 and p['S_kva']<=sm+1e-6 and p['I_max_A']<=imax+1e-6
            if not mv:PASS=PASS and abs(p['Q_kvar'])<=3+1e-6
            ports.append(dict(source=source,slot=t,case=case,port_limits_PASS=bool(PASS),**p));portpass=bool(portpass and PASS)
        before=float(np.where(e.objective_line_mask,base_a[t],-np.inf).max())
        for n in targets:
            old=float(base_a[t,groups[n]].max());new=float(a['line_rho'][groups[n]].max())
            finite.append(dict(source=source,slot=t,case=case,target_line=n,base_target_rho=old,new_target_rho=new,
                target_relief_rho=old-new,base_global_rho=before,global_relief_rho=before-s['rho_max'],**s,
                port_limits_PASS=portpass,endpoint_electrical_PASS=s['hard_constraints_PASS'] and portpass,
                dispatch96_certificate=False,slot0_connection_available=t>0,scope='instantaneous engineering AC only'))
    for t in slots:
        e.apply_inputs(t,data);a=e.settle('fixed',states[t]);counts['base']+=1
        assert np.abs(a['line_rho']-base['line_rho'][t]).max()<1e-7
        demand=dict(e.base_pcc);bounds={s:float(data['source_mask_P_upper_bound_kw'][t,i]) for i,s in enumerate(sorted(s for s in sites if s.startswith('AIDC')))}
        for site in sites:
            if site.startswith('AIDC'):corners=[(-bounds[site],-bounds[site]*qf)]
            else:
                mv=e.pccs[site]['mode']=='MV_DEDICATED_480V';p,q=(450,300) if mv else (5,3);corners=[(-p,-q),(-p,q),(p,-q),(p,q)]
            for dp,dq in corners:
                changed=dict(demand);x,y=changed[site];changed[site]=(x+dp,y+dq);endpoint(t,site,changed,base['line_rho'],'PLANNING',states[t])
        for case,aidc,mess in [('AIDC_RELAXATION',True,False),('SIX_STA_INSTANT',False,True),('JOINT_RELAXATION',True,True)]:
            changed=dict(demand)
            if aidc:
                for site,p in bounds.items():x,y=changed[site];changed[site]=(x-p,y-p*qf)
            if mess:
                for site in initial:changed[site]=(-450.,0.) if e.pccs[site]['mode']=='MV_DEDICATED_480V' else (-5.,0.)
            endpoint(t,case,changed,base['line_rho'],'PLANNING',states[t])
        print('Joint precheck slot',t,counts,flush=True)
    actual_record=next(r for r in records if r['source']=='ACTUAL' and not r['controlled'])
    astage=REPORT/'ac'/actual_record['first']['tag'];actual=dict(np.load(astage/'AC_96.npz'));adata=dict(np.load(source_input('ACTUAL','2025-05-01')));astates=read(astage/'CONTROL_STATES.json')
    t=int(read(astage/'RECEIPT.json')['peak_slot']);e.apply_inputs(t,adata);changed=dict(e.base_pcc)
    for site in initial:changed[site]=(-450.,0.) if e.pccs[site]['mode']=='MV_DEDICATED_480V' else (-5.,0.)
    endpoint(t,'SIX_STA_INSTANT',changed,actual['line_rho'],'ACTUAL',astates[t])
    write(folder/'DERIVATIVE_REUSE.json',dict(status='REUSED',archive=receipt(REPORT/'FINAL_SEVEN_TIME_DERIVATIVES.npz'),
        duplicate_derivative_AC_calls=0,baseline_scope='original C0 layout; nonlinear selected-layout results separate'))
    table(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv',finite);write(folder/'ALL_PORT_ENDPOINT_READBACK.json',ports)
    write(folder/'RECEIPT.json',dict(day=DAY,AC_calls=counts,runtime_seconds=time.perf_counter()-begin,parameters=e.verify_parameters(),
        failed_endpoint_line_rows=sum(not r['endpoint_electrical_PASS'] for r in finite),
        failed_endpoint_port_rows=sum(not r['port_limits_PASS'] for r in ports),all_failures_retained=True,
        actual_nonzero_AIDC_schedule_certified=False,Native_calls=0,Production=False))


def recover_completed_csv():
    """No AC replay: completed numerical CSV survives a JSON serialization error."""
    folder=REPORT/'precheck';result=rows(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv')
    identities={(r['source'],int(r['slot']),r['case']) for r in result}
    prereg=read(folder/'PREREGISTRATION.json')
    endpoint_count=len(result)//len(prereg['targets'])
    assert endpoint_count==190 and len(result)==190*len(prereg['targets']) and len(prereg['slots'])==3
    truth=lambda x:str(x).lower()=='true'
    elapsed=(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv').stat().st_mtime-(folder/'PREREGISTRATION.json').stat().st_ctime
    write(folder/'RECEIPT.json',dict(day=DAY,status='COMPLETED_WITH_ENDPOINT_DETAIL_UNAVAILABLE',
        AC_calls=dict(base=3,fixed=0,automatic=190),runtime_seconds=elapsed,
        runtime_measurement='filesystem timestamps approximation; perf_counter value lost at serialization exception',
        numerical_endpoint_CSV=receipt(REPORT/'AIDC_MESS_JOINT_PRECHECK.csv'),
        completed_endpoint_solves=endpoint_count,source_slot_site_groups=len(identities),
        failed_endpoint_line_rows=sum(not truth(r['endpoint_electrical_PASS']) for r in result),
        all_failures_retained=True,actual_nonzero_AIDC_schedule_certified=False,
        recovery_AC_solves=0,endpoint_individual_port_raw_readback='UNAVAILABLE: NumPy bool JSON serialization raised after complete CSV persisted',
        port_limit_checks_in_CSV='computed actual readbacks, summary preserved; detailed individual readback lost',
        final96_actual_port_readbacks='COMPLETE in each PORT_96.json; not affected',Native_calls=0,Production=False))


if __name__=='__main__':
    import sys
    recover_completed_csv() if '--recover-csv' in sys.argv else run()
