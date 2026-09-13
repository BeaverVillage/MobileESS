import os,sys,json,time,csv
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
import numpy as np
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;ROOT=H.parent;PREV=ROOT/'IEEE8500_production_compatibility_20260911'
sys.path.insert(0,str(PREV))
import screen_compatible_b0 as old
from control_telemetry import control_state
read,save,table,sha,record=old.read,old.save,old.table,old.sha,old.record
frozen=old.frozen;OLD=old.OLD;PCC=old.PCC
KEYS=['voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_winding_kva_loading_pu']
VIOLATIONS=['undervoltage_nodes','overvoltage_nodes','line_violations','transformer_current_violations','transformer_kva_violations']
def check_freeze():
    mf=H/'PRE_EXECUTION_FREEZE_MANIFEST.json';assert sha(mf)==(H/'PRE_EXECUTION_FREEZE_MANIFEST.sha256').read_text().split()[0]
    for r in read(mf)['bound_files']:assert sha(Path(r['path']))==r['sha256'],r['path']
def input_authorities():
    f=read(OLD/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');md=np.array(f['demand_mw_96'])/max(f['demand_mw_96']);mpv=np.array(f['pv_mw_96'])/max(f['pv_mw_96']);ratio=read(OLD/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio']
    with np.load(OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:ap=z['pcc'].copy();aq=z['qcc'].copy()
    return md,mpv,ratio,ap,aq,read(PCC/'PCC_OVERLAY_INVENTORY.json')
def allowed_audit(native,adapted,source):
    diffs=old.differences(native,adapted);expected={'regcontrol.feeder_rega','regcontrol.feeder_regb','regcontrol.feeder_regc'};seen=set();src=[]
    for r in diffs:
        n,k=r['element'],r['property'].lower()
        if n in expected:assert k=='vreg' and float(r['before'])==126.5 and float(r['after'])==125.;seen.add(n)
        elif n=='capacitor.capbank3':assert k in ['enabled','__element_enabled__']
        else:assert n=='vsource.source' and k=='pu' and float(r['before'])==1.05 and float(r['after'])==source;src.append(r)
    assert seen==expected and not adapted['capacitor.capbank3']['__element_enabled__'] and len(src)==int(source!=1.05)
    return dict(status='PASS',source_pu=source,exact_static_differences=diffs,native_config_sha256=frozen.digest(native),adapted_config_sha256=frozen.digest(adapted),additional_change_beyond_previous_stage='Vsource.source.pu only',canonical_reproduction=False)
def extrema_row(source,a,t,cv,cc,err,arrays,nodes,ax,scheduled):
    v,ll,tx,kv=arrays;tol=1e-9
    row=dict(source_pu=source,alpha=a,slot=t,converged=bool(cv),control_actions_complete=bool(cc),solver_error=err,Vmin_pu=float(v.min()),Vmin_node=str(nodes[v.argmin()]),Vmax_pu=float(v.max()),Vmax_node=str(nodes[v.argmax()]),max_phase_line_loading_pu=float(ll.max()),line_witness=str(ax['line_label'][ll.argmax()]),max_transformer_phase_current_pu=float(tx.max()),transformer_current_witness=str(ax['tx_label'][tx.argmax()]),max_transformer_winding_kva_pu=float(kv.max()),transformer_kva_witness=str(ax['kva_label'][kv.argmax()]),undervoltage_nodes=int((v<.95-tol).sum()),overvoltage_nodes=int((v>1.05+tol).sum()),line_violations=int((ll>1+tol).sum()),transformer_current_violations=int((tx>1+tol).sum()),transformer_kva_violations=int((kv>1+tol).sum()),**scheduled)
    row['feasible_slot']=bool(cv and cc and err is None and sum(row[k] for k in VIOLATIONS)==0);return row
def summarize(source,a,rows,elapsed):
    return dict(source_pu=source,alpha=a,feasible=all(r['feasible_slot'] for r in rows),converged_slots=sum(r['converged'] for r in rows),control_complete_slots=sum(r['control_actions_complete'] for r in rows),solver_error_slots=sum(r['solver_error'] is not None for r in rows),Vmin_pu=min(r['Vmin_pu'] for r in rows),Vmax_pu=max(r['Vmax_pu'] for r in rows),max_phase_line_loading_pu=max(r['max_phase_line_loading_pu'] for r in rows),max_transformer_phase_current_pu=max(r['max_transformer_phase_current_pu'] for r in rows),max_transformer_winding_kva_pu=max(r['max_transformer_winding_kva_pu'] for r in rows),**{k:sum(r[k] for r in rows) for k in VIOLATIONS},explicit_snapshot_solves=96,fresh_engine_contexts=1,elapsed_seconds=elapsed)
def run_case(source,a,folder,data):
    folder.mkdir(parents=True,exist_ok=False);started=time.perf_counter();d=frozen.engine(folder/'runtime');native=old.configs(d);loads=frozen.native_inventory(d);ax=frozen.measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames());P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);md,mpv,ratio,ap,aq,inv=data
    d.Text.Command(f'Redirect "{H / f"Source_{source:.3f}_Compatibility.dss"}"');adapted=old.configs(d);audit=allowed_audit(native,adapted,source);save(folder/'PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json',audit)
    assert frozen.add_resources(d,loads,ratio,inv)==(OLD/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8');after_add=old.configs(d);assert all(after_add[n]==adapted[n] for n in adapted)
    values=[[],[],[],[]];rows=[];states=[]
    for t in range(96):
        old.inputs(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t);err=None
        try:d.Solution.SolveSnap()
        except Exception as ex:
            if '#485' not in str(ex):raise
            err=str(ex)
        arrays=old.measure(d,ax);assert list(d.Circuit.AllNodeNames())==list(nodes)
        for vv,x in zip(values,arrays):vv.append(x)
        schedule=dict(native_P_scheduled_kw=float(a*md[t]*P.sum()),native_Q_scheduled_kvar=float(a*md[t]*Q.sum()),PV_scheduled_kw=float(a*ratio*mpv[t]*P.sum()),AIDC_P_scheduled_kw=float(ap[t].sum()),AIDC_Q_scheduled_kvar=float(aq[t].sum()))
        rows.append(extrema_row(source,a,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),err,arrays,nodes,ax,schedule));states.append(control_state(d,t,source))
        for j in range(12):d.Loads.Name(f'op8500_aidc{j+1:02d}');assert d.Loads.kW()==ap[t,j] and d.Loads.kvar()==aq[t,j]
    for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
    after=old.configs(d);drift=[n for n in adapted if after[n]!=adapted[n]];assert not drift
    save(folder/'STATIC_CONSERVATION_AUDIT.json',dict(status='PASS',elements_compared=len(adapted),unexpected_changes=drift,base_native_load_PQ_PF_restored=True,source_pu_all_slots=source,all_native_controlled_caps_and_controls_preserved=True,CAPBank3_disabled_all_slots=True,AIDC_PQ_input_max_error=0.,adapted_config_sha256=audit['adapted_config_sha256']))
    summary=summarize(source,a,rows,time.perf_counter()-started);table(folder/'B0_96_SLOT_EXTREMA.csv',rows);save(folder/'B0_CONTROL_STATES_96.json',states);save(folder/'B0_SUMMARY.json',summary)
    np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,line_phase_axes=ax['line_label'],transformer_current_axes=ax['tx_label'],transformer_kva_axes=ax['kva_label'],**{k:np.array(v) for k,v in zip(KEYS,values)})
    # Fresh 1.050 runs must reproduce the immutable preceding stage, not reuse it.
    if source==1.05:
        with np.load(PREV/'screen'/f'alpha_{a:.2f}'/'B0_ALL_PHASE_ARRAYS.npz') as z:delta={k:float(np.max(np.abs(z[k]-np.array(v)))) for k,v in zip(KEYS,values)}
        save(folder/'PREVIOUS_SOURCE_1P050_REPRODUCTION.json',dict(status='PASS' if max(delta.values())<=1e-10 else 'FAIL',max_absolute_differences=delta));assert max(delta.values())<=1e-10,delta
    d.Basic.ClearAll();print(json.dumps(summary),flush=True);return summary
def scan_source(source):
    data=input_authorities();rows=[]
    for a in read(H/'SOURCE_GRID_RULE.json')['alpha_grid_descending']:
        rows.append(run_case(source,a,H/'screen'/f'source_{source:.3f}'/f'alpha_{a:.2f}',data));table(H/'screen'/f'source_{source:.3f}'/'ALPHA_SCREEN_TABLE.csv',rows);save(H/'screen'/f'source_{source:.3f}'/'ALPHA_SCREEN_TABLE.json',rows)
    return rows
def main():
    check_freeze();rule=read(H/'SOURCE_GRID_RULE.json');assert not (H/'EXECUTION_START.json').exists();save(H/'EXECUTION_START.json',dict(utc=datetime.now(timezone.utc).isoformat(),pre_execution_manifest_sha256=sha(H/'PRE_EXECUTION_FREEZE_MANIFEST.json'),workers=5,source_grid=rule['source_grid_descending'],cases=105,chronological_slots_per_case=96))
    # Deterministic map ordering is source descending, regardless of worker timing.
    with ProcessPoolExecutor(max_workers=5) as pool:groups=list(pool.map(scan_source,rule['source_grid_descending']))
    screen=[r for g in groups for r in g];assert len(screen)==105;table(H/'SOURCE_ALPHA_SCREEN_TABLE.csv',screen);save(H/'SOURCE_ALPHA_SCREEN_TABLE.json',screen)
    good=[r for r in screen if r['feasible']];chosen=max(good,key=lambda r:(r['source_pu'],r['alpha'])) if good else None
    save(H/'PROVISIONAL_LEXICOGRAPHIC_SELECTION.json',dict(status='FEASIBLE_PAIR_PENDING_INDEPENDENT_REPLAY' if chosen else 'NO_FEASIBLE_PAIR_ON_FROZEN_SOURCE_ALPHA_GRID',final_authority=False,selected=chosen,feasible_pair_count=len(good),selection='lexicographic max(source_pu,alpha)',source_summary=[dict(source_pu=source,feasible_alphas=[r['alpha'] for r in screen if r['source_pu']==source and r['feasible']]) for source in rule['source_grid_descending']],B1_B2_B3_runs=0))
    allrows=[]
    for r in screen:
        with (H/'screen'/f'source_{r["source_pu"]:.3f}'/f'alpha_{r["alpha"]:.2f}'/'B0_96_SLOT_EXTREMA.csv').open(encoding='utf-8',newline='') as f:allrows.extend(csv.DictReader(f))
    table(H/'B0_10080_SLOT_EXTREMA.csv',allrows);print('GRID_COMPLETE',json.dumps(chosen),flush=True)
if __name__=='__main__':main()
