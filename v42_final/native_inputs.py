"""Bind approved Q50 to May known metadata without reading future outcomes."""
import re,zipfile,math
import pyarrow.parquet as pq
from .common import *
from .runtime import FrozenQ50
from .state import planning_remaining,legacy_unassigned


def memory_mib(value):
    # Exact frozen V6 normalization inherited by the V10 feature contract.
    m=re.fullmatch(r'([\d.]+)([KMGTPkmgtp]?)[nN]?',str(value).strip())
    return float(m[1])*{'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3,'':1}[m[2].upper()] if m else np.nan


def main():
    require(read(OUT/'FROZEN_FOLD5_PROVIDER_REPRODUCTION.json')['PASS'],'PROVIDER_REPRODUCTION_REQUIRED')
    oldpath=ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json';old=read(oldpath);issue=pd.Timestamp(old['issue_time'])
    snapshot=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet')
    cols=['id','submit_time','nodes_req','processors_req','memory_req','wallclock_req','qos','partition','gpus_requested','account_hash','source_member']
    f=pd.read_parquet(snapshot,columns=cols);f['id']=f.id.astype(str)
    raw=read(RUNTIME/'docs/runtime_vnext8_trace_feature_total/SOURCE_MANIFEST.json')['raw']
    require(sha(raw['path'])==raw['sha256'],'RAW_REQUEST_ARCHIVE_SHA')
    # array_pos was not retained by the old native snapshot. Recover only this
    # submission descriptor for the already-known exact IDs, never start/end.
    arrays=[];members=sorted(f.source_member.unique())
    with zipfile.ZipFile(raw['path']) as archive:
        for member in members:
            with archive.open(member) as stream:
                a=pq.read_table(stream,columns=['id','array_pos'],use_threads=False).to_pandas()
            a['id']=a.id.astype(str);arrays.append(a[a.id.isin(set(f.id))])
    a=pd.concat(arrays);require(a.id.is_unique and set(a.id)==set(f.id),'ARRAY_DESCRIPTOR_IDENTITY')
    f=f.merge(a,on='id',validate='one_to_one');require((f.submit_time<=issue).all(),'KNOWN_SUBMISSION_CAUSALITY')
    requests=pd.DataFrame(dict(num_gpus_req=f.gpus_requested,num_nodes_req=f.nodes_req,num_cores_req=f.processors_req,
        requested_memory_mib=f.memory_req.map(memory_mib),requested_seconds=f.wallclock_req.dt.total_seconds(),
        array_index=f.array_pos,account=f.account_hash,qos=f.qos,partition=f.partition))
    provider=FrozenQ50();q=provider.predict_batch(requests.to_dict('records'),submit_times=list(f.submit_time),event_time=issue)
    qby=dict(zip(f.id,q));ts=pd.read_csv(OUT/'TIMESHIFT_CAPABILITY_SUMMARY.csv',dtype={'job_id':str}).set_index('job_id')
    gamma=read(OUT/'RUNTIME_RESERVE_CALIBRATION.json')['gamma_90'];kernel=pd.read_csv(OUT/'RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv').survival.to_numpy()
    rows=[]
    for j in old['known_population']:
        total=float(qby[j['job_uid']]);elapsed=j['elapsed_seconds'] or 0.;p=planning_remaining(total,elapsed,state=j['state'])
        start=int(j['reference_start_if_authorized'])
        end=start+p['nominal_slots']
        risk_end=(total-elapsed)/900 if j['state']=='RUNNING' else start+total/900
        rows.append(dict(j,**p,old_source_exact_service_seconds=j['exact_service_seconds'],
            exact_service_seconds=p['nominal_remaining_seconds'],service_slots=p['nominal_slots'],
            V10_Q50_total_seconds=total,nominal_reference_end=end,reference_end=end,
            risk_nominal_completion_issue_slot=math.ceil(risk_end),
            can_timeshift=bool(ts.loc[j['job_uid'],'can_timeshift']) if j['planning_eligible'] else None,
            delay_budget_slots=int(ts.loc[j['job_uid'],'delay_budget_slots']),
            runtime_authority=MODEL,old_requested_remaining_is_new_nominal=False,
            unresolved_external_source_service_end=j['reference_end'] if not j['planning_eligible'] else None))
    # Legacy exception uses original source service, not a new synthetic site
    # or a new inferred completion. It remains explicitly external/unresolved.
    legacy=legacy_unassigned(old['known_population']);require(len(legacy)==44,'LEGACY_44_IDENTITY')
    profile=pd.read_csv(OUT/'MAY01_CC4_EXECUTION_PROFILE.csv')
    bundle=dict(old,known_population=rows,C0_binding='LIFETIME_GPUH_EXECUTION_LAG_CONVOLUTION',
        unknown_nominal_GPU=profile.nominal_GPU.tolist(),CC4_reserve_GPU=profile.CC4_uncertainty_headroom_target_GPU.tolist(),
        runtime_reserve_gamma=gamma,runtime_survival_kernel=kernel.tolist(),RUNTIME_PROVIDER_READY=True,
        runtime_provider=rec(provider.root/'INTEGRITY.json'),old_PR93_certificate_status='SUPERSEDED_FOR_V42_FINAL_INTERFACE',
        current_RUNNING_GPU_is_hard=True,Actual_duplicate_runtime_reserve=False,
        legacy_unassigned_basis='Original authorized pre-D00 source residual only; new Q50 does not create D-day service',
        new_timeshift_authority=rec(OUT/'TIMESHIFT_DELAY_AUTHORITY.json'))
    dump('MAY01_FINAL_NATIVE_INPUT_BUNDLE.json',bundle);csv('MAY01_Q50_JOB_LEDGER.csv',rows)
    dump('MAY01_RUNTIME_INFERENCE_AUDIT.json',dict(PASS=True,N=len(rows),admitted_N=sum(r['planning_eligible'] for r in rows),
        q50_seconds_min=float(q.min()),q50_seconds_max=float(q.max()),
        running_Q50_expired_N=sum(r['state']=='RUNNING' and r['overrun_uncertainty'] for r in rows),
        old_source=rec(oldpath),snapshot=rec(snapshot),raw=raw,raw_members=members,raw_columns_read=['id','array_pos'],
        predictor_columns=list(requests),future_outcome_reads=0,model_fit_calls=0,calibration_fit_calls=0,
        prior_request_version_limitation='Kestrel trace proxy inherited; study authorization does not establish original request-version history',
        member_projection='April archive for already-known IDs only; no May Actual payload',runtime_unit='seconds'))
    # Update denominator to this interface's nominal remaining-service GPUh.
    active=[r for r in rows if r['planning_eligible']];den=sum(r['service_slots']*r['GPU_gang']/4 for r in active)
    dump('FINAL_CAPABILITY_COUNTS.json',dict(scope='Source candidate masks, not complete-option globally feasible witnesses',
        jobs=len(active),nominal_remaining_reserved_GPUh=den,
        masks={key:dict(jobs=sum(bool(r[key]) for r in active),job_share=sum(bool(r[key]) for r in active)/len(active),
            nominal_remaining_GPUh=sum(r['service_slots']*r['GPU_gang']/4 for r in active if r[key]),
            GPUh_share=sum(r['service_slots']*r['GPU_gang']/4 for r in active if r[key])/den)
            for key in ('can_timeshift','can_prestart_place','can_checkpoint_migrate')},unresolved=44))
    print(json.dumps(dict(jobs=len(rows),Q50_min=float(q.min()),Q50_max=float(q.max()),
        running_expired=sum(r['state']=='RUNNING' and r['overrun_uncertainty'] for r in rows)),indent=2))


if __name__=='__main__':main()
