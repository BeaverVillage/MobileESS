"""Read-only publication of the explicit one-time model restart and reuse."""
from pathlib import Path
import sys,json,shutil,sqlite3,datetime,urllib.request
import psutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.processes import live
from v42_svr11.report import generate
from report_svr11_campaign import run
root=Path(r'D:\v42_svr11_may_20261011_06');old=Path(r'D:\v42_svr11_may_20261011_04')
m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
generate(root,ledger);run(root)
folder=SOURCE/'docs/v42_svr11_final_20261011/epoch06_snapshot';folder.mkdir(parents=True,exist_ok=True)
names=('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','HANDOFF_37_VALIDATION.json',
    'PREDECESSOR_DRAIN_CONTRACT.json','MODEL_CHECKPOINT_REUSE_CONTRACT.json','MIGRATION_STATUS.json',
    'REUSE_ADMISSION.json','MONITOR_PROCESS.json','MONITOR_UI_RELEASE.json','SUPERVISOR_PROCESS.json',
    'WATCHDOG_LAST_RUN.json','REPORT.json','REPORT.md','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json',
    'PERFORMANCE_COMPARISON.json','PERFORMANCE_COMPARISON.md','NORMALAMPS_CLASSIFICATION_CORRECTION.json')
for name in names:
    if (root/name).exists():shutil.copyfile(root/name,folder/name)
shutil.copyfile(root/'hardware/HARDWARE.json',folder/'HARDWARE.json')
(folder/'reuse').mkdir(exist_ok=True)
for p in (root/'reuse').glob('*.json'):shutil.copyfile(p,folder/'reuse'/p.name)
shutil.copyfile(old/'USER_AUTHORIZED_MODEL_RESTART.json',folder/'USER_AUTHORIZED_MODEL_RESTART.json')
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert state['source_SHA']==m['execution_SHA'] and Path(state['root'])==root
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
assert a['status']=='ACTIVE' and str(root) in a['prompt'] and m['execution_SHA'] in a['prompt']
atomic(folder/'HOURLY_AUTOMATION.json',a)
peers=[]
for worker in state['workers']:
    p=psutil.Process(worker['PID']);path=root/'models'/worker['day']/'forecast'
    progress=list((root/'models'/worker['day']).rglob('MODEL_GENERATION_PROGRESS.json'))
    peers.append(dict(worker,RSS_MB=p.memory_info().rss/1024**2,CPU_seconds=sum(p.cpu_times()[:2]),
        model_progress=read(progress[0]) if progress else None))
supervisor=read(root/'SUPERVISOR_PROCESS.json');assert live(supervisor)
snapshot=dict(status=state['status'],policy=state['policy'],counts=state['counts'],source_SHA=m['execution_SHA'],
    scientific_commit=m['source_commit'],equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],root=str(root),
    qualified_reused_completed_dates=sum(bool(r.get('reused')) for r in state['dates']),
    completed_forecast_slots_reused=151,user_authorized_one_time_Native0_interruption_count=3,
    active_workers=peers,supervisor=supervisor,original_execution_SHA_and_Runtime_preserved=True,
    independent_handoff37=read(root/'HANDOFF_37_VALIDATION.json')['verified_PASS'],
    regression='43 passed: native clock equivalence, lifecycle, reuse and controller/Anytime',
    hourly_ACTIVE=True,hourly_execution_observed=False,monitor_HTTP=200,UTC=now())
atomic(folder/'SNAPSHOT.json',snapshot)
p=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=p.read_text(encoding='utf8')
marker='\n\n# SVR11 official May 2025 campaign'
if text.startswith('Current official'):text=text[text.index(marker)+2:]
intro=f'''Current official execution authority: **Epoch06**, Source `{m['execution_SHA']}`, scientific commit `{m['source_commit']}`, Root `{root}`. [Current snapshot](epoch06_snapshot/SNAPSHOT.json), [ledger](epoch06_snapshot/CAMPAIGN_LEDGER.json), [model reuse contract](epoch06_snapshot/MODEL_CHECKPOINT_REUSE_CONTRACT.json), [one-time user-authorized interruption](epoch06_snapshot/USER_AUTHORIZED_MODEL_RESTART.json), [37-date check](epoch06_snapshot/HANDOFF_37_VALIDATION.json), [dashboard](epoch06_snapshot/MONITOR_STATE.json). Previous snapshots and original evidence remain historical and unchanged.

All **31 completed B0 dates are reused** with independent same-equipment/input/full96 Planning/Actual/Fresh/control/physical verification. Execution SHA remains Epoch04 for May01–30 and Epoch02 for May31; validation SHA is Epoch06. B0 is not rerun. The four historical May19–22 false failures retain their original FAIL evidence and compiled NormalAmps763.323673A/separate kVA revalidation and Epoch04 actual rerun PASS.

The user explicitly authorized a single interruption to fix slow model generation. Only the three Epoch04 pre-Native model Workers were terminated, each with Native Runtime0; exact identity and failure receipts remain linked. Epoch06 actually restarted B2 May01–03. Previously completed Forecast slots50/50/51 (151 total) are reused under a frozen original generation SHA, input and array-byte contract; they are partial model evidence, never date PASS. Future healthy Workers are preserved.

Forecast probes still independently compile, replay the same chronological prefix, perturb the same60 controls in both signs and perform all native AC/queue/control checks. They skip only unused EventLog/receipt copies. Real native automatic-regulator circuits give identical voltage, Tap, queue and solve counts in full/fast paths. Finalized completed owner/callback registries are reclaimed with the existing CFFI disposer. Regression43passed. Physics, equations, Native budgets, MILP domains, U4 and A/B3 sequencing are unchanged.

Existing Windows Supervisor/Monitor jobs and the existing hourly ACTIVE automation target checkout06/Root06; no duplicate task was created. HTTP200 http://127.0.0.1:8796 shows the current source. Snapshot handoff is **{snapshot['independent_handoff37']}/37**, terminal dates **{state['counts']['completed']}/124**. All-policy FAIL-CONTINUE and bounded Native0 technical retries remain. Full monthly completion and a completed Codex scheduled execution are not claimed. Earlier descriptions below are historical.

'''
p.write_bytes((intro+text).encode())
body=f'''Fix slow SVR11 forecast-model preparation and preserve reusable results. After the user's explicit one-time restart authorization, stop only three pre-Native Epoch04 model Workers (Runtime0), retain exact identity/FAIL receipts, then actually restart B2 May01–03 in immutable Epoch06. Reuse all31 verified B0 dates and151 completed Forecast model slots with separate original execution/generation SHA and current validation SHA; no full reset or date PASS from partial work.

Skip unused forecast-probe EventLog/receipt copies while retaining independent source compile, chronological prefix, signed perturbations, native solve order and AC/control/queue checks. Retire finalized owner/callback registries using existing CFFI disposal. Validation:43 tests PASS, including real native full/fast voltage/Tap/queue/solve-count equality, owner lifetime, provenance tamper and U4/FAIL-CONTINUE. Original transformer current uses compiled NormalAmps763.323673A plus separate kVA; all four historical May19–22 false failures and later actual reruns PASS. Original FAIL evidence stays intact.

Source `{m['execution_SHA']}`, commit `{m['source_commit']}`, equipment `{snapshot['equipment_SHA']}`, Root `{root}`. Actual Supervisor/Workers/monitor, frozen source/ledger/reuse/interrupt/37-date/Windows/hourly receipts: docs/v42_svr11_final_20261011/epoch06_snapshot/. At snapshot {state['counts']['completed']}/124 terminal and {snapshot['independent_handoff37']}/37 handoff verified; remaining campaign is running. Existing hourly and Windows jobs are retargeted, HTTP200 http://127.0.0.1:8796. Preserve B0→B2→B1→B3 Worker1/3/1/1, U4 M1800 and original A/B3 order, independent Planning/Actual controls, physical ratings and FAIL-CONTINUE. No monthly completion, new holdout, algorithm or equipment-safety certification claim.
'''
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode())
print(json.dumps(snapshot,ensure_ascii=False))
