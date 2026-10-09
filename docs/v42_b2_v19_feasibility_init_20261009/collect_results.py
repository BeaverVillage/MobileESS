"""Collect sealed measured evidence without Solver calls or model mutation."""
from pathlib import Path
import sys,json,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fractions import Fraction as F
import numpy as np
from v42_b2_seed_recovery_v19.common import read,atomic,record,sha,now
from v42_b2_seed_recovery_v19.policy import MODEL_FIELDS,verify_manifest

HERE=Path(__file__).resolve().parent
CAMPAIGN=Path('D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01')
MAIN=Path('D:/MobileESS_V42')

def attempt(root,day,version):
    path=root/f'dates/B2/{day}/attempts/seed_policy_{version}'
    return path,read(path/'RESULT.json'),read(path/'NATIVE_RUNTIME_LEDGER.json')

def row(label,path,result,ledger,*,only_start=False):
    scientific=result.get('scientific',{})
    calls=[c for c in ledger['calls'] if not only_start or c['track']=='M_START']
    passed=True if only_start else result.get('PASS') is True
    cert=read(path/'output/STATIONARY_DISPATCH_REPLAY.json') if only_start else read(scientific['FULL_certificate']['path']) if passed else None
    return dict(label=label,day=result['identity']['day'],FULL_PASS=passed,
        UB=cert['Global_UB'] if cert else None,exact_UB=cert['exact_Global_UB'] if cert else None,
        initialization_Native_Runtime=float(sum(F(float(c['Native_Runtime'])) for c in calls)),
        first_FULL_wall_seconds=None if only_start else scientific.get('first_FULL_pass_wall_seconds'),
        model_generation=scientific.get('model_generation'),
        first_FULL_stage='STATIONARY_LP' if only_start else scientific.get('first_FULL_stage'),
        point_SHA=cert['point_vector_sha256'] if cert else None,
        source_SHA=result['source_SHA'],source_commit=result.get('source_commit'),
        Native_calls=calls,result=record(path/'RESULT.json'),ledger=record(path/'NATIVE_RUNTIME_LEDGER.json'),
        FULL_certificate=record(path/'output/STATIONARY_DISPATCH_REPLAY.json') if only_start else scientific.get('FULL_certificate'),
        LB=None,Global_Gap=None,Adaptive_entered=False)

def main():
    final=CAMPAIGN/'initialization_benchmark_v19_03';manifest=verify_manifest(final/'CONTINUATION_V19_MANIFEST.json')
    cp=read(final/'CHECKPOINT_V19.json');assert cp['state']=='INITIALIZATION_BENCHMARK_COMPLETE' and not cp['workers']
    frozen={name:dict(expected=expected,actual=sha(MAIN/name)) for name,expected in manifest['builder_original_sources'].items()}
    assert all(r['expected']==r['actual'] for r in frozen.values())
    B1={day:dict(expected=receipt,actual=record(receipt['path'])) for day,receipt in manifest['inherited_B1_results'].items()}
    assert len(B1)==31 and all(r['expected']==r['actual'] for r in B1.values())
    rows=[]
    p,r,l=attempt(CAMPAIGN,'2025-05-01','v17_01');rows.append(row('May01 V17',p,r,l,only_start=True))
    previous=CAMPAIGN/'initialization_benchmark_v18r2_01'
    p,r,l=attempt(previous,'2025-05-02','v18r2_01');rows.append(row('May02 V18R2',p,r,l))
    p,r,l=attempt(previous,'2025-05-03','v18r2_01');rows.append(row('May03 V18R2',p,r,l))
    history=[];identity=[];cumulative=[]
    for day in ('2025-05-03','2025-05-04'):
        p,r,l=attempt(final,day,'v19_03');assert r['PASS'] and r['Native_calls']==1
        assert l['inflight'] is None and l['measured_Native_Runtime']==r['Native_Runtime']
        assert r['scientific']['seed_MILP_calls']==0 and not r['scientific']['Adaptive_entered']
        current=row('May'+day[-2:]+' V19',p,r,l);rows.append(current)
        for name in ('BENCHMARK_FULL_CERTIFICATE.json','INITIAL_POINT_DISPATCH.json','V19_MODEL_IDENTITY_VERIFICATION.json','STATIONARY_DISPATCH_MODEL_IDENTITY.json','ORIGINAL_MODEL_BUILD_TIMING.json'):
            shutil.copy2(p/'output'/name,HERE/('MAY'+day[-2:]+'_'+name))
        atomic(HERE/('MAY'+day[-2:]+'_RESULT_SUMMARY.json'),dict(**current,initialization_limit=1500.,remaining_initialization_Native=1500.-r['Native_Runtime']))
        baseline=(previous/f'dates/B2/{day}/attempts/seed_policy_v18r2_01/output/SCIENTIFIC_CASE_IDENTITY.json') if day.endswith('03') else (CAMPAIGN/f'initialization_benchmark_v19_02/dates/B2/{day}/attempts/seed_policy_v19_02/output/SCIENTIFIC_CASE_IDENTITY.json')
        old=read(baseline);new=read(p/'output/SCIENTIFIC_CASE_IDENTITY.json')
        comparison={k:dict(baseline=old[k],current=new[k],equal=old[k]==new[k]) for k in MODEL_FIELDS}
        assert all(value['equal'] for value in comparison.values())
        identity.append(dict(day=day,baseline=record(baseline),current=record(p/'output/SCIENTIFIC_CASE_IDENTITY.json'),PASS=True,fields=comparison,
            case_SHA_differs_by_artifact_root=True,no_previous_point_reuse=True))
        measured=F(0);tries=[]
        for n in (1,2,3):
            trial=CAMPAIGN/f'initialization_benchmark_v19_{n:02d}'
            a=trial/f'dates/B2/{day}/attempts/seed_policy_v19_{n:02d}'
            if (a/'RESULT.json').exists():
                rr=read(a/'RESULT.json');ll=read(a/'NATIVE_RUNTIME_LEDGER.json');assert ll['inflight'] is None
                measured+=F(float(rr['Native_Runtime']))
                tries.append(dict(attempt=n,Native_Runtime=rr['Native_Runtime'],status=rr['status'],PASS=rr['PASS'],source_SHA=rr['source_SHA'],result=record(a/'RESULT.json'),ledger=record(a/'NATIVE_RUNTIME_LEDGER.json')))
                if n==2:history.append(row('May'+day[-2:]+' V19 before FULL-route fixing',a,rr,ll))
        if day.endswith('03'):
            _,old_result,old_ledger=attempt(previous,day,'v18r2_01');measured+=F(float(old_result['Native_Runtime']))
        diagnostic=F(0);diagnostics=[]
        if day.endswith('03'):
            for n in (1,2,3,4):
                a=CAMPAIGN/f'feasibility_diagnostics_v19_{n:02d}/dates/B2/{day}/attempts/seed_policy_v19_01'
                rr=read(a/'RESULT.json');diagnostic+=F(float(rr['Native_Runtime']))
                diagnostics.append(dict(attempt=n,measured_LP_Native=rr['Native_Runtime'],result=record(a/'RESULT.json'),IIS_Native_Runtime='UNKNOWN' if n>=3 else 'NOT_CALLED'))
        q=read(CAMPAIGN/'QUARANTINE_V18_DATES.json').get('dates',{}).get(day)
        cumulative.append(dict(day=day,V19_initialization_attempts=tries,
            known_initialization_benchmark_Native=float(measured),known_diagnostic_LP_Native=float(diagnostic),
            diagnostic_attempts=diagnostics,known_study_optimize_Native_subtotal=float(measured+diagnostic),
            official_known_prior_Native=q['known_prior_Native_Runtime'] if q else 0.,
            official_cumulative_Native='UNKNOWN' if q else 0.,official_remaining_Native='UNKNOWN' if q else 5400.,
            combined_all_activity_Native='UNKNOWN' if q or diagnostics else float(measured),
            reason='V18_LOST_CALL_REMAINS_QUARANTINED_AND_IIS_RUNTIME_NOT_AN_OPTIMIZE_RUNTIME' if q else 'BENCHMARK_ONLY_OFFICIAL_DATE_BUDGET_UNTOUCHED',
            official_budget_reset=False))
    data=dict(UTC=now(),execution_commit=manifest['source_commit'],execution_SHA=manifest['execution_SHA'],manifest=record(final/'CONTINUATION_V19_MANIFEST.json'),comparison=rows,prior_V19_measured_history=history,
        independent_LB_and_Adaptive_not_run=True,official_runtime_not_reset=True,final_experiment_first_FULL_ONLY=True)
    atomic(HERE/'MEASURED_COMPARISON.json',data)
    atomic(HERE/'FROZEN_SOURCE_AND_MODEL_VERIFICATION.json',dict(PASS=True,scientific_source_files_checked=len(frozen),sources=frozen,
        B1_results_checked=31,B1_records=B1,same_day_original_model_identity=identity,
        original_FULL_Compact_C3A_Adaptive_Pricing_RMP_UB_LB_sources_unchanged=True,
        execution_SHA=manifest['execution_SHA'],official_quarantine=record(CAMPAIGN/'QUARANTINE_V18_DATES.json')))
    atomic(HERE/'CUMULATIVE_NATIVE_ACCOUNTING.json',dict(dates=cumulative,UNKNOWN_never_reset_to_zero=True,benchmark_prior_attempts={},official_results_immutable=True))
    print(json.dumps(dict(PASS=True,scientific_sources=len(frozen),B1=31,dates=[dict(label=r['label'],Native=r['initialization_Native_Runtime'],UB=r['UB'],FULL=r['FULL_PASS']) for r in rows],cumulative=cumulative),ensure_ascii=False))

if __name__=='__main__':main()
