import sys,json,csv,hashlib,time,math
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OLD=ROOT/'IEEE8500_operating_point_20260911';PCC=ROOT/'IEEE8500_pcc_overlay_20260911'
sys.path.insert(0,str(OLD))
import run_b0_screen as frozen
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')
def table(p,rs):
    if not rs:return
    with Path(p).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader()
        for r in rs:w.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()})
def record(p):
    p=Path(p);s=p.stat();return dict(path=str(p),sha256=sha(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
def check_freeze():
    f=read(HERE/'PRE_EXECUTION_FREEZE_MANIFEST.json')
    assert sha(HERE/'PRE_EXECUTION_FREEZE_MANIFEST.json')==(HERE/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').read_text().split()[0]
    for r in f['bound_files']:assert sha(Path(r['path']))==r['sha256'],r['path']
    return f
def configs(d):
    out=frozen.static_inputs(d)
    for n in out:d.Circuit.SetActiveElement(n);out[n]['__element_enabled__']=d.CktElement.Enabled()
    return out
def differences(a,b):
    assert a.keys()==b.keys();return [dict(element=n,property=k,before=v,after=b[n][k]) for n,props in a.items() for k,v in props.items() if v!=b[n][k]]
def control_state(d,t):
    regs=[];caps=[]
    for name in d.RegControls.AllNames():
        d.RegControls.Name(name);tf=d.RegControls.Transformer();tap=d.RegControls.TapNumber();vreg=d.RegControls.ForwardVreg();band=d.RegControls.ForwardBand();ratio=float(d.Properties.Value('ptratio'));enabled=d.CktElement.Enabled();w=d.RegControls.TapWinding()
        d.Transformers.Name(tf);d.Transformers.Wdg(w);regs.append(dict(name=name,transformer=tf,tap_number=tap,tap_pu=d.Transformers.Tap(),Vreg=vreg,band=band,PT_ratio=ratio,enabled=enabled,min_tap=d.Transformers.MinTap(),max_tap=d.Transformers.MaxTap()))
    for name in d.Capacitors.AllNames():
        d.Capacitors.Name(name);en=d.CktElement.Enabled();states=list(d.Capacitors.States());kv=d.Capacitors.kV();kvar=d.Capacitors.kvar()
        q=float(-np.asarray(d.CktElement.Powers()).reshape(-1,2)[:,1].sum()) if en else 0.
        caps.append(dict(name=name,enabled=en,step_states=states,effective_ON=en and any(states),nameplate_kvar=kvar,nominal_kV=kv,physical_injected_kvar=q))
    ctrls=[]
    for name in d.CapControls.AllNames():d.CapControls.Name(name);ctrls.append(dict(name=name,enabled=d.CktElement.Enabled(),capacitor=d.CapControls.Capacitor()))
    d.Vsources.First();source=d.Vsources.PU()
    assert source==1.05
    assert all(r['Vreg']==125 and r['band']==2 and r['PT_ratio']==60 and r['enabled'] for r in regs)
    assert all(c['enabled']==(c['name']!='capbank3') for c in caps) and all(c['enabled'] for c in ctrls)
    return dict(slot=t,source_pu=source,regulators=regs,capacitors=caps,capcontrols=ctrls,control_iterations=d.Solution.ControlIterations(),powerflow_iterations=d.Solution.Iterations())
def inputs(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t):
    factor=float(a*md[t]);d.Solution.LoadMult(1.);d.Solution.Hour(t//4);d.Solution.Seconds((t%4)*900)
    for i,r in enumerate(loads):
        d.Loads.Name(r['load']);d.Loads.kW(float(factor*P[i]));d.Loads.kvar(float(factor*Q[i]));assert abs(d.Loads.kW()-factor*P[i])<1e-12 and abs(d.Loads.kvar()-factor*Q[i])<1e-12
        if a>0:assert abs(d.Loads.PF()-r['base_pf'])<1e-12
        d.Generators.Name(f'op8500_pv_{i:04d}');val=float(a*ratio*P[i]*mpv[t]);d.CktElement.Enabled(val>0)
        if val>0:d.Generators.kW(val);d.Generators.kvar(0.)
    for j in range(12):d.Loads.Name(f'op8500_aidc{j+1:02d}');d.Loads.kW(float(ap[t,j]));d.Loads.kvar(float(aq[t,j]))
def measure(d,ax):
    v=np.array(d.Circuit.AllBusMagPu());raw=np.array(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)[:,0];pw=np.array(d.PDElements.AllPowers()).reshape(-1,2)
    assert len(raw)==len(pw)==ax['flat_count']
    ll=raw[ax['line_pos']]/ax['line_rating'];tx=raw[ax['tx_pos']]/ax['tx_rating'];p=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],0]);q=np.bincount(ax['power_group'],weights=pw[ax['power_pos'],1]);kva=np.hypot(p,q)/ax['kva_rating']
    assert all(np.isfinite(x).all() for x in [v,ll,tx,kva]);return v,ll,tx,kva
def main():
    check_freeze();rule=read(HERE/'COMPATIBILITY_RULE.json');forecast=read(OLD/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');md=np.array(forecast['demand_mw_96'])/max(forecast['demand_mw_96']);mpv=np.array(forecast['pv_mw_96'])/max(forecast['pv_mw_96']);ratio=read(OLD/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio']
    with np.load(OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:ap=z['pcc'].copy();aq=z['qcc'].copy()
    inv=read(PCC/'PCC_OVERLAY_INVENTORY.json');screen=[];allrows=[];native_sha=adapted_sha=None;tol=rule['limits']['floating_point_boundary_tolerance']
    for a in rule['alpha_grid_descending']:
        folder=HERE/'screen'/f'alpha_{a:.2f}';folder.mkdir(parents=True,exist_ok=False);d=frozen.engine(folder/'runtime');native=configs(d);loads=frozen.native_inventory(d);P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);nodes=np.array(d.Circuit.AllNodeNames())
        # Axes are unchanged: only capacitor status and regulator setpoints differ.
        ax=frozen.measurement_axes(d);d.Text.Command(f'Redirect "{HERE / "IEEE8500_Compatibility_Adaptation.dss"}"');adapted=configs(d);diff=differences(native,adapted)
        expected_regs={'regcontrol.feeder_rega','regcontrol.feeder_regb','regcontrol.feeder_regc'};seen=set()
        for r in diff:
            n,k=r['element'],r['property'].lower()
            if n in expected_regs:assert k=='vreg' and float(r['before'])==126.5 and float(r['after'])==125.;seen.add(n)
            else:assert n=='capacitor.capbank3' and k in ['enabled','__element_enabled__']
        assert seen==expected_regs and not adapted['capacitor.capbank3']['__element_enabled__']
        if native_sha is None:
            native_sha=frozen.digest(native);adapted_sha=frozen.digest(adapted)
            save(HERE/'PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json',dict(status='PASS',exact_static_differences=diff,native_config_sha256=native_sha,adapted_config_sha256=adapted_sha,canonical_reproduction=False,permitted_adaptation_only=True))
            table(HERE/'NATIVE_LOAD_BASELINE.csv',loads)
        else:assert native_sha==frozen.digest(native) and adapted_sha==frozen.digest(adapted)
        assert frozen.add_resources(d,loads,ratio,inv)==(OLD/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8')
        base_after_add=configs(d);assert all(base_after_add[n]==adapted[n] for n in adapted)
        vv=[];lines=[];tfs=[];kvas=[];rr=[];states=[];started=time.perf_counter()
        for t in range(96):
            inputs(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t);err=None
            try:d.Solution.SolveSnap()
            except Exception as ex:
                if '#485' not in str(ex):raise
                err=str(ex)
            cv=bool(d.Solution.Converged());cc=bool(d.Solution.ControlActionsDone());v,ll,tx,kv=measure(d,ax)
            assert list(d.Circuit.AllNodeNames())==list(nodes)
            vv.append(v);lines.append(ll);tfs.append(tx);kvas.append(kv)
            row=dict(alpha=a,slot=t,converged=cv,control_actions_complete=cc,solver_error=err,Vmin_pu=float(v.min()),Vmin_node=str(nodes[v.argmin()]),Vmax_pu=float(v.max()),Vmax_node=str(nodes[v.argmax()]),max_phase_line_loading_pu=float(ll.max()),line_witness=str(ax['line_label'][ll.argmax()]),max_transformer_phase_current_pu=float(tx.max()),transformer_current_witness=str(ax['tx_label'][tx.argmax()]),max_transformer_winding_kva_pu=float(kv.max()),transformer_kva_witness=str(ax['kva_label'][kv.argmax()]),undervoltage_nodes=int((v<.95-tol).sum()),overvoltage_nodes=int((v>1.05+tol).sum()),line_violations=int((ll>1+tol).sum()),transformer_current_violations=int((tx>1+tol).sum()),transformer_kva_violations=int((kv>1+tol).sum()),native_P_scheduled_kw=float(a*md[t]*P.sum()),native_Q_scheduled_kvar=float(a*md[t]*Q.sum()),PV_scheduled_kw=float(a*ratio*mpv[t]*P.sum()),AIDC_P_scheduled_kw=float(ap[t].sum()),AIDC_Q_scheduled_kvar=float(aq[t].sum()))
            row['feasible_slot']=cv and cc and err is None and sum(row[k] for k in ['undervoltage_nodes','overvoltage_nodes','line_violations','transformer_current_violations','transformer_kva_violations'])==0
            rr.append(row);states.append(control_state(d,t))
            for j in range(12):d.Loads.Name(f'op8500_aidc{j+1:02d}');assert d.Loads.kW()==ap[t,j] and d.Loads.kvar()==aq[t,j]
        for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
        after=configs(d);drift=[n for n in adapted if after[n]!=adapted[n]];assert not drift
        summary=dict(alpha=a,feasible=all(r['feasible_slot'] for r in rr),converged_slots=sum(r['converged'] for r in rr),control_complete_slots=sum(r['control_actions_complete'] for r in rr),solver_error_slots=sum(r['solver_error'] is not None for r in rr),Vmin_pu=min(r['Vmin_pu'] for r in rr),Vmax_pu=max(r['Vmax_pu'] for r in rr),max_phase_line_loading_pu=max(r['max_phase_line_loading_pu'] for r in rr),max_transformer_phase_current_pu=max(r['max_transformer_phase_current_pu'] for r in rr),max_transformer_winding_kva_pu=max(r['max_transformer_winding_kva_pu'] for r in rr),undervoltage_nodes=sum(r['undervoltage_nodes'] for r in rr),overvoltage_nodes=sum(r['overvoltage_nodes'] for r in rr),line_violations=sum(r['line_violations'] for r in rr),transformer_current_violations=sum(r['transformer_current_violations'] for r in rr),transformer_kva_violations=sum(r['transformer_kva_violations'] for r in rr),explicit_snapshot_solves=96,fresh_engine_contexts=1,elapsed_seconds=time.perf_counter()-started)
        table(folder/'B0_96_SLOT_EXTREMA.csv',rr);save(folder/'B0_CONTROL_STATES_96.json',states);save(folder/'B0_SUMMARY.json',summary);save(folder/'STATIC_CONSERVATION_AUDIT.json',dict(status='PASS',elements_compared=len(adapted),unexpected_changes=drift,base_native_load_PQ_PF_restored=True,source_pu_1p05_all_slots=True,all_native_controlled_caps_and_controls_preserved=True,CAPBank3_disabled_all_slots=True,AIDC_PQ_input_max_error=0.,adapted_config_sha256=adapted_sha))
        np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,voltage_pu=np.array(vv),line_phase_axes=ax['line_label'],line_current_loading_pu=np.array(lines),transformer_current_axes=ax['tx_label'],transformer_current_loading_pu=np.array(tfs),transformer_kva_axes=ax['kva_label'],transformer_winding_kva_loading_pu=np.array(kvas))
        screen.append(summary);allrows.extend(rr);table(HERE/'ALPHA_SCREEN_TABLE.csv',screen);save(HERE/'ALPHA_SCREEN_TABLE.json',screen);d.Basic.ClearAll();print(json.dumps(summary),flush=True)
    feasible=[r for r in screen if r['feasible']];chosen=max(feasible,key=lambda r:r['alpha']) if feasible else None
    status='ADAPTED_B0_ALPHA8500_AUTHORITY_SELECTED' if chosen else 'NO_FEASIBLE_ALPHA_ON_FIXED_COMPATIBILITY_GRID'
    save(HERE/'ALPHA8500_AUTHORITY.json',dict(status=status,alpha8500=chosen['alpha'] if chosen else None,date='2025-05-21',canonical_IEEE8500_reproduction=False,model='User-fixed IEEE8500 reduced-load compatibility adaptation',rule_sha256=sha(HERE/'COMPATIBILITY_RULE.json'),pre_execution_freeze_sha256=sha(HERE/'PRE_EXECUTION_FREEZE_MANIFEST.json'),selected_summary=chosen,feasible_alphas=[r['alpha'] for r in feasible],screened_alphas=[r['alpha'] for r in screen],selection='Largest feasible alpha on the exact fixed 21-point grid; no tuning',selected_phase_arrays=record(HERE/'screen'/f'alpha_{chosen["alpha"]:.2f}'/'B0_ALL_PHASE_ARRAYS.npz') if chosen else None,B1_B2_B3_runs=0,additional_tuning=0))
    table(HERE/'B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv',allrows);print('COMPATIBILITY_SCREEN_COMPLETE '+status+' alpha='+str(chosen['alpha'] if chosen else None),flush=True)
if __name__=='__main__':main()
