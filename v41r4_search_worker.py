"""One phase of the single corrected-budget campaign; no quality reruns."""
from fast_prepare import *
from v41r4_search_runtime import BASE_RUN,BASE_OUT,MAY_RUN,MAY_OUT,configure,prepare_ranking,recovery,install_reports
import os,sys,time,traceback,subprocess
from dayahead.paper_analysis.storage import write_json


def junction(path,target):
    path=Path(path);target=Path(target).resolve()
    assert path.absolute().is_relative_to(MAY_RUN) and target.is_relative_to(BASE_RUN) and target!=BASE_RUN
    if path.exists():
        assert path.resolve()==target;return
    assert target.is_dir()
    path.parent.mkdir(parents=True,exist_ok=True)
    # Literal paths are arguments, never expanded shell expressions.
    env=os.environ.copy();env['V41_LINK_PATH']=str(path);env['V41_LINK_TARGET']=str(target)
    subprocess.run(['powershell.exe','-NoProfile','-Command',"$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:V41_LINK_PATH -Target $env:V41_LINK_TARGET | Out-Null"],env=env,check=True,capture_output=True)
    assert path.resolve()==target


def sync(day):
    for policy in ('B0','B2'):
        if policy=='B2':
            receipt=BASE_OUT/day/'PHASE_B2_DA.json'
            if not receipt.exists() or read(receipt)['status']!='PASS':continue
        target=BASE_RUN/day/policy
        target.mkdir(parents=True,exist_ok=True)
        junction(MAY_RUN/day/policy,target)
    for directory in ('domain','screen'):
        target=BASE_OUT/day/directory
        if target.is_dir():junction(MAY_OUT/day/directory,target)
    for name in ('INPUT_PREPARATION.json','V41R3_TIMESHIFTING_PRESERVATION_AUDIT.json',
        'V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json','V41R3_B0_ACCEPTANCE.json',
        'B0_DAYAHEAD_SUMMARY.json','B2_DAYAHEAD_SUMMARY.json'):
        source=BASE_OUT/day/name
        if source.exists():copy(source,MAY_OUT/day/name)


def main(day,phase):
    from dayahead.v40h.identity import verify_manifest
    release=read(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V3.json')
    assert release['status']=='FROZEN' and release['automatic_quality_reruns']==0
    verify_manifest(release['source']);sync(day)
    receipt=MAY_OUT/day/f'PHASE_{phase}.json'
    assert not receipt.exists(),'PRESERVE_EXISTING_CORRECTED_PHASE'
    started=time.time()
    try:
        reusable_b2=phase=='B2_DA' and (BASE_OUT/day/'PHASE_B2_DA.json').exists() and read(BASE_OUT/day/'PHASE_B2_DA.json')['status']=='PASS'
        if phase in ('electrical','domain','B0_DA') or reusable_b2:
            old=BASE_OUT/day/f'PHASE_{phase}.json'
            if not old.exists():
                from v41r4_worker import main as original
                original(day,phase)
            assert read(old)['status']=='PASS',('RETAINED_PHASE_NOT_VALID',str(old))
            if phase in ('B0_DA','B2_DA'):
                from v41r4_search_runtime import verify_old_or_current
                verify_old_or_current(day,phase[:2])
            sync(day)
            result=dict(status='PASS',reused_phase=record(old),additional_optimization_calls=0,
                preparation_or_policy_unchanged=True)
        else:
            policy,stage=phase.split('_');assert policy in ('B0','B1','B2','B3')
            if stage=='DA':
                assert policy in ('B1','B2','B3')
                assert not any((MAY_RUN/day/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in release['policies'])
                for parent in (('B0','B1') if policy=='B3' else ('B0',)):
                    assert read(MAY_OUT/day/f'PHASE_{parent}_DA.json')['status']=='PASS'
                # This is not a restart-until-better controller. A phase has
                # one token, and every completed termination is final.
                save(MAY_OUT/day/f'{policy}_SINGLE_CORRECTED_RUN_TOKEN.json',dict(day=day,policy=policy,
                    started_at=started,reason='USER_AUTHORIZED_SEARCH_BUDGET_CORRECTION',
                    corrected_search_run_limit=1,additional_quality_runs=0))
            else:
                assert stage=='AC'
                for p in release['policies']:
                    assert read(MAY_RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json')['status']=='COMPLETE'
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
                os.environ.pop('V41_FO_RECOVERY_PLAN',None)
                with activate():execution.actual(day,policy)
                result=accept_actual(day,policy)
        save(receipt,dict(status='PASS',day=day,phase=phase,started_at=started,completed_at=time.time(),
            elapsed_seconds=time.time()-started,result=result,budget_version='ACTUAL_FO_SEARCH_SECONDS',automatic_repeat=False))
        print('CORRECTED_SEARCH_PHASE_PASS',day,phase,flush=True)
    except BaseException as error:
        save(receipt,dict(status='FAIL_CLOSED',day=day,phase=phase,error=repr(error),traceback=traceback.format_exc(),
            started_at=started,completed_at=time.time(),automatic_retry=False))
        raise

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
