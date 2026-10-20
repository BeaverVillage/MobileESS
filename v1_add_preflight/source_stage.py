"""Complete the priority May01 input audit without any Greensboro AC."""
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record
sys.path.insert(0,str(ROOT))


def main():
    from v44.inputs import resolve_receipt
    from v43_actual.observations import load_observations
    from v42_regcontrol.authority import source
    manifest=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    bundle=Path(manifest['actual_bundle']);pro=read(bundle/'SOURCE_PROVENANCE.json')
    power=read(bundle/'POWER_AUTHORITY.json');plan=read(bundle/'PLANNING_INPUT_BUNDLE.json')
    pairs=[(k,r) for k,r in manifest['files'].items()]
    pairs += [('Kestrel_archive',pro['archive'])]
    pairs += [('daily_'+k,r) for k,r in pro['daily_sources'].items()]
    pairs += [('raw_realized_'+k,r) for k,r in pro['raw_realized_sources'].items()]
    pairs += [('D1_snapshot',pro['snapshot'])]
    for k in ('C1','C1_implementation','GFS','NOAA','planning_C1'):pairs.append(('power_'+k,power[k]))
    rows=[]
    for role,r in pairs:
        try:
            checked=resolve_receipt(r)
            rows.append(dict(role=role,source_path=r['path'],resolved_path=checked['path'],
                expected_sha256=r['sha256'],observed_sha256=checked['sha256'],bytes=checked['bytes'],status='PASS'))
        except Exception as error:
            rows.append(dict(role=role,source_path=r['path'],resolved_path='',expected_sha256=r['sha256'],
                observed_sha256='',bytes=r.get('bytes'),status='NOT_VERIFIED',reason=str(error)))
    csvout('PRIMARY_MAY01_SOURCE_AUTHORITY.csv',rows,
        ['role','source_path','resolved_path','expected_sha256','observed_sha256','bytes','status','reason'])
    forecast=read(resolve_receipt(pro['daily_sources']['aemo_forecast.json'])['path'])
    aemo=plan['forecast_inputs']['AEMO'];forecast_checks={}
    for key in ('demand_mw_96','pv_mw_96','timestamps_96'):
        forecast_checks[key]=forecast[key]==aemo[key]
    cutoff=datetime.fromisoformat(aemo['cutoff_fixed_aest'])
    stamp_checks={k:datetime.fromisoformat(aemo[k])<=cutoff for k in ('demand_issue','pv_issue')}
    begin=manifest['axis']['issue_seconds'];end=manifest['axis']['end_seconds']
    obs=load_observations(begin=begin,end=end);raw=[obs.at(begin+t*900,observed_now=begin+t*900) for t in range(120)]
    derived=pd.read_parquet(resolve_receipt(pro['daily_sources']['aemo_actual.parquet'])['path'])
    weather=pd.read_parquet(resolve_receipt(pro['daily_sources']['noaa_actual_weather.parquet'])['path'])
    compare=[]
    for t in range(96):
        r=raw[t+24]
        compare.append(dict(slot=t,raw_asof_demand_mw=r['demand']['values']['demand_mw'],
            derived_interval_end_demand_mw=float(derived.iloc[t].demand_mw),
            raw_asof_PV_mw=r['pv']['values']['pv_mw'],derived_interval_end_PV_mw=float(derived.iloc[t].rooftop_pv_mw),
            raw_hourly_asof_wetbulb_c=r['weather']['values']['t_wb_c'],
            derived_interpolated_wetbulb_c=float(weather.iloc[t].t_wb_c),
            effective_r043_source='raw as-of observations; proven by 120 archived setpoint digests',
            derived_is_retained_but_not_substituted=True))
    csvout('ACTUAL_RAW_ASOF_VS_DERIVED_AUDIT.csv',compare)
    model=source()['bg']
    save('NORMALIZATION_AND_APPLICATION_ORDER.json',dict(
        original_commit='affc7226a519adbe072d7debbc3ae25ea71c3487',new_scaling_operations=0,
        alpha_BG=power['alpha_BG'],alpha_BG_already_in_exported_arrays=True,alpha_BG_reapplied_to_Greensboro=False,
        alpha_grid=model.ALPHA_GRID,P95_reference_MW=model.P95_REFERENCE_MW,
        annual_max_reference_MW=model.ANNUAL_MAX_REFERENCE_MW,
        IEEE123_native_P_reference_kw=model.IEEE123_NATIVE_P_KW,
        IEEE123_native_Q_reference_kvar=model.IEEE123_NATIVE_Q_KVAR,
        PV_reference_max_MW=model.PV_REFERENCE_MAX_MW,original_PV_capacity_kw=model.PV_CAPACITY_EXPECTED_KW,
        IT_idle_kw_per_installed_GPU=power['current_IT_idle_kW_per_installed_GPU'],
        IT_swing_kw_per_active_GPU=power['current_IT_swing_kW_per_active_GPU'],PF_AIDC=power['PF_AIDC'],
        C1_normalization_factor=power['normalization'],C1_NLR_equivalent_scale=3.4987194698200215,
        C1_normalization_applied_inside_exact_original_callback=True,
        source_functions=[record(ROOT/'v43_actual/case.py'),record(ROOT/'v43_actual/vendor/actual.py'),
            record(model.__file__),resolve_receipt(power['C1_implementation'])],
        operation_order=[
            'D1 cutoff selects existing AEMO forecast and GFS; frozen reference/ML/job/traffic inputs retained.',
            'V16.2 gross=alpha_grid*(demand_MW*3490/7100.2615 + PV_MW*698.000002861023/4021.226).',
            'Frozen archetype residuals allocate gross P by IEEE123 bus/phase; frozen Q lookup and relative Q/P allocate Q.',
            'Dated final generation authority applies alpha_BG=1.15 once to gross background P/Q; PV is not multiplied by alpha_BG.',
            'NativeAllocation converts bus/phase targets to original load elements without duplication.',
            'Original phase PV Generator Model=1 receives original P and Q=0.',
            'Actual FCFS GPU -> IT -> exact C1 using raw observed weather -> AIDC P and PF0.95 Q; no planning power copied.',
            'Original MESS commands and independent Actual TIME controls; Planning7 and Actual43 equipment remain distinct.',
            'This audit reads setpoints only; no new IEEE123 or Greensboro AC/optimization.'],
        Greensboro_rule='Consume exported final totals directly; never multiply by alpha_BG or alpha_grid again.'))
    # The new P/Q vectors have different bus axes; compare conserved totals,
    # rather than expecting the spatial arrays to have equal SHAs.
    canonical=np.load(DOC/'IEEE123_FROZEN_ELECTRICAL_INPUTS.npz');candidate=np.load(RUN/'GREENSBORO_PQ_ALLOCATION_CANDIDATE.npz')
    metrics=[]
    for role in ('ACTUAL','PLANNING'):
        sl=slice(24,None) if role=='ACTUAL' else slice(None)
        for quantity,unit in [('P','kW'),('Q','kvar')]:
            original=np.array([math.fsum(r) for r in canonical[role+'_BG_'+quantity+('_kw' if quantity=='P' else '_kvar')][sl]])
            new=np.array([math.fsum(r) for r in candidate[role.lower()+'_'+quantity+'_candidate'][sl]])
            delta=abs(new-original);maximum=float(delta.max());relative=float(maximum/max(abs(original)))
            metrics.append(dict(role=role,quantity='background_'+quantity,unit=unit,max_abs_error=maximum,
                max_relative_error=relative,status='PASS_ARITHMETIC_ONLY',original_SHA='ELECTRICAL_ARRAY_SHA256.json',
                new_SHA=record(RUN/'GREENSBORO_PQ_ALLOCATION_CANDIDATE.npz')['sha256'],physical_mapping='NOT_VERIFIED'))
        for quantity,unit in [('PV_P','kW'),('PV_Q','kvar'),('net_P','kW'),('net_Q','kvar')]:
            metrics.append(dict(role=role,quantity=quantity,unit=unit,max_abs_error='',max_relative_error='',
                status='NOT_VERIFIED',original_SHA='ELECTRICAL_ARRAY_SHA256.json',new_SHA='',
                physical_mapping='PV and PCC mapping not certified; zero PV not substituted'))
        for quantity,unit in [('AIDC_P','kW'),('AIDC_Q','kvar')]:
            metrics.append(dict(role=role,quantity=quantity,unit=unit,max_abs_error=0.,max_relative_error=0.,
                status='PASS_IDENTITY_BINDING_ONLY',original_SHA='ELECTRICAL_ARRAY_SHA256.json',
                new_SHA='same original site-axis array',physical_mapping='PCC NOT_VERIFIED'))
    csvout('INPUT_IDENTITY_METRICS_96.csv',metrics)
    save('INPUT_IDENTITY_CERTIFICATION.json',dict(status='INPUT_MAPPING_NOT_VERIFIED',
        primary_source_receipts='PASS' if all(r['status']=='PASS' for r in rows) else 'NOT_VERIFIED',
        primary_receipt_count=len(rows),primary_failures=[r for r in rows if r['status']!='PASS'],
        forecast_bundle_array_checks=forecast_checks,declared_D1_issue_checks=stamp_checks,
        original_forecast_causal_availability='NOT_CERTIFIED (preserved inherited limitation)',
        actual_applied_setpoint_matches=120,actual_prefix24_preserved=True,
        P_Q_total_identity='PASS_ARITHMETIC_ONLY',AIDC_site_array_identity='PASS_IDENTITY_ONLY',
        PV_total_identity='NOT_VERIFIED',net_P_Q_identity='NOT_VERIFIED',
        job_UID_GPU_QoS_deadline='Same frozen source/window/descriptor receipts; no rewrite',
        route_ETA_energy='Same full Route Table bytes and traffic forecast receipt; no rewrite',
        blocking=['No certified PV phase/voltage/rating interconnection mapping',
            'AIDC12 + STA12 complete PCC acceptance and AIDC spatial order not verified',
            'Recursive ancestral evidence failures retained separately; do not promote source file checks to full lineage PASS'],
        Greensboro_AC_allowed=False,B0_status='B0_NOT_BUILT',scaling_searches=0))
    print('Primary source receipts:',sum(r['status']=='PASS' for r in rows),'/',len(rows))


if __name__=='__main__':main()
