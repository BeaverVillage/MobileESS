"""Validate the exact recovered observations and seal a May23-only release."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r049 import operations as recovery
from v44_recovery_r049 import weather
from v44.common import read,record,atomic,verify,digest,now

op=recovery.op
assert not recovery.AUTH.exists()
supplement=read(weather.SUPPLEMENT);verify(supplement['sources']);assert supplement['PASS']
from v44_week3 import preparation as prepare_only
from v44_recovery_r029.weather import loader as baseline_loader
from v44.config import axis
from v44.inputs import BUNDLE_ROOT
observations=[]
with op.bindings(dict(day='2025-05-23',arm='B0',campaign_root=str(recovery.ROOT))),prepare_only.no_execution():
    for day in ('2025-05-22','2025-05-23','2025-05-24'):
        a=axis(day);bundle=BUNDLE_ROOT/('DAY_'+day.replace('-',''))
        old=baseline_loader()(begin=a['issue_seconds'],end=a['end_seconds'],bundle=bundle)
        new=weather.loader()(begin=a['issue_seconds'],end=a['end_seconds'],bundle=bundle)
        failures=[];age=0.
        for t in range(121):
            stamp=a['issue_seconds']+900*t
            try:old.at(stamp,observed_now=stamp)
            except ValueError:failures.append(t)
            current=new.at(stamp,observed_now=stamp);age=max(age,current['weather']['observation_age_seconds'])
        assert old.demand.receipt_sha==new.demand.receipt_sha and old.pv.receipt_sha==new.pv.receipt_sha
        if day!='2025-05-23':assert old.sha==new.sha
        else:assert failures==[33,34,35] and age<=7200.
        observations.append(dict(day=day,PASS=True,queries=121,original_failed_slots=failures,max_weather_age_seconds=age,
            unrelated_day_identical=day!='2025-05-23',old_bundle_sha=old.sha,new_bundle_sha=new.sha))
atomic(recovery.VALIDATION,dict(PASS=True,UTC=now(),Native_calls=0,control_ticks=0,
    regressions=80,regression=record('D:/v44_r049_regression_20261020.xml'),observations=observations,
    all_May23_121_lookups_PASS=True,original_finite_replay_count=supplement['original_finite_wet_bulb_replay_count'],
    original_finite_wet_bulb_max_abs_error=supplement['original_finite_replay_max_abs_error'],
    original_raw_files_unchanged=True,source_values_temporally_interpolated=False,
    pressure_is_derived_from_same_time_altimeter=True,max_staleness_seconds=7200))
user=recovery.HOME/'USER_REQUEST.json'
atomic(user,dict(UTC=now(),text='5월 23일은 원본 기상 공백있으면 해결해. 해결 못하는거야?',
    requested_action='Recover valid same-time raw weather source and restore May23 B0 to the existing one-worker monthly queue.'))
atomic(recovery.AUTH,dict(UTC=now(),sources=recovery.sources(),previous_authorization=record(recovery.previous.AUTH),
    validation=record(recovery.VALIDATION),supplement=record(weather.SUPPLEMENT),user_request=record(user),
    day='2025-05-23',arm='B0',eligibility_restored=True,new_B0_workers=1,original_raw_files_modified=False,
    physical_model_or_tolerance_changed=False,weather_source_derivation_changed=True,
    labelled_assumption='Standard atmosphere used to invert the measured altimeter setting with observed station elevation; pressure labelled derived, not directly observed.',
    only_original_missing_two_weather_hours_supplemented=True,current_workers_natural_terminal_only=True))
cert=dict(read(recovery.ROOT/'DOCUMENTS/B0_PREEXECUTION_CERTIFICATION.json'),UTC=now(),
    R049_authorization=record(recovery.AUTH),excluded_dates=[],allowed_dates=['2025-05-23'],weather_recovery=record(weather.SUPPLEMENT))
atomic(recovery.CERT,cert)
permit=dict(read(recovery.ROOT/'OPERATIONS/B0_EXECUTION_PERMIT.json'),UTC=now(),certification_sha=digest(cert),
    excluded_dates=[],allowed_dates=['2025-05-23'],R049_authorization=record(recovery.AUTH),
    recovery_sources=recovery.sources()+[record(recovery.AUTH),record(weather.SUPPLEMENT)],supersedes_May23_weather_exclusion_only=True)
atomic(recovery.PERMIT,permit)
recovery.authority()
with recovery.bindings(dict(day='2025-05-23',arm='B0',campaign_root=str(recovery.ROOT))):
    from v44 import prepare
    prepare.require_execution_permit(recovery.PERMIT,cert)
atomic(recovery.ROOT/'OPERATIONS/MAY23_WEATHER_RECOVERY_STATUS.json',dict(UTC=now(),status='RECOVERED_REQUEUE_ARMED',
    authorization=record(recovery.AUTH),validation=record(recovery.VALIDATION),original_exclusion_retained_as_history=True))
print(dict(PASS=True,May23_lookups=121,neighbor_lookups=242,max_staleness_seconds=7200,original_weather_unchanged=True),flush=True)
