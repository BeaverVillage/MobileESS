"""Separate clean replay with scalar bus/element measurement, no bulk PDE metrics."""
import sys,math,time
import numpy as np
sys.dont_write_bytecode=True
import screen_source_grid as s
H=s.H
def scalar_plan(d):
    line_labels=[];tx_labels=[];kva_labels=[];plans=[]
    for name in d.PDElements.AllNames():
        d.Circuit.SetActiveElement(name)
        if not d.CktElement.Enabled():continue
        kind=name.split('.')[0].lower()
        if kind not in ('line','transformer'):continue
        nc=d.CktElement.NumConductors();nt=d.CktElement.NumTerminals();nodes=list(d.CktElement.NodeOrder());buses=list(d.CktElement.BusNames());ph=d.CktElement.NumPhases();ix=[];ratings=[];kr=[]
        if kind=='line':d.Lines.Name(name.split('.',1)[1]);rating=d.Lines.NormAmps()
        for term in range(nt):
            if kind=='transformer':
                d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(term+1);kva=d.Transformers.kVA();rating=kva/d.Transformers.kV()/(math.sqrt(3) if ph==3 else 1);kr.append(kva);kva_labels.append(f'{name}|w{term+1}|{buses[term]}')
            for c in range(nc):
                node=nodes[term*nc+c]
                if node==0:continue
                ix.append(term*nc+c);ratings.append(rating);label=f'{name}|t{term+1}|{buses[term]}|node{node}'
                (line_labels if kind=='line' else tx_labels).append(label)
        plans.append(dict(name=name,kind=kind,nc=nc,nt=nt,positions=np.array(ix),ratings=np.array(ratings),kva_ratings=np.array(kr)))
    return dict(plans=plans,bus_names=list(d.Circuit.AllBusNames()),node_names=np.array(d.Circuit.AllNodeNames()),line_label=np.array(line_labels),tx_label=np.array(tx_labels),kva_label=np.array(kva_labels))
def scalar_measure(d,plan):
    node_voltage={};lines=[];currents=[];kvas=[]
    for bus in plan['bus_names']:
        d.Circuit.SetActiveBus(bus);phases=list(d.Bus.Nodes());v=np.asarray(d.Bus.puVmagAngle())[::2];assert len(phases)==len(v)
        node_voltage.update({f'{bus}.{node}':value for node,value in zip(phases,v)})
    voltage=np.array([node_voltage[str(n)] for n in plan['node_names']])
    for r in plan['plans']:
        d.Circuit.SetActiveElement(r['name']);amps=np.asarray(d.CktElement.CurrentsMagAng())[::2];v=amps[r['positions']]/r['ratings']
        if r['kind']=='line':lines.extend(v)
        else:
            currents.extend(v);pq=np.asarray(d.CktElement.Powers()).reshape(r['nt'],r['nc'],2).sum(axis=1);kvas.extend(np.hypot(pq[:,0],pq[:,1])/r['kva_ratings'])
    arrays=[voltage,np.array(lines),np.array(currents),np.array(kvas)];assert all(np.isfinite(x).all() for x in arrays);return arrays
def set_inputs_independently(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t):
    d.Solution.LoadMult(1.);d.Solution.Hour(t//4);d.Solution.Seconds(900*(t%4))
    for i,r in enumerate(loads):
        p=float(P[i]*float(a*md[t]));q=float(Q[i]*float(a*md[t]));d.Loads.Name(r['load']);d.Loads.kW(p);d.Loads.kvar(q)
        assert d.Loads.kW()==p and d.Loads.kvar()==q
        if p>0:assert abs(d.Loads.PF()-r['base_pf'])<1e-12
        pv=float(a*ratio*P[i]*mpv[t]);d.Generators.Name(f'op8500_pv_{i:04d}');d.CktElement.Enabled(pv>0)
        if pv>0:d.Generators.kW(pv);d.Generators.kvar(0.)
    for i in range(12):d.Loads.Name(f'op8500_aidc{i+1:02d}');d.Loads.kW(float(ap[t,i]));d.Loads.kvar(float(aq[t,i]))
def main():
    s.check_freeze();selection=s.read(H/'PROVISIONAL_LEXICOGRAPHIC_SELECTION.json');chosen=selection['selected']
    if chosen is None:
        s.save(H/'INDEPENDENT_REPLAY_VERIFICATION.json',dict(status='NOT_APPLICABLE_NO_FEASIBLE_PAIR',simulation_slots=0,additional_tuning=False));print('NO_FEASIBLE_PAIR_STOP');return
    source,a=chosen['source_pu'],chosen['alpha'];folder=H/'independent_replay';folder.mkdir(exist_ok=False);started=time.perf_counter()
    d=s.frozen.engine(folder/'runtime');native=s.old.configs(d);loads=s.frozen.native_inventory(d);plan=scalar_plan(d);d.Text.Command(f'Redirect "{H / f"Source_{source:.3f}_Compatibility.dss"}"');adapted=s.old.configs(d);s.save(folder/'PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json',s.allowed_audit(native,adapted,source))
    md,mpv,ratio,ap,aq,inv=s.input_authorities();P=np.array([r['base_kw'] for r in loads]);Q=np.array([r['base_kvar'] for r in loads]);assert s.frozen.add_resources(d,loads,ratio,inv)==(s.OLD/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8')
    case=H/'screen'/f'source_{source:.3f}'/f'alpha_{a:.2f}';saved=np.load(case/'B0_ALL_PHASE_ARRAYS.npz');expected_states=s.read(case/'B0_CONTROL_STATES_96.json')
    for key,plan_key in [('node_names','node_names'),('line_phase_axes','line_label'),('transformer_current_axes','tx_label'),('transformer_kva_axes','kva_label')]:assert np.array_equal(saved[key],plan[plan_key]),key
    values=[[],[],[],[]];rows=[];states=[];diffs={k:0. for k in s.KEYS};state_differences=[]
    for t in range(96):
        set_inputs_independently(d,loads,P,Q,ap,aq,a,md,mpv,ratio,t);err=None
        try:d.Solution.SolveSnap()
        except Exception as ex:
            if '#485' not in str(ex):raise
            err=str(ex)
        arrays=scalar_measure(d,plan)
        for k,x,v in zip(s.KEYS,arrays,values):v.append(x);diffs[k]=max(diffs[k],float(np.max(np.abs(x-saved[k][t]))))
        rows.append(s.extrema_row(source,a,t,d.Solution.Converged(),d.Solution.ControlActionsDone(),err,arrays,plan['node_names'],plan,{}));state=s.control_state(d,t,source);states.append(state)
        # Physical state comparison excludes iteration counters, which are solver telemetry.
        for key in ['source_pu','regulators','capacitors','capcontrols']:
            if state[key]!=expected_states[t][key]:state_differences.append(dict(slot=t,field=key))
        if (t+1)%24==0:print('INDEPENDENT_REPLAY',t+1,'/96',flush=True)
    for r in loads:d.Loads.Name(r['load']);d.Loads.kW(r['base_kw']);d.Loads.PF(r['base_pf'])
    after=s.old.configs(d);drift=[n for n in adapted if after[n]!=adapted[n]];assert not drift
    summary=s.summarize(source,a,rows,time.perf_counter()-started);s.save(folder/'B0_SUMMARY.json',summary);s.table(folder/'B0_96_SLOT_EXTREMA.csv',rows);s.save(folder/'B0_CONTROL_STATES_96.json',states)
    np.savez_compressed(folder/'B0_ALL_PHASE_ARRAYS.npz',node_names=plan['node_names'],line_phase_axes=plan['line_label'],transformer_current_axes=plan['tx_label'],transformer_kva_axes=plan['kva_label'],**{k:np.array(v) for k,v in zip(s.KEYS,values)})
    ok=summary['feasible'] and max(diffs.values())<=1e-10 and not state_differences
    s.save(H/'INDEPENDENT_REPLAY_VERIFICATION.json',dict(status='PASS' if ok else 'FAIL_STOP_NO_FINAL_AUTHORITY',source_pu=source,alpha8500=a,simulation_slots=96,separate_clean_process=True,fresh_context=True,measurement_method='Scalar bus puVmagAngle and per-element CurrentsMagAng/Powers; no bulk PDE metric API',max_absolute_phase_array_differences=diffs,physical_control_state_differences=state_differences,unexpected_static_changes=drift,summary=summary,production_tuning=False))
    d.Basic.ClearAll();print('INDEPENDENT_REPLAY_COMPLETE',ok,diffs,flush=True)
if __name__=='__main__':main()
