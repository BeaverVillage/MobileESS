"""IEEE8500 S0/SVR3 with independent, source-supported IDC mobile ports."""
import re,math,json
import numpy as np
from .full_common import *

def source_ports():
    recovery=read(ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')['recovered']
    r=next(r['resolved'] for r in recovery if Path(r['original']).name=='Generated_ThreePhase_PCC_v4.dss')
    p=Path(r['path']);assert sha(p.read_bytes())==r['sha256']
    text=p.read_text(encoding='utf-8');blocks={}
    for i in range(1,13):
        site=f'IDC{i:02d}';m=re.search(r'(?im)^New Transformer\.MESS_'+site+r'_TX.*\n~.*\n~.*',text)
        assert m and re.search(r'kVAs=\[750 750\]',m.group(0))
        assert f'Generator.MESS_DIS_{site}' in text and f'Load.MESS_CHG_{site}' in text
        blocks[site]=m.group(0)
    return put('IDC_ORIGINAL_PHYSICAL_CONTRACT.json',dict(source=record(p),source_blocks=blocks,
        source_building_transformer_kVA=1500,source_mobile_transformer_kVA=750,
        independent_building_and_mobile_facilities=True,IDC_PQ_allowed=True,visit_only=False,
        IEEE8500_design=dict(MV_LL_kV=12.47,LV_LL_kV=.48,mobile_transformer_kVA=750,port_kVA=600,occupancy=1,
            connection='delta_grounded_wye',R_pct_each=.5,XHL_pct=5.662375826453062,no_load_loss_pct=0,magnetizing_current_pct=0,
            explanation='Separate research750kVA mobile transformer like original IDC service; PR199 voltage/impedance design, original IDC zero no-load/magnetizing model. Building MV PCC remains separate. No field certificate inferred.'),
        scientific_physical_domain='24 original service IDs retain MOVE/STAY/P/Q; all24 one-vehicle occupancy',
        field_installation='FIELD_INSTALLATION_UNVERIFIED'))

def engine(tag,role='ACTUAL'):
    from . import correction as c,correction_svr_run as runner
    from .correction_svr_implicit import source_svr
    from .correction_time100 import clock_class
    runner.source_svr=source_svr;runner.RUN=RUN/'ac';runner.RUN.mkdir(exist_ok=True);c.clock_class=clock_class
    class Full(runner.Instrumented):configuration='S1_03' if role=='ACTUAL' else 'S0'
    e=Full(tag,role,'TIME');e.d.Solution.MaxIterations(100)
    oldphase={(x['element'],x['terminal'],x['conductor']):x['physical_phase'] for x in e.line_axes}
    contract=read(OUT/'IDC_ORIGINAL_PHYSICAL_CONTRACT.json')['IEEE8500_design']
    for j in range(1,13):
        site=f'IDC{j:02d}';aidc=f'AIDC{j:02d}';mv=e.pccs[aidc]['bus'];name='full_mobile_'+site.lower();lv=name+'_lv'
        e.d.Text.Command(f'new Transformer.{name} phases=3 windings=2 buses=[{mv}.1.2.3 {lv}.1.2.3.0] conns=[delta wye] kvs=[12.47 .48] kvas=[750 750] %rs=[.5 .5] xhl={contract["XHL_pct"]} %noloadloss=0 %imag=0 rneut=0 normhkva=750 emerghkva=750')
        e.d.Text.Command(f'new Load.mobile_{site.lower()} phases=3 bus1={lv}.1.2.3 conn=wye kv=.48 kw=0 kvar=0 model=1 status=fixed vminpu=.8 vmaxpu=1.2')
        e.pccs[site]=dict(element='Load.mobile_'+site.lower(),bus=lv,mode='MV_DEDICATED_480V',mv_bus=mv)
        e.port_meta.append(dict(site=site,mv_bus=mv,secondary_bus=lv,transformer_kva=750.,interface_kva=600.,interface_current_A=600/(math.sqrt(3)*.48),
            vehicle_P_limit_kw=300.,vehicle_Q_limit_kvar=250.,vehicle_PCS_kva=400.,occupancy_limit=1,hardware_status='SCIENTIFIC_MODEL_FIELD_UNVERIFIED'))
    before=e.control_state()
    e.d.Text.Command('set voltagebases=[115 12.47 .48 .208]');e.d.Text.Command('calcvoltagebases')
    e.d.Solution.ControlMode(-1);e.d.Solution.Solve();e.d.Solution.ControlMode(2)
    assert e.control_state()==before,'PASSIVE_IDC_INSTALLATION_CHANGED_CONTROL_STATE'
    e.inventory=e._inventory();e._orient_original_lines();e._prepare_array_axes();e.orientation=c.independent_orientation(e)
    e.canonical,e.security,e.cmv,e.clv=c.masks(e.line_axes,e.orientation)
    e.all_mask=e.canonical;e.mv_mask=e.cmv;e.lv_mask=e.clv;e.triplex_mask=e.clv
    for x,b in zip(e.line_axes,e.canonical):x.update(physical_phase=oldphase[x['element'],x['terminal'],x['conductor']],objective_included=bool(b))
    e.initial_state=e.control_state();assert len(e.port_meta)==24 and len(e.pccs)==36
    # Separate demands: AIDCxx is building load, IDCxx is mobile-only facility.
    import types
    inherited=e.apply
    def apply(role,t,beta,mess=None,aidc_delta=None):
        inherited(role,t,beta,mess,aidc_delta)
        for j in range(1,13):
            s=f'IDC{j:02d}';p,q=(mess or {}).get(s,(0.,0.));e.base_pcc[s]=(p,q)
            e.d.Loads.Name(e.pccs[s]['element'].split('.',1)[1]);e.d.Loads.kW(float(p));e.d.Loads.kvar(float(q))
    e.apply=apply
    return e

def audit():
    init();resources();source_ports();e=engine('PORT_AUDIT');e.mode='STATIC'
    saved=RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03';state=read(saved/'STATES.json')[55]
    # Newly created transformers at1pu are passive; include existing source state.
    e.apply('ACTUAL',55,2.);row,a,_,_=e.measure('ACTUAL',55,2.,state=state,fixed=True)
    with np.load(saved/'AC_FULL.npz') as z:
        j=np.flatnonzero(z['event_slot']==55)[-1];err=float(np.max(abs(a['line_rho']-z['line_rho'][j])))
    checks=[]
    for site in [f'IDC{i:02d}' for i in range(1,13)]:
        for sign,qs in ((-1,-1),(-1,1),(1,-1),(1,1)):
            e.apply('ACTUAL',55,2.,mess={site:(sign*300,qs*250)})
            r,b,_,ports=e.measure('ACTUAL',55,2.,state=state,fixed=True)
            port=next(x for x in ports if x['site']==site)
            checks.append(dict(sign=sign,P=sign*300,Q=qs*250,**port,local_voltage_PASS=r['node_voltage_violation_cells']==0,
                converged=r['converged'],port_PASS=r['converged'] and port['current_loading']<=1 and port['interface_loading']<=1,transformer_max=r['transformer_nameplate_max']))
    table('IDC12_PORT_PQ_READBACK.csv',checks)
    put('IDC12_PORT_CERTIFICATION.json',dict(PASS=all(x['port_PASS'] for x in checks),zero_MESS_old_B0_line_rho_error=err,
        original_lines=3703,Triplex=1177,IDC_mobile_ports=12,STA_mobile_ports=12,
        building_mobile_rating_shared=False,all24_occupancy_required=True,full_PQ_box_system_safe_claim=False,
        SCIENTIFIC_PORT_MODEL_READY=True,FIELD_INSTALLATION_UNVERIFIED=True,engineering_assumptions=record(OUT/'IDC_ORIGINAL_PHYSICAL_CONTRACT.json')))
    put('FULL_AXES.json',dict(line=e.line_axes,nodes=e.node_axes,transformer_current=e.transformer_axes,transformer_winding=e.transformer_winding_axes))
    print('IDC PORTS',len(checks),'zero B0 rho error',err,flush=True)
if __name__=='__main__':audit()
