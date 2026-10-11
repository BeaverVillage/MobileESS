"""Publish a compact live snapshot; no historical outcome is relabeled."""
from pathlib import Path
import sys,shutil,json,urllib.request,sqlite3,datetime,subprocess
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.report import generate
ROOT=Path(r'D:\v42_svr11_may_20261011_12')
DIAG=Path(r'D:\v42_svr11_planning_diagnostics_20261011')

def publish():
    m=verify(ROOT/'CAMPAIGN_MANIFEST.json');ledger=read(ROOT/'CAMPAIGN_LEDGER.json');generate(ROOT,ledger)
    with urllib.request.urlopen('http://127.0.0.1:8796/api/state') as response:state=json.load(response)
    assert state['root']==str(ROOT) and state['source_SHA']==m['execution_SHA']
    folder=SOURCE/'docs/v42_svr11_final_20261011/epoch12_snapshot';folder.mkdir(parents=True,exist_ok=True)
    names=('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','MODEL_VALIDATION_RELEASE_CONTRACT.json',
        'SELECTIVE_REUSE_LEDGER.json','FROZEN_PLAN_MODEL_IMPROVEMENT.json','REGRESSION_VALIDATION.json',
        'PREDECESSOR_DRAIN_CONTRACT.json','MIGRATION_STATUS.json','IMPLEMENTATION_REGRESSIONS.json',
        'REPORT.json','REPORT.md','MONITOR_UI_RELEASE.json','MONITOR_PROCESS.json',
        'SUPERVISOR_PROCESS.json','SUPERVISOR_HEARTBEAT.json','WATCHDOG_LAST_RUN.json',
        'WINDOWS_SCHEDULE_REGISTRATION.json','WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json')
    for name in names:
        if (ROOT/name).exists():shutil.copyfile(ROOT/name,folder/name)
    (folder/'hardware').mkdir(exist_ok=True)
    for path in (ROOT/'hardware').glob('*.json'):shutil.copyfile(path,folder/'hardware'/path.name)
    for name in ('MAY18_QUANTITATIVE_CAUSE_DECOMPOSITION.json','EPOCH10_DRAIN_PRESERVATION.json'):
        shutil.copyfile(DIAG/name,folder/name)
    shutil.copyfile(DIAG/'storage/STORAGE_COMPRESSION_RECEIPT.json',folder/'STORAGE_COMPRESSION_RECEIPT.json')
    cleanup=None;purge=None
    cleanup_index=DIAG/'storage/LATEST_UNUSED_RESULTS_CLEANUP.json'
    if cleanup_index.exists():
        cleanup_record=read(cleanup_index);assert record(cleanup_record['path'])['sha256']==cleanup_record['sha256']
        cleanup=read(cleanup_record['path']);shutil.copyfile(cleanup_record['path'],folder/'UNUSED_RESULTS_CLEANUP.json')
        recovery=cleanup['recovery_map'];assert record(recovery['path'])['sha256']==recovery['sha256']
        shutil.copyfile(recovery['path'],folder/'UNUSED_RESULTS_RECOVERY_MAP.json')
        purge_index=DIAG/'storage/LATEST_BACKUP_REMOVAL.json'
        if purge_index.exists():
            pr=read(purge_index);assert record(pr['path'])['sha256']==pr['sha256']
            purge=read(pr['path'])
            assert all(not Path(r['path']).exists() for r in purge['archives'])
            assert any(r['sha256']==cleanup['archive']['sha256'] for r in purge['archives'])
            shutil.copyfile(pr['path'],folder/'BACKUP_REMOVAL_RECEIPT.json')
        else:assert record(cleanup['archive']['path'])['sha256']==cleanup['archive']['sha256']
        post=Path(cleanup_record['path']).parent/'POST_CLEANUP_VERIFICATION.json'
        if post.exists():shutil.copyfile(post,folder/'POST_CLEANUP_VERIFICATION.json')
    shutil.copyfile(DIAG/'FINAL_GENERATOR_CONNECTION/GENERATOR_CONNECTION_VALIDATION.json',folder/'GENERATOR_CONNECTION_VALIDATION.json')
    validation=read(ROOT/'MODEL_VALIDATION_RELEASE_CONTRACT.json')
    for key in ('May18_reoptimization','normal_date_validation','May18_Actual'):
        r=validation['evidence'][key];assert record(r['path'])==r
        shutil.copyfile(r['path'],folder/(key+'_VALIDATION.json'))
    atomic(folder/'MONITOR_STATE.json',state)
    c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
    hourly=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
        ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
    assert hourly['status']=='ACTIVE' and str(ROOT) in hourly['prompt'] and m['execution_SHA'] in hourly['prompt']
    hourly['next_run_KST']=datetime.datetime.fromtimestamp(hourly['next_run_at']/1000,datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    atomic(folder/'HOURLY_AUTOMATION.json',hourly)
    native=read(ROOT/'dates/B0/2025-05-01/attempts/attempt_01/NATIVE_RUNTIME_LEDGER.json')
    r=read(ROOT/'dates/B0/2025-05-01/attempts/attempt_01/RESULT.json')
    assert r['PASS'] and r['source_SHA']==m['execution_SHA'] and native['measured_Native_Runtime']==0
    assert r['metrics']['environments']['ACTUAL']['slots']==96
    atomic(folder/'B0_MAY01_RESULT.json',r)
    summary=dict(root=str(ROOT),source_SHA=m['execution_SHA'],manifest_commit=m['source_commit'],
        equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],counts=state['counts'],policy=state['policy'],
        workers=state['workers'],supervisor=read(ROOT/'SUPERVISOR_PROCESS.json'),
        hourly_ACTIVE=True,next_hourly_KST=hourly['next_run_KST'],
        old_optimized_results_promoted=0,old_physical_PASS_promoted=0,
        May18_Actual=record(validation['evidence']['May18_Actual']['path']),
        final_month_completed=False,monitor_URL='http://127.0.0.1:8796',UTC=now())
    atomic(folder/'SNAPSHOT.json',summary)
    cleanup_text='' if cleanup is None else f''' Additional user-authorized cleanup removed {cleanup['byte_reconstructible_slot_duplicates']} obsolete slot NPZ duplicates with independently proven byte-identical reconstruction from retained merged NPZ, and {cleanup['archived_loose_arrays']} closed historical array JSON files after complete ZIP-entry SHA verification. Net allocated storage recovered, after the backup archive, is {cleanup['net_allocated_recovered']:,}bytes. Removed loose array paths are explicitly recorded rather than claimed present. May16/May18 details, failed dates, current campaign, raw/source/shared inodes, all ledgers/Native histories and performance CSV remain untouched. [Cleanup receipt](epoch12_snapshot/UNUSED_RESULTS_CLEANUP.json), [archive/reconstruction map](epoch12_snapshot/UNUSED_RESULTS_RECOVERY_MAP.json).'''
    if purge:
        cleanup_text=f''' User-directed obsolete-data cleanup deleted {cleanup['deleted_files']} loose files ({cleanup['byte_reconstructible_slot_duplicates']} byte-identical slot NPZ duplicates and {cleanup['archived_loose_arrays']} closed PASS detailed array JSON files). The user's subsequent instruction also removed both unnecessary ZIP backups: {purge['additional_allocated_recovered']:,} additional bytes, {purge['total_cleanup_allocated_recovered']:,}bytes total allocated recovery. **Those historical detailed arrays now have no backup and cannot be restored**; the original archive map documents prior verification rather than a currently available archive. Essential317 loose records retain their original SHA, and all239 entries in the earlier essential ZIP were proved duplicated in retained loose originals before ZIP deletion. May16/May18 details, failures, current campaign, raw/source/shared inodes, ledgers/Native histories and performance CSV remain. Obsolete slot duplicates can still be reconstructed byte-identically from retained merged files. [Cleanup history](epoch12_snapshot/UNUSED_RESULTS_CLEANUP.json), [backup removal](epoch12_snapshot/BACKUP_REMOVAL_RECEIPT.json), [original deletion map](epoch12_snapshot/UNUSED_RESULTS_RECOVERY_MAP.json).'''
    intro=f'''Current official execution: **Epoch12**, Root `{ROOT}`, Source `{m['execution_SHA']}`, manifest commit `{m['source_commit']}`. Equipment remains `{summary['equipment_SHA']}`. [Snapshot](epoch12_snapshot/SNAPSHOT.json), [ledger](epoch12_snapshot/CAMPAIGN_LEDGER.json), [validation and limitations](epoch12_snapshot/MODEL_VALIDATION_RELEASE_CONTRACT.json).

May18's original Planning estimate1.027409814pu missed optimized Forecast1.050890442pu and Actual1.051030026pu. Same-P/Q diagnostic tap swaps independently separate prior-history tap contribution0.011539025145pu, current-slot AUTO tap contribution0.013581027418pu and fixed-tap affine remainder−0.001639425000pu. Original Reg4 LDC compensation couples delivered P/Q to secondary voltage; a single B0-anchored absolute-voltage secant does not represent that discrete control history. [Quantitative RCA](epoch12_snapshot/MAY18_QUANTITATIVE_CAUSE_DECOMPOSITION.json).

The new model uses original native LDC identities, physical deadband endpoints, finite winding-current bounds and fixed-capacitor Q∝V² bounds, plus local relative-voltage/flow response. It adds no tap decision or empirical date-specific voltage offset and keeps every original controller/equipment setting and physical limit. For the old May18 plan, the new upper endpoint1.053022666pu detects the missed risk. Remaining5 historical interval-miss cells are explicitly retained: this is a locally validated approximation, **not a global nonlinear safety envelope**. The final generator independently recomputed121 causal AUTO responses at slot51 and matched all9 candidate coefficient fields bitwise. [Connection proof](epoch12_snapshot/GENERATOR_CONNECTION_VALIDATION.json).

New-candidate May18 reoptimization took103.778 Native seconds: FULL feasible and independent Forecast96 PASS, Vmin0.961985876/Vmax1.049376625, no voltage/current/kVA/SVR violation. Normal May16 reoptimization took112.773 Native seconds and Forecast96 PASS, Vmax1.047549376. May18's frozen candidate then ran **direct Actual→Fresh96**, Vmin0.963012362/Vmax1.048813544, every physical guard PASS and all AC/control steps complete, no repair/reoptimization/tap copying and no intervening DayAhead AC. Actual took29.529 seconds. These Source11 development executions retain their own SHA and are validation evidence; none becomes an official Epoch12 date. [May18 Forecast](epoch12_snapshot/May18_reoptimization_VALIDATION.json), [normal date](epoch12_snapshot/normal_date_validation_VALIDATION.json), [May18 Actual](epoch12_snapshot/May18_Actual_VALIDATION.json).75 implementation regressions pass.

The new campaign starts all124 dates afresh: **B0 3Workers Native0 → B2 3Workers → B1 1Worker → B3 stage batch**. B3 reuses only this Epoch's FULL-verified same-date B1 A1, then M1 all31 max3→process/RAM/Commit barrier→A2 all31 max1→barrier→M2 all31 max3→valid-date Actual/Fresh96. M stages keep Native1800, A5400, common U4, original objectives/integers/physical domains. Individual physical/solver FAIL cannot gate independent dates or policy transition. Only restartable technical failures get bounded3 attempts from Native0 after the next-date assignment; original ledgers survive. FULL-verified TIME_LIMIT is accepted, without requiring a global-gap certificate.

Official paths proceed from Forecast/model→Planning→decision freeze→Actual→Fresh96. There is no postoptimization Forecast96 replay or fabricated Planning AC PASS. Actual starts an independent native context with originalReg7/SVR11 AUTO, empty initial queue and no Planning control-state transfer. B0 May01 independently completed all96 Actual slots at Native0. [New B0 evidence](epoch12_snapshot/B0_MAY01_RESULT.json). At this snapshot {state['counts']['completed']}/124 terminal, PASS{state['counts']['PASS']}/FAIL{state['counts']['FAIL']}; full campaign completion remains pending.

Only unchanged raw inputs/domain descriptors reuse original bytes. SHA-verified raw files use NTFS hardlinks; every changed sensitivity and dependent model is regenerated. Old optimized plans and physical PASS are never promoted. New date-specific electrical models are shared across B1/B2/B3. The earlier historical312-file in-place compression recovered3,896,577,213bytes without deletion at that time. [Reuse](epoch12_snapshot/SELECTIVE_REUSE_LEDGER.json), [earlier compression](epoch12_snapshot/STORAGE_COMPRESSION_RECEIPT.json), [old124-date preservation](epoch12_snapshot/EPOCH10_DRAIN_PRESERVATION.json).{cleanup_text}

Existing hourly heartbeat is ACTIVE and the two existing Windows safeguard registrations target this Root/Source; HTTP monitor http://127.0.0.1:8796 matches it. Old dispatch remains quiesced and healthy Epoch10 Workers all finished naturally. May2025 remains retrospective development, not an independent holdout. [Schedule](epoch12_snapshot/HOURLY_AUTOMATION.json), [migration](epoch12_snapshot/MIGRATION_STATUS.json).

The existing hourly recovery was updated at the user's request for Epoch12, preserving its ACTIVE status, one-hour interval and current chat. Future approved epoch transitions require matching immutable manifest/release/migration and live process/HTTP evidence before retargeting these same schedules. [Verified schedule update](epoch12_snapshot/HOURLY_USER_UPDATE_VERIFIED_20261011.json), [direct process, memory and Windows observations](epoch12_snapshot/HEARTBEAT_DIRECT_OBSERVATION_20261011_1507.json), [all124 performance and separate PASS cohorts](epoch12_snapshot/PERFORMANCE_COMPARISON.json).

<!-- EPOCH12_CURRENT_END -->

'''
    p=SOURCE/'docs/v42_svr11_final_20261011/README.md';previous=p.read_text(encoding='utf8')
    if '<!-- EPOCH12_CURRENT_END -->' in previous:previous=previous.split('<!-- EPOCH12_CURRENT_END -->',1)[1].lstrip()
    p.write_bytes((intro+previous).encode('utf8'))
    body=intro.split('<!-- EPOCH12_CURRENT_END -->')[0].replace('](epoch12_snapshot/',
        '](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-svr11-final-may-20261011-epoch02/docs/v42_svr11_final_20261011/epoch12_snapshot/')
    (ROOT/'DRAFT_PR_BODY.md').write_text(body,encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':publish()
