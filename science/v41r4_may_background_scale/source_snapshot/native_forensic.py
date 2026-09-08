"""Read-only B0 native-control counterfactuals. No authority or model mutation."""
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import hashlib,json,os,time
import numpy as np
import pandas as pd
from screen import ROOT,OUT as SCALE,OLD,RUN,DAY,record,read,save,scale

OUT=ROOT/'dayahead/artifacts/v41r3_native_voltage_control_forensic'
ALPHAS=(1.,1.2,1.4,1.6)

def properties(odd,name,selected=None,excluded=()):
    odd.Circuit.SetActiveElement(name)
    assert str(odd.CktElement.Name()).lower()==name.lower()
    return {p:str(odd.Properties.Value(p)) for p in (selected or odd.CktElement.AllPropertyNames()) if p.lower() not in {x.lower() for x in excluded}}

def settings(odd):
    reg={n:properties(odd,'regcontrol.'+n,excluded=('Enabled','TapNum','Reset','Like')) for n in odd.RegControls.AllNames()}
    cap={n:properties(odd,'capacitor.'+n,selected=('Bus1','Bus2','Phases','kvar','kV','Conn','NumSteps','BaseFreq','Enabled')) for n in odd.Capacitors.AllNames()}
    return dict(regulators=reg,capacitors=cap,CapControl_count=int(odd.CapControls.Count()))

def setup():
    from dayahead.grid_background_v16_2 import AuthorityBackgroundBinding
    from dayahead.v28r2.opendss_mapping import FeederAssets,compile_clean_engine
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    assert read(SCALE/'V41R3_BACKGROUND_SCALE_AUTHORITY.json')['selected_alpha_BG'] is None
    OUT.mkdir(parents=True,exist_ok=True)
    save(OUT/'PROTECTED_BEFORE.json',dict(files=[record(p) for p in [SCALE/'V41R3_BACKGROUND_SCALE_AUTHORITY.json',SCALE/'V41R3_FINAL_FREEZE.json',SCALE/'V41R3_SCALE_REBALANCE_REPORT.json',SCALE/'V41R3_SCALE_REBALANCE_REPORT.md',ROOT/'dayahead/mess_physics.py']],
        source=record(__file__),Full_May='HOLD',ADDITIONAL_DEPENDENCY_GATE='PENDING_NOT_EXECUTED_UNTIL_ALPHA_FROZEN'))
    assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY);prev=Path.cwd()
    try:
        odd,adapter=compile_clean_engine(assets);conf=settings(odd)
        assert conf['CapControl_count']==0,'CapControl found: explicitly implement Mode D before continuing'
        reg=[];caps=[]
        for name,r in conf['regulators'].items():
            odd.RegControls.Name(name);tx=r['Transformer'];odd.Circuit.SetActiveElement('transformer.'+tx)
            buses=list(odd.CktElement.BusNames());phases=int(odd.CktElement.NumPhases())
            txp=properties(odd,'transformer.'+tx,selected=('XHL','%LoadLoss','MinTap','MaxTap','NumTaps'))
            reg.append(dict(name=name,transformer=tx,physical_buses=buses,phases=phases,parameters=r,transformer_parameters=txp,
                controller='NATIVE_AUTONOMOUS_REGCONTROL_IN_DA; FROZEN_EXOGENOUS_STATE_IN_CURRENT_ACTUAL',
                optimization_decision_variable=False))
        for name,c in conf['capacitors'].items():
            odd.Capacitors.Name(name)
            caps.append(dict(name=name,parameters=c,kvar_nameplate=float(odd.Capacitors.kvar()),
                states=list(map(int,odd.Capacitors.States())),NumSteps=int(odd.Capacitors.NumSteps()),
                semantics='FIXED_SHUNT_ALWAYS_ON; NO_CAPCONTROL; no endogenous switching or optimization',autonomous_switching=False))
        odd.Basic.ClearAll()
    finally:os.chdir(prev)
    save(OUT/'NATIVE_CONTROL_DEVICE_INVENTORY.json',dict(status='PASS',settings=conf,RegControl_count=len(reg),regulators=reg,capacitors=caps,
        CapControl_count=0,MODE_D='NOT_APPLICABLE',Bus83=next(c for c in caps if c['name']=='c83'),
        assets=assets.sha256,master=record(assets.master),regulator_definition=record(assets.master.parent/'IEEE123Regulators.DSS'),
        control_implementation=record(ROOT/'dayahead/v28r2/opendss_mapping.py'),
        native_enable_source=record(ROOT/'dayahead/run_v16_3_voltage_candidate.py')))
    backgrounds={};power={};ps=read(SCALE/'V41R3_BACKGROUND_INPUT_PROVENANCE.json')['AIDC_power_sources']
    for stage in ['DAYAHEAD','ACTUAL']:
        with np.load(SCALE/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz') as z:
            axis=[tuple(k.split('::')) for k in z['bus_phase_keys']]
            rows=lambda x:tuple(dict(zip(axis,map(float,row))) for row in x)
            backgrounds[stage]=AuthorityBackgroundBinding(rows(z['gross_P_kw']-z['PV_P_kw']),rows(z['gross_Q_kvar']),rows(z['gross_P_kw']),rows(z['PV_P_kw']),dict(source=record(SCALE/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz')))
        with np.load(ps[stage]['path']) as z:
            pk,qk=('pcc','qcc') if stage=='DAYAHEAD' else ('PCC_P','PCC_Q');power[stage]=(z[pk].copy(),z[qk].copy())
    prev=Path.cwd()
    try:
        src=assets.master.parent.parent
        binding=build_full_grid_binding(assets=src/'opendss_assets',contract=src/'power_v70_p4f_contract',
            demand_mw_96=[0.]*96,rooftop_pv_mw_96=[0.]*96,aidc_plan_kw_96x12=power['DAYAHEAD'][0],pcc_asset=assets.pcc,background_binding=backgrounds['DAYAHEAD'])
    finally:os.chdir(prev)
    return backgrounds,power,ps,binding,conf

def da_state(alpha):
    folder=SCALE/'baseline/DAYAHEAD' if alpha==1 else SCALE/'screen'/f'alpha_{alpha:.3f}'/'DAYAHEAD'
    with np.load(folder/'physics/OPENDSS_PHASE_ARRAYS.npz') as z:
        return {k:z[k].copy() for k in ['node_names','regulator_taps','capacitor_states']}

@contextmanager
def control_mode(mode,voltage):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.opendss_mapping import CAPACITORS
    from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
    old=backend.apply_frozen_native_state
    def native(odd,v,slot):
        # Autonomous Actual trajectory carries previous Actual state forward.
        # Initial condition is the corresponding DA state at slot 0.
        if slot==0:old(odd,v,slot)
        if mode=='C':
            for i,n in enumerate(CAPACITORS):odd.Capacitors.Name(n);odd.Capacitors.States([int(v['capacitor_states'][slot,i])])
        _enable_native_controls(odd)
    if mode in ('B','C'):backend.apply_frozen_native_state=native
    try:yield
    finally:backend.apply_frozen_native_state=old

@contextmanager
def capture_devices(conf):
    from dayahead.v28r2 import opendss_backend as backend
    old=backend._voltage_vector;rows=[];counts=[]
    def observed(odd,nodes):
        result=old(odd,nodes);slot=len(counts);active=odd.CktElement.Name()
        assert settings(odd)==conf,'NATIVE_CONTROL_SETTING_CHANGED'
        counts.append(int(odd.Solution.ControlIterations()))
        for name,r in conf['regulators'].items():
            odd.Transformers.Name(r['Transformer']);odd.Transformers.Wdg(int(r['TapWinding']));tap=float(odd.Transformers.Tap())
            odd.Circuit.SetActiveElement('regcontrol.'+name)
            rows.append(dict(slot=slot,kind='RegControl',device=name,transformer=r['Transformer'],tap=tap,
                tap_number=int(odd.Properties.Value('TapNum')),enabled=bool(odd.CktElement.Enabled())))
        for name,c in conf['capacitors'].items():
            odd.Capacitors.Name(name);states=list(map(int,odd.Capacitors.States()))
            odd.Circuit.SetActiveElement('capacitor.'+name);n=int(odd.CktElement.NumConductors())
            pq=np.asarray(odd.CktElement.Powers(),float).reshape(-1,2)[:n]
            rows.append(dict(slot=slot,kind='Capacitor',device=name,state=states[0],
                nominal_kvar=float(odd.Capacitors.kvar()),P_consumption_kW=float(pq[:,0].sum()),Q_injection_kvar=float(-pq[:,1].sum()),
                Q_injection_A_kvar=float(-pq[0,1]),Q_injection_B_kvar=float(-pq[1,1]) if n>=3 else None,
                Q_injection_C_kvar=float(-pq[2,1]) if n>=3 else None,enabled=bool(odd.CktElement.Enabled())))
        odd.Circuit.SetActiveElement(active)
        return result
    backend._voltage_vector=observed
    try:yield rows,counts
    finally:backend._voltage_vector=old

def replay(alpha,mode,stage,bg,power,ps,binding,conf,state_alpha=None):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v40e.readback import observe as observe_components
    from dayahead.v41.mapper_audit import observe as observe_mapper
    from dayahead.v41.grid_archive import observe as observe_grid,persist as persist_grid
    folder=OUT/'runs'/f'alpha_{alpha:.3f}'/mode;assert not folder.exists()
    voltage=da_state(alpha if state_alpha is None else state_alpha)
    context=SimpleNamespace(legacy_context=({},None,scale(bg,alpha),binding,None,None))
    ids=tuple(f'MESS{i:02}' for i in range(1,5));locations=np.array([[f'TRANSIT_{v}' for v in ids] for _ in range(96)])
    trajectory=FrozenTrajectory(DAY,stage,'B0',*power,np.zeros((96,4)),np.zeros((96,4)),ids,locations,ps['sha256'])
    before=trajectory.immutable_sha256;prev=Path.cwd()
    try:
        with corrected_mapping(),observe_components(folder/'readback','B0',stage) as seen,observe_mapper(folder/'mapper',DAY,stage),observe_grid() as observed,capture_devices(conf) as (devices,iterations),control_mode(mode,voltage):
            result=backend.run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=context,voltage=voltage,trajectory=trajectory,output=folder/'physics')
    finally:os.chdir(prev)
    assert trajectory.immutable_sha256==before
    vf,bf,sf=persist_grid(folder/'grid',DAY,'B0',stage,result,observed,folder/'readback/OPENDSS_COMPONENTS_96.parquet')
    dev=pd.DataFrame(devices);dev.to_parquet(folder/'CONTROL_DEVICES_96.parquet',index=False)
    dev.to_csv(folder/'CONTROL_DEVICES_96.csv',index=False)
    local=vf[vf.bus=='83'].pivot(index='slot',columns='phase',values='voltage_pu')
    cap=dev[(dev.kind=='Capacitor')&(dev.device=='c83')].set_index('slot')
    sf['Bus83_Va_pu']=local.A;sf['Bus83_Vb_pu']=local.B;sf['Bus83_Vc_pu']=local.C
    sf['Bus83_cap_nominal_kvar']=cap.nominal_kvar;sf['Bus83_cap_actual_Q_injection_kvar']=cap.Q_injection_kvar
    sf['Bus83_cap_state']=cap.state;sf['native_control_iterations']=iterations
    sf.to_csv(folder/'SYSTEM_AND_BUS83_96.csv',index=False);sf.to_parquet(folder/'SYSTEM_AND_BUS83_96.parquet',index=False)
    s=result.summary
    wv=vf.loc[vf.voltage_pu.idxmax()];wl=bf[bf.kind=='line'].loc[bf[bf.kind=='line'].loading_pu.idxmax()]
    summary=dict(s,alpha_BG=alpha,mode=mode,stage=stage,
        worst_voltage=dict(bus=str(wv.bus),node=str(wv.node),phase=str(wv.phase),slot=int(wv.slot),timestamp=wv.timestamp.isoformat(),value=float(wv.voltage_pu)),
        worst_line=dict(line=str(wl.line_id),phase=str(wl.phase),slot=int(wl.slot),timestamp=wl.timestamp.isoformat(),value=float(wl.loading_pu)),
        actual_inputs_identical_within_alpha=stage=='ACTUAL',MESS_OFF=True,control_settings_unchanged=True,
        autonomous_Actual_controls=mode in ('B','C'),control_state_initialization='DA slot-0 state; native Actual states carried across slots' if mode in ('B','C') else 'Frozen DA state for each slot',
        frozen_state_alpha_BG=alpha if state_alpha is None else state_alpha,
        Bus83_voltage_min=float(local.min().min()),Bus83_voltage_max=float(local.max().max()),
        Bus83_cap_nominal_kvar=600.,Bus83_actual_cap_Q_min_kvar=float(cap.Q_injection_kvar.min()),Bus83_actual_cap_Q_max_kvar=float(cap.Q_injection_kvar.max()),
        root_import_P_peak_kW=float(sf.feeder_import_P_kW.max()),root_import_Q_min_kvar=float(sf.feeder_import_Q_kvar.min()),root_import_Q_max_kvar=float(sf.feeder_import_Q_kvar.max()),
        component_totals={k:dict(min=float(sf[k].min()),max=float(sf[k].max()),energy=float(.25*sf[k].sum())) for k in ['background_P_kw','background_Q_kvar','AIDC_P_kw','AIDC_Q_kvar','PV_P_kw','PV_Q_kvar']},
        every_slot_system=record(folder/'SYSTEM_AND_BUS83_96.csv'),every_device_every_slot=record(folder/'CONTROL_DEVICES_96.csv'),
        AIDC_power_source=ps,background_source=bg.evidence['source'],trajectory_SHA=before)
    if mode=='A':
        old=SCALE/'baseline/ACTUAL' if alpha==1 else SCALE/'screen'/f'alpha_{alpha:.3f}'/'ACTUAL'
        with np.load(old/'physics/OPENDSS_PHASE_ARRAYS.npz') as z:
            arrays=dict(voltage_pu=result.voltage_pu,phase_current_a=result.phase_current_a,phase_current_loading_pu=result.phase_current_loading_pu,
                transformer_total_kva_loading_pu=result.transformer_total_kva_loading_pu,regulator_taps=result.regulator_taps,capacitor_states=result.capacitor_states)
            assert all(np.array_equal(z[k],v,equal_nan=True) for k,v in arrays.items()),'MODE_A_NOT_BIT_EXACT'
        summary['current_result_reproduction']='BIT_EXACT_ALL_VOLTAGE_CURRENT_TAP_CAP_ARRAYS'
    save(folder/'SUMMARY.json',summary)
    print('FORENSIC',alpha,mode,stage,'rho',s['rho_max_AC'],'V',s['Vmin_pu'],s['Vmax_pu'],flush=True)
    return summary

def main():
    bg,power,ps,binding,conf=setup()
    save(OUT/'FORENSIC_PROTOCOL.json',dict(status='DIAGNOSTIC_ONLY',alphas=list(ALPHAS),
        modes={'A':'Current DA native states frozen in Actual; bit-exact reproduction required',
            'B':'Actual native autonomous controls; DA slot-0 initialization and autonomous state carry-forward',
            'C':'Actual native regulators; preserve DA capacitor state (fixed shunts)',
            'D':'NOT_APPLICABLE: zero CapControl devices'},
        auxiliary={'FIXED_DA1_ACTUAL':'Scaled Actual background at alpha=1 DA tap states; isolates background P/Q effect',
            'FIXED_DA1_FORECAST':'Scaled forecast background at alpha=1 DA tap states; forecast-to-Actual telescoping decomposition'},
        decomposition='Full matched node/slot voltage arrays first; global maxima and fixed Mode-A-worst node/slot separately. Capacitor switching delta zero; passive Q(V) remains physical.',
        MESS='OFF',AIDC_decisions='FROZEN_V41R2_B0',optimization_calls=0,models_changed=False,
        alpha_authority_frozen=False,ADDITIONAL_DEPENDENCY_GATE='PENDING_NOT_EXECUTED',Full_May='HOLD',source=record(__file__)))
    results=[]
    for alpha in ALPHAS:
        for mode in ('A','B','C'):
            results.append(replay(alpha,mode,'ACTUAL',bg['ACTUAL'],power['ACTUAL'],ps['ACTUAL'],binding,conf))
        if alpha!=1:
            results.append(replay(alpha,'FIXED_DA1_ACTUAL','ACTUAL',bg['ACTUAL'],power['ACTUAL'],ps['ACTUAL'],binding,conf,state_alpha=1.))
            results.append(replay(alpha,'FIXED_DA1_FORECAST','DAYAHEAD',bg['DAYAHEAD'],power['DAYAHEAD'],ps['DAYAHEAD'],binding,conf,state_alpha=1.))
    save(OUT/'FORENSIC_RUN_INDEX.json',dict(status='COMPLETE',results=results,trajectories=len(results),slots=len(results)*96))
    print('FORENSIC_RUNS_COMPLETE',len(results),flush=True)

if __name__=='__main__':main()
