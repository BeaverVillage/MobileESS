import os,json,csv,math,time,hashlib
from pathlib import Path
from collections import defaultdict,deque,Counter
import numpy as np
import opendssdirect as odd
from select_date import HERE,ROOT,sha,rec

OVERLAY=ROOT/'IEEE8500_pcc_overlay_20260911'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(path,v):
    Path(path).parent.mkdir(exist_ok=True,parents=True)
    Path(path).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')
def table(path,rows):
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()})
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def engine(folder):
    folder.mkdir(exist_ok=True,parents=True)
    d=odd.NewContext();d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False);d.Basic.DataPath(str(folder))
    d.Text.Command(f'Compile "{OVERLAY / "Master_IEEE8500_PCC.dss"}"')
    assert d.Error.Number()==0 and d.Circuit.NumBuses()==4912 and d.Circuit.NumNodes()==8639
    d.Solution.MaxIterations(100);d.Solution.MaxControlIterations(1000)
    assert d.Solution.ControlMode()==0
    return d

def static_inputs(d):
    out={}
    # Dynamic tap positions/capacitor states are expected native-control outputs.
    for name in d.Circuit.AllElementNames():
        d.Circuit.SetActiveElement(name)
        if name.lower().startswith('transformer.'):
            d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(1)
        excluded={'wdgcurrents','tap','taps','tapnum','states'}
        if name.lower().startswith('reactor.'):excluded.update(['rmatrix','xmatrix'])
        if name.lower().startswith('capacitor.'):excluded.add('cmatrix')
        out[name.lower()]={k:d.Properties.Value(k) for k in d.CktElement.AllPropertyNames() if k.lower() not in excluded}
    return out

def native_inventory(d):
    rows=[];adj=defaultdict(set);secondary_phase={}
    for name in d.PDElements.AllNames():
        d.Circuit.SetActiveElement(name)
        if not d.CktElement.Enabled():continue
        buses=[b.split('.')[0].lower() for b in d.CktElement.BusNames()]
        for b in buses[1:]:
            if b!=buses[0]:adj[b].add(buses[0]);adj[buses[0]].add(b)
        if name.lower().startswith('transformer.'):
            d.Transformers.Name(name.split('.',1)[1])
            if d.Transformers.NumWindings()==3:
                nodes=d.CktElement.NodeOrder();phase='ABC'[nodes[0]-1]
                for b in buses[1:]:secondary_phase[b]=phase
    # Native secondary buses link via triplex lines to the center-tapped transformer.
    for name in d.Loads.AllNames():
        d.Loads.Name(name);bus=d.CktElement.BusNames()[0];base=bus.split('.')[0]
        queue=deque([base]);seen={base};phase=None
        while queue:
            b=queue.popleft()
            if b in secondary_phase:phase=secondary_phase[b];break
            for n in sorted(adj[b]-seen):seen.add(n);queue.append(n)
        assert phase in 'ABC'
        props={k:d.Properties.Value(k) for k in d.CktElement.AllPropertyNames()}
        assert props['Status'].lower() in ('variable','fixed') and props['Daily'].lower() in ('','none')
        rows.append(dict(load=name,bus_connection=bus,local_nodes=d.CktElement.NodeOrder(),phases=d.CktElement.NumPhases(),primary_phase=phase,connection='delta' if d.Loads.IsDelta() else 'wye',base_kv=d.Loads.kV(),base_kw=d.Loads.kW(),base_kvar=d.Loads.kvar(),base_pf=d.Loads.PF(),model=d.Loads.Model(),Vminpu=d.Loads.Vminpu(),Vmaxpu=d.Loads.Vmaxpu(),status=props['Status']))
    assert len(rows)==2354 and all(r['base_kw']>0 and r['phases']==1 for r in rows)
    return rows

def add_resources(d,loads,ratio,inventory):
    cmds=['! Separate B0 resource objects; existing authority files are referenced, never edited.']
    for i,r in enumerate(loads):
        peak=ratio*r['base_kw']
        cmd=f'New Generator.op8500_pv_{i:04d} phases={r["phases"]} bus1={r["bus_connection"]} conn={r["connection"]} kv={r["base_kv"]:.17g} kW={peak:.17g} kvar=0 kVA={peak:.17g} Model=1 Status=Fixed Vminpu={r["Vminpu"]:.17g} Vmaxpu={r["Vmaxpu"]:.17g} enabled=no'
        d.Text.Command(cmd);cmds.append(cmd)
    for r in inventory:
        if r['PCC_role']!='AIDC':continue
        cmd=f'New Load.op8500_{r["location_id"].lower()} phases=3 bus1={r["PCC_bus"]}.1.2.3 conn=wye kv=0.48 kW=0 kvar=0 Model=1 Vminpu=0.85 Vmaxpu=1.15 Status=Fixed'
        d.Text.Command(cmd);cmds.append(cmd)
    assert d.Loads.Count()==2366 and d.Generators.Count()==2354
    return '\n'.join(cmds)+'\n'

def measurement_axes(d):
    names=d.PDElements.AllNames();axes=[];line_pos=[];line_rating=[];line_label=[];tx_pos=[];tx_rating=[];tx_label=[];power_pos=[];power_group=[];kva_rating=[];kva_label=[];offset=0
    nc_api=d.PDElements.AllNumConductors();nt_api=d.PDElements.AllNumTerminals()
    for ei,name in enumerate(names):
        d.Circuit.SetActiveElement(name);nc=d.CktElement.NumConductors();nt=d.CktElement.NumTerminals()
        if not d.CktElement.Enabled():offset+=nc*nt;continue
        nodes=d.CktElement.NodeOrder();buses=d.CktElement.BusNames()
        assert nc==nc_api[ei] and nt==nt_api[ei]
        kind=name.split('.')[0].lower()
        if kind=='line':d.Lines.Name(name.split('.',1)[1]);rating=d.Lines.NormAmps();assert rating>0
        for term in range(nt):
            if kind=='transformer':
                d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(term+1);kv=d.Transformers.kV();kva=d.Transformers.kVA();ph=d.CktElement.NumPhases()
                rating=kva/(math.sqrt(3)*kv) if ph==3 else kva/kv
                assert kv>0 and kva>0 and ph in (1,3)
                group=len(kva_rating);kva_rating.append(kva);kva_label.append(f'{name}|w{term+1}|{buses[term]}')
                for c in range(nc):power_pos.append(offset+term*nc+c);power_group.append(group)
            for c in range(nc):
                node=nodes[term*nc+c];pos=offset+term*nc+c
                if node==0 or kind not in ('line','transformer'):continue
                label=f'{name}|t{term+1}|{buses[term]}|node{node}'
                axes.append(dict(kind=kind,element=name,terminal=term+1,bus_connection=buses[term],local_node=node,current_rating_A=rating,PDE_flat_conductor_index=pos))
                if kind=='line':line_pos.append(pos);line_rating.append(rating);line_label.append(label)
                else:tx_pos.append(pos);tx_rating.append(rating);tx_label.append(label)
        offset+=nc*nt
    return dict(line_pos=np.array(line_pos),line_rating=np.array(line_rating),line_label=np.array(line_label),tx_pos=np.array(tx_pos),tx_rating=np.array(tx_rating),tx_label=np.array(tx_label),power_pos=np.array(power_pos),power_group=np.array(power_group),kva_rating=np.array(kva_rating),kva_label=np.array(kva_label),flat_count=offset,rows=axes)

def main():
    start=time.perf_counter();spec=read(HERE/'OPERATING_POINT_PREREGISTRATION.json');f=read(HERE/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');ratio=read(HERE/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio'];inv=read(OVERLAY/'PCC_OVERLAY_INVENTORY.json')
    assert read(HERE/'FORECAST_CAUSALITY_AND_INPUT_BINDING.json')['status']=='PASS'
    with np.load(HERE/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:aidcp=z['pcc'].copy();aidcq=z['qcc'].copy()
    D=np.array(f['demand_mw_96']);pv=np.array(f['pv_mw_96']);md=D/D.max();mpv=pv/pv.max()
    aidcs=sorted([r for r in inv if r['PCC_role']=='AIDC'],key=lambda r:r['location_id']);assert len(aidcs)==12
    screen=[];selected=None;canonical=None;slots_all=[]
    for alpha in spec['alpha_grid_descending']:
        if screen:assert not screen[-1]['feasible']
        folder=HERE/'screen'/f'alpha_{alpha:.2f}';folder.mkdir(parents=True,exist_ok=False)
        d=engine(folder/'runtime');base=static_inputs(d);loads=native_inventory(d);P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);total=P.sum()
        if canonical is None:
            canonical=digest(base);table(HERE/'NATIVE_LOAD_AND_PV_ALLOCATION.csv',[dict(**r,PV_weight=r['base_kw']/total,PV_peak_kw_at_alpha1=ratio*r['base_kw']) for r in loads])
            save(HERE/'NATIVE_STATIC_BASELINE_SHA256.json',dict(sha256=canonical,native_and_PCC_elements=len(base),excluded_dynamic_properties=['tap','taps','tapnum','states','wdgcurrents'],excluded_unused_matrix_properties=['Reactor RMatrix/XMatrix','Capacitor CMatrix']))
        else:assert canonical==digest(base)
        ax=measurement_axes(d);nodes=np.array(d.Circuit.AllNodeNames());n=len(nodes);assert n==8639
        resource_text=add_resources(d,loads,ratio,inv)
        after=static_inputs(d);assert all(after[n]==v for n,v in base.items())
        if not (HERE/'B0_RESOURCE_OBJECTS.dss').exists():
            (HERE/'B0_RESOURCE_OBJECTS.dss').write_text(resource_text,encoding='utf-8')
            (HERE/'Master_IEEE8500_B0_OperatingPoint.dss').write_text(f'Compile "{OVERLAY / "Master_IEEE8500_PCC.dss"}"\nRedirect "{HERE / "B0_RESOURCE_OBJECTS.dss"}"\n! No Solve: use run_b0_screen.py for frozen 96-slot inputs.\n',encoding='utf-8')
        else:assert (HERE/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8')==resource_text
        if alpha==1:
            table(HERE/'HARD_LIMIT_CURRENT_AXES.csv',ax['rows'])
            table(HERE/'HARD_LIMIT_TRANSFORMER_KVA_AXES.csv',[dict(winding_terminal=s,nameplate_kva=float(k)) for s,k in zip(ax['kva_label'],ax['kva_rating'])])
            save(HERE/'PREFLIGHT_INPUT_FREEZE.json',dict(specification=rec(HERE/'OPERATING_POINT_PREREGISTRATION.json'),date=rec(HERE/'SELECTED_DATE_FREEZE.json'),forecast=rec(HERE/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json'),PV_ratio=rec(HERE/'PV_PENETRATION_RATIO_AUTHORITY.json'),AIDC=rec(HERE/'V41R4_B0_AIDC_POWER_UNCHANGED.npz'),resources=rec(HERE/'B0_RESOURCE_OBJECTS.dss'),allocation=rec(HERE/'NATIVE_LOAD_AND_PV_ALLOCATION.csv'),native_base_kw=float(total),native_base_kvar=float(Q.sum()),engine=d.Basic.Version()))
        vv=np.empty((96,n));ll=np.empty((96,len(ax['line_pos'])));tt=np.empty((96,len(ax['tx_pos'])));kk=np.empty((96,len(ax['kva_rating'])));rows=[];states=[];readback=[];tol=1e-9
        tstart=time.perf_counter()
        for t in range(96):
            factor=float(alpha*md[t]);d.Solution.LoadMult(1.);d.Solution.Hour(t//4);d.Solution.Seconds((t%4)*900)
            for i,r in enumerate(loads):
                d.Loads.Name(r['load']);d.Loads.kW(float(factor*P[i]));d.Loads.kvar(float(factor*Q[i]))
                assert abs(d.Loads.kW()-factor*P[i])<1e-12 and abs(d.Loads.kvar()-factor*Q[i])<1e-12
                if factor>0:assert abs(d.Loads.PF()-r['base_pf'])<1e-12
                d.Generators.Name(f'op8500_pv_{i:04d}');value=float(alpha*ratio*P[i]*mpv[t]);d.CktElement.Enabled(value>0)
                if value>0:d.Generators.kW(value);d.Generators.kvar(0.)
            for j,r in enumerate(aidcs):
                d.Loads.Name('op8500_'+r['location_id'].lower());d.Loads.kW(float(aidcp[t,j]));d.Loads.kvar(float(aidcq[t,j]))
            d.Solution.SolveSnap();converged=bool(d.Solution.Converged());controls_done=bool(d.Solution.ControlActionsDone());err=d.Error.Number()
            if err:raise RuntimeError(f'OpenDSS error {err}, alpha={alpha}, slot={t}')
            vv[t]=d.Circuit.AllBusMagPu();raw=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)[:,0];powers=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
            assert len(raw)==len(powers)==ax['flat_count']
            ll[t]=raw[ax['line_pos']]/ax['line_rating'];tt[t]=raw[ax['tx_pos']]/ax['tx_rating']
            sp=np.bincount(ax['power_group'],weights=powers[ax['power_pos'],0]);sq=np.bincount(ax['power_group'],weights=powers[ax['power_pos'],1]);kk[t]=np.hypot(sp,sq)/ax['kva_rating']
            assert all(np.isfinite(a[t]).all() for a in [vv,ll,tt,kk])
            r=dict(alpha=alpha,slot=t,converged=converged,native_control_actions_done=controls_done,voltage_min_pu=float(vv[t].min()),voltage_min_node=str(nodes[vv[t].argmin()]),voltage_max_pu=float(vv[t].max()),voltage_max_node=str(nodes[vv[t].argmax()]),line_phase_current_max_pu=float(ll[t].max()),line_max_asset=str(ax['line_label'][ll[t].argmax()]),transformer_phase_current_max_pu=float(tt[t].max()),transformer_current_max_asset=str(ax['tx_label'][tt[t].argmax()]),transformer_total_kva_max_pu=float(kk[t].max()),transformer_kva_max_asset=str(ax['kva_label'][kk[t].argmax()]),voltage_violations=int(((vv[t]<.95-tol)|(vv[t]>1.05+tol)).sum()),line_current_violations=int((ll[t]>1+tol).sum()),transformer_current_violations=int((tt[t]>1+tol).sum()),transformer_kva_violations=int((kk[t]>1+tol).sum()),native_demand_multiplier=factor,native_P_scheduled_kw=float(factor*total),native_Q_scheduled_kvar=float(factor*Q.sum()),PV_scheduled_kw=float(alpha*ratio*total*mpv[t]),AIDC_P_scheduled_kw=float(aidcp[t].sum()),AIDC_Q_scheduled_kvar=float(aidcq[t].sum()))
            rows.append(r)
            taps=[]
            for rn in d.RegControls.AllNames():d.RegControls.Name(rn);taps.append(int(d.RegControls.TapNumber()))
            caps=[]
            for cn in d.Capacitors.AllNames():d.Capacitors.Name(cn);caps.append(list(d.Capacitors.States()))
            states.append(dict(slot=t,regcontrol_names=d.RegControls.AllNames(),tap_numbers=taps,capacitor_names=d.Capacitors.AllNames(),capacitor_states=caps,control_iterations=d.Solution.ControlIterations(),powerflow_iterations=d.Solution.Iterations()))
            pe=qe=0.;actual_p=actual_q=0.
            for j,a in enumerate(aidcs):
                d.Loads.Name('op8500_'+a['location_id'].lower());assert d.Loads.kW()==aidcp[t,j] and d.Loads.kvar()==aidcq[t,j]
                aP=np.asarray(d.CktElement.Powers()).reshape(-1,2).sum(axis=0);pe=max(pe,abs(aP[0]-aidcp[t,j]));qe=max(qe,abs(aP[1]-aidcq[t,j]));actual_p+=aP[0];actual_q+=aP[1]
            readback.append(dict(slot=t,scheduled_P_kw=float(aidcp[t].sum()),physical_P_kw=float(actual_p),scheduled_Q_kvar=float(aidcq[t].sum()),physical_Q_kvar=float(actual_q),max_site_P_readback_error_kw=float(pe),max_site_Q_readback_error_kvar=float(qe),AIDC_fixed_status_excludes_native_LoadMult=True))
            if t%24==23:print(f'alpha={alpha:.2f} slots={t+1}/96',flush=True)
        # Restore only nominal scheduled P/Q to prove static definitions were conserved.
        for r in loads:
            d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
        final=static_inputs(d);diff=[n for n in base if final[n]!=base[n]]
        save(folder/'NATIVE_STATIC_DEFINITION_AUDIT.json',dict(native_and_PCC_elements_compared=len(base),changed_definitions=diff,static_definition_SHA_before=digest(base),static_definition_SHA_after=digest({n:final[n] for n in base}),tap_cap_states_allowed_to_evolve=True));assert not diff
        feasible=all(r['converged'] and r['native_control_actions_done'] and not sum(r[k] for k in ['voltage_violations','line_current_violations','transformer_current_violations','transformer_kva_violations']) for r in rows)
        summary=dict(alpha=alpha,feasible=feasible,converged_slots=sum(r['converged'] for r in rows),native_control_complete_slots=sum(r['native_control_actions_done'] for r in rows),voltage_min_pu=float(vv.min()),voltage_max_pu=float(vv.max()),max_phase_line_loading_pu=float(ll.max()),max_transformer_phase_current_pu=float(tt.max()),max_transformer_total_kva_pu=float(kk.max()),voltage_violation_rows=sum(r['voltage_violations'] for r in rows),line_current_violation_rows=sum(r['line_current_violations'] for r in rows),transformer_current_violation_rows=sum(r['transformer_current_violations'] for r in rows),transformer_kva_violation_rows=sum(r['transformer_kva_violations'] for r in rows),solve_count=96,fresh_engine_count=1,elapsed_seconds=time.perf_counter()-tstart)
        table(folder/'B0_96_SLOT_EXTREMA.csv',rows);table(folder/'AIDC_PHYSICAL_READBACK.csv',readback);save(folder/'NATIVE_CONTROL_STATES_96.json',states);save(folder/'B0_SUMMARY.json',summary)
        np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=nodes,voltage_pu=vv,line_phase_axes=ax['line_label'],line_current_loading_pu=ll,transformer_current_axes=ax['tx_label'],transformer_current_loading_pu=tt,transformer_kva_axes=ax['kva_label'],transformer_total_kva_loading_pu=kk)
        screen.append(summary);table(HERE/'ALPHA_SCREEN_TABLE.csv',screen);save(HERE/'ALPHA_SCREEN_TABLE.json',screen);print(json.dumps(summary),flush=True);d.Basic.ClearAll()
        if feasible:selected=alpha;break
    save(HERE/'SELECTED_ALPHA_AND_B0_STATUS.json',dict(status='B0_FEASIBLE_OPERATING_POINT_FROZEN' if selected is not None else 'NO_FEASIBLE_ALPHA_ON_FROZEN_GRID',selected_date='2025-05-21',selected_alpha=selected,screened_alphas=[r['alpha'] for r in screen],selection_rule='largest feasible on preregistered descending grid; null if none',B1_B2_B3_runs=0,optimization_calls=0,Actual_data_used=False,total_elapsed_seconds=time.perf_counter()-start))
    print('SCREEN_COMPLETE selected_alpha='+str(selected),flush=True)
if __name__=='__main__':main()
