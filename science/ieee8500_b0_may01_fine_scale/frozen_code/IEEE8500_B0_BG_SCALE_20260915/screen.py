"""B0-only background P/Q screening; immutable May01 MESS6 spatial authority."""
import os, sys, json, time, hashlib, csv
from pathlib import Path
sys.dont_write_bytecode = True
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np
import opendssdirect as odd
OUT = Path(__file__).absolute().parent
ROOT = OUT.parent.parent
AUTH = ROOT / 'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
sys.path.insert(0, str(ROOT / 'IEEE8500_stress_calibration_20260911'))
import stress_common as s
read, save, table = s.read, s.save, s.table

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def files():
    paths = list((ROOT/'IEEE8500_scalability_20260910/source').rglob('*'))
    paths = [p for p in paths if p.is_file() and p.suffix.lower() == '.dss']
    for folder in [AUTH, ROOT/'independent_screening/IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912']:
        paths += list(folder.glob('*.dss'))
    paths += [AUTH/n for n in ['SCREENING_RULE.json','D1_AEMO_VIC1_FORECAST.json','PCC_OVERLAY_INVENTORY.json','MAPPING_FREEZE.json','FLEET_AUTHORITY.json']]
    paths += [s.overlay_path(1.04,123.5), ROOT/'IEEE8500_production_compatibility_20260911/IEEE8500_Compatibility_Adaptation.dss']
    paths += [Path(m.__file__) for m in [s,s.base,s.old,s.frozen]]
    paths += [ROOT/'IEEE8500_stress_calibration_20260911/stress_control_telemetry.py',Path(__file__)]
    return sorted(set(paths),key=str)

def geometry(d, ax):
    coords={}
    for b in d.Circuit.AllBusNames():
        d.Circuit.SetActiveBus(b);coords[b.lower()]=[d.Bus.X(),d.Bus.Y()]
    names=list(dict.fromkeys(x.split('|')[0] for x in ax['line_label']))
    rows=[]
    for name in names:
        d.Circuit.SetActiveElement(name)
        buses=[b.split('.')[0].lower() for b in d.CktElement.BusNames()]
        rows.append(dict(name=name,bus1=buses[0],bus2=buses[1],xy=[coords[buses[0]],coords[buses[1]]]))
    return dict(coordinates=coords,lines=rows,spatial_transform='none; original OpenDSS bus X/Y')

def run(alpha,rule,forecast,reference):
    folder=OUT/f'alpha_{alpha:.2f}';folder.mkdir(exist_ok=False)
    runtime=folder/'runtime';runtime.mkdir()
    d=odd.NewContext()
    d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False)
    d.Basic.DataPath(str(runtime))
    d.Text.Command(f'Compile "{AUTH / "PCC_Master.dss"}"')
    d.Basic.DataPath(str(runtime))
    d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000)
    assert (d.Circuit.NumBuses(),d.Circuit.NumNodes(),d.Transformers.Count(),d.Solution.ControlMode())==(4912,8639,1226,0)
    loads=s.frozen.native_inventory(d)
    P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads])
    ax=s.frozen.measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames())
    d.Text.Command(f'Redirect "{s.overlay_path(rule["source_pu"],rule["Vreg_V"])}"')
    adapted=s.old.configs(d)
    geo=geometry(d,ax)
    signature=dict(static=s.frozen.digest(adapted),geometry=s.frozen.digest(geo),allocation=s.frozen.digest(loads),axes=s.frozen.digest(ax['rows']))
    if reference is not None:assert signature==reference
    else:
        save(OUT/'GEOMETRY.json',geo);table(OUT/'NATIVE_LOAD_PV_ALLOCATION.csv',loads)
        table(OUT/'HARD_LIMIT_CURRENT_AXES.csv',ax['rows'])
    inv=read(AUTH/'PCC_OVERLAY_INVENTORY.json')
    resource=s.frozen.add_resources(d,loads,rule['PV_ratio'],inv)
    for r in inv:
        if r['PCC_role']=='MESS':
            resource+=f'New Load.screen_mess_{r["location_id"].lower()} phases=3 bus1={r["PCC_bus"]}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed\n'
            d.Text.Command(resource.splitlines()[-1])
    (folder/'RESOURCE_OBJECTS.dss').write_text(resource,encoding='utf-8')
    md=np.array(forecast['demand_mw_96']);md=md/md.max()
    mpv=np.array(forecast['pv_mw_96']);mpv=mpv/mpv.max()
    zero=np.zeros((96,12));values=[[],[],[],[]];rows=[];states=[];start=time.perf_counter()
    for t in range(96):
        # Existing setter scales P/Q uniformly. Correct PV back to its FIXED authority alpha.
        s.old.inputs(d,loads,P,Q,zero,zero,alpha,md,mpv,rule['PV_ratio'],t)
        for i,r in enumerate(loads):
            d.Generators.Name(f'op8500_pv_{i:04d}')
            val=float(rule['PV_alpha_fixed']*rule['PV_ratio']*P[i]*mpv[t])
            d.CktElement.Enabled(val>0)
            if val>0:d.Generators.kW(val);d.Generators.kvar(0.)
        err=None
        try:d.Solution.SolveSnap()
        except Exception as exc:err=str(exc)
        error_number=d.Error.Number()
        if error_number:err=f'{err}; DSS error {error_number}'
        arrays=s.old.measure(d,ax)
        for target,a in zip(values,arrays):target.append(a)
        assert list(d.Circuit.AllNodeNames())==list(nodes)
        scheduled=dict(native_P_scheduled_kw=float(alpha*md[t]*P.sum()),native_Q_scheduled_kvar=float(alpha*md[t]*Q.sum()),PV_scheduled_kw=float(rule['PV_alpha_fixed']*rule['PV_ratio']*mpv[t]*P.sum()),AIDC_P_scheduled_kw=0.,AIDC_Q_scheduled_kvar=0.,MESS_P_scheduled_kw=0.,MESS_Q_scheduled_kvar=0.)
        row=s.base.extrema_row(rule['source_pu'],alpha,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),err,arrays,nodes,ax,scheduled)
        rows.append(row);states.append(s.control_state(d,t,rule['source_pu'],rule['Vreg_V']))
        for r in inv:
            name=('op8500_' if r['PCC_role']=='AIDC' else 'screen_mess_')+r['location_id'].lower()
            d.Loads.Name(name)
            assert d.Loads.kW()==0 and d.Loads.kvar()==0
            assert np.max(np.abs(d.CktElement.Powers()))<1e-10
        if t%24==23:print(f'alpha={alpha:.2f} slots={t+1}/96',flush=True)
    summary=s.base.summarize(rule['source_pu'],alpha,rows,time.perf_counter()-start)
    summary.update(status='PASS' if summary['feasible'] else 'FAIL',date=rule['date'],PV_alpha_fixed=rule['PV_alpha_fixed'])
    for key,axis in [('max_phase_line_loading_pu','line_witness'),('max_transformer_phase_current_pu','transformer_current_witness'),('max_transformer_winding_kva_pu','transformer_kva_witness')]:
        r=max(rows,key=lambda r:r[key]);summary[key+'_slot']=r['slot'];summary[axis]=r[axis]
    for r in loads:
        d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
    after=s.old.configs(d);drift=[n for n in adapted if after[n]!=adapted[n]]
    assert not drift,drift
    assert geometry(d,ax)==geo
    save(folder/'STATIC_SPATIAL_CONSERVATION_AUDIT.json',dict(status='PASS',signatures=signature,native_and_PCC_elements=len(adapted),unexpected_changes=drift,AIDC_MESS_PQ_readback_zero_all_96=True,PV_fixed_all_candidates=True))
    table(folder/'B0_96_SLOT_EXTREMA.csv',rows);save(folder/'B0_CONTROL_STATES_96.json',states);save(folder/'B0_SUMMARY.json',summary)
    np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,line_phase_axes=ax['line_label'],transformer_current_axes=ax['tx_label'],transformer_kva_axes=ax['kva_label'],**{k:np.array(v) for k,v in zip(s.KEYS,values)})
    d.Basic.ClearAll();print(json.dumps(summary),flush=True)
    return summary,signature

def main():
    rule=read(AUTH/'SCREENING_RULE.json');forecast=read(AUTH/'D1_AEMO_VIC1_FORECAST.json')
    assert rule['date']=='2025-05-01' and rule['alpha_BG']==.5 and rule['PV_mode']=='fixed'
    candidates=[round(rule['alpha_BG']+.02*i,2) for i in range(5)]
    freeze=dict(scope='DAYAHEAD B0 exact AC only; AIDC/MESS OFF',date=rule['date'],authority=str(AUTH),candidates=candidates,current_scale=rule['alpha_BG'],PV_alpha_fixed=rule['PV_alpha_fixed'],PV_ratio=rule['PV_ratio'],hard_limits=rule['hard_limits'],colorbar=[0,1],colormap='YlOrRd',heatmap_value='per physical line maximum across phases, both terminals and 96 slots',source_pu=rule['source_pu'],Vreg_V=rule['Vreg_V'],CAPBank3=rule['CAPBank3'],optimization_calls=0,Actual_data_used=False,files=[dict(path=str(p),sha256=sha(p)) for p in files()])
    save(OUT/'PRE_EXECUTION_FREEZE.json',freeze)
    screen=[];signature=None
    for alpha in candidates:
        result,signature=run(alpha,rule,forecast,signature);screen.append(result)
        table(OUT/'SCREEN_TABLE.csv',screen);save(OUT/'SCREEN_TABLE.json',screen)
    good=[r for r in screen if r['feasible']]
    selected=max(good,key=lambda r:(r['max_phase_line_loading_pu'],r['alpha'])) if good else None
    changed=[r['path'] for r in freeze['files'] if sha(r['path'])!=r['sha256']]
    assert not changed,changed
    save(OUT/'RECOMMENDATION.json',dict(status='COMPLETE',selected_scale=selected['alpha'] if selected else None,selected=selected,feasible_scales=[r['alpha'] for r in good],selection='maximum exact phase-line loading among five screened feasible candidates',screened_global_optimum_claim=False,authority_promoted=False,B1_B2_B3_runs=0,optimization_calls=0,explicit_B0_snapshot_solves=480,source_file_conservation='PASS',changed_source_files=changed))
    print('SCREEN_COMPLETE',flush=True)

if __name__=='__main__':main()
