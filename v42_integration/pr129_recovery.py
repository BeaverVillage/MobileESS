"""Audit PR129's pre-policy frozen model reference against DD00 observations.

Only its Reference can contribute prior modeled site pins. Historical B0
Queue/occupancy/power results never supply common observed sites. Entire
overloaded prior-site candidate groups are rejected before any reuse; no
greedy subset is promoted as if it were the original reference authority.
"""
from collections import Counter
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

from .policy import digest
from .source_recovery import episode_id
from .m_engine import file_record,_write


PR129_HEAD='97ef9cc9b655d93a42b0b43d593aac01b951c6f3'
PR125_HEAD='043298363fe51edde0bddaa073a553e526ffef2c'
CORE=('v42_capacity/reference.py','v42_capacity/actual.py','v42_capacity/queue.py','v42_capacity/replay.py')
FOLDER='docs/v42_may_b0_zero_margin_holdout'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _utc(seconds):
    return datetime.fromtimestamp(seconds,timezone.utc).isoformat()


def _blob(repo,commit,path):
    return subprocess.check_output(['git','show',commit+':'+path],cwd=repo,stderr=subprocess.PIPE)


def _git_check(repo,commit,path,local):
    blob=_blob(repo,commit,path)
    receipt=file_record(local)
    exact=blob==Path(local).read_bytes()
    if not exact:
        raise ValueError('PR129_ORIGINAL_GIT_BLOB_BYTES_DRIFT:'+path)
    return dict(commit=commit,git_path=path,git_blob_sha256=hashlib.sha256(blob).hexdigest(),
                exact_bytes=True,local=receipt)


def audit_reference(candidate_path, current_folder, archive_root, *, repo, output):
    """Check324 rows, output prior model pins only; no placement or solver."""
    repo,current_folder,archive_root,output=map(Path,(repo,current_folder,archive_root,output))
    candidate=_read(candidate_path)
    if digest({k:v for k,v in candidate.items() if k!='initial_state_sha'})!=candidate['initial_state_sha']:
        raise ValueError('CURRENT_DDAY_BOUNDARY_CANDIDATE_SHA_DRIFT')
    if candidate['private_future_runtime_or_completion_values_in_candidate']:
        raise ValueError('PRIVATE_FUTURE_VALUES_IN_DDAY_BOUNDARY')
    running=[r for r in candidate['initial_source_roster'] if r['boundary_source_state']=='RUNNING']
    fixed={r['job_uid']:r['current_model_site'] for r in running if r['current_model_site'] is not None}
    missing=[r for r in running if r['job_uid'] not in fixed]
    if (len(running),sum(r['GPU_gang'] for r in running),len(fixed),
        sum(r['GPU_gang'] for r in running if r['job_uid'] in fixed),len(missing),
        sum(r['GPU_gang'] for r in missing))!=(324,472,151,296,173,176):
        raise ValueError('DDAY_324_472_151_296_173_176_COUNTS_DRIFT')
    if set(candidate['excluded_UIDs']).intersection(r['job_uid'] for r in running):
        raise ValueError('COMPLETED44_REINTRODUCED_IN_DDAY_RUNNING')
    if len({r['job_uid'] for r in running})!=324:
        raise ValueError('DDAY_RUNNING_DUPLICATE_UID')
    old_folder=archive_root/'BUNDLE/DAY_20250501'
    old_input=archive_root/'INPUT/BUNDLE/DAY_20250501'
    ref_path=old_folder/'REFERENCE.json'
    freeze_path=old_folder/'PLANNING_FREEZE.json'
    old_plan_path=old_input/'PLANNING_INPUT_BUNDLE.json'
    old_provenance_path=old_input/'SOURCE_PROVENANCE.json'
    current_plan_path=current_folder/'PLANNING_INPUT_BUNDLE.json'
    current_native_path=current_folder/'NATIVE_INPUT_TEMPLATE_B1.json'
    current_provenance_path=current_folder/'SOURCE_PROVENANCE.json'
    git_proofs=[_git_check(repo,PR129_HEAD,FOLDER+'/BUNDLE/DAY_20250501/'+name,old_folder/name)
                for name in ('REFERENCE.json','PLANNING_FREEZE.json','INPUT_FREEZE.json','ACTUAL_CAPACITY_RECEIPT.json')]
    for name in CORE:
        git_proofs.append(_git_check(repo,PR129_HEAD,name,repo/name))
        git_proofs.append(_git_check(repo,PR125_HEAD,name,repo/name))
    reference,freeze,old_plan,current_plan,native,old_prov,current_prov=map(_read,
        (ref_path,freeze_path,old_plan_path,current_plan_path,current_native_path,old_provenance_path,current_provenance_path))
    ref_receipt=file_record(ref_path)
    if freeze['reference']['sha256']!=ref_receipt['sha256'] or not freeze['freeze_before_Actual_truth']:
        raise ValueError('PR129_REFERENCE_PRE_ACTUAL_FREEZE_NOT_ESTABLISHED')
    if file_record(old_plan_path)['sha256']!=file_record(current_plan_path)['sha256']:
        raise ValueError('PR129_CURRENT_ISSUE_REQUEST_PROJECTION_CHANGED')
    refs={r['job_uid']:r for r in reference['rows']}
    if len(refs)!=len(reference['rows']) or len(refs)!=1649:
        raise ValueError('PR129_KNOWN_REFERENCE_UID_ROSTER_DRIFT')
    issue=datetime.fromisoformat(old_plan['issue_time']).timestamp()
    begin=candidate['Actual_begin_seconds']
    same_axis=issue==candidate['planning_issue_seconds'] and begin-issue==24*900 and old_plan['day']==candidate['day']=='2025-05-01'
    if old_plan['capacities']!=current_plan['capacities'] or native['capacities']!=old_plan['capacities']:
        raise ValueError('PR129_CURRENT_780_SITE_CAPACITY_DRIFT')
    capacities=current_plan['capacities']
    compatible=current_plan['rack_compatibility']
    # PR129 exposes one maximum single-gang envelope; current Native has four
    # nonadditive logical envelopes. Their site total and maximum gang must
    # agree; four envelopes never create four times the site capacity.
    rack_equal=all(max(old_plan['rack_compatibility'][s])==max(compatible[s])==
        max(r['compatibility_GPU_limit'] for r in native['racks'] if r['aidc_id']==s) for s in capacities)
    site_source=reference['audit']
    no_future=site_source['actual_reads']==0 and site_source['optimizer_calls']==0
    grid_blind=site_source['voltage_reads']==0 and site_source['optimizer_calls']==0
    if not no_future or not grid_blind or not site_source['full_reference_ready']:
        raise ValueError('PR129_PRE_POLICY_GRID_BLIND_REFERENCE_NOT_READY')
    fixed_use=Counter()
    prior_use=Counter()
    for row in running:
        uid=row['job_uid']
        if uid in fixed:fixed_use[fixed[uid]]+=row['GPU_gang']
        elif uid in refs:prior_use[refs[uid]['reference_site']]+=row['GPU_gang']
    joint_use={s:fixed_use[s]+prior_use[s] for s in capacities}
    overloaded={s for s in capacities if joint_use[s]>capacities[s]}
    pins={};cross=[]
    source_paths=[Path(candidate_path),ref_path,freeze_path,old_plan_path,old_provenance_path,
        current_plan_path,current_native_path,current_provenance_path,
        archive_root/'ADAPTED_SOURCE/v42_capacity/planning.py',
        archive_root/'ADAPTED_SOURCE/v42_capacity/replay.py',*[repo/x for x in CORE]]
    receipts=[file_record(p) for p in source_paths]
    for row in sorted(running,key=lambda r:r['job_uid']):
        uid=row['job_uid'];old=refs.get(uid);is_fixed=uid in fixed
        ep=episode_id(uid,row['source_submit_seconds'])
        request_same=bool(old and old['source_member']==row['source_member'] and old['source_row']==row['source_row']
            and datetime.fromisoformat(old['submit_time']).timestamp()==row['source_submit_seconds']
            and old['GPU_gang']==row['GPU_gang'] and old['Q50_total_seconds']==row['frozen_Q50_total_seconds']
            and old_prov['archive']['sha256']==current_prov['archive']['sha256'])
        # A prior PENDING reference is a frozen assignment for the same unique
        # raw request/episode, not proof that its planned start actually ran.
        # For prior RUNNING, its observed start must also match exactly.
        episode_same=bool(request_same and ((old['state_at_D1_cutoff']=='RUNNING'
            and issue-old['elapsed_seconds']==row['observed_start_seconds']) or
            (old['state_at_D1_cutoff']=='PENDING' and issue<=row['observed_start_seconds']<=begin)))
        prior_site=None if old is None else old['reference_site']
        allowed=bool(old and prior_site in row['compatible_sites'] and prior_site in capacities
                     and any(row['GPU_gang']<=limit for limit in compatible[prior_site]))
        checks=dict(SAME_UID_AND_RAW_EXECUTION_EPISODE=episode_same,
            SAME_MAY01_AXIS_OR_EXPLICIT_24SLOT_ADJUSTMENT=same_axis,
            SAME_GPU_GANG_AND_FROZEN_REQUEST=request_same,
            SAME_12_SITE_IDS_AND_780_CAPACITY=old_plan['capacities']==current_plan['capacities'],
            SAME_OR_EXPLICITLY_NONADDITIVE_RACK_COMPATIBILITY=bool(rack_equal and allowed),
            NO_FUTURE_ACTUAL_END_SITE_SELECTION=no_future,
            NO_GRID_VOLTAGE_LOADING_OR_UB_SELECTION=grid_blind,
            NO_CONFLICT_WITH_FIXED151_AND_JOINT_CURRENT_CAPACITY=bool(old and
                (not is_fixed or prior_site==fixed[uid]) and (is_fixed or prior_site not in overloaded)),
            EXISTING_RUNNING_LOCATION_UNCHANGED=bool(not is_fixed or prior_site==fixed[uid]),
            NO_OTHER_ARM_POLICY_EXECUTION_RESULT=bool(freeze['freeze_before_Actual_truth']
                and old and old['site_authority_source']=='USER_DEFINED_GRID_BLIND_REFERENCE_PLACEMENT'))
        passed=all(checks.values()) and not is_fixed
        if passed:
            pins[uid]=dict(PASS=True,episode_id=ep,site=prior_site,observed_start_seconds=row['observed_start_seconds'],
                gpu=row['GPU_gang'],assigned_at_seconds=issue,assigned_at_semantics='FROZEN_REFERENCE_MODEL_ISSUE_SNAPSHOT_NOT_KESTREL_ACTION_TIME',
                policy_independent=True,future_completion_used=False,grid_or_policy_result_used=False,
                INITIAL_SITE_AUTHORITY='REUSED_SYNTHETIC_GRID_BLIND_REFERENCE',KESTREL_OBSERVED_SITE=False,
                source_receipt=ref_receipt,checks=checks,checks_sha=digest(checks))
        status=('FROZEN_151_SITE_PRESERVED' if is_fixed else 'PR129_PRIOR_MODEL_SITE_REUSABLE' if passed
            else 'PR129_REFERENCE_UID_ABSENT' if old is None else 'PR129_JOINT_CURRENT_CAPACITY_CONFLICT'
            if prior_site in overloaded else 'PR129_IDENTITY_OR_AUTHORITY_UNRESOLVED')
        cohort=str(next((r for r in native['known_population'] if r['job_uid']==uid),{}).get('cohort','')).split('|')
        cross.append(dict(job_uid=uid,episode_id=ep,
            episode_identity_evidence='SAME_UNIQUE_ARCHIVE_MEMBER_ROW_UID_SUBMIT; observedRUNNINGstart checked when available in priorreference',
            submit_UTC=_utc(row['source_submit_seconds']),submit_seconds=row['source_submit_seconds'],
            origin_unknown_at_D1=row['origin_unknown'],source_state_at_D1=row['source_state_at_issue'],
            state_at_DDAY00='RUNNING',observed_start_UTC=_utc(row['observed_start_seconds']),
            observed_start_seconds=row['observed_start_seconds'],GPU_gang=row['GPU_gang'],
            GPU_type=None,GPU_type_authority='UNCONFIRMED; ORIGINAL_MODEL_COMPATIBLE_SITE_ENVELOPE_RETAINED',
            QoS=cohort[0] if cohort else None,current_frozen_site=row['current_model_site'],
            PR129_reference_UID_present=old is not None,PR129_reference_site=prior_site,
            PR129_site_authority=None if old is None else old['site_authority_source'],
            PR129_reference_state_at_issue=None if old is None else old['state_at_D1_cutoff'],
            PR129_reference_start_issue_slot=None if old is None else old['reference_start'],
            prior_assignment_model_snapshot_seconds=issue if old else None,
            frozen_site_matches_prior=None if not is_fixed or old is None else fixed[uid]==prior_site,
            previous_completed44_overlap=False,raw_KESTREL_observed_AIDC_site=None,
            KESTREL_OBSERVED_SITE=False,PR129_reusable_model_site=prior_site if passed else None,
            recovery_PASS=passed,classification=status,source_member=row['source_member'],source_row=row['source_row'],
            PR129_reference_source_path=ref_receipt['path'],PR129_reference_source_SHA=ref_receipt['sha256'],
            PR129_head=PR129_HEAD,PR125_head=PR125_HEAD,source_capacities_sha=digest(capacities),
            source_record_GPU_or_service_changed=False,old_actual_result_promoted=False,
            **checks))
    reused_use=Counter(fixed_use)
    for uid,pin in pins.items():reused_use[pin['site']]+=pin['gpu']
    if any(reused_use[s]>capacities[s] for s in capacities):
        raise ValueError('PR129_ACCEPTED_PIN_CURRENT_CAPACITY_CONFLICT')
    audit=dict(schema='PR129_PRIOR_GRID_BLIND_REFERENCE_RECOVERY_AUDIT_V1',audit_completed=True,
        PR129_head=PR129_HEAD,PR125_head=PR125_HEAD,git_proofs=git_proofs,
        counts=dict(RUNNING_00=324,RUNNING_GPU=472,fixed=151,fixed_GPU=296,unresolved=173,unresolved_GPU=176,
            reference_UID_overlap=sum(r['PR129_reference_UID_present'] for r in cross),
            prior_pending_reference_UID_overlap=sum(r['PR129_reference_state_at_issue']=='PENDING' for r in cross),
            fixed151_reference_site_agreement=sum(r['frozen_site_matches_prior'] is True for r in cross),
            fixed151_reference_site_conflict=sum(r['frozen_site_matches_prior'] is False for r in cross),
            reusable_prior_model_sites=len(pins),reusable_prior_model_GPU=sum(p['gpu'] for p in pins.values()),
            residual_fallback_jobs=173-len(pins),residual_fallback_GPU=176-sum(p['gpu'] for p in pins.values())),
        validated_pins=pins,source_receipts=receipts,per_UID_checks=cross,
        issue_seconds=issue,DDAY_begin_seconds=begin,axis_adjustment_slots=24,
        INITIAL_SITE_AUTHORITY='REUSED_SYNTHETIC_GRID_BLIND_REFERENCE',KESTREL_OBSERVED_SITE=False,
        SOURCE18R_NUMERICALLY_IDENTICAL=False,PR129_NUMERICALLY_IDENTICAL=False,
        PR129_physics='7RegControl frozen zero-margin B0',current_physics='approved11SVR source; no oldAC/power transfer',
        policy_specific_actual_ledger=file_record(old_folder/'ACTUAL_QUEUE_LEDGER.csv'),
        policy_specific_actual_ledger_used_for_sites=False,policy_specific_actual_power_or_AC_transferred=False,
        current_joint_all_prior_reference_use=joint_use,overloaded_reference_sites=sorted(overloaded),
        overloaded_site_groups_rejected_entirely=True,no_capacity_cherrypick=True,
        accepted_fixed151_plus_reused_use=dict(reused_use),site_capacities=capacities,
        frozen151_sites_changed=0,completed44_reintroduced=0,synthetic_new_site_assignment_calls=0,
        Native_Optimize_calls=0,private_future_completion_reads=0,grid_or_MESS_selection_reads=0,
        source_prior_pending_is_not_observed_actual_execution=True,
        source_raw_request_version_history='UNVERIFIED_SOURCE_PROXY; exactsameprojectedmodelrequests, not customercontractclaim')
    reuse=dict(schema='PR125_GRID_BLIND_REUSE_AUDIT_V1',PR125_head=PR125_HEAD,
        exact_source_functions=git_proofs[4:],PR129_reference_audit=ref_receipt,
        reused_primitives=['build_reference','RUNNING source_site pins first','whole-gang issue_use capacity',
            'numeric site order','GPU-descending thenUID unassignedRUNNING order','strictFCFS submit/UID PENDING order',
            'Controller/EpisodeLedger observed physical completion separate from nominal expiry'],
        approved_adjustments=['issue_time=DDAY00','observed324RUNNING frame replaces old254issue frame',
            '151Source18r sites and validated prior modelpins fixed first','1300observedPENDING queue kept complete',
            'single-gang logical rack envelope nonadditive; preserve all12site capacity'],
        rejected_reuse=['PR129 B0 actual_queue admission/site','PR129 actual_GPU/PCC/FreshAC',
            'conflicting151reference replacement','entireoverloaded current reference site groups'],
        model_assumption='V42_DDAY_COMMON_GRID_BLIND_INITIAL_SITE_V1 + COMMON_GRID_BLIND_FCFS_QUEUE_V1',
        known_unknown_initialization_rule_same=True,old_reference_not_regenerated_in_this_audit=True,
        future_completion_or_grid_UB_in_assignment_inputs=False,new_assignment_algorithm=False,
        greedy_failure_does_not_prove_integer_infeasibility=True,solver_calls=0,
        prior_recovered_jobs=len(pins),prior_recovered_GPU=sum(p['gpu'] for p in pins.values()),
        expected_remaining_PR125_fallback_jobs=173-len(pins),expected_remaining_PR125_fallback_GPU=176-sum(p['gpu'] for p in pins.values()),
        Actual96_or_newFreshAC_PASS_transferred=False,source_receipts=receipts)
    output.mkdir(parents=True,exist_ok=True)
    for name,value in (('PR129_REFERENCE_SITE_RECOVERY.json',audit),('PR125_GRID_BLIND_REUSE_AUDIT.json',reuse)):
        if (output/name).exists():raise FileExistsError('PR129_RECOVERY_ARTIFACT_EXISTS:'+str(output/name))
        _write(output/name,value)
    for name in ('PR129_MAY01_REFERENCE_CROSSWALK.csv','PR129_REFERENCE_SITE_RECOVERY.csv','MAY01_RUNNING_324_CROSSWALK.csv'):
        path=output/name
        if path.exists():raise FileExistsError('PR129_RECOVERY_ARTIFACT_EXISTS:'+str(path))
        with path.open('w',newline='',encoding='utf8') as stream:
            writer=csv.DictWriter(stream,fieldnames=tuple(cross[0]));writer.writeheader();writer.writerows(cross)
    return audit
