"""Publish an exact-cache execution epoch with explicit reused provenance."""
from pathlib import Path
import sys,json,sqlite3,datetime,urllib.request,shutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.report import generate
from report_svr11_campaign import run

ROOT=Path(r'D:\v42_svr11_may_20261011_10');OLD=Path(r'D:\v42_svr11_may_20261011_09')

def publish():
    m=verify(ROOT/'CAMPAIGN_MANIFEST.json');ledger=read(ROOT/'CAMPAIGN_LEDGER.json')
    generate(ROOT,ledger);run(ROOT)
    with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
    assert state['source_SHA']==m['execution_SHA'] and Path(state['root']).resolve()==ROOT
    folder=SOURCE/'docs/v42_svr11_final_20261011/epoch10_snapshot';folder.mkdir(parents=True,exist_ok=True)
    names=('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','PREDECESSOR_DRAIN_CONTRACT.json','MIGRATION_STATUS.json',
        'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json','MODEL_CHECKPOINT_REUSE_CONTRACT.json','REUSE_ADMISSION.json','B2_PRE_DISPATCH_REUSE.json',
        'TRANSFER_INTENT.json','TRANSFER_COMPLETE.json','SOURCE_SCOPE_VERIFICATION.json','REPORT.json','REPORT.md',
        'PERFORMANCE_COMPARISON.json','PERFORMANCE_COMPARISON.md','MONITOR_UI_RELEASE.json','MONITOR_PROCESS.json',
        'LIVE_OBSERVATION.json','WATCHDOG_LAST_RUN.json','SUPERVISOR_PROCESS.json','SUPERVISOR_HEARTBEAT.json',
        'WINDOWS_SCHEDULE_REGISTRATION.json','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json','HANDOFF_37_VALIDATION.json','HANDOFF_RECEIPT.json')
    for name in names:
        if (ROOT/name).exists():shutil.copyfile(ROOT/name,folder/name)
    (folder/'hardware').mkdir(exist_ok=True)
    for p in (ROOT/'hardware').glob('*.json'):shutil.copyfile(p,folder/'hardware'/p.name)
    (folder/'benchmarks').mkdir(exist_ok=True)
    for r in read(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json')['benchmarks']:
        shutil.copyfile(r['path'],folder/'benchmarks'/(Path(r['path']).parent.name+'.json'))
    for name in ('ALL_FORECAST_INPUT_EQUIVALENCE.json','REGRESSION.json'):
        shutil.copyfile(ROOT/'model_benchmarks'/name,folder/'benchmarks'/name)
    (folder/'reuse').mkdir(exist_ok=True)
    for p in (ROOT/'reuse').glob('*_B*.json'):shutil.copyfile(p,folder/'reuse'/p.name)
    atomic(folder/'MONITOR_STATE.json',state)
    c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
    a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
        ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
    assert a['status']=='ACTIVE' and str(ROOT) in a['prompt'] and m['execution_SHA'] in a['prompt']
    a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    atomic(folder/'HOURLY_AUTOMATION.json',a)
    atomic(folder/'PRESERVED_EPOCH09_HISTORY.json',dict(original_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),
        original_quiesced_ledger=record(OLD/'CAMPAIGN_LEDGER.json'),isolation=record(OLD/'SOURCE_EPOCH_SUCCESSOR_ISOLATION.json'),
        original_failed_attempts=[record(p) for p in (OLD/'dates').rglob('RESULT.json') if not read(p).get('PASS')],
        equipment_unchanged=True,qualified_reuse_execution_SHA_retained=True,original_files_modified=False,UTC=now()))
    h=read(ROOT/'HANDOFF_37_VALIDATION.json') if (ROOT/'HANDOFF_37_VALIDATION.json').exists() else {}
    handoff=read(ROOT/'HANDOFF_RECEIPT.json') if (ROOT/'HANDOFF_RECEIPT.json').exists() else {}
    models=read(ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json')
    snap=dict(root=str(ROOT),source_SHA=m['execution_SHA'],manifest_commit=m['source_commit'],
        equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],counts=state['counts'],policy=state['policy'],workers=state['workers'],
        qualified_reused_dates=sum(bool(r.get('reused')) for r in ledger['dates'].values()),
        original_model_slots_reused=sum(len(v['slots']) for v in models['days'].values()),
        handoff37_verified=h.get('verified_PASS',0),handoff37_complete=bool(h.get('PASS') and handoff.get('PASS')),
        monitor_URL='http://127.0.0.1:8796',hourly_ACTIVE=True,monthly_campaign_complete=False,UTC=now())
    atomic(folder/'SNAPSHOT.json',snap)
    p=SOURCE/'docs/v42_svr11_final_20261011/README.md';previous=p.read_text(encoding='utf8');marker='<!-- EPOCH10_CURRENT_END -->'
    if marker in previous:previous=previous.split(marker,1)[1].lstrip()
    intro=f'''Current execution **Epoch10**, same common equipment as **Epoch09**. Source `{m['execution_SHA']}`, manifest commit `{m['source_commit']}`, equipment `{snap['equipment_SHA']}`, Root `{ROOT}`. [Snapshot](epoch10_snapshot/SNAPSHOT.json), [ledger](epoch10_snapshot/CAMPAIGN_LEDGER.json), [exact equivalence](epoch10_snapshot/FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json), [models reused](epoch10_snapshot/MODEL_CHECKPOINT_REUSE_CONTRACT.json), [physical freeze](epoch10_snapshot/hardware/HARDWARE.json), [report](epoch10_snapshot/PERFORMANCE_COMPARISON.md), [preserved original history](epoch10_snapshot/PRESERVED_EPOCH09_HISTORY.json).

Forecast model generation repeatedly recomputed the same exact Fraction native-load allocation in every independent prefix. Cache the original checked allocations once per96 slots while retaining every DSS load setter, order, float value, fresh compile, control, solve and clock command. No engine, solved state, taps or queue are cached or copied to Actual. All31×96 Forecast setter inputs are identical. Representative slot0/47/95 comparisons each replay121 independent base/positive/negative responses with bitwise-identical measurements and sensitivities and identical native solve times/counts. Slot47 improved24.93→14.68s (1.70×), slot95 improved46.64→24.52s (1.90×); these measured prefixes are not a full-month speed or voltage-safety certification.52 regression tests pass. Native algorithms, objectives, integer domains, physical constraints, budgets and equipment are unchanged.

Only predecessor dispatch was quiesced. May13/14/15 healthy Workers finished naturally with zero terminations/hot patches. Independently qualify and reuse{snap['qualified_reused_dates']} completed dates and{snap['original_model_slots_reused']} completed Forecast slots. Original execution Source SHA, Native/Wall Runtime, physical evidence and failed attempts remain preserved. Current Source SHA labels new executions and separate revalidation, never relabels old execution. The common SVR11 equipment comparison is unchanged; older pre-Epoch09 equipment results remain separate history.

Current{state['counts']['completed']}/124 terminal; remaining B2→B1→B3 proceeds in original order with Worker3/1/1. Individual FAIL never gates later dates/policies; technical retries remain finite fresh Native0 attempts after following-date assignment. FULL-verified TIME_LIMIT is accepted normally. Planning/Actual autonomous controls remain independent and Actual repair/reoptimization remain0. Original voltage.95–1.05, line/SVR400A, original compiled NormalAmps and separate kVA/tap constraints remain literal.

[37-date verification](epoch10_snapshot/HANDOFF_37_VALIDATION.json), [live scheduled handoff](epoch10_snapshot/HANDOFF_RECEIPT.json). HTTP200 monitor http://127.0.0.1:8796; existing hourly ACTIVE and only two existing Windows jobs target this Root/Source. May2025 remains retrospective, not an independent holdout. Full124 completion remains pending.

{marker}

'''
    p.write_bytes((intro+previous).encode())
    body=intro.split(marker)[0].replace('](epoch10_snapshot/',
        '](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-svr11-final-may-20261011-epoch10/docs/v42_svr11_final_20261011/epoch10_snapshot/')
    (ROOT/'DRAFT_PR_BODY.md').write_bytes(body.encode())
    print(json.dumps(snap,ensure_ascii=False))

if __name__=='__main__':publish()
