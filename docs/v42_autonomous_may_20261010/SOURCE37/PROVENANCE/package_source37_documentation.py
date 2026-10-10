from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02');HERE=Path(__file__).resolve().parent
DOC=REPO/'docs/v42_autonomous_may_20261010/SOURCE37'
assert not DOC.exists();DOC.mkdir(parents=True)
def rec(p):
 p=Path(p).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(p):return json.loads(Path(p).read_bytes().decode('utf-8-sig'))
def put(path,b):
 p=DOC/path;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b)
 return p
manifest=read(ROOT/'B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json');union=dict(manifest['builder_original_sources'],**manifest['execution_sources'])
science_before={n:rec(REPO/n) for n in union};assert all(science_before[n]['sha256']==h for n,h in union.items())
audit_path=HERE/'SOURCE37_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json';audit=read(audit_path);assert audit['PASS'] is True
old_inventory_before={p:rec(p) for p in audit['old_documentation_inventories']};assert old_inventory_before==audit['old_documentation_inventories']
provenance={}
def copy(src,dst):
 src=Path(src);b=src.read_bytes();target=put(dst,b);assert target.read_bytes()==b
 provenance[str(target.relative_to(DOC))]=dict(source=rec(src),copy=rec(target))
def top(src,dst):
 for p in sorted(Path(src).iterdir()):
  if p.is_file():copy(p,Path(dst)/p.name)
top('D:/v42_first_sweep_zero_contract_owner_review_20261010_01','CONTROLLER_ZERO_CONTRACT/OWNER165')
top('D:/v42_first_sweep_zero_contract_independent_review_20261010_01','CONTROLLER_ZERO_CONTRACT/INDEPENDENT165')
top('D:/v42_source37_owner_review_20261010_02','SELECTED_NATIVE_DENIED_REVIEW/OWNER374_FINAL02')
top('D:/v42_source37_independent_review_20261010_03','SELECTED_NATIVE_DENIED_REVIEW/INDEPENDENT374_FINAL03')
top('D:/v42_source37_owner_review_20261010_01','HARNESS_HISTORY/OWNER_INITIAL01')
top('D:/v42_source37_independent_review_20261010_01','HARNESS_HISTORY/INDEPENDENT_INITIAL01')
top('D:/v42_source37_independent_review_20261010_02','HARNESS_HISTORY/INDEPENDENT_INITIAL02')
for p in sorted(HERE.iterdir()):
 if p.is_file() and p.name not in ('package_source37_documentation.py','SOURCE37_DOC_SCOPE_CURRENT_MONITOR_API_CONTEXT.json'):
  copy(p,Path('DEPLOYMENT/INDEPENDENT_READONLY_AUDIT')/p.name)
for p in sorted((HERE/'artifacts').iterdir()):copy(p,Path('DEPLOYMENT/INDEPENDENT_READONLY_AUDIT/artifacts')/p.name)
for name in ['build_v37_validation_template.py','freeze_sparse_v37.py','smoke_sparse_v37.py','prepare_verified_v37_zero_start_retries.py','V37_SPARSE_IMMUTABLE_FREEZE.json','V37_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json','V37_VALIDATION_BINDING_TEMPLATE.json','V37_VERIFIED_REPAIR_VALIDATION.json','V37_ZERO_START_RETRY_PREPARATION.json','V37_ZERO_START_RETRY_DEPLOYMENT.json','CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T021517.json']:
 copy(ROOT/'autonomous'/name,Path('DEPLOYMENT/ROOT_OPERATIONAL_RECORDS')/name)
copy(ROOT/'B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json','DEPLOYMENT/ROOT_OPERATIONAL_RECORDS/B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json')
for p in sorted((ROOT/'autonomous').glob('CONTROLLER_FIRST_SWEEP_ZERO_CONTRACT*.json')):copy(p,Path('CONTROLLER_ZERO_CONTRACT/ACTUAL_OWNED_RELOAD')/p.name)
for p in sorted((ROOT/'autonomous').glob('CONTROLLER_ZERO_CONTRACT_RELOAD_B2_*_NATIVE_BEFORE.json')):copy(p,Path('CONTROLLER_ZERO_CONTRACT/ACTUAL_OWNED_RELOAD')/p.name)
copy(ROOT/'autonomous/reload_owned_supervisor_first_sweep_zero_contract.py','CONTROLLER_ZERO_CONTRACT/ACTUAL_OWNED_RELOAD/reload_owned_supervisor_first_sweep_zero_contract.py')
continuity=Path('D:/v42_source36_actual_transition_independent_audit_20261010_01/events/OWNED_CONTROL_ONLY_SUPERVISOR_RELOAD_CONTINUITY_70a5a5f3')
for p in sorted(continuity.iterdir()):
 if p.is_file():copy(p,Path('CONTROLLER_ZERO_CONTRACT/INDEPENDENT_OWNED_RELOAD_ACCEPTANCE')/p.name)
for name in ['v42_autonomous_b2/worker.py']:
 copy(Path('D:/v42run37')/name,Path('PRODUCTION_SOURCE/FROZEN_D37')/name)
for name in ['v42_autonomous/supervisor.py','v42_autonomous/recovery.py','tests/test_v42_autonomous_first_sweep_zero_contract.py','tests/test_v42_autonomous_b2_f1_price_seed.py']:
 copy(REPO/name,Path('PRODUCTION_SOURCE/COMMIT_300ACBEB')/name)
copy(Path(__file__),'PROVENANCE/package_source37_documentation.py')
hourly=read(ROOT/'autonomous/CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T021517.json')
assert rec(ROOT/'autonomous/CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T021517.json')['sha256']=='f7ad4b330825941ccd57c0efc068b98f7b512bb9303e76b6947a8413120863fb'
assert hourly['toml']['status']==hourly['database']['status']=='ACTIVE' and hourly['database']['last_run_at'] is None and hourly['actual_scheduled_run_observed'] is False
api=read(HERE/'SOURCE37_DOC_SCOPE_CURRENT_MONITOR_API_CONTEXT_02.json')
README='''Source37 adds an early zero-start admission check and a controller request-field correction. It does not alter the original model, objective, domain, signed certificates, pricing algorithms, precision, Threads1, single-call limits or total5400 Native budget. The original1007 files and other98 execution modules are byte-identical to Source36; only worker.py changes in execution99. Scientific commit300acbeb7a53da184d996bc352a8527cfb3549f5, executionSHA ba88d19a1e0d0abbbf343ee55deec49753b8e68d6a31c37c1ee9a8cf288c4a82.

The ordinary Source36 May10 request omitted restart_from_zero/previous_attempts/reset_authorization despite a sealed fresh deployment. It naturally failed at the unchanged projection authority after6 measured Native calls,584.6879997253418seconds. Its full RESULT and ledger are preserved as exact artifacts. The controller now propagates the verified fresh contract, and Source37 calls the same original authority after complete source/request admission and before model preparation or Native.

Owner and independent selected scientific suites each passed374 tests with retained real model construction and optimize denied, attempts[]. Owner and independent controller suites each passed165. These qualify source/admission behavior; they are not Native performance or convergence measurements. Initial owner373/374 guard-fixture failure and stale metadata path, independent01 pretest path escape, and independent02 final metadata path failure are preserved with original runners/XML/logs/exception histories. No incomplete harness was promoted to qualifiedPASS. Independent03 completed full source/counter proof; its110 string literals were checked for control characters and all historical paths were verified before execution.

The owned controller reload82852→80264 is separately recorded. The later Source37 deployment occurred2026-10-10T02:14:12.011075+00:00; lease c4c7547609954eefaa5ad213269fb2ca was explicitly released02:14:13.906026+00:00. Only May10 queue cb3c3b7e32b0455c883aefb16051c340 was added as READY_VERIFIED_REPAIR, priority100, freshNative0/full5400. Three slot requests are sealed; no output, RESULT or Native ledger existed for them at the independent audit cutoff. All9 Source36 queue IDs remained:3 with verified Native progress and6 READY; their27 existing request SHAs were retained.

The post-deployment audit binds current Source36 PID91368/107404/65052, exact process birth/command/cwd/request, and ordered completed Native prefixes to the earlier independent owned80264 reload observation. It verifies all1111 files in each D35/D36/D37 checkout and unchanged old Source35/36 documentation inventories. This is an explicitly bounded earlier-cursor comparison, not an invented simultaneous prepare-before snapshot. Supervisor80264 and sole monitor105976 were verified read-only. Production workers, queues, leases and source were not modified by the independent reviewer.

A single cached monitor API snapshot is saved with snapshot_UTC2026-10-10T02:21:00.639868+00:00. The first3 were RUNNING on Source36, PASSfalse, with global gaps approximately.280606/.251254/.700901 and completed Native2080.719/1965.522/866.286seconds; these values belong only to that saved snapshot. May10 was RETRY_PENDING and its displayedNative584.688 referred to the preserved failed Source36 attempt. Source37 READY Native0 is distinct from those old fields. FinalFULL Global Gap≤.03, Actual/Fresh and datePASS remain pending; no actual Source37 solve or speedup is claimed.

The saved hourly configuration verification at02:15:17.693928+00:00 reports ACTIVE with last_run_at null and actual_scheduled_run_observed false. It confirms configuration only. The automation prompt itself is not copied.

Folders: CONTROLLER_ZERO_CONTRACT retains165-test and owned-reload evidence; SELECTED_NATIVE_DENIED_REVIEW retains complete374 qualifications; HARNESS_HISTORY retains incomplete external audits; DEPLOYMENT retains immutable binding, three actual admissions, queue/API/runtime snapshots and readonly audit; PRODUCTION_SOURCE holds exact changed source/test copies; PROVENANCE binds each copied artifact. AllPASS fields in this package concern qualification or evidence integrity, not final scientific datePASS.
'''
put('README.md',README.encode('utf-8'))
put('PROVENANCE/COPY_SOURCE_SHA_INDEX.json',(json.dumps(dict(schema='V42_SOURCE37_DOCUMENTATION_EXACT_COPY_SOURCE_INDEX_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),files=provenance),ensure_ascii=False,indent=2)+chr(10)).encode('utf-8'))
science_after={n:rec(REPO/n) for n in union};old_inventory_after={p:rec(p) for p in old_inventory_before}
assert science_before==science_after and old_inventory_before==old_inventory_after
put('PROVENANCE/SCIENCE_AND_OLD_SEAL_PRESERVATION.json',(json.dumps(dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),source_record_count=1106,original1007_execution99_start_end_identical=True,source_before=science_before,source_after=science_after,old_inventories_before=old_inventory_before,old_inventories_after=old_inventory_after,operational_mutations=0,Native_model_calls=0,actual_scientific_PASS_claimed=False),ensure_ascii=False,indent=2)+chr(10)).encode('utf-8'))
files={p.relative_to(DOC).as_posix():rec(p) for p in sorted(DOC.rglob('*')) if p.is_file()}
put('SHA_INVENTORY.json',(json.dumps(dict(schema='V42_SOURCE37_ALL_DOCUMENTATION_SHA_INVENTORY_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),files=files,excluding_only='SHA_INVENTORY.json'),ensure_ascii=False,indent=2)+chr(10)).encode('utf-8'))
assert all(rec(DOC/name)==r for name,r in files.items())
print(json.dumps(dict(PASS=True,package=str(DOC),files=len(files)+1,total_bytes=sum(p.stat().st_size for p in DOC.rglob('*') if p.is_file()),inventory=rec(DOC/'SHA_INVENTORY.json'),source1106_start_end_identical=True,old35_36_seals_unchanged=True)))
