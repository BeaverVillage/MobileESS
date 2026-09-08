"""User-authorized physical-support correction; preserves residual authority."""
from dataclasses import replace
from pathlib import Path
import json, shutil, hashlib
import numpy as np
import calibrate as c

DAY='2025-05-04'
RUN=c.ROOT/'frozen_artifacts/v41r4'
TEXT=('Historical empirical residual trajectories are preserved, while '
      'scenario materialization is projected onto the physical support of the '
      'corresponding exogenous quantity. PV active power is constrained to be '
      'nonnegative.')

def verify(ref):
    p=Path(ref['path'])
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    assert h==ref['sha256'],('FILE_DRIFT',str(p))
    return p

def load_authority():
    seal=c.read(c.OUT/'V41R4_UNCERTAINTY_AUTHORITY_SEAL.json')
    return c.read(verify(seal['authority']))

def amend():
    p=c.OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json'
    a=load_authority()
    if 'physical_support' in a:return a
    oldseal=c.read(c.OUT/'V41R4_UNCERTAINTY_AUTHORITY_SEAL.json')
    archive=c.OUT/'selection_original';archive.mkdir(exist_ok=True)
    for name in (p.name,p.name+'.sha256','V41R4_UNCERTAINTY_AUTHORITY_SEAL.json'):
        assert not (archive/name).exists();shutil.copyfile(c.OUT/name,archive/name)
    bg,paths,refs=c.load_mapping()
    adapter=c.read(paths.runtime_adapter)
    upper=sum(float(r['capacity_kw']) for r in adapter['pv_generators'])
    assert abs(upper-bg.PV_CAPACITY_EXPECTED_KW)<1e-8
    support=dict(statement=TEXT,PV_lower_kW=0.,
        PV_upper=dict(kind='EXISTING_INSTALLED_CAPACITY',aggregate_kW=upper,source=c.record(paths.runtime_adapter),field='pv_generators[].capacity_kw',time_dependent=False),
        rule='PV=min(installed_capacity,max(0,DA_PV+same_day_residual)); BG P/Q unchanged',
        all_May_days_and_policies=True,policy_result_tuning=False,Actual_result_tuning=False,
        arbitrary_clipped_fraction_rejection_threshold=None,user_authorization='V41R4 ROBUST SCENARIO PHYSICAL-SUPPORT CORRECTION',
        residual_array_or_selected_day_changes=0,previous_authority=oldseal['authority'],previous_authority_archived=c.record(archive/p.name))
    a['physical_support']=support
    original=json.loads((archive/p.name).read_text(encoding='utf-8'))
    assert {k:v for k,v in a.items() if k!='physical_support'}==original
    assert a['d_HIGH']=='2025-01-29' and a['d_LOW']=='2025-03-12'
    p.write_text(json.dumps(a,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    c.RECORDS.pop(str(p.resolve()),None)
    ref=c.record(p)
    (c.OUT/(p.name+'.sha256')).write_text(ref['sha256']+'  '+p.name+'\n',encoding='ascii')
    seal=dict(status='FROZEN_PHYSICAL_SUPPORT_AMENDMENT',authority=ref,residuals=oldseal['residuals'],construction_source=c.record(__file__),original_seal=c.record(archive/'V41R4_UNCERTAINTY_AUTHORITY_SEAL.json'),d_HIGH=a['d_HIGH'],d_LOW=a['d_LOW'],MAY_DATA_USED=False,MAY04_ACTUAL_USED=False)
    (c.OUT/'V41R4_UNCERTAINTY_AUTHORITY_SEAL.json').write_text(json.dumps(seal,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return a

def materialize(day, nominal, authority, installed):
    """Pure materializer, shared identically by every May day and policy."""
    assert day.startswith('2025-05-')
    assert authority['physical_support']['all_May_days_and_policies']
    axis=sorted(set().union(*(set(r) for r in nominal.gross_p_kw_96)))
    def array(rows):return np.array([[r.get(k,0.) for k in axis] for r in rows])
    p,q,pv=map(array,(nominal.gross_p_kw_96,nominal.gross_q_kvar_96,nominal.pv_generation_kw_96))
    cap=np.array([installed.get(k,0.) for k in axis]);total=float(cap.sum())
    assert abs(total-authority['physical_support']['PV_upper']['aggregate_kW'])<1e-8
    assert p.shape==q.shape==pv.shape and len(p)==96
    pshare=p/p.sum(axis=1,keepdims=True);qshare=q/q.sum(axis=1,keepdims=True)
    pvshare=cap/total
    arrays={};audit={}
    for label in ('S0','S1','S2'):
        r=authority['selected_residuals'].get(label,{k:[0.]*96 for k in ('P_BG_kW','Q_BG_kvar','PV_P_kW')})
        pp=1.6*(p+pshare*np.array(r['P_BG_kW'])[:,None])
        qq=1.6*(q+qshare*np.array(r['Q_BG_kvar'])[:,None])
        raw=pv+np.array(r['PV_P_kW'])[:,None]*pvshare
        projected=np.minimum(cap,np.maximum(0.,raw))
        assert np.isfinite([pp,qq,raw,projected]).all() and (pp>=0).all() and (qq>=0).all()
        assert (projected>=0).all() and (projected<=cap).all()
        raw_total=raw.sum(axis=1);new_total=projected.sum(axis=1)
        correction=np.abs(projected-raw).sum(axis=1)
        denom=float(np.maximum(raw,0).sum()*.25)
        audit[label]=dict(source_day=authority['d_HIGH'] if label=='S1' else authority['d_LOW'] if label=='S2' else None,
            negative_PV_slots_before_projection=np.flatnonzero(raw_total<0).tolist(),minimum_raw_PV_kW=float(raw_total.min()),
            projected_slot_count=int(np.count_nonzero(correction>0)),total_clipped_energy_kWh=float(correction.sum()*.25),
            lower_projection_energy_kWh=float(np.maximum(-raw,0).sum()*.25),upper_projection_energy_kWh=float(np.maximum(raw-cap,0).sum()*.25),
            daily_PV_energy_before_kWh=float(raw_total.sum()*.25),daily_PV_energy_after_kWh=float(new_total.sum()*.25),
            daily_positive_raw_PV_energy_kWh=denom,clipped_energy_fraction_of_positive_raw_PV=None if denom==0 else float(correction.sum()*.25/denom),
            maximum_single_slot_correction_kW=float(correction.max()),raw_PV_kW_96=raw_total.tolist(),projected_PV_kW_96=new_total.tolist(),
            finite=True,slots=96,background_P_Q_clipped=False,unauthorized_clipping=False,
            negative_after=0,upper_excess_after=0,aggregate_BG_P_min_kW=float(pp.sum(axis=1).min()),aggregate_BG_Q_min_kvar=float(qq.sum(axis=1).min()))
        arrays[label]=dict(bus_phase_keys=np.array(['::'.join(k) for k in axis]),gross_P_kw=pp,gross_Q_kvar=qq,PV_P_kw=projected,PV_P_raw_kw=raw,PV_capacity_kw=cap)
    return arrays,audit

def background(label):
    from dayahead.grid_background_v16_2 import AuthorityBackgroundBinding
    with np.load(RUN/'scenarios'/f'{label}.npz') as z:
        axis=[tuple(k.split('::')) for k in z['bus_phase_keys']]
        rows=lambda key:tuple(dict(zip(axis,map(float,row))) for row in z[key])
        p,q,pv=rows('gross_P_kw'),rows('gross_Q_kvar'),rows('PV_P_kw')
    net=tuple({k:r[k]-pv[t][k] for k in axis} for t,r in enumerate(p))
    return AuthorityBackgroundBinding(net,q,p,pv,dict(V41R3_scaled=True,alpha_BG=1.6,scenario=label,V41R4=True,authority=c.record(c.OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json')))

def main():
    a=amend();bg,paths,refs=c.load_mapping()
    fpath=c.WORK/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days'/DAY/'aemo_forecast.json'
    f=c.read(fpath)
    nominal=bg.build_authority_background_binding(timestamps_fixed_aest=f['timestamps_96'],demand_mw_96=f['demand_mw_96'],rooftop_pv_mw_96=f['pv_mw_96'],paths=paths)
    adapter=c.read(paths.runtime_adapter);installed={}
    for r in adapter['pv_generators']:
        k=(r['bus'].lower(),'ABC'[r['phase']-1]);installed[k]=installed.get(k,0.)+r['capacity_kw']
    arrays,audit=materialize(DAY,nominal,a,installed)
    # S0 preserves the exact stored alpha=1.60 operating point.
    with np.load(c.SCALE/'inputs/ORIGINAL_DAYAHEAD_BACKGROUND.npz') as z:
        assert np.array_equal(arrays['S0']['bus_phase_keys'],z['bus_phase_keys'])
        for key in ('gross_P_kw','gross_Q_kvar','PV_P_kw'):
            expected=z[key]*(1.6 if key!='PV_P_kw' else 1.)
            assert np.array_equal(expected,arrays['S0'][key]),('NOMINAL_DRIFT',key)
    outputs={};(RUN/'scenarios').mkdir(parents=True,exist_ok=True)
    for label,arr in arrays.items():
        p=RUN/'scenarios'/f'{label}.npz';assert not p.exists();np.savez_compressed(p,**arr)
        outputs[label]=c.record(p)
    report=dict(status='PASS',day=DAY,policy_independent=True,authority=c.record(c.OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json'),
        source_day_identity_preserved=True,selection_changed=False,selected_residual_arrays_changed=False,
        statement=TEXT,upper_bound=a['physical_support']['PV_upper'],
        fraction_rejection_threshold=None,scenarios=audit,outputs=outputs,nominal_source=c.record(fpath),
        May04_Actual_access_count=0,historical_optimization_calls=0,historical_OpenDSS_calls=0,
        forecast_only_materialization=True,source=c.record(__file__))
    c.save('V41R4_SCENARIO_PHYSICAL_SUPPORT_AUDIT.json',report)
    print(json.dumps({s:{k:v for k,v in r.items() if not k.endswith('_96')} for s,r in audit.items()}),flush=True)

if __name__=='__main__':main()
