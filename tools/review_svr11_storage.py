"""Read-only inventory plus receipt of explicitly authorized fixture cleanup."""
from pathlib import Path
import sys,subprocess,shutil,json,psutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import record,atomic,read,now
from v42_svr11.processes import live
REPORT=SOURCE/'docs/v42_epoch15_integration_20261011/STORAGE_REVIEW.json'
FIXTURE=SOURCE/'docs/test_tmp_c3a'
ROOTS=[Path('D:/v42_svr11_may_20261011_'+str(n)) for n in (12,13,14)]+[
    Path('D:/')/n for n in ('v42_svr11_full_milp_development_20261011',
    'v42_svr11_ldc_development_20261011','v42_svr11_phase2_tests_20261011_a',
    'v42_svr11_planning_diagnostics_20261011','v42_svr11_model_performance_20261011')]


def inventory(root):
    names=subprocess.check_output(['rg','--files','--hidden',str(root)],text=True,encoding='utf8').splitlines()
    files=[];bytes_=0;linked=0
    for name in names:
        path=Path(name)
        if not path.is_file():continue
        stat=path.stat();bytes_+=stat.st_size
        if stat.st_nlink>1:linked+=1
        files.append(dict(path=str(path),bytes=stat.st_size,NTFS_links=stat.st_nlink))
    return dict(root=str(root),files=len(files),logical_bytes=bytes_,existing_hardlinked_files=linked,
        largest_files=sorted(files,key=lambda row:row['bytes'],reverse=True)[:5])


def planning_snapshot():
    old=Path('D:/v42_svr11_may_20261011_14');ledger=read(old/'CAMPAIGN_LEDGER.json')
    row=ledger['dates']['B2/2025-05-03'];peer=row.get('worker',{})
    supervisor=read(old/'SUPERVISOR_PROCESS.json')
    def observation(receipt):
        answer=dict(receipt,live=live(receipt))
        if answer['live']:
            process=psutil.Process(receipt['PID'])
            answer.update(process_status=process.status(),CPU_seconds=sum(process.cpu_times()[:2]))
        return answer
    return dict(old_May03_worker=observation(peer),old_supervisor=observation(supervisor),
        campaign_transition_started_by_this_helper=False,new_source_immutable=True,
        next_action='Root final validation, immutable release, then existing Windows job update and migration safeguard')


def prepare():
    if REPORT.exists():raise PermissionError('STORAGE_REVIEW_ALREADY_PREPARED')
    resolved=FIXTURE.resolve()
    if resolved!=Path('D:/v42_svr11_epoch15_20261011/docs/test_tmp_c3a'):
        raise PermissionError('EXPLICIT_FIXTURE_TARGET_NOT_RESOLVED')
    tracked=subprocess.check_output(['git','ls-files','--','docs/test_tmp_c3a'],cwd=SOURCE,text=True)
    if tracked.strip():raise PermissionError('FIXTURE_CONTAINS_TRACKED_HISTORY')
    fixture_files=[record(path) for path in sorted(FIXTURE.rglob('*')) if path.is_file()]
    if any(not Path(row['path']).resolve().is_relative_to(resolved) for row in fixture_files):
        raise PermissionError('FIXTURE_PATH_OWNERSHIP_DRIFT')
    report=dict(schema='SVR11_EPOCH15_STORAGE_REVIEW_V1',PASS=True,status='EXPLICIT_FIXTURE_CLEANUP_PREPARED',
        source_scientific_files_changed=0,D_free_before_bytes=shutil.disk_usage('D:/').free,UTC_before=now(),
        inspected_roots=[inventory(root) for root in ROOTS],
        active_old_worker_namespace_excluded=str(Path('D:/v42_svr11_may_20261011_14/dates/B2/2025-05-03')),
        retained_categories=['immutable source','raw inputs','validated sensitivity caches','Native runtime ledgers',
            'PASS/FAIL result records','original 96-slot physical evidence','essential matrix/proof SHA receipts',
            'historical May16/18 full-MILP validation','current in-progress development validation'],
        large_historical_files_deleted=[],historical_logical_bytes_deleted=0,
        large_cleanup_conclusion='No clearly unnecessary large historical artifact satisfied evidence-preserving deletion criteria; retained all historical artifacts',
        apparent_duplicate_probe_files=[record(Path('D:/v42_svr11_planning_diagnostics_20261011')/name)
            for name in ('2025-05-18_FULL_HISTORY_PROBE.json','2025-05-18_FULL_HISTORY_PROBE_BASELINE_INCLUDED.json')],
        apparent_duplicate_decision='Different SHA despite equal size; retained both',
        fixture_cleanup=dict(explicitly_authorized_by_parent=True,target=str(resolved),tracked_files=0,
            preconditions=['exact resolved target','inside new checkout docs','untracked test-only fixtures',
                'no recursive link/junction traversal','per-file SHA and byte receipts retained'],
            files=fixture_files,logical_bytes=sum(row['bytes'] for row in fixture_files),deleted=False),
        transition_observation=planning_snapshot(),processes_terminated=0)
    atomic(REPORT,report);print(json.dumps(dict(report=str(REPORT),fixture_bytes=report['fixture_cleanup']['logical_bytes'],
        D_free_before_bytes=report['D_free_before_bytes']),ensure_ascii=False))


def finalize():
    report=read(REPORT)
    if FIXTURE.exists():raise PermissionError('FIXTURE_CLEANUP_NOT_COMPLETED')
    report['fixture_cleanup']['deleted']=True
    report.update(status='REVIEW_COMPLETE',D_free_after_bytes=shutil.disk_usage('D:/').free,UTC_after=now(),
        deleted_logical_bytes=report['fixture_cleanup']['logical_bytes'],deleted_files=len(report['fixture_cleanup']['files']),
        transition_observation_after=planning_snapshot())
    report['observed_D_free_change_bytes']=report['D_free_after_bytes']-report['D_free_before_bytes']
    report['free_space_delta_attribution']='Observed system delta includes concurrent immutable validation/campaign writes; cleanup claim is limited to listed fixture bytes'
    atomic(REPORT,report);print(json.dumps({key:report[key] for key in ('status','deleted_logical_bytes','deleted_files',
        'D_free_before_bytes','D_free_after_bytes','observed_D_free_change_bytes')},ensure_ascii=False))


def blocked():
    report=read(REPORT)
    if any(record(row['path'])!=row for row in report['fixture_cleanup']['files']):
        raise PermissionError('BLOCKED_FIXTURE_PRESERVATION_BYTES_DRIFT')
    report.update(status='REVIEW_COMPLETE_FIXTURE_CLEANUP_POLICY_BLOCKED',
        D_free_after_bytes=shutil.disk_usage('D:/').free,UTC_after=now(),
        deleted_logical_bytes=0,deleted_files=0,transition_observation_after=planning_snapshot(),
        automatic_approval_review=dict(action='Delete six explicitly authorized untracked test fixture JSONs and empty fixture directory',
            rejected=True,stated_reason='blocked by policy',
            safer_attempt='Exact six literal file paths without recursive deletion',safer_attempt_also_rejected=True,
            files_preserved=True))
    report['observed_D_free_change_bytes']=report['D_free_after_bytes']-report['D_free_before_bytes']
    report['free_space_delta_attribution']='No files were deleted; observed system delta reflects concurrent validation/campaign writes'
    atomic(REPORT,report);print(json.dumps({key:report[key] for key in ('status','deleted_logical_bytes',
        'D_free_before_bytes','D_free_after_bytes')},ensure_ascii=False))


if __name__=='__main__':
    {'prepare':prepare,'finalize':finalize,'blocked':blocked}[sys.argv[1]]()
