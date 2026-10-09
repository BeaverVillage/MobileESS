"""Preserve owner/actual-startup evidence; independent review is still pending."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
O=Path(__file__).parent;REPO=Path(r'D:\MobileESS_v42_autonomous');D=REPO/'docs/v42_autonomous_may_20261010/CONTROLLER_DUPLICATE_STARTUP'
D.mkdir(exist_ok=False);rows=[]
def cp(p,name):
 b=p.read_bytes();q=D/name;q.parent.mkdir(parents=True,exist_ok=True)
 with q.open('xb') as f:f.write(b)
 assert q.read_bytes()==b
 rows.append(dict(relative_path=q.relative_to(D).as_posix(),source_path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),raw_bytes_identical=True))
for p in sorted(O.iterdir()):
 if p.is_file():cp(p,Path('owner')/p.name)
for p in sorted((O/'actual_periodic_raw').iterdir()):
 if p.is_file():cp(p,Path('owner/actual_periodic_raw')/p.name)
fixture=next((O/'pytest_full').rglob('REAL_WINDOWS_STARTUP_DUPLICATE_NATIVE_DENIED_PROOF.json')).parent
for p in sorted(fixture.rglob('*')):
 if p.is_file():cp(p,Path('actual_isolated_win_mutex_fixture')/p.relative_to(fixture))
first_fixture=next((O/'pytest_targeted').rglob('child_stderr.log')).parent
for name in ['child_stderr.log','child_stdout.log','SUPERVISOR_ERROR.json','CHILD_NATIVE_DENIAL_INSTALLED.json']:
 p=first_fixture/name
 if p.exists():cp(p,Path('historical_initial_fixture_failure')/name)
expected=json.loads((O/'FULL_NATIVE_DENIED_TEST_RECEIPT.json').read_bytes())['source_files_end']
for rel,row in expected.items():
 p=REPO/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];cp(p,Path('source4_raw')/rel)
text='''# Verified duplicate supervisor startup rejection

Status at this package's creation: final owner142 tests PASS; independent142 review pending. The existing Windows periodic task has already loaded the future startup candidate and recorded a verified rejection. Active supervisor107788 and the scientific Source32 workers were not restarted. A coordinator reload is unnecessary for this startup-only path. No Git action was performed by the owner.

The prior five-minute duplicate entry raised canonical `LockBusy` at the global `AUTONOMOUS_SUPERVISOR.lock`. The broad CLI error writer replaced `SUPERVISOR_ERROR.json` with that duplicate error. This repair intercepts only mutex-entry refusal. An exact canonical exception, exact resolved root lock, recognized OS errno, actual live PID/create/command/cwd/executable, and matching heartbeat no older than60seconds are all required. The freshness window establishes operational ownership; it is not a scientific time budget or resource throttle.

Verified duplicate entry creates a unique immutable JSON under `autonomous/startup_rejections` and returns. Existing public error, CP, scientific request/ledger files and lock ownership are untouched. Dead, mismatched, stale, corrupt or unreadable owner proof remains a strict startup error. Different locks, unsupported exceptions, and errors raised after mutex acquisition remain on their existing strict paths. No lock removal, lease breaking, or scientific change is introduced.

Owner results and historical failures:

| Evidence | Outcome | Scope |
|---|---:|---|
| `owner/TARGETED_NATIVE_DENIED_TEST_RECEIPT_02.json` |16 PASS,1 FAIL| Isolated owner child lacked its synthetic continuation manifest; the child remained Native/model-denied |
| `owner/HARNESS_ROOT_PATH_CLONE_FAILURE_03.json` |Tests0| Output-suffix clone accidentally altered the runner root; strict FileNotFound occurred before tests |
| `owner/TARGETED_NATIVE_DENIED_TEST_RECEIPT_04.json` |17 PASS| Corrected targeted fixture before the final mutex-still-held assertion was added |
| `owner/FULL_NATIVE_DENIED_TEST_RECEIPT.json` |142 PASS,10.680s| Final four-file hashes stable; parent and child real model constructors/optimize denied; attempted entries[] |
| `owner/ACTUAL_ISOLATED_WIN_MUTEX_DUPLICATE_PROOF_RECEIPT.json` |PASS| Real canonical supervisor child and real Windows byte-range mutex; duplicate returned and original mutex stayed held |

The isolated proof checks prior error, CP, three sealed-request fixtures and Native-ledger fixtures byte-for-byte. Its child is terminated only as external test teardown. Fictional fixture date PASS and empty ledgers are not scientific evidence. No production process action or Native/model construction occurred in the owner test work.

Actual periodic observation: event`20261009T223320448514_df070a15592346f9b4f2b2dea7531cc4.json` records duplicate98264 and unchanged owner107788 at22:33:20UTC, matching owner heartbeat age about1second. Scheduled task LastRun22:33:20 and result0 support successful rejection. `owner/ACTUAL_PERIODIC_DUPLICATE_STARTUP_READ_ONLY_AUDIT.json` independently verifies unchanged actual OS identities, same sealed requests, preserved completed Native prefixes, and HTTP8794. Current Source32 PIDs are106760/95584/107636; captured Native totals were1240.6150002479553/1246.7820000648499/1005.8949999809265 seconds. Date PASS is not claimed.

The public error file still exactly matched the pre-full-test22:28 LockBusy observation after the22:33 rejection. It had already replaced the original21:38 heartbeat error before this fix; that original evidence remains byte-exact in the separate sealed `CONTROLLER_HEARTBEAT_IO` package. This package does not rewrite that earlier package or retrospectively label the historical sharing cause as proven.

Actual OS task execution was not instrumented by the reviewer; its event declares Native/model0, and the unchanged worker ledgers plus source path support the operational scope. The independent audit itself invoked no Native/model/process action. Operational files/API were captured sequentially at recorded timestamps. Current immutable D32 source was used for science binding while separate Repo Source33 science work proceeded. No solver performance or final scientific PASS is established here.

Raw copied bytes are preserved. `SHA_INVENTORY_PENDING_REVIEW.json` and `SHA256SUMS_PENDING_REVIEW.txt` seal this state. Later independent acceptance can be added separately without altering these historical pending records.
'''
with (D/'README.md').open('x',encoding='utf-8') as f:f.write(text)
b=(D/'README.md').read_bytes();rows.append(dict(relative_path='README.md',source_path=None,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),generated_documentation=True))
inv=D/'SHA_INVENTORY_PENDING_REVIEW.json'
with inv.open('x',encoding='utf-8') as f:json.dump(dict(UTC=datetime.now(timezone.utc).isoformat(),schema='V42_DUPLICATE_STARTUP_SELECTED_EVIDENCE_PENDING_INDEPENDENT_REVIEW',owner142_PASS=True,independent142_review='PENDING',future_startup_applied_by_existing_periodic_task=True,active_owner_loop_not_restarted=True,files=rows,file_count=len(rows),selected_bytes=sum(x['bytes'] for x in rows),raw_copy_byte_identity=True,production_changes_by_packager=0,git_mutations=0),f,ensure_ascii=False,indent=2);f.write('\n')
with (D/'SHA256SUMS_PENDING_REVIEW.txt').open('x',encoding='utf-8') as f:
 for row in rows:f.write(row['sha256']+'  '+row['relative_path']+'\n')
 f.write(hashlib.sha256(inv.read_bytes()).hexdigest()+'  '+inv.name+'\n')
print(json.dumps(dict(PASS=True,path=str(D),selected_files=len(rows),all_files=len(rows)+2,selected_bytes=sum(x['bytes'] for x in rows),inventory_SHA=hashlib.sha256(inv.read_bytes()).hexdigest())))
