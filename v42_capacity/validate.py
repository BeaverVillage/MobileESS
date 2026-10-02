"""Independent evidence checks against saved numerical arrays and CSV bytes."""
import csv
import gzip
import hashlib
import numpy as np
import pandas as pd
from .common import *


def main():
    source=read(OUT/'ELECTRICAL_SOURCE_AUTHORITY.json')
    for row in source['static_sources']+source['code_sources']: resolve(row)
    audits=[]; total_rows=0
    for d in range(1,31):
        day=f'2025-04-{d:02d}'; path=OUT/'BUNDLE'/day_folder(day)
        p=np.load(path/'PLANNING_PHYSICAL.npz'); a=np.load(path/'ACTUAL_PHYSICAL.npz')
        v=np.load(path/'V_ACTUAL_AC.npz'); vp=np.load(path/'V_PLAN.npz'); h=np.load(path/'APRIL_D1_VOLTAGE_RESPONSE.npz')
        c=read(path/'FRESH_ACTUAL_AC_RECEIPT.json'); caps=p['capacities']
        assert (p['total_gpu']<=caps+1e-9).all() and (a['GPU']<=caps+1e-9).all()
        assert np.array_equal(p['known_gpu']+p['cc4_served_gpu'],p['total_gpu'])
        assert np.allclose(a['IT_kw'],.1041606964512843*caps+.5477239090195797*a['GPU'],atol=1e-12,rtol=0)
        assert np.allclose(a['PCC_Q_kvar'],a['PCC_P_kw']*np.tan(np.arccos(.95)),atol=1e-12,rtol=0)
        assert np.array_equal(v['node_names'],vp['node_names'])
        assert np.array_equal(np.sqrt(vp['V_squared']),vp['V_PLAN'])
        controls=np.zeros_like(h['anchor_control']); controls[:,:12]=p['PCC_P_kw']
        model=vp['voltage_constant']+np.einsum('tc,tcn->tn',controls,h['sensitivity'])
        assert np.allclose(model,vp['V_squared'],atol=1e-12,rtol=0)
        assert bool(v['converged'].all()) and len(v['converged'])==96
        assert c['voltage_violations']==int(np.sum((v['V_ACTUAL_AC']<.95)|(v['V_ACTUAL_AC']>1.05)))
        assert np.array_equal(v['regulator_taps'],h['regulator_taps'])
        assert np.array_equal(v['capacitor_states'],h['capacitor_states'])
        led=list(csv.DictReader((path/'ACTUAL_QUEUE_LEDGER.csv').open(encoding='utf8')))
        assert all(r['future_duration_reads']=='0' and r['future_end_reads']=='0' and r['grid_reads']=='0' for r in led)
        assert all(r['timeshift_optimization']=='False' and r['migration_optimization']=='False' for r in led)
        audits.append(dict(day=day,Planning_Actual_capacity_PASS=True,Actual_IT_recomputed_PASS=True,
            power_arrays_differ_from_Planning=not np.array_equal(p['PCC_P_kw'],a['PCC_P_kw']),
            affine_squared_voltage_evaluation_PASS=True,causal_policy_fields_PASS=True,
            fresh_convergence_PASS=True,all_96_native_control_states_match_frozen_Plan=True))
    stored=read(OUT/'VOLTAGE_RESIDUAL_STORAGE.json')
    digest=hashlib.sha256()
    with gzip.open(OUT/'APRIL_B0_PLANNING_ACTUAL_VOLTAGE_RESIDUALS.csv.gz','rb') as z:
        for chunk in iter(lambda:z.read(1048576),b''): digest.update(chunk)
    assert digest.hexdigest()==stored['CSV']['sha256']
    frame=pd.read_csv(OUT/'APRIL_B0_PLANNING_ACTUAL_VOLTAGE_RESIDUALS.csv.gz',dtype={'node':str,'phase':str},float_precision='round_trip')
    assert len(frame)==1111680 and not frame[['day','node','phase','slot']].duplicated().any()
    assert np.array_equal(frame.V_ACTUAL_AC-frame.V_PLAN,frame.e_total)
    assert np.array_equal(np.maximum(frame.e_total,0),frame.r_up)
    assert np.array_equal(np.maximum(-frame.e_total,0),frame.r_down)
    assert np.array_equal(abs(frame.e_total),frame.abs_e)
    for day,group in frame.groupby('day',sort=False):
        path=OUT/'BUNDLE'/day_folder(day)
        p=np.load(path/'V_PLAN.npz'); a=np.load(path/'V_ACTUAL_AC.npz')
        assert np.array_equal(group.V_PLAN.to_numpy().reshape(96,386),p['V_PLAN'])
        assert np.array_equal(group.V_ACTUAL_AC.to_numpy().reshape(96,386),a['V_ACTUAL_AC'])
    write(OUT,'INDEPENDENT_NUMERICAL_AUDIT.json',dict(PASS=True,days=audits,rows_checked=len(frame),
        residual_CSV_lossless_compression_PASS=True,exact_CSV_NPZ_numeric_identity_PASS=True,
        residual_formula_PASS=True,node_phase_slot_duplicate_rows=0,scientific_policy_changes=0,
        Actual_capacity_violations=0,Planning_capacity_violations=0))
    print('Independent numerical evidence PASS',len(frame),'rows',flush=True)


if __name__=='__main__': main()
