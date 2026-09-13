import time
import numpy as np
from stress_common import *

def run_case(source,vreg,a,folder,data):
    folder.mkdir(parents=True,exist_ok=False);started=time.perf_counter();d=frozen.engine(folder/'runtime');native=old.configs(d);loads=frozen.native_inventory(d);ax=frozen.measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames());P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);md,mpv,ratio,ap,aq,inv=data
    d.Text.Command(f'Redirect "{overlay_path(source,vreg)}"');adapted=old.configs(d);audit=allowed_audit(native,adapted,source,vreg);save(folder/'PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json',audit)
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
        rows.append(extrema_row(source,a,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),err,arrays,nodes,ax,schedule));states.append(control_state(d,t,source,vreg));rows[-1]["vreg_V"]=vreg
        for j in range(12):d.Loads.Name(f'op8500_aidc{j+1:02d}');assert d.Loads.kW()==ap[t,j] and d.Loads.kvar()==aq[t,j]
    for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
    after=old.configs(d);drift=[n for n in adapted if after[n]!=adapted[n]];assert not drift
    save(folder/'STATIC_CONSERVATION_AUDIT.json',dict(status='PASS',elements_compared=len(adapted),unexpected_changes=drift,base_native_load_PQ_PF_restored=True,source_pu_all_slots=source,all_native_controlled_caps_and_controls_preserved=True,CAPBank3_disabled_all_slots=True,AIDC_PQ_input_max_error=0.,adapted_config_sha256=audit['adapted_config_sha256']))
    summary=summarize(source,a,rows,time.perf_counter()-started);table(folder/'B0_96_SLOT_EXTREMA.csv',rows);save(folder/'B0_CONTROL_STATES_96.json',states);save(folder/'B0_SUMMARY.json',summary)
    np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,line_phase_axes=ax['line_label'],transformer_current_axes=ax['tx_label'],transformer_kva_axes=ax['kva_label'],**{k:np.array(v) for k,v in zip(KEYS,values)})
    # Read-only reproduction check for the 15 common old/new grid cases.
    if vreg==125. and source in [1.045,1.04,1.035]:
        with np.load(PREV/'screen'/f'source_{source:.3f}'/f'alpha_{a:.2f}'/'B0_ALL_PHASE_ARRAYS.npz') as z:delta={k:float(np.max(np.abs(z[k]-np.array(v)))) for k,v in zip(KEYS,values)}
        save(folder/'PREVIOUS_125V_CASE_REPRODUCTION.json',dict(status='PASS' if max(delta.values())<=1e-10 else 'FAIL',max_absolute_differences=delta));assert max(delta.values())<=1e-10,delta
    d.Basic.ClearAll();print(json.dumps(summary),flush=True);return summary
