import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;OLD=BASE/'selection_v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
before=read(ROOT/'V2_IMMUTABILITY_BEFORE.json')
old_names={p.relative_to(OLD).as_posix() for p in OLD.rglob('*') if p.is_file()}
expected={r['path'] for r in before}
changed=[]
for r in before:
    p=OLD/r['path']
    if not p.is_file() or sha(p)!=r['sha256'] or p.stat().st_size!=r['bytes'] or p.stat().st_mtime_ns!=r['mtime_ns']:changed.append(r['path'])
assert not changed and old_names==expected
frozen_v2=read(OLD/'SELECTION_FREEZE_MANIFEST.json')
assert all(sha(OLD/r['path'])==r['sha256'] for r in frozen_v2['files'])
record={'status':'PASS','selection_v2_files_checked':len(before),'changed_files':changed,'added_files':sorted(old_names-expected),'removed_files':sorted(expected-old_names),'content_size_and_mtime_preserved':True,'v2_original_freeze_entries_verified':len(frozen_v2['files'])}
(ROOT/'V2_IMMUTABILITY_VERIFICATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
proc=read(ROOT/'PROCEDURE_FREEZE_MANIFEST.json')
assert sha(BASE/'FREEZE_MANIFEST.json')==proc['original_freeze_sha256']
assert sha(OLD/'SELECTION_FREEZE_MANIFEST.json')==proc['selection_v2_freeze_sha256']
for r in proc['inputs']:assert sha(BASE/r['path'])==r['sha256']
for r in proc['files']:assert sha(ROOT/r['path'])==r['sha256']
valid=read(ROOT/'SELECTION_VALIDATION.json')
assert all(valid['checks'].values()) and valid['hard_criteria_all_pass']
assert read(ROOT/'DETERMINISM_VERIFICATION.json')['status']=='PASS'
mapping=read(ROOT/'AIDC01_AIDC12_IEEE8500_MAPPING.json');assert len(mapping)==12
assert len(read(ROOT/'ALL_66_PAIR_METRICS.json'))==66
artifacts=sorted(p for p in ROOT.iterdir() if p.is_file() and p.name not in ('GUARDED_SELECTION_FREEZE_MANIFEST.json','GUARDED_SELECTION_FREEZE_MANIFEST.sha256'))
manifest={'freeze_id':'IEEE8500_SOURCE_PROXIMITY_GUARDED_SELECTION','status':valid['status'],'global_optimality':'NOT_CLAIMED_NOT_CERTIFIED','original_candidate_count':638,'guarded_candidate_count':606,'root_distance_q05_ohm':read(ROOT/'ROOT_DISTANCE_GUARD_AUDIT.json')['root_distance_q05_ohm'],'aidc_count':12,'changed_site_count_vs_v2':len(read(ROOT/'CHANGED_SITES_VS_V2.json')),'AIDC_loads_added':0,'PCCs_added':0,'B0_B1_B2_B3_runs':0,'OpenDSS_compile_runs':0,'procedure_freeze_sha256':sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json'),'original_v2_freeze_sha256':sha(OLD/'SELECTION_FREEZE_MANIFEST.json'),'data_inputs':proc['inputs'],'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in artifacts],'excluded_generated_environment_directories':['__pycache__']}
(ROOT/'GUARDED_SELECTION_FREEZE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
h=sha(ROOT/'GUARDED_SELECTION_FREEZE_MANIFEST.json');(ROOT/'GUARDED_SELECTION_FREEZE_MANIFEST.sha256').write_text(h+'  GUARDED_SELECTION_FREEZE_MANIFEST.json\n',encoding='ascii')
for r in manifest['files']:assert sha(ROOT/r['path'])==r['sha256']
print(json.dumps({'status':manifest['status'],'v2_preservation':record,'guarded_artifacts_hashed':len(artifacts),'manifest_sha256':h},indent=2))
