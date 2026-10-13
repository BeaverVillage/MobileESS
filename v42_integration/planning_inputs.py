"""Issue-only Planning receipts from the preserved frozen Native reference.

This adapter does not regenerate R0, reconstruct a pre-day queue, open Actual
truth, or assign missing sites. The 44 unresolved RUNNING records remain in
the Known ledger; their original nominal/requested reference ends before slot
24, so they contribute no source-predicted D-day Planning occupancy.
"""
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .a_engine import digest
from .m_engine import file_record
from .qos import ObservedJob, QoSWindowProvider


REFERENCE_LABEL = 'FROZEN_CAUSAL_REFERENCE_AT_ISSUE'


def _epoch(value):
    return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()


def prepare_planning(folder, data, *, source_freeze, strict_stats, case_sha, provider_sha):
    """Return all1649 issued Known receipts; no Actual initializer arguments."""
    from .coordinator import verify_sources
    from .production_case import read
    from .actual_validation import load_stats
    folder=Path(folder)
    native_path=folder/'NATIVE_INPUT_TEMPLATE_B1.json'
    native=read(native_path)
    bundle,jobs,bounds,resources,*_=data
    sources=[file_record(native_path)]
    if isinstance(strict_stats,(str,Path)):
        sources.append(file_record(strict_stats))
        stats=load_stats(strict_stats)
    else:
        stats=strict_stats
    verify_sources(source_freeze,sources)
    issue=_epoch(native['issue_time'])
    midnight=_epoch(native['day']+'T00:00:00+10:00')
    if midnight-issue!=24*900 or bundle['day']!=native['day']:
        raise ValueError('ISSUE_NATIVE_24_SLOT_DDAY_AXIS_REQUIRED')
    rows={r['job_uid']:r for r in native['known_population']}
    if len(rows)!=1649 or len(rows)!=len(native['known_population']):
        raise ValueError('FROZEN_ISSUE_KNOWN_1649_UID_ROSTER_REQUIRED')
    if set(rows)!={r['job_uid'] for r in bundle['known_population']}:
        raise ValueError('SAVED_NATIVE_KNOWN_UID_ROSTER_DRIFT')
    if set(jobs)!={uid for uid,r in rows.items() if r['planning_eligible'] and r['service_slots']>0}:
        raise ValueError('EXPLICIT_MODELED_JOB_ROSTER_DRIFT')
    frozen_reference=native['reference']
    if frozen_reference['sha256']!=bundle['reference']['sha256']:
        raise ValueError('PRESERVED_FROZEN_CAUSAL_REFERENCE_SHA_DRIFT')
    original_reference_record=file_record(frozen_reference['path'])
    if any(original_reference_record[k]!=frozen_reference[k] for k in ('sha256','bytes')):
        raise ValueError('ORIGINAL_FROZEN_REFERENCE_BYTES_DRIFT')
    sources.append(original_reference_record)
    reference_sha=digest(dict(label=REFERENCE_LABEL,reference_source=frozen_reference,
        issue=issue,source_known_reference=[dict(uid=uid,state=r['state'],
            source_start=r['reference_start_if_authorized'],planning_site=r['planning_site'],
            current_site_if_running=r['current_site_if_running'],
            nominal_service_seconds=r['nominal_remaining_seconds'],GPU_gang=r['GPU_gang'])
            for uid,r in sorted(rows.items())]))
    qos=QoSWindowProvider(stats,case_sha=case_sha,provider_sha=provider_sha)
    receipts={}
    external=[]
    for uid,row in sorted(rows.items()):
        state=row['state']
        if not row['known_at_issue'] or _epoch(row['submit_time'])>issue or state not in ('RUNNING','PENDING'):
            raise ValueError('FROZEN_CURRENT_OBSERVATION_REQUIRED:'+uid)
        site=row['current_site_if_running'] if state=='RUNNING' else row['planning_site']
        start_seconds=(issue-float(row['elapsed_seconds']) if state=='RUNNING'
                       else issue+int(row['reference_start_if_authorized'])*900)
        if state=='RUNNING' and site is None:
            requested_end=row['unresolved_external_source_service_end']
            if (row['planning_eligible'] or row['service_slots']!=0 or row['reference_end']>24
                    or requested_end>24 or row['nominal_remaining_seconds']!=0):
                raise ValueError('UNRESOLVED_RUNNING_SOURCE_NOMINAL_DDAY_SERVICE_NOT_ZERO:'+uid)
            external.append(dict(uid=uid,GPU_gang=row['GPU_gang'],source_site=None,
                source_requested_reference_end_issue_slot=requested_end,
                source_Q50_reference_end_issue_slot=row['reference_end'],
                source_remaining_requested_seconds=row['remaining_service_seconds'],
                Dday_nominal_service_GPUh=0.,predicted_at_issue_only=True,
                actual_completion_reads=0,classification='SOURCE_PREDICTED_PRE_DDAY_EXTERNAL_SERVICE'))
        elif site not in native['capacities']:
            raise ValueError('FROZEN_KNOWN_REFERENCE_SITE_REQUIRED:'+uid)
        if uid in jobs:
            job=jobs[uid]
            if (job.state!=state or job.gpu!=row['GPU_gang'] or job.service_slots!=row['service_slots']
                or job.reference_start!=row['reference_start_if_authorized']
                or job.reference_site!=site):
                raise ValueError('ORIGINAL_DATA_FROZEN_JOB_REFERENCE_OR_SERVICE_DRIFT:'+uid)
        # A finite native representation is not a new deadline. Source metadata
        # lacks confirmed request-version/batch/protection authority, so the
        # real issuer retains B0 while still recording every observed UID.
        reference_slot=int(row['reference_start_if_authorized'])
        end_slot=max(int(resources.control_end),reference_slot)
        representation=tuple(issue+t*900 for t in range(end_slot+1))
        observed=ObservedJob(uid=uid,submit_seconds=_epoch(row['submit_time']),event_seconds=issue,
            reference_start_seconds=start_seconds,t50_seconds=float(row['V10_Q50_total_seconds']),
            gpu=int(row['GPU_gang']),qos='UNCONFIRMED',protected=None,batch_eligible=None,
            requested_walltime_seconds=None,partition='',origin_unknown=False,is_observed=True,
            state=state,representation_starts_seconds=representation,
            nominal_service_seconds=float(row['nominal_remaining_seconds']),
            provider_sha=provider_sha,reference_sha=reference_sha)
        receipt=qos.issue(observed)
        reference=dict(uid=uid,reference_start_seconds=start_seconds,reference_site=site,
            origin=REFERENCE_LABEL,reference_sha=reference_sha,
            source_reference_sha=frozen_reference['sha256'],nominal_release_is_physical_completion=False,
            grid_reads=0,realized_completion_reads=0,solver_calls=0,queue_regeneration_calls=0)
        receipts[uid]=dict(observed=asdict(observed),reference=reference,receipt=receipt.to_dict(),
            native_reference=row,source_issue_only=True)
    if len(external)!=44 or sum(r['GPU_gang'] for r in external)!=59:
        raise ValueError('ORIGINAL_EXTERNAL_RUNNING_44_59_ROSTER_DRIFT')
    gate=dict(status='INITIAL_QUEUE_UNVERIFIED',PASS=False,actual_ready=False,
        scope='DDAY_2025_05_01_00_TO_24_AEST_96_SLOTS',
        reason='INDEPENDENT_DDAY_MODELED_SITE_QUEUE_INITIAL_STATE_NOT_ESTABLISHED',
        Planning_issue_only=True,Planning_allowed=True,Actual_full96_allowed=False,
        pre_day_queue_replay_executed=False,synthetic_initialization_authorized=False,
        actual_begin_epoch_seconds=midnight,source_issue_epoch_seconds=issue,
        source_record_deletion=0,unknown_reclassification=0,CC4_external_job_double_count=0)
    verify_sources(source_freeze,sources)
    return dict(qos_provider=qos,known_receipts=receipts,receipts=sources,planning=native,
        issue_epoch_seconds=issue,day_begin_epoch_seconds=midnight,end_epoch_seconds=midnight+86400,
        reference_label=REFERENCE_LABEL,reference_sha=reference_sha,arguments={},actual_gate=gate,
        planning_external_running=external,actual_truth_reads=0,
        planning_known_UID_count=len(receipts),source_reference_regeneration_calls=0,
        frozen_known_reference_reused=True,
        frozen_reference_start_rule='EXACT_SOURCE_APPROVED_FIXED_COMMON_REFERENCE_AT_ISSUE',
        frozen_nominal_service_provider='V10_Q50',
        same_reference_rule_for_known_unknown_real_actual='NOT_ESTABLISHED_DDAY_INITIAL_QUEUE_UNVERIFIED',
        common_QoS_formula_and_provider_implemented_and_fixture_tested=True,
        planning_only=True,source_snapshot_record=file_record(native_path))
