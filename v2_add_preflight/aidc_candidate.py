"""Bounded, independently checked Job witnesses; no A-stage solver calls."""
import ast
from dataclasses import dataclass
import io
import json
import math
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from .audit import DOC,ROOT,read,save,sha,table
from .physical import RUNTIME


def actual_c1(gpu,sites,day,role='ACTUAL'):
    """Compile only the original pure C1 functions, without campaign imports."""
    power=read(day['files']['power_authority']['path'])
    impl=Path('D:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/v28r2/c1_affine.py')
    model=Path('D:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')
    names={'C1Parameters','load_c1','_softplus','exact_c1_pcc_kw'}
    tree=ast.parse(impl.read_text(encoding='utf-8'))
    body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    env=dict(np=np,json=json,Path=Path,dataclass=dataclass,FROZEN_NLR_EQUIVALENT_SCALE=3.4987194698200215,
             GFS_NORMALIZATION_FACTOR=power['normalization'],__name__='v2_add_original_pure_c1')
    # The dataclass decorator needs a registered module for annotation resolution.
    import types,sys
    module=types.ModuleType(env['__name__']);module.__dict__.update(env);sys.modules[module.__name__]=module
    exec(compile(ast.Module(body=body,type_ignores=[]),str(impl),'exec'),module.__dict__)
    pars=module.load_c1(model)
    if role=='ACTUAL':
        weather=pd.read_parquet(Path('D:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v24t_thermal_aware_aidc/V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet'),columns=['ts','t_wb_c','rh_pct'])
        seconds=np.array([pd.Timestamp(t).timestamp() for t in weather['ts']]);order=np.argsort(seconds);seconds=seconds[order];weather=weather.iloc[order]
    else:
        coefficients=pd.read_csv(Path(day['files']['power_authority']['path']).with_name('C1_PLANNING_COEFFICIENTS.csv'))
        weather=coefficients
        weather=weather[weather['aidc_id']==sites[0]].sort_values('slot')
    native=read(day['files']['native']['path']);installed=np.array([native['capacities'][s] for s in sites])
    it=power['current_IT_idle_kW_per_installed_GPU']*installed+power['current_IT_swing_kW_per_active_GPU']*gpu
    if role=='PLANNING':
        # Preserve the original Planning C1 affine envelope, rather than silently
        # replacing it with Actual's nonlinear exact callback.
        lookup=coefficients.set_index(['aidc_id','slot'])
        p=np.array([[float(lookup.loc[(s,t),'slope'])*it[t,j]+float(lookup.loc[(s,t),'intercept_kw'])
                     for j,s in enumerate(sites)] for t in range(len(it))])
        return p,p*np.tan(np.arccos(power['PF_AIDC'])),it
    result=[]
    for t,row in enumerate(it):
        index=np.searchsorted(seconds,day['axis']['issue_seconds']+900*t,side='right')-1 if role=='ACTUAL' else t
        assert index>=0
        w=weather.iloc[index]
        result.append(module.exact_c1_pcc_kw(row,float(w['t_wb_c'] if role=='ACTUAL' else w['wetbulb_c']),float(w['rh_pct']),pars))
    p=np.array(result);q=p*np.tan(np.arccos(power['PF_AIDC']))
    return p,q,it


def prepare():
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    byuid={r['job_uid']:r for r in native['known_population']};bywindow={r['job_id']:r for r in windows}
    archive=read(Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/ARCHIVED_RESULTS_20250501_14.json'))['days'][0]
    z=zipfile.ZipFile(archive['archive'])
    prefix='2025-05-01/B1/attempt001/A1/AIDC_FROZEN/'
    rb=z.read(prefix+'AIDC_REFERENCE.json');ref=json.loads(rb)
    pb=z.read(prefix+'PLANNING_PHYSICAL.npz');plan=np.load(io.BytesIO(pb))
    assert ref['identity']['input']['sha256']==day['files']['native']['sha256']
    assert ref['identity']['windows']['sha256']==day['files']['windows']['sha256']
    assert sha(pb)==ref['identity']['physical']['sha256'] and ref['identity']['FULL_feasible'] and ref['identity']['PASS']
    known=np.zeros((120,12));sites=list(map(str,plan['sites']));duration_error=0;wan_rows=0
    nominal_gpuh=0
    legacy_window_violations=[]
    for uid,r in ref['selected_jobs'].items():
        j=byuid[uid];w=bywindow[uid]
        if r['start'] not in w['allowed_starts']:legacy_window_violations.append(uid)
        assert r['initial_site'] in native['capacities']
        duration=sum(e-b for s,b,e in r['segments'])
        duration_error=max(duration_error,abs(duration-j['service_slots']))
        for s,b,e in r['segments']:
            known[max(0,int(b)):min(120,int(e)),sites.index(s)]+=j['GPU_gang']
        nominal_gpuh+=j['GPU_gang']*duration*.25
        wan_rows+=len(r['wan'])
        assert r['checkpoint']==-1 and r['destination']==''
    assert duration_error==0 and np.array_equal(known[24:],plan['known_gpu']) and wan_rows==0
    assert np.all(plan['GPU']<=np.array([native['capacities'][s] for s in sites])+1e-8)
    sourcefolder=DOC/'source/aidc_pilot';sourcefolder.mkdir(exist_ok=True)
    (sourcefolder/'PLANNING_REFERENCE.json').write_bytes(rb)
    (sourcefolder/'PLANNING_PHYSICAL.npz').write_bytes(pb)
    save('LEGACY_AIDC_PLANNING_CANDIDATE_REJECTION.json',dict(status='REJECTED_NOT_USED',
        reason='Legacy accepted schedule violates freshly bound original WINDOWS allowed-start sets',
        allowed_start_violation_jobs=len(legacy_window_violations),example_UIDs=legacy_window_violations[:20],
        input_and_windows_receipt_match=True,modified_or_relaxed=False))
    # Legacy accepted Actual execution is screened independently, not assumed QoS feasible.
    legacy=json.loads(z.read('2025-05-01/B1/attempt002/ACTUAL/C1/ACTUAL_EVENT_LEDGERS.json'))
    legacy_excess=[r for r in legacy['qos_ledger'] if r['total_intentional_burden_seconds']>r['budget_seconds']+1e-6]
    save('LEGACY_AIDC_ACTUAL_CANDIDATE_REJECTION.json',dict(status='REJECTED_NOT_USED',
        reason='Independent QoS burden audit found source legacy accepted Actual trace exceeds original budgets',
        intentional_budget_excess_jobs=len(legacy_excess),
        maximum_intentional_budget_excess_s=max((r['total_intentional_burden_seconds']-r['budget_seconds'] for r in legacy_excess),default=0),
        legacy_ACCEPTED_does_not_prove_all_QoS=True,modified_or_relaxed=False))
    base=np.load(Path('D:/smartds_gso_substation2_v44_r043_runtime/jobs/ACTUAL_PHYSICAL.npz'))
    led=read(Path('D:/smartds_gso_substation2_v44_r043_runtime/jobs/EVENT_LEDGERS.json'))
    assert not led['migration_receipts'] and not any(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-6 for r in led['qos_ledger'])
    gpu=base['GPU'].copy();original_gpu=gpu.copy();begin=day['axis']['issue_seconds']
    events=led['job_event_ledger'];start={r['uid']:r for r in events if r['event']=='RUNNING'}
    release={r['uid']:r for r in events if r['event']=='GPU_RELEASE_CONTROL'}
    completion={r['uid']:r for r in events if r['event']=='COMPLETION_OBSERVED'}
    # At most one original known, single-GPU, same-site job per site. Only four
    # finite delay choices, inside original authority and complete rebound horizon.
    b0=read(DOC/'B0_CASE_SUMMARIES.json')['1.50']['ACTUAL']
    peak=b0['peak_slot']+24
    chosen=[];used=set()
    for uid in sorted(start):
        if uid not in byuid or uid not in release or uid not in completion:continue
        j=byuid[uid]
        if j['GPU_gang']!=1 or uid not in bywindow or not bywindow[uid]['can_timeshift']:continue
        s=start[uid]['site'];b=int(round((start[uid]['time_seconds']-begin)/900));end=int(round((release[uid]['time_seconds']-begin)/900))
        if s in used or not (24<=b<120 and b<=peak<end):continue
        budget=led['qos_budget_ledger'][uid];current=next(r for r in led['qos_ledger'] if r['uid']==uid)
        for delay in (1,2,3,4):
            if not b<=peak<b+delay:continue
            newstart=start[uid]['time_seconds']+delay*900
            if end+delay>120 or b+delay not in bywindow[uid]['allowed_starts']:continue
            if newstart>budget['latest_start_seconds']+1e-6:continue
            if current['total_intentional_burden_seconds']+delay*900>budget['budget_seconds']+1e-6:continue
            deadline=budget['hard_contract'].get('completion_deadline_seconds')
            if deadline is not None and completion[uid]['time_seconds']+delay*900>deadline:continue
            trial=gpu.copy();k=sites.index(s);trial[b:end,k]-=1;trial[b+delay:end+delay,k]+=1
            if np.min(trial)<-1e-8 or np.any(trial>np.array([native['capacities'][s] for s in sites])+1e-8):continue
            gpu=trial;used.add(s)
            chosen.append(dict(uid=uid,site=s,start_slot=b,release_slot=end,delay_slots=delay,
                GPU=1,compute_seconds_preserved=True,known_allowed_start=True,
                original_budget_seconds=budget['budget_seconds'],added_intentional_seconds=delay*900,
                migration=False,WAN_bytes=0,offline_realized_duration_witness=True))
            break
    peak_only_actual_count=len(chosen)
    if not chosen:
        save('G3_AIDC_WITNESS_SCOPE_AMENDMENT.json',dict(
            reason='No nonzero peak-overlap witness among finite one-GPU/same-site delays; try a deterministic day-wide feasibility witness',
            scope='at most one Job per site; UID lexical order; delay1/2/3/4; same original allowed starts/QoS/deadline/capacity/service/WAN constraints',
            AC_performance_used_to_select_jobs=False,source_constraints_relaxed=False))
        for uid in sorted(start):
            if uid not in byuid or uid not in release or uid not in completion:continue
            j=byuid[uid]
            if j['GPU_gang']!=1 or uid not in bywindow or not bywindow[uid]['can_timeshift']:continue
            site=start[uid]['site'];b=int(round((start[uid]['time_seconds']-begin)/900));end=int(round((release[uid]['time_seconds']-begin)/900))
            if site in used or not 24<=b<end<120:continue
            budget=led['qos_budget_ledger'][uid];current=next(r for r in led['qos_ledger'] if r['uid']==uid)
            for delay in (1,2,3,4):
                newstart=start[uid]['time_seconds']+delay*900
                if end+delay>120 or b+delay not in bywindow[uid]['allowed_starts']:continue
                if newstart>budget['latest_start_seconds']+1e-6 or current['total_intentional_burden_seconds']+delay*900>budget['budget_seconds']+1e-6:continue
                deadline=budget['hard_contract'].get('completion_deadline_seconds')
                if deadline is not None and completion[uid]['time_seconds']+delay*900>deadline:continue
                trial=gpu.copy();k=sites.index(site);trial[b:end,k]-=1;trial[b+delay:end+delay,k]+=1
                if np.min(trial)<-1e-8 or np.any(trial>np.array([native['capacities'][s] for s in sites])+1e-8):continue
                gpu=trial;used.add(site)
                chosen.append(dict(uid=uid,site=site,start_slot=b,release_slot=end,delay_slots=delay,GPU=1,
                    compute_seconds_preserved=True,known_allowed_start=True,original_budget_seconds=budget['budget_seconds'],
                    added_intentional_seconds=delay*900,migration=False,WAN_bytes=0,offline_realized_duration_witness=True,
                    scope='DAY_WIDE_AFTER_NO_PEAK_WITNESS'))
                break
    baseline_p,baseline_q,baseline_it=actual_c1(original_gpu,sites,day)
    baseline_error=float(np.max(abs(baseline_p-base['PCC_P_kw'])))
    assert baseline_error<1e-7,('Original C1/as-of weather reproduction failed',baseline_error)
    p,q,it=actual_c1(gpu,sites,day)
    assert np.array_equal(gpu.sum(axis=0),original_gpu.sum(axis=0))
    frozen=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')
    assert np.array_equal(base['PCC_P_kw'],frozen['ACTUAL_AIDC_P_kw'])
    # Build the Planning witness from the original B0 reference, not the rejected
    # legacy optimized schedule. Same bounded, same-site, one-GPU delays only.
    b0ref=json.loads(z.read('campaign_support/references/2025-05-01/AIDC_REFERENCE.json'))
    b0plan=np.load(io.BytesIO(z.read('campaign_support/references/2025-05-01/PLANNING_PHYSICAL.npz')))
    assert np.array_equal(b0plan['PCC_P_kw'],frozen['PLANNING_AIDC_P_kw'])
    pgpu=b0plan['GPU'].copy();planning_chosen=[];planning_used=set()
    ppeak=read(DOC/'B0_CASE_SUMMARIES.json')['1.50']['PLANNING']['peak_slot']+24
    for uid,r in sorted(b0ref['selected_jobs'].items()):
        j=byuid[uid];w=bywindow[uid]
        if j['GPU_gang']!=1 or not w['can_timeshift'] or len(r['segments'])!=1:continue
        site,b,end=r['segments'][0]
        if site in planning_used or not 24<=b<=ppeak<end:continue
        for delay in (1,2,3,4):
            if not b<=ppeak<b+delay or end+delay>120 or b+delay not in w['allowed_starts']:continue
            trial=pgpu.copy();k=sites.index(site)
            trial[b-24:end-24,k]-=1;trial[b+delay-24:end+delay-24,k]+=1
            if np.min(trial)<-1e-8 or np.any(trial>np.array([native['capacities'][s] for s in sites])+1e-8):continue
            pgpu=trial;planning_used.add(site)
            planning_chosen.append(dict(uid=uid,site=site,start_slot=b,release_slot=end,delay_slots=delay,
                GPU=1,known_allowed_start=True,service_slots_preserved=True,WAN_bytes=0))
            break
    peak_only_planning_count=len(planning_chosen)
    if not planning_chosen:
        for uid,r in sorted(b0ref['selected_jobs'].items()):
            j=byuid[uid];w=bywindow[uid]
            if j['GPU_gang']!=1 or not w['can_timeshift'] or len(r['segments'])!=1:continue
            site,b,end=r['segments'][0]
            if site in planning_used or not 24<=b<end<120:continue
            for delay in (1,2,3,4):
                if end+delay>120 or b+delay not in w['allowed_starts']:continue
                trial=pgpu.copy();k=sites.index(site);trial[b-24:end-24,k]-=1;trial[b+delay-24:end+delay-24,k]+=1
                if np.min(trial)<-1e-8 or np.any(trial>np.array([native['capacities'][s] for s in sites])+1e-8):continue
                pgpu=trial;planning_used.add(site)
                planning_chosen.append(dict(uid=uid,site=site,start_slot=b,release_slot=end,delay_slots=delay,GPU=1,
                    known_allowed_start=True,service_slots_preserved=True,WAN_bytes=0,scope='DAY_WIDE_AFTER_NO_PEAK_WITNESS'))
                break
    planbase_p,_,_=actual_c1(b0plan['GPU'],sites,day,'PLANNING')
    plan_error=float(np.max(abs(planbase_p-frozen['PLANNING_AIDC_P_kw'])))
    assert plan_error<1e-7,('Planning original C1/forecast reproduction failed',plan_error)
    pp,pq,pit=actual_c1(pgpu,sites,day,'PLANNING')
    assert np.array_equal(pgpu.sum(axis=0),b0plan['GPU'].sum(axis=0))
    arrays=dict(PLANNING_P=pp,PLANNING_Q=pq,ACTUAL_P=p,ACTUAL_Q=q,
        ACTUAL_GPU=gpu,ACTUAL_delta_GPU=gpu-original_gpu)
    out=RUNTIME/'phase2/AIDC_FEASIBLE_CANDIDATE.npz';np.savez_compressed(out,**arrays)
    save('AIDC_FEASIBLE_CANDIDATE_AUDIT.json',dict(status='PASS_LIMITED_WITNESSES' if chosen or planning_chosen else 'NO_NONZERO_WITNESS',
        source='bounded same-site source-authorized delays of original B0 reference/FCFS, not an IEEE8500 B1 result',
        archive_verification_reused=archive['verification'],archive_path=archive['archive'],
        planning_physical_sha256=sha(pb),planning_known_jobs=len(ref['selected_jobs']),
        planning_nominal_GPUh=nominal_gpuh,planning_duration_error_slots=duration_error,
        planning_known_GPU_reproduction_exact=True,planning_WAN_transfers=wan_rows,
        legacy_planning_allowed_start_violations=len(legacy_window_violations),legacy_planning_candidate_used=False,
        planning_job_changes=planning_chosen,planning_GPUh_change=float((pgpu-b0plan['GPU']).sum()*.25),
        peak_only_planning_witness_count=peak_only_planning_count,peak_only_actual_witness_count=peak_only_actual_count,
        planning_baseline_C1_reproduction_error_kw=plan_error,
        planning_power_contract='Original frozen affine C1 Planning coefficients; Actual uses original exact C1 with as-of observed weather',
        actual_baseline_source='PR235 independent original FCFS replay',
        actual_baseline_qos_budget_violations=0,actual_baseline_C1_reproduction_error_kw=baseline_error,
        actual_job_changes=chosen,actual_GPUh_change=float((gpu-original_gpu).sum()*.25),
        actual_migration_count=0,actual_WAN_bytes=0,actual_capacity_violations=0,
        actual_peak_flexible_kw_observed=float(np.maximum(frozen['ACTUAL_AIDC_P_kw'][peak]-p[peak],0).sum()),
        actual_max_site_power_reduction_kw=float(np.max(frozen['ACTUAL_AIDC_P_kw']-p)),
        actual_max_site_rebound_kw=float(np.max(p-frozen['ACTUAL_AIDC_P_kw'])),
        candidate_path=str(out),candidate_sha256=sha(out.read_bytes()),
        diagnostic_only=True,new_solver_calls=0,new_causal_optimization_claim=False,
        limited_witness_not_maximum_job_flexibility=True))
    return arrays


if __name__=='__main__':
    assert read(DOC/'PREFLIGHT_GATES.json')['G2']['status']=='COMPLETE'
    prepare()
