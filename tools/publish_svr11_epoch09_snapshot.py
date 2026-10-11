"""Publish current physical epoch without promoting predecessor numerical work."""
from pathlib import Path
import sys,json,sqlite3,datetime,urllib.request,shutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.report import generate
from report_svr11_campaign import run

root=Path(r'D:\v42_svr11_may_20261011_09');old=Path(r'D:\v42_svr11_may_20261011_08')
m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
generate(root,ledger);run(root)
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert state['source_SHA']==m['execution_SHA'] and Path(state['root']).resolve()==root
folder=SOURCE/'docs/v42_svr11_final_20261011/epoch09_snapshot';folder.mkdir(parents=True,exist_ok=True)
for name in ('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','EQUIPMENT_CHANGE_CONTRACT.json',
    'PREDECESSOR_DRAIN_CONTRACT.json','MIGRATION_STATUS.json','SOURCE_SCOPE_VERIFICATION.json','REGRESSION_VALIDATION.json',
    'REPORT.json','REPORT.md','PERFORMANCE_COMPARISON.json','PERFORMANCE_COMPARISON.md',
    'MONITOR_UI_RELEASE.json','MONITOR_PROCESS.json','MONITOR_RESTART_RECEIPT.json','LIVE_OBSERVATION.json','WATCHDOG_LAST_RUN.json',
    'SUPERVISOR_PROCESS.json','SUPERVISOR_HEARTBEAT.json','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json',
    'HANDOFF_37_VALIDATION.json','HANDOFF_RECEIPT.json'):
    if (root/name).exists():shutil.copyfile(root/name,folder/name)
(folder/'hardware').mkdir(exist_ok=True)
for p in (root/'hardware').glob('*.json'):shutil.copyfile(p,folder/'hardware'/p.name)
atomic(folder/'MONITOR_STATE.json',state)
c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
    ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
assert a['status']=='ACTIVE' and str(root) in a['prompt'] and m['execution_SHA'] in a['prompt']
a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
atomic(folder/'HOURLY_AUTOMATION.json',a)
origin=read(old/'CAMPAIGN_LEDGER.json');view=[]
for key,row in origin['dates'].items():
    path=Path(read(row['request'])['result']) if row.get('request') and row.get('status')=='RUNNING' else Path(row['result']) if row.get('result') else None
    if path and path.exists():
        r=read(path);view.append(dict(key=key,original_ledger_status=row['status'],
            result_status=r['status'],source_SHA=r['source_SHA'],Native_Runtime=r.get('Native_Runtime'),
            reason=r.get('reason'),result=record(path),counted_in_current_epoch=False))
atomic(folder/'PRESERVED_EPOCH08_RESULTS.json',dict(original_ledger=record(old/'CAMPAIGN_LEDGER.json'),
    results=view,original_files_modified=False,quiesced_ledger_may_still_show_naturally_finished_workers_running=True,UTC=now()))
h=read(root/'HANDOFF_37_VALIDATION.json') if (root/'HANDOFF_37_VALIDATION.json').exists() else {}
handoff=read(root/'HANDOFF_RECEIPT.json') if (root/'HANDOFF_RECEIPT.json').exists() else {}
handoff_complete=bool(h.get('PASS') and h.get('verified_PASS')==37 and
    h.get('final_all_receipt_bytes_reverified') and handoff.get('PASS') and
    handoff.get('source_SHA')==m['execution_SHA'])
handoff_status=('All37 handoff dates are independently verified PASS and live scheduled recovery handoff is complete. '
    'The campaign processes continue toward all124 dates; full campaign completion remains pending.'
    if handoff_complete else '37-date handoff and full campaign completion are pending.')
snap=dict(root=str(root),source_SHA=m['execution_SHA'],manifest_commit=m['source_commit'],
    equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],counts=state['counts'],policy=state['policy'],
    migration=read(root/'MIGRATION_STATUS.json'),workers=state['workers'],
    monitor_URL='http://127.0.0.1:8796',hourly_ACTIVE=True,handoff37_verified=h.get('verified_PASS',0),
    handoff37_complete=handoff_complete,
    old_equipment_numerical_results_or_models_promoted=0,monthly_campaign_complete=False,UTC=now())
atomic(folder/'SNAPSHOT.json',snap)
p=SOURCE/'docs/v42_svr11_final_20261011/README.md';previous=p.read_text(encoding='utf8')
marker='<!-- EPOCH09_CURRENT_END -->'
if marker in previous:previous=previous.split(marker,1)[1].lstrip()
intro=f'''Current official common equipment: **Epoch09**. Source `{m['execution_SHA']}`, manifest commit `{m['source_commit']}`, equipment `{snap['equipment_SHA']}`, Root `{root}`. [Snapshot](epoch09_snapshot/SNAPSHOT.json), [ledger](epoch09_snapshot/CAMPAIGN_LEDGER.json), [placement evidence](epoch09_snapshot/EQUIPMENT_CHANGE_CONTRACT.json), [physical freeze](epoch09_snapshot/hardware/HARDWARE.json), [source scope](epoch09_snapshot/SOURCE_SCOPE_VERIFICATION.json), [report](epoch09_snapshot/PERFORMANCE_COMPARISON.md), [preserved origin results](epoch09_snapshot/PRESERVED_EPOCH08_RESULTS.json).

Epoch08 B2 May04 and May05 both have genuine Actual voltage failures at the unregulated line82 receiving-side SVR8 primary. Preserve those failures and all prior PASS/FAIL results. Relocate **the existing SVR8** before original Line.l82, retain remote Bus82 A/B/C sensing and all settings/ratings; exactly11 banks and original RegControl7/capacitors4 remain. Original line impedance, length, phases and400A are preserved. Only minimum connection/compile/rating/controller checks and one AC timestamp passed. This is retrospective engineering, not monthly safety certification or independent holdout.

Native U4/A models, algorithms, domains, objective and budgets remain unchanged. All network-coupled official physics/results and Forecast sensitivities require fresh computation under this new common equipment. Reuse exact raw inputs and descriptors; promote zero prior-equipment dates/models. Source08 numerical results remain separate history. Healthy origin Workers finish naturally, with zero terminations or hot patches; frozen migration then starts B0→B2→B1→B3, Worker1/3/1/1, all124 despite date/policy FAIL. Technical retries are finite fresh Native0 attempts after following-date allocation. Actual controls remain independent of Planning and Actual repair/reoptimization remain0.

Current {state['counts']['completed']}/124 terminal, {snap['handoff37_verified']}/37 independently verified handoff dates; migration `{snap['migration']['status']}`. [37-date verification](epoch09_snapshot/HANDOFF_37_VALIDATION.json), [live recovery handoff](epoch09_snapshot/HANDOFF_RECEIPT.json). Monitor HTTP200 at http://127.0.0.1:8796. Existing hourly ACTIVE and two Windows jobs now target Epoch09. {handoff_status}

B2 May06 first attempt failed on Windows progress-file replacement after Native169.08799982070923s; retain that FAIL and all receipts. After allocating following dates, attempt2 restarted at Native0, reused the same frozen96-slot model, and completed with Native160.02400016784668s and independently verified full physical PASS. The monitor now distinguishes retry stage and preserved/recovered errors. Only the independent HTTP process was restarted for this display update. Earlier sections below are preserved historical epochs.

{marker}

'''
p.write_bytes((intro+previous).encode())
body=intro.split(marker)[0].replace('](epoch09_snapshot/',
    '](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-svr11-final-may-20261011-epoch09/docs/v42_svr11_final_20261011/epoch09_snapshot/')
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode())
print(json.dumps(snap,ensure_ascii=False))
