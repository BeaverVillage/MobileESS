"""Add immutable independent raw evidence and seal Source35 documentation only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

REPO = Path('D:/MobileESS_v42_autonomous')
TOP = REPO/'docs/v42_autonomous_may_20261010/SOURCE35'
DEST = TOP/'DEPLOYMENT'
AUDIT = Path('D:/v42_source35_deployment_independent_audit_20261010_01')
SELF = Path(__file__).resolve()

def now():return datetime.now(timezone.utc).isoformat()
def rec(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def tree(root):return {p.relative_to(root).as_posix():rec(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
def save(path,raw):
    assert path.resolve().is_relative_to(TOP.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as out:out.write(raw)
    assert path.read_bytes()==raw
def json_save(path,obj):save(path,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

old_deployment=tree(DEST)
old_subpackages={name:tree(TOP/name) for name in ('DIAGNOSIS','PRICE_REVIEW')}
initial=json.loads((DEST/'PACKAGING_SHA_INVENTORY.json').read_bytes())
for path,expected in initial['files'].items():assert rec((DEST/path).read_bytes())==expected
provenance=[]
audit_raw=(AUDIT/'SOURCE35_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json').read_bytes()
assert rec(audit_raw)==dict(bytes=1220008,sha256='b6de3f15adfb6eb73a76a24dc2333f2b10410b4c8b51b733342f33e41cbd5bcd')
audit=json.loads(audit_raw)
assert audit['PASS'] is True and audit['Native_optimize_calls']==audit['real_Native_model_constructions']==0
assert audit['modelattempts']==audit['nativeattempts']==[]
assert audit['execution_source_count']==99 and audit['original_source_count']==1007 and audit['frozen_unique_source_asset_count']==1111
assert audit['scientific_HEAD']=='810f98a5da7eb09f61354bbfa67bc3945951f0d7'
assert audit['execution_SHA']=='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
assert len(audit['new_queue_rows'])==len(audit['superseded_unstarted_Source34_rows'])==9
assert len(audit['active_Source32_continuity'])==3
assert audit['actual_Source35_performance_or_final_PASS_claimed'] is False
refs={}
def walk(x):
    if isinstance(x,dict):
        if all(k in x for k in ('path','sha256','bytes')) and Path(x['path']).is_relative_to(AUDIT):refs[Path(x['path']).name]=x
        for v in x.values():walk(v)
    elif isinstance(x,list):
        for v in x:walk(v)
walk(audit)
for p in sorted(AUDIT.glob('*')):
    if not p.is_file():continue
    captured=now();raw=p.read_bytes();record=rec(raw)
    if p.name in refs:
        expected=refs[p.name];assert record=={k:expected[k] for k in ('bytes','sha256')}
    relative='independent_actual_deployment/'+p.name
    save(DEST/relative,raw)
    assert p.read_bytes()==raw
    if 'PRELIMINARY' in p.name:kind='HISTORICAL_FAILED_AUDIT_HARNESS_RAW_RECEIPT'
    elif p.name.startswith('INITIAL_'):kind='INITIAL_READONLY_AUDIT_SNAPSHOT'
    elif p.name=='audit_deployment.py':kind='FINAL_AUDIT_PRODUCER_SOURCE_NO_RERUN'
    elif p.name=='SOURCE35_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json':kind='FINAL_INDEPENDENT_READONLY_DEPLOYMENT_AUDIT'
    else:kind='SAVED_AUDIT_RAW_EVIDENCE_SNAPSHOT'
    provenance.append(dict(source_path=str(p),copied_path=relative,capture_UTC=captured,kind=kind,
                           referenced_by_final_audit=p.name in refs,**record))
assert len(provenance)==27
for p,expected in old_deployment.items():assert rec((DEST/p).read_bytes())==expected
for name,expected in old_subpackages.items():assert tree(TOP/name)==expected

preliminaries=[]
for p in sorted(AUDIT.glob('*PRELIMINARY*')):
    saved=json.loads(p.read_bytes())
    preliminaries.append(dict(name=p.name,PASS=saved['PASS'],error=saved['error'],
                               finished_UTC=saved['finished_UTC'],**rec(p.read_bytes())))
json_save(DEST/'FINAL_ADDITIVE_PACKAGING_OBSERVATION.json',dict(
    schema='V42_SOURCE35_DEPLOYMENT_FINAL_ADDITIVE_PACKAGING_OBSERVATION',UTC=now(),PASS=True,
    scope='Copy and rehash saved final audit, producer and every existing audit-directory raw file; do not rerun audit.',
    final_independent_audit=rec(audit_raw),independent_audit_started_UTC=audit['started_UTC'],
    independent_audit_finished_UTC=audit['finished_UTC'],
    total_independent_directory_raw_copies=len(provenance),final_audit_directly_referenced_directory_receipts=len(refs),
    initial_failed_harness_raw_receipts=preliminaries,
    final_audit_scientific_source_start_end_identical=audit['source_start_end_identical'],
    final_audit_saved_producer_evidence_start_end_identical=audit['saved_producer_evidence_start_end_identical'],
    HTTP_8794_not_independently_queried_by_final_audit=audit['HTTP_8794_not_independently_queried_by_this_audit'],
    initial_package_pending_flags_are_historical=True,existing_DEPLOYMENT_raw_bytes_unchanged=True,
    existing_DIAGNOSIS_PRICE_REVIEW_bytes_unchanged=True,
    no_raw_stdout_or_stderr_file_found_in_independent_audit_directory=True,
    no_missing_stdout_or_stderr_reconstructed=True,
    Native_optimize_calls=0,real_Native_model_constructions=0,producer_helper_or_audit_reruns=0,
    live_queue_lease_manifest_worker_process_science_or_Git_changes=0,
    actual_Source35_performance_or_final_date_PASS_claimed=False))
json_save(DEST/'ADDITIVE_PROVENANCE_SHA_INDEX.json',dict(schema='V42_RAW_BYTE_ADDITIVE_COPY_PROVENANCE_V1',
    UTC=now(),PASS=True,records=provenance))
save(DEST/'seal_deployment_with_independent_audit.py',SELF.read_bytes())

dep_readme='''# Source35 deployment and independent audit

The completed Root producer receipt records nine Source35 READY repairs at2026-10-09T23:43:29.107706+00:00. May01–03 have priority1000 and May04–09 priority100, each a separately authorized fresh attempt with Native0 initial accounting and5400 seconds. All27 day/slot request bytes are preserved. The manual repair lease was explicitly released at23:43:33.511935+00:00, after the enqueue receipt completed.

The independent read-only audit finished at2026-10-09T23:47:30.751429+00:00 and reports PASS. It rechecked Source35 HEAD810f98a5, execution99/a8cb6983, unchanged original1007 files plus five required assets (1111 unique paths), owner and independent335 qualification bindings, all27 sealed requests and saved actual canonical factory admissions, nine READY rows, and exactly nine unstarted Source34 rows superseded. It checked the three existing Source32 worker identities, their preserved completed Native prefixes and continued measured accounting, supervisor107788 identity and the released lease. It imported no science modules and executed no admission, producer helper, model or Native solve. HTTP8794 was not independently queried by this audit; the raw receipt states that limitation.

independent_actual_deployment preserves all27 files found in the audit directory: final receipt, final producer source, directly referenced raw records, additional before/current snapshots and both preliminary failed audit harness receipts. The first failed harness referenced a missing tests_passed field; the second retained a V34 attempt-name assertion. Both raw errors/tracebacks are preserved. The final producer is the final version; no unavailable historical producer version, stdout or stderr was reconstructed. Initial and final live snapshots retain distinct names and receipt times.

The initial PACKAGING_* files and their pending flags describe the earlier copying stage and remain byte-identical. FINAL_ADDITIVE_PACKAGING_OBSERVATION.json records the completed audit addition. PROVENANCE_SHA_INDEX.json and ADDITIVE_PROVENANCE_SHA_INDEX.json bind source paths and exact copied bytes. SHA_INVENTORY.json is the final package index; PACKAGING_SHA_INVENTORY.json remains the preserved initial index. No producer JSON, script, ledger or request bytes were normalized.

The saved hourly verification records ACTIVE configuration and no actual scheduled run observed. Test335 PASS, Native/model-denied admission PASS and deployment-audit PASS do not establish actual Source35 performance or final date PASS. At the independent audit time the existing Source32 first-three workers were still active and new Source35 science was pending. No live worker, process, queue, lease, manifest, scientific source or Git state was changed by this packaging.
'''
save(DEST/'README.md',dep_readme.encode('utf-8'))
dep_records=tree(DEST)
json_save(DEST/'SHA_INVENTORY.json',dict(schema='V42_SOURCE35_FINAL_DEPLOYMENT_DOCS_SHA_INVENTORY_V1',
    UTC=now(),PASS=True,files=dep_records,excludes_only='SHA_INVENTORY.json'))

top_readme='''# Source35 current-F1 computational pricing seed

Source35 scientific commit810f98a5da7eb09f61354bbfa67bc3945951f0d7 has99 declared execution files, execution SHAa8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14, and unchanged1007 original sources. Its immutable checkout contains1111 unique declared source/asset paths. The added price-seed adapter and worker hook leave the97 other Source34 execution files byte-identical, including retained full-LP and RMP policies.

The adapter supplies a separately checked same-current-attempt F1 dual only as computational pricing input at existing L1/L4 calls when the certified input is empty and the certified frontier is zero. Existing original repair, full-domain certificate, pricing, Frontier and final exact bracket remain authoritative. A negative checked F1 bound is not published as a stronger certified Global LB. Missing or ineligible current state follows the original path. Historical points, checkpoints or Native budgets are not admitted into fresh retries.

- DIAGNOSIS preserves actual saved Source32 first-three evidence and a fresh independent original checker replay. Repaired coupling has48 nonzero rows per day while actual L1/L4 prices were zero-coupling and RMP Pi was unavailable. This establishes a candidate computational input, not a performance result.
- PRICE_REVIEW preserves owner335 and independent335 selected production tests under real constructor/optimizer denial, raw XML/logs, historical draft failures, static reviews and hook preview. All1007 originals and97 other Source34 execution files matched; Native/model0 qualification is not actual date PASS.
- DEPLOYMENT preserves actual27 sealed fresh request admissions, completed nine-READY enqueue at2026-10-09T23:43:29.107706+00:00, released lease at23:43:33.511935+00:00, and the independent read-only deployment audit finished23:47:30.751429+00:00. Nine unstarted Source34 repairs were superseded; the three existing Source32 worker identities and completed Native prefixes were preserved. The first-three actual Source35 scientific outcomes remained pending at that audit time.

The saved hourly configuration verification is ACTIVE and reports no actual scheduled run observed. These timestamped deployment/configuration and Native0 test records do not establish Source35 day or month performance, final Global Gap or date PASS. Existing subpackage raw evidence and historical failures remain intact. No science, worker, process, queue, lease, manifest or Git changes were made by the documentation packagers.

Each subpackage retains raw-byte provenance and SHA inventories. The top SHA_INVENTORY.json covers all Source35 documentation except itself. Producer receipt PASS fields are read in their stated qualification scope; they are not interpreted as final scientific PASS.
'''
save(TOP/'README.md',top_readme.encode('utf-8'))
top_records=tree(TOP)
json_save(TOP/'SHA_INVENTORY.json',dict(schema='V42_SOURCE35_ALL_DOCUMENTATION_SHA_INVENTORY_V1',
    UTC=now(),PASS=True,files=top_records,excludes_only='SHA_INVENTORY.json'))
for p,expected in dep_records.items():assert rec((DEST/p).read_bytes())==expected
for p,expected in top_records.items():assert rec((TOP/p).read_bytes())==expected
for name,expected in old_subpackages.items():assert tree(TOP/name)==expected
print(json.dumps(dict(PASS=True,path=str(TOP),deployment_files=len(tree(DEST)),
    total_files=len(tree(TOP)),total_bytes=sum(p.stat().st_size for p in TOP.rglob('*') if p.is_file()),
    top_inventory=rec((TOP/'SHA_INVENTORY.json').read_bytes()),
    deployment_inventory=rec((DEST/'SHA_INVENTORY.json').read_bytes()),
    additive_provenance=rec((DEST/'ADDITIVE_PROVENANCE_SHA_INDEX.json').read_bytes()),
    independent_raw_files=len(provenance),prior_subpackages_unchanged=True),indent=2))
