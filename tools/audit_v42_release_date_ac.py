"""Two fixed-MESS date-clock diagnostic inputs; Native0, never May02 Actual.

Run only after the shared measurement window is explicitly released. Passive
return profiling copies original Clock receipts without replacing any function,
class, engine setting or argument. Each engine remains the original compiler.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import argparse
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read, _validated_hardware_context
from v42_integration.current_ac_admission import CurrentACAdmission,AEST
from v42_integration.rc02_prefix_cache import PrefixCachedCurrentAC,memory_gate
from v42_integration.release_date_ac import DateCurrentAC,DatePrefixCachedCurrentAC,date_ac_static_equivalence
from v42_integration.isolated_unknown import BASE,no_native
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest

RC=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OLD=RC/'RC01/AIDC/REPLAY02'


def observed_call(function,*args):
    from v42_voltage_control.timecontrol import CommonClock
    codes={CommonClock.bind.__code__,CommonClock.settle_slot.__code__}
    records=[];previous=sys.getprofile()
    def observe(frame,event,value):
        if event=='return' and frame.f_code in codes and isinstance(value,dict):
            clock=frame.f_locals['self']
            records.append(dict(function=frame.f_code.co_name,namespace=clock.namespace,day=clock.day,
                receipt=deepcopy(value)))
    began=perf_counter()
    try:
        sys.setprofile(observe)
        result=function(*args)
    finally:
        sys.setprofile(previous)
    if sys.getprofile() is not previous:
        raise ValueError('DATE_AC_PASSIVE_PROFILER_NOT_RESTORED')
    return dict(raw_probe_result=result,observed_original_clock_returns=records,
        wall_seconds=perf_counter()-began,performance_comparison_claim=False,
        passive_return_observation_only=True,clock_or_engine_or_class_patched=False,
        runtime_source_execution=False)


def audit(output):
    if output.exists():raise FileExistsError('DATE_AC_DIAGNOSTIC_MUST_NOT_OVERWRITE')
    static=date_ac_static_equivalence()
    prefix_record=file_record(OLD/'C0/PUBLIC_PREFIX_ORIGINAL_C1.json')
    freeze_record=file_record(BASE/'PLANNING_FREEZE.json')
    mess_record=file_record(BASE/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    manifest_record=file_record('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    freeze=read(freeze_record['path'])['source_freeze'];mess=read(mess_record['path'])
    manifest=read(manifest_record['path'])
    if mess['plan_sha']!=digest({k:v for k,v in mess.items() if k!='plan_sha'}):
        raise ValueError('DATE_AC_FIXED_MESS_PLAN_SEAL_DRIFT')
    records=[prefix_record,freeze_record,mess_record,manifest_record,*static['original_sources'],
        static['additive_source'],file_record(__file__),file_record(ROOT/'v42_voltage_control/timecontrol.py'),
        *[manifest[k] for k in ('hardware','scenario','thermal')]]
    if any(file_record(r['path'])!=r for r in records):
        raise ValueError('DATE_AC_DIAGNOSTIC_SOURCE_DRIFT')
    prefix=read(prefix_record['path']);begin=prefix[0]['start_seconds']
    if datetime.fromtimestamp(begin,AEST).date().isoformat()!='2025-05-01':
        raise ValueError('DATE_AC_SAVED_PREFIX_DAY_DRIFT')
    current=deepcopy(prefix[1]);history=deepcopy(prefix[:1])
    sites=tuple(f'AIDC{i+1:02d}' for i in range(12))
    base=dict(begin=begin,sites=sites,power_model=None,observations=None,
        source_freeze=freeze,manifest=manifest,mess=mess)
    output.mkdir(parents=True)
    _write(output/'EXECUTED_DIAGNOSTIC_SOURCE.json',dict(files=records,
        static_equivalence=static,Native_calls=0,new_native_model_builds=0,
        scope='FIXED_M2_TWO_DATE_CLOCK_INPUTS_NOT_D0_ACTUAL_OR_FULL96',
        private_Truth_read=False,passive_return_profile_restored_in_finally=True))
    results={}
    with no_native() as attempts,_validated_hardware_context(freeze,manifest):
        for label,oracle,method in (
            ('MAY01_ORIGINAL_CURRENT',CurrentACAdmission(**base),'_probe'),
            ('MAY01_DATE_CURRENT',DateCurrentAC(**base),'_probe'),
            ('MAY01_ORIGINAL_PREFIX',PrefixCachedCurrentAC(**base,proof_records=records),'_replay_current'),
            ('MAY01_DATE_PREFIX',DatePrefixCachedCurrentAC(**base,proof_records=records),'_replay_current')):
            memory_gate()
            result=observed_call(getattr(oracle,method),history,current)
            result.update(input_scope='SAVED_MAY01_PUBLIC_PREFIX_SLOT1_FIXED_MESS_ONLY',
                input_sha=digest(dict(history=history,current=current)),MESS_plan_sha=mess['plan_sha'])
            _write(output/(label+'.json'),result);results[label]=result
            print(label,result['raw_probe_result']['current_native_seconds'],flush=True)
        shifted=deepcopy(base);shifted['begin']=begin+86400
        diagnostic_history=deepcopy(history);diagnostic_current=deepcopy(current)
        for row in [*diagnostic_history,diagnostic_current]:
            row['start_seconds']+=86400;row['end_seconds']+=86400
        for label,oracle,method in (
            ('MAY02_CLOCK_DIAGNOSTIC_CURRENT',DateCurrentAC(**shifted),'_probe'),
            ('MAY02_CLOCK_DIAGNOSTIC_PREFIX',DatePrefixCachedCurrentAC(**shifted,proof_records=records),'_replay_current')):
            memory_gate()
            result=observed_call(getattr(oracle,method),diagnostic_history,diagnostic_current)
            result.update(input_scope='DATE_SHIFTED_MAY01_PUBLIC_VALUES_NOT_REAL_MAY02_SOURCE',
                input_sha=digest(dict(history=diagnostic_history,current=diagnostic_current)),
                MESS_plan_sha=mess['plan_sha'],actual_May02_data_certified=False,
                May02_D0_or_FULL96_or_production_certified=False)
            _write(output/(label+'.json'),result);results[label]=result
            print(label,result['raw_probe_result']['current_native_seconds'],flush=True)
    equalities={}
    for kind in ('CURRENT','PREFIX'):
        a=results['MAY01_ORIGINAL_'+kind];b=results['MAY01_DATE_'+kind]
        equalities[kind]=dict(full_probe_result_exact=a['raw_probe_result']==b['raw_probe_result'],
            clock_return_receipts_exact=a['observed_original_clock_returns']==b['observed_original_clock_returns'],
            same_physical_steps=a['raw_probe_result']['physical_steps']==b['raw_probe_result']['physical_steps'],
            same_pending_queue=a['raw_probe_result']['future_queue_not_executed']==b['raw_probe_result']['future_queue_not_executed'])
    dates={}
    for label,packet in results.items():
        day='2025-05-02' if label.startswith('MAY02') else '2025-05-01'
        clocks=packet['observed_original_clock_returns'];probe=packet['raw_probe_result']
        dates[label]=dict(day=day,clock_receipts_observed=len(clocks),
            correct_executed_clock_day=bool(clocks) and all(c['day']==day and c['namespace']=='ACTUAL' for c in clocks),
            current_relative_seconds=probe['current_native_seconds'],relative900=probe['current_native_seconds']==900,
            original_RegControl=probe['original_RegControl'],SVR_count=probe['SVR_count'],
            original_fullnetwork_measurement_executed=all(s['checked_nodes']>0 and s['checked_current_rows']>0
                and s['physical_sha'] and s['SVR_sha'] for s in probe['physical_steps']),
            current_physical_PASS=probe['PASS'])
    unchanged=all(file_record(r['path'])==r for r in records)
    passed=(all(all(v.values()) for v in equalities.values()) and unchanged and not attempts
        and all(r['correct_executed_clock_day'] and r['relative900'] and r['original_RegControl']==7
            and r['SVR_count']==11 and r['original_fullnetwork_measurement_executed'] for r in dates.values()))
    report=dict(status='PASS_DATE_CLOCK_AND_MAY01_EQUIVALENCE_DIAGNOSTIC_ONLY' if passed else 'NOT_CERTIFIED',
        two_input_points=['MAY01_SAVED_PUBLIC_SLOT1','MAY02_DATE_SHIFT_CLOCK_DIAGNOSTIC_SLOT1'],
        same_input_May01=equalities,clock_and_measurement=dates,source_unchanged=unchanged,
        Native_calls=0,blocked_native_attempts=attempts,new_native_model_builds=0,original_OpenDSS_engine_compiles=6,
        actual_Environment_or_private_truth_read=False,Actual_runs=0,new_D0_May02_or_FULL96_certified=False,
        original_current_ASOF_semantics_preserved=True,official_settled_Fresh_or_Full96_gate_issued=False,
        passive_profile_changes_physics_or_clock_or_engine=False,diagnostic_tool=file_record(__file__))
    _write(output/'DATE_AC_PHYSICAL_DIAGNOSTIC.json',report)
    print(report['status'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=RC/'RC03/DATE_AC/PHYSICAL01')
    audit(parser.parse_args().output)
