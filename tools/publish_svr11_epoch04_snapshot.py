"""Publish current actual execution and preserved corrections without new AC."""
from pathlib import Path
import sys,json,shutil,sqlite3,datetime,urllib.request
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
root=Path(r'D:\v42_svr11_may_20261011_04');old=Path(r'D:\v42_svr11_may_20261011_03');original=Path(r'D:\v42_svr11_may_20261011_02')
m=verify(root/'CAMPAIGN_MANIFEST.json');folder=SOURCE/'docs/v42_svr11_final_20261011/epoch04_snapshot';folder.mkdir(parents=True,exist_ok=True)
names=['CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','SUPERVISOR_PROCESS.json','SUPERVISOR_HEARTBEAT.json',
    'MONITOR_PROCESS.json','MONITOR_UI_RELEASE.json','MIGRATION_STATUS.json','PREDECESSOR_DRAIN_CONTRACT.json',
    'WATCHDOG_LAST_RUN.json','CONTEXT_RETENTION_DIAGNOSIS.json','NORMALAMPS_CLASSIFICATION_CORRECTION.json',
    'WINDOWS_SCHEDULE_REGISTRATION.json','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json','HANDOFF_37_VALIDATION.json',
    'REPORT.md','REPORT.json','PERFORMANCE_COMPARISON.md','PERFORMANCE_COMPARISON.json']
receipts=[]
for name in names:
    if (root/name).exists():shutil.copyfile(root/name,folder/name);receipts.append(record(folder/name))
for name in ('DISPATCH_QUIESCENCE_FOR_CONTEXT_FIX.json','SOURCE_EPOCH_SUCCESSOR_ISOLATION.json'):
    shutil.copyfile(old/name,folder/name);receipts.append(record(folder/name))
shutil.copyfile(old/'CAMPAIGN_LEDGER.json',folder/'PRESERVED_EPOCH03_LEDGER.json')
shutil.copyfile(original/'NORMALAMPS_FOUR_DAY_REASSESSMENT.json',folder/'NORMALAMPS_FOUR_DAY_REASSESSMENT.json')
shutil.copyfile(root/'hardware/HARDWARE.json',folder/'HARDWARE.json')
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert state['source_SHA']==m['execution_SHA'] and Path(state['root'])==root
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
atomic(folder/'HOURLY_AUTOMATION.json',a)
v=dict(status=state['status'],policy=state['policy'],counts=state['counts'],source_SHA=m['execution_SHA'],
    scientific_source_commit=m['source_commit'],root=str(root),equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],
    active_workers=state['workers'],corrected_historical_May19_22_PASS=True,old_results_promoted=False,
    healthy_workers_terminated=0,regression='120 passed, 1 skipped',monitor_HTTP=200,hourly_ACTIVE=a['status']=='ACTIVE',
    hourly_observed_successor_run=False,receipts=receipts,UTC=now())
atomic(folder/'SNAPSHOT.json',v)
readme=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=readme.read_text(encoding='utf8')
marker='\n\n# SVR11 official May 2025 campaign'
if text.startswith('Current official epoch:'):text=text[text.index(marker)+2:]
if '\n\nEpoch04 completed-probe lifecycle correction' in text:text=text.split('\n\nEpoch04 completed-probe lifecycle correction')[0]
text='''Current official epoch: **Epoch04**. The original-transformer NormalAmps and audited DSS cwd corrections are retained. After observed predecessor B2 MemoryErrors, only completed model-probe context ownership is retired; physics, independent contexts and optimization are unchanged. [Actual execution snapshot](epoch04_snapshot/SNAPSHOT.json), [ledger](epoch04_snapshot/CAMPAIGN_LEDGER.json), [37-date verification](epoch04_snapshot/HANDOFF_37_VALIDATION.json), [context diagnosis](epoch04_snapshot/CONTEXT_RETENTION_DIAGNOSIS.json) and [dashboard state](epoch04_snapshot/MONITOR_STATE.json). Prior Epoch02/03 evidence is preserved.

'''+text
text=text.replace('Current immutable scientific Source SHA:', 'Prior Epoch03 immutable scientific Source SHA:')
text+='''

Epoch04 completed-probe lifecycle correction

Epoch02 B2 May01–03 naturally failed with MemoryError during forecast-only model preparation, before Native optimization. ClearAll left each finished independent native context reachable through the pinned library's weak-key/strong-value owner registries. Eight empty contexts remained alive after garbage collection; detaching only the exact completed owners let all eight disappear. A solve-free test with sixteen native circuits confirms registry reclamation and rejects prime/nonowned context retirement. Existing CFFI automatic context disposal is preserved; no raw pointer release or context/control-state reuse occurs. Every signed probe still independently recompiles the same Source and forecast prefix, with identical perturbations and detached measurement arrays. No mathematical model, sensitivity definition, equipment, control, tolerance, algorithm or Native allowance changes.

The Epoch03 dispatcher alone was quiesced to prevent new assignments while its existing B0 Worker finished naturally. No scientific Worker or Solver was terminated or hot-patched. Its exact suspended PID/create-time/command and receipt are bound into the successor drain contract; that prior dispatcher must not be resumed. All Epoch02/03 results and ledgers remain immutable and are not promoted into Epoch04. The official Epoch04 Supervisor and dashboard actually started after predecessor workers drained.

Source SHA: `5ccd4ed37f3e7686e8b94ef86e5b14d8f7ceb4509fead55268b7228d47c6cb91`; scientific commit: `0ddd4d646d6331b80e47015ebc300e3f240b26d4`; Root: `D:\\v42_svr11_may_20261011_04`; checkout: `D:\\v42_svr11_epoch04_20261011`. Hardware SHA remains `bb81b33f497c0967dee83ae0843cc54981e167c3ea7733ad1e3bb8dc2b0b2fed`. Tests: 120 passed, 1 skipped. Actual all-124-day B0→B2→B1→B3 execution continues, and the 37-date chat handoff requires Epoch04's own independently verified evidence. The hourly heartbeat and existing five-minute Windows Supervisor/Monitor jobs use the Epoch04 `tools/svr11_monitor_ui.py safeguard` entry point. Dashboard: http://127.0.0.1:8796. Full monthly completion and scheduled Codex-run observation are not claimed from registration alone.
'''
readme.write_bytes(text.encode('utf8'))
body=f'''Correct four B0 May19–22 misclassifications: original transformer current authority is compiled NormalAmps (reg1a 763.323673207438 A) with independent winding kVA. Both 96-slot trajectories for all four dates pass that unchanged contract; the extra synthesized 693.930612 A guard was incorrect. Preserve original data/FAIL history and link an explicit correction.

Also fix exact audited DSS compile-cwd admission and the observed model-probe context retention that caused all three predecessor B2 workers to fail with MemoryError before Native entry. Only exact completed native context owners are detached, preserving CFFI automatic disposal and independently recompiled Source/prefix/perturbation/measurements. No model equations, hardware, automatic controls, U4 algorithm, feasibility rules, native budgets or tolerances change.

Epoch04 actually runs B0→B2→B1→B3 (1/3/1/1 workers), FAIL-CONTINUE and bounded next-date-first Native0 retries. Healthy workers finished naturally; only the predecessor dispatcher was quiesced, and no old result is promoted. Validation: 120 passed, 1 skipped. At this snapshot: {state['counts']['completed']}/124 completed, PASS{state['counts']['PASS']}/FAIL{state['counts']['FAIL']}, current {state['policy']}. The 37-date handoff and full campaign remain incomplete. Existing hourly automation ACTIVE and Windows jobs are retargeted; dashboard HTTP200 at http://127.0.0.1:8796.

Scientific SHA `{m['execution_SHA']}`, commit `{m['source_commit']}`, equipment SHA `{v['equipment_SHA']}`. Runtime `D:\\v42_svr11_may_20261011_04`; evidence `docs/v42_svr11_final_20261011/epoch04_snapshot/`. Preserve prior snapshots. Retrospective design; no independent May holdout or monthly AC-only canary claim.
'''
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode('utf8'))
print(json.dumps({k:value for k,value in v.items() if k!='receipts'},ensure_ascii=False))
