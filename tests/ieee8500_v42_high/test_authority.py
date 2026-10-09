"""Source/time/population regressions without feeder or optimizer imports."""
import csv,json,hashlib
from pathlib import Path
import numpy as np
import pytest
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'docs/ieee8500_v42_high_impact_scenario'
DATA=ROOT/'ieee8500_v42_high/data/validation/2025-05-02'

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(name):
    with (DATA/'sources'/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def test_frozen_validation_bytes_and_producer_identity():
    m=read(REPORT/'VALIDATION_SOURCE_SHA256.json')
    for name,r in m['output_files'].items():assert sha(ROOT/name)==r['sha256'],name
    assert sha(REPORT/'INPUT_PRODUCER_FROZEN.py.txt')==m['producer']['sha256']

def test_actual_15minute_interval_energy_uses_all_three_subintervals():
    raw=rows('ACTUAL_SELECTED_DEMAND_5MIN.csv')
    assert len(raw)==288
    stamps=pd.DatetimeIndex([pd.Timestamp(r['SETTLEMENTDATE'],tz='Etc/GMT-10') for r in raw])
    expected=pd.date_range('2025-05-02 00:05',periods=288,freq='5min',tz='Etc/GMT-10')
    assert stamps.equals(expected)
    mw=np.array([float(r['TOTALDEMAND']) for r in raw])
    with np.load(DATA/'derived/ACTUAL_INPUTS.npz',allow_pickle=False) as z:
        assert np.max(abs(z['demand_mw']-mw.reshape(96,3).mean(axis=1)))<1e-10
        assert abs(z['demand_mw'].sum()*.25-mw.sum()/12)<1e-8
        # This dataset distinguishes the correct interval mean from endpoint sampling.
        assert np.max(abs(z['demand_mw']-mw[2::3]))>1

def test_half_hour_PV_and_forecast_values_preserve_original_energy():
    actual_pv=rows('ACTUAL_SELECTED_PV_30MIN.csv')
    forecast=read(DATA/'sources/AEMO_FORECAST.json')
    assert len(actual_pv)==48
    a=np.array([float(r['POWER']) for r in actual_pv])
    with np.load(DATA/'derived/ACTUAL_INPUTS.npz',allow_pickle=False) as z:
        np.testing.assert_array_equal(z['pv_mw'],np.repeat(a,2))
        assert abs(z['pv_mw'].sum()*.25-a.sum()*.5)<1e-8
    with np.load(DATA/'derived/PLANNING_INPUTS.npz',allow_pickle=False) as z:
        for key in ('demand','pv'):np.testing.assert_array_equal(z[key+'_mw'],forecast[key+'_mw_96'])

def test_original_gang_population_capacity_and_private_truth_separation():
    plan=read(DATA/'sources/PLANNING_INPUT_BUNDLE.json')
    actual=read(DATA/'sources/PRIVATE_ACTUAL_INPUT_BUNDLE.json')
    private=rows('PRIVATE_ACTUAL_Kestrel_UID_JOIN.csv')
    known=plan['known_population'];new=actual['post_issue_arrivals']
    expected={str(j['job_uid']):j['GPU_gang'] for j in known+new}
    assert len(known)==1532 and len(new)==1329 and len(expected)==2861
    assert {r['job_uid']:int(r['immutable_requested_GPU']) for r in private}==expected
    assert all(r['controller_future_duration_access']=='False' for r in private)
    assert not plan['future_actual_arrival_IDs_present']
    assert not plan['forecast_inputs']['current_CC4']['future_job_ids']
    for name in ('PLANNING_INPUTS','ACTUAL_INPUTS'):
        with np.load(DATA/'derived'/f'{name}.npz',allow_pickle=False) as z:
            assert z['capacities'].sum()==780
            assert z['total_gpu'].shape==(96,12)
            assert np.isfinite(z['PCC_P_kw']).all() and np.isfinite(z['PCC_Q_kvar']).all()
            assert (z['total_gpu']<=z['capacities']+1e-9).all()
    queue=read(REPORT/'VALIDATION_ACTUAL_QUEUE_AUDIT.json')
    assert queue['future_duration_controller_reads']==queue['future_end_controller_reads']==0
    assert queue['Actual_CC4_physical_GPU']==queue['Actual_global_reoptimization']==0

def test_forecast_cutoff_and_disclosed_holdout_scope():
    p=read(DATA/'sources/PLANNING_INPUT_BUNDLE.json')
    f=read(DATA/'sources/AEMO_FORECAST.json')
    issue=pd.Timestamp(p['issue_time'])
    assert issue==pd.Timestamp(f['cutoff_fixed_aest'])
    assert pd.Timestamp(f['demand_issue'])<=issue and pd.Timestamp(f['pv_issue'])<=issue
    weather=pd.read_parquet(DATA/'sources/GFS_D1_WEATHER.parquet')
    initialization=pd.DatetimeIndex(weather.ts_fixed_aest)-pd.to_timedelta(weather.lead_hours,unit='h')
    assert initialization.nunique()==1 and initialization[0]<=issue
    d=read(REPORT/'DATE_SELECTION_PREREGISTRATION.json')
    assert d['IEEE123_prior_exposed'] and not d['globally_pristine_holdout']
    assert not d['Actual_for_BG_GPU_port_selection']
    frozen=read(REPORT/'VALIDATION_PLANNING_INPUT_FREEZE.json')
    assert frozen['GFS_publication_before_cutoff']=='UNVERIFIED'

def test_stationary_schedule_respects_both_AC_limits_and_independent_SOC(monkeypatch):
    # Intercept artifact writers: testing the real schedule performs no AC,
    # external writes, prereg edits or mutation of current root output files.
    from ieee8500_v42_high import schedule as module
    captured={}
    monkeypatch.setattr(module,'write',lambda path,value:captured.__setitem__(path.name,value))
    monkeypatch.setattr(module,'table',lambda path,value:captured.__setitem__(path.name,list(value)))
    module.stationary_schedule()
    records=captured['MESS_SCHEDULE_SOC_96.csv']
    fleet=read(ROOT/'docs/ieee8500_v42_single_case/integration_contracts/RESEARCH_FLEET_CONFIGURATION.json')['initial_locations']
    assert len(records)==96*6 and len(set(fleet.values()))==6
    assert {(r['unit'],r['site']) for r in records}==set(fleet.items())
    eta=.95*.90
    for unit,site in fleet.items():
        selected=[r for r in records if r['unit']==unit]
        energy=1140.
        assert [r['slot'] for r in selected if r['P_charge_AC_kw']]==list(range(8,16))
        assert [r['slot'] for r in selected if r['P_discharge_AC_kw']]==list(range(68,76))
        for r in selected:
            ch,dis=r['P_charge_AC_kw'],r['P_discharge_AC_kw']
            assert 0<=ch<=5 and 0<=dis<=5 and ch*dis==0
            assert r['Q_kvar']==r['route_energy_kwh']==r['route_distance_km']==0
            assert r['port_occupancy_units']==1
            if r['slot']==0:assert ch==dis==0 and not r['available']
            energy+=.25*(eta*ch-dis/eta)
            assert abs(energy-r['E_after_kwh'])<1e-9
            assert 660<=energy<=1620
        assert abs(energy-1140)<1e-9
    assert captured['MESS_SCHEDULE_RECEIPT.json']['Pcharge_per_unit_kw']==5
    assert abs(captured['MESS_SCHEDULE_RECEIPT.json']['Pdischarge_per_unit_kw']-5*eta*eta)<1e-12

def test_May02_C0_input_adapter_has_exact_P5_keys():
    from ieee8500_v42_high.common import inputs
    expected={'sites','capacities','total_gpu','IT_kw','PCC_P_kw','PCC_Q_kvar','demand_mw','pv_mw','gross_factor','pv_factor'}
    for source in ('PLANNING','ACTUAL'):
        p=inputs('C0',source,'2025-05-02')
        assert p.resolve()==(DATA/'derived'/f'{source}_INPUTS.npz').resolve()
        with np.load(p,allow_pickle=False) as z:
            assert set(z.files)==expected|({'known_gpu','cc4_gpu'} if source=='PLANNING' else set())

@pytest.mark.parametrize('damage,message',[
    ('missing','PORT_AXIS_COVERAGE'),('duplicate','PORT_AXIS_COVERAGE'),
    ('nan','NONFINITE_PORT_READBACK'),('slot0','CONNECTION_DELAY')])
def test_saved_port_auditor_rejects_incomplete_nonfinite_or_unconnected_readback(monkeypatch,damage,message):
    from ieee8500_v42_high import schedule as module
    # Synthetic readback is exclusively a negative validator fixture, never AC evidence.
    records=[dict(slot=t,site=f'STA{i:02d}',P_kw=0.,Q_kvar=0.,S_kva=0.,I_max_A=0.,
        per_conductor_A=[0.,0.],per_conductor_PQ=[[0.,0.],[0.,0.]]) for t in range(96) for i in range(1,13)]
    if damage=='missing':records.pop()
    if damage=='duplicate':records[-1]=records[0].copy()
    if damage=='nan':records[0]['P_kw']=float('nan')
    if damage=='slot0':records[0]['P_kw']=1.
    monkeypatch.setattr(module,'read',lambda path:records)
    monkeypatch.setattr(module,'write',lambda path,value:None)
    with pytest.raises(AssertionError,match=message):module.audit_ac_ports('NEGATIVE_FIXTURE',[{} for t in range(96)])
