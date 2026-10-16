"""Post-Golden bindings to original inputs, windows and private event service.

Planning is never rebuilt. This adapter retains the 18:00 Known roster through
the entire prefix and day. Missing initial sites are an explicit Actual model
assumption, separate from the numerical Golden and Source permission claims.
"""
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import shutil

import numpy as np

from v43.common import DOC, RUNS, ROOT, read, record, verify_records, atomic
from .io import checked
from .vendor.actual import JobRequest, FrozenPowerModel, _require_public_metadata
from .vendor.qos import TrainingStatistics, CohortStatistic, ObservedJob, CausalReferenceScheduler
from .vendor.policy import digest
from .vendor.known_commands import compile_known_commands
from .vendor.initial_state import prepare_initialization, verified_initial_sites
from .windows import OriginalKnownWindows

BUNDLE = Path('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE/DAY_20250501')
STATS = Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/QOS_EMPIRICAL_STATS_STRICT.json')


def load_stats(path=STATS):
    doc = read(path)
    if doc['descriptive_only']:
        raise ValueError('DESCRIPTIVE_STATS_HAVE_NO_QOS_AUTHORITY')
    rows = tuple(CohortStatistic(r['level'],tuple(r['key']),r['n_unique_uids'],r['q90_higher_z']) for r in doc['cohorts'])
    result = TrainingStatistics(doc['cutoff_seconds'],doc['source_sha'],rows,
        tuple(doc.get('uids',[])),doc['input_rows'],doc['exclusions'],False,doc['provenance_note'])
    if digest(result.to_dict()) != digest({k:v for k,v in doc.items() if k != 'uids'}):
        raise ValueError('STRICT_STATS_SOURCE_DRIFT')
    return result


def accepted():
    certificate = read(DOC/'GOLDEN003_CERTIFIED_NUMERICAL_CASE.json')
    if not certificate['Gate_A_PASS']:
        raise ValueError('GATE_A_PASS_REQUIRED')
    verify_records([certificate[k] for k in ('result','planning_freeze','planning_arrays')])
    freeze = read(certificate['planning_freeze']['path'])
    verify_records(list(freeze['scientific_input'].values()))
    native = read(freeze['scientific_input']['NATIVE_INPUT.json']['path'])
    windows = read(freeze['scientific_input']['WINDOWS.json']['path'])
    with np.load(certificate['planning_arrays']['path'],allow_pickle=False) as stream:
        arrays = {k:stream[k].copy() for k in stream.files}
    return certificate,freeze,native,windows,arrays


def initialize(output):
    """Reuse the existing issue-only capacity algorithm; no private service read."""
    output = Path(output)
    certificate,freeze,native,windows,arrays = accepted()
    inputs = output/'INPUTS'
    inputs.mkdir(parents=True,exist_ok=True)
    pairs = [(Path(freeze['scientific_input']['NATIVE_INPUT.json']['path']),inputs/'NATIVE_INPUT_TEMPLATE_B1.json'),
             (BUNDLE/'PLANNING_INPUT_BUNDLE.json',inputs/'PLANNING_INPUT_BUNDLE.json')]
    for source,target in pairs:
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError('ACTUAL_INITIAL_INPUT_DRIFT')
        if not target.exists():
            shutil.copyfile(source,target)
    policy_path = output/'INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json'
    if not policy_path.exists():
        prepare_initialization(inputs,policy_path.parent,budget=None,
            source_assessment=dict(scope='V43_ACTUAL_ONLY_ISSUE18_MODEL_INITIALIZATION',
                observed_site_claim=False,Golden003_planning_modified=False))
    plan = read(inputs/'PLANNING_INPUT_BUNDLE.json')
    policy = verified_initial_sites(policy_path,native,plan)
    return policy,policy_path


def power_model(power, capacities):
    """Load the same C1 model/implementation; no fitting or coefficient repair."""
    model_path = checked(power['C1'])
    implementation = checked(power['C1_implementation'])
    # Bind PR189's original backend before the older C1 package root. The
    # current AC adapter must resolve the same seven-RegControl compiler.
    from v42_regcontrol.authority import source
    source()
    import sys
    sys.path.insert(0,str(implementation.parents[2]))
    module = importlib.import_module('dayahead.v28r2.c1_affine')
    if record(module.__file__)['sha256'] != power['C1_implementation']['sha256']:
        raise ValueError('EXACT_ORIGINAL_C1_SOURCE_REQUIRED')
    parameters = module.load_c1(model_path)
    thermal = importlib.import_module('dayahead.v28.thermal')
    receipts = [record(implementation),record(model_path),record(thermal.__file__)]
    authority = digest(dict(idle=power['current_IT_idle_kW_per_installed_GPU'],
        swing=power['current_IT_swing_kW_per_active_GPU'],power_factor=power['PF_AIDC'],sources=receipts))
    callback = lambda it,w:module.exact_c1_pcc_kw(it,float(w['t_wb_c']),float(w['rh_pct']),parameters)
    return FrozenPowerModel(power['current_IT_idle_kW_per_installed_GPU'],
        power['current_IT_swing_kW_per_active_GPU'],capacities,power['PF_AIDC'],callback,authority),receipts


def prepare(output, *, private_service=True):
    output = Path(output)
    certificate,freeze,native,windows,arrays = accepted()
    initial,initial_path = initialize(output)
    plan,actual,provenance,power = [read(BUNDLE/name) for name in
        ('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json')]
    issue = datetime.fromisoformat(plan['issue_time']).timestamp()
    midnight = datetime.fromisoformat(plan['day']).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
    end = midnight+86400
    if issue != datetime.fromisoformat(native['issue_time']).timestamp() or midnight-issue != 21600:
        raise ValueError('PR189_18AEST_ISSUE_AXIS_REQUIRED')
    raw = {r['job_uid']:r for r in native['known_population']}
    if set(raw) != {r['job_uid'] for r in plan['known_population']}:
        raise ValueError('ORIGINAL_KNOWN_ROSTER_CHANGED')
    provider_sha = digest(dict(runtime=native['runtime_provider'],runtime_authority=plan['runtime_authority']))
    case_sha = digest(dict(Golden003=certificate['planning_freeze'],initialization_sha=initial['initialization_sha'],
        axis=[issue,midnight,end],Known_windows=freeze['scientific_input']['WINDOWS.json'],
        unknown_contract='V43_STRICT_PENDING_PRESITE_SHARED_C0_C1'))
    reference_sha = digest(dict(rule='PR189_KNOWN_REFERENCE_THEN_CAUSAL_GRID_BLIND_UNKNOWN',
        Known_input=freeze['scientific_input']['NATIVE_INPUT.json'],initialization=initial['initialization_sha']))
    reference = CausalReferenceScheduler(plan['capacities'],reference_sha=reference_sha)
    qos = OriginalKnownWindows(load_stats(),case_sha=case_sha,provider_sha=provider_sha,
        windows=windows,issue_seconds=issue,
        external_running=[uid for uid,row in raw.items() if row['state']=='RUNNING'
            and uid not in {w['job_id'] for w in windows} and row['service_slots']==0])
    window_by = {r['job_id']:r for r in windows}
    population = plan['known_population']+actual['post_issue_arrivals']
    if len({r['job_uid'] for r in population}) != len(population):
        raise ValueError('DUPLICATE_PHYSICAL_UID')
    requests,running = [],[]
    representation = tuple(float(t) for t in np.arange(issue,end+900,900))
    for row in population:
        uid = row['job_uid']
        known = uid in raw
        metadata = {key:row.get(key) for key in ('protected','batch_eligible','requested_walltime_seconds')}
        metadata.update(qos=row.get('qos','UNCONFIRMED'),partition=row.get('partition',''),
            origin_unknown=not known,state=row['state'],representation_starts_seconds=representation,
            source_request_provenance=row['request_version_history'],
            can_prestart_place=bool(raw[uid].get('can_prestart_place',False)) if known else False,
            Can_TimeShift=bool(raw[uid].get('can_timeshift',False)) if known else False,
            Can_Checkpoint_Migrate=False,
            metadata_authority='ORIGINAL_KNOWN_MODEL_WINDOWS' if known else 'STRICT_OBSERVED_SOURCE_ATTRIBUTES',
            source_customer_permission_claim=False,initial_research_placement_is_change_consent=False)
        if known:
            metadata['reference_start_seconds'] = issue+900*window_by.get(uid,{'reference_start':0})['reference_start']
        site = initial['mapping'][uid] if row['state'] == 'RUNNING' else row.get('source_site')
        if row['state'] == 'RUNNING':
            initial_row = next(r for r in initial['per_job'] if r['uid'] == uid)
            metadata.update(elapsed_compute_seconds=row['elapsed_seconds'],episode_id=initial_row['episode_id'],
                initial_site_source=initial_row['INITIAL_SITE_SOURCE'],KESTREL_OBSERVED_SITE=False)
        _require_public_metadata(metadata)
        request = JobRequest(uid,datetime.fromisoformat(row['submit_time']).timestamp(),int(row['GPU_gang']),
            tuple(row['compatible_sites']),row['Q50_total_seconds'],site,metadata)
        if row['state'] == 'RUNNING':
            running.append((request,site,issue-row['elapsed_seconds']))
        else:
            requests.append(request)
    # Establish Known references before observing any post-issue arrival. Keep
    # native reference locations and windows; no new planning/reference solve.
    for request,site,start in sorted(running,key=lambda x:(x[0].submit,x[0].uid)):
        reference.observe_running(request,site=site,start_seconds=start,event_seconds=issue,
            elapsed_compute_seconds=issue-start)
    for request in sorted((r for r in requests if r.uid in raw),key=lambda r:(r.submit,r.uid)):
        row = raw[request.uid]
        site = row['planning_site']
        start = issue+900*window_by[request.uid]['reference_start']
        release = max(start+900,issue+900*row['reference_end'])
        reference.reservations[site].append((start,release,request.gpu))
        reference.assigned[request.uid] = dict(uid=request.uid,reference_site=site,reference_start_seconds=start,
            nominal_release_seconds=release,origin='PR189_ORIGINAL_KNOWN_REFERENCE',reference_sha=reference_sha)
        reference.last_pending_start_seconds = max(reference.last_pending_start_seconds,start)
    commands = compile_known_commands(freeze['selected_jobs'],slot_zero_seconds=issue,
        gpu_by_uid={uid:row['GPU_gang'] for uid,row in raw.items()})
    model,power_sources = power_model(power,plan['capacities'])
    result = dict(capacities=plan['capacities'],requests=requests,running=running,reference=reference,
        qos_window_provider=qos,known_schedule=commands,begin=issue,end=end,arm='B1',
        power_model=model)
    from v42_final.workload import ForecastBook
    cc4=plan['forecast_inputs']['current_CC4']
    result['forecast']=ForecastBook(tuple(cc4['Q50_GPUh']),tuple(cc4['Q90_GPUh']),midnight)
    identity = dict(schema='V43_PR189_POSTFREEZE_EVENT_CASE_V1',case_sha=case_sha,
        provider_sha=provider_sha,reference_sha=reference_sha,initialization=record(initial_path),
        Known=len(raw),Unknown=len(population)-len(raw),initial_Running=len(running),
        known_commands=len(commands),Known_commands_sha=digest(commands),
        source_receipts=[record(BUNDLE/name) for name in ('PLANNING_INPUT_BUNDLE.json',
            'ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json')]+[record(STATS)]+power_sources,
        Golden003=certificate['planning_freeze'],Golden_reexecuted=False,Planning_modified=False,
        Source_initial_running_sites_certified=False,missing_initial_sites='44_MODEL_ASSUMED',
        external_Running_continuation_without_native_window=len(qos.external_running),
        Unknown_reclassified_at_midnight=0,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',CAUSAL_PASS=False,
        Actual96_PASS=False,Fresh96_PASS=False,Native_calls=0)
    if private_service:
        from .vendor.private_truth import _truth
        from v42_capacity.actual import Environment
        truth,archive = _truth(population,provenance['archive'])
        completions = {}
        for request,site,start in running:
            observed = truth[request.uid]
            completion = datetime.fromisoformat(observed['end_time']).timestamp()
            if datetime.fromisoformat(observed['start_time']).timestamp() != start or not start <= issue < completion:
                raise ValueError('INITIAL_RUNNING_OBSERVED_HISTORY_SOURCE_DRIFT')
            completions[request.uid] = completion
        result['environment'] = Environment({uid:r['realized_seconds'] for uid,r in truth.items()},completions)
        identity.update(private_source=archive,private_exact_join_count=len(truth),
            private_service_controller_features=False)
    atomic(output/'CASE_BINDINGS.json',identity)
    return result,identity
