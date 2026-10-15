"""Measured same-input Original AC equivalence before any cache adoption."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record,_power_model,_validated_hardware_context
from v42_integration.current_ac_admission import CurrentACAdmission
from v42_integration.rc02_prefix_cache import PrefixCachedCurrentAC,memory_gate
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.isolated_unknown import BASE,RAW,no_native
from v42_integration.unified_contract import digest

OLD=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/VOLTAGE/PREFIX_CACHE_BENCH01'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'EXECUTED_BENCHMARK_SOURCE.json').exists():raise FileExistsError('RC02_BENCHMARK_IMMUTABLE')
    original=read(OLD/'EXECUTED_SOURCE.json')['files']
    manifest=read('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json')
    records=original+[record(ROOT/'v42_integration/rc02_prefix_cache.py'),record(__file__),
        record(ROOT/'v42_voltage_control/timecontrol.py')]+[manifest[k] for k in ('hardware','scenario','thermal')]
    for r in records:
        if any(record(r['path'])[k]!=r[k] for k in ('sha256','bytes')):raise ValueError('BENCHMARK_SOURCE_DRIFT')
    write_new(OUT/'EXECUTED_BENCHMARK_SOURCE.json',dict(material=records,Native_calls=0,
        observation_cache_only=True,all_native_prefix_solves_executed=True))
    prefix=read(OLD/'C0/PUBLIC_PREFIX_ORIGINAL_C1.json')
    real=read(OLD/'CURRENT_SAME_INPUT_AC_CROSSCHECK.json')['results']
    freeze=read(BASE/'PLANNING_FREEZE.json')['source_freeze']
    mess=read(BASE/'M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json')
    points=[]
    begin=prefix[0]['start_seconds'];sites=tuple(f'AIDC{i+1:02d}' for i in range(12))
    for row in real:
        t=int((row['time_seconds']-begin)/900)
        current=deepcopy(prefix[t]);current.update(GPU=row['instant_GPU'],P=row['candidate_P'],Q=row['candidate_Q'])
        points.append(dict(name='ACTUAL_START_'+row['uid'],current=current,expected=row))
    # Late current state is a diagnostic point, not a new dispatch. Include a
    # known physical-FAIL interval so cache equivalence cannot mean PASS-only.
    for t in (12,15):points.append(dict(name='ASOF_INTERVAL_CURRENT_'+str(t),current=deepcopy(prefix[t]),expected=None))
    class ExistingObservations:
        def at(self,when,*,observed_now):
            if when>observed_now:raise ValueError('BENCHMARK_FUTURE_OBSERVATION')
            return deepcopy(prefix[int((when-begin)/900)]['observations'])
    results=[];conditional=[]
    with no_native() as attempts,_validated_hardware_context(freeze,manifest):
        model,_=_power_model(read(RAW/'POWER_AUTHORITY.json'),read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')['capacities'])
        arguments=dict(begin=begin,sites=sites,power_model=model,observations=ExistingObservations(),
            source_freeze=freeze,manifest=manifest,mess=mess)
        plain=CurrentACAdmission(**arguments)
        cached=PrefixCachedCurrentAC(**arguments,proof_records=records)
        for point in points:
            current=point['current'];history=prefix[:current['slot']]
            memory=memory_gate()
            tick=perf_counter();baseline=plain._probe(history,current);baseline_seconds=perf_counter()-tick
            key=cached.prefix_proofs.key(history=history,current_slot=current['slot'],
                current_observations=current['observations'],source_sha=freeze['source_sha'],MESS_plan_sha=mess['plan_sha'])
            cached.prefix_proofs.put(key,baseline['physical_steps'][:-1])
            tick=perf_counter();fast=cached._probe(history,current);cached_seconds=perf_counter()-tick
            same_current=baseline['physical_steps'][-1]==fast['physical_steps'][-1]
            same_full=baseline['physical_steps']==fast['physical_steps']
            same_queue=baseline['future_queue_not_executed']==fast['future_queue_not_executed']
            same_fail=baseline['historical_prefix_physical_PASS']==fast['historical_prefix_physical_PASS']
            original_match=True
            if point['expected'] is not None:
                original_match=(baseline['physical_steps'][-1]['physical_sha']==digest(point['expected']['physical'])
                    and baseline['physical_steps'][-1]['SVR_sha']==digest(point['expected']['SVR']))
            row=dict(point=point['name'],slot=current['slot'],memory=memory,
                baseline_seconds=baseline_seconds,cached_seconds=cached_seconds,
                speedup=baseline_seconds/cached_seconds,same_full_physical_steps=same_full,
                same_current_full_physical_and_SVR_SHA=same_current,same_pending_queue=same_queue,
                previous_failure_preserved=same_fail,real_start_RC01_proof_matches=original_match,
                current_PASS=baseline['PASS'],past_physical_PASS=baseline['historical_prefix_physical_PASS'],
                measured_prefix_steps=len(baseline['physical_steps'])-1,
                original_prefix_physical_solves_executed=fast['executed_prefix_physical_solves'],
                Native_calls=0,current_input=current,source_bound_prefix_key=key)
            row['PASS']=all((same_current,same_full,same_queue,same_fail,original_match,
                row['measured_prefix_steps']==row['original_prefix_physical_solves_executed']))
            write_new(OUT/(point['name']+'_PROOF.json'),dict(result=row,baseline=baseline,cached=fast))
            results.append(row)
            print(point['name'],row['PASS'],round(baseline_seconds,3),round(cached_seconds,3),flush=True)
        for site in ('AIDC03','AIDC12'):
            rows=[]
            for t in range(2):
                row=deepcopy(prefix[0]);row.update(slot=t,start_seconds=begin+t*900,end_seconds=begin+(t+1)*900)
                gpu=np.asarray(prefix[0]['GPU'],float);gpu[sites.index(site)]+=1
                power=model.recompute(gpu[None,:],sites,[row['observations']['weather']['values']])
                row.update(GPU=gpu.tolist(),P=power['PCC_P_kw'][0].tolist(),Q=power['PCC_Q_kvar'][0].tolist());rows.append(row)
            tick=perf_counter();full=cached._probe([],rows[0],future_rows=rows);cold=perf_counter()-tick
            tick=perf_counter();memo=cached._probe([],rows[0],future_rows=rows);warm=perf_counter()-tick
            plain_result={k:v for k,v in full.items() if k!='conditional_proof_cache_hit'}
            memo_result={k:v for k,v in memo.items() if k!='conditional_proof_cache_hit'}
            item=dict(site=site,scope='COUNTERFACTUAL_PUBLIC_HELD_INPUT_Q50_1800_NOT_REAL_JOB_OR_PERMISSION',
                PASS=plain_result==memo_result,baseline_seconds=cold,cached_seconds=warm,
                physical_and_SVR_and_pending_queue_exact=plain_result==memo_result,
                independent_current_candidate_still_required=True)
            conditional.append(item);write_new(OUT/('CONDITIONAL_'+site+'_PROOF.json'),dict(result=item,full=full,cached=memo))
    for r in records:
        if any(record(r['path'])[k]!=r[k] for k in ('sha256','bytes')):raise ValueError('BENCHMARK_SOURCE_DRIFT_AFTER')
    report=dict(status='PASS_SAME_INPUT_PHYSICAL_SVR_AND_QUEUE_EQUIVALENCE' if all(r['PASS'] for r in results+conditional) else 'NOT_CERTIFIED',
        scope='NATIVE0_EXACT_PREFIX_OBSERVATION_CACHE_BENCHMARK_NOT_RC01_REEXECUTION',results=results,
        conditional_prediction_proofs=conditional,
        Native_calls=0,blocked_native_attempts=attempts,Original_controls_unchanged=True,
        no_prefix_solve_or_due_queue_checks_skipped=True,physical_FAIL_not_hidden=True,
        frozen_RC01_algorithm_modified=False,campaign_or_Full96_or_new_control_policy_CERTIFIED=False,
        sum_baseline_seconds=sum(r['baseline_seconds'] for r in results),sum_cached_seconds=sum(r['cached_seconds'] for r in results))
    write_new(OUT/'BENCHMARK_RESULT.json',report)
    print(report['status'],flush=True)


if __name__=='__main__':main()
