"""Materialize and audit only May-04 before electrical generation."""
from pathlib import Path
from decimal import Decimal
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,write_npz,digest
from dayahead.v41.preflight import record
from dayahead.v41.persistence import table
from .authority import ROOT,OLD,OLD_RUN,OUT,CAP,RACK,DAY,VECTOR,OLD_VECTOR,SITES,capacity,snapshot,aggregate_it

def json(name,value):write_json(OUT/name,value)
def stats(jobs,cap):
    from dayahead.v40g_segments.canonical import occupancy,import_frozen
    gpu,_=occupancy(import_frozen(jobs),SITES);caps=np.array(cap)
    pending=[r for r in jobs if r['state_at_issue']=='PENDING'];assigned=[r for r in jobs if r['AIDC_site'] in SITES]
    wait=np.array([r['start_slot']/4 for r in pending if r['AIDC_site'] in SITES])
    return dict(job_count=len(jobs),RUNNING_count=sum(r['state_at_issue']=='RUNNING' for r in jobs),PENDING_count=len(pending),
        D00_RUNNING=sum(r['start_slot']<=24<r['end_slot'] for r in assigned),
        D_day_starts=sum(24<=r['start_slot']<120 for r in assigned),still_queued_at_H=sum(r['start_slot']>=120 for r in pending),
        D24_carryout=sum(r['start_slot']<120<r['end_slot'] for r in assigned),
        true_cross_H_GPUh=sum(max(0,r['end_slot']-120)*r['requested_GPU']/4 for r in assigned if r['start_slot']<120<r['end_slot']),
        UNASSIGNED_count=sum(r['AIDC_site']=='UNASSIGNED' for r in jobs),
        UNASSIGNED_Dday_count=sum(r['AIDC_site']=='UNASSIGNED' and max(24,r['start_slot'])<min(120,r['end_slot']) for r in jobs),
        capacity_wait_hours=dict(mean=float(wait.mean()),P50=float(np.quantile(wait,.5)),P90=float(np.quantile(wait,.9)),P95=float(np.quantile(wait,.95))),
        natural_delay_hours=0,waiting_origin='D-1 issue slot0; old stored starts are resource-delay outputs',
        scheduled_GPUh=float(gpu.sum()/4),mean_occupancy=float(gpu.sum(1).mean()/caps.sum()),
        FULL_fraction=float(np.mean(gpu==caps)),all_12_FULL_fraction=float(np.mean(np.all(gpu==caps,axis=1))),
        per_site={s:dict(mean_occupancy=float((gpu[:,i]/caps[i]).mean()),FULL_fraction=float((gpu[:,i]==caps[i]).mean()),mean_headroom_GPU=float((caps[i]-gpu[:,i]).mean())) for i,s in enumerate(SITES)}),gpu

def run():
    from dayahead.v41.common import build
    from dayahead.v41.data import RUNTIME
    cap,_=capacity();path,_=snapshot(DAY)
    jobs,seal=build(DAY,path,cap)
    # Rebuild from the causal source, separately; compare full job bytes.
    second,seal2=build(DAY,path,cap,folder_override=OUT/'repro_reference')
    assert jobs==second
    json('V41R2_REFERENCE_REPRODUCIBILITY.json',dict(status='PASS',first=seal['files']['COMMON_B0_REFERENCE_JOBS.json'],second=seal2['files']['COMMON_B0_REFERENCE_JOBS.json'],
        exact_job_content_equal=True,capacity_authority=record(CAP),source_state='D-1 18:00',old_B0_reused=False))
    oldjobs=read(OLD_RUN/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
    oldstats,oldgpu=stats(oldjobs,OLD_VECTOR);newstats,gpu=stats(jobs,VECTOR)
    before={r['job_uid']:r for r in oldjobs}
    changes=[dict(job_id=r['job_uid'],state_at_issue=r['state_at_issue'],old_start=before[r['job_uid']]['start_slot'],new_start=r['start_slot'],
        old_site=before[r['job_uid']]['AIDC_site'],new_site=r['AIDC_site'],GPU=r['requested_GPU'],end=r['end_slot'],duration=r['safe_duration_slots']) for r in jobs]
    table(OUT/'V41R2_REFERENCE_JOB_COMPARISON.parquet',pd.DataFrame(changes))
    json('V41R2_REFERENCE_SCHEDULING_COMPARISON.json',dict(status='PASS',old=oldstats,new=newstats,
        changed_start_count=sum(r['old_start']!=r['new_start'] for r in changes),changed_initial_site_count=sum(r['old_site']!=r['new_site'] for r in changes),
        capacity_tuned_using_P1_P2=False,old_result_role='HISTORICAL_COMPARISON_ONLY'))
    from dayahead.v39a.contracts import C_REF_W_PER_GPU,CENTER_SWING_W_PER_GPU,IDLE_W_PER_GPU,POWER_TOLERANCE_KW
    from dayahead.v39a.power import site_it_power_kw,validate_power_conservation
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY,PF_TAN
    assert IDLE_W_PER_GPU>0 and C_REF_W_PER_GPU>IDLE_W_PER_GPU
    lineage=Path('D:/codex_mobileess_workspace/MobileESS_v35r3j_aidc_scale_freeze/dayahead/artifacts/v35r3j_aidc_it_scale_consistency_freeze')
    origins=[lineage/n for n in ['V35R3J_FROZEN_IT_REFERENCE_LINEAGE.json','V35R3J_EXPANDED_AIDC_POWER_CONTRACT.json','V35R3J_SCALE_METHOD_DECISION.json']]
    ref=read(origins[0]); expanded=read(origins[2])
    assert abs(Decimal(str(ref['c_ref_W_per_requested_GPU']))-C_REF_W_PER_GPU)<Decimal('0.00000000001')
    c1path=ROOT/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'
    wp=day_root(SOURCE_DATA_REPOSITORY,DAY)/'gfs_d1_weather.parquet';weather=pd.read_parquet(wp);c1=load_c1(c1path)
    def trajectory(load,caps):
        it=np.array([[float(site_it_power_kw(caps[i],int(load[t,i]))) for i in range(12)] for t in range(96)])
        p=np.array([exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),c1) for t,w in enumerate(weather.itertuples())])
        return it,p,p*PF_TAN
    it,pcc,qcc=trajectory(gpu,VECTOR);oldit,oldp,oldq=trajectory(oldgpu,OLD_VECTOR)
    audits=[validate_power_conservation(dict(zip(SITES,VECTOR)),dict(zip(SITES,map(int,row)))) for row in gpu]
    assert all(a['status']=='PASS' for a in audits)
    idle=np.tile(np.array(VECTOR)*float(IDLE_W_PER_GPU)/1000,(96,1));active=gpu*float(CENTER_SWING_W_PER_GPU)/1000
    arrays=dict(gpu=gpu,it=it,pcc=pcc,qcc=qcc,capacity_component=idle,active_component=active,aggregate_it=it.sum(1))
    write_npz(OUT/'V41R2_B0_IT_PCC.npz',**arrays)
    table(OUT/'V41R2_B0_SITE_POWER.parquet',pd.DataFrame([dict(site=s,slot=t,GPU=int(gpu[t,i]),capacity=VECTOR[i],IT_kW=it[t,i],idle_kW=idle[t,i],active_kW=active[t,i],
        PCC_kW=pcc[t,i],PCC_kvar=qcc[t,i],PUE=pcc[t,i]/it[t,i],thermal_other_kW=pcc[t,i]-it[t,i],wetbulb_C=float(weather.iloc[t].t_wb_c),RH_pct=float(weather.iloc[t].rh_pct),
        old_IT_kW=oldit[t,i],old_PCC_kW=oldp[t,i],old_PCC_kvar=oldq[t,i]) for t in range(96) for i,s in enumerate(SITES)]))
    pmax=trajectory(np.tile(VECTOR,(96,1)),VECTOR)[1];site_rows=[]
    # Exact unchanged dedicated-site ratings are also verified against generated arrays after generation.
    oldcert=read(OLD_RUN/'e/20250504/V41_ELECTRICAL_CERTIFICATE.json')
    with np.load(oldcert['outputs']['transformer_coefficients']['path']) as z:
        assert 500. in z['ratings']
    for i,s in enumerate(SITES):
        kva=np.hypot(pcc[:,i],qcc[:,i]);worst=int(kva.argmax());max_install=pmax[:,i]/.95
        site_rows.append(dict(site=s,max_P_kW=float(pcc[:,i].max()),max_Q_kvar=float(qcc[:,i].max()),max_kVA=float(kva.max()),
            slot=worst,transformer_rating_kVA=1500,utilization=float(kva.max()/1500),violation_count=int((kva>1500).sum()),
            full_installation_max_kVA=float(max_install.max()),full_installation_utilization=float(max_install.max()/1500)))
    tx=dict(status='PASS' if all(r['full_installation_max_kVA']<=1500 for r in site_rows) else 'FAIL',sites=site_rows,
        unchanged_rating_source=oldcert['outputs']['transformer_coefficients'],no_automatic_uprating=True)
    json('V41R2_PCC_TRANSFORMER_CAPABILITY.json',tx);assert tx['status']=='PASS',tx
    power=dict(status='PASS',source_proof=[record(p) for p in origins]+[record(OLD/'dayahead/v39a/contracts.py'),record(OLD/'dayahead/v39a/power.py')],
        interpretation='V35R3J derives c_ref in W per requested GPU from the historical aggregate/624. V39A explicitly freezes c_ref and CENTER and decomposes installed idle plus active swing. V41R2 retains those per-GPU values; its enlarged aggregate is derived.',
        c_ref_W_per_GPU=str(C_REF_W_PER_GPU),d_CENTER_W_per_GPU=str(CENTER_SWING_W_PER_GPU),p_idle_eq_W_per_GPU=str(IDLE_W_PER_GPU),
        old_full_active_IT_kW=str(aggregate_it(624,624)),new_full_active_IT_kW=str(aggregate_it(780,780)),
        old_idle_IT_kW=str(aggregate_it(0,624)),new_idle_IT_kW=str(aggregate_it(0,780)),
        old_mean_active_IT_kW=float((oldgpu*float(CENTER_SWING_W_PER_GPU)/1000).sum(1).mean()),new_mean_active_IT_kW=float(active.sum(1).mean()),
        invalid_formula_replaced='Legacy aggregate_it_power_kw assumed fixed 624; now installed-capacity parameter controls the aggregate',
        no_measured_facility_claim=True,conservation_tolerance_kW=str(POWER_TOLERANCE_KW),max_conservation_residual_kW=max(a['absolute_error_kW'] for a in audits),
        C1=record(c1path),weather=record(wp),PF=.95,PF_tan=PF_TAN,capacity=record(CAP),trajectory=record(OUT/'V41R2_B0_IT_PCC.npz'))
    json('V41R2_AIDC_POWER_CAPACITY_REBASE_AUDIT.json',power)
    text=f"# V41R2 AIDC power capacity rebase\n\n{power['interpretation']}\n\nFrozen per GPU: c_ref={C_REF_W_PER_GPU} W; CENTER={CENTER_SWING_W_PER_GPU} W; equivalent idle={IDLE_W_PER_GPU} W.\n\nFull active aggregate: {power['old_full_active_IT_kW']} → {power['new_full_active_IT_kW']} kW. Installed idle: {power['old_idle_IT_kW']} → {power['new_idle_IT_kW']} kW.\n\nThe legacy fixed-624 aggregate formula is invalid for 780 and is replaced with the sum of installed idle and active swing. C1, weather, PF and site hosts are frozen. Conservation passes at {POWER_TOLERANCE_KW} kW tolerance. These are synthetic equivalent-GPU powers, with no measured-facility claim.\n"
    (OUT/'V41R2_AIDC_POWER_CAPACITY_REBASE_AUDIT.md').write_text(text,encoding='utf-8')
    dependencies=dict(status='AUDITED_REGEN_PENDING',scope=DAY,capacity_authority=record(CAP),AIDC_PCC_trajectory=record(OUT/'V41R2_B0_IT_PCC.npz'),
        historical_certificate=record(OLD_RUN/'e/20250504/V41_ELECTRICAL_CERTIFICATE.json'),
        families={
        'A_C1_IT_to_PCC':dict(classification='PARTIAL_REGEN_REQUIRED',reason='Frozen nonlinear C1 parameters and weather unchanged; capacity-dependent GPU-to-IT/PCC lookup domain and trajectories rebuilt',sources=[record(c1path),record(ROOT/'dayahead/v40e/electrical.py')]),
        'B_Planning_voltage':dict(classification='REGENERATE_REQUIRED',reason='AC base V and AIDC gradients depend on the operating point. Frozen April MESS joint gradients remain; intercept is reanchored.',sources=[oldcert['outputs']['voltage']]),
        'C_Phase_line_current':dict(classification='REGENERATE_REQUIRED',reason='AC current constant and sensitivity linearized at the AIDC PCC anchor',sources=[oldcert['outputs']['current']]),
        'D_Transformer_current_kVA':dict(classification='PARTIAL_REGEN_REQUIRED',reason='Current constants/sensitivities relinearized. Lossless P/Q flow mapping and physical ratings depend on topology/phase only and require exact numerical equality.',sources=[oldcert['outputs']['transformer_coefficients']]),
        'E_Operating_point':dict(classification='REGENERATE_REQUIRED',reason='Anchor changed to newly materialized 780 B0 PCC; all May-04 anchor descendants regenerated',sources=[record(OUT/'V41R2_B0_IT_PCC.npz')])},
        regeneration='May-04 full AC coefficient regeneration; no other days',no_duplicate_mapper=record(ROOT/'dayahead/v40e/mapping.py'),
        source_graph=[record(ROOT/p) for p in ['dayahead/v40i/electrical.py','dayahead/v40e/electrical.py','dayahead/v28r2/electrical_subproblem.py','dayahead/v41/electrical.py']])
    json('V41R2_ELECTRICAL_COEFFICIENT_DEPENDENCY_AUDIT.json',dependencies)
    print('PREPARE_PASS',oldstats['mean_occupancy'],newstats['mean_occupancy'],oldstats['all_12_FULL_fraction'],newstats['all_12_FULL_fraction'],flush=True)

if __name__=='__main__':run()
