"""Actual May31 input-loader binding checks, without full MILP construction.

The receipt explicitly separates date binding from a full matrix/domain proof.
Every date worker must materialize and prove its own model before first Native.
"""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from .common import ROOT,DAYS,read,record,sha,digest,atomic,d_path
from v42_final.common import MODEL

WORKER_PROOF='WORKER_REQUIRED_BEFORE_FIRST_NATIVE_EVERY_DATE'


def _require(ok,label):
    if not ok:raise ValueError('MAY31_DATE_BINDING_'+label)


def _axis(bundle):
    midnight=datetime.fromisoformat(bundle['day']).replace(tzinfo=timezone(timedelta(hours=10)))
    issue=datetime.fromisoformat(bundle['issue_time'])
    _require(issue.tzinfo is not None and issue==midnight-timedelta(hours=6),'D1_CAUSAL_ISSUE')
    return issue,midnight


def check_a_cells(bundle,window_rows,data):
    loaded,jobs,bounds,seconds,resources,raw=data
    issue,midnight=_axis(bundle)
    _require(loaded==bundle,'ACTUAL_LOADER_BUNDLE')
    source={r['job_uid']:r for r in bundle['known_population'] if r['planning_eligible']}
    _require(len(source)==sum(r['planning_eligible'] for r in bundle['known_population']), 'UNIQUE_ORIGINAL_JOB_IDS')
    windows={r['job_id']:r for r in window_rows}
    _require(len(windows)==len(window_rows) and set(source).issubset(windows),'FULL_WINDOW_IDENTITY')
    _require(set(raw)==set(source) and set(jobs)=={uid for uid,r in source.items() if r['service_slots']>0}
        and set(jobs)==set(bounds)==set(seconds),'ALL_ORIGINAL_POSITIVE_SERVICE_JOBS')
    for uid,r in source.items():
        submitted=datetime.fromisoformat(r['submit_time'])
        _require(submitted.tzinfo is not None and submitted<=issue and r['runtime_authority']==MODEL,'CAUSAL_JOB:'+uid)
        source_window=windows[uid]
        expected_raw=dict(r,can_timeshift=source_window['can_timeshift'],
            delay_budget_slots=source_window['latest_start']-source_window['reference_start'])
        _require(raw[uid]==expected_raw,'SOURCE_JOB_AND_WINDOW_ROUTING:'+uid)
        if uid not in jobs:continue
        job=jobs[uid];bound=bounds[uid]
        _require(job.uid==uid and job.state==r['state'] and job.reference_start==r['reference_start_if_authorized']
            and job.reference_site==r['planning_site'] and job.service_slots==r['service_slots']
            and job.gpu==r['GPU_gang'] and job.elapsed_seconds==r['elapsed_seconds']
            and job.duration_authority==MODEL and seconds[uid]==r['exact_service_seconds'], 'NATIVE_JOB_CELL:'+uid)
        cohort=r['cohort'].split('|')
        compatible=tuple(s for s,capacity in bundle['capacities'].items()
            if r['GPU_gang']<=capacity and any(rack['aidc_id']==s
                and r['GPU_gang']<=rack['compatibility_GPU_limit'] for rack in bundle['racks']))
        from v42_job_capability import checkpoint_records
        checkpoint=bool(r['can_checkpoint_migrate'] and any(24<=cp<118 for cp,_ in
            checkpoint_records(job,job.reference_start,min(job.reference_start+job.service_slots,120))))
        _require(job.submit==job.event==0 and job.qos==cohort[0] and job.protected==(cohort[3]=='True')
            and job.initial_sites==compatible and job.checkpoint_authorized==checkpoint
            and job.admitted and not job.unknown_arrival and job.migrations_used==0
            and not job.standby_candidate_authorized,'ORIGINAL_JOB_CAPABILITY_CELLS:'+uid)
        _require(tuple(bound.allowed_starts)==tuple(source_window['allowed_starts'])
            and bound.latest_completion==max(max(bound.allowed_starts),120)+job.service_slots,
            'ORIGINAL_FINITE_SERVICE_WINDOW_AND_TAIL:'+uid)
        bound.require()
    racks={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in bundle['capacities']}
    _require(resources.capacities==bundle['capacities'] and resources.rack_limits==racks
        and resources.control_end==120 and resources.bytes_per_gpu==bundle['WAN']['bytes_per_gpu']
        and resources.restart_slots==1 and resources.max_active_transfers==bundle['WAN']['maximum_active_transfers'],
        'ORIGINAL_ALL_RESOURCE_CELLS')
    paths={(p['source'],p['destination']):tuple(p['links']) for p in bundle['WAN']['paths']}
    _require(resources.paths==paths,'ALL_ORIGINAL_WAN_PATHS')
    expected_wan={(link,t):values[t-24] if t>=24 else 0
        for link,values in bundle['WAN']['link_capacity_bytes_15min'].items() for t in range(120)}
    _require(resources.wan_capacities==expected_wan,'ORIGINAL_WAN_ISSUE_TO_DAY_24_SLOT_MAPPING')
    fixed={}
    for r in source.values():
        if r['state']=='RUNNING' and r['service_slots']==0:
            key=(r['planning_site'],0);fixed[key]=fixed.get(key,0)+r['GPU_gang']
    _require(resources.fixed_gpu==fixed and not resources.fixed_wan and not resources.fixed_transfers,
        'Q50_EXPIRED_RUNNING_ISSUE_GANGS_PRESERVED')
    return dict(PASS=True,raw_eligible_jobs=len(raw),positive_service_native_jobs=len(jobs),
        zero_future_service_rows=len(raw)-len(jobs),job_ids_SHA=digest(sorted(jobs)),
        native_jobs_SHA=digest({uid:asdict(j) for uid,j in jobs.items()}),
        windows_SHA=digest({uid:asdict(b) for uid,b in bounds.items()}),
        resources_SHA=digest(asdict(resources)),all_original_jobs_windows_and_resource_cells_checked=True,
        source_service_seconds_preserved=True,issue_relative_axis=120,DDAY_offset=24,
        latest_completion_is_representation_tail_not_new_deadline=True)


def check_coefficients(day,certificate,coefficients):
    _require(certificate['input_identity']['identity']['inputs']['day']==day,'SAME_DAY_ELECTRICAL_CERTIFICATE')
    outputs=certificate['outputs'];arrays={}
    for name in ('voltage','current','planning_coefficients','transformer_coefficients'):
        ref=outputs[name]
        _require(sha(ref['path'])==ref['sha256'],'ELECTRICAL_OUTPUT_SHA:'+name)
        with np.load(ref['path'],allow_pickle=False) as z:arrays[name]={k:z[k].copy() for k in z.files}
    v,p,tx=arrays['voltage'],arrays['planning_coefficients'],arrays['transformer_coefficients']
    _require(str(v['operating_day'])==day and len(coefficients)==96
        and v['anchor_control'].shape==(96,60),'ORIGINAL_DAY_96_CONTROL60_AXIS')
    from v42_thermal.planning import normalized_response,require_coefficient
    current,matrix,denominators=normalized_response(p['branch_names'],p['current_constant'],p['current_matrix'],arrays['current']['rating_a'])
    unchanged=('voltage_constant','voltage_matrix','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits')
    ids=[i for i,n in enumerate(p['branch_names']) if str(n).startswith('transformer.')]
    ratings=[None]*len(p['branch_names'])
    for i,r in zip(ids,tx['ratings']):ratings[i]=float(r)
    for t,c in enumerate(coefficients):
        require_coefficient(c)
        _require(c.slot==t and c.control_names==tuple(map(str,v['control_names']))
            and c.branch_names==tuple(map(str,p['branch_names'])) and c.transformer_ratings==tuple(ratings)
            and np.array_equal(c.anchor,v['anchor_control'][t]),'ALL_ORIGINAL_COEFFICIENT_AXES')
        _require(all(np.array_equal(getattr(c,key),p[key][t]) for key in unchanged)
            and np.array_equal(c.current_constant,current[t]) and np.array_equal(c.current_matrix,matrix[t])
            and np.array_equal(c.current_denominators_A,denominators),'BIT_EXACT_ORIGINAL_COEFFICIENTS')
    _require(len(ids)==120 and len(set(coefficients[0].control_names))==60,'ALL_TRANSFORMER_PHASES_AND_CONTROLS')
    return dict(PASS=True,slots=96,controls=60,transformer_phase_current_rows_per_slot=120,
        all_unchanged_source_coefficient_arrays_bit_exact=True,
        original_NormalAmps_denominator_binding_bit_exact=True,
        coefficient_SHA_by_slot=[c.coefficient_sha256 for c in coefficients],
        transformer_current_authority_SHA=coefficients[0].transformer_current_authority_sha256,
        electrical_outputs={name:record(row['path']) for name,row in outputs.items()
            if name in ('voltage','current','planning_coefficients','transformer_coefficients')})


def check_forecast(bundle,operations,kernel_path,*,may01_profile_path=None,may01_bundle_path=None):
    from v42_final.workload import profile,ForecastBook
    issue,midnight=_axis(bundle); cc=operations['forecast_inputs']['current_CC4']
    _require(cc['target_day']==bundle['day'] and not cc['future_job_ids']
        and np.array_equal(bundle['C0_Q50'],cc['Q50_GPUh'])
        and np.array_equal(bundle['C0_Q90'],cc['Q90_GPUh']),'ORIGINAL_SAME_DAY_CC4')
    if 'issue_time' in cc:_require(datetime.fromisoformat(cc['issue_time'])==issue,'CC4_ISSUE')
    book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),midnight.timestamp())
    kernel=pd.read_csv(kernel_path).kappa.to_numpy()
    nominal=profile(book.q50,kernel);reserve=profile(np.asarray(book.q90)-np.asarray(book.q50),kernel)
    if bundle['day']=='2025-05-01':
        # native_inputs.main preserves this CSV as scientific input.  Its
        # original historical producer used the in-memory TRAIN kernel before
        # serializing that kernel; regenerating from the later CSV is a
        # different binary64 computation.  Prove source preservation directly,
        # and independently prove the current loader's profile below.
        profile_path=Path(may01_profile_path or ROOT/'docs/v42_final_integration/MAY01_CC4_EXECUTION_PROFILE.csv')
        bundle_path=Path(may01_bundle_path or ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
        frozen=pd.read_csv(profile_path); frozen_bundle=read(bundle_path)
        _require(frozen_bundle['day']==bundle['day']
            and np.array_equal(frozen.slot,np.arange(len(frozen)))
            and np.array_equal(frozen_bundle['C0_Q50'],bundle['C0_Q50'])
            and np.array_equal(frozen_bundle['C0_Q90'],bundle['C0_Q90']),
            'MAY01_ORIGINAL_SERIALIZED_CC4_SOURCE')
        _require(np.array_equal(bundle['unknown_nominal_GPU'],frozen.nominal_GPU)
            and np.array_equal(bundle['CC4_reserve_GPU'],frozen.CC4_uncertainty_headroom_target_GPU)
            and np.array_equal(bundle['unknown_nominal_GPU'],frozen_bundle['unknown_nominal_GPU'])
            and np.array_equal(bundle['CC4_reserve_GPU'],frozen_bundle['CC4_reserve_GPU'])
            and len(frozen)==len(nominal)==len(reserve),
            'ORIGINAL_FULL_CC4_PROFILE_AND_TAIL')
        preserved_profile=dict(kind='ORIGINAL_MAY01_SERIALIZED_INPUT_PROFILE',
            profile=record(profile_path),native_input=record(bundle_path),
            original_producer=record(ROOT/'v42_final/native_inputs.py'),
            stored_profile_bit_exact=True,
            recomputation_from_serialized_kernel_bit_exact=bool(
                np.array_equal(bundle['unknown_nominal_GPU'],nominal)
                and np.array_equal(bundle['CC4_reserve_GPU'],reserve)),
            recomputation_difference_is_not_a_tolerance_acceptance=True)
    else:
        _require(np.array_equal(bundle['unknown_nominal_GPU'],nominal)
            and np.array_equal(bundle['CC4_reserve_GPU'],reserve),'ORIGINAL_FULL_CC4_PROFILE_AND_TAIL')
        preserved_profile=dict(kind='ORIGINAL_PER_DAY_CSV_KERNEL_PROFILE',
            original_producer=record(ROOT/'v42_pr134_b1/inputs.py'),stored_profile_bit_exact=True,
            recomputation_from_serialized_kernel_bit_exact=True)
    _require(np.array_equal(cc['nominal_unknown_GPU_96'],nominal[:96])
        and np.array_equal(cc['spread_headroom_GPU_96'],reserve[:96]),'SAME_DAY_CC4_PREFIX')
    return dict(PASS=True,day_start_epoch=book.day_start,issue_epoch=issue.timestamp(),
        nominal_full_slots=len(nominal),reserve_full_slots=len(reserve),
        hourly_Q50_GPUh=float(sum(book.q50)),original_kernel=record(kernel_path),
        original_full_profile_exact=True,stored_profile_authority=preserved_profile,
        actual_current_loader_profile_bit_exact=True,full_tail_kept=True,reserve_entered_electrical_load=False)


def check_day(day,campaign_root):
    root=d_path(campaign_root); a_inputs=root/'inputs/B1'/day; m_inputs=root/'inputs/B2'/day
    output=root/'date_bindings'/day;output.mkdir(parents=True,exist_ok=True)
    a=read(a_inputs/'NATIVE_INPUT.json'); m=read(m_inputs/'NATIVE_INPUT.json')
    _require(a['day']==m['day']==day,'ARM_DATE')
    from v42_pr134_b1.native import bind,original_coefficients_for_day
    from v42_integrated.contract import physical_authority
    from v42_native.voltage import voltage_for,Stage
    import v42_may01.prepare as original
    import gurobipy as gp
    def forbid_model(*args,**kwargs):raise AssertionError('DATE_BINDING_FULL_MODEL_CONSTRUCTION_FORBIDDEN')
    with patch.object(gp,'Model',forbid_model),physical_authority() as thermal:
        data_module,_,a_coeff,power,idle,swing=bind(a,a_inputs,output)
        a_cells=check_a_cells(a,read(a_inputs/'WINDOWS.json'),data_module.load_native())
        cert=read(a['electrical_certificate']['path'])
        coeff=check_coefficients(day,cert,a_coeff)
        _require(m['electrical_certificate']['sha256']==a['electrical_certificate']['sha256']
            and sha(m['electrical_certificate']['path'])==m['electrical_certificate']['sha256'], 'B2_SAME_DAY_ELECTRICAL_SOURCE')
        # Original M coefficients use the same source constructor/certificate.
        m_coeff=original_coefficients_for_day(original,cert,day)
        _require(all(x.coefficient_sha256==y.coefficient_sha256 for x,y in zip(a_coeff,m_coeff)),
                 'A_M_ORIGINAL_COEFFICIENT_CONSTRUCTOR')
        voltages={stage.value:asdict(voltage_for(stage)) for stage in (Stage.A1,Stage.M1)}
        _require(all(v['lower_pu']==.95 and v['upper_pu']==1.05 and v['lower_squared']==.95**2
            and v['upper_squared']==1.05**2 for v in voltages.values()),'ORIGINAL_ZERO_MARGIN_VOLTAGE')
    forecast=check_forecast(a,read(a_inputs/'OPERATIONS.json'),output/'CC4_EXECUTION_LAG_KERNEL.csv')
    from .input_checks import verify_b2
    frozen=read(m_inputs/'B2_FIXED_AIDC.json')
    with np.load(m_inputs/'PLANNING_PHYSICAL.npz',allow_pickle=False) as z:planning={k:z[k].copy() for k in z.files}
    payload=dict(bundle=m,identity=frozen['identity'],selected_jobs=frozen['selected_jobs'],planning=planning,
        anchor=dict(day=day,PCC_P_kw=planning['PCC_P_kw'].tolist()))
    admission=verify_b2(payload,m_inputs)
    c1=pd.read_csv(m_inputs/'C1_PLANNING_COEFFICIENTS.csv',float_precision='round_trip')
    default=pd.read_csv(m_inputs/'C1_PLANNING_COEFFICIENTS.csv')
    _require(len(c1)==96*len(a['capacities']) and all(power[row.aidc_id,int(row.slot)].slope==row.slope
        and power[row.aidc_id,int(row.slot)].intercept_kw==row.intercept_kw for row in c1.itertuples()),
        'ORIGINAL_SERIALIZED_C1_COEFFICIENTS')
    default_parser_differences=sum(power[row.aidc_id,int(row.slot)].slope!=row.slope
        or power[row.aidc_id,int(row.slot)].intercept_kw!=row.intercept_kw for row in default.itertuples())
    power_authority=read(m_inputs/'POWER_AUTHORITY.json')
    _require(idle==power_authority['current_IT_idle_kW_per_installed_GPU']
        and swing==power_authority['current_IT_swing_kW_per_active_GPU'],'ORIGINAL_IT_POWER_CONSTANTS')
    controls=np.zeros((96,60));names=list(m_coeff[0].control_names);sites=list(map(str,planning['sites']))
    for j,name in enumerate(names):
        site=name.split('[',1)[1][:-1]
        if name.startswith('aidc_load_kw'):controls[:,j]=planning['PCC_P_kw'][:,sites.index(site)]
        else:_require(name.startswith(('mess_p_kw','mess_q_kvar')),'ORIGINAL_CONTROL_FAMILY')
    _require(sum(n.startswith('aidc_load_kw') for n in names)==12
        and sum(n.startswith('mess_p_kw') for n in names)==24
        and sum(n.startswith('mess_q_kvar') for n in names)==24,'ORIGINAL_12_AIDC_24_MESS_PQ_CONTROL_AXIS')
    result=dict(PASS=True,day=day,Native_calls=0,model_build_calls=0,full_native_matrix_materialized=False,
        full_model_matrix_and_domain_proof=WORKER_PROOF,date_binding_only=True,
        A_original_actual_load_native=a_cells,electrical_coefficients=coeff,original_CC4=forecast,
        original_IT_constants=dict(idle_kw_per_installed_gpu=idle,swing_kw_per_active_gpu=swing),
        C1_serialized_original_binary64_values_exact=True,
        legacy_default_CSV_parser_differing_cells=int(default_parser_differences),
        B2_C1_consumer='UNCHANGED_EXISTING_CAPACITY_PLANNING_DEFAULT_PANDAS_PARSER',
        B2_fixed_AIDC_admission=admission,M_fixed_AIDC_control_anchor_SHA=digest(controls),
        M_AIDC_decision_variables=0,voltage=voltages,NormalAmps_authority=thermal['transformer_current_authority_sha256'],
        all_original_120_phase_current_bindings=True,
        source_inputs={arm:{name:record(root/'inputs'/arm/day/name) for name in
            (('NATIVE_INPUT.json','WINDOWS.json','OPERATIONS.json') if arm=='B1' else
             ('NATIVE_INPUT.json','PLANNING_INPUT_BUNDLE.json','B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz'))}
            for arm in ('B1','B2')})
    atomic(output/'DATE_BINDING_CHECK.json',result)
    return result


def audit_all(campaign_root,progress=None):
    root=d_path(campaign_root); rows=[];checker_at_start=record(Path(__file__))
    for day in DAYS:
        if progress:progress(dict(phase='MAY31_ACTUAL_INPUT_LOADER_BINDING_NATIVE0',day=day))
        rows.append(check_day(day,root))
    _require(sha(Path(__file__))==checker_at_start['sha256'],'CHECKER_SOURCE_CHANGED_DURING_AUDIT')
    result=dict(PASS=all(r['PASS'] for r in rows),days_checked=len(rows),days=rows,Native_calls=0,
        model_build_calls=0,full_native_matrix_materialized=False,
        full31_native_matrix_proof_status='NOT_MATERIALIZED_BY_DATE_BINDING_AUDIT',
        full_model_matrix_and_domain_proof=WORKER_PROOF,date_binding_only=True,
        worker_required_source=dict(A=record(ROOT/'v42_may_campaign/a_stage.py'),M=record(ROOT/'v42_may_campaign/m_stage.py'),
            M_matrix_proof=record(ROOT/'v42_may_campaign/m_model.py')),
        sources={name:record(ROOT/name) for name in ('v42_pr134_b1/native.py','v42_temporal/native.py',
            'v42_may01/prepare.py','v42_thermal/planning.py','v42_integrated/contract.py','v42_native/service.py')},
        checker=checker_at_start)
    atomic(root/'MAY31_ACTUAL_INPUT_LOADER_BINDING_AUDIT.json',result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    args=parser.parse_args()
    r=audit_all(args.root,lambda x:print(x['day'],'actual original input binding Native0',flush=True))
    print('MAY31 ACTUAL INPUT BINDING',r['PASS'],r['days_checked'],flush=True)
