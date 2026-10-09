"""Known-UID capability upper bound, preserving current V42 input masks.

No optimization, anonymous CC4 flexibility, idle-power removal, invented Jobs,
or dispatch certification. Current WINDOWS overrides only inherited TS fields,
exactly as v42_may_campaign.bindings/check_a_cells and the original A loader.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from v42_job_capability import Job, checkpoint_records
from .audit_source import write_csv


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def occupancy_by_job(rows):
    result={}
    issue_slots=np.arange(24,120)
    for row in rows:
        if row['status']!='REFERENCE_ASSIGNED':
            raise ValueError('Reference contains unassigned job')
        start=int(row['reference_start']);g=int(row['GPU_gang'])
        if row.get('q50_expired_hard_occupancy'):
            result[str(row['job_uid'])]=np.full(96,float(g))
        else:
            seconds=float(row['nominal_remaining_seconds'])
            active=np.maximum(0,np.minimum(900.,seconds-(issue_slots-start)*900))
            active[issue_slots<start]=0
            result[str(row['job_uid'])]=g*active/900.
    return result


def compatible_sites(native,row):
    gpu=int(row['GPU_gang'])
    return tuple(s for s,c in native['capacities'].items() if gpu<=c and any(
        rack['aidc_id']==s and gpu<=rack['compatibility_GPU_limit'] for rack in native['racks']))


def make_job(row,start,site,compatible):
    cohort=row['cohort'].split('|')
    return Job(str(row['job_uid']),row['state'],0,0,int(start),site,int(row['service_slots']),int(row['GPU_gang']),
        qos=cohort[0],protected=cohort[3]=='True',initial_sites=compatible,checkpoint_authorized=True,
        elapsed_seconds=row['elapsed_seconds'],duration_authority=row['runtime_authority'])


def audit_current_may01(native_folder=None,source_data_dir=None,output_dir=None):
    root=Path(__file__).resolve().parents[1]
    data=Path(source_data_dir or root/'ieee8500_v42/data/v42_inputs')
    out=Path(output_dir or root/'docs/ieee8500_v42_single_case');out.mkdir(parents=True,exist_ok=True)
    pinned=root/'ieee8500_v42/data/workload_flexibility'
    native_folder=Path(native_folder) if native_folder else pinned
    if not (native_folder/'NATIVE_INPUT.json').exists() or not (native_folder/'WINDOWS.json').exists():
        native_folder=pinned
    manifest=json.loads((pinned/'MANIFEST.json').read_text(encoding='utf-8'))
    for name in ('NATIVE_INPUT.json','WINDOWS.json'):
        if sha(native_folder/name)!=manifest['files'][name]['sha256']:
            raise ValueError('Pinned May01 input identity drift: '+name)
    paths={'native':native_folder/'NATIVE_INPUT.json','windows':native_folder/'WINDOWS.json',
        'planning':data/'PLANNING_INPUT_BUNDLE.json','reference':data/'REFERENCE.json',
        'power':data/'POWER_AUTHORITY.json','C1_weather_coefficients':data/'C1_PLANNING_COEFFICIENTS.csv',
        'C1_model':data/'C1_MODEL.json','C1_source':data/'c1_affine.py',
        'C1_thermal_source':data/'source/dayahead/v28/thermal.py',
        'physical_baseline':data/'PLANNING_PHYSICAL.npz',
        'capability_source':root/'v42_job_capability.py','current_binding_source':root/'v42_may_campaign/bindings.py',
        'current_native_loader_source':root/'v42_pr134_b1/native.py','native_canonical_source':root/'v42_final/native.py'}
    before={k:sha(p) for k,p in paths.items()}
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
    native,windows,planning,ref,power=(read(paths[k]) for k in ('native','windows','planning','reference','power'))
    rows=ref['rows'];sites=sorted(planning['capacities']);site_index={s:i for i,s in enumerate(sites)}
    nby={str(r['job_uid']):r for r in native['known_population']};rby={str(r['job_uid']):r for r in rows}
    pby={str(r['job_uid']):r for r in planning['known_population']};wby={str(r['job_id']):r for r in windows}
    if len(nby)!=1649 or len(native['known_population'])!=1649 or len(rows)!=1649 or len(planning['known_population'])!=1649 or set(nby)!=set(rby) or set(nby)!=set(pby):
        raise ValueError('Original 1649 unique UID population identity failed')
    if len(wby)!=len(windows) or set(wby)!={u for u,r in nby.items() if r['planning_eligible']}:
        raise ValueError('Current window population identity failed')
    if native['day']!=planning['day'] or planning['day']!='2025-05-01':
        raise ValueError('May01 date mismatch')
    if planning['future_actual_arrival_IDs_present']:
        raise ValueError('Future arrival leakage')
    if any(rby[u]['GPU_gang']!=nby[u]['GPU_gang'] or rby[u]['service_slots']!=nby[u]['service_slots'] or
           rby[u]['state']!=nby[u]['state'] or
           abs(float(rby[u]['nominal_remaining_seconds'])-float(nby[u]['exact_service_seconds']))>1e-9 for u in nby):
        raise ValueError('Job state/GPU/service quantity identity failed')
    occupancy=occupancy_by_job(rows)
    native_occupancy=occupancy_by_job([dict(r,status='REFERENCE_ASSIGNED',
        reference_start=r['reference_start_if_authorized'],nominal_remaining_seconds=r['exact_service_seconds'])
        for r in native['known_population']])
    known=np.zeros((96,12));eligible=np.zeros_like(known);ts_gpu=np.zeros_like(known);ps_gpu=np.zeros_like(known)
    native_known=np.zeros_like(known);native_eligible=np.zeros_like(known)
    mg_gpu=np.zeros_like(known);mg_mature_gpu=np.zeros_like(known);job_records=[];active_ids={}
    issue_slots=np.arange(24,120)
    for uid in sorted(nby):
        source,row=nby[uid],rby[uid];site=row['reference_site'];k=site_index[site];active=occupancy[uid]
        known[:,k]+=active
        current_window=wby.get(uid);compatible=compatible_sites(native,source)
        cohort=source['cohort'].split('|');protected=cohort[3]=='True';qos=cohort[0]
        admitted=bool(source['planning_eligible'])
        ts=bool(admitted and current_window and current_window['can_timeshift'])
        if ts and (source['state']!='PENDING' or protected or qos in ('high','urgent')):
            raise ValueError('Current source TS authorization violates its QoS/state gate')
        ps=bool(admitted and source['can_prestart_place'] and source['state']=='PENDING' and len(compatible)>1)
        cps=();native_cps=()
        if admitted and source['can_checkpoint_migrate'] and source['service_slots']>0:
            native_job=make_job(source,source['reference_start_if_authorized'],source['planning_site'],compatible)
            native_cps=tuple(cp for cp,_ in checkpoint_records(native_job,native_job.reference_start,
                min(native_job.reference_start+native_job.service_slots,120)) if 24<=cp<118)
            # Current B0 attribution is a declared relaxation; same source gang,
            # duration, elapsed, masks and checkpoint physics, different R0 site/start.
            job=make_job(source,row['reference_start'],site,compatible)
            cps=tuple(cp for cp,_ in checkpoint_records(job,job.reference_start,
                min(job.reference_start+job.service_slots,120)) if 24<=cp<118)
        mg=bool(native_cps and cps and len(compatible)>1)
        mature=issue_slots>=min(cps) if mg else np.zeros(96,dtype=bool)
        enabled=np.logical_or(ts or ps,mature)
        native_active=native_occupancy[uid]
        if np.any(native_active):
            native_k=site_index[source['planning_site']]
            native_mature=issue_slots>=min(native_cps) if native_cps and len(compatible)>1 else np.zeros(96,dtype=bool)
            native_known[:,native_k]+=native_active
            native_eligible[:,native_k]+=native_active*np.logical_or(ts or ps,native_mature)
        eligible[:,k]+=active*enabled;ts_gpu[:,k]+=active*ts;ps_gpu[:,k]+=active*ps
        mg_gpu[:,k]+=active*mg;mg_mature_gpu[:,k]+=active*mature
        record={'job_uid':uid,'state':source['state'],'GPU_gang':source['GPU_gang'],'service_slots':source['service_slots'],
            'native_raw_can_timeshift':source['can_timeshift'],'current_window_can_timeshift':current_window['can_timeshift'] if current_window else None,
            'source_can_prestart_place':source['can_prestart_place'],'source_can_checkpoint_migrate':source['can_checkpoint_migrate'],
            'effective_TS':ts,'effective_PS':ps,'source_current_Q50_checkpoint_candidate':bool(native_cps),
            'effective_MG_checkpoint_candidate':mg,'current_reference_earliest_eligible_checkpoint':min(cps) if cps else None,
            'qos':qos,'protected':protected,'planning_eligible':admitted,'compatible_sites':list(compatible),
            'native_reference_site':source['planning_site'],'current_reference_site':site,
            'native_reference_start':source['reference_start_if_authorized'],'current_reference_start':row['reference_start'],
            'same_source_reference_site':source['planning_site']==site,
            'same_source_reference_start':source['reference_start_if_authorized']==row['reference_start'],
            'current_window_allowed_starts':current_window['allowed_starts'] if current_window else [],
            'current_reference_in_source_window':bool(current_window and row['reference_start'] in current_window['allowed_starts']),
            'Dday_active_GPUh':float(active.sum()/4),'eligible_Dday_active_GPUh':float((active*enabled).sum()/4),
            'native_Dday_active_GPUh':float(native_active.sum()/4),
            'dispatch_certified':False,'mask_scope':'SOURCE_CANDIDATE_AUTHORITY_WITH_CURRENT_B0_ATTRIBUTION_RELAXATION'}
        job_records.append(record)
        for t in np.flatnonzero((active>0)&enabled):
            active_ids.setdefault((int(t),site),[]).append({'uid':uid,'active_gpu':float(active[t]),
                'TS':ts,'PS':ps,'MG_checkpoint_mature':bool(mature[t])})
    with np.load(paths['physical_baseline'],allow_pickle=False) as baseline:
        if list(map(str,baseline['sites']))!=sites:
            raise ValueError('Physical baseline site axis mismatch')
        error=float(np.max(abs(known-baseline['known_gpu'])))
    if error>1e-10 or np.any(eligible>known+1e-10):
        raise ValueError('Known-only occupancy conservation failed')
    # Recompute the exact source C1 at current installed GPU, preserving weather.
    from .capacity import load_c1_module
    module=load_c1_module();params=module.load_c1(data/'C1_MODEL.json')
    with paths['C1_weather_coefficients'].open(encoding='utf-8-sig',newline='') as stream:
        coeff=list(csv.DictReader(stream))
    weather={int(r['slot']):r for r in coeff}
    idle=float(power['current_IT_idle_kW_per_installed_GPU']);swing=float(power['current_IT_swing_kW_per_active_GPU'])
    slopes=np.zeros_like(known)
    for t in range(96):
        for k,s in enumerate(sites):
            cap=planning['capacities'][s]
            c=module.endpoint_secant(s,t,idle*cap,(idle+swing)*cap,float(weather[t]['wetbulb_c']),float(weather[t]['rh_pct']),params)
            slopes[t,k]=c.slope
    p_upper=eligible*slopes*swing
    native_p_upper=native_eligible*slopes*swing
    q_per_p=float(np.tan(np.arccos(float(power['PF_AIDC']))))
    output=[]
    for t in range(96):
        for k,s in enumerate(sites):
            output.append({'day':planning['day'],'slot':t,'issue_origin_slot':t+24,'aidc_id':s,
                'installed_GPU':planning['capacities'][s],'known_active_GPU':float(known[t,k]),
                'timeshift_active_GPU':float(ts_gpu[t,k]),'prestart_active_GPU':float(ps_gpu[t,k]),
                'checkpoint_candidate_active_GPU':float(mg_gpu[t,k]),'checkpoint_mature_active_GPU':float(mg_mature_gpu[t,k]),
                'eligible_union_active_GPU':float(eligible[t,k]),'noneligible_known_active_GPU':float(known[t,k]-eligible[t,k]),
                'C1_slope':float(slopes[t,k]),'IT_swing_kW_per_GPU':swing,
                'known_only_reducible_P_upper_bound_kW':float(p_upper[t,k]),
                'known_only_reducible_P_upper_bound_W':float(1000*p_upper[t,k]),
                'coupled_Q_reduction_upper_bound_kvar':float(q_per_p*p_upper[t,k]),
                'AIDC_fixed_PF':float(power['PF_AIDC']),'injected_Q_per_injected_P':q_per_p,
                'anonymous_CC4_in_bound':False,'installed_idle_in_bound':False,
                'full_dispatch_QoS_WAN_certified':False,
                'eligible_jobs_and_source_masks':active_ids.get((t,s),[])})
    after={k:sha(p) for k,p in paths.items()}
    if before!=after:
        raise ValueError('Read-only active campaign or frozen input identity changed')
    receipt={'status':'KNOWN_JOB_CAPABILITY_UPPER_BOUND_ONLY_NOT_NATIVE_DISPATCH_CERTIFIED','slots':96,'sites':sites,
        'UID_count':1649,'UID_state_GPU_service_identity_PASS':True,'UID_exact_compute_seconds_identity_PASS':True,
        'UID_population_sha256':hashlib.sha256(json.dumps(sorted(nby)).encode()).hexdigest(),
        'source_readonly_identity_PASS':True,'sources':{k:{'path':str(p),'sha256':before[k]} for k,p in paths.items()},
        'pinned_current_input_manifest':manifest,'current_inputs_portable_fallback_used':native_folder==pinned,
        'known_baseline_maximum_absolute_GPU_error':error,'known_Dday_GPUh':float(known.sum()/4),
        'eligible_known_Dday_GPUh':float(eligible.sum()/4),'eligible_known_Dday_GPUh_share':float(eligible.sum()/known.sum()),
        'maximum_known_active_GPU':float(known.sum(axis=1).max()),'maximum_eligible_known_active_GPU':float(eligible.sum(axis=1).max()),
        'maximum_site_known_only_reducible_P_kW':float(p_upper.max()),'maximum_system_known_only_reducible_P_kW':float(p_upper.sum(axis=1).max()),
        'maximum_system_known_only_reducible_Q_kvar':float((q_per_p*p_upper).sum(axis=1).max()),
        'native_reference_independent_audit':{'known_Dday_GPUh':float(native_known.sum()/4),
            'eligible_known_Dday_GPUh':float(native_eligible.sum()/4),
            'maximum_system_known_only_reducible_P_kW':float(native_p_upper.sum(axis=1).max()),
            'dispatch_certified':False,'attribution':'Exact current Native B1 R0 site/start; still a local capability upper-bound relaxation'},
        'raw_native_TS_job_count':sum(r['native_raw_can_timeshift'] is True for r in job_records),
        'effective_current_WINDOW_TS_job_count':sum(r['effective_TS'] for r in job_records),
        'effective_source_PS_job_count':sum(r['effective_PS'] for r in job_records),
        'current_Q50_source_checkpoint_candidate_count':sum(r['source_current_Q50_checkpoint_candidate'] for r in job_records),
        'B0_reference_site_mismatch_count':sum(not r['same_source_reference_site'] for r in job_records),
        'B0_reference_start_mismatch_count':sum(not r['same_source_reference_start'] for r in job_records),
        'B0_reference_outside_source_window_count':sum(not r['current_reference_in_source_window'] for r in job_records if r['planning_eligible']),
        'effective_TS_authority':'Same-folder WINDOWS.json routes inherited TS fields, exactly as current v42_pr134_b1.native.bind/load_native + v42_may_campaign.bindings.check_a_cells',
        'per_slot_bound':'eligible known active GPU * unchanged IT swing * current C1 slope; remove no idle/intercept; exclude anonymous CC4',
        'AIDC_direction':{'fixed_PF':float(power['PF_AIDC']),'injected_Q_per_injected_P':q_per_p,
                         'Q_independently_controllable':False,'positive_injection_semantics':'consume less P and proportionally less Q'},
        'WAN_constraints_preserved_in_source':{'maximum_active_transfers':native['WAN']['maximum_active_transfers'],
            'bytes_per_gpu':native['WAN']['bytes_per_gpu'],'paths':len(native['WAN']['paths']),
            'link_count':len(native['WAN']['link_capacity_bytes_15min'])},
        'QoS_deadline_joint_WAN_capacity_dispatch_verified':False,
        'upper_bound_relaxations':['Simultaneous removal of locally eligible known jobs at one cell is an upper bound; whole service must reappear elsewhere/time in a real solution',
            'Shared WAN, destination capacity, restart and full QoS/finite-window coupling not solved',
            'Different current B0 vs Native B1 reference assignments/starts make attribution uncertified until reference adapter is validated'],
        'model_or_mask_mutations':0,'job_duplication':0,'GPU_scaling':1.0,'anonymous_CC4_flexibility_claimed':False,
        'Native_optimization_calls':0,'OpenDSS_calls':0,'certified_admissible_candidate_weights':False}
    write_csv(out/'FLEXIBLE_WORKLOAD_AUDIT.csv',output);write_csv(out/'FLEXIBLE_WORKLOAD_JOB_MASKS.csv',job_records)
    np.savez_compressed(out/'KNOWN_JOB_FLEXIBILITY_BOUND.npz',sites=np.array(sites),known_gpu=known,eligible_gpu=eligible,
        P_upper_bound_kw=p_upper,Q_upper_bound_kvar=q_per_p*p_upper,C1_slope=slopes,
        native_reference_known_gpu=native_known,native_reference_eligible_gpu=native_eligible,
        native_reference_P_upper_bound_kw=native_p_upper,native_reference_Q_upper_bound_kvar=q_per_p*native_p_upper)
    (out/'FLEXIBLE_WORKLOAD_AUDIT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    text=f'''# 원본 Job 기반 AIDC 유연성 상한 감사

2025-05-01의 원본 Native/B1·현재 Planning·현재 B0 Reference 1,649개 UID를 전부 대조했다. state/GPU gang/service slots는 동일하며 Job 복제·수요 배율·유연성 비율 조작을 하지 않았다. 현재 B0의 정확한 초 단위 마지막 슬롯 점유율을 독립 계산하여 frozen known_gpu 배열과 최대 오차 {error:.3g} GPU로 일치시켰다. 원본 식별 Job만 계산하고 익명 CC4, 설치 GPU의 idle 및 C1 intercept 전력은 제거 가능한 유연성으로 세지 않았다.

현재 A loader는 NATIVE_INPUT의 역사적 can_timeshift 값을 같은 폴더 WINDOWS의 승인 mask/allowed_starts로 대체한다. 따라서 raw TS=true는 {receipt['raw_native_TS_job_count']}개지만 실제 current WINDOW TS=true는 {receipt['effective_current_WINDOW_TS_job_count']}개다. 이를 새 권한으로 만들어낸 것이 아니라 현재 source binding 그대로 보존했다. prestart flag는 원본 Native 것을 유지했고 checkpoint는 원본 checkpoint_records·causal elapsed·양자화·24≤cp<118을 확인했다. 시간별 migration 기여는 해당 checkpoint가 도달한 이후만 계산했다. 보호/QoS를 완화하거나 WAN 경로·용량을 늘리지 않았다.

96×12 셀마다 `eligible known active GPU × 원본 IT swing({swing:.12f} kW/GPU) × 해당 슬롯/site의 원본 C1 slope`를 계산했다. known GPUh={receipt['known_Dday_GPUh']:.6f}, 후보 유연 known GPUh={receipt['eligible_known_Dday_GPUh']:.6f}({100*receipt['eligible_known_Dday_GPUh_share']:.3f}%)이며 사이트 한 셀 최대 P 상한={receipt['maximum_site_known_only_reducible_P_kW']:.6f} kW, 계통 합 최대 상한={receipt['maximum_system_known_only_reducible_P_kW']:.6f} kW다. 이는 모든 AIDC 전력을 없애는 계산이 아니다. 각 셀의 UID·TS/PS/도달한 MG mask는 CSV에 있고 전체 원본 mask·시작/위치 대조는 `FLEXIBLE_WORKLOAD_JOB_MASKS.csv`에 있다.

AIDC PF={power['PF_AIDC']}를 그대로 사용했다. 소비 P를 줄이면 소비 Q도 ΔQ={q_per_p:.12f}×ΔP로 같이 줄어든다. 따라서 전기 민감도를 적용할 때 AIDC 방향은 dI/dP+{q_per_p:.12f}×dI/dQ이며 P/Q를 독립 제어하는 MESS와 구별해야 한다. 개별 P/Q 편미분만으로 AIDC Q 제어 성능을 주장할 수 없다.

현재 B0 Reference와 Native B1 Reference는 같은 Job 수량에도 site {receipt['B0_reference_site_mismatch_count']}개, 시작 {receipt['B0_reference_start_mismatch_count']}개가 다르며 현재 B0 시작이 원본 source window 밖인 admitted Job은 {receipt['B0_reference_outside_source_window_count']}개다. 따라서 이 파일은 현재 B0 위치/시간에 UID 후보 mask를 투영한 **명시적 상한 완화**이며 Native A-stage와 물리적으로 동치인 실행 가능 dispatch 또는 인증된 candidate weighting이 아니다. 실제 재배치/시간 이동은 전체 compute service, destination GPU/Rack, checkpoint/WAN·restart, QoS와 finite window를 동시에 만족해야 한다. 이 공동 검증·reference adapter가 완료되기 전에는 표의 상한을 Production 성능이나 글로벌 최적해로 승격할 수 없다. Native Solver·최적화·OpenDSS는 실행하지 않았고 활성 캠페인과 입력은 읽기만 했다.

`KNOWN_JOB_FLEXIBILITY_BOUND.npz`에는 현재 B0 배열과 **원본 Native B1 R0 위치/시작을 별도 계산한** 배열을 함께 저장했다. 별도 Native R0 known GPUh={receipt['native_reference_independent_audit']['known_Dday_GPUh']:.6f}, 후보 유연 GPUh={receipt['native_reference_independent_audit']['eligible_known_Dday_GPUh']:.6f}, 계통 합 최대 P 상한={receipt['native_reference_independent_audit']['maximum_system_known_only_reducible_P_kW']:.6f} kW이며 이것도 공동 dispatch 인증은 아니다. portable 입력은 `data/workload_flexibility/NATIVE_INPUT.json`·`WINDOWS.json`과 SHA manifest의 원본 byte 사본이고 Actual·성과 결과를 추가하지 않았다. `python -m ieee8500_v42.workload_flexibility`로 D: 활성 캠페인 없이 동일 감사를 재현한다.
'''
    (out/'FLEXIBLE_WORKLOAD_AUDIT_KO.md').write_text(text,encoding='utf-8')
    return {'sites':sites,'known_gpu':known,'eligible_gpu':eligible,'P_upper_bound_kw':p_upper,
            'Q_upper_bound_kvar':q_per_p*p_upper,'receipt':receipt}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--native-folder',type=Path)
    args=parser.parse_args();result=audit_current_may01(args.native_folder)
    print(json.dumps({k:result['receipt'][k] for k in ('status','UID_count','eligible_known_Dday_GPUh_share',
        'maximum_system_known_only_reducible_P_kW','B0_reference_site_mismatch_count','B0_reference_start_mismatch_count')},indent=2))


if __name__=='__main__':
    main()
