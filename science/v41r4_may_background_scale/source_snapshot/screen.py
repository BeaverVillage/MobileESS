"""B0-only, solver-free, clean-engine background-scale screen."""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from contextlib import contextmanager
import hashlib,json,os,sys,time
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'MobileESS_v41r2_780gpu_capacity_rebase'
RUN=OLD/'frozen_artifacts/v41r2_780'
OUT=ROOT/'dayahead/artifacts/v41r3_scale_rebalance'
DAY='2025-05-04'
def record(p):
    p=Path(p)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p.resolve()),sha256=h,bytes=p.stat().st_size)
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    with p.open('x',encoding='utf-8') as f:f.write(data)
    assert json.loads(p.read_text(encoding='utf-8'))==v
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def persist_arrays(p,**a):
    p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists()
    np.savez_compressed(p,**a)
    with np.load(p) as z:assert all(np.array_equal(z[k],v,equal_nan=True) if np.asarray(v).dtype.kind=='f' else np.array_equal(z[k],v) for k,v in a.items())
    return record(p)

def inputs():
    from dayahead.grid_background_v16_2 import AuthorityBackgroundBinding
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY);assets.validate()
    src=assets.master.parent.parent
    adapter=read(assets.runtime_adapter)
    da_source=RUN/'e/20250504/kernel/electrical'/DAY/'UPSTREAM_BUS_PHASE_TARGETS.npz'
    with np.load(da_source) as z:
        axis=[tuple(k.split('::')) for k in z['bus_phase_keys']]
        da={k:z[k].copy() for k in ['gross_P_kw','gross_Q_kvar','PV_P_kw']}
    actual_source=RUN/DAY/'B0/actual/audit/mapper/NATIVE_BUS_PHASE_96.parquet'
    af=pd.read_parquet(actual_source)
    pv_source=RUN/DAY/'B0/actual/actual_readback/OPENDSS_COMPONENT_ELEMENTS.parquet'
    pf=pd.read_parquet(pv_source);pf=pf[pf.component=='PV'].copy()
    ac={k:np.zeros((96,len(axis))) for k in da};index={k:i for i,k in enumerate(axis)}
    for r in af.itertuples():
        j=index[(r.bus,r.phase)];ac['gross_P_kw'][r.slot,j]=r.target_P_kW;ac['gross_Q_kvar'][r.slot,j]=r.target_Q_kvar
    pvmap={('generator.'+r['generator_name']).lower():(r['bus'].lower(),'ABC'[r['phase']-1]) for r in adapter['pv_generators']}
    assert not pf.duplicated(['slot','element']).any() and len(pf)==96*len(pvmap)
    for r in pf.itertuples():
        assert abs(r.P_kw-r.expected_P_kw)<1e-8 and r.Q_kvar==0
        ac['PV_P_kw'][r.slot,index[pvmap[r.element.lower()]]]=r.expected_P_kw
    assert len(af)==96*len(af[['bus','phase']].drop_duplicates())
    power={};power_sources={};backgrounds={};records={}
    for stage,a in [('DAYAHEAD',da),('ACTUAL',ac)]:
        p=RUN/DAY/'B0'/('dayahead/FROZEN_AIDC_POWER.npz' if stage=='DAYAHEAD' else 'actual/ACTUAL_AIDC_POWER.npz')
        with np.load(p) as z:
            pkey,qkey=('pcc','qcc') if stage=='DAYAHEAD' else ('PCC_P','PCC_Q')
            power[stage]=(z[pkey].copy(),z[qkey].copy())
        power_sources[stage]=record(p)
        rows=lambda x:tuple(dict(zip(axis,map(float,row))) for row in x)
        backgrounds[stage]=AuthorityBackgroundBinding(rows(a['gross_P_kw']-a['PV_P_kw']),rows(a['gross_Q_kvar']),rows(a['gross_P_kw']),rows(a['PV_P_kw']),{'role':'FROZEN_V41R2_B0_EXOGENOUS_SETPOINTS'})
        p=OUT/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz'
        records[stage]=persist_arrays(p,bus_phase_keys=np.array(['::'.join(k) for k in axis]),**a)
    oldv=RUN/'e/20250504/kernel/electrical'/DAY/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{DAY}.npz'
    with np.load(oldv) as z:voltage={k:z[k].copy() for k in ['node_names','regulator_taps','capacitor_states']}
    # Binding supplies topology/ratings only. No AC coefficients enter selection.
    previous=Path.cwd()
    try:
        binding=build_full_grid_binding(assets=src/'opendss_assets',contract=src/'power_v70_p4f_contract',
            demand_mw_96=[0.]*96,rooftop_pv_mw_96=[0.]*96,aidc_plan_kw_96x12=power['DAYAHEAD'][0],
            pcc_asset=assets.pcc,background_binding=backgrounds['DAYAHEAD'])
    finally:os.chdir(previous)
    refs=[record(da_source),record(actual_source),record(pv_source)]
    lineage=read(RUN/'e/20250504/kernel/electrical'/DAY/'UPSTREAM_REUSE_CERTIFICATE.json')
    original_sources=[]
    for p,h in lineage['source_input_SHAs'].items():
        r=record(p);assert r['sha256']==h;original_sources.append(r)
    for r in read(RUN/DAY/'B0/actual/ACTUAL_EXOGENOUS_AUTHORITY.json').values():
        current=record(r['path']);assert current['sha256']==r['sha256'];original_sources.append(current)
    save(OUT/'V41R3_BACKGROUND_INPUT_PROVENANCE.json',dict(status='PASS',original_background_arrays=records,
        compiled_input_sources=refs,raw_exogenous_sources=original_sources,AIDC_power_sources=power_sources,
        Actual_reconstruction='Original target_P/target_Q columns and expected PV setpoints only; no policy results or control decisions',
        original_native_state_for_alpha1_validation=record(oldv),feeder_assets=assets.sha256,
        ML_RETRAIN_COUNT=0,ML_RECALIBRATION_COUNT=0,ML_MODEL_CHANGE_COUNT=0))
    return backgrounds,power,power_sources,voltage,binding,records

def scale(background,alpha):
    p=tuple({k:alpha*v for k,v in r.items()} for r in background.gross_p_kw_96)
    q=tuple({k:alpha*v for k,v in r.items()} for r in background.gross_q_kvar_96)
    net=tuple({k:r[k]-background.pv_generation_kw_96[t].get(k,0.) for k in r} for t,r in enumerate(p))
    return replace(background,gross_p_kw_96=p,gross_q_kvar_96=q,net_p_kw_96=net,
        evidence={**background.evidence,'alpha_BG':alpha,'PV_scaled':False})

@contextmanager
def native_day_ahead(enabled):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.run_v16_3_voltage_candidate import _enable_native_controls
    old=backend.apply_frozen_native_state
    if enabled:backend.apply_frozen_native_state=lambda odd,voltage,slot:_enable_native_controls(odd)
    try:yield
    finally:backend.apply_frozen_native_state=old

def replay(alpha,stage,bg,power,power_source,voltage,binding,folder,native=False):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v40e.readback import observe as observe_components
    from dayahead.v41.mapper_audit import observe as observe_mapper
    from dayahead.v41.grid_archive import observe as observe_grid,persist as persist_grid
    background=scale(bg,alpha);axis=list(background.gross_p_kw_96[0])
    arrays=dict(bus_phase_keys=np.array(['::'.join(k) for k in axis]))
    for name,rows in [('gross_P_kw',background.gross_p_kw_96),('gross_Q_kvar',background.gross_q_kvar_96),('PV_P_kw',background.pv_generation_kw_96)]:
        arrays[name]=np.array([[r.get(k,0.) for k in axis] for r in rows])
    scaled=persist_arrays(folder/'SCALED_BACKGROUND.npz',**arrays)
    context=SimpleNamespace(legacy_context=({},None,background,binding,None,None))
    ids=tuple(f'MESS{i:02}' for i in range(1,5));locations=np.array([[f'TRANSIT_{v}' for v in ids] for _ in range(96)])
    trajectory=FrozenTrajectory(DAY,stage,'B0',*power,np.zeros((96,4)),np.zeros((96,4)),ids,locations,power_source['sha256'])
    previous=Path.cwd()
    try:
        with corrected_mapping(),observe_components(folder/'readback','B0',stage) as seen,observe_mapper(folder/'mapper',DAY,stage),observe_grid() as observed,native_day_ahead(native):
            result=backend.run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=context,voltage=voltage,trajectory=trajectory,output=folder/'physics')
    finally:os.chdir(previous)
    vf,bf,sf=persist_grid(folder/'grid',DAY,'B0',stage,result,observed,folder/'readback/OPENDSS_COMPONENTS_96.parquet')
    summary=result.summary
    gates=dict(voltage=summary['Vmin_pu']>=.95 and summary['Vmax_pu']<=1.05,
        line=summary['rho_max_AC']<1.,transformer_current=summary['transformer_phase_current_loading_max']<1.,
        transformer_kVA=summary['transformer_total_kva_loading_max']<1.,convergence=summary['convergence_count']==96)
    def worst(frame,col,maximum=True):
        r=frame.loc[frame[col].idxmax() if maximum else frame[col].idxmin()]
        return {k:(v.isoformat() if isinstance(v,pd.Timestamp) else v.item() if isinstance(v,np.generic) else v) for k,v in r.to_dict().items() if k in ['slot','timestamp','node','bus','phase','line_id',col]}
    summary.update(alpha_BG=alpha,stage=stage,physical_gates=gates,eligible=all(gates.values()),
        target_stress=.75<=summary['rho_max_AC']<=.85,root_import_P_peak_kW=float(sf.feeder_import_P_kW.max()),
        root_import_Q_peak_kvar=float(sf.feeder_import_Q_kvar.max()),root_import_P_min_kW=float(sf.feeder_import_P_kW.min()),
        transformer_phase_current_max_A=float(bf.loc[bf.kind=='transformer','current_A'].max()),
        worst_line=worst(bf[bf.kind=='line'],'loading_pu'),worst_voltage_high=worst(vf,'voltage_pu'),worst_voltage_low=worst(vf,'voltage_pu',False),
        native_control_rule='NATIVE_DA_B0_THEN_FROZEN_IN_ACTUAL',native_DA_solve=native,
        scaled_background=scaled,AIDC_power_source=power_source,mapper=record(folder/'mapper/MAPPER_AUDIT.json'))
    save(folder/'SUMMARY.json',summary)
    print('B0_SCREEN',alpha,stage,'rho',summary['rho_max_AC'],'V',summary['Vmin_pu'],summary['Vmax_pu'],'eligible',summary['eligible'],flush=True)
    return summary,result

def main():
    assert (OUT/'PROTECTED_BEFORE.json').exists()
    rule=dict(schema='V41R3_PREDECLARED_B0_SCALE_SELECTION_V1',coarse=[1.2,1.3,1.4,1.5,1.6],delta_alpha=.025,
        both_stages_required=True,target_interval=[.75,.85],rho_target=.8,
        rank='minimize max(abs(rho_DA-.80),abs(rho_Actual-.80)); then mean absolute error; then smaller alpha',
        refinement='Only if no eligible coarse candidate in target. One adjacent coarse interval containing .80 of max(DA,Actual) rho; otherwise nearest interval. Minimum distance to .80 then lower alpha; interior .025 grid only.',
        no_out_of_range_search=True,B1_B2_B3_RESULTS_USED_FOR_SELECTION=False,MESS='OFF',optimization_calls=0,
        native_controls='Existing D1 native-control rule regenerated from each scaled B0 forecast; Actual freezes that candidate D1 state.',
        hard_limits=dict(Vmin=.95,Vmax=1.05,line_strict_upper=1.,transformer_current_strict_upper=1.,transformer_kVA_strict_upper=1.),
        created_UTC=pd.Timestamp.now(tz='UTC').isoformat(),source=record(__file__),Full_May='HOLD')
    save(OUT/'V41R3_PREDECLARED_SELECTION_RULE.json',rule)
    bg,power,ps,voltage,binding,sources=inputs()
    # Reproduce protected B0 with its own frozen taps before screening scales.
    for stage in ['DAYAHEAD','ACTUAL']:
        s,r=replay(1.,stage,bg[stage],power[stage],ps[stage],voltage,binding,OUT/'baseline'/stage)
        old=read(RUN/DAY/'B0'/('dayahead/FRESH_RESULT.json' if stage=='DAYAHEAD' else 'actual/ACTUAL_RESULT.json'))['summary']
        errors={k:abs(s[k]-old[k]) for k in ['Vmin_pu','Vmax_pu','rho_max_AC','transformer_phase_current_loading_max','transformer_total_kva_loading_max']}
        assert max(errors.values())<1e-9,errors
        save(OUT/'baseline'/stage/'REPRODUCTION.json',dict(status='PASS',errors=errors))
    candidates=[]
    def candidate(a):
        folder=OUT/'screen'/f'alpha_{a:.3f}'
        da,dr=replay(a,'DAYAHEAD',bg['DAYAHEAD'],power['DAYAHEAD'],ps['DAYAHEAD'],voltage,binding,folder/'DAYAHEAD',native=True)
        v=dict(node_names=voltage['node_names'],regulator_taps=dr.regulator_taps,capacitor_states=dr.capacitor_states)
        ac,ar=replay(a,'ACTUAL',bg['ACTUAL'],power['ACTUAL'],ps['ACTUAL'],v,binding,folder/'ACTUAL')
        c=dict(alpha_BG=a,DAYAHEAD=da,ACTUAL=ac,eligible=da['eligible'] and ac['eligible'],target=da['target_stress'] and ac['target_stress'])
        candidates.append(c);save(folder/'CANDIDATE.json',c)
    for a in rule['coarse']:candidate(a)
    qualified=lambda:[c for c in candidates if c['eligible'] and c['target']]
    if not qualified():
        intervals=[]
        for lo,hi in zip(candidates,candidates[1:]):
            x,y=[max(c['DAYAHEAD']['rho_max_AC'],c['ACTUAL']['rho_max_AC']) for c in [lo,hi]]
            distance=0 if min(x,y)<=.8<=max(x,y) else min(abs(x-.8),abs(y-.8))
            intervals.append((distance,lo['alpha_BG'],hi['alpha_BG']))
        _,lo,hi=min(intervals)
        save(OUT/'V41R3_REFINEMENT_INTERVAL.json',dict(lower=lo,upper=hi,step=.025,only_B0_inputs=True))
        for v in range(round(lo*1000)+25,round(hi*1000),25):candidate(v/1000)
    def rank(c):
        d=[abs(c[s]['rho_max_AC']-.8) for s in ['DAYAHEAD','ACTUAL']]
        return max(d),sum(d)/2,c['alpha_BG']
    chosen=min(qualified(),key=rank) if qualified() else None
    authority=dict(schema='V41R3_BACKGROUND_SCALE_AUTHORITY_V1',status='FROZEN' if chosen else 'FAIL_CLOSE_NO_ELIGIBLE_ALPHA',
        selected_alpha_BG=chosen['alpha_BG'] if chosen else None,original_background_SHA=sources,
        selected=chosen,all_candidates=candidates,selection_rule=record(OUT/'V41R3_PREDECLARED_SELECTION_RULE.json'),
        B1_B2_B3_RESULTS_USED_FOR_SELECTION=False,background_scale_may_change_after_policy_results=False,
        downstream_execution_allowed=bool(chosen),Full_May='HOLD',frozen_UTC=pd.Timestamp.now(tz='UTC').isoformat())
    save(OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json',authority)
    print('SCREEN_COMPLETE',authority['status'],authority['selected_alpha_BG'],flush=True)

if __name__=='__main__':main()
