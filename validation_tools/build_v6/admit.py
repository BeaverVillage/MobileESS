"""One explicit version boundary for the user-requested May23 rebuild."""
from copy import deepcopy
import json,shutil,subprocess
from pathlib import Path
from v42_pr134_b1.common import ROOT,read,atomic,record,sha,now,same_process,digest
from v42_may_build_v6.policy import VERSION,MANIFEST,ATTEMPT,RETRY_DATES,PRECISION,source_files,verify_policy
from v42_may_campaign_native90.maintenance_session import valid
from .preflight import RUN,DOC


def main(token):
    valid(RUN/'hourly_maintenance',token)
    if (RUN/MANIFEST).exists():raise PermissionError('IMMUTABLE_V6_ALREADY_ADMITTED')
    previous=read(RUN/'CONTINUATION_V5_MANIFEST.json');base=read(RUN/'CAMPAIGN_MANIFEST.json')
    if not (RUN/'HOLD_V5.json').exists() or same_process(read(RUN/'COORDINATOR_V5_HOST.json')['process']):
        raise PermissionError('V5_COORDINATOR_NOT_HELD_AT_VERSION_BOUNDARY')
    stop=read(RUN/'MAY23_V5_USER_RESTART_RECEIPT.json')
    if same_process(stop['worker']) or stop['Native_calls_before_stop']!=0:
        raise PermissionError('ONLY_USER_REQUESTED_NATIVE_ZERO_REBUILD')
    gates={k:DOC/f for k,f in dict(FRESH_ORIGINAL_MODELS='BUILD_EQUIVALENCE.json',
        REGRESSION='REGRESSION_VERIFICATION.json',OS_PERSISTENCE='OS_PERSISTENCE_VERIFICATION.json',
        MONITOR_UI='MONITOR_UI_VERIFICATION.json').items()}
    if any(read(p).get('PASS') is not True for p in gates.values()):raise PermissionError('V6_GATE_NOT_PASS')
    if read(DOC/'MAY31_INPUT_VALIDATION.json')['PASS'] is not True:raise PermissionError('MAY31_RAW_INPUT_GATE_NOT_PASS')
    source=RUN/'preflight_v6/B1/2025-05-23/fresh01/output'
    prep=read(source/'A_PREPARE_RECEIPT.json');domain=read(source/'STATIC/DOMAIN/2025-05-23/PHYSICAL_DOMAIN_CACHE.json')
    cache=dict(scope='CURRENT_DATE_NATIVE_ZERO_INPUTS_ONLY',folder=str(source),
        preparation=record(source/'A_PREPARE_RECEIPT.json'),DATA=record(source/'STATIC/DATA/DATA.pkl'),
        physical_receipt=record(source/'STATIC/DOMAIN/2025-05-23/PHYSICAL_DOMAIN_CACHE.json'),
        receipt=record(source/'STATIC/DOMAIN/2025-05-23/PHYSICAL_DOMAIN_CACHE.json'),
        complete_domain_hashes=domain['complete_domain_hashes'],inputs=prep['scientific_input'],model_verification=prep['verification'])
    boundary=RUN/'BASE_CHECKPOINT_BOUNDARY_V6.json'
    if boundary.exists():raise PermissionError('V6_BOUNDARY_ALREADY_EXISTS')
    shutil.copyfile(RUN/'CHECKPOINT_V5.json',boundary)
    manifest=deepcopy(base)
    manifest.update(schema=VERSION,base_manifest=record(RUN/'CAMPAIGN_MANIFEST.json'),
        previous_manifest=record(RUN/'CONTINUATION_V5_MANIFEST.json'),base_checkpoint=record(boundary),
        attempt_id=ATTEMPT,precision=PRECISION,authorized_recovery_dates=list(RETRY_DATES),
        input_cache_sources={'B1/2025-05-23':cache},monitor_port=8793,
        tasks={role:'MobileESS_V42_B1B2_P1_'+base['run_id']+'_BuildV6_'+role.title() for role in ('coordinator','monitor','watchdog')},
        implementation=dict(version=VERSION,sources=source_files(),source_SHA=digest(source_files())),
        validation={k:record(p) for k,p in gates.items()},
        source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        authority=dict(explicit_user_requested_recovery_dates=['2025-05-23'],
            completed_May01_through_May22_results_preserved=True,recovery_order=['2025-05-%02d'%i for i in range(23,32)],
            B1_parallel_workers=1,B2_parallel_workers=3,automatic_failed_date_retries=0,
            Native_ceiling_seconds=5400,wall_ceiling_seconds=None,Heuristics=.05,Threads=1,
            original_problem_and_full_domains_unchanged=True,prior_native_point_bound_or_clock_transferred=False),UTC=now())
    atomic(RUN/MANIFEST,manifest);verify_policy(RUN)
    from v42_may_build_v6.coordinator import load_checkpoint,recovery_requests
    checkpoint=load_checkpoint(RUN,manifest);recovery_requests(RUN,manifest,checkpoint,{})
    assert all(checkpoint['dates']['B1/2025-05-%02d'%i]['status']=='PASS' for i in range(1,23))
    assert checkpoint['dates']['B1/2025-05-23']['status']=='PENDING'
    atomic(DOC/'CONTINUATION_ADMISSION.json',dict(PASS=True,UTC=now(),Native_calls=0,P2_calls=0,
        manifest=record(RUN/MANIFEST),source_version=VERSION,previous_manifest=manifest['previous_manifest'],
        original_checkpoint=record(boundary),completed_dates_preserved=22,
        first_worker='B1/2025-05-23',B2_parallel_workers=3,actual_dispatch='NOT_YET_OBSERVED'))
    print(json.dumps(dict(PASS=True,manifest_SHA=sha(RUN/MANIFEST),version=VERSION)),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--token',required=True);main(p.parse_args().token)
