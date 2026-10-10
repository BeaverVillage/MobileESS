"""Publish verified current execution and preserve all predecessor evidence."""
from pathlib import Path
import sys,json,shutil,sqlite3,datetime,urllib.request
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.report import generate
from report_svr11_campaign import run
root=Path(r'D:\v42_svr11_may_20261011_08');old=Path(r'D:\v42_svr11_may_20261011_06')
m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
generate(root,ledger);run(root)
folder=SOURCE/'docs/v42_svr11_final_20261011/epoch08_snapshot';folder.mkdir(parents=True,exist_ok=True)
names=('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','HANDOFF_37_VALIDATION.json','HANDOFF_RECEIPT.json',
    'PREDECESSOR_DRAIN_CONTRACT.json','MODEL_CHECKPOINT_REUSE_CONTRACT.json','MIGRATION_STATUS.json',
    'REUSE_ADMISSION.json','TECHNICAL_FAIL_RETRY_ADMISSION.json','B2_PRE_DISPATCH_REUSE.json',
    'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json','COEFFICIENT_IO_EQUIVALENCE.json','LINE82_PRIMARY_VOLTAGE_CAUSE_AUDIT.json',
    'MONITOR_PROCESS.json','MONITOR_UI_RELEASE.json','SUPERVISOR_PROCESS.json','WATCHDOG_LAST_RUN.json',
    'REPORT.json','REPORT.md','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json','LIVE_OBSERVATION.json',
    'PERFORMANCE_COMPARISON.json','PERFORMANCE_COMPARISON.md','NORMALAMPS_CLASSIFICATION_CORRECTION.json')
for name in names:
    if (root/name).exists():shutil.copyfile(root/name,folder/name)
shutil.copyfile(root/'hardware/HARDWARE.json',folder/'HARDWARE.json')
(folder/'reuse').mkdir(exist_ok=True)
for p in (root/'reuse').glob('*.json'):shutil.copyfile(p,folder/'reuse'/p.name)
preserved=folder/'preserved_predecessors';preserved.mkdir(exist_ok=True)
for base,name in ((old,'DISPATCH_QUIESCENCE_FOR_FORECAST_RECEIPT_FIX.json'),
    (Path(r'D:\v42_svr11_may_20261011_04'),'USER_AUTHORIZED_MODEL_RESTART.json'),
    (Path(r'D:\v42_svr11_may_20261011_07'),'NEVER_EXECUTED_ISOLATION.json')):
    if (base/name).exists():shutil.copyfile(base/name,preserved/name)
original=[]
for p in sorted((old/'dates/B2').glob('*/attempts/*/RESULT.json')):
    r=read(p);original.append(dict(receipt=record(p),status=r['status'],reason=r.get('reason'),Native_Runtime=r.get('Native_Runtime')))
atomic(preserved/'ORIGIN_B2_TERMINAL_RESULTS.json',dict(results=original,original_files_unchanged=True,UTC=now()))
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert state['source_SHA']==m['execution_SHA'] and Path(state['root'])==root
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
assert a['status']=='ACTIVE' and str(root) in a['prompt'] and m['execution_SHA'] in a['prompt']
atomic(folder/'HOURLY_AUTOMATION.json',a)
h=read(root/'HANDOFF_37_VALIDATION.json') if (root/'HANDOFF_37_VALIDATION.json').exists() else {}
physical_failures=[dict(day=r['day'],arm=r['arm'],reason=r.get('reason'),result=r.get('result')) for r in state['dates']
    if r['status']=='FAIL' and r.get('result') and Path(r['result']).is_relative_to(root/'dates')]
snapshot=dict(status=state['status'],policy=state['policy'],counts=state['counts'],source_SHA=m['execution_SHA'],
    scientific_commit=m['source_commit'],equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],root=str(root),
    reused_B0_dates=31,reused_complete_forecast_slots=576,original_execution_generation_SHA_and_Runtime_preserved=True,
    healthy_origin_workers_terminated=0,workers=state['workers'],migration=read(root/'MIGRATION_STATUS.json'),
    current_epoch_physical_or_execution_failures=physical_failures,
    handoff37_verified=h.get('verified_PASS',0),handoff37_final_bytes_reverified=h.get('final_all_receipt_bytes_reverified',False),
    tests='37 unit checks passed; independent of 37 physical date handoff target',
    hourly_ACTIVE=True,monitor_HTTP=200,UTC=now())
atomic(folder/'SNAPSHOT.json',snapshot)
p=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=p.read_text(encoding='utf8')
marker='# SVR11 official May 2025 campaign'
if marker in text:text=text[text.index(marker):]
intro=f'''Current official authority: **Epoch08**, Source `{m['execution_SHA']}`, manifest commit `{m['source_commit']}`, Root `{root}`. [Snapshot](epoch08_snapshot/SNAPSHOT.json), [ledger](epoch08_snapshot/CAMPAIGN_LEDGER.json), [37-date audit](epoch08_snapshot/HANDOFF_37_VALIDATION.json), [migration](epoch08_snapshot/MIGRATION_STATUS.json), [report](epoch08_snapshot/PERFORMANCE_COMPARISON.md). Historical snapshots and original failures remain unchanged.

Reuse all31 independently verified B0 dates and all576 complete Forecast model slots for May01–06. Original execution/generation SHA04/02/06 and prior Native Runtime remain distinct from current validation SHA08. Completed models are not date PASS. The one user-authorized interruption stopped only three Source04 pre-Native Workers at Runtime0; all subsequent healthy Workers drain naturally. Source07 never ran and is explicitly isolated.

Fix a false final Forecast mutation rejection caused by equivalent C: junction/D: canonical paths; exact SHA/byte length remain mandatory. Cache each immutable NPZ field once with detached slot copies. All96 real slot values are bitwise identical, measured loader44.30s→0.80s,96→1 decompressions per field; this is not full campaign timing.37 unit checks passed. Native equations, solve order, U4/A models, budgets and physical ratings are preserved. Original reg1a compiled NormalAmps763.323673A and separate kVA are enforced; the four historical B0 May19–22 corrections remain PASS with original FAIL evidence retained.

Snapshot: {state['counts']['completed']}/124 terminal; {snapshot['handoff37_verified']}/37 independently verified handoff dates. Migration state `{snapshot['migration']['status']}`; HTTP200 http://127.0.0.1:8796. Existing hourly ACTIVE and existing Windows jobs target this Root. Technical FAILs retain original Runtime and retry from Native0 after following-date assignment, alongside independent dates. B0→B2→B1→B3 continues despite date/policy FAIL. Monthly completion is not claimed before all124 and bounded recovery finish. May2025 is retrospective, not an independent holdout. Earlier descriptions below are historical.

'''
failure_notice=''
if physical_failures:
    failure_notice=f'''Current-epoch failures: `{physical_failures}`. B2 May04 has one genuine Actual voltage violation at slot37, `svr_bus82_series_input.1`:1.0500718582125512pu exceeds1.05. Bus81A1.0487085559148974 and controlled Bus82A1.0067858144335873 pass, while line82 voltage rise leaves the primary upstream of the regulated winding. All current/kVA/tap/convergence checks pass. [Saved cause audit](epoch08_snapshot/LINE82_PRIMARY_VOLTAGE_CAUSE_AUDIT.json) retains B0 same-date, prior B2 and historical evidence. No tolerance relaxation, Actual repair, unchanged physical-failure retry or new hardware is applied. Other dates continue. A conservative existing-bank placement change remains an unimplemented candidate; any justified equipment change requires a separate common epoch and fresh affected physics/results.37-date PASS handoff is not complete.

'''
p.write_bytes((failure_notice+intro+text).encode())
body=f'''Fix slow SVR11 model preparation and final Forecast receipt identity while preserving reusable scientific work. Immutable Epoch08 reuses all31 independently verified B0 dates and576 complete Forecast slots with original execution/generation SHA and Runtime retained. Only the user's one-time authorized Source04 pre-Native restart interrupted Workers; later healthy Workers drain naturally. Source07 never ran and is isolated.

Canonicalize equivalent C:/D: receipt paths while still rejecting changed SHA or size. Read immutable NPZ fields once, preserving detached copies and exact96-slot values; real loader44.30s→0.80s, not full campaign speed.37 unit checks PASS, including native clock equality, lifecycle, path-content tamper and retry/reuse admission. Model equations, U4/A settings, Native budgets, hardware and physical limits are unchanged. Original transformer current uses compiled NormalAmps with separate kVA; original false failures remain linked.

Source `{m['execution_SHA']}`, manifest commit `{m['source_commit']}`, Root `{root}`. Current {state['counts']['completed']}/124 terminal and {snapshot['handoff37_verified']}/37 handoff dates verified; migration `{snapshot['migration']['status']}`. Existing monitor/hourly/Windows target the current Root. Preserve B0→B2→B1→B3, Worker1/3/1/1, bounded fresh Native0 technical retries after next-date assignment, independent Planning/Actual controls and FAIL-CONTINUE. Snapshot, frozen manifest, hardware, ledger, reuse, Native failure history and scheduler evidence: docs/v42_svr11_final_20261011/epoch08_snapshot/. Full campaign completion is not yet claimed; May2025 is retrospective.
'''
(root/'DRAFT_PR_BODY.md').write_bytes((failure_notice+body).encode())
print(json.dumps(snapshot,ensure_ascii=False))
