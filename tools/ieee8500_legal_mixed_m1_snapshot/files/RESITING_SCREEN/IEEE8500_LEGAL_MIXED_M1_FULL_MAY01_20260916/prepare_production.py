import sys,os,json,hashlib,shutil
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).absolute().parent;ROOT=H.parent.parent
A=ROOT/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
names=['bootstrap.py','common8500.py','numerical_coefficients.py','full_electrical_rows.py','frozen_binding.py','headroom_authority.py','v41r4_ieee8500_adapter.py','v41r4_loop_budget.py','v41r4_search_budget.py','aidc_runtime.py','ranking8500.py','grid8500.py','structural_projection.py','fleet_binding.py','mess_grid8500.py','mess_runtime.py','physical_closure.py','a1_worker.py','mf_worker.py','HEADROOM_AUTHORITY.json','AIDC_2X_AUTHORITY.json','SCREENING_RULE.json','D1_AEMO_VIC1_FORECAST.json','MAY01_B0_AIDC_POWER.npz','NORMALIZED_B0_AIDC_POWER.npz','REFERENCE_JOBS.json','FLEET_AUTHORITY.json','IEEE8500_V41R4_AIDC_BINDING_PASS.json']
for n in names:shutil.copyfile(A/n,H/n)
diffs=read(A/'CODE_DIFF.json')
for r in diffs:
 src=Path(r['override']);dst=H/'overrides'/Path(*r['module'].split('.')).with_suffix('.py');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);assert sha(dst)==r['override_sha256'];r['override']=str(dst)
save(H/'CODE_DIFF.json',diffs)
layout=read(H/'LAYOUT.json');inv=read(A/'PCC_OVERLAY_INVENTORY.json');selected=dict(zip(layout['station_ids'],layout['mess']));cmd=[]
for r in inv:
 r['connection']='.1.2.3'
 if r['PCC_role']=='AIDC':r['host_bus']=layout['aidc'][int(r['location_id'][-2:])-1]
 elif r['location_id'] in selected:
  c=selected[r['location_id']];r.update(host_bus=c['bus'],phases=c['phases'],primary_kv=c['kv'],connection='.1.0' if c['phases']==1 else '.1.2.3')
 primary=selected[r['location_id']]['key']+'.0' if r['PCC_role']=='MESS' and r['location_id'] in selected and r['phases']==1 else r['host_bus']+'.1.2.3'
 cmd.extend([f'New Transformer.{r["transformer"]} Phases={r["phases"]} Windings=2 XHL=5.75 %Rs=[0.8 0.2] %NoLoadLoss=0 %Imag=0',f'~ Buses=[{primary} {r["PCC_bus"]}{r["connection"]}] Conns=[wye wye] kVs=[{r["primary_kv"]} 0.48] kVAs=[{r["rating_kva"]} {r["rating_kva"]}]'])
 r.pop('host_x',None);r.pop('host_y',None)
cmd.append('CalcVoltageBases')
cmd.extend(f'SetkVBase Bus={r["PCC_bus"]} kVLN=0.48' for r in inv if r['phases']==1)
(H/'PCC_OVERLAY.dss').write_text('\n'.join(cmd),encoding='utf-8');save(H/'PCC_OVERLAY_INVENTORY.json',inv)
ports=[]
for i,sid in enumerate([f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]):
 loc='A'+sid if sid.startswith('IDC') else sid;r=next(r for r in inv if r['PCC_role']=='MESS' and r['location_id']==loc)
 ports.append(dict(service=sid,location=loc,host=r['host_bus'],PCC=r['PCC_bus'],transformer=r['transformer'],P_column=12+i,Q_column=36+i))
save(H/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json',dict(status='PASS',services=ports,inheritance='18 unselected MESS PCC mappings unchanged by explicit user reply'))
for n,old,new in [
 ('numerical_coefficients.py',"COEFF_HOME=H.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912'",'COEFF_HOME=H'),
 ('frozen_binding.py',"WORKSPACE=HOME.parent.parent",'WORKSPACE=HOME.parent.parent'),
 ('v41r4_ieee8500_adapter.py',"assert r['rating_kva']==750 and r['phases']==3","assert r['rating_kva']==750 and r['phases'] in (1,3)"),
 ('mess_runtime.py',"or len(node_names) != 8639:","or len(node_names) != {len(AX['nodes'])}:"),
 ('mess_runtime.py',"src=src.replace(old,'if len(controls) != 60 or len(node_names) != {len(AX['nodes'])}:')","src=src.replace(old,f\"if len(controls) != 60 or len(node_names) != {len(AX['nodes'])}:\")")]:
 p=H/n;x=p.read_text(encoding='utf-8');assert old in x,(n,old);p.write_text(x.replace(old,new),encoding='utf-8')
save(H/'PRODUCTION_AUTHORIZATION.json',dict(authorized=True,date='2025-05-01',policies=['B0','B1','B2','B3'],Fresh=True,Actual=False,workers=1,threads=4,source='Current user full validation request plus 18-PCC inheritance reply'))
save(H/'SOURCE_COPY_MANIFEST.json',dict(files=[dict(path=str(A/n),sha256=sha(A/n)) for n in names],layout_sha256=sha(H/'LAYOUT.json'),inherited_mapping_sha256=sha(A/'PCC_OVERLAY_INVENTORY.json')))
print('PRODUCTION_BINDING_PREPARED')
