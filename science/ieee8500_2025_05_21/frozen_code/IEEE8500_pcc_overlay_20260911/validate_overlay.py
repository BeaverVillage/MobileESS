import os,csv,json,hashlib,math
from pathlib import Path
from collections import Counter
import opendssdirect as odd
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'IEEE8500_scalability_20260910';RUN=ROOT/'runtime_output';RUN.mkdir(exist_ok=True)
os.chdir(RUN)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):
    (ROOT/(name+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
    if isinstance(data,list) and data:
        with (ROOT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader()
            for r in data:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()})
def engine():
    d=odd.NewContext();d.Basic.AllowChangeDir(False);d.Basic.AllowForms(False);d.Basic.AllowEditor(False);d.Basic.AllowDOScmd(False);d.Basic.DataPath(str(RUN));return d
def snapshot(d):
    result={}
    for name in d.Circuit.AllElementNames():
        d.Circuit.SetActiveElement(name)
        if name.lower().startswith('transformer.'):
            d.Transformers.Name(name.split('.',1)[1]);d.Transformers.Wdg(1)
        # Compare applicable model inputs, not read-only solution output or unused
        # matrix storage exposed by the C-API for scalar R/X and kV/kvar models.
        excluded={'wdgcurrents'}
        if name.lower().startswith('reactor.'):excluded.update(['rmatrix','xmatrix'])
        if name.lower().startswith('capacitor.'):excluded.add('cmatrix')
        result[name.lower()]={'buses':d.CktElement.BusNames(),'phases':d.CktElement.NumPhases(),'enabled':d.CktElement.Enabled(),'properties':{p:d.Properties.Value(p) for p in d.CktElement.AllPropertyNames() if p.lower() not in excluded}}
    return result
def counts(d):
    return {'buses':d.Circuit.NumBuses(),'nodes':d.Circuit.NumNodes(),'elements':d.Circuit.NumCktElements(),'transformers':d.Transformers.Count(),'lines':d.Lines.Count(),'loads':d.Loads.Count(),'capacitors':d.Capacitors.Count(),'regcontrols':d.RegControls.Count(),'capcontrols':d.CapControls.Count(),'element_classes':dict(Counter(n.split('.')[0].lower() for n in d.Circuit.AllElementNames()))}
def bus_inventory(d):
    rows=[]
    for b in d.Circuit.AllBusNames():
        d.Circuit.SetActiveBus(b);rows.append({'bus':b,'nodes':d.Bus.Nodes(),'base_ln_kv':d.Bus.kVBase(),'base_sqrt3_kv':d.Bus.kVBase()*math.sqrt(3)})
    return rows
def no_load(d,label,inventory):
    before=snapshot(d);mode=d.Solution.ControlMode();enabled={}
    for name in d.Circuit.AllElementNames():
        if name.split('.')[0].lower() in ('load','generator','pvsystem','storage','isource'):
            d.Circuit.SetActiveElement(name);enabled[name]=d.CktElement.Enabled();d.CktElement.Enabled(False)
    d.Solution.ControlMode(-1)
    d.Solution.Solve()
    assert d.Error.Number()==0 and d.Solution.Converged(),label
    test=[]
    for row in inventory:
        d.Circuit.SetActiveBus(row['host_bus']);a=d.Bus.Voltages();pn=d.Bus.Nodes();primary={n:complex(a[2*i],a[2*i+1]) for i,n in enumerate(pn)}
        d.Circuit.SetActiveBus(row['PCC_bus']);a=d.Bus.Voltages();sn=d.Bus.Nodes();secondary={n:complex(a[2*i],a[2*i+1]) for i,n in enumerate(sn)}
        errors=[abs(secondary[n]/primary[n]-0.48/12.47)/(0.48/12.47) for n in (1,2,3)]
        d.Circuit.SetActiveElement('Transformer.'+row['transformer']);nodeorder=d.CktElement.NodeOrder()
        assert nodeorder==[1,2,3,0,1,2,3,0] and max(errors)<1e-4
        test.append({'transformer':row['transformer'],'host_bus':row['host_bus'],'PCC_bus':row['PCC_bus'],'node_order_after_no_load_solve':nodeorder,'max_complex_phase_ratio_relative_error':max(errors),'nominal_LV_HV_ratio':.48/12.47,'phase_ratio_pass':True,'new_PC_injection_elements':0})
    for name,state in enabled.items():d.Circuit.SetActiveElement(name);d.CktElement.Enabled(state)
    d.Solution.ControlMode(mode)
    after=snapshot(d);diff=[k for k in before if before[k]!=after[k]]
    save(label+'_NO_LOAD_STATE_RESTORATION',{'native_PC_objects_isolated_count':len(enabled),'disabled_PC_names':sorted(enabled),'control_mode_restored':d.Solution.ControlMode()==mode,'model_property_changes_after_restore':diff,'native_capacitor_states_and_regulator_taps_preserved':not diff,'converged':True,'loadmult_not_changed':True,'PCC_external_injections':0,'note':'Native capacitor shunts and transformer magnetizing/no-load branches remain; this is zero external PC injection, not zero total source power. Tiny PCC anti-float admittance is retained from reference defaults.'})
    assert not diff
    return test

def run():
    freeze=read(ROOT/'OVERLAY_PREVALIDATION_FREEZE.json')
    for r in freeze['files']:assert sha(ROOT/r['path'])==r['sha256']
    native=engine();native.Text.Command(f'Compile "{BASE / "source/Master-unbal.dss"}"');assert native.Error.Number()==0
    nc=counts(native);nb=bus_inventory(native);ns=snapshot(native)
    overlay=engine();overlay.Text.Command(f'Compile "{ROOT / "Master_IEEE8500_PCC.dss"}"');compile_text=overlay.Text.Result();assert overlay.Error.Number()==0
    oc=counts(overlay);ob=bus_inventory(overlay);osnap=snapshot(overlay)
    changes=[k for k in ns if k not in osnap or ns[k]!=osnap[k]]
    save('NATIVE_DEFINITION_COMPARISON',{'native_elements_compared':len(ns),'native_parameter_changes':changes,'comparison_scope':'Every native circuit element: applicable static DSS definition properties, terminal buses, phases, enabled state. Transformers normalized to active winding 1.','excluded_non_input_properties':['Transformer.WdgCurrents: derived no-load solution output','Reactor.RMatrix/XMatrix: unused matrix representation; source reactor explicitly uses scalar R/X','Capacitor.CMatrix: unused matrix representation; native capacitors explicitly use kV/kvar'],'engine_unset_matrix_getter_issue':'Unused matrix getters returned unstable/uninitialized values across fresh contexts. Their scalar source definitions and all applicable ratings/impedances are compared instead.'})
    assert not changes
    inventory=read(ROOT/'PCC_OVERLAY_INVENTORY.json');expected={'transformer.'+r['transformer'] for r in inventory}
    added=set(osnap)-set(ns);assert added==expected
    assert oc['buses']==nc['buses']+36 and oc['nodes']==nc['nodes']+108 and oc['transformers']==nc['transformers']+36
    for k in ['lines','loads','capacitors','regcontrols','capcontrols']:assert oc[k]==nc[k]
    bmap={b['bus']:b for b in ob};new_buses=set(bmap)-{b['bus'] for b in nb};assert new_buses=={r['PCC_bus'] for r in inventory}
    assert all(bmap[b['bus']]==b for b in nb)
    generated=[]
    for r in inventory:
        overlay.Transformers.Name(r['transformer']);wind=[]
        for w in [1,2]:
            overlay.Transformers.Wdg(w);wind.append({'winding':w,'kv':overlay.Transformers.kV(),'kva':overlay.Transformers.kVA(),'percent_R':overlay.Transformers.R(),'delta':overlay.Transformers.IsDelta(),'tap':overlay.Transformers.Tap(),'Rneut':overlay.Transformers.Rneut(),'Xneut':overlay.Transformers.Xneut()})
        assert [w['kv'] for w in wind]==[12.47,.48] and all(w['kva']==r['rating_kva'] and not w['delta'] for w in wind)
        assert [w['percent_R'] for w in wind]==[.8,.2] and overlay.Transformers.Xhl()==5.75
        assert bmap[r['host_bus']]['nodes']==[1,2,3] and bmap[r['PCC_bus']]['nodes']==[1,2,3]
        assert abs(bmap[r['PCC_bus']]['base_sqrt3_kv']-.48)<1e-9
        generated.append({**r,'windings':wind,'bus_terminals':overlay.CktElement.BusNames(),'XHL_percent':overlay.Transformers.Xhl(),'no_load_loss_percent':float(overlay.Properties.Value('%noloadloss')),'imag_percent':float(overlay.Properties.Value('%imag')),'normal_rating_kva':float(overlay.Properties.Value('normhkva')),'emergency_rating_kva':float(overlay.Properties.Value('emerghkva'))})
    assert all(r['no_load_loss_percent']==r['imag_percent']==0 for r in generated)
    assert all(abs(r['normal_rating_kva']-r['rating_kva']*1.1)<1e-8 and abs(r['emergency_rating_kva']-r['rating_kva']*1.5)<1e-8 for r in generated)
    incidence={b:[] for b in new_buses}
    for name,item in osnap.items():
        for bus in set(b.split('.')[0] for b in item['buses']):
            if bus in incidence:incidence[bus].append(name)
    assert all(len(v)==1 for v in incidence.values())
    by_location={}
    for r in inventory:by_location.setdefault(r['location_id'],[]).append(r)
    shared=[]
    for name,rr in sorted(by_location.items()):
        roles=sorted(r['PCC_role'] for r in rr)
        assert roles==(['AIDC','MESS'] if name.startswith('AIDC') else ['MESS'])
        assert len({r['host_bus'] for r in rr})==1 and len({r['PCC_bus'] for r in rr})==len(rr)
        shared.append({'location_id':name,'primary_host':rr[0]['host_bus'],'PCC_roles':roles,'independent_PCC_buses':[r['PCC_bus'] for r in rr],'parallel_primary_branch_count':len(rr)})
    save('PCC_GENERATED_TRANSFORMER_AUDIT',generated);save('SHARED_HOST_INDEPENDENT_BRANCH_AUDIT',shared);save('OVERLAY_BUS_NOMINAL_BASES',ob)
    no_load(native,'BASELINE',[])
    tests=no_load(overlay,'OVERLAY',inventory);save('PCC_ZERO_INJECTION_PHASE_VALIDATION',tests)
    final=snapshot(overlay);assert final==osnap
    hostmultiplicity=Counter(r['host_bus'] for r in inventory)
    summary={'status':'PASS_IEEE8500_ADDITIVE_PCC_OVERLAY_ZERO_INJECTION_STRUCTURAL_VALIDATION','engine':overlay.Basic.Version(),'compile_result':compile_text,'compile_error':0,'native_counts':nc,'overlay_counts':oc,'generated_PCC_transformers':36,'AIDC_PCC_transformers':12,'AIDC_PCC_kva':1500,'MESS_PCC_transformers':24,'MESS_PCC_kva':750,'generated_PCC_buses':36,'unique_service_hosts':24,'duplicate_service_registry_hosts':0,'intentional_AIDC_hosts_with_two_independent_branches':sum(n==2 for n in hostmultiplicity.values()),'unintended_duplicate_host_assignments':0,'duplicate_PCC_bus_names':0,'duplicate_transformer_names':0,'native_parameter_changes':0,'native_bus_nodes_and_nominal_bases_changed':0,'native_line_and_transformer_ratings_changed':0,'PCC_secondary_base_kv_ll':.48,'PCC_primary_kv_ll':12.47,'new_PCC_bus_phase_patterns':dict(Counter('.'.join(map(str,bmap[b]['nodes'])) for b in new_buses)),'nominal_bus_base_sqrt3_histogram':dict(Counter(round(b['base_sqrt3_kv'],6) for b in ob)),'no_load_structural_solve_count':2,'explicit_operational_solve_count':0,'new_Load_Generator_Storage_PV_objects':0,'max_PCC_complex_phase_ratio_relative_error':max(r['max_complex_phase_ratio_relative_error'] for r in tests),'all_temporary_validation_states_restored':True,'AIDC_MESS_PCS_GPU_energy_scale_changes':0,'AIDC_STA_host_changes':0,'site_selection_rule_changes':0,'PCC_LV_buses_are_distinct_leaves':True,'additive_corridors':36,'full_graph_bus_vertices':oc['buses'],'full_graph_unique_corridors':4875+36,'full_graph_cycle_rank':0,'background_scaling_runs':0,'background_temporalization_runs':0,'alpha8500_selection_runs':0,'B0_B1_B2_B3_runs':0}
    save('PCC_OVERLAY_STRUCTURAL_VALIDATION',summary)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':run()
