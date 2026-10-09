"""Planning-only location/scale admission and paired Fresh research validation."""
import numpy as np
from datetime import datetime, timezone
from ieee8500_v42_high.common import ROOT,REPORT as HIGH,read,write,rows,table,receipt,sha,inputs,BG_CANDIDATES
from ieee8500_v42_high.screen import run_day,fresh_compare
REPORT=ROOT/'docs/ieee8500_v42_joint_pcc_reselection'
DAY='2025-05-01'


def scope_override():
    p=dict(schema='MAY01_EXECUTION_SCOPE_OVERRIDE_V1',day=DAY,slots=96,
        supersedes='OPERATING_POINT_PREREGISTRATION.json separate_actual_and_date only',
        original_preregistration=receipt(REPORT/'OPERATING_POINT_PREREGISTRATION.json'),
        authority='latest human May01-only instruction',May02_results='PRESERVED_EXCLUDED_FROM_JOINT_SELECTION_AND_EFFECTS',
        duplicate_completed_AC=False,long_B1_B2_B3=False,other_campaign_mutations=0,
        own_runner_stop=dict(launcher_pid=94996,child_pid=103940,reason='prevent future May02 branch; completed outputs preserved'))
    path=REPORT/'MAY01_EXECUTION_SCOPE_OVERRIDE.json'
    if path.exists():assert read(path)==p
    else:write(path,p)
    return p


def preregister():
    p=dict(schema='DISPERSED_JOINT_OPERATING_POINT_V1',BG_candidates=list(BG_CANDIDATES),installed_GPU=780,
        installed_expansion='retained high C0/C1/C2 same-job recomputation; hardware-unverified expansion not admitted to final locations',
        candidate_families=['C0_OLD_12LV','C1_MIXED_6MV_6LV','C2_12MV'],maximum_new_full96_Planning_screen_trials=10,
        C0='reuse fixed original high-load comparator15 recomputed+16Fresh datasets; no site mutation',
        selection_priority='C2 thenC1 among model-grid/geometry/dispersion eligible Planning targets; closest rho0.8 then lowerBG; no policy effect or Actual selection',
        target_rho=[.75,.85],common_P5_source=1.04,common_all12_Vreg=123.5,common_CAPBank3_off=True,
        MESS_screening=False,vehicle_units=6,vehicle_Pmax_kw=450,vehicle_Smax_kva=600,vehicle_capacity_kwh=1800,
        vehicle_Emin_kwh=660,vehicle_Emax_kwh=1620,Einitial_and_Eterminal_kwh=1140,
        interfaces=['M1_150kW','M2_300kW','M3_450kW'],MV_Smax_kva=600,MV_phase_current_limit_A=600/(np.sqrt(3)*.48),
        dedicated_transformer_kva=750,new_primary_conductors=0,
        MESS_charge_slots=list(range(8,16)),MESS_discharge_slots=list(range(68,76)),Q_kvar=0.,
        schedule_power_rule='Pch=min(portPmax,(Emax-Einitial)/(eta_ch*2),(Einitial-Emin)/(eta_ch*2)); Pdis=Pch*eta_ch*eta_dis',
        schedule_correction='exact MV battery headroom formula uses eta_ch denominator; earlier conservative LV-comparator formula preserved; no AC effect chosen timing',
        LV_eta=.855,MV_eta=.95,slot0_blocked_entirely=True,connection_delay_seconds=600,
        original_six_initial_STA_IDs_fixed=True,stationary_feasible_proxy_schedule=True,route_distance_and_energy=0,
        traffic_actual_new_PCC_GIS_ETA='UNVERIFIED; original logical service-road ETA preserved; no new empirical travel claim',
        active_interface_selection='M3 by original vehicle rating and engineering-bound availability; all M1/M2/M3 Planning schedule screens retained; if M3 fails reportFAIL, no Actual retune',
        AIDC_control='0; nonzero96QoS/WAN/checkpoint contract not certified; no job synthesis or scaling',
        separate_actual_and_date='May01 Actual private replay, May02 paired exposed-date engineering validation; no unseen/independent holdout claim',
        Actual_failure='FAIL, no location/BG/GPU/PCS/timing or physical rating changes',
        raw_original_AllLine_min_rho_max_unchanged=True,Native_calls=0,field_Production_frozen=False)
    path=REPORT/'OPERATING_POINT_PREREGISTRATION.json'
    if path.exists():assert read(path)==p
    else:write(path,p)
    return p


def source_input(source,day):
    if day!=DAY:raise ValueError('JOINT_RESEARCH_MAY01_ONLY')
    return ROOT/'ieee8500_v42_high/data/facility/recomputed'/f'C0_{source}_INPUTS.npz'


def run_or_reuse(tag,bg,**kwargs):
    """Reuse completed matching records; preserve interrupted output before resume."""
    day=kwargs.get('day',DAY)
    if day!=DAY:raise ValueError('JOINT_RESEARCH_MAY01_ONLY')
    folder=REPORT/'ac'/tag;proof=folder/'RECEIPT.json'
    ledger_path=REPORT/'EXECUTION_REUSE_LEDGER.json'
    ledger=read(ledger_path) if ledger_path.exists() else {}
    if proof.exists():
        r=read(proof)
        expected=dict(day=DAY,source=kwargs.get('source','PLANNING'),bg=bg,layout=kwargs.get('layout','L0'),slots=96)
        assert all(r[k]==v for k,v in expected.items()),('REUSE_METADATA_MISMATCH',tag)
        assert r['AIDC_input']['sha256']==sha(kwargs['input_path'])
        assert r['mapping']['sha256']==sha(kwargs['mapping_path'])
        snap=read(folder/'PARAMETER_SNAPSHOT.json')
        assert snap['P5_overlay_sha256']==sha(HIGH/'overlays/P5.dss') and snap['source_pu']==1.04
        assert len(rows(folder/'SLOTS.csv'))==96
        with np.load(folder/'AC_96.npz') as a:assert a['node_voltage_pu'].shape[0]==96
        assert all((folder/f).exists() for f in ('CUSTOMER_PV_PCC_96.npz','CONTROL_STATES.json','PORT_96.json'))
        previous=ledger.get(tag,{})
        ledger[tag]={**previous,'status':'COMPLETED' if previous.get('status')=='COMPLETED' else 'REUSED',
            'receipt':receipt(proof),'new_operating_point_solves':previous.get('new_operating_point_solves',0),
            'subsequent_reuse_reads':previous.get('subsequent_reuse_reads',0)+1,'Native_calls':0}
        write(ledger_path,ledger)
        return r
    if folder.exists():
        archive=REPORT/'interrupted_preserved'/tag
        archive.parent.mkdir(parents=True,exist_ok=True)
        assert folder.resolve().is_relative_to(REPORT.resolve()) and not archive.exists()
        folder.rename(archive)
        ledger[tag]=dict(status='NEW_VALIDATION_REQUIRED',interrupted_archive=str(archive),
            interrupted_completed_slots='UNKNOWN_0_TO_95; no completion receipt; no finished case repeated')
    ledger[tag]={**ledger.get(tag,{}), 'status':'RUNNING'};write(ledger_path,ledger)
    r=run_day(tag,bg,**kwargs)
    ledger[tag]={**ledger[tag],'status':'COMPLETED','receipt':receipt(proof),'new_operating_point_solves':96,
        'runtime_seconds':r['runtime_seconds'],'Native_calls':0}
    write(ledger_path,ledger)
    return r


def schedule(mapping,level):
    p=preregister();initial=read(HIGH/'SCHEDULE_PREREGISTRATION_CLARIFICATION.json')['initial_vehicle_locations']
    by={r['location_id']:r for r in rows(mapping)};energy={u:1140. for u in initial};schedule=[];soc=[]
    for t in range(96):
        changed={}
        for unit,site in initial.items():
            mv=by[site]['connection_mode']=='MV_3PH';eta=.95 if mv else .855;limit=float(level) if mv else 5.
            pch=min(limit,480/(eta*2),480/(eta*2));pdis=pch*eta*eta
            ch=pch if t in p['MESS_charge_slots'] else 0.;dis=pdis if t in p['MESS_discharge_slots'] else 0.
            before=energy[unit];energy[unit]+=.25*(eta*ch-dis/eta)
            assert 660-1e-8<=energy[unit]<=1620+1e-8 and max(ch,dis)<=limit+1e-8
            changed[site]=(ch-dis,0.)
            soc.append(dict(slot=t,unit=unit,site=site,mode='MV_480V' if mv else 'LV_240V',Pch_AC_kw=ch,Pdis_AC_kw=dis,Q_kvar=0.,
                P_consumption_AC_kw=ch-dis,E_before_kwh=before,E_after_kwh=energy[unit],eta_charge=eta,eta_discharge=eta,
                original_SOC_bounds_preserved=True,route_energy_kwh=0.,route_distance_km=0.,connection_delay_seconds=600,slot0_zero=True,
                station_occupancy_units=1,field_access_and_ETA='UNVERIFIED'))
        schedule.append(changed)
    assert max(abs(e-1140) for e in energy.values())<1e-8
    return schedule,soc


def audit_ports(tag,dispatch,level):
    data=read(REPORT/'ac'/tag/'PORT_96.json');expected={(t,f'STA{i:02d}') for t in range(96) for i in range(1,13)}
    actual=[(r['slot'],r['site']) for r in data];assert len(actual)==1152 and len(set(actual))==1152 and set(actual)==expected
    errors=[];maxI=dict(MV=0.,LV=0.);PQerror=0.
    for r in data:
        mv=r['port_mode']=='MV_DEDICATED_480V';limit=float(level) if mv else 5.;smax=600. if mv else 6.;imax=600/(np.sqrt(3)*.48) if mv else 27.
        desired=dispatch[r['slot']].get(r['site'],(0.,0.));error=max(abs(r['P_kw']-desired[0]),abs(r['Q_kvar']-desired[1]));PQerror=max(PQerror,error)
        finite=np.isfinite([r['P_kw'],r['Q_kvar'],r['S_kva'],r['I_max_A'],*r['per_conductor_A'],*r['per_conductor_voltage_V']]).all()
        PASS=finite and error<1e-5 and abs(r['P_kw'])<=limit+1e-7 and r['S_kva']<=smax+1e-7 and r['I_max_A']<=imax+1e-7
        if not mv:PASS=PASS and abs(r['Q_kvar'])<=3+1e-7 and abs(r['per_conductor_A'][0]-r['per_conductor_A'][1])<1e-6
        else:
            pq=np.asarray(r['per_conductor_PQ']);PASS=PASS and np.abs(pq[:3]-np.array(desired)[None,:]/3).max()<1e-5
        if r['slot']==0:PASS=PASS and abs(r['P_kw'])<1e-8 and abs(r['Q_kvar'])<1e-8
        maxI['MV' if mv else 'LV']=max(maxI['MV' if mv else 'LV'],r['I_max_A'])
        if not PASS:errors.append(dict(slot=r['slot'],site=r['site'],pq_error=error,current_A=r['I_max_A']))
    result=dict(tag=tag,port_actual_current_and_PQ_PASS=not errors,errors=errors,max_current_A=maxI,
        phase_PQ_error_max=PQerror,port_and_vehicle_P_S_distinct=True,all12_all96=True,field_GIS_protection='UNVERIFIED',Native_calls=0)
    write(REPORT/'ac'/tag/'PORT_SCHEDULE_AUDIT.json',result)
    return result


def run():
    p=preregister();scope_override();screens=[]
    for case in ('C1','C2'):
        mapping=REPORT/(case+'_SCORED')/'JOINT_LOCATION_SELECTION.csv'
        if not mapping.exists():continue
        for bg in BG_CANDIDATES:
            screens.append(run_or_reuse(f'{case}_BG{bg:.3f}_B0_PLANNING',bg,input_path=source_input('PLANNING',DAY),
                layout='M3',mapping_path=mapping,report_dir=REPORT))
            table(REPORT/'JOINT_BG_SCREENING.csv',screens)
    eligible=[r for r in screens if r['grid_hard_PASS'] and .75<=r['rho_max']<=.85]
    selected=min(eligible,key=lambda r:(0 if r['tag'].startswith('C2_') else 1,abs(r['rho_max']-.8),r['bg'])) if eligible else None
    decision=dict(selected=selected,Planning_only=True,Actual_for_selection=False,policy_effects_for_selection=False,
        rule=p['selection_priority'],field_Production_eligible=False)
    write(REPORT/'PLANNING_SCENARIO_SELECTION.json',decision)
    if selected is None:return
    case=selected['tag'].split('_')[0];mapping=REPORT/(case+'_SCORED')/'JOINT_LOCATION_SELECTION.csv';bg=selected['bg']
    write(REPORT/'SELECTED_RESEARCH_CONFIGURATION.json',dict(case=case,bg=bg,GPU_capacity=780,P5_overlay=receipt(HIGH/'overlays/P5.dss'),
        mapping=receipt(mapping),placement=read(REPORT/(case+'_SCORED')/'SELECTION_RESULT.json'),ratings=receipt(HIGH/'ENGINEERING_MV_DESIGN.json'),
        effective_model_status='ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED',algorithm_changed=False,min_rho_max_changed=False,
        AIDC_jobs_changed=False,original_ratings_changed=False,Actual_failure_no_retune=True,Native_calls=0,Production=False))
    # Interface screens use fixed schedules/ratings; their effects do not choose placement.
    levels=[]
    for level in (150,300,450):
        dispatch,soc=schedule(mapping,level);label=f'M{1 if level==150 else 2 if level==300 else 3}'
        table(REPORT/f'{label}_SOC_96.csv',soc)
        r=run_or_reuse(f'{case}_{label}_SCHEDULE_PLANNING',bg,layout=label,input_path=source_input('PLANNING',DAY),
            mapping_path=mapping,report_dir=REPORT,schedule=dispatch);port=audit_ports(r['tag'],dispatch,level)
        levels.append(dict(interface=label,level_kw=level,**r,port_audit=port))
        write(REPORT/'INTERFACE_PLANNING_SCREENING.json',levels)
    dispatch,soc=schedule(mapping,450);records=[]
    for day,prefix in [(DAY,'FINAL')]:
        for source in ('PLANNING','ACTUAL'):
            for controlled in (False,True):
                tag=f'{prefix}_{"MESS" if controlled else "B0"}_{source}'
                if source=='PLANNING':tag=f'{case}_M3_SCHEDULE_PLANNING' if controlled else selected['tag']
                kwargs=dict(layout='M3',input_path=source_input(source,day),mapping_path=mapping,report_dir=REPORT,
                    schedule=dispatch if controlled else None,source=source,day=day)
                r=run_or_reuse(tag,bg,**kwargs);fresh=run_or_reuse(tag+'_FRESH',bg,**kwargs);comparison=fresh_compare(tag,tag+'_FRESH',REPORT)
                port=audit_ports(tag,dispatch,450) if controlled else None
                if controlled:audit_ports(tag+'_FRESH',dispatch,450)
                records.append(dict(day=day,source=source,controlled=controlled,first=r,fresh=fresh,comparison=comparison,port_audit=port))
                write(REPORT/'RUN_RECEIPT.json',dict(Planning_selection=decision,records=records,Native_calls=0,
                    Actual_retuning=False,all_original_algorithms_preserved=True,field_Production=False))


if __name__=='__main__':run()
