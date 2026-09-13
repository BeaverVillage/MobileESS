import sys, json, math
from pathlib import Path
from datetime import datetime, timezone
sys.dont_write_bytecode=True
import numpy as np
import screen_compatible_b0 as s
H=s.HERE
def scalar_current(d,label,transformer=False):
    name,term,bus,node=label.split('|');term=int(term[1:]);node=int(node[4:]);d.Circuit.SetActiveElement(name);nc=d.CktElement.NumConductors();order=d.CktElement.NodeOrder();positions=[i for i in range((term-1)*nc,term*nc) if order[i]==node];assert len(positions)==1
    amps=d.CktElement.CurrentsMagAng()[2*positions[0]]
    if transformer:
        d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(term);rating=d.Transformers.kVA()/d.Transformers.kV()/(math.sqrt(3) if d.CktElement.NumPhases()==3 else 1)
    else:d.Lines.Name(name.split('.',1)[1]);rating=d.Lines.NormAmps()
    return amps/rating
def scalar_kva(d,label):
    name,w,bus=label.split('|');w=int(w[1:]);d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(w);nc=d.CktElement.NumConductors();pw=np.array(d.CktElement.Powers()).reshape(-1,2)[(w-1)*nc:w*nc].sum(axis=0);return float(np.hypot(*pw)/d.Transformers.kVA())
def independent_selected_replay(authority):
    a=authority['alpha8500']
    if a is None:return dict(status='NOT_APPLICABLE_NO_FEASIBLE_ALPHA',extra_tuning=False)
    d=s.frozen.engine(H/'verification_runtime');loads=s.frozen.native_inventory(d);ax=s.frozen.measurement_axes(d);d.Text.Command(f'Redirect "{H / "IEEE8500_Compatibility_Adaptation.dss"}"')
    f=s.read(s.OLD/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');md=np.array(f['demand_mw_96'])/max(f['demand_mw_96']);mpv=np.array(f['pv_mw_96'])/max(f['pv_mw_96']);ratio=s.read(s.OLD/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio'];inv=s.read(s.PCC/'PCC_OVERLAY_INVENTORY.json');s.frozen.add_resources(d,loads,ratio,inv)
    P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads])
    with np.load(s.OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:ap=z['pcc'].copy();aq=z['qcc'].copy()
    saved=np.load(H/'screen'/f'alpha_{a:.2f}'/'B0_ALL_PHASE_ARRAYS.npz');keys=['voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_winding_kva_loading_pu'];diffs={k:0. for k in keys};scalar=[]
    witnesses={k:np.unravel_index(saved[k].argmax(),saved[k].shape) for k in keys};witnesses['voltage_min']=np.unravel_index(saved['voltage_pu'].argmin(),saved['voltage_pu'].shape)
    for t in range(96):
        s.inputs(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t);d.Solution.SolveSnap();assert d.Solution.Converged() and d.Solution.ControlActionsDone()
        arrays=s.measure(d,ax)
        for k,v in zip(keys,arrays):diffs[k]=max(diffs[k],float(np.max(np.abs(v-saved[k][t]))))
        s.control_state(d,t)
        for k,(slot,i) in witnesses.items():
            if t!=slot:continue
            key='voltage_pu' if k=='voltage_min' else k;expected=float(saved[key][t,i])
            if key=='voltage_pu':
                node=str(saved['node_names'][i]);bus,ph=node.rsplit('.',1);d.Circuit.SetActiveBus(bus);j=d.Bus.Nodes().index(int(ph));value=d.Bus.puVmagAngle()[2*j];label=node
            elif key=='line_current_loading_pu':label=str(saved['line_phase_axes'][i]);value=scalar_current(d,label)
            elif key=='transformer_current_loading_pu':label=str(saved['transformer_current_axes'][i]);value=scalar_current(d,label,True)
            else:label=str(saved['transformer_kva_axes'][i]);value=scalar_kva(d,label)
            scalar.append(dict(metric=k,slot=int(t),axis=label,saved=expected,scalar_API=value,absolute_difference=abs(value-expected)))
    assert max(diffs.values())<1e-10 and max(x['absolute_difference'] for x in scalar)<1e-10
    d.Basic.ClearAll();return dict(status='PASS',alpha=a,chronological_slots=96,max_absolute_array_differences=diffs,independent_scalar_global_witness_checks=scalar)
def main():
    s.check_freeze();authority=s.read(H/'ALPHA8500_AUTHORITY.json');rows=s.read(H/'ALPHA_SCREEN_TABLE.json');rule=s.read(H/'COMPATIBILITY_RULE.json');assert [r['alpha'] for r in rows]==rule['alpha_grid_descending']
    candidates=[r['alpha'] for r in rows if r['feasible']];assert authority['alpha8500']==(max(candidates) if candidates else None)
    for r in rows:
        folder=H/'screen'/f'alpha_{r["alpha"]:.2f}';assert s.read(folder/'STATIC_CONSERVATION_AUDIT.json')['status']=='PASS';states=s.read(folder/'B0_CONTROL_STATES_96.json');assert len(states)==96
        with np.load(folder/'B0_ALL_PHASE_ARRAYS.npz') as z:
            vals=[z[k] for k in ['voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_winding_kva_loading_pu']];assert all(v.shape[0]==96 for v in vals)
            feasible=r['converged_slots']==96 and r['control_complete_slots']==96 and r['solver_error_slots']==0 and vals[0].min()>=.95-1e-9 and vals[0].max()<=1.05+1e-9 and all(v.max()<=1+1e-9 for v in vals[1:]);assert bool(feasible)==r['feasible']
    verification=independent_selected_replay(authority);s.save(H/'INDEPENDENT_SELECTED_ALPHA_VERIFICATION.json',verification)
    protected=s.read(H/'PROTECTED_AUTHORITIES_BEFORE.json');changed=[r['path'] for r in protected if s.record(Path(r['path']))!=r];assert not changed
    s.check_freeze();s.save(H/'IMMUTABILITY_FINAL_AUDIT.json',dict(status='PASS',protected_files=len(protected),SHA256_size_mtime_unchanged=True,changed_files=changed,pre_execution_bindings_unchanged=True))
    report=['# IEEE8500 production operating-point compatibility B0 screen','',f'**{authority["status"]}**',f'','Selected date: **2025-05-21**. Selected alpha8500: **'+str(authority['alpha8500'])+'**.','', 'This is a user-fixed compatibility adaptation for the reduced-load IEEE8500 operating point and the 0.95–1.05 pu study envelope. It is **not canonical IEEE8500 reproduction**.','', 'Only FEEDER_REGA/B/C Vreg changes from 126.5 V to 125.0 V, and uncontrolled fixed CAPBank3 is out of service. Source pu=1.05, PT ratio=60, band=2 V, tap limits, all nine controlled capacitor phases and their CapControls, native topology/impedance/ratings, 24 locations, PCC transformers, and AIDC/MESS scales remain unchanged.','', 'Rule, code and all previous source/PCC/topology/input/evidence hashes were frozen before execution. Every alpha uses a fresh OpenDSS context with 96 chronological snapshots and accepted control-state carry-forward. No EventLog properties were edited. Only the unchanged D-1 demand/PV forecasts, frozen B0 exogenous PV ratio and AIDC P/Q inputs are used. MESS injections remain zero.','', '| alpha | feasible | converged/controls | Vmin | Vmax | line I pu | transformer phase I pu | transformer winding kVA pu |','|---:|:---:|:---:|---:|---:|---:|---:|---:|']
    for r in rows:report.append(f'| {r["alpha"]:.2f} | {r["feasible"]} | {r["converged_slots"]}/{r["control_complete_slots"]} | {r["Vmin_pu"]:.9f} | {r["Vmax_pu"]:.9f} | {r["max_phase_line_loading_pu"]:.9f} | {r["max_transformer_phase_current_pu"]:.9f} | {r["max_transformer_winding_kva_pu"]:.9f} |')
    report.extend(['','Limits: 0.95≤V≤1.05 pu and line/transformer phase-current/transformer winding-kVA loading ≤1.0 pu, unchanged numerical boundary tolerance 1e-9. All 8639 nodes, both line terminals and every transformer winding are included. Voltage/thermal violations and unconverged or unsettled slots fail feasibility. The largest feasible value is selected from all 21 fixed grid values; there is no grid refinement or tuning.','',f'Independent selected-alpha replay: **{verification["status"]}**. All 21 saved phase-array sets independently reproduce the recorded feasibility decisions. All {len(protected)} previous evidence files retain SHA256, size and modification time.','', 'The original NO_FEASIBLE_ALPHA_ON_FROZEN_GRID and NATIVE_VOLTAGE_CONTROL_COMPATIBILITY_MISMATCH evidence remain intact, including native alpha=0 Vmax>1.05. New adapted results do not replace or relabel those native findings.','', 'B1/B2/B3 runs: **0**. Additional setpoint/source/capacitor tuning or resource rescaling: **0**. '+('A feasible B0 operating point has been frozen; no optimization is executed in this task.' if candidates else 'No feasible alpha exists under the fixed rule; stop here without additional changes.'),'','Artifacts: ALPHA8500_AUTHORITY.json, ALPHA_SCREEN_TABLE.csv, B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv, screen/alpha_*/B0_ALL_PHASE_ARRAYS.npz, screen/alpha_*/B0_CONTROL_STATES_96.json, PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json, INDEPENDENT_SELECTED_ALPHA_VERIFICATION.json, IMMUTABILITY_FINAL_AUDIT.json, PRE_EXECUTION_FREEZE_MANIFEST.json.'])
    (H/'IEEE8500_COMPATIBILITY_B0_REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    files=[dict(path=str(p.relative_to(H)),sha256=s.sha(p),bytes=p.stat().st_size) for p in sorted(H.rglob('*')) if p.is_file() and p.name not in ['COMPATIBILITY_EVIDENCE_FREEZE_MANIFEST.json','COMPATIBILITY_EVIDENCE_FREEZE_MANIFEST.sha256']]
    mf=H/'COMPATIBILITY_EVIDENCE_FREEZE_MANIFEST.json';assert not mf.exists();s.save(mf,dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),status=authority['status'],alpha8500=authority['alpha8500'],canonical_reproduction=False,pre_execution_manifest_sha256=s.sha(H/'PRE_EXECUTION_FREEZE_MANIFEST.json'),protected_files_unchanged=len(protected),B0_screen_slots=2016,selected_alpha_verification=verification['status'],B1_B2_B3_runs=0,files=files));(H/'COMPATIBILITY_EVIDENCE_FREEZE_MANIFEST.sha256').write_text(s.sha(mf)+'  '+mf.name+'\n',encoding='ascii');print('FINAL_FREEZE_COMPLETE',authority['alpha8500'],s.sha(mf),flush=True)
if __name__=='__main__':main()
