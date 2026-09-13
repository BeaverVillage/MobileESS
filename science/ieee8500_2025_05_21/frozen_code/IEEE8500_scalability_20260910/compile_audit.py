"""Compile the byte-identical unbalanced master; no scenario or explicit Solve."""
import csv, hashlib, json, math, os
from collections import Counter, defaultdict, deque
from pathlib import Path
import opendssdirect as d

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'audit'
RUN = ROOT / 'runtime_output'
RUN.mkdir(exist_ok=True)
os.chdir(RUN)
d.Basic.AllowForms(False)
d.Basic.AllowEditor(False)
d.Basic.AllowDOScmd(False)
d.Basic.AllowChangeDir(False)
d.Basic.DataPath(str(RUN))
master = ROOT / 'source' / 'Master-unbal.dss'
# Compile resolves redirects relative to the master; output remains in runtime_output.
d.Text.Command(f'Compile "{master}"')
compile_result = d.Text.Result()
error = d.Error.Number()

def save(name, rows):
    (OUT/(name+'.json')).write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    if isinstance(rows,list) and rows:
        with (OUT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader()
            for row in rows:
                w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()})

def prop(name):
    return d.Properties.Value(name)

buses=[]
for b in d.Circuit.AllBusNames():
    d.Circuit.SetActiveBus(b)
    buses.append({'bus':b,'nodes':d.Bus.Nodes(),'kv_base_ln':d.Bus.kVBase(), 'kv_base_sqrt3':d.Bus.kVBase()*math.sqrt(3), 'coord_defined':d.Bus.Coorddefined(),'x':d.Bus.X(),'y':d.Bus.Y()})
bd={b['bus']:b for b in buses}
regs=[]
for n in d.RegControls.AllNames():
    d.RegControls.Name(n)
    regs.append({'name':n,'transformer':d.RegControls.Transformer(),'winding':d.RegControls.Winding(),'vreg':d.RegControls.ForwardVreg(),'band':d.RegControls.ForwardBand(),'ptratio':d.RegControls.PTRatio(),'tap_number_after_calcvoltagebases':d.RegControls.TapNumber()})
reg_names={r['transformer'] for r in regs}
xfmrs=[]
for n in d.Transformers.AllNames():
    d.Transformers.Name(n)
    row={'name':n,'phases':d.CktElement.NumPhases(),'buses':d.CktElement.BusNames(),'enabled':d.CktElement.Enabled(),'bank':prop('bank'),'sub':prop('sub'),'windings':[], 'is_regulator':n in reg_names}
    for w in range(1,d.Transformers.NumWindings()+1):
        d.Transformers.Wdg(w)
        row['windings'].append({'winding':w,'kv':d.Transformers.kV(),'kva':d.Transformers.kVA(),'delta':d.Transformers.IsDelta(),'tap':d.Transformers.Tap()})
    xfmrs.append(row)
caps=[]
for n in d.Capacitors.AllNames():
    d.Capacitors.Name(n)
    caps.append({'name':n,'buses':d.CktElement.BusNames(),'phases':d.CktElement.NumPhases(),'kv':d.Capacitors.kV(),'kvar':d.Capacitors.kvar(),'states':d.Capacitors.States()})
capcontrols=[]
for n in d.CapControls.AllNames():
    d.CapControls.Name(n)
    capcontrols.append({'name':n,'capacitor':d.CapControls.Capacitor(),'monitored_obj':d.CapControls.MonitoredObj(),'mode':int(d.CapControls.Mode()),'on':d.CapControls.ONSetting(),'off':d.CapControls.OFFSetting()})
edges=[]
lines=[]
for n in d.Lines.AllNames():
    d.Lines.Name(n)
    buses_raw=d.CktElement.BusNames()
    row={'name':n,'bus1':buses_raw[0],'bus2':buses_raw[1],'phases':d.Lines.Phases(),'length':d.Lines.Length(),'units':int(d.Lines.Units()),'linecode':d.Lines.LineCode(),'switch':d.Lines.IsSwitch(),'enabled':d.CktElement.Enabled(),'any_open':any(d.CktElement.IsOpen(t,c) for t in (1,2) for c in range(1,d.CktElement.NumConductors()+1)), 'r1':d.Lines.R1(),'x1':d.Lines.X1(),'r_matrix':d.Lines.RMatrix(),'x_matrix':d.Lines.XMatrix()}
    lines.append(row)
    if row['enabled'] and not row['any_open']:
        edges.append({'element':'line.'+n,'u':buses_raw[0].split('.')[0],'v':buses_raw[1].split('.')[0],'kind':'line','phases':row['phases']})
for row in xfmrs:
    bs=list(dict.fromkeys(b.split('.')[0] for b in row['buses']))
    if row['enabled']:
        for b in bs[1:]:
            edges.append({'element':'transformer.'+row['name'],'u':bs[0],'v':b,'kind':'regulator' if row['is_regulator'] else 'transformer','phases':row['phases']})
for el in d.Circuit.AllElementNames():
    if el.lower().startswith('reactor.'):
        d.Circuit.SetActiveElement(el)
        bs=[b.split('.')[0] for b in d.CktElement.BusNames()]
        if len(bs)==2 and bs[0]!=bs[1]:
            edges.append({'element':el,'u':bs[0],'v':bs[1],'kind':'reactor','phases':d.CktElement.NumPhases()})

adj=defaultdict(set)
pairs=defaultdict(list)
for e in edges:
    if e['u']==e['v']: continue
    adj[e['u']].add(e['v']); adj[e['v']].add(e['u'])
    pairs[tuple(sorted((e['u'],e['v'])))].append(e['element'])
components=[]; seen=set()
for b in bd:
    if b in seen: continue
    comp=set([b]); q=[b];seen.add(b)
    while q:
        u=q.pop()
        for v in adj[u]:
            if v not in seen:seen.add(v);comp.add(v);q.append(v)
    components.append(comp)
root='sourcebus'; parent={root:None}; q=deque([root])
while q:
    u=q.popleft()
    for v in sorted(adj[u]):
        if v not in parent:parent[v]=u;q.append(v)
exclusion=set(['sourcebus'])
for x in xfmrs:
    if x['sub'].lower() in ('yes','true') or x['is_regulator']:
        exclusion.update(b.split('.')[0] for b in x['buses'])
exclusion.update(b for b in bd if 'hvmv_sub' in b or b.startswith('regxfmr_'))
# Three-phase connectivity must persist from the feeder head, not merely exist locally.
phase_adj=defaultdict(set)
for e in edges:
    if e['kind']=='line' and e['phases']==3:
        phase_adj[e['u']].add(e['v']);phase_adj[e['v']].add(e['u'])
line_by_name={'line.'+l['name']:l for l in lines}
for pair, elements in pairs.items():
    # Three separately modelled phase links are a complete ABC corridor.
    phase_pairs=set()
    for el in elements:
        if el in line_by_name:
            l=line_by_name[el]
            n1=l['bus1'].split('.')[1:] or list(map(str,range(1,l['phases']+1)))
            n2=l['bus2'].split('.')[1:] or list(map(str,range(1,l['phases']+1)))
            phase_pairs.update(zip(n1,n2))
    if {('1','1'),('2','2'),('3','3')}.issubset(phase_pairs):
        u,v=pair;phase_adj[u].add(v);phase_adj[v].add(u)
    rr=[x for x in xfmrs if 'transformer.'+x['name'] in elements and x['is_regulator']]
    if len(rr)==3 and {x['buses'][0].split('.')[1] for x in rr}=={'1','2','3'}:
        u,v=pair;phase_adj[u].add(v);phase_adj[v].add(u)
three_reach=set(['_hvmv_sub_lsb']);q=['_hvmv_sub_lsb']
while q:
    for v in phase_adj[q.pop()]:
        if v not in three_reach:three_reach.add(v);q.append(v)
for b in buses:
    reasons=[]
    if abs(b['kv_base_sqrt3']-12.47)>0.01247:reasons.append('not_12.47kV_primary')
    if set(b['nodes'])!={1,2,3}:reasons.append('not_exact_ABC')
    if b['bus'] in exclusion:reasons.append('source_substation_or_regulator_terminal')
    if b['bus'] not in three_reach:reasons.append('no_continuous_ABC_primary_path')
    if b['bus'] not in parent:reasons.append('unreachable')
    b['eligibility_exclusions']=reasons
    b['electrically_eligible']=not reasons
    b['selection_ready']=not reasons and b['coord_defined']
    b['parent_bus']=parent.get(b['bus'])

summary={'engine':d.Basic.Version(),'compile_command':f'Compile "{master}"','compile_result':compile_result,'error_number':error,'circuit':d.Circuit.Name(),'num_buses':d.Circuit.NumBuses(),'num_nodes':d.Circuit.NumNodes(),'num_elements':d.Circuit.NumCktElements(),'explicit_solve_commands':0,'calcvoltagebases_in_original_master':True,'load_flow_convergence_not_asserted':True,'scenario_runs':0,'aidc_count_planned':12,'aidc_hosts_selected':[], 'bus_node_patterns':dict(Counter('.'.join(map(str,b['nodes'])) for b in buses)),'bus_nominal_bases_ln':dict(Counter(round(b['kv_base_ln'],6) for b in buses)), 'bus_nominal_bases_sqrt3':dict(Counter(round(b['kv_base_sqrt3'],6) for b in buses)), 'line_count':len(lines),'line_phase_counts':dict(Counter(l['phases'] for l in lines)),'line_unit_counts':dict(Counter(l['units'] for l in lines)),'open_lines':sum(l['any_open'] for l in lines),'transformer_count':len(xfmrs),'transformer_phase_winding_counts':dict(Counter(f"{x['phases']}ph_{len(x['windings'])}wdg" for x in xfmrs)), 'regcontrol_count':len(regs),'regulator_banks':sorted(set(x['bank'] for x in xfmrs if x['is_regulator'])),'capacitor_objects':len(caps),'capacitor_kvar_total':sum(c['kvar'] for c in caps),'capacitor_distinct_buses':len(set(c['buses'][0].split('.')[0] for c in caps)),'capcontrol_count':len(capcontrols),'loads':d.Loads.Count(),'graph_bus_vertices':len(bd),'graph_physical_edges':len(edges),'graph_unique_bus_pairs':len(pairs),'graph_components':len(components),'component_sizes':sorted(map(len,components),reverse=True),'graph_cycle_rank_after_parallel_bank_collapse':len(pairs)-len(bd)+len(components),'parallel_bus_pairs':[{'buses':list(k),'elements':v} for k,v in pairs.items() if len(v)>1], 'coords_defined':sum(b['coord_defined'] for b in buses),'electrically_eligible_buses':sum(b['electrically_eligible'] for b in buses),'selection_ready_buses':sum(b['selection_ready'] for b in buses),'eligibility_exclusion_counts_overlapping':dict(Counter(r for b in buses for r in b['eligibility_exclusions']))}
for n,rows in [('buses',buses),('lines',lines),('transformers',xfmrs),('regulators',regs),('capacitors',caps),('capacitor_controls',capcontrols),('topology_edges',edges),('compile_audit',summary)]:save(n,rows)
manifest=json.loads((OUT/'source_manifest.json').read_text())
checks=[{'relative_path':m['relative_path'],'unchanged':hashlib.sha256((ROOT/'source'/m['relative_path']).read_bytes()).hexdigest()==m['sha256']} for m in manifest]
save('source_integrity_after_compile',checks)
assert all(x['unchanged'] for x in checks)
print(json.dumps(summary,indent=2))

