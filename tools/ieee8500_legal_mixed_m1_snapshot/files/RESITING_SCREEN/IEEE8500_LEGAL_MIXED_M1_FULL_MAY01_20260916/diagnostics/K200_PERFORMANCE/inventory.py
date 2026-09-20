import pathlib,json,hashlib
D=pathlib.Path(__file__).absolute().parent;H=D.parent.parent;W=H.parent.parent;O=W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
def rec(p):
 r={'path':str(p),'exists':p.exists()}
 if p.is_file():
  with p.open('rb') as f:r.update(bytes=p.stat().st_size,sha256=hashlib.file_digest(f,'sha256').hexdigest())
 return r
beam='B2/beam/2025-05-01/B2/B2'
specs=[
 ('candidate_cache','B2/candidate_cache','B2/candidate_cache','*.pkl','CandidateResultCache.load/store','Previous result identity differs: PCC binding, 96 coefficient hashes, screen authority and namespace. Current cold misses produce new cache; old cache still exists.'),
 ('route_candidate_enumeration',beam+'/s1/B2-ROOT/LOCAL_SEARCH.json',beam+'/s1/B2-ROOT/LOCAL_SEARCH.json',None,'enumerate_initial_relocations; _local_search','Enumeration in memory; final LOCAL_SEARCH emitted after K completes. Candidate-table SHA identical. Current missing summary is not deleted input.'),
 ('traffic_path_cache','traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz','traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz',None,'mess_runtime.traffic; daily_traffic_authority','Reused identical frozen route table in isolated namespaces; disk SHA identical.'),
 ('mobility_feasibility_cache',beam+'/s1/B2-ROOT/LOCAL_SEARCH.json',beam+'/s1/B2-ROOT/LOCAL_SEARCH.json',None,'enumerate_initial_relocations / screen_dynamic_candidates','No separate persistent mobility feasibility cache in this path; same route enumeration authority; screen regenerated for changed electrical context.'),
 ('beam_K200_checkpoints',beam,beam,'STAGE_*.json','_run_case stage_path restoration','Old six stage checkpoints retained. Current first K200 stage unfinished, so no stage checkpoint yet; cannot import old electrical results.'),
 ('incumbent_warm_start',beam+'/s1/B2-ROOT/SEEDS.json',beam+'/s1/B2-ROOT/SEEDS.json',None,'_local_search emits SEEDS; _full_child consumes dispatch','Old seeds retained; current seeds not generated until 201 restricted results complete. Different electrical authority invalidates old solved seeds as certified current results.'),
 ('electrical_screening',beam+'/CONGESTION_MAP.json',beam+'/CONGESTION_MAP.json',None,'_critical_states; build_planning_screen_context; screen_dynamic_candidates','Both initial seed maps contain 20 states. Current screen authority SHA differs; recomputed. Candidate separation states persist in result caches and memory.'),
 ('coefficient_cache','../IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912/coefficients','coefficients','COEFFICIENTS.npz','numerical_coefficients.build; mess_runtime.coefficients','Both 96 coefficient files retained; old source is sibling namespace. Current infrastructure requires new coefficients; loaded as tuple once before candidates.'),
 ('station_travel_matrices','traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz','traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz',None,'MobilityRouteTable from frozen route table','Travel times and mobility energy come from identical route-table authority; no separate missing station matrix on this code path.'),
 ('service_domain','MESS_24_SERVICE_PCC_COLUMN_BINDING.json','MESS_24_SERVICE_PCC_COLUMN_BINDING.json',None,'mess_runtime.search _service_mapping / control_names','Both full-production runs have 24 service points and 60 controls. Six is fleet size/selected stations, not previous route-domain size.'),
 ('OpenDSS_replay_cache','B2/final_exact/AC_VALIDATION.json','B2/final_exact/AC_VALIDATION.json',None,'mess_runtime.search after _run_case; exact','Not a K200 child cache. Current final replay not due until route search finishes. No child OpenDSS/native settling calls.'),
 ('Gurobi_nodefiles_MIP_start','B2','B2','*.mst','build_fixed_candidate_model; full child dispatch seed','Restricted candidate models are fresh; no disk MIP-start/nodefile restore code. Full-stage seeds generated after K200. No missing start file implicated.')]
rows=[]
for kind,oldrel,newrel,pattern,generator,note in specs:
 row={'category':kind,'generator':generator,'finding':note,'deletion_evidence':'No evidence for deletion of this IEEE8500 artifact; previous root remains present.'}
 for label,p in [('previous',O/oldrel),('current',H/newrel)]:
  row[label]=rec(p)
  if pattern and p.is_dir():
   files=sorted(p.rglob(pattern));row[label].update(count=len(files),example_records=[rec(q) for q in files[:2]])
 rows.append(row)
manifest=W/'B3_2ROUND_EXTENSION/INVALIDATED_2ROUND_RUN_MANIFEST.json';v=json.loads(manifest.read_text(encoding='utf-8-sig'))
out={'items':rows,'cleanup_manifest':rec(manifest),'cleanup_status':v.get('status'),'cleanup_targets':v.get('deletion_roots'),'scope_limit':'Workspace artifact/source/manifests audit only; no filesystem journal or recycle-bin forensic recovery. Cannot prove no historical deletion ever occurred.'}
(D/'artifact_inventory.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print([(r['category'],r['previous'].get('count',r['previous']['exists']),r['current'].get('count',r['current']['exists'])) for r in rows])
