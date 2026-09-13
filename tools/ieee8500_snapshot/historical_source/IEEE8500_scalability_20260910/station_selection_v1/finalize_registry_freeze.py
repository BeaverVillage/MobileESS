import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
before=read(ROOT/'EXISTING_EVIDENCE_BEFORE.json');expected={r['path'] for r in before}
current={p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file() and 'station_selection_v1' not in p.relative_to(BASE).parts and 'source' not in p.relative_to(BASE).parts}
changed=[]
for r in before:
    p=BASE/r['path']
    if not p.is_file() or sha(p)!=r['sha256'] or p.stat().st_mtime_ns!=r['mtime_ns'] or p.stat().st_size!=r['bytes']:changed.append(r['path'])
assert not changed and current==expected
preserve={'status':'PASS','existing_evidence_files_verified':len(before),'changed_files':changed,'added_existing_directory_files':sorted(current-expected),'removed_existing_files':sorted(expected-current),'contents_sizes_mtimes_unchanged':True,'source_directory_written':False}
(ROOT/'EXISTING_EVIDENCE_PRESERVATION.json').write_text(json.dumps(preserve,indent=2),encoding='utf-8')
proc=read(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')
for r in proc['files']:assert sha(ROOT/r['path'])==r['sha256']
for r in proc['inputs']:assert sha(BASE/r['path'])==r['sha256']
assert sha(BASE/'FREEZE_MANIFEST.json')==proc['original_freeze_sha256']
v=read(ROOT/'REGISTRY_VALIDATION.json');assert v['all_STA_hard_criteria_pass'] and v['unchanged_FINAL_AIDC_mapping'] and v['decision_logs_and_mapping_identical']
reg=read(ROOT/'FINAL_24_LOCATION_ELECTRICAL_MAPPING.json');assert len(reg)==24 and len({r['ieee8500_bus'] for r in reg})==24 and all(r['is_MESS_service_location'] for r in reg)
auth=read(ROOT/'FINAL_AIDC_HOST_AUTHORITY.json');raw=read(BASE/auth['source_mapping_path']);assert auth['frozen_mapping']==raw
assert {r['location_id']:r['ieee8500_bus'] for r in reg if r['location_role']=='AIDC'}=={r['aidc_id']:r['ieee8500_bus'] for r in raw}
assert len(read(ROOT/'STA_66_PAIR_METRICS.json'))==66 and len(read(ROOT/'AIDC_STA_144_CROSS_PAIR_DIAGNOSTICS.json'))==144
assert (ROOT/'FINAL_24_LOCATION_TOPOLOGY.png').stat().st_size>10000
files=sorted(p for p in ROOT.iterdir() if p.is_file() and p.name not in ('SERVICE_REGISTRY_FREEZE_MANIFEST.json','SERVICE_REGISTRY_FREEZE_MANIFEST.sha256'))
manifest={'freeze_id':'IEEE8500_FINAL_AIDC_AUTHORITY_AND_24_SERVICE_LOCATION_REGISTRY','status':v['status'],'final_immutable_AIDC_count':12,'selected_STA_count':12,'distinct_MESS_service_locations':24,'AIDC_host_changes':0,'AIDC_authority_sha256':sha(ROOT/'FINAL_AIDC_HOST_AUTHORITY.json'),'original_AIDC_mapping_sha256':auth['source_mapping_sha256'],'STA_pairs':66,'AIDC_STA_cross_pairs':144,'PCC_transformers_created':0,'background_scaling_runs':0,'B0_B1_B2_B3_runs':0,'global_optimality':'NOT_CLAIMED','procedure_freeze_sha256':sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json'),'inputs':proc['inputs'],'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in files],'runtime':{'numpy':'1.26.4','scipy':'1.14.1','matplotlib':'3.9.4','random_draws':0,'search_replays':2},'excluded_generated_cache_directories':['plot_cache','__pycache__']}
(ROOT/'SERVICE_REGISTRY_FREEZE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
h=sha(ROOT/'SERVICE_REGISTRY_FREEZE_MANIFEST.json');(ROOT/'SERVICE_REGISTRY_FREEZE_MANIFEST.sha256').write_text(h+'  SERVICE_REGISTRY_FREEZE_MANIFEST.json\n',encoding='ascii')
assert all(sha(ROOT/r['path'])==r['sha256'] for r in manifest['files'])
print(json.dumps({'status':v['status'],'AIDC_host_changes':0,'locations':24,'STA_pairs':66,'cross_pairs':144,'old_evidence_unchanged_count':len(before),'frozen_artifacts':len(files),'manifest_sha256':h},indent=2))
