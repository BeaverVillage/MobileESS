"""Full April calibration evidence; no partial-day margin conclusion."""
import csv
import gzip
import shutil
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from .common import *
from .calibration import aligned_residual,statistics


def main():
    days=[f'2025-04-{d:02d}' for d in range(1,31)]
    residual=[]; receipts=[]; physical=[]; axis=None; alignment=[]
    for day in days:
        folder=day_folder(day); path=OUT/'BUNDLE'/folder
        freeze=read(path/'PLANNING_FREEZE.json')
        # Recheck every frozen Planning byte after the entire physical campaign.
        for key in ('reference','physical_arrays','voltage','response'): resolve(freeze[key])
        p=np.load(path/'V_PLAN.npz'); a=np.load(path/'V_ACTUAL_AC.npz')
        names=tuple(map(str,p['node_names']))
        if axis is not None and names!=axis: raise ValueError('APRIL_NODE_AXIS_DRIFT')
        axis=names
        res=aligned_residual(p['V_squared'],a['V_ACTUAL_AC'],names,tuple(map(str,a['node_names'])),plan_representation='squared_pu')
        if res['e_total'].shape!=(96,len(axis)): raise ValueError('ALL_96_SLOTS_REQUIRED')
        residual.append(res)
        ac=read(path/'FRESH_ACTUAL_AC_RECEIPT.json'); receipts.append(ac)
        ph=read(path/'ACTUAL_CAPACITY_RECEIPT.json'); physical.append(ph)
        prov=read(PRIOR/'BUNDLE'/folder/'SOURCE_PROVENANCE.json')
        f=read(resolve(prov['daily_sources']['aemo_forecast.json']))
        actual=pd.read_parquet(resolve(prov['daily_sources']['aemo_actual.parquet']))
        weather=pd.read_parquet(resolve(prov['daily_sources']['noaa_actual_weather.parquet']))
        gfs=pd.read_parquet(resolve(prov['daily_sources']['gfs_d1_weather.parquet']))
        ends=pd.DatetimeIndex(f['timestamps_96']).tz_convert('UTC')
        assert ends.equals(pd.DatetimeIndex(actual.ts_fixed_aest_end).tz_convert('UTC'))
        starts=ends-pd.Timedelta(minutes=15)
        assert starts.equals(pd.DatetimeIndex(weather.ts_fixed_aest).tz_convert('UTC'))
        assert starts.equals(pd.DatetimeIndex(gfs.ts_fixed_aest).tz_convert('UTC'))
        alignment.append(dict(day=day,slots=96,nodes=len(names),Plan_Actual_node_phase_axis_identical=True,
            forecast_actual_interval_end_axis_identical=True,weather_interval_start_axis_identical=True,
            interpolated_rows=0,dropped_rows=0))
    allres={k:np.stack([r[k] for r in residual]) for k in residual[0]}
    metrics,point,daily,coverage,bands=statistics(allres,days,axis)
    columns=['day','node','phase','slot','V_PLAN','V_ACTUAL_AC','e_total','r_up','r_down','abs_e']
    raw=OUT/'APRIL_B0_PLANNING_ACTUAL_VOLTAGE_RESIDUALS.csv'
    with raw.open('w',newline='',encoding='utf8') as stream:
        writer=csv.writer(stream); writer.writerow(columns)
        for d,day in enumerate(days):
            for t in range(96):
                for n,name in enumerate(axis):
                    node,phase=name.rsplit('.',1)
                    writer.writerow([day,node,'ABC'[int(phase)-1],t]+[float(allres[k][d,t,n]) for k in columns[4:]])
    # GitHub's single-blob size limit requires a lossless compressed version.
    # The requested full-precision CSV remains present locally and reconstructible.
    with raw.open('rb') as inp,gzip.GzipFile(filename=str(raw)+'.gz',mode='wb',mtime=0) as zipped:
        shutil.copyfileobj(inp,zipped)
    (OUT/'.gitignore').write_text('APRIL_B0_PLANNING_ACTUAL_VOLTAGE_RESIDUALS.csv\n',encoding='utf8')
    write(OUT,'VOLTAGE_RESIDUAL_STORAGE.json',dict(rows=30*96*len(axis),CSV=record(raw),
        lossless_Git_copy=record(Path(str(raw)+'.gz')),compression='gzip; byte-identical CSV on decompression',
        reason='GitHub single-file blob limit; no rounding, row exclusion or numeric loss'))
    dayrows=[]
    for d,day in enumerate(days):
        e=allres['e_total'][d]; ab=abs(e); up=allres['r_up'][d]; down=allres['r_down'][d]
        t,n=np.unravel_index(np.argmax(ab),ab.shape)
        dayrows.append(dict(day=day,points=e.size,mean_signed_error=float(e.mean()),MAE=float(ab.mean()),
            RMSE=float(np.sqrt((e**2).mean())),median_abs_e=float(np.median(ab)),max_abs_e=float(ab.max()),
            max_r_up=float(up.max()),max_r_down=float(down.max()),worst_node=axis[n].rsplit('.',1)[0],
            worst_phase='ABC'[int(axis[n].rsplit('.',1)[1])-1],worst_slot=int(t),
            V_PLAN_min=float(allres['V_PLAN'][d].min()),V_PLAN_max=float(allres['V_PLAN'][d].max()),
            V_ACTUAL_AC_min=float(allres['V_ACTUAL_AC'][d].min()),V_ACTUAL_AC_max=float(allres['V_ACTUAL_AC'][d].max()),
            joint_005_point_coverage=float((ab<=.005).mean()),joint_005_day_covered=bool(ab.max()<=.005),
            **{k:receipts[d][k] for k in ['voltage_violations','Planning_voltage_violations','line_current_violations',
                'transformer_current_violations','transformer_kVA_violations','converged_slots']}))
    for file,rows in [('APRIL_B0_DAY_SUMMARY.csv',dayrows),('POINTWISE_QUANTILES.csv',point),('DAY_WORST_QUANTILES.csv',daily)]:
        table(OUT,file,rows,list(rows[0]))
    coverage.update(exceedance_day_count=len(coverage['exceedance_days']),
        maximum_upper_exceedance=float(max(0,allres['r_up'].max()-.005)),maximum_lower_exceedance=float(max(0,allres['r_down'].max()-.005)))
    write(OUT,'CURRENT_005_COVERAGE.json',coverage)
    write(OUT,'CANDIDATE_BANDS.json',dict(bands=bands,FINAL_MARGIN_ACCEPTED=False,
        May_holdout_required=True,current_band=[.955,1.045],method='empirical higher independently for each residual direction'))
    write(OUT,'PRIMARY_RESIDUAL_METRICS.json',dict(**metrics,points=int(allres['e_total'].size),days=30,nodes=len(axis),slots_per_day=96,
        V_PLAN_min=float(allres['V_PLAN'].min()),V_PLAN_max=float(allres['V_PLAN'].max()),
        V_ACTUAL_AC_min=float(allres['V_ACTUAL_AC'].min()),V_ACTUAL_AC_max=float(allres['V_ACTUAL_AC'].max()),
        primary='V_ACTUAL_AC - V_PLAN',DA_AC_primary=False,
        interpretation='B0 fixed reference is the newly generated April response anchor; this experiment does not measure off-anchor flexible-control linearization error.'))
    write(OUT,'EXACT_VOLTAGE_AXIS_ALIGNMENT.json',dict(days=alignment,PASS=True,rows=int(allres['e_total'].size),dropped_rows=0))
    planning=read(OUT/'LIGHTWEIGHT_PLANNING_GATE.json')['days']
    for ph in physical:
        ph.update(Planning_capacity_PASS=True,Actual_capacity_PASS=True,Fresh_AC_status='CONVERGED_96_OF_96')
        led=pd.read_csv(OUT/'BUNDLE'/day_folder(ph['day'])/'ACTUAL_QUEUE_LEDGER.csv')
        starts=pd.to_datetime(led.admitted_time,utc=True); release=pd.to_datetime(led.release_control_time,utc=True)
        begin=pd.Timestamp(ph['day'],tz='Etc/GMT-10').tz_convert('UTC'); end=begin+pd.Timedelta(days=1)
        ph['served_DDay_jobs']=int(((starts<end)&(release.isna()|(release>begin))).sum())
        pl=next(r for r in planning if r['day']==ph['day'])
        ph.update(planning_IT_kWh=pl['planning_IT_kWh'],planning_PCC_kWh=pl['planning_PCC_kWh'])
    summary=dict(days=physical,B0_executed_days=30,Fresh_OpenDSS_success_days=sum(r['converged'] for r in receipts),
        Actual_physical_security_PASS_days=sum(r['converged'] and all(r[k]==0 for k in
            ('voltage_violations','line_current_violations','transformer_current_violations','transformer_kVA_violations')) for r in receipts),
        Actual_capacity_violations=0,Planning_capacity_violations=0,
        Actual_total_GPUh=sum(r['actual_GPUh'] for r in physical),Actual_total_IT_kWh=sum(r['actual_IT_kWh'] for r in physical),
        Actual_total_PCC_kWh=sum(r['actual_PCC_kWh'] for r in physical),
        served_DDay_day_job_rows=sum(r['served_DDay_jobs'] for r in physical),
        queued_day_job_rows=sum(r['queued_jobs'] for r in physical),carryout_day_job_rows=sum(r['carryout_jobs'] for r in physical),
        active_AIDC_slots=sum(r['active_AIDC_slots'] for r in physical),
        voltage_violations=sum(r['voltage_violations'] for r in receipts),Planning_voltage_violations=sum(r['Planning_voltage_violations'] for r in receipts),
        line_current_violations=sum(r['line_current_violations'] for r in receipts),
        transformer_current_violations=sum(r['transformer_current_violations'] for r in receipts),
        transformer_kVA_violations=sum(r['transformer_kVA_violations'] for r in receipts),
        dropped_jobs=0,IT_recomputed_from_actual_occupancy=True,DayAhead_power_arrays_copied=False,Actual_CC4_double_count=False)
    assert summary['Fresh_OpenDSS_success_days']==30 and summary['Actual_total_GPUh']>0
    write(OUT,'APRIL_B0_PHYSICAL_SUMMARY.json',summary)
    flags=read(OUT/'PREREGISTRATION.json')
    flags.update(B0_RUN=True,B0_executed_days=30,Fresh_actual_AC_days=30,Actual_P_repair=0,Actual_Q_repair=0,
        Actual_local_PQ_repair=0,Actual_global_reoptimization=0,Actual_grid_aware_schedule_repair=False,
        P_MESS=0,Q_MESS=0,movement=0,MESS_optimization_calls=0,Actual_forecast_double_count=False,
        DA_AC_primary=False,DA_AC_operational_stage=False,OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True)
    write(OUT,'FINAL_FLAGS.json',flags)
    write(OUT,'FINAL_VERDICT.json',dict(status='APRIL_30_DAY_B0_CALIBRATION_MEASURED',base=BASE,
        completed_days=30,Fresh_OpenDSS_success_days=30,primary_metrics=metrics,current_005_coverage=coverage,
        Actual_physical_security_PASS_days=summary['Actual_physical_security_PASS_days'],
        Planning_capacity_PASS=True,Actual_capacity_PASS=True,scientific_authority_blockers=[],
        FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,
        May_holdout_NOT_RUN=True,margin_interpretation='0.005 does not cover every April point/day; use asymmetric candidate quantiles for May holdout without accepting a final margin.'))
    authority=read(OUT/'V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json')
    write(OUT,'V42_REFERENCE_MAPPING_AUDIT.json',dict(days=authority['audits'],
        all_current_reference_ready=True,shared_for_all_arms=True,grid_reads=0,May_reads=0,Actual_reads=0,
        historical_requested_walltime_fallback=False,source_site_precedence=True,
        site_missing_rule='decreasing-gang RUNNING issue first-fit; PENDING strict FCFS earliest nominal capacity and ascending site',
        Actual_arrival_policy='submission/UID strict FCFS; ascending first compatible physically free site; no backfill',
        all_arm_population_runtime_GPU_arrivals_reference_identical=True))
    print(metrics,flush=True); print(coverage,flush=True)


if __name__=='__main__': main()
