"""Publish reuse and migration evidence; never start scientific work."""
from pathlib import Path
import sys,json,shutil,sqlite3,datetime,urllib.request
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.report import generate
from report_svr11_campaign import run
root=Path(r'D:\v42_svr11_may_20261011_05');old=Path(r'D:\v42_svr11_may_20261011_04')
m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
generate(root,ledger);run(root)
folder=SOURCE/'docs/v42_svr11_final_20261011/epoch05_snapshot';folder.mkdir(parents=True,exist_ok=True)
for name in ('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','HANDOFF_37_VALIDATION.json','CALLBACK_CONTEXT_DIAGNOSIS.json',
    'PREDECESSOR_DRAIN_CONTRACT.json','MIGRATION_STATUS.json','REUSE_ADMISSION.json','MONITOR_PROCESS.json',
    'MONITOR_UI_RELEASE.json','SUPERVISOR_PROCESS.json','WATCHDOG_LAST_RUN.json','REPORT.json','REPORT.md',
    'WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json','B2_PRE_DISPATCH_REUSE.json',
    'PERFORMANCE_COMPARISON.json','PERFORMANCE_COMPARISON.md','NORMALAMPS_CLASSIFICATION_CORRECTION.json'):
    if (root/name).exists():shutil.copyfile(root/name,folder/name)
shutil.copyfile(root/'hardware/HARDWARE.json',folder/'HARDWARE.json')
(folder/'reuse').mkdir(exist_ok=True)
for p in (root/'reuse').glob('*.json'):shutil.copyfile(p,folder/'reuse'/p.name)
for name in ('DISPATCH_QUIESCENCE_FOR_CALLBACK_FIX.json','MODEL_TECHNICAL_FIX_EQUIVALENCE.json'):
    shutil.copyfile(old/name,folder/name)
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert state['source_SHA']==m['execution_SHA'] and Path(state['root'])==root
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
atomic(folder/'HOURLY_AUTOMATION.json',a)
snapshot=dict(status=state['status'],policy=state['policy'],counts=state['counts'],source_SHA=m['execution_SHA'],
    scientific_commit=m['source_commit'],equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],root=str(root),
    qualified_reused_completed_dates=sum(bool(r.get('reused')) for r in state['dates']),
    active_workers=state['workers'],healthy_workers_terminated=0,original_execution_SHA_preserved=True,
    independent_handoff37=read(root/'HANDOFF_37_VALIDATION.json')['verified_PASS'],
    callback_and_reuse_regression='31 passed',hourly_ACTIVE=a['status']=='ACTIVE',
    hourly_execution_observed=False,monitor_HTTP=200,UTC=now())
atomic(folder/'SNAPSHOT.json',snapshot)
p=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=p.read_text(encoding='utf8')
marker='\n\n# SVR11 official May 2025 campaign'
if text.startswith('Current official epoch:'):text=text[text.index(marker)+2:]
text=f'''Current official execution authority: **Epoch05**, Source `{m['execution_SHA']}`, scientific commit `{m['source_commit']}`, Root `{root}`. [Current snapshot](epoch05_snapshot/SNAPSHOT.json), [ledger](epoch05_snapshot/CAMPAIGN_LEDGER.json), [reuse receipts](epoch05_snapshot/REUSE_ADMISSION.json), [callback diagnosis](epoch05_snapshot/CALLBACK_CONTEXT_DIAGNOSIS.json), [37-date check](epoch05_snapshot/HANDOFF_37_VALIDATION.json), [dashboard](epoch05_snapshot/MONITOR_STATE.json). Prior epochs and their execution evidence remain preserved.

All **31 completed B0 dates are reused**, with independently rehashed same-equipment/scenario/thermal/input, both96 Planning/Actual full-phase voltage/current/kVA/control/tap checks and Fresh arrays. Original execution SHA is Epoch04 for May01–30 and Epoch02 for May31; validation SHA is Epoch05. No B0 rerun is required or launched. Reuse changes provenance admission, never original result bytes, Runtime, tolerances or physical ratings. Unfinished B2 work is not represented as a completed result.

The additional EventCallbackManager retained native contexts after engine wrappers disappeared. Eight empty retired contexts left nine callback managers (baseline one). The minimal fix lets completed engine/utility destructors finalize first, then drops only their exact retired callback manager. Existing CFFI disposal remains the sole native destructor. Tests cover16 native circuits without solving, all three owner registries and weak native-context reclamation, live owner protection, prime/nonowner rejection and reuse proof tamper/identity rejection;31 passed. No equations, source topology, controls, prefix, optimization policy or Native budget change. Common completed predecessor model arrays30 slots were exactly equal.

The Epoch04 dispatcher alone is quiesced; three existing B2 Workers continue naturally. Frozen migration waits for those Workers, preserving all Native/runtime/result history and avoiding duplicate Workers. The successor starts at B2 because B0 all31 are already independently verified. The same hourly automation and two existing Windows jobs point to checkout05/Root05 safeguard. HTTP200 dashboard remains http://127.0.0.1:8796. At this snapshot the 37-date handoff is **{snapshot['independent_handoff37']}/37**, and full May completion is not claimed. Prior descriptions below are historical snapshots.

'''+text
p.write_bytes(text.encode())
body=f'''Preserve and reuse all31 verified B0 dates instead of resetting completed work for technical corrections. Original result bytes, execution SHA and Runtime are retained; Epoch05 identifies independent same-equipment/input/full96 evidence validation. May01–30 originated in Epoch04 and May31 in Epoch02. Ledger and per-date receipts explicitly distinguish execution and validation authority.

Correct original-transformer current classification to compiled NormalAmps763.323673 A plus separate winding kVA; all four May19–22 original trajectories and later actual reruns PASS. Retain every original FAIL/result/SHA. Added SVR finite-phase ratings and original line ratings remain strict.

Fix exact DSS cwd admission and completed probe ownership. An additional callback-manager registry retained native contexts even after Python engine wrappers disappeared. After owner finalization, retire only exact completed callback managers, retaining CFFI automatic disposal. No physical/model/algorithm/native-budget change. Validation:31 callback/reuse/controller regression tests PASS; prior120 PASS1 skip remain recorded. The old dispatcher is quiesced; healthy B2 Workers continue naturally until frozen successor migration admits B2. B0 is not dispatched again.

Source `{m['execution_SHA']}`, scientific commit `{m['source_commit']}`, equipment `{snapshot['equipment_SHA']}`. Root `{root}`. Current {state['status']}, {state['counts']['completed']}/124 terminal; handoff {snapshot['independent_handoff37']}/37. Existing hourly automation ACTIVE, existing Windows jobs retargeted, HTTP200 http://127.0.0.1:8796. All policy/date FAIL-CONTINUE, Native0 bounded technical retries, independent Planning/Actual automatic controls, U4 M1800 and original A/B3 sequencing remain. Full completion and scheduled Codex execution are not claimed. Evidence: docs/v42_svr11_final_20261011/epoch05_snapshot/. Retrospective design; no independent holdout claim.
'''
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode())
print(json.dumps(snapshot,ensure_ascii=False))
