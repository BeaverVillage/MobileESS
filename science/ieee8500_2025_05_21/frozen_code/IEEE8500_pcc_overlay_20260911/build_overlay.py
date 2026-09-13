import csv,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;WS=ROOT.parent;BASE=WS/'IEEE8500_scalability_20260910';SITES=BASE/'station_selection_v1';V41=WS/'v41r4_final_results_pr'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):
    (ROOT/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    if isinstance(data,list) and data:
        with (ROOT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

assert not (ROOT/'IEEE8500_PCC_Overlay.dss').exists()
f=read(SITES/'SERVICE_REGISTRY_FREEZE_MANIFEST.json')
assert all(sha(SITES/r['path'])==r['sha256'] for r in f['files'])
aidc=read(SITES/'FINAL_AIDC_HOST_AUTHORITY.json');registry=read(SITES/'FINAL_24_LOCATION_ELECTRICAL_MAPPING.json')
assert len(registry)==24 and len({r['ieee8500_bus'] for r in registry})==24
assert {r['location_id']:r['ieee8500_bus'] for r in registry if r['location_role']=='AIDC'}=={r['aidc_id']:r['ieee8500_bus'] for r in aidc['frozen_mapping']}
authority={'authority_id':'FINAL_IMMUTABLE_IEEE8500_24_LOCATION_TOPOLOGY_AUTHORITY','AIDC_authority':'FINAL_IMMUTABLE','STA_and_24_location_registry_authority':'FINAL_IMMUTABLE','site_selection_rule_changes_allowed':False,'host_changes_allowed':False,'AIDC_count':12,'STA_count':12,'locations':registry,'source_registry_path':str(SITES/'FINAL_24_LOCATION_ELECTRICAL_MAPPING.json'),'source_registry_sha256':sha(SITES/'FINAL_24_LOCATION_ELECTRICAL_MAPPING.json'),'source_registry_freeze_sha256':sha(SITES/'SERVICE_REGISTRY_FREEZE_MANIFEST.json'),'source_AIDC_authority_sha256':sha(SITES/'FINAL_AIDC_HOST_AUTHORITY.json')}
save('FINAL_IMMUTABLE_TOPOLOGY_AUTHORITY',authority)
before=[{'path':str(p.relative_to(BASE)).replace('\\','/'),'sha256':sha(p),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in sorted(BASE.rglob('*')) if p.is_file()]
save('ORIGINAL_IEEE8500_AND_EVIDENCE_BEFORE',before)
ref=V41/'dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss';contract=V41/'dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_CONTRACT_V2.json'
ct=read(contract);assert sha(ref)==ct['generated_three_phase_pcc_v4']['sha256']
text=ref.read_text(encoding='utf-8');blocks=re.findall(r'(?im)^New Transformer\.[^\r\n]+\r?\n~[^\r\n]+\r?\n~[^\r\n]+',text)
assert len(blocks)==36
assert all('Phases=3 Windings=2 XHL=5.75 %R=0.8 %NoLoadLoss=0 %Imag=0' in b and 'Conns=[wye wye]' in b for b in blocks)
assert sum('kVAs=[1500 1500]' in b for b in blocks)==12 and sum('kVAs=[750 750]' in b for b in blocks)==24
save('STATIC_PCC_REFERENCE_PROVENANCE',{'reference':str(ref),'reference_sha256':sha(ref),'contract':str(contract),'contract_sha256':sha(contract),'reference_primary_kv':4.16,'overlay_primary_kv':12.47,'secondary_kv':.48,'voltage_adaptation_reason':'Match immutable IEEE8500 primary host nominal voltage; kVA and reference transformer per-unit specifications unchanged','explicit_user_ratings_authority':{'AIDC_kva':1500,'MESS_kva':750},'reference_transformer_blocks':blocks,'reference_resolved_winding_percent_resistances':[.8,.2],'PCC_only_no_resource_scale_change':True,'performance_results_read':False})
native_buses={b['bus'] for b in read(BASE/'audit/buses.json')};inventory=[];commands=['! IEEE8500 additive PCC overlay. Transformers only; final host authority immutable.','! 12.47/0.48 kV adapts the V41 static 4.16/0.48 kV template to IEEE8500.','! %Rs=[0.8 0.2] explicitly resolves template %R=0.8 on winding 1.','! No Load/Generator/Storage/PCS/PCC-link line objects are created.','']
for loc in registry:
    name=loc['location_id'];host=loc['ieee8500_bus']
    roles=[('AIDC',1500),('MESS',750)] if loc['location_role']=='AIDC' else [('MESS',750)]
    for role,kva in roles:
        tx=f'PCC8500_{role}_{name}_TX';bus=f'pcc8500_{role.lower()}_{name.lower()}_lv'
        assert bus not in native_buses
        commands += [f'New Transformer.{tx} Phases=3 Windings=2 XHL=5.75 %Rs=[0.8 0.2] %NoLoadLoss=0 %Imag=0',f'~ Buses=[{host}.1.2.3 {bus}.1.2.3] Conns=[wye wye]',f'~ kVs=[12.47 0.48] kVAs=[{kva} {kva}]','']
        inventory.append({'location_id':name,'location_role':loc['location_role'],'PCC_role':role,'host_bus':host,'PCC_bus':bus,'transformer':tx.lower(),'phases':3,'primary_kv':12.47,'secondary_kv':.48,'rating_kva':kva,'host_x':loc['bus_x'],'host_y':loc['bus_y']})
assert len(inventory)==36 and len({r['PCC_bus'] for r in inventory})==36
(ROOT/'IEEE8500_PCC_Overlay.dss').write_text('\n'.join(commands)+'\n',encoding='utf-8')
(ROOT/'PCC_BusCoordinates.dss').write_text('\n'.join(f"SetBusXY Bus={r['PCC_bus']} x={r['host_x']:.15g} y={r['host_y']:.15g}" for r in inventory)+'\n',encoding='utf-8')
master=f'''! Compile native source unchanged, then only additive PCC transformers.
Compile "{(BASE/'source/Master-unbal.dss').as_posix()}"
Redirect "{(ROOT/'IEEE8500_PCC_Overlay.dss').as_posix()}"
! Native voltagebases already contain 0.48 kV. Do not modify the base list.
CalcVoltageBases
Redirect "{(ROOT/'PCC_BusCoordinates.dss').as_posix()}"
'''
(ROOT/'Master_IEEE8500_PCC.dss').write_text(master,encoding='utf-8')
save('PCC_OVERLAY_INVENTORY',inventory)
save('OVERLAY_SCOPE_CONTRACT',{'AIDC_PCC_count':12,'AIDC_PCC_kva':1500,'MESS_service_PCC_count':24,'MESS_PCC_kva':750,'independent_parallel_primary_branches_at_AIDC_hosts':True,'resource_objects_added':0,'PCS_GPU_energy_scale_changes':0,'host_changes':0,'native_DSS_edits':0,'background_scaling_runs':0,'temporalization_runs':0,'alpha8500_selection_runs':0,'B0_B1_B2_B3_runs':0,'no_load_harness':'Fresh isolated engine contexts; disable native Load/Generator/PVSystem/Storage/Isource objects in memory and turn controls off; preserve native capacitors, transformer/regulator taps and ratings. Solve once, then restore enabled states and control mode. No model-file mutation and no loadmult change.'})
save('OVERLAY_PREVALIDATION_FREEZE',{'files':[{'path':p.name,'sha256':sha(p)} for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='OVERLAY_PREVALIDATION_FREEZE.json'],'immutable_registry_sha256':authority['source_registry_sha256']})
print(json.dumps({'generated_transformers':36,'generated_PCC_buses':36,'protected_original_files':len(before),'static_template_sha256':sha(ref)},indent=2))
