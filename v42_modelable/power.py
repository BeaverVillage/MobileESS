"""April-bound current C1 coefficients and fixed CC4 physical capacity preflight."""
from dataclasses import asdict
from pathlib import Path
import csv
import sys
import numpy as np
import pandas as pd
from v42_april_port.audit import read, checked, record, write, table
from .freeze import ROOT, OUT

def known_occupancy(rows, sites):
    gpu=np.zeros((96,len(sites)))
    for row in rows:
        if row['status']!='REFERENCE_ASSIGNED': raise ValueError('UNASSIGNED_PHYSICAL_REFERENCE')
        start=int(row['reference_start']); n=int(row['service_slots']); g=int(row['GPU_gang'])
        site=sites.index(row['reference_site'])
        if row.get('q50_expired_hard_occupancy'):
            gpu[:,site]+=g
        else:
            seconds=float(row['nominal_remaining_seconds'])
            for t in range(96):
                issue_slot=t+24
                active=max(0.,min(900.,seconds-(issue_slot-start)*900)) if issue_slot>=start else 0.
                gpu[t,site]+=g*active/900.
    return gpu

def allocate_unknown(known, unknown, capacities):
    """Fixed TRAIN execution profile, first site ID with spare capacity, no LP.

    Never clip/discard forecast occupancy or change its timing to force feasibility.
    Residual unallocated demand is an explicit physical construction failure.
    This is forecast power allocation, never an identified job reference schedule.
    """
    out=np.zeros_like(known); residual=np.array(unknown,float).copy()
    for t in range(96):
        for s,c in enumerate(capacities):
            take=min(residual[t],max(0.,c-known[t,s])); out[t,s]=take; residual[t]-=take
    return out,residual

def main():
    # Freeze the forecast-power mapping before querying feasibility diagnostics.
    rule_path=OUT/'BUNDLE/FORECAST_POWER_ALLOCATION_RULE.json'
    rule=dict(frozen=True,grid_blind=True,site_order='ascending AIDC ID',
        nominal_timing='unmodified current TRAIN execution-lag kernel',
        aggregate_GPUh_retiming=False,clipping=False,unknown_UIDs_created=False,
        anonymous_LP_schedule_promoted=False,known_reference_changed=False,
        reserve_is_realized_load=False)
    if rule_path.exists() and read(rule_path)!=rule: raise ValueError('ALLOCATION_RULE_DRIFT')
    write(OUT,'BUNDLE/FORECAST_POWER_ALLOCATION_RULE.json',rule)
    inherited=read(ROOT/'docs/v42_april_port_from_may_pipeline/MAY_PIPELINE/MAY_POWER_CONVERSION_AUDIT.json')
    sources=inherited['code_and_static_authority'] if 'code_and_static_authority' in inherited else None
    if sources is None:
        # Find the named source map without relying on an evidence-layout label.
        sources=next(v for v in inherited.values() if isinstance(v,dict) and 'power_C1' in v)
    c1path=checked(sources['power_C1']); checked(sources['power_per_GPU_constants']); modelpath=checked(sources['C1_model'])
    sys.path.insert(0,str(c1path.parents[2]))
    from dayahead.v28r2.c1_affine import load_c1, endpoint_secant
    from dayahead.v39a.contracts import IDLE_W_PER_GPU, CENTER_SWING_W_PER_GPU
    import dayahead.v28r2.c1_affine as module
    if Path(module.__file__).resolve()!=c1path.resolve(): raise ValueError('CURRENT_C1_IMPORT_IDENTITY')
    params=load_c1(modelpath); idle=float(IDLE_W_PER_GPU)/1000; swing=float(CENTER_SWING_W_PER_GPU)/1000
    audits=[]
    for d in range(1,31):
        day='2025-04-%02d'%d; folder='DAY_'+day.replace('-','')
        p=read(OUT/'BUNDLE'/folder/'PLANNING_INPUT_BUNDLE.json')
        prov=read(OUT/'BUNDLE'/folder/'SOURCE_PROVENANCE.json')
        wf=checked(prov['daily_sources']['gfs_d1_weather.parquet']); wa=checked(prov['daily_sources']['noaa_actual_weather.parquet'])
        weather=pd.read_parquet(wf); actual_weather=pd.read_parquet(wa)
        if len(weather)!=96 or len(actual_weather)!=96: raise ValueError('WEATHER_96_AXIS')
        sites=sorted(p['capacities']); caps=np.array([p['capacities'][s] for s in sites])
        rows=read(OUT/'REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json')['audits'][d-1]
        # Read all canonical known fields from the deterministic preflight rows,
        # preserving exact seconds and expired-RUNNING occupancy semantics.
        from v42_april_b0_v2.reference import build_reference
        refs,audit=build_reference(p['known_population'],p['capacities'],p['rack_compatibility'],issue_time=p['issue_time'])
        known=known_occupancy([r for r in refs if r['status']=='REFERENCE_ASSIGNED'],sites)
        unknown=np.array(p['forecast_inputs']['current_CC4']['nominal_unknown_GPU_96'])
        anon,residual=allocate_unknown(known,unknown,caps)
        coefficients=[]; cache={}
        for t in range(96):
            w=weather.iloc[t]
            for s,c in zip(sites,caps):
                key=(int(c),float(w.t_wb_c),float(w.rh_pct))
                if key not in cache:
                    cache[key]=endpoint_secant(s,t,idle*c,(idle+swing)*c,float(w.t_wb_c),float(w.rh_pct),params)
                coefficients.append(dict(asdict(cache[key]),aidc_id=s,slot=t))
        table(OUT,'BUNDLE/'+folder+'/C1_PLANNING_COEFFICIENTS.csv',coefficients,list(coefficients[0]))
        table(OUT,'BUNDLE/'+folder+'/FORECAST_OCCUPANCY_PREFLIGHT.csv',[
            dict(slot=t,known_GPU=float(known[t].sum()),CC4_nominal_GPU=float(unknown[t]),
                 total_required_GPU=float(known[t].sum()+unknown[t]),total_capacity_GPU=int(caps.sum()),
                 unallocated_CC4_GPU=float(residual[t]),capacity_feasible=bool(residual[t]<=1e-8)) for t in range(96)],
            ['slot','known_GPU','CC4_nominal_GPU','total_required_GPU','total_capacity_GPU','unallocated_CC4_GPU','capacity_feasible'])
        slots=np.flatnonzero(residual>1e-8).tolist()
        audits.append(dict(day=day,current_C1_date_bound=True,
            fixed_known_plus_CC4_power_constructible=not slots and audit['full_reference_ready'],infeasible_slots=slots,
            maximum_unallocated_GPU=float(residual.max()),maximum_required_GPU=float((known.sum(1)+unknown).max()),
            capacity_GPU=int(caps.sum()),known_reference_ready=audit['full_reference_ready'],
            assigned_known_only_lower_bound=not audit['full_reference_ready'],
            blocked_known_jobs=audit['blocked_jobs'],
            occupancy_forecast_profile_modified=False,reference_changed=False,
            voltage_results_read=False,Actual_results_read=False))
        write(OUT,'BUNDLE/'+folder+'/POWER_AUTHORITY.json',dict(current_IT_idle_kW_per_installed_GPU=idle,
            current_IT_swing_kW_per_active_GPU=swing,C1=record(modelpath),C1_implementation=record(c1path),
            GFS=record(wf),NOAA=record(wa),planning_C1=record(OUT/'BUNDLE'/folder/'C1_PLANNING_COEFFICIENTS.csv'),
            exact_Actual_C1_required=True,normalization=5.987971384940258,PF_AIDC=.95,
            Q_PCC='P_PCC*tan(acos(0.95))',alpha_BG=1.15,May_numerical_coefficients_copied=False,
            physical_power_arrays_generated=False,forecast_capacity_preflight=audits[-1]))
        print(day,'forecast power construction',audits[-1]['fixed_known_plus_CC4_power_constructible'],'peak GPU',audits[-1]['maximum_required_GPU'],flush=True)
    write(OUT,'BUNDLE/APRIL_POWER_CONSTRUCTION_GATE.json',dict(days=audits,
        fixed_profile_constructible_days=sum(r['fixed_known_plus_CC4_power_constructible'] for r in audits),
        current_C1_date_bound_days=30,optimizer_calls=0,OpenDSS_calls=0,
        scientific_voltage_outcomes_used=False,May_outcomes_used=False))

if __name__=='__main__': main()
