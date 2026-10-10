"""Copy selected Source32 and undeployed Source31 evidence verbatim into new docs."""
from pathlib import Path
import hashlib,json
from datetime import datetime,timezone
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02')
DEST=REPO/'docs/v42_autonomous_may_20261010/SOURCE32';DEST.mkdir(exist_ok=False)
OUT=Path(__file__).parent;inventory=[];skipped=[]
def rec(path,data):return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def copy(source,target):
    source=Path(source);data=source.read_bytes();target=DEST/target;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(data)
    assert target.read_bytes()==data
    inventory.append(dict(relative_path=target.relative_to(DEST).as_posix(),source=rec(source,data),packaged=rec(target,data)))
def add_folder(source,target,recursive=False):
    source=Path(source)
    for path in sorted(source.rglob('*') if recursive else source.iterdir()):
        if not path.is_file():continue
        if path.suffix.lower() not in ('.json','.py','.md','.patch','.xml','.txt','.log'):continue
        if path.stat().st_size>1500000:
            skipped.append(dict(path=str(path),reason='Large scientific/terminal packet omitted; referenced original SHA remains in raw receipts',bytes=path.stat().st_size));continue
        copy(path,Path(target)/path.relative_to(source))

for path in sorted((ROOT/'autonomous').glob('*')):
    if path.is_file() and ('v32' in path.name.lower() or 'V32' in path.name):copy(path,Path('deployment')/path.name)
copy(ROOT/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json','deployment/B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json')
incident_path=ROOT/'autonomous/SOURCE32_ROOT_LEASE_ENQUEUE_INTERRUPTION_AND_RESUME.json'
incident=json.loads(incident_path.read_text(encoding='utf-8-sig'))
copy(incident_path,'deployment/SOURCE32_ROOT_LEASE_ENQUEUE_INTERRUPTION_AND_RESUME.json')
for lease in incident['leases']:
    source=Path(lease['record']['path'])
    assert rec(source,source.read_bytes())==lease['record']
    copy(source,Path('deployment/released_lease_history')/source.name)
add_folder('D:/v42_source32_cli_identity_review_20261010_01','owner_current188')
add_folder('D:/v42_source32_independent_review_20261010_01','independent_current188')
add_folder(OUT,'execution_audit',recursive=True)

review=Path('D:/v42_full_lp_warmstart_readonly_review_20261010_01')
for name in ('SOURCE32_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW.json','seal_source32_helpers_review.py'):
    copy(review/name,Path('operational_static_review')/name)
add_folder(review/'source32_helper_review_raw','operational_static_review/raw',recursive=True)
for name in ('SOURCE30_ACTUAL_FULL_LP_CAP_AND_SOURCE31_CANDIDATE_PROPOSAL.json','SOURCE31_F1_NATIVE_DENIED_TEST_RECEIPT.json','SOURCE31_F1_NATIVE_DENIED_TEST_RECEIPT_02.json','SOURCE31_F1_NATIVE_DENIED_TEST_RESULT.xml','SOURCE31_F1_NATIVE_DENIED_TEST_RESULT_02.xml','SOURCE31_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW.json','run_source31_native_denied_tests.py','seal_actual_lp_cap_and_proposal.py','seal_source31_helper_static_review.py','stdout.txt','stdout_02.txt','stderr.txt','stderr_02.txt'):
    copy(review/name,Path('SOURCE31_HISTORY/owner_and_actual_LP_caps')/name)
add_folder('D:/v42_b2_v31_independent_review_20261010_01','SOURCE31_HISTORY/independent98')
for name in ('V31_SPARSE_IMMUTABLE_FREEZE.json','V31_VALIDATION_BINDING_TEMPLATE.json','build_v31_operational_helpers.py','build_v31_validation_template.py','freeze_sparse_v31.py','smoke_sparse_v31.py','prepare_verified_v31_zero_start_retries.py','run_v31_native_denied_regressions.py'):
    copy(ROOT/'autonomous'/name,Path('SOURCE31_HISTORY/frozen_not_deployed')/name)
add_folder(ROOT/'autonomous/source30_regression_20261009T212753480380','SOURCE31_HISTORY/integrated305')
for name in ('SOURCE30_CLI_DUPLICATE_BUDGET_IDENTITY_NATIVE0_PROOF.json','SOURCE30_FIRST3_ORIGINAL_FULL_LP_ACTUAL_300_CAP.json'):
    copy(Path('D:/v42_source30_actual_watch_20261010')/name,Path('actual_Source30_failures')/name)

readme='''# Source32 selected evidence and Source31 undeployed history

This package preserves selected raw JSON receipts, denied-test outputs, operational helpers and independent deployment execution observations. Copies keep original bytes. Their absolute references continue to point to the original evidence; this package does not relabel copied proofs as new mathematical authority.

Source32 is the canonical CLI identity repair combined with the previously reviewed same-attempt F1 complete-basis `Method=0`, `LPWarmStart=2` computational candidate. Its immutable checkout is `D:\\v42run32`, commit `6997c0ac54a8d46f345bb99d9b3cf18ffb199a30`, execution98 SHA `9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9`. Original scientific source1007 and the other96 execution files retain their Source30 bytes. The sparse checkout contains98 execution files,1007 original files and5 required assets,1110 unique files.

The current owner and independent selected suites each report188 PASS with real Native optimize/model construction denied. They cover current CLI, worker scope, F1 state/basis and RMP paths. Source31 owner98/independent98/integrated305 records and unchanged Source30 cache120/RMP72 records are historical evidence, not a current Source32 full-suite rerun. Native0 tests, admission smoke and deployment audit are not daily or monthly PASS, and they establish no actual speedup or Global Gap qualification.

The independent deployment audit verified27 distinct sealed fresh0 requests with full5400-second date budgets and no previous checkpoint or Native budget carry. At its timestamp all27 requests had no output, Native ledger or terminal result, and nine new Source32 queues were READY: May01/02/03 priority1000 and May04–09 priority100. Only the three previously unstarted Source30 queues for May07–09 were superseded. May04/05/06 continued on Source30 with the same PID/create/cmd/cwd/request identities (75836/82904/101664) and exact measured Native call prefixes. Their cumulative Native times progressed306.511→477.347,306.674→426.946 and7.322→307.358 seconds. These are timestamped deployment observations; later worker/queue transitions may change status naturally.

Initial Source32 enqueue stopped after four READY when the parent released the manual repair lease too early. The parent reacquired a lease and resumed idempotently. The separate resume observation records that the exception itself is a parent report, while all four original queue IDs/timestamps were independently found exactly once in the final nine-row queue. Raw partial/resume evidence remains separate from the completed deployment receipt. Initial failed test-harness receipts are retained and are not counted as production solver failures.

Source31 remains frozen at `D:\\v42run31`, commit `d9b5c52d3436943a807f0860e2548b029e7f9dc9`, execution SHA `ab7691473aea6d1d5b883afa8bc07ab0d091448c7e3fb0644c4c82f743b3169b`. It was never deployed, queued or run because it retained the Source30 CLI duplicate-class failure. The deployment audit checked its HEAD and all1110 frozen file bytes remained unchanged. Its candidate tests do not repair that separate CLI failure.

Actual Source30 May01/02/03 full LP calls each reached the original300-second policy cap with status11 and SolCount0. Later the three dates failed before Native RMP entry with `RMP_PRESOLVE_ORIGINAL_BUDGET_OR_SCOPE_CLOSURE_DRIFT`, at Native626.365/619.713/660.145 seconds. The Native0 reproduction identifies different `__main__.ReceiptDateBudget` and canonical worker classes despite identical bytecode. Source32 changes the CLI owner, retaining the strict RMP original class/code/scope/closure guard. The LPWarmStart2 candidate changes the computational use of the actual current F1 basis; complete original model, budget and exact scientific checkers remain required. Actual Source32 RMP execution,300-cap behavior, independent Global LB and final three-date PASS remain pending at this audit timestamp.

Full13MB terminal/scientific packets, models and large matrix data are omitted. Their original paths/SHA references remain in raw JSON receipts. SHA inventory records each included source and copied byte hash. No production, immutable checkout, queue, process or Native/model changes were made by this packaging/audit work. Git commit/push belongs to the parent task.
'''
target=DEST/'README.md';data=readme.encode('utf-8');target.write_bytes(data)
inventory.append(dict(relative_path='README.md',source=None,packaged=rec(target,data)))
index=dict(schema='V42_SOURCE32_SELECTED_EVIDENCE_BYTE_INVENTORY',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
    copied_raw_bytes_preserved=True,entries=inventory,omitted=skipped,production_changes=0,git_mutations=0)
target=DEST/'SHA_INVENTORY.json';data=(json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode('utf-8');target.write_bytes(data)
sum_rows=[(row['relative_path'],row['packaged']['sha256']) for row in inventory]+[('SHA_INVENTORY.json',hashlib.sha256(data).hexdigest())]
sums=DEST/'SHA256SUMS.txt';sums.write_text(''.join(sha+'  '+name+'\n' for name,sha in sorted(sum_rows)),encoding='utf-8')
for row in inventory:assert rec(DEST/row['relative_path'],(DEST/row['relative_path']).read_bytes())==row['packaged']
handoff=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),root=str(DEST),files=len(list(DEST.rglob('*')))-len([p for p in DEST.rglob('*') if p.is_dir()]),
    bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),inventory=rec(target,data),SHA256SUMS=rec(sums,sums.read_bytes()),README=rec(DEST/'README.md',(DEST/'README.md').read_bytes()),omitted=skipped)
target=OUT/'SOURCE32_SELECTED_DOCS_PACKAGE_HANDOFF.json'
with target.open('x',encoding='utf-8') as stream:json.dump(handoff,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(handoff,ensure_ascii=False))
