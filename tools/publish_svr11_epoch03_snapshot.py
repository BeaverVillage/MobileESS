"""Read-only publication; captures incomplete state without changing science."""
from pathlib import Path
import sys,json,shutil,sqlite3,datetime,urllib.request,re
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic,read,record,now
from v42_svr11.authority import verify
root=Path(r'D:\v42_svr11_may_20261011_03');old=Path(r'D:\v42_svr11_may_20261011_02')
m=verify(root/'CAMPAIGN_MANIFEST.json');folder=SOURCE/'docs/v42_svr11_final_20261011/epoch03_snapshot'
folder.mkdir(parents=True,exist_ok=True)
names=['CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','PREDECESSOR_DRAIN_CONTRACT.json','MIGRATION_STATUS.json',
       'MONITOR_PROCESS.json','MONITOR_UI_RELEASE.json','NORMALAMPS_CLASSIFICATION_CORRECTION.json',
       'WINDOWS_SCHEDULE_REGISTRATION.json','HANDOFF_37_VALIDATION.json','REPORT.md','REPORT.json']
receipts=[]
for name in names:
    if (root/name).exists():shutil.copyfile(root/name,folder/name);receipts.append(record(folder/name))
for name in ('NORMALAMPS_FOUR_DAY_REASSESSMENT.json','WORKER_CWD_DIAGNOSIS.json','LATEST_POLICY_TRANSITION.json'):
    shutil.copyfile(old/name,folder/name);receipts.append(record(folder/name))
shutil.copyfile(old/'CAMPAIGN_LEDGER.json',folder/'PRESERVED_EPOCH02_LEDGER.json')
shutil.copyfile(root/'hardware/HARDWARE.json',folder/'HARDWARE.json')
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as r:state=json.load(r)
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
automation=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
automation['next_run_KST']=datetime.datetime.fromtimestamp(automation['next_run_at']/1000,
    datetime.timezone(datetime.timedelta(hours=9))).isoformat()
atomic(folder/'HOURLY_AUTOMATION.json',automation)
proof=read(old/'NORMALAMPS_FOUR_DAY_REASSESSMENT.json')
v=dict(status=state['status'],source_SHA=m['execution_SHA'],scientific_source_commit=m['source_commit'],
    equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],root=str(root),counts=state['counts'],
    corrected_historical_B0_May19_22_all_PASS=proof['all_four_contract_reassessment_PASS'],
    official_successor_results_promoted=False,healthy_science_terminated=0,regression='118 passed, 1 skipped',
    monitor_HTTP=200,hourly_ACTIVE=automation['status']=='ACTIVE',hourly_observed_successor_run=False,
    receipts=receipts,UTC=now())
atomic(folder/'SNAPSHOT.json',v)
readme=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=readme.read_text(encoding='utf8')
start=text.index('Observed physical FAILs are retained.')
text=text[:start]+'''Epoch02's May19–22 FAIL labels were classifier defects: the original thermal Source authority uses compiled NormalAmps only, with independent winding kVA. It does not impose an additional synthesized nominal phase-current limit. The full 96-slot Planning/Actual data of all four dates pass unchanged NormalAmps, winding kVA, 0.95–1.05 voltage, and added-SVR finite phase ratings. The original reg1a limit is 763.323673207438 A; Actual primary A-phase peaks are 718.868929984, 701.565149396, 736.240955431 and 699.766016938 A. The original nominal-current diagnostics remain recorded. Earlier FAIL results, ledger and published Epoch02 snapshot are preserved; their claim that the extra original nameplate-current guard was mandatory is superseded by [the correction evidence](epoch03_snapshot/NORMALAMPS_FOUR_DAY_REASSESSMENT.json).

Epoch03 corrects this original-transformer classifier and the process guard that mistook native OpenDSS Compile/Redirect's temporary cwd for checkout drift. Only the exact audited master/pcc/ratings/phase_pv asset-parent directories are admitted alongside the exact request code root. PID/create-time/command, source identity, request ownership, other-epoch exclusion and worker caps remain mandatory. Legacy studies keep their historical classifier; added SVRs retain finite per-phase current and kVA limits, original winding kVA and all line ratings remain unchanged.

The frozen migration gate preserves healthy Epoch02 B2 workers until natural completion, then starts Epoch03's common all-124-day campaign. No live scientific code is patched and no old result is promoted. The independently sealed dashboard can display the pending migration and predecessor workers separately. Existing Windows tasks and the hourly heartbeat use `tools/svr11_monitor_ui.py safeguard`, which invokes the frozen migration gate and recovers only the read-only HTTP process while predecessor science drains. Policy-boundary stall checks explicitly require B0→B2→B1→B3 progression despite FAIL dates, with bounded technical retries only after dispatching the next independent date, each new attempt beginning at Native zero.

Current immutable scientific Source SHA: `d8f3aea83a2b7257511762fbb480892dd2fb308b051fa904b21b097b9d0bbd31`; scientific commit: `21183dac093e8665965d087c1aaff52cdb622576`. Current Root: `D:\\v42_svr11_may_20261011_03`; checkout: `D:\\v42_svr11_epoch03_20261011`. Equipment SHA remains `bb81b33f497c0967dee83ae0843cc54981e167c3ea7733ad1e3bb8dc2b0b2fed`. [Epoch03 execution snapshot](epoch03_snapshot/SNAPSHOT.json), [ledger](epoch03_snapshot/CAMPAIGN_LEDGER.json), [migration status](epoch03_snapshot/MIGRATION_STATUS.json), [hardware](epoch03_snapshot/HARDWARE.json), [hourly registration](epoch03_snapshot/HOURLY_AUTOMATION.json) and [monitor state](epoch03_snapshot/MONITOR_STATE.json) explicitly distinguish registration/pending state from actual execution. The 37-date handoff remains incomplete until the successor's own all-37 original evidence is verified. Regressions: 118 passed, 1 skipped; no extra monthly AC-only study or new scientific Native experiment.
'''
text=text.replace('Runtime root: `D:\\v42_svr11_may_20261011_02`. Entry points:',
    'Historical Epoch02 entry points (preserved for provenance; current launch uses the Epoch03 safeguard below):')
text='''Current official epoch: **Epoch03**. It corrects the original-transformer NormalAmps classifier and transient OpenDSS cwd guard; physical hardware is unchanged. Read [the current execution snapshot](epoch03_snapshot/SNAPSHOT.json) and the correction/migration notes below. Historical Epoch02 results remain intact.

'''+text if not text.startswith('Current official epoch:') else text
readme.write_bytes(text.encode('utf8'))
body=f'''Correct the SVR11 original-transformer classifier: the shared Source thermal contract uses compiled NormalAmps (reg1a 763.323673207438 A), with independent winding kVA. An extra synthesized 693.930612 A phase-current guard caused four incorrect B0 FAIL labels. Every original 96-slot Planning/Actual receipt for May19–22 passes the unchanged NormalAmps/kVA/voltage/finite added-SVR contract; immutable old evidence and an explicit correction receipt are retained.

The release also admits only audited DSS asset-parent cwd directories during native Compile/Redirect, preserving exact source/root/PID/command binding. A frozen migration gate lets healthy predecessor B2 workers finish, then executes the common Source Epoch03 B0→B2→B1→B3 campaign with 1/3/1/1 workers, FAIL-CONTINUE and bounded next-date-first Native0 retries. No predecessor result is promoted. Equipment/settings, U4 M1800/A5400 budgets, independent Actual control and no Actual repair are unchanged. No monthly AC-only canary is added.

Validation: 118 passed, 1 skipped. Current snapshot: {state['status']}, {state['counts']['completed']}/124 official successor dates; historical four-day correction is PASS, successor 37-date handoff is still incomplete. Hourly automation ACTIVE, existing Windows Supervisor/Monitor tasks retargeted without duplicates; live monitor HTTP200 at http://127.0.0.1:8796.

Scientific Source SHA `{m['execution_SHA']}`; scientific commit `{m['source_commit']}`; equipment SHA `{v['equipment_SHA']}`. Runtime Root `D:\\v42_svr11_may_20261011_03`. Evidence: `docs/v42_svr11_final_20261011/epoch03_snapshot/` and preserved `epoch02_snapshot/`. This retrospective May03-informed design is not an independent May holdout. Full campaign completion is not claimed.
'''
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode('utf8'))
print(json.dumps(v,ensure_ascii=False))
