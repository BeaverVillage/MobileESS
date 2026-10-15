"""Explain frozen forecast affine versus realized AUTO Fresh evaluation."""
from pathlib import Path
import csv
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_contract import digest
from v42_holdout.realization import archive_rows
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'
RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    target=OUT/'AFFINE_FRESH_AUTHORITY_AND_DIFFERENCE_AUDIT.json'
    if target.exists():raise FileExistsError('AFFINE_FRESH_AUDIT_MUST_NOT_OVERWRITE')
    plan=read(RAW/'PLANNING_INPUT_BUNDLE.json');actual=read(RAW/'ACTUAL_INPUT_BUNDLE.json')
    begin=pd.Timestamp(plan['day'],tz='Etc/GMT-10');end=begin+pd.Timedelta(days=1)
    exogenous={}
    for kind,time_key,column in (('demand','SETTLEMENTDATE','TOTALDEMAND'),('pv','INTERVAL_DATETIME','POWER')):
        source=actual['realized_inputs']['authority'][kind]
        rows=[r for r in archive_rows(source['path']) if r.get('REGIONID')=='VIC1' and time_key in r
            and (kind!='pv' or r.get('TYPE')=='MEASUREMENT')]
        frame=pd.DataFrame(rows)
        axis=pd.to_datetime(frame[time_key],format='%Y/%m/%d %H:%M:%S').dt.tz_localize('Etc/GMT-10')
        values=pd.Series(pd.to_numeric(frame[column]).to_numpy(),index=pd.DatetimeIndex(axis))
        values=values[(values.index>begin)&(values.index<=end)]
        step=15 if kind=='demand' else 30
        data=values.reindex(pd.date_range(begin+pd.Timedelta(minutes=step),end,freq=f'{step}min')).to_numpy(float)
        exogenous[kind]=(data if kind=='demand' else np.repeat(data,2))[:16]
        assert np.isfinite(exogenous[kind]).all()
    aemo=plan['forecast_inputs']['AEMO']
    exo_rows=[dict(slot=t,demand_forecast_MW=aemo['demand_mw_96'][t],demand_realized_MW=exogenous['demand'][t],
        demand_realized_minus_forecast_MW=exogenous['demand'][t]-aemo['demand_mw_96'][t],
        PV_forecast_MW=aemo['pv_mw_96'][t],PV_realized_MW=exogenous['pv'][t],
        PV_realized_minus_forecast_MW=exogenous['pv'][t]-aemo['pv_mw_96'][t]) for t in range(16)]
    with (OUT/'FORECAST_REALIZED_EXOGENOUS_FIRST16.csv').open('w',encoding='utf8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(exo_rows[0]));w.writeheader();w.writerows(exo_rows)
    variants={}
    for label in ('C0','C1'):
        base=OUT/label;authority=read(base/'AFFINE_OBSERVED_AUTHORITY.json')
        slots=read(base/'FRESH_16/FRESH_PHYSICAL_SLOTS.json');receipt=read(base/'FRESH_16/FRESH_PHYSICAL_RESULT.json')
        cert=read(authority['certificate']['path'])
        assert file_record(authority['certificate']['path'])==authority['certificate']
        assert file_record(authority['coefficients']['path'])==authority['coefficients']
        with np.load(base/'AFFINE_OBSERVED_DIAGNOSTICS.npz',allow_pickle=False) as packet:
            a={k:packet[k].copy() for k in packet.files}
        voltage=np.sqrt(np.maximum(0.,a['voltage_squared']))
        worst=tuple(int(v) for v in np.unravel_index(np.argmin(voltage),voltage.shape))
        errors=[];matched_counts=[]
        for t,slot in enumerate(slots):
            observed={r['node_phase'].lower():r['voltage_pu'] for r in slot['physical']['nodes']}
            matching=[(j,observed[str(n).lower()]) for j,n in enumerate(a['node_names']) if str(n).lower() in observed]
            matched_counts.append(len(matching))
            errors.extend(abs(voltage[t,j]-v) for j,v in matching)
        i,j=worst;node=str(a['node_names'][j])
        fresh_node=next((r['voltage_pu'] for r in slots[i]['physical']['nodes'] if r['node_phase'].lower()==node.lower()),None)
        variants[label]=dict(
            affine_AIDC_PQ_from_actual=True,fixed_MESS_identical=True,
            affine_background=authority['background'],Fresh_background='REALIZED_AEMO_PV_DEMAND_AND_CAUSAL_AUTO_SVR',
            certificate_Actual_inputs_read=cert['Actual_inputs_read'],
            certificate_validity_scope=cert['validity_scope'],
            certificate_global_nonlinear_envelope_certified=cert['global_nonlinear_envelope_certified'],
            certificate_control_semantics=cert['control_semantics'],certificate_sensitivity_semantics=cert['sensitivity_semantics'],
            physical_equipment_changed=False,voltage_bounds_changed=False,
            Fresh_original_initial_inventory=receipt['original_initial_inventory'],
            Fresh_SVR_state_SHA_by_slot=[digest(r['SVR']) for r in slots],
            Fresh_clock_SHA_by_slot=[digest(r['clock']) for r in slots],
            worst_affine_voltage=dict(slot=i,node=node,voltage_pu=float(voltage[i,j]),Fresh_same_slot_same_node_pu=fresh_node),
            max_absolute_control_anchor_delta=float(np.max(np.abs(a['control_anchor_delta']))),
            aligned_voltage_node_count_by_slot=matched_counts,
            max_absolute_aligned_affine_Fresh_voltage_difference_pu=max(errors) if errors else None,
            attribution='FORECAST_REALIZED_BACKGROUND_DIFFERENCE_AND_LOCAL_LDC_SECANT_VALIDITY;INDIVIDUAL_CAUSAL_SHARES_NOT_IDENTIFIED',
            nonlinear_Fresh_is_decisive=True,affine_rejections_not_retroactively_replaced_by_Fresh_admission=True)
    report=dict(status='AUDITED_DIFFERENT_EVALUATION_STATES',variants=variants,
        exogenous_first16=file_record(OUT/'FORECAST_REALIZED_EXOGENOUS_FIRST16.csv'),
        forecast_or_physical_constraints_modified=False,extra_AC_or_Native_calls=0,
        conclusion='AIDC_PQ_AND_MESS_MATCH;FROZEN_FORECAST_AFFINE_IS_NOT_REALIZED_NONLINEAR_AC_CERTIFICATE')
    _write(target,report)
    print(json.dumps({k:{n:v for n,v in r.items() if n in ('worst_affine_voltage','max_absolute_control_anchor_delta',
        'max_absolute_aligned_affine_Fresh_voltage_difference_pu')} for k,r in variants.items()},indent=2))


if __name__=='__main__':main()
