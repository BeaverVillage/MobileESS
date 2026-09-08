"""Independent date/phase with retained B0/B2 and cold B0-seeded B1."""
from fast_prepare import *
from v41r4_loop_runtime import BASE_RUN,BASE_OUT,PREVIOUS_RUN,PREVIOUS_OUT,MAY_RUN,MAY_OUT,configure,prepare_ranking,recovery,install_reports,verify_old_or_current
from v41r4_loop_budget import adapted
import os,sys,time,traceback,subprocess
from datetime import datetime,timezone


def junction(path,target):
    path=Path(path);target=Path(target).resolve()
    assert path.absolute().is_relative_to(MAY_RUN) and target.is_relative_to(BASE_RUN) and target!=BASE_RUN
    if path.exists():assert path.resolve()==target;return
    assert target.is_dir();path.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['V41_LINK_PATH']=str(path);env['V41_LINK_TARGET']=str(target)
    subprocess.run(['powershell.exe','-NoProfile','-Command',"$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:V41_LINK_PATH -Target $env:V41_LINK_TARGET | Out-Null"],env=env,check=True,capture_output=True)
    assert path.resolve()==target


def retained(day,policy,stage='DA'):
    for run,out in ((PREVIOUS_RUN,PREVIOUS_OUT),(BASE_RUN,BASE_OUT)):
        phase=out/day/f'PHASE_{policy}_{stage}.json'
        if phase.exists() and read(phase)['status']=='PASS':return run,out,phase
    return None


def sync(day):
    for directory in ('domain','screen'):
        target=BASE_OUT/day/directory
        if target.is_dir():junction(MAY_OUT/day/directory,target)
    for name in ('INPUT_PREPARATION.json','V41R3_TIMESHIFTING_PRESERVATION_AUDIT.json','V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json','V41R3_B0_ACCEPTANCE.json'):
        source=BASE_OUT/day/name
        if source.exists():copy(source,MAY_OUT/day/name)


def reuse_da(day,policy):
    source=retained(day,policy);assert source
    run,out,phase=source;da=run/day/policy/'dayahead'
    r=read(da/'DAYAHEAD_RECEIPT.json');expected=r['science']
    approved=[read(BASE_OUT/'MAY_CAMPAIGN_RELEASE.json')['source']]
    producer=PREVIOUS_OUT/day/f'PRODUCER_{policy}.json'
    if producer.exists():approved.append(read(producer)['science'])
    assert expected in approved,'UNAPPROVED_RETAINED_PRODUCER'
    junction(MAY_RUN/day/policy/'dayahead',da)
    save(MAY_OUT/day/f'REUSED_DA_PRODUCER_{policy}.json',dict(science=expected,source=record(da/'DAYAHEAD_RECEIPT.json')))
    verify_old_or_current(day,policy,expected)
    copy(out/day/f'{policy}_DAYAHEAD_SUMMARY.json',MAY_OUT/day/f'{policy}_DAYAHEAD_SUMMARY.json')
    return dict(status='PASS',reused_phase=record(phase),additional_optimization_calls=0,actual_inputs_read=False)


def normalize_actual_metadata():
    from dayahead.v41 import scientific_archive as archive
    from copy import deepcopy
    original=archive.actual_inputs
    def inputs(output,day,decision,da_output,obs,exo,mess_result,workload):
        normalized=deepcopy(mess_result)
        for move in normalized['moves']:
            source=move['actual_traffic_source'];current=archive.record(source['path'])
            assert set(source)<={'path','sha256','bytes','exists'} and source.get('exists',True) is True
            assert all(source[k]==current[k] for k in current),'ACTUAL_TRAFFIC_HASH_DRIFT'
            move['actual_traffic_source']=current
        return original(output,day,decision,da_output,obs,exo,normalized,workload)
    archive.actual_inputs=inputs


def reuse_actual(day,policy):
    source=retained(day,policy,'AC')
    if source is None:return None
    run,out,phase=source;ac=run/day/policy/'actual'
    # This function is called only after all four new Day-Ahead freezes.
    opened=datetime.now(timezone.utc).isoformat()
    freezes={p:read(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json') for p in ('B0','B1','B2','B3')}
    assert all(r['status']=='COMPLETE' and r['completed_at']<=opened for r in freezes.values())
    from dayahead.v40h.identity import verify_manifest
    r=read(ac/'ACTUAL_RECEIPT.json')
    assert r['status']=='COMPLETE' and r['decision_SHA']==freezes[policy]['decision_SHA']
    assert r['day_ahead']==record(MAY_RUN/day/policy/'dayahead/DAYAHEAD_RECEIPT.json'), 'CACHED_ACTUAL_DA_AUTHORITY_MISMATCH'
    assert all(record(item['path'])==item for item in r['files'].values()), 'CACHED_ACTUAL_RECEIPT_HASH_DRIFT'
    # Original archive hashes and producer are checked without editing the archive.
    from dayahead.v41 import scientific_archive as archive
    archive.verify_manifest(ac/'SCIENTIFIC_MANIFEST.json')
    if 'science' in r:verify_manifest(r['science'])
    junction(MAY_RUN/day/policy/'actual',ac)
    save(MAY_OUT/day/f'CACHED_ACTUAL_IMPORT_{policy}.json',dict(status='PASS',opened_at=opened,
        original_boundary=record(ac/'ACTUAL_BOUNDARY_RECEIPT.json'),original_receipt=record(ac/'ACTUAL_RECEIPT.json'),
        original_phase=record(phase),all_four_new_DA_freezes={p:record(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json') for p in freezes},
        numerical_replay_reused_byte_exact=True,additional_optimizer_calls=0))
    import v41r4_report as report
    fn=adapted(report.accept_actual,[("boundary=read(ac/'ACTUAL_BOUNDARY_RECEIPT.json');assert all(t<=boundary['opened_at'] for t in all_freezes.values())",
        "boundary=read(MAY_OUT/day/f'CACHED_ACTUAL_IMPORT_{policy}.json');assert all(t<=boundary['opened_at'] for t in all_freezes.values())")])
    return fn(day,policy)


def main(day,phase):
    from dayahead.v40h.identity import verify_manifest
    release=read(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V4.json');assert release['status']=='FROZEN'
    verify_manifest(release['source']);sync(day)
    receipt=MAY_OUT/day/f'PHASE_{phase}.json';assert not receipt.exists(),'PRESERVE_EXISTING_PHASE'
    started=time.time()
    try:
        if phase in ('electrical','domain','B0_DA'):
            old=BASE_OUT/day/f'PHASE_{phase}.json'
            if not old.exists():
                from v41r4_worker import main as original
                original(day,phase)
            assert read(old)['status']=='PASS';sync(day)
            result=reuse_da(day,'B0') if phase=='B0_DA' else dict(status='PASS',reused_phase=record(old))
        elif phase=='B2_DA' and retained(day,'B2'):
            result=reuse_da(day,'B2')
        else:
            policy,stage=phase.split('_');assert policy in release['policies']
            if stage=='DA':
                assert policy in ('B1','B2','B3')
                assert not any((MAY_RUN/day/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in release['policies'])
                for parent in (('B0','B1') if policy=='B3' else ('B0',)):
                    assert read(MAY_OUT/day/f'PHASE_{parent}_DA.json')['status']=='PASS'
                save(MAY_OUT/day/f'{policy}_SINGLE_CORRECTED_RUN_TOKEN.json',dict(day=day,policy=policy,
                    reason='USER_FINAL_LOOP_WALL_CLOCK_RULE',started_at=started,additional_quality_runs=0))
            else:
                assert stage=='AC'
                for p in release['policies']:assert read(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json')['status']=='COMPLETE'
            prep=time.perf_counter();execution=configure(day,policy);install_reports()
            from dayahead.v41.temporal_restore import activate
            from v41r4_report import accept_dayahead,accept_actual
            if stage=='DA':
                if policy=='B1':prepare_ranking(day,prep);recovery(day)
                with activate():execution.dayahead(day,policy)
                from dayahead.v41r3 import candidates
                if candidates._store is not None and not candidates._store.complete:candidates._store.finish()
                result=accept_dayahead(day,policy)
            else:
                result=reuse_actual(day,policy) if policy in ('B0','B2') else None
                if result is None:
                    os.environ.pop('V41_FO_RECOVERY_PLAN',None);normalize_actual_metadata()
                    with activate():execution.actual(day,policy)
                    result=accept_actual(day,policy)
        save(receipt,dict(status='PASS',day=day,phase=phase,started_at=started,completed_at=time.time(),
            elapsed_seconds=time.time()-started,result=result,budget_version='FIXED_1800_LOOP_WALL_CLOCK',automatic_repeat=False))
        print('LOOP_WALL_PHASE_PASS',day,phase,flush=True)
    except BaseException as error:
        save(receipt,dict(status='FAIL_CLOSED',day=day,phase=phase,error=repr(error),traceback=traceback.format_exc(),
            started_at=started,completed_at=time.time(),automatic_retry=False));raise


if __name__=='__main__':main(sys.argv[1],sys.argv[2])
