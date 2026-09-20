"""Actual B0 policy: frozen reference AIDC ON, MESS OFF, background .58."""
import os,sys,json,time,hashlib,shutil
from pathlib import Path
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import numpy as np
import opendssdirect as odd
WORK=Path(__file__).absolute().parent;ROOT=WORK.parent.parent
H=Path(sys.argv[2]).absolute();ALPHA=float(sys.argv[1]);H.mkdir(parents=True,exist_ok=True)
BG=ROOT/'independent_screening/IEEE8500_B0_BG_SCALE_20260915'
AUTH=ROOT/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
sys.path.insert(0,str(BG))
import screen as original
s=original.s;read,save,table=original.read,original.save,original.table
sha=original.sha

def main():
    assert not (H/'B0_SUMMARY.json').exists(),'Completed run already exists'
    rule=read(AUTH/'SCREENING_RULE.json');forecast=read(AUTH/'D1_AEMO_VIC1_FORECAST.json')
    assert rule['date']=='2025-05-01' and rule['PV_mode']=='fixed'
    src=AUTH/'MAY01_B0_AIDC_POWER.npz';jobs=AUTH/'REFERENCE_JOBS.json'
    with np.load(src) as z:ap=z['pcc'].copy();aq=z['qcc'].copy();gpu=z['gpu'].copy();it=z['it'].copy()
    with np.load(AUTH/'NORMALIZED_B0_AIDC_POWER.npz') as z:
        assert np.array_equal(ap,2*z['pcc']) and np.array_equal(aq,2*z['qcc'])
    assert ap.shape==aq.shape==(96,12) and np.isfinite(ap).all() and (ap>0).all()
    inherited=read(AUTH/'INHERITED_SOURCE_FREEZE.json')
    # Source ancestry checks use the preserved hashes, independent of migrated path prefixes.
    def records(obj):
        if isinstance(obj,dict):
            if 'path' in obj and 'sha256' in obj:yield obj
            for value in obj.values():yield from records(value)
        elif isinstance(obj,list):
            for value in obj:yield from records(value)
    for p in [src,jobs,AUTH/'NORMALIZED_B0_AIDC_POWER.npz']:
        matches=[r for r in records(inherited) if r['path'].replace('\\','/').split('/')[-1]==p.name]
        assert matches and any(r['sha256']==sha(p) for r in matches),p
    paths=original.files()+[src,jobs,AUTH/'NORMALIZED_B0_AIDC_POWER.npz',AUTH/'AIDC_2X_AUTHORITY.json',AUTH/'INHERITED_SOURCE_FREEZE.json',Path(__file__),BG/'GEOMETRY.json',BG/'alpha_0.58/STATIC_SPATIAL_CONSERVATION_AUDIT.json']
    frozen=[dict(path=str(p),sha256=sha(p)) for p in sorted(set(paths),key=str)]
    save(H/'PRE_EXECUTION_FREEZE.json',dict(policy='B0',namespace='DAYAHEAD',date=rule['date'],background_scale=ALPHA,AIDC='ON: frozen May01 B0 reference workload/PCC injections',AIDC_source=str(src),AIDC_scale_already_in_source=2.,additional_AIDC_rescaling=0,MESS='OFF',PV_alpha_fixed=rule['PV_alpha_fixed'],PV_ratio=rule['PV_ratio'],source_pu=rule['source_pu'],Vreg_V=rule['Vreg_V'],CAPBank3=rule['CAPBank3'],hard_limits=rule['hard_limits'],B1_B2_B3_runs=0,optimization_calls=0,Actual_inputs_used=False,files=frozen))
    shutil.copyfile(src,H/'B0_REFERENCE_AIDC_POWER.npz');shutil.copyfile(jobs,H/'B0_REFERENCE_JOBS.json')
    runtime=H/'runtime';runtime.mkdir(exist_ok=True)
    d=odd.NewContext();d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False)
    d.Basic.DataPath(str(runtime));d.Text.Command(f'Compile "{AUTH/"PCC_Master.dss"}"');d.Basic.DataPath(str(runtime))
    d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000)
    assert (d.Circuit.NumBuses(),d.Circuit.NumNodes(),d.Transformers.Count(),d.Solution.ControlMode())==(4912,8639,1226,0)
    loads=s.frozen.native_inventory(d);P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads])
    ax=s.frozen.measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames())
    d.Text.Command(f'Redirect "{s.overlay_path(rule["source_pu"],rule["Vreg_V"])}"')
    adapted=s.old.configs(d);geo=original.geometry(d,ax)
    signature=dict(static=s.frozen.digest(adapted),geometry=s.frozen.digest(geo),allocation=s.frozen.digest(loads),axes=s.frozen.digest(ax['rows']))
    assert signature==read(BG/'alpha_0.58/STATIC_SPATIAL_CONSERVATION_AUDIT.json')['signatures']
    assert geo==read(BG/'GEOMETRY.json')
    save(H/'GEOMETRY.json',geo);table(H/'NATIVE_LOAD_PV_ALLOCATION.csv',loads);table(H/'HARD_LIMIT_CURRENT_AXES.csv',ax['rows'])
    inv=read(AUTH/'PCC_OVERLAY_INVENTORY.json');resource=s.frozen.add_resources(d,loads,rule['PV_ratio'],inv)
    for r in inv:
        if r['PCC_role']=='MESS':
            cmd=f'New Load.b0_mess_{r["location_id"].lower()} phases=3 bus1={r["PCC_bus"]}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed'
            d.Text.Command(cmd);resource+=cmd+'\n'
    (H/'RESOURCE_OBJECTS.dss').write_text(resource,encoding='utf-8')
    md=np.array(forecast['demand_mw_96']);md/=md.max();mpv=np.array(forecast['pv_mw_96']);mpv/=mpv.max()
    values=[[],[],[],[]];rows=[];states=[];readback=[];start=time.perf_counter()
    for t in range(96):
        s.old.inputs(d,loads,P,Q,ap,aq,ALPHA,md,mpv,rule['PV_ratio'],t)
        for i,r in enumerate(loads):
            d.Generators.Name(f'op8500_pv_{i:04d}');v=float(rule['PV_alpha_fixed']*rule['PV_ratio']*P[i]*mpv[t]);d.CktElement.Enabled(v>0)
            if v>0:d.Generators.kW(v);d.Generators.kvar(0.)
        error=None
        try:d.Solution.SolveSnap()
        except Exception as exc:error=str(exc)
        en=d.Error.Number()
        if en:error=f'{error}; DSS error {en}'
        arrays=s.old.measure(d,ax)
        for target,a in zip(values,arrays):target.append(a)
        assert list(d.Circuit.AllNodeNames())==list(nodes)
        schedule=dict(native_P_scheduled_kw=float(ALPHA*md[t]*P.sum()),native_Q_scheduled_kvar=float(ALPHA*md[t]*Q.sum()),PV_scheduled_kw=float(rule['PV_alpha_fixed']*rule['PV_ratio']*mpv[t]*P.sum()),AIDC_P_scheduled_kw=float(ap[t].sum()),AIDC_Q_scheduled_kvar=float(aq[t].sum()),MESS_P_scheduled_kw=0.,MESS_Q_scheduled_kvar=0.)
        row=s.base.extrema_row(rule['source_pu'],ALPHA,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),error,arrays,nodes,ax,schedule)
        rows.append(row);states.append(s.control_state(d,t,rule['source_pu'],rule['Vreg_V']))
        for r in inv:
            aidc=r['PCC_role']=='AIDC';n=('op8500_' if aidc else 'b0_mess_')+r['location_id'].lower();d.Loads.Name(n)
            j=int(r['location_id'][4:])-1 if aidc else 0
            ep,eq=(float(ap[t,j]),float(aq[t,j])) if aidc else (0.,0.)
            assert d.Loads.kW()==ep and d.Loads.kvar()==eq
            actual=np.array(d.CktElement.Powers()).reshape(-1,2).sum(axis=0)
            # Command equality is exact; solved P/Q residuals follow the unchanged DSS tolerance.
            assert np.isfinite(actual).all()
            if aidc:assert actual[0]>0
            else:assert np.max(np.abs(actual))<1e-10
            readback.append(dict(slot=t,role=r['PCC_role'],location=r['location_id'],PCC_bus=r['PCC_bus'],scheduled_P_kw=ep,scheduled_Q_kvar=eq,physical_P_kw=float(actual[0]),physical_Q_kvar=float(actual[1]),P_residual_kw=float(actual[0]-ep),Q_residual_kvar=float(actual[1]-eq)))
        if t%24==23:print(f'B0 policy {ALPHA:.6f} AIDC ON MESS OFF: {t+1}/96',flush=True)
    summary=s.base.summarize(rule['source_pu'],ALPHA,rows,time.perf_counter()-start)
    summary.update(policy='B0',namespace='DAYAHEAD',status='PASS' if summary['feasible'] else 'FAIL',date=rule['date'],AIDC='REFERENCE_ON',MESS='OFF',PV_alpha_fixed=rule['PV_alpha_fixed'],optimization_calls=0,B1_B2_B3_runs=0)
    summary.update(max_PCC_readback_P_residual_kw=max(abs(r['P_residual_kw']) for r in readback),max_PCC_readback_Q_residual_kvar=max(abs(r['Q_residual_kvar']) for r in readback),OpenDSS_convergence_tolerance=d.Solution.Convergence())
    for key,witness in [('max_phase_line_loading_pu','line_witness'),('max_transformer_phase_current_pu','transformer_current_witness'),('max_transformer_winding_kva_pu','transformer_kva_witness'),('Vmin_pu','Vmin_node'),('Vmax_pu','Vmax_node')]:
        r=(min if key=='Vmin_pu' else max)(rows,key=lambda r:r[key]);summary[key+'_slot']=r['slot'];summary[witness]=r[witness]
    for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
    after=s.old.configs(d);assert all(after[n]==adapted[n] for n in adapted);assert original.geometry(d,ax)==geo
    save(H/'STATIC_SPATIAL_CONSERVATION_AUDIT.json',dict(status='PASS',signatures=signature,identical_to_background_screening=True,native_and_PCC_elements=len(adapted),unexpected_changes=[],B0_reference_injections_unchanged=True,MESS_zero_all_96=True,PV_unchanged=True))
    table(H/'B0_96_SLOT_EXTREMA.csv',rows);table(H/'B0_PCC_INJECTION_READBACK.csv',readback);save(H/'B0_CONTROL_STATES_96.json',states);save(H/'B0_SUMMARY.json',summary)
    np.savez_compressed(H/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,line_phase_axes=ax['line_label'],transformer_current_axes=ax['tx_label'],transformer_kva_axes=ax['kva_label'],**{k:np.array(v) for k,v in zip(s.KEYS,values)})
    assert all(sha(r['path'])==r['sha256'] for r in frozen)
    save(H/'SOURCE_CONSERVATION.json',dict(status='PASS',checked_files=len(frozen),new_scheduling_optimization_calls=0,B1_B2_B3_runs=0))
    d.Basic.ClearAll();print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
