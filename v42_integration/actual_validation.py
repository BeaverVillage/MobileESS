"""Isolated real May Job-event/power validation; never starts a campaign.

Source descriptors and frozen Q50 enter the controller. Exact retrospective
service is joined only after source freeze, exclusively inside PR125's private
Environment. Fresh AC accepts recomputed Actual injections and verified frozen
11-SVR hardware; it does not promote old campaign/model certification.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from .qos import TrainingStatistics, CohortStatistic, QoSWindowProvider


class InitialStateAuthorityBlocked(ValueError):
    def __init__(self, receipt):
        super().__init__("OBSERVED_RUNNING_SITE_AUTHORITY_MISSING:"+str(receipt["missing_running_site_jobs"]))
        self.receipt = receipt


class DDayInitialStateAuthorityBlocked(ValueError):
    def __init__(self,receipt):
        super().__init__('DDAY_INITIAL_STATE_NOT_AUTHORIZED:'+receipt['status'])
        self.receipt=receipt


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def record(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def checked(receipt):
    from v42_capacity.common import resolve
    path = Path(resolve(receipt))
    actual = record(path)
    if any(actual[key] != receipt[key] for key in ("sha256", "bytes")):
        raise ValueError("INTEGRATION_ACTUAL_SOURCE_RECEIPT_DRIFT")
    return path


def write(path, value):
    from .m_engine import _json_value
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_value(value), indent=2, ensure_ascii=False,
                               allow_nan=False)+"\n", encoding="utf-8")


def load_stats(path):
    doc = read(path)
    if doc["descriptive_only"]:
        raise ValueError("DESCRIPTIVE_STATS_HAVE_NO_QOS_AUTHORITY")
    rows = tuple(CohortStatistic(row["level"], tuple(row["key"]), row["n_unique_uids"], row["q90_higher_z"])
                 for row in doc["cohorts"])
    result = TrainingStatistics(doc["cutoff_seconds"], doc["source_sha"], rows,
        tuple(doc.get("uids", [])), doc["input_rows"], doc["exclusions"], False, doc["provenance_note"])
    if result.to_dict() != {key: value for key, value in doc.items() if key != "uids"}:
        # JSON tuples/lists are equivalent, but every scientific field matters.
        from .policy import digest
        if digest(result.to_dict()) != digest({key: value for key, value in doc.items() if key != "uids"}):
            raise ValueError("QOS_STATISTICS_RELOAD_DRIFT")
    return result


def inspect_inputs(folder, output=None):
    """Read-only data coverage inspection; no retrospective truth or AC."""
    folder = Path(folder)
    names = ("PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "POWER_AUTHORITY.json")
    plan, actual, provenance, power = [read(folder/name) for name in names]
    if plan["day"] != actual["day"] or plan["capacities"] != actual["capacities"] or plan["slot_seconds"] != 900:
        raise ValueError("REAL_ACTUAL_CASE_DESCRIPTOR_MISMATCH")
    population = plan["known_population"]+actual["post_issue_arrivals"]
    result = dict(day=plan["day"], sources=[record(folder/name) for name in names],
        known_jobs=len(plan["known_population"]), origin_unknown_jobs=len(actual["post_issue_arrivals"]),
        observed_running_jobs=sum(row["state"] == "RUNNING" for row in plan["known_population"]),
        missing_qos_jobs=sum("qos" not in row for row in population),
        missing_batch_eligibility_jobs=sum("batch_eligible" not in row for row in population),
        missing_request_walltime_jobs=sum("requested_walltime_seconds" not in row for row in population),
        missing_raw_physical_site_jobs=sum(row.get("source_site") is None for row in population),
        request_version_status="UNVERIFIED_SOURCE_PROXY", protected_status="UNCONFIRMED_WHERE_ABSENT",
        completion_observation_rows=sum(row.get("end_observed_by_day_end") is not None
                                        for row in actual["observed_known_episodes"]),
        private_truth_source=provenance["archive"], C1=power["C1"], C1_implementation=power["C1_implementation"],
        source_hourly_NOAA=provenance["daily_sources"]["noaa_actual_weather.parquet"],
        raw_site_absence_does_not_establish_migration_authority=True, solver_calls=0, actual_executed=False)
    if output is not None:
        write(output, result)
    return result


def audit_initial_state(folder, output=None):
    """Read-only private simulator audit; never emits controller features."""
    from v42_voltage_control.b0_new import _truth
    folder = Path(folder)
    plan, actual, provenance, native = [read(folder/name) for name in (
        "PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "NATIVE_INPUT_TEMPLATE_B1.json")]
    source_rows = [record(folder/name) for name in (
        "PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "NATIVE_INPUT_TEMPLATE_B1.json")]
    truth, archive = _truth(plan["known_population"]+actual["post_issue_arrivals"], provenance["archive"])
    issue = pd.Timestamp(plan["issue_time"]).timestamp()
    day_begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    day_end = day_begin+86400
    assigned, missing = [], []
    for row in native["known_population"]:
        if row["state"] != "RUNNING":
            continue
        service = truth[row["job_uid"]]
        start, end = (pd.Timestamp(service[name]).timestamp() for name in ("start_time", "end_time"))
        item = dict(uid=row["job_uid"], gpu=row["GPU_gang"], source_modeled_current_site=row["current_site_if_running"],
            planning_eligible=row["planning_eligible"], source_external_end_issue_slot=row.get("unresolved_external_source_service_end"),
            source_start_seconds=start, source_end_seconds=end, observed_start_seconds=issue-row["elapsed_seconds"],
            observed_history_matches=abs(start-(issue-row["elapsed_seconds"])) <= 1e-6,
            private_source_issue_overlap_seconds=max(0., min(end, day_end)-max(start, issue)),
            private_source_Dday_overlap_seconds=max(0., min(end, day_end)-max(start, day_begin)))
        (assigned if row["current_site_if_running"] is not None else missing).append(item)
    result = dict(day=plan["day"], exact_private_source_join_count=len(truth), archive=archive,
        assigned_running_jobs=len(assigned), missing_running_site_jobs=len(missing),
        missing_running_site_GPU=sum(r["gpu"] for r in missing),
        missing_site_Dday_overlap_jobs=sum(r["private_source_Dday_overlap_seconds"] > 0 for r in missing),
        missing_site_issue_prefix_overlap_jobs=sum(r["private_source_issue_overlap_seconds"] > 0 for r in missing),
        assigned_running_history_mismatches=sum(not r["observed_history_matches"] for r in assigned),
        missing_rows=missing, assigned_rows=assigned, source_receipts=source_rows,
        private_audit_only=True, future_values_delivered_to_controller_or_qos=False,
        completion_before_Dday_is_retrospective_audit_not_planning_release_authority=True,
        actual_engine_executed=False, solver_calls=0)
    if any(record(r["path"]) != r for r in source_rows):
        raise ValueError("INITIAL_STATE_AUDIT_SOURCE_DRIFT")
    if output is not None:
        write(output, result)
    return result


def _weather(provenance, begin, end):
    path = checked(provenance["daily_sources"]["noaa_actual_weather.parquet"])
    frame = pd.read_parquet(path)
    if "ts" not in frame or not {"t_wb_c", "rh_pct"} <= set(frame):
        raise ValueError("ACTUAL_NOAA_TIMESTAMP_OR_PHYSICAL_FIELDS_MISSING")
    frame.index = pd.DatetimeIndex(frame.ts).tz_convert("UTC")
    if frame.index.duplicated().any():
        raise ValueError("ACTUAL_NOAA_DUPLICATE_OBSERVATION")
    target = pd.date_range(pd.Timestamp(begin, unit="s", tz="UTC"),
                           pd.Timestamp(end, unit="s", tz="UTC"), freq="15min", inclusive="left")
    numeric = frame[["t_wb_c", "rh_pct"]]
    # Exact inherited realization.py rule: bracketed time-linear interpolation,
    # interval-start weather, no extrapolation or invented physical coefficient.
    weather = numeric.reindex(numeric.index.union(target)).sort_index().interpolate(
        method="time", limit_area="inside").reindex(target)
    if not np.isfinite(weather.to_numpy()).all():
        raise ValueError("ACTUAL_NOAA_BRACKETING_OBSERVATION_MISSING")
    rows = weather.to_dict("records")
    return rows, dict(source=record(path), interpolation_source=record(Path(__file__).parents[1]/"v42_holdout/realization.py"),
        interpolation="time/inside", slot_weather="interval_start", begin_UTC=target[0].isoformat(),
        slots=len(rows), actual_weather_used_only_in_actual_power=True)


def _power_model(power, capacities):
    from .actual import FrozenPowerModel
    from v42_voltage_control.b0_new import _c1
    # The existing reviewed loader binds physical packages first, preventing an
    # older C1 package root from redirecting the later IEEE123 compiler.
    module, parameters, receipts = _c1(power)
    if record(module.__file__)["sha256"] != power["C1_implementation"]["sha256"]:
        raise ValueError("EXACT_ACTUAL_C1_SOURCE_MISMATCH")
    from .policy import digest
    receipts += [record(sys.modules["dayahead.v28.thermal"].__file__)]
    authority_sha = digest(dict(idle=power["current_IT_idle_kW_per_installed_GPU"],
        swing=power["current_IT_swing_kW_per_active_GPU"], power_factor=power["PF_AIDC"], sources=receipts))
    callback = lambda it, weather: module.exact_c1_pcc_kw(it, float(weather["t_wb_c"]), float(weather["rh_pct"]), parameters)
    return FrozenPowerModel(power["current_IT_idle_kW_per_installed_GPU"],
        power["current_IT_swing_kW_per_active_GPU"], capacities, power["PF_AIDC"], callback, authority_sha), receipts


def _build_dday_actual_inputs(plan, actual, freeze, truth, qos, planning_known_receipts):
    """Bind the authorized midnight snapshot to public requests and private service.

    This function never admits a job or replays the pre-day queue. Future
    source values are checked here and remain solely in the Environment.
    """
    from copy import deepcopy
    from dataclasses import asdict, fields
    from .actual import JobRequest, _require_public_metadata
    from .qos import ObservedJob, CausalReferenceScheduler
    from .policy import digest
    from .dday_boundary import seconds
    from v42_capacity.actual import Environment
    begin, end = freeze['begin_epoch_seconds'], freeze['end_epoch_seconds']
    issue = seconds(plan['issue_time'])
    population = plan['known_population'] + actual['post_issue_arrivals']
    source = {row['job_uid']: row for row in population}
    known = {row['job_uid'] for row in plan['known_population']}
    if len(source) != len(population) or set(truth) != set(source):
        raise ValueError('DDAY_PRIVATE_SOURCE_UID_ROSTER_DRIFT')
    if (freeze['provider_identifiers'].get('CC4_provider_sha') != digest(plan['forecast_inputs']['current_CC4'])
            or freeze['provider_identifiers'].get('frozen_Q50_values_sha') !=
                digest({uid:row['Q50_total_seconds'] for uid,row in source.items()})):
        raise ValueError('DDAY_FROZEN_NOMINAL_OR_CC4_PROVIDER_DRIFT')
    initial = freeze['running'] + freeze['pending']
    initial_by_uid = {row['uid']: row for row in initial}
    if len(initial_by_uid) != len(initial):
        raise ValueError('DDAY_INITIAL_JOB_DUPLICATE')
    running_uids = {row['uid'] for row in freeze['running']}
    pending_uids = {row['uid'] for row in freeze['pending']}
    completed, future = [], []
    for uid, row in source.items():
        submit = seconds(row['submit_time'])
        service = truth[uid]
        start, completion = seconds(service['start_time']), seconds(service['end_time'])
        if completion < start or start < submit:
            raise ValueError('DDAY_PRIVATE_SOURCE_EVENT_ORDER')
        if submit > begin:
            future.append(uid)
        elif completion <= begin:
            completed.append(dict(uid=uid, submit_seconds=submit,
                observed_start_seconds=start, observed_completion_seconds=completion,
                gpu=row['GPU_gang'], origin_unknown=uid not in known,
                status='PRE_DDAY_COMPLETED_EXCLUDED_FROM_DDAY_ACTUAL',
                active_Dday_GPU=0, CC4_depletions=0, reregistrations=0))
        else:
            target = running_uids if start <= begin else pending_uids
            if uid not in target:
                raise ValueError('DDAY_SOURCE_OBSERVED_STATE_ROSTER_DRIFT')
    completed_uids = {row['uid'] for row in completed}
    expected_initial = set(source)-set(future)-completed_uids
    if set(initial_by_uid) != expected_initial or not set(freeze['excluded_44uids']) <= completed_uids:
        raise ValueError('DDAY_INITIAL_OR_EXCLUDED_UID_ROSTER_DRIFT')
    ordered_pending = sorted(freeze['pending'], key=lambda row:(row['submit_seconds'], row['uid']))
    if freeze['pending'] != ordered_pending or any(row['queue_position'] != i+1
            for i, row in enumerate(ordered_pending)):
        raise ValueError('DDAY_COMMON_FCFS_QUEUE_ORDER_DRIFT')
    representation = tuple(float(t) for t in np.arange(begin, end+900, 900))
    requests, running, durations, completions = [], [], {}, {}
    reused = []
    def request_for(uid, row=None):
        native = source[uid]
        submit = seconds(native['submit_time'])
        is_running = uid in running_uids
        state = 'RUNNING' if is_running else 'PENDING'
        if row is not None and (row['submit_seconds'] != submit or row['gpu'] != native['GPU_gang']
                or row['q50'] != native['Q50_total_seconds']
                or tuple(row['compatible_sites']) != tuple(native['compatible_sites'])
                or row['origin_unknown'] != (uid not in known)):
            raise ValueError('DDAY_FROZEN_REQUEST_CONTRACT_DRIFT:'+uid)
        metadata = deepcopy(row['metadata']) if row is not None else {}
        _require_public_metadata(metadata)
        metadata.update(state=state, origin_unknown=uid not in known,
            representation_starts_seconds=tuple(metadata.get('representation_starts_seconds', representation)),
            qos=metadata.get('qos', native.get('qos', 'UNCONFIRMED')),
            protected=metadata.get('protected', native.get('protected')),
            batch_eligible=metadata.get('batch_eligible', native.get('batch_eligible')),
            requested_walltime_seconds=metadata.get('requested_walltime_seconds', native.get('requested_walltime_seconds')),
            partition=metadata.get('partition', native.get('partition', '')),
            can_prestart_place=metadata.get('can_prestart_place', False),
            source_request_provenance=native.get('request_version_history'),
            common_initial_state_sha=freeze['common_initial_state_sha'],
            dday_initialization_seconds=begin, initial_observed_state=state if row is not None else None,
            cc4_eligible=submit >= begin,
            source_representation='EXPLICIT_DDAY_MIDNIGHT_96_SLOT_CONTROL_AXIS')
        for name in ('release_seconds', 'hard_earliest_start_seconds', 'hard_latest_start_seconds',
                     'completion_deadline_seconds'):
            if name in native and name not in metadata:
                metadata[name] = native[name]
        if uid in known:
            shared = planning_known_receipts.get(uid)
            prior = qos.receipts.get(uid)
            if shared is None or prior is None:
                raise ValueError('FROZEN_KNOWN_QOS_RECEIPT_REQUIRED:'+uid)
            old = deepcopy(shared['observed'])
            old['representation_starts_seconds'] = tuple(old['representation_starts_seconds'])
            old_job = ObservedJob(**old)
            if (old_job.uid != uid or old_job.gpu != native['GPU_gang'] or
                    old_job.submit_seconds != submit or old_job.t50_seconds != native['Q50_total_seconds']
                    or old_job.authority_sha != prior.authority_sha
                    or prior.case_sha != qos.case_sha or prior.provider_sha != qos.provider_sha
                    or prior.stats_sha != qos.stats.sha or digest(shared['receipt']) != digest(prior.to_dict())):
                raise ValueError('FROZEN_KNOWN_QOS_AUTHORITY_DRIFT:'+uid)
            # Contracts and reference remain exactly those issued at Planning.
            # State and event advance; observed execution history is separate.
            metadata.update(old)
            metadata.update(state=state, event_seconds=begin, origin_unknown=False,
                reused_planning_qos_authority=dict(uid=uid, case_sha=qos.case_sha,
                    provider_sha=qos.provider_sha, stats_sha=qos.stats.sha,
                    reference_sha=prior.reference_sha, authority_sha=prior.authority_sha, gpu=native['GPU_gang']))
            reused.append(uid)
        if row is not None:
            metadata.update(episode_id=row['episode_id'], initial_site_authority=row['initial_site_authority'],
                KESTREL_OBSERVED_SITE=False,
                elapsed_compute_seconds=row['elapsed_compute_seconds'])
        _require_public_metadata(metadata)
        site = row['site'] if is_running else None
        request = JobRequest(uid, submit, native['GPU_gang'], tuple(native['compatible_sites']),
            native['Q50_total_seconds'], site, metadata)
        durations[uid] = truth[uid]['realized_seconds']
        if is_running:
            start = row['observed_start_seconds']
            if (seconds(truth[uid]['start_time']) != start or
                    row['elapsed_compute_seconds'] != begin-start or
                    not start <= begin < seconds(truth[uid]['end_time'])):
                raise ValueError('DDAY_RUNNING_HISTORY_DRIFT:'+uid)
            running.append((request, site, start))
            completions[uid] = seconds(truth[uid]['end_time'])
        else:
            requests.append(request)
        return request
    for row in sorted(freeze['running'], key=lambda row:(row['submit_seconds'], row['uid'])):
        request_for(row['uid'], row)
    for row in ordered_pending:
        request_for(row['uid'], row)
    for uid in sorted(future, key=lambda uid:(seconds(source[uid]['submit_time']), uid)):
        request_for(uid)
    ref_sha = digest(dict(rule='DDAY_CAUSAL_GRID_BLIND_REFERENCE_V1',
        common_initial_state_sha=freeze['common_initial_state_sha'], capacities=plan['capacities'],
        nominal_provider=freeze['provider_identifiers']))
    shadow = CausalReferenceScheduler(plan['capacities'], reference_sha=ref_sha)
    for request, site, start in running:
        shadow.observe_running(request, site=site, start_seconds=start,
            event_seconds=begin, elapsed_compute_seconds=begin-start)
    # Future arrivals remain absent from the reference until their submit event.
    for request in requests:
        if request.uid in pending_uids:
            shadow.submit(request, event_seconds=begin)
    audit = dict(initial_running_jobs=len(running), initial_running_GPU=sum(r[0].gpu for r in running),
        initial_pending_jobs=len(pending_uids), initial_pending_GPU=sum(source[uid]['GPU_gang'] for uid in pending_uids),
        future_submission_jobs=len(future), historical_completed_jobs=len(completed),
        excluded_44_active_GPU=0, Known_receipts_reused_without_reissue=len(reused),
        prefix_origin_unknown_jobs=sum(row['origin_unknown'] for row in initial),
        prefix_origin_unknown_CC4_depletions=0, pending_queue_order=[row['uid'] for row in ordered_pending],
        preday_queue_replay_executed=False, actual_engine_executed=False,
        future_UIDs_in_reference=0, new_QoS_receipts_before_Actual=0,
        observed_history_rewrites=0, source_issue_epoch_seconds=issue,
        simulated_begin_epoch_seconds=begin, simulated_end_epoch_seconds=end, simulated_slots=96)
    return dict(requests=requests, running=running, environment=Environment(durations, completions),
        reference=shadow, historical_source_ledger=sorted(completed, key=lambda row:row['uid']),
        boundary_consumption_audit=audit)


def prepare_actual(folder, *, source_freeze, strict_stats, case_sha, provider_sha, blocker_output=None,
                   initial_site_authority=None, initial_state_freeze=None, planning_provider=None,
                   planning_known_receipts=None, arm='B0'):
    """Consume certified DD00 initial state; never replay the pre-day queue."""
    if initial_site_authority is not None:
        raise ValueError('SYNTHETIC_INITIALIZATION_SUPERSEDED_BY_DDAY_BOUNDARY_POLICY')
    from .dday_boundary import audit_dday_state, assert_full96_authority
    from .coordinator import verify_sources
    if initial_state_freeze is None:
        gate=audit_dday_state(folder)
        verify_sources(source_freeze,gate['source_receipts'])
        if blocker_output is not None:write(blocker_output,gate)
        raise DDayInitialStateAuthorityBlocked(gate)
    from .dday_initialization import load_dday_state
    from v42_voltage_control.b0_new import _truth
    from v42_final.workload import ForecastBook
    folder=Path(folder)
    freeze=load_dday_state(initial_state_freeze,arm=arm)
    assert_full96_authority(freeze)
    coverage=inspect_inputs(folder)
    names=('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json')
    plan,actual,provenance,power=[read(folder/name) for name in names]
    begin=pd.Timestamp(plan['day'],tz='Etc/GMT-10').timestamp()
    issue=pd.Timestamp(plan['issue_time']).timestamp()
    if (freeze['day']!=plan['day'] or freeze['begin_epoch_seconds']!=begin
            or freeze['end_epoch_seconds']!=begin+86400 or begin-issue!=21600
            or freeze['capacities']!=plan['capacities']):
        raise ValueError('DDAY_ACTUAL_SOURCE_DAY_AXIS_OR_CAPACITY_DRIFT')
    receipts=coverage['sources']+freeze['source_receipts']+[record(initial_state_freeze)]
    stats=load_stats(strict_stats) if isinstance(strict_stats,(str,Path)) else strict_stats
    if isinstance(strict_stats,(str,Path)):receipts.append(record(strict_stats))
    verify_sources(source_freeze,receipts)
    if (planning_provider is None or planning_known_receipts is None or
            planning_provider.case_sha!=case_sha or planning_provider.provider_sha!=provider_sha
            or planning_provider.stats.sha!=stats.sha):
        raise ValueError('FROZEN_PLANNING_QOS_PROVIDER_REQUIRED_FOR_DDAY_ACTUAL')
    before=planning_provider.export_ledger()
    truth,archive_receipt=_truth(plan['known_population']+actual['post_issue_arrivals'],provenance['archive'])
    built=_build_dday_actual_inputs(plan,actual,freeze,truth,planning_provider,planning_known_receipts)
    if planning_provider.export_ledger()!=before:
        raise ValueError('DDAY_PREPARATION_MUTATED_PLANNING_QOS_LEDGER')
    cc4=plan['forecast_inputs']['current_CC4']
    forecast=ForecastBook(tuple(cc4['Q50_GPUh']),tuple(cc4['Q90_GPUh']),begin)
    weather,weather_receipt=_weather(provenance,begin,begin+86400)
    if len(weather)!=96:raise ValueError('DDAY_ACTUAL_WEATHER_EXACT96_REQUIRED')
    power_model,power_receipts=_power_model(power,plan['capacities'])
    receipts += [archive_receipt,*power_receipts,weather_receipt['source'],weather_receipt['interpolation_source']]
    verify_sources(source_freeze,receipts)
    arguments={key:built[key] for key in ('requests','running','environment','reference')}
    arguments.update(capacities=plan['capacities'],qos_window_provider=planning_provider,
        begin=begin,end=begin+86400,forecast=forecast,power_model=power_model,weather=weather)
    gate={key:freeze[key] for key in ('status','full96_actual_authorized','initial_queue_verified',
        'active_running_site_authority','common_initial_state_sha','Arm_initial_state_SHA')}
    gate.update(day=plan['day'],day_begin_epoch_seconds=begin,end_epoch_seconds=begin+86400,
        initial_state_freeze=record(initial_state_freeze),source_issue_epoch_seconds=issue,
        preday_queue_replay_executed=False,initial_state_model_assumption=True,
        KESTREL_OBSERVED_SITE=False,Source18rNumericEqual=False)
    coverage.update(initial_state_freeze=record(initial_state_freeze),
        initial_state_model_assumption=True,boundary_consumption=built['boundary_consumption_audit'])
    return dict(arguments=arguments,qos_provider=planning_provider,known_receipts=planning_known_receipts,
        receipts=receipts,planning=plan,actual_descriptor=actual,actual_gate=gate,
        issue_epoch_seconds=issue,day_begin_epoch_seconds=begin,end_epoch_seconds=begin+86400,
        source_coverage=coverage,archive_receipt=archive_receipt,exact_private_source_join_count=len(truth),
        weather_receipt=weather_receipt,historical_source_ledger=built['historical_source_ledger'],
        boundary_consumption_audit=built['boundary_consumption_audit'],initial_state_freeze=freeze)


def _prepare_issue_actual_superseded(folder, *, source_freeze, strict_stats, case_sha, provider_sha, blocker_output=None,initial_site_authority=None):
    """Post-freeze simulator arguments and separate observed Known budgets.

    Only known_receipts may enter an A-stage adapter. The returned Environment
    owns future realization privately; Unknown UIDs never enter the shadow or
    QoS ledger until submission is observed by the Actual event engine.
    """
    from .coordinator import verify_sources
    from .actual import JobRequest
    from v42_capacity.actual import Environment
    from v42_capacity.reference import build_reference
    from v42_final.workload import ForecastBook
    from v42_voltage_control.b0_new import _truth
    folder = Path(folder)
    coverage = inspect_inputs(folder)
    native_path = folder/"NATIVE_INPUT_TEMPLATE_B1.json"
    native = read(native_path)
    coverage["sources"].append(record(native_path))
    verify_sources(source_freeze, coverage["sources"])
    plan, actual, provenance, power = [read(folder/name) for name in
        ("PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "POWER_AUTHORITY.json")]
    issue = pd.Timestamp(plan["issue_time"]).timestamp()
    day_begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    end = day_begin+86400
    if day_begin-issue != 21600:
        raise ValueError("REAL_CASE_EXPLICIT_24_SLOT_ISSUE_AXIS_REQUIRED")
    native_known = {row["job_uid"]: row for row in native["known_population"]}
    if set(native_known) != {row["job_uid"] for row in plan["known_population"]}:
        raise ValueError("SOURCE_NATIVE_OBSERVED_POPULATION_MISMATCH")
    missing = [row for row in native_known.values() if row["state"] == "RUNNING" and row["current_site_if_running"] is None]
    initialization=None
    if initial_site_authority is not None:
        from .initial_state import verified_initial_sites
        initialization=verified_initial_sites(initial_site_authority,native,plan)
        coverage['sources'].append(record(initial_site_authority))
        verify_sources(source_freeze,[coverage['sources'][-1]])
        native_known={uid:(dict(row,current_site_if_running=initialization['mapping'][uid])
            if row['state']=='RUNNING' else row) for uid,row in native_known.items()}
        coverage['initialization_policy']=dict(policy_id=initialization['policy_id'],
            initialization_sha=initialization['initialization_sha'],original_missing_sites=len(missing),
            INITIAL_SITE_SOURCE='SYNTHETIC_MODEL_ASSUMPTION',KESTREL_OBSERVED_SITE=False,
            SOURCE18R_NUMERICALLY_IDENTICAL=False,frozen_210_site_changes=0)
        missing=[]
    if missing:
        private_audit_path = Path(__file__).parents[1]/"docs/v42_common_am_qos_integration/PRIVATE_INITIAL_STATE_AUTHORITY_AUDIT.json"
        private_audit = read(private_audit_path) if private_audit_path.is_file() else None
        if private_audit is not None and (private_audit["day"] != plan["day"] or
                {r["uid"] for r in private_audit["missing_rows"]} != {r["job_uid"] for r in missing}):
            raise ValueError("PRIVATE_INITIAL_STATE_AUDIT_CASE_MISMATCH")
        if private_audit is not None:
            verify_sources(source_freeze, private_audit["source_receipts"])
        blocked = dict(day=plan["day"], status="NOT_ESTABLISHED_INPUT_AUTHORITY",
            reason="OBSERVED_RUNNING_SITE_AUTHORITY_MISSING_IN_CAUSAL_ISSUE_PREFIX",
            missing_running_site_jobs=len(missing), missing_running_site_GPU=sum(r["GPU_gang"] for r in missing),
            missing_site_uids=[r["job_uid"] for r in missing],
            assigned_native_running_sites_preserved=True,
            missing_site_Dday_overlap_jobs=None if private_audit is None else private_audit["missing_site_Dday_overlap_jobs"],
            missing_site_issue_prefix_overlap_jobs=None if private_audit is None else private_audit["missing_site_issue_prefix_overlap_jobs"],
            private_overlap_audit=None if private_audit is None else record(private_audit_path),
            retrospective_no_Dday_overlap_does_not_authorize_prefix_site_or_queue=True,
            raw_population_retained=len(plan["known_population"])+len(actual["post_issue_arrivals"]),
            jobs_dropped=0, invented_running_sites=0, synthetic_external_scope_contract=False,
            full96_queue_causality="NOT_ESTABLISHED", actual_engine_executed=False, Fresh_AC="NOT_EXECUTED",
            Gurobi_native_seconds=0, other_solver_wall_seconds=0, source_receipts=coverage["sources"], campaign_HOLD=True)
        if blocker_output is not None:
            write(blocker_output, blocked)
        raise InitialStateAuthorityBlocked(blocked)
    # Pin every already RUNNING site's frozen observed model location. The
    # clone preserves raw descriptors; new reference generation cannot relocate
    # history. PENDING remains on the same causal grid-blind reference rule.
    reference_population = [dict(row, source_site=native_known[row["job_uid"]]["current_site_if_running"],
        source_site_authority=(next(p['INITIAL_SITE_SOURCE'] for p in initialization['per_job'] if p['uid']==row['job_uid'])
            if initialization is not None else 'FROZEN_NATIVE_MODEL_RUNNING_LOCATION')) if row["state"] == "RUNNING" else dict(row)
        for row in plan["known_population"]]
    refs, audit = build_reference(reference_population, plan["capacities"], plan["rack_compatibility"],
                                  issue_time=plan["issue_time"])
    if not audit["full_reference_ready"]:
        raise ValueError("INITIAL_SOURCE_REFERENCE_NOT_READY")
    reference = {row["job_uid"]: row for row in refs}
    population = plan["known_population"]+actual["post_issue_arrivals"]
    # This is the reviewed original exact source-row extraction. Its output is
    # never passed to policy/provider/controller metadata.
    truth, archive_receipt = _truth(population, provenance["archive"])
    requests, running, durations, completions = [], [], {}, {}
    representation = tuple(float(t) for t in np.arange(issue, end+900, 900))
    unknown_uids = {row["job_uid"] for row in actual["post_issue_arrivals"]}
    for row in population:
        uid = row["job_uid"]
        submit = pd.Timestamp(row["submit_time"]).timestamp()
        metadata = dict(qos=row.get("qos", "UNCONFIRMED"), protected=row.get("protected"),
            batch_eligible=row.get("batch_eligible"), partition=row.get("partition", ""),
            requested_walltime_seconds=row.get("requested_walltime_seconds"), origin_unknown=uid in unknown_uids,
            representation_starts_seconds=representation, can_prestart_place=False,
            source_request_provenance=row["request_version_history"],
            source_representation="EXPLICIT_INDEPENDENT_DAILY_CASE_ISSUE_TO_DAYEND_CONTROL_AXIS",
            metadata_authority="UNSUPPORTED_ATTRIBUTES_REMAIN_UNCONFIRMED", state=row["state"])
        if row['state']=='RUNNING' and initialization is not None:
            initial=next(p for p in initialization['per_job'] if p['uid']==uid)
            metadata.update(episode_id=initial['episode_id'],initial_site_source=initial['INITIAL_SITE_SOURCE'],
                KESTREL_OBSERVED_SITE=False,initialization_sha=initialization['initialization_sha'])
        request = JobRequest(uid, submit, row["GPU_gang"], tuple(row["compatible_sites"]),
            row["Q50_total_seconds"], row.get("source_site"), metadata)
        durations[uid] = truth[uid]["realized_seconds"]
        if row["state"] == "RUNNING":
            observed_start = issue-row["elapsed_seconds"]
            source_start = pd.Timestamp(truth[uid]["start_time"]).timestamp()
            completion = pd.Timestamp(truth[uid]["end_time"]).timestamp()
            if observed_start != source_start or not source_start <= issue < completion:
                raise ValueError("INITIAL_RUNNING_OBSERVED_HISTORY_SOURCE_DRIFT")
            site = native_known[uid]["current_site_if_running"]
            if site != reference[uid]["reference_site"]:
                raise ValueError("OBSERVED_RUNNING_SITE_REWRITE")
            running.append((request, site, observed_start))
            completions[uid] = completion
        else:
            requests.append(request)
    stats = load_stats(strict_stats) if isinstance(strict_stats, (str, Path)) else strict_stats
    qos = QoSWindowProvider(stats, case_sha=case_sha, provider_sha=provider_sha)
    cc4 = plan["forecast_inputs"]["current_CC4"]
    forecast = ForecastBook(tuple(cc4["Q50_GPUh"]), tuple(cc4["Q90_GPUh"]), day_begin)
    weather, weather_receipt = _weather(provenance, issue, end)
    power_model, power_receipts = _power_model(power, plan["capacities"])
    from dataclasses import asdict, fields
    from .qos import CausalReferenceScheduler, ObservedJob
    from .policy import digest
    ref_sha = digest(dict(rule="CAUSAL_REFERENCE_START", issue=issue, capacities=plan["capacities"],
                         frozen_runtime_authority=plan["runtime_authority"], known=plan["known_population"],
                         initialization_sha=None if initialization is None else initialization['initialization_sha']))
    planning_shadow = CausalReferenceScheduler(plan["capacities"], reference_sha=ref_sha)
    known_requests = []
    for request, site, start in sorted(running, key=lambda row: (row[0].submit, row[0].uid)):
        planning_shadow.observe_running(request, site=site, start_seconds=start,
            event_seconds=issue, elapsed_compute_seconds=issue-start)
        known_requests.append(request)
    for request in sorted((r for r in requests if r.uid not in unknown_uids), key=lambda r: (r.submit, r.uid)):
        planning_shadow.submit(request, event_seconds=issue)
        known_requests.append(request)
    known_receipts = {}
    for request in known_requests:
        ref = planning_shadow.assigned[request.uid]
        request.metadata["reference_start_seconds"] = ref["reference_start_seconds"]
        attributes = {f.name: request.metadata[f.name] for f in fields(ObservedJob) if f.name in request.metadata}
        attributes.update(uid=request.uid, submit_seconds=request.submit, event_seconds=issue,
            reference_start_seconds=ref["reference_start_seconds"], t50_seconds=request.q50,
            gpu=request.gpu, is_observed=True, provider_sha=provider_sha, reference_sha=ref_sha)
        observed = ObservedJob(**attributes)
        receipt = qos.issue(observed)
        known_receipts[request.uid] = dict(observed=asdict(observed), reference=ref, receipt=receipt.to_dict(),
            native_reference=reference[request.uid], request=asdict(request))
    receipts = coverage["sources"]+[archive_receipt, *power_receipts, weather_receipt["source"]]
    if isinstance(strict_stats, (str, Path)):
        receipts.append(record(strict_stats))
    verify_sources(source_freeze, receipts)
    arguments = dict(capacities=plan["capacities"], requests=requests, environment=Environment(durations, completions),
        qos_window_provider=qos, running=running, begin=issue, end=end, forecast=forecast,
        reference=CausalReferenceScheduler(plan["capacities"], reference_sha=ref_sha),
        power_model=power_model, weather=weather)
    return dict(arguments=arguments, qos_provider=qos, known_receipts=known_receipts, receipts=receipts,
        planning=plan, actual_descriptor=actual, issue_epoch_seconds=issue, day_begin_epoch_seconds=day_begin,
        end_epoch_seconds=end, source_coverage=coverage, archive_receipt=archive_receipt,
        exact_private_source_join_count=len(truth), weather_receipt=weather_receipt)


def run_b0(folder, output, *, source_freeze, strict_stats, case_sha, provider_sha,initial_site_authority=None,
           initial_state_freeze=None,planning_provider=None,planning_known_receipts=None):
    """Representative real full96 through the common new Actual engine."""
    from .coordinator import verify_sources
    from .actual import run_actual
    started = time.perf_counter()
    output = Path(output)
    if output.exists():
        raise ValueError("INTEGRATION_ACTUAL_ATTEMPT_ALREADY_EXISTS")
    try:
        prepared = prepare_actual(folder, source_freeze=source_freeze, strict_stats=strict_stats,
            case_sha=case_sha, provider_sha=provider_sha, blocker_output=output/"REAL_ACTUAL_BLOCKED.json",
            initial_site_authority=initial_site_authority,initial_state_freeze=initial_state_freeze,
            planning_provider=planning_provider,planning_known_receipts=planning_known_receipts,arm='B0')
    except InitialStateAuthorityBlocked:
        # The failure is an input authority receipt, not dropped jobs,
        # solver infeasibility, TIME_LIMIT or a fabricated subset validation.
        raise
    plan = prepared["planning"]
    coverage = prepared["source_coverage"]
    issue, day_begin, end = (prepared[key] for key in ("issue_epoch_seconds", "day_begin_epoch_seconds", "end_epoch_seconds"))
    receipts, archive_receipt, weather_receipt = (prepared[key] for key in ("receipts", "archive_receipt", "weather_receipt"))
    result = run_actual(arm="B0", **prepared["arguments"])
    output.mkdir(parents=True)
    simulated_begin=prepared['arguments']['begin']
    first = int((day_begin-simulated_begin)/900)
    arrays = dict(sites=np.array(result["sites"]), timestamps_start_epoch_seconds=np.arange(day_begin, end, 900),
        GPU=result["occupancy_GPU"][first:], compute_GPU=result["compute_occupancy_GPU"][first:],
        **{key: result["physical"][key][first:] for key in ("IT_kw", "PCC_P_kw", "PCC_Q_kvar")})
    if arrays["GPU"].shape != (96, 12):
        raise ValueError("REAL_ACTUAL_FULL96_SLICE_AXIS_DRIFT")
    np.savez_compressed(output/"ACTUAL_OCCUPANCY_POWER_TRACE.npz", **arrays)
    for filename, key in (("JOB_EVENT_LEDGER.json", "job_event_ledger"), ("RESERVATION_LEDGER.json", "reservation_ledger"),
        ("CC4_DEPLETION_LEDGER.json", "cc4_depletion_ledger"), ("MIGRATION_RECEIPTS.json", "migration_receipts"),
        ("QOS_ACTUAL_RECEIPTS.json", "qos_ledger"), ("QOS_BUDGET_LEDGER.json", "qos_budget_ledger"),
        ("ACTUAL_QUEUE_LEDGER.json", "queue_ledger"), ("CARRYOUT_RECEIPT.json", "carryout")):
        write(output/filename, result[key])
    write(output/"PRIVATE_REALIZED_SOURCE_RECEIPT.json", dict(archive=archive_receipt,
        exact_source_join_count=prepared["exact_private_source_join_count"], private_environment_only=True,
        realized_duration_used_for_qos_or_reference=False, source_extractor=record(Path(__file__).parents[1]/"v42_voltage_control/b0_new.py")))
    write(output/'PREDAY_HISTORICAL_SOURCE_LEDGER.json',prepared['historical_source_ledger'])
    write(output/'DDAY_INITIAL_STATE_CONSUMPTION_RECEIPT.json',prepared['boundary_consumption_audit'])
    verify_sources(source_freeze, receipts)
    receipt = dict(day=plan["day"], arm="B0", engine=result["engine"], status="EXECUTED_JOB_EVENT_POWER_FULL96",
        real_data=True, source_coverage=coverage, source_freeze=source_freeze, sources=receipts,
        time_axis=dict(simulated_begin_epoch_seconds=simulated_begin, source_issue_epoch_seconds=issue,
            day_begin_epoch_seconds=day_begin, end_epoch_seconds=end,
            source_issue_to_dayend_replay=False, simulated_slots=96, reported_day_slots=96, slice="[0,96)",
            source_timezone="FIXED_AEST_UTC+10", reporting_UTC_explicit=True),
        physical_trace=record(output/"ACTUAL_OCCUPANCY_POWER_TRACE.npz"), weather=weather_receipt,
        raw_job_sites_missing=True, initial_site_model_assumption="V42_DDAY_COMMON_GRID_BLIND_INITIAL_SITE_V1",
        common_initial_state_sha=prepared['actual_gate']['common_initial_state_sha'],
        KESTREL_OBSERVED_SITE=False,KESTREL_OBSERVED_QUEUE=False,Source18rNumericEqual=False,
        intentional_actions=0, qos_delay_authority_supported_jobs=sum(r["budget_seconds"] > 0 for r in result["qos_budget_ledger"].values()),
        qos_window_empty_jobs=sum(r["status"] == "EMPTY_AUTHORIZED_WINDOW" for r in result["qos_budget_ledger"].values()),
        receipt=result["receipt"], simulated_96slot_compute_GPUh=result["receipt"]["actual_compute_GPUh"],
        actual_full96_compute_GPUh=float(arrays["compute_GPU"].sum()/4),
        actual_full96_occupation_GPUh=float(arrays["GPU"].sum()/4),
        actual_full96_IT_kWh=float(arrays["IT_kw"].sum()/4), actual_full96_PCC_kWh=float(arrays["PCC_P_kw"].sum()/4),
        execution_completion="EXECUTED", FULL_optimization="NOT_APPLICABLE_B0", gap="NOT_CERTIFIED",
        QoS_PASS=not any(r["latest_start_excess_seconds"] > 0 for r in result["qos_ledger"]),
        Actual_physical_PASS=None, Fresh_AC="NOT_EXECUTED", wall_seconds=time.perf_counter()-started,
        Gurobi_native_seconds=0, other_solver_wall_seconds=0, campaign_HOLD_preserved=True)
    write(output/"REAL_ACTUAL_RESULT.json", receipt)
    return receipt


def run_real_job_component(folder, output, *, source_freeze, strict_stats, case_sha, provider_sha, uid=None):
    """One real source-backed Job in an explicitly isolated component fixture.

    This does not establish original May01 queue/population causality. The full
    raw population is retained and its initial-site blocker remains unchanged.
    """
    from .coordinator import verify_sources
    from .actual import JobRequest, run_actual
    from v42_capacity.actual import Environment
    from v42_voltage_control.b0_new import _truth
    folder, output = Path(folder), Path(output)
    if output.exists():
        raise ValueError("REAL_JOB_COMPONENT_ATTEMPT_ALREADY_EXISTS")
    started = time.perf_counter()
    names = ("PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "SOURCE_PROVENANCE.json", "POWER_AUTHORITY.json", "NATIVE_INPUT_TEMPLATE_B1.json")
    plan, actual, provenance, power, native = [read(folder/name) for name in names]
    receipts = [record(folder/name) for name in names]
    verify_sources(source_freeze, receipts)
    known = {r["job_uid"]: r for r in plan["known_population"]}
    eligible = {r["job_uid"]: r for r in native["known_population"]
                if r["state"] == "RUNNING" and r["current_site_if_running"] is not None}
    uid = sorted(eligible)[0] if uid is None else uid
    if uid not in eligible or uid not in known:
        raise ValueError("COMPONENT_JOB_REQUIRES_SOURCE_OBSERVED_RUNNING_SITE")
    row, initial = known[uid], eligible[uid]
    site = initial["current_site_if_running"]
    issue = pd.Timestamp(plan["issue_time"]).timestamp()
    day_begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    end = day_begin+86400
    observed_start = issue-row["elapsed_seconds"]
    truth, archive_receipt = _truth([row], provenance["archive"])
    source_start = pd.Timestamp(truth[uid]["start_time"]).timestamp()
    source_completion = pd.Timestamp(truth[uid]["end_time"]).timestamp()
    if abs(source_start-observed_start) > 1e-6 or not source_start <= issue < source_completion:
        raise ValueError("COMPONENT_OBSERVED_RUNNING_HISTORY_DRIFT")
    metadata = dict(qos="UNCONFIRMED", protected=None, batch_eligible=None, partition="",
        requested_walltime_seconds=None, origin_unknown=False, state="RUNNING", can_prestart_place=False,
        representation_starts_seconds=tuple(np.arange(issue, end+900, 900)),
        source_request_provenance=row["request_version_history"],
        source_initial_site_authority="FROZEN_NATIVE_OBSERVED_RUNNING_LOCATION",
        evidence_kind="REAL_JOB_COMPONENT_FIXTURE")
    request = JobRequest(uid, pd.Timestamp(row["submit_time"]).timestamp(), row["GPU_gang"],
        tuple(row["compatible_sites"]), row["Q50_total_seconds"], site, metadata)
    stats = load_stats(strict_stats)
    qos = QoSWindowProvider(stats, case_sha=case_sha, provider_sha=provider_sha)
    weather, weather_receipt = _weather(provenance, issue, end)
    power_model, power_receipts = _power_model(power, plan["capacities"])
    result = run_actual(plan["capacities"], [], Environment({uid: truth[uid]["realized_seconds"]}, {uid: source_completion}),
        arm="B0", qos_window_provider=qos, running=[(request, site, observed_start)],
        begin=issue, end=end, power_model=power_model, weather=weather)
    output.mkdir(parents=True)
    first = int((day_begin-issue)/900)
    arrays = dict(sites=np.array(result["sites"]), timestamps_start_epoch_seconds=np.arange(day_begin, end, 900),
        GPU=result["occupancy_GPU"][first:], compute_GPU=result["compute_occupancy_GPU"][first:],
        **{key: result["physical"][key][first:] for key in ("IT_kw", "PCC_P_kw", "PCC_Q_kvar")})
    if arrays["GPU"].shape != (96, 12):
        raise ValueError("COMPONENT_DAY_AXIS_DRIFT")
    np.savez_compressed(output/"ACTUAL_OCCUPANCY_POWER_TRACE.npz", **arrays)
    for filename, key in (("JOB_EVENT_LEDGER.json", "job_event_ledger"), ("RESERVATION_LEDGER.json", "reservation_ledger"),
        ("QOS_BUDGET_LEDGER.json", "qos_budget_ledger"), ("QOS_ACTUAL_RECEIPTS.json", "qos_ledger"),
        ("CARRYOUT_RECEIPT.json", "carryout")):
        write(output/filename, result[key])
    receipts += [archive_receipt, weather_receipt["source"], *power_receipts, record(strict_stats)]
    verify_sources(source_freeze, receipts)
    receipt = dict(day=plan["day"], arm="B0", evidence_kind="REAL_JOB_COMPONENT_FIXTURE",
        logical_scope="REAL_JOB_COMPONENT_FIXTURE", status="EXECUTED_REAL_JOB_COMPONENT_FIXTURE",
        original_full_case_certified=False, original_May01_full96_queue_causality="NOT_ESTABLISHED",
        original_raw_population_retained=len(known)+len(actual["post_issue_arrivals"]),
        selected_fixture_uid=uid, selection_rule="FIRST_UID_WITH_OBSERVED_NATIVE_RUNNING_SITE",
        selected_job_source=dict(source_member=row["source_member"], source_row=row["source_row"], archive=archive_receipt),
        selected_observed_initial_site=site, component_jobs=1, fixture_other_job_interactions_removed_explicitly=True,
        source_freeze=source_freeze, sources=receipts, weather=weather_receipt,
        physical_trace=record(output/"ACTUAL_OCCUPANCY_POWER_TRACE.npz"),
        source_realized_seconds_private=truth[uid]["realized_seconds"],
        controller_realized_seconds_reads=0, controller_future_completion_reads=0,
        capacities=plan["capacities"], frozen_C1_power_recomputed=True, planning_PQ_copied=False,
        real_action_observation_claimed=False, fixture_unknown_migration_observation_claimed=False,
        receipt=result["receipt"], Fresh_AC="NOT_EXECUTED", Actual_physical_PASS=None,
        wall_seconds=time.perf_counter()-started, Gurobi_native_seconds=0, other_solver_wall_seconds=0,
        campaign_HOLD_preserved=True)
    write(output/"REAL_ACTUAL_RESULT.json", receipt)
    return receipt


@contextmanager
def _validated_hardware_context(source_freeze, manifest):
    """New integration-only read context for unchanged thermal/hardware assets.

    This is not a campaign permit or old model/source certification. Every
    referenced asset and current integration source is checked on entry/exit.
    The original measurement API reads this context to select the approved
    COMPILED_NORMALAMPS_ONLY contract, including unchanged extra-SVR guards.
    """
    from .coordinator import verify_sources
    from v42_svr11.authority import integration_physical_scope
    from v42_voltage_control.integration import validate_scenario
    receipts = [manifest[key] for key in ("hardware", "scenario", "thermal")]
    verify_sources(source_freeze, receipts)
    hardware, scenario, thermal = [read(checked(receipt)) for receipt in receipts]
    validate_scenario(scenario)
    if (not hardware.get("PASS") or hardware.get("SVR_count") != 11 or not thermal.get("PASS")
            or hardware["scenario_SHA"] != scenario["scenario_SHA"]
            or hardware["scenario"]["sha256"] != manifest["scenario"]["sha256"]
            or manifest["original_transformer_current_authority"] != "COMPILED_NORMALAMPS_ONLY"
            or len(scenario["svr"]["units"]) != 11 or scenario["capcontrol"] is not None):
        raise ValueError("INTEGRATION_ORIGINAL_11SVR_HARDWARE_OR_THERMAL_CONTRACT_DRIFT")
    with integration_physical_scope(source_freeze, hardware=manifest["hardware"],
                                   scenario=manifest["scenario"], thermal_receipt=manifest["thermal"]):
        yield scenario
    verify_sources(source_freeze, receipts)


def mess_service_bindings(source, model_sites):
    """Resolve canonical M sites using frozen alias code and electrical assets."""
    import inspect
    import re
    from dayahead.v38.authority import V38WanAuthority
    mapping_path, pcc_path = source["assets"].service_mapping, source["assets"].pcc
    table = pd.read_csv(mapping_path)
    service_ids = set(table.service_node_id.astype(str).str.upper())
    text = pcc_path.read_text(encoding="utf-8")
    generators = {service.upper(): name for name, service in re.findall(
        r"^\s*New\s+Generator\.(MESS_DIS_(\S+))\s+", text, re.IGNORECASE|re.MULTILINE)}
    loads = {service.upper(): name for name, service in re.findall(
        r"^\s*New\s+Load\.(MESS_CHG_(\S+))\s+", text, re.IGNORECASE|re.MULTILINE)}
    bindings = {}
    for site in model_sites:
        service = V38WanAuthority.historical_idc(str(site)).upper()
        if service not in service_ids or service not in generators or service not in loads:
            raise ValueError("FROZEN_MODEL_MESS_ELECTRICAL_SERVICE_MAPPING_MISSING:"+str(site))
        bindings[site] = dict(service_id=service, generator=generators[service], load=loads[service])
    if len({row["service_id"] for row in bindings.values()}) != len(bindings):
        raise ValueError("MODEL_MESS_SERVICE_ALIAS_COLLISION")
    return bindings, [record(mapping_path), record(pcc_path), record(inspect.getfile(V38WanAuthority))]


def fresh_ac_minimum(folder, actual_output, output, *, source_freeze, campaign_manifest, slots=1,
                     mess_plan=None, mess_execution_receipt=None, trace_path=None, arm="B0",case_scope=None):
    """Fresh original 11-SVR AC with exactly frozen AIDC and MESS injections."""
    from .coordinator import verify_sources
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_voltage_control.integration import _equipment, measure_full_network, assert_control_inventory
    from v42_voltage_control.timecontrol import CommonClock
    from v42_voltage_control.svr import install
    from v42_holdout.realization import archive_rows
    if arm not in {"B0", "B1", "B2", "B3"} or type(slots) is not int or not 1 <= slots <= 96:
        raise ValueError("EXPLICIT_LIMITED_FRESH_AC_SLOT_COUNT_REQUIRED")
    started = time.perf_counter()
    folder, actual_output, output = Path(folder), Path(actual_output), Path(output)
    if output.exists():
        raise ValueError("INTEGRATION_FRESH_AC_ATTEMPT_ALREADY_EXISTS")
    if trace_path is None:
        result = read(actual_output/"REAL_ACTUAL_RESULT.json")
        if result["status"] not in {"EXECUTED_JOB_EVENT_POWER_FULL96", "EXECUTED_REAL_JOB_COMPONENT_FIXTURE"}:
            raise ValueError("RECOMPUTED_REAL_ACTUAL_REQUIRED_BEFORE_AC")
    else:
        # Coordinator consumers supply the explicit full96 slice of their
        # recomputed common Actual trace. Its SHA/epoch axis are checked below.
        result = dict(physical_trace=record(trace_path), sources=inspect_inputs(folder)["sources"])
    verify_sources(source_freeze, result["sources"]+[result["physical_trace"], record(campaign_manifest)])
    plan, actual = read(folder/"PLANNING_INPUT_BUNDLE.json"), read(folder/"ACTUAL_INPUT_BUNDLE.json")
    provenance = read(folder/"SOURCE_PROVENANCE.json")
    manifest = read(campaign_manifest)
    begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10")
    end = begin+pd.Timedelta(days=1)
    exogenous = {}
    exo_receipts = []
    for kind, time_key, column in (("demand", "SETTLEMENTDATE", "TOTALDEMAND"), ("pv", "INTERVAL_DATETIME", "POWER")):
        path = checked(actual["realized_inputs"]["authority"][kind])
        exo_receipts.append(record(path))
        records = [r for r in archive_rows(path) if r.get("REGIONID") == "VIC1" and time_key in r
                   and (kind != "pv" or r.get("TYPE") == "MEASUREMENT")]
        frame = pd.DataFrame(records)
        dates = pd.to_datetime(frame[time_key], format="%Y/%m/%d %H:%M:%S").dt.tz_localize("Etc/GMT-10")
        values = pd.Series(pd.to_numeric(frame[column]).to_numpy(), index=pd.DatetimeIndex(dates))
        values = values[(values.index > begin)&(values.index <= end)]
        if values.index.duplicated().any():
            raise ValueError("FRESH_AC_REALIZED_EXOGENOUS_DUPLICATE")
        axis = pd.date_range(begin+pd.Timedelta(minutes=15 if kind == "demand" else 30), end,
                             freq="15min" if kind == "demand" else "30min")
        data = values.reindex(axis).to_numpy(float)
        exogenous[kind] = data if kind == "demand" else np.repeat(data, 2)
        if exogenous[kind].shape != (96,) or not np.isfinite(exogenous[kind]).all():
            raise ValueError("FRESH_AC_REALIZED_EXOGENOUS_COVERAGE_MISSING")
    stamps = [stamp.isoformat() for stamp in pd.date_range(begin+pd.Timedelta(minutes=15), end, freq="15min")]
    if not pd.DatetimeIndex(stamps).tz_convert("UTC").equals(pd.DatetimeIndex(plan["forecast_inputs"]["AEMO"]["timestamps_96"]).tz_convert("UTC")):
        raise ValueError("FRESH_AC_ORIGINAL_EXOGENOUS_TIME_AXIS_DRIFT")
    with np.load(result["physical_trace"]["path"], allow_pickle=False) as packet:
        if tuple(map(str,packet['sites']))!=tuple(f'AIDC{j:02d}' for j in range(1,13)):
            raise ValueError('FRESH_AC_ACTUAL_SITE_AXIS_DRIFT')
        p, q = packet["PCC_P_kw"].copy(), packet["PCC_Q_kvar"].copy()
        partial_trace = (case_scope or {}).get('partial_actual_trace_authorized') is True
        trace_slots = slots if partial_trace else 96
        if partial_trace and slots == 96:
            raise ValueError('PARTIAL_FRESH_AC_SCOPE_REQUIRES_STRICT_PREFIX')
        if "timestamps_start_epoch_seconds" not in packet or not np.array_equal(
                packet["timestamps_start_epoch_seconds"], begin.timestamp()+np.arange(trace_slots)*900):
            raise ValueError("FRESH_AC_ACTUAL_EXPLICIT_TIME_AXIS_REQUIRED")
    if p.shape != (trace_slots, 12) or q.shape != (trace_slots, 12):
        raise ValueError("FRESH_AC_ACTUAL_FULL96_PQ_AXIS")
    if not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError('FRESH_AC_FINITE_ACTUAL_PQ_REQUIRED')
    if arm in {"B0", "B1"} and mess_plan is not None:
        if (mess_plan.get('MESS_control')!='OFF' or any(abs(float(v))>0
                for field in ('P_by_site','Q_by_site') for row in mess_plan[field].values() for v in row)):
            raise ValueError("MESS_OFF_ARM_MUST_HAVE_NO_ACTIVE_MESS_PLAN")
    mess_p = mess_q = None
    if mess_plan is not None:
        from .policy import digest
        if digest({k: v for k, v in mess_plan.items() if k != "plan_sha"}) != mess_plan["plan_sha"]:
            raise ValueError("ACTUAL_FROZEN_MESS_PLAN_SHA_DRIFT")
        if (mess_execution_receipt is None or mess_execution_receipt.get("plan_sha") != mess_plan["plan_sha"]
                or mess_execution_receipt.get("frozen_execution_validated") is not True):
            raise ValueError("FROZEN_MESS_ROUTE_MODE_SOC_EXECUTION_RECEIPT_REQUIRED")
        mess_p, mess_q = mess_plan["P_by_site"], mess_plan["Q_by_site"]
        if (set(mess_p) != set(mess_q) or any(len(values) != 96 for values in list(mess_p.values())+list(mess_q.values()))
                or mess_plan.get("dt_seconds", 900) != 900 or mess_plan.get("time_axis", list(range(96))) != list(range(96))):
            raise ValueError("FROZEN_MESS_EXPLICIT_FULL96_AXIS_REQUIRED")
    elif arm in {"B2", "B3"}:
        raise ValueError("MESS_CONTROLLED_ARM_REQUIRES_FROZEN_MESS_EXECUTION")
    rows = []
    aliases, alias_sources = {}, []
    with _validated_hardware_context(source_freeze, manifest) as scenario:
        source = authority.source()
        if mess_plan is not None:
            aliases, alias_sources = mess_service_bindings(source, mess_p)
            verify_sources(source_freeze, alias_sources)
        bg = background(stamps, exogenous["demand"].tolist(), exogenous["pv"].tolist())
        engine, adapter, original_inventory = authority.compile_verified()
        try:
            nodes = {n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit(".", 1)[-1] in {"1", "2", "3"}}
            equipment = _equipment(engine)
            native = source["NativeAllocation"].from_adapter(adapter)
            native.validate_native_engine(engine)
            clock = CommonClock("ACTUAL", plan["day"])
            clock.bind(engine)
            svrs = install(engine, scenario["svr"])
            assert_control_inventory(source["inventory"](engine), scenario, initial=True)
            from dayahead.v28r2.opendss_mapping import _set_generator, _set_load, mess_injection_mapping
            for slot in range(slots):
                totals, _, allocation = native.apply(engine, bg, slot)
                for row in adapter["pv_generators"]:
                    key = (str(row["bus"]).lower(), "ABC"[int(row["phase"])-1])
                    _set_generator(engine, row["generator_name"], bg.pv_generation_kw_96[slot].get(key, 0), 0)
                for j in range(12):
                    _set_load(engine, f"IDC_IDC{j+1:02d}", p[slot, j], q[slot, j])
                for name in engine.Generators.AllNames():
                    if name.lower().startswith("mess_dis_"):
                        _set_generator(engine, name, 0, 0)
                for name in engine.Loads.AllNames():
                    if name.lower().startswith("mess_chg_"):
                        _set_load(engine, name, 0, 0)
                mess_applied = []
                if mess_plan is not None:
                    for site in sorted(mess_p):
                        injection = mess_injection_mapping(mess_p[site][slot], mess_q[site][slot])
                        names = aliases[site]
                        _set_generator(engine, names["generator"], injection["generator_p_kw"], injection["generator_q_kvar"])
                        _set_load(engine, names["load"], injection["charging_load_p_kw"], injection["charging_load_q_kvar"])
                        engine.Generators.Name(names["generator"])
                        gp, gq = float(engine.Generators.kW()), float(engine.Generators.kvar())
                        engine.Loads.Name(names["load"])
                        lp, lq = float(engine.Loads.kW()), float(engine.Loads.kvar())
                        if not np.allclose((gp-lp, gq-lq), (mess_p[site][slot], mess_q[site][slot]), rtol=0, atol=1e-9):
                            raise ValueError("ACTUAL_APPLIED_FROZEN_MESS_PQ_DRIFT")
                        mess_applied.append(dict(site=site, P_kW=gp-lp, Q_kvar=gq-lq, generator_P_kW=gp,
                            generator_Q_kvar=gq, charge_load_P_kW=lp, charge_load_Q_kvar=lq,
                            electrical_service=names["service_id"], generator_name=names["generator"], charge_load_name=names["load"]))
                clock_receipt = clock.settle_slot(engine, slot)
                assert_control_inventory(source["inventory"](engine), scenario)
                physical = measure_full_network(engine, nodes, equipment)
                hardware = svrs.measure()
                applied = []
                for j in range(12):
                    engine.Loads.Name(f"IDC_IDC{j+1:02d}")
                    applied.append((float(engine.Loads.kW()), float(engine.Loads.kvar())))
                if not np.array_equal(np.asarray(applied), np.column_stack((p[slot], q[slot]))):
                    raise ValueError("FRESH_AC_ACTUAL_APPLIED_PQ_DRIFT")
                rows.append(dict(slot=slot, PCC_P_kw=p[slot].tolist(), PCC_Q_kvar=q[slot].tolist(),
                    MESS_plan_sha=None if mess_plan is None else mess_plan["plan_sha"], MESS_applied=mess_applied,
                    clock=clock_receipt, physical=physical, SVR=hardware, native_load_PQ=totals,
                    allocation=allocation, PASS=bool(physical["PASS"] and hardware["hardware_PASS"] and hardware["added_nodes_voltage_PASS"])))
        finally:
            engine.Basic.ClearAll()
    output.mkdir(parents=True)
    write(output/"FRESH_PHYSICAL_SLOTS.json", rows)
    receipt = dict(day=plan["day"], arm=arm, status="PASS" if all(r["PASS"] for r in rows) else "PHYSICAL_FAIL",
        PASS=all(r["PASS"] for r in rows), executed_actual_slots=slots,
        full96_Actual_AC_established=slots == 96 and result.get("evidence_kind") != "REAL_JOB_COMPONENT_FIXTURE",
        logical_scope=("REAL_JOB_COMPONENT_FIXTURE" if result.get("evidence_kind") == "REAL_JOB_COMPONENT_FIXTURE"
                       else "MINIMUM_REPRESENTATIVE_REAL_ACTUAL" if slots < 96 else "FULL96_REAL_ACTUAL"),
        evidence_kind=result.get("evidence_kind", "REAL_DATA"),
        original_full_case_certified=False,
        partial_actual_trace_authorized=partial_trace,
        supplied_actual_trace_slots=trace_slots,
        case_scope=case_scope,science_version=source_freeze['science_version'],
        SOURCE18R_NUMERICALLY_IDENTICAL=False,
        common_initial_state_sha=(case_scope or {}).get('common_initial_state_sha'),
        evaluation_case_sha=(case_scope or {}).get('evaluation_case_sha'),
        KESTREL_OBSERVED_SITE=False,
        actual_power_trace=result["physical_trace"], hardware_sources=[manifest[k] for k in ("hardware", "scenario", "thermal")],
        MESS_plan_sha=None if mess_plan is None else mess_plan["plan_sha"], MESS_execution_receipt=mess_execution_receipt,
        frozen_MESS_PQ_consumed=mess_plan is not None, MESS_OFF=mess_plan is None or mess_plan.get('MESS_control')=='OFF',
        MESS_source_derived_service_bindings=aliases, MESS_mapping_sources=alias_sources,
        exogenous_sources=exo_receipts, source_freeze=source_freeze, original_initial_inventory=original_inventory,
        initial_Planning_control_state_reads=0, global_reoptimization=0, MESS_PQ_repair=0,
        original_compiler_clock_SVR_and_measurement_reused=True, original_Fresh96_body_executed=False,
        voltage_violation_cells=sum(r["physical"]["voltage_violation_cells"] for r in rows),
        line_current_violation_cells=sum(r["physical"]["line_current_violation_cells"] for r in rows),
        transformer_current_violation_cells=sum(r["physical"]["transformer_current_violation_cells"] for r in rows),
        transformer_kVA_violation_cells=sum(r["physical"]["transformer_kva_violation_cells"] for r in rows),
        physical_SolveSnap_count=sum(r["clock"]["physical_solve_count"] for r in rows),
        solver_native_seconds=0, AC_wall_seconds=time.perf_counter()-started, campaign_HOLD_preserved=True)
    write(output/"FRESH_PHYSICAL_RESULT.json", receipt)
    verify_sources(source_freeze, result["sources"]+exo_receipts+alias_sources)
    return receipt
