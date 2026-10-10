"""Read-only source-bound enrichment of the preserved nineteen May01 cells."""
import csv
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.dont_write_bytecode=True
CODE=Path(r'D:\v42u4final')
sys.path.insert(0,str(CODE))
ROOT=Path(r'D:\v42_actual_voltage_audit_20261010')
ATTEMPT=Path(r'D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01')
OPS=ATTEMPT/'output/OPERATIONS'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def receipt(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),sha256=sha,bytes=path.stat().st_size)
def cell(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')) if isinstance(value,(list,dict)) else value
def sums(values):return float(sum(values.values()))

def main():
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    request=read(ATTEMPT/'REQUEST.json');inputpath=Path(request['input_folder'])
    physical=read(OPS/'FRESH/RAW_PHYSICAL_INPUT_LOG.json')
    forecast_path=inputpath/'OPERATIONS.json'
    forecast=read(forecast_path)['forecast_inputs']['AEMO']
    actual_path=Path(physical['Actual_exogenous']['path'])
    plan_path=ATTEMPT/'output/OPTIMIZED_MESS_PLAN.json';plan=read(plan_path)
    controls=read(OPS/'FRESH/RAW_CONTROL_LOG.json')
    diagnostic_counts_path=ROOT/'factorial/FULL_PQ_REPLAY/OBSERVED_CONTROL_ITERATIONS.json'
    diagnostic_counts=read(diagnostic_counts_path)
    controls_settings=authority.regulator_parameters(controls['source_initial_inventory'])
    aggregate=authority.digest(controls_settings)
    cell_path=ROOT/'B2_MAY01_19CELL_PQ_FACTORIAL.csv'
    sources=[cell_path,ATTEMPT/'REQUEST.json',plan_path,forecast_path,actual_path,diagnostic_counts_path,
        OPS/'FRESH/RAW_CONTROL_LOG.json',OPS/'FRESH/RAW_PHYSICAL_INPUT_LOG.json',
        OPS/'ACTUAL/ACTUAL_MESS_TRAJECTORY.npz',OPS/'ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz',
        OPS/'SOURCE/PLANNING_PHYSICAL.npz',CODE/'v42_regcontrol/runner.py',CODE/'v42_regcontrol/authority.py',
        CODE/'v42_may_campaign_native90/operations.py',Path(__file__)]
    source=authority.source()
    sources.extend(Path(row['path']) for row in source['audit']['static_source_graph']['files']+source['audit']['code_read'])
    before=[receipt(path) for path in dict.fromkeys(sources)]
    actual=pd.read_parquet(actual_path)
    stamps=[pd.Timestamp(x).tz_convert('Etc/GMT-10').isoformat() for x in actual.ts_fixed_aest_end]
    assert pd.DatetimeIndex(stamps).tz_convert('UTC').equals(pd.DatetimeIndex(forecast['timestamps_96']).tz_convert('UTC'))
    # Original exact background binding, including single alpha_BG=1.15 on gross P/Q, no PV scaling.
    fbg=background(stamps,forecast['demand_mw_96'],forecast['pv_mw_96'])
    abg=background(stamps,actual.demand_mw.tolist(),actual.rooftop_pv_mw.tolist())
    original_before=receipt(OPS/'ACTUAL/ACTUAL_MESS_TRAJECTORY.npz')
    with np.load(OPS/'ACTUAL/ACTUAL_MESS_TRAJECTORY.npz',allow_pickle=False) as data:
        mess={k:data[k].copy() for k in data.files}
    with np.load(OPS/'SOURCE/PLANNING_PHYSICAL.npz',allow_pickle=False) as data:
        aidc_plan={k:data[k].copy() for k in ('PCC_P_kw','PCC_Q_kvar')}
    with np.load(OPS/'ACTUAL/ACTUAL_FIXED_TRAJECTORY.npz',allow_pickle=False) as data:
        aidc_actual={k:data[k].copy() for k in data.files}
    assert all(np.array_equal(aidc_plan[k],aidc_actual[k]) for k in aidc_plan)
    with cell_path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==19
    for row in rows:
        t=int(row['slot_0based']);station=row['station']
        selected=[i for i,site in enumerate(mess['locations'][t]) if site==station]
        unit_details=[]
        for i in selected:
            unit=str(mess['unit_ids'][i]);values=plan['values']
            pch=float(values[f'Pch[{unit},{station},{t}]']);pdis=float(values[f'Pdis[{unit},{station},{t}]'])
            q=float(values[f'Q[{unit},{station},{t}]'])
            assert pdis-pch == mess['P_kw'][t,i] and q == mess['Q_kvar'][t,i]
            unit_details.append(dict(unit=unit,location=station,Pch_kw=pch,Pdis_kw=pdis,Pnet_kw=float(mess['P_kw'][t,i]),Q_kvar=q))
        control=controls['slots'][t]
        previous=controls['slots'][t-1]['taps'] if t else [r['initial_tap'] for r in controls['source_initial_inventory']['regulators']]
        tap_fields={}
        for i,reg in enumerate(controls_settings['regulators']):
            name=reg['name'];tap=float(control['taps'][i]);prior=float(previous[i])
            tap_fields.update({name+'_enabled':bool(control['all_7_RegControls_enabled']),name+'_settings_SHA':authority.digest(reg),
                name+'_previous_tap':prior,name+'_settled_tap':tap,name+'_tap_change':tap-prior,
                name+'_settled_tap_position':int(round((tap-1.)/reg['tap_step']))})
        row.update(local_MESS_Pch_kw=sum(r['Pch_kw'] for r in unit_details),local_MESS_Pdis_kw=sum(r['Pdis_kw'] for r in unit_details),
            local_MESS_Pnet_kw=sum(r['Pnet_kw'] for r in unit_details),local_MESS_Q_kvar=sum(r['Q_kvar'] for r in unit_details),
            local_MESS_location=station,local_MESS_unit_Pch_Pdis_Q=unit_details,
            Forecast_AEMO_demand_mw=float(forecast['demand_mw_96'][t]),Actual_AEMO_demand_mw=float(actual.demand_mw.iloc[t]),
            Actual_minus_Forecast_AEMO_demand_mw=float(actual.demand_mw.iloc[t])-float(forecast['demand_mw_96'][t]),
            Forecast_AEMO_rooftop_PV_mw=float(forecast['pv_mw_96'][t]),Actual_AEMO_rooftop_PV_mw=float(actual.rooftop_pv_mw.iloc[t]),
            Actual_minus_Forecast_AEMO_rooftop_PV_mw=float(actual.rooftop_pv_mw.iloc[t])-float(forecast['pv_mw_96'][t]),
            Forecast_background_gross_P_kw=sums(fbg.gross_p_kw_96[t]),Actual_background_gross_P_kw=sums(abg.gross_p_kw_96[t]),
            Actual_minus_Forecast_background_gross_P_kw=sums(abg.gross_p_kw_96[t])-sums(fbg.gross_p_kw_96[t]),
            Forecast_background_gross_Q_kvar=sums(fbg.gross_q_kvar_96[t]),Actual_background_gross_Q_kvar=sums(abg.gross_q_kvar_96[t]),
            Actual_minus_Forecast_background_gross_Q_kvar=sums(abg.gross_q_kvar_96[t])-sums(fbg.gross_q_kvar_96[t]),
            Forecast_feeder_PV_kw=sums(fbg.pv_generation_kw_96[t]),Actual_feeder_PV_kw=sums(abg.pv_generation_kw_96[t]),
            Actual_minus_Forecast_feeder_PV_kw=sums(abg.pv_generation_kw_96[t])-sums(fbg.pv_generation_kw_96[t]),
            Forecast_AIDC_PCC_P_total_kw=float(aidc_plan['PCC_P_kw'][t].sum()),Actual_AIDC_PCC_P_total_kw=float(aidc_actual['PCC_P_kw'][t].sum()),
            Actual_minus_Forecast_AIDC_PCC_P_total_kw=float((aidc_actual['PCC_P_kw'][t]-aidc_plan['PCC_P_kw'][t]).sum()),
            Forecast_AIDC_PCC_Q_total_kvar=float(aidc_plan['PCC_Q_kvar'][t].sum()),Actual_AIDC_PCC_Q_total_kvar=float(aidc_actual['PCC_Q_kvar'][t].sum()),
            Actual_minus_Forecast_AIDC_PCC_Q_total_kvar=float((aidc_actual['PCC_Q_kvar'][t]-aidc_plan['PCC_Q_kvar'][t]).sum()),
            Forecast_AIDC_PCC_P_kw_12=aidc_plan['PCC_P_kw'][t].tolist(),Actual_AIDC_PCC_P_kw_12=aidc_actual['PCC_P_kw'][t].tolist(),
            Forecast_AIDC_PCC_Q_kvar_12=aidc_plan['PCC_Q_kvar'][t].tolist(),Actual_AIDC_PCC_Q_kvar_12=aidc_actual['PCC_Q_kvar'][t].tolist(),
            all_seven_RegControls_enabled=bool(control['all_7_RegControls_enabled']),regulator_settings_SHA=aggregate,
            Actual_control_actions_done_from_bit_exact_FullPQ_replay=diagnostic_counts[t]['control_actions_done'],
            Actual_control_iterations_from_bit_exact_FullPQ_replay=diagnostic_counts[t]['control_iterations'],
            Actual_total_solution_iterations_from_bit_exact_FullPQ_replay=diagnostic_counts[t]['electrical_iterations'],
            Actual_capacitor_states=control['caps'],
            tap_previous_basis='PREVIOUS_SETTLED_ACTUAL' if t else 'ORIGINAL_SOURCE_INITIAL',**tap_fields)
    output=ROOT/'B2_MAY01_19CELL_INPUT_CONTROL_ENRICHMENT.csv'
    with output.open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows({k:cell(v) for k,v in row.items()} for row in rows)
    after=[receipt(path) for path in dict.fromkeys(sources)]
    assert before==after and receipt(OPS/'ACTUAL/ACTUAL_MESS_TRAJECTORY.npz')==original_before
    report=dict(schema='V42_MAY01_19CELL_INPUT_CONTROL_READ_ONLY_V1',PASS=True,rows=19,
        preserved_original_scientific_sources=True,Native_optimizer_calls=0,Fresh_AC_calls=0,
        original_source_before_after_SHA_equal=True,regulator_settings_SHA=aggregate,AIDC_Planning_Actual_bit_equal=True,
        Pnet_sign='Pdis-Pch; positive discharge; Q original generator sign',
        background_semantics='Original source background(); feeder sums after exact single alpha_BG=1.15 gross P/Q scaling; PV unscaled',
        attribution_scope='Raw input differences and observed taps are linked context; factorial P/Q voltage effects are exact original Fresh interventions, not additive prediction of exogenous effects',
        output=receipt(output),Source_SHA_receipts=before,Forecast_background_evidence=fbg.evidence,Actual_background_evidence=abg.evidence)
    with (ROOT/'B2_MAY01_19CELL_INPUT_CONTROL_ENRICHMENT.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(dict(PASS=True,rows=19,output=receipt(output),AIDC_delta=0,Native=0,Fresh=0)))

if __name__=='__main__':main()
