"""Diagnostic PCC substitution only: no job solve, acceptance, or new policy."""
from pathlib import Path
import os
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,reference,digest
from dayahead.v40e.audit import REL
from dayahead.v40e.neutral_forensic import table


def run(repo):
    from dayahead.v40e.electrical import electrical_context
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v28r2.electrical_context import with_realized_background
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v35.execution import MESS_INITIAL
    import gurobipy as gp
    repo=Path(repo).resolve();root=repo/REL;s=root/'smoke/2025-05-01';out=root/'neutral_move_forensic'
    context=electrical_context(repo,'2025-05-01')
    with np.load(s/'CORRECTED_ACTUAL_EXOGENOUS.npz') as z:exo={k:z[k] for k in z.files}
    data={}
    for c in ('B0','B1'):
        f=pd.read_parquet(s/c/'aidc_site_timeseries.parquet').sort_values(['slot','site_id'])
        data[c]=tuple(f[k].to_numpy().reshape(96,12) for k in ['P_PCC_kW','Q_PCC_kvar'])
    actual=with_realized_background(SOURCE_DATA_REPOSITORY,context,
        timestamps_96=[x.isoformat() for x in pd.date_range('2025-05-01T00:00:00+10:00',periods=96,freq='15min')],
        demand_mw_96=exo['demand'],pv_mw_96=exo['pv'],aidc_plan_kw_96x12=data['B0'][0])
    ids=tuple(sorted(MESS_INITIAL));locations=np.array([[MESS_INITIAL[m] for m in ids] for _ in range(96)],dtype=str)
    saved={}
    for c in data:
        with np.load(s/c/'actual_grid/OPENDSS_PHASE_ARRAYS.npz') as z:saved[c]={k:z[k] for k in z.files}
    k=next(i for i,(n,p) in enumerate(zip(saved['B1']['branch_names'],saved['B1']['branch_phases'])) if n=='line.l10' and p=='A')
    rows=[];full=[];oldopt=gp.Model.optimize;previous=Path.cwd()
    def forbidden(*a,**k):raise RuntimeError('NO_OPTIMIZATION_IN_ATTRIBUTION')
    gp.Model.optimize=forbidden
    try:
        for count in range(13):
            p=data['B0'][0].copy();q=data['B0'][1].copy()
            p[:,:count]=data['B1'][0][:,:count];q[:,:count]=data['B1'][1][:,:count]
            identity=digest({'DIAGNOSTIC_ONLY':True,'B1_first_n_sites':count,'P':p,'Q':q})
            trajectory=FrozenTrajectory('2025-05-01','ACTUAL','B0_B1_PCC_DIAGNOSTIC',p,q,np.zeros((96,4)),np.zeros((96,4)),ids,locations,identity)
            with corrected_mapping():
                r=run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=actual,voltage=context.voltage,trajectory=trajectory)
            os.chdir(previous)
            assert np.array_equal(r.regulator_taps,saved['B0']['regulator_taps'])
            assert np.array_equal(r.capacitor_states,saved['B0']['capacitor_states'])
            row={'B1_first_n_sites':count,'site_changed_this_step':'BASE_B0' if count==0 else f'AIDC{count:02d}',
                'line':'line.l10','phase':'A','slot':30,'current_A':float(r.phase_current_a[30,k]),
                'rho_same_coordinate':float(r.phase_current_loading_pu[30,k]),
                'Delta_current_A_from_previous':0 if not rows else float(r.phase_current_a[30,k])-rows[-1]['current_A'],
                'Delta_rho_from_previous':0 if not rows else float(r.phase_current_loading_pu[30,k])-rows[-1]['rho_same_coordinate'],
                'Delta_site_P_kw':0 if count==0 else float(data['B1'][0][30,count-1]-data['B0'][0][30,count-1]),
                'Delta_site_Q_kvar':0 if count==0 else float(data['B1'][1][30,count-1]-data['B0'][1][30,count-1])}
            rows.append(row);full.append(r.phase_current_a)
            if count in (0,12):
                c='B0' if count==0 else 'B1'
                row['endpoint_max_current_error_A']=float(abs(r.phase_current_a-saved[c]['phase_current_a']).max())
                row['endpoint_max_voltage_error_pu']=float(abs(r.voltage_pu-saved[c]['voltage_pu']).max())
                assert row['endpoint_max_current_error_A']<1e-8 and row['endpoint_max_voltage_error_pu']<1e-10
            print('PCC attribution '+str(count)+'/12: '+str(row['current_A']),flush=True)
    finally:
        gp.Model.optimize=oldopt;os.chdir(previous);context.voltage.close();context.current.close()
    frame=pd.DataFrame(rows);table(out,'ORDERED_SITE_PCC_CURRENT_ATTRIBUTION',frame)
    np.savez_compressed(out/'ORDERED_SITE_PCC_CURRENT_ARRAYS.npz',phase_current_a=np.array(full),branch_names=saved['B0']['branch_names'],branch_phases=saved['B0']['branch_phases'])
    result={'status':'PASS','kind':'DIAGNOSTIC_ELECTRICAL_INPUT_INTERVENTION_ONLY','site_order':[f'AIDC{x:02d}' for x in range(1,13)],
        'description':'Start with all B0 Actual PCC; replace one complete site P/Q trajectory at a time by B1. Identical realized exogenous inputs and frozen controls. Endpoints reproduce both saved Actual trajectories.',
        'interpretation':'Exact telescoping nonlinear current attribution in the specified order. Individual increments are order dependent, not unique causal shares or an executable hybrid job schedule.',
        'decision_optimization_calls':0,'method_changed':False,'production_decision_changed':False,'FULL_MAY_AUTHORIZED':'NO',
        'sum_current_increments_A':float(frame.Delta_current_A_from_previous.sum()),
        'endpoint_current_difference_A':rows[-1]['current_A']-rows[0]['current_A'],
        'telescoping_error_A':float(frame.Delta_current_A_from_previous.sum())-(rows[-1]['current_A']-rows[0]['current_A']),
        'source_PQ':{c:reference(s/c/'aidc_site_timeseries.parquet') for c in data},'exogenous_source':reference(s/'CORRECTED_ACTUAL_EXOGENOUS.npz'),
        'rows':rows}
    write_json(out/'V40E_PCC_ONLY_CURRENT_ATTRIBUTION.json',result)
    print('PCC-only exact endpoint confirmation PASS',flush=True)
    return result
