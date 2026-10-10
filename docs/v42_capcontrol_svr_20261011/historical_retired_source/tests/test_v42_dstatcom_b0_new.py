"""B0 raw-input arithmetic and causality fixtures; no E2E claim or DSS solves."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from v42_dstatcom import b0_new as subject
from v42_b3_joint.contracts import canonical


@dataclass
class Coefficient:
    slope:float=2.
    intercept_kw:float=3.


@pytest.fixture
def inputs(tmp_path):
    folder=tmp_path/'INPUT';folder.mkdir()
    stamps=pd.date_range('2025-05-01T00:15:00+10:00',periods=96,freq='15min').astype(str).tolist()
    forecast=dict(timestamps_96=stamps,demand_mw_96=[100.]*96,pv_mw_96=[10.]*96,
        demand_issue='2025-04-30T08:00:00+00:00',pv_issue='2025-04-30T08:00:00+00:00',
        cutoff_fixed_aest='2025-04-30T18:00:00+10:00')
    subject._write(folder/'forecast.json',forecast)
    pd.DataFrame(dict(t_wb_c=[20.]*96,rh_pct=[50.]*96)).to_parquet(folder/'weather.parquet',index=False)
    sites={f'AIDC{i:02d}':65 for i in range(1,13)}
    from v42_final.common import MODEL
    known=dict(job_uid='known',submit_time='2025-04-30T07:00:00+00:00',state_at_D1_cutoff='PENDING',
        source_site=None,source_site_authority=None,GPU_gang=4,service_slots=1,nominal_remaining_seconds=900.,
        Q50_total_seconds=900.,elapsed_seconds=0.,runtime_authority=MODEL,compatible_sites=list(sites))
    planning=dict(day='2025-05-01',slots=96,capacities=sites,rack_compatibility={s:[65] for s in sites},
        known_population=[known],future_actual_arrival_IDs_present=False,input_gate_PASS=True,
        issue_time='2025-04-30T08:00:00+00:00',forecast_inputs=dict(AEMO=forecast,current_CC4=dict(
            target_day='2025-05-01',future_job_ids=[],nominal_unknown_GPU_96=[10.]*96,Q50_GPUh=[240.],full_tail_nominal_GPUh=0.)))
    subject._write(folder/'PLANNING_INPUT_BUNDLE.json',planning)
    subject._write(folder/'SOURCE_PROVENANCE.json',dict(day='2025-05-01',daily_sources={
        'aemo_forecast.json':subject.record(folder/'forecast.json'),
        'gfs_d1_weather.parquet':subject.record(folder/'weather.parquet')}))
    subject._write(folder/'POWER_AUTHORITY.json',dict(current_IT_idle_kW_per_installed_GPU=.1,
        current_IT_swing_kW_per_active_GPU=.5))
    (folder/'ACTUAL_INPUT_BUNDLE.json').write_text('THIS_ACTUAL_FILE_MUST_NOT_BE_READ_BY_PLANNING')
    # A previous solution/model point trap remains physically adjacent.
    (folder/'PLANNING_PHYSICAL.npz').write_text('OLD_SOLUTION_MUST_NOT_BE_READ')
    (folder/'V_PLAN.npz').write_text('OLD_MODEL_POINT_MUST_NOT_BE_READ')
    module=SimpleNamespace(endpoint_secant=lambda *args:Coefficient(),exact_c1_pcc_kw=lambda it,*args:it*2+3)
    return folder,module


def test_new_planning_regenerates_source_reference_cc4_c1_and_never_reads_old_or_actual(inputs,tmp_path):
    folder,module=inputs
    with patch.object(subject,'_c1',return_value=(module,None,[])):
        result=subject.build_planning('2025-05-01',folder,tmp_path/'new')
    arrays=result['arrays']
    assert np.array_equal(arrays['GPU'][:,0],np.full(96,10.))
    assert not arrays['GPU'][:,1:].any()
    assert np.array_equal(arrays['PCC_P_kw'],2*arrays['IT_kw']+3)
    assert result['receipt']['Actual_arrays_or_service_truth_reads']==0
    assert result['receipt']['old_solution_schedule_or_modelpoint_reads']==0
    assert result['receipt']['Native_optimizer_calls']==0
    assert result['receipt']['CC4_conservation']['PASS'] is True
    assert (tmp_path/'new/REFERENCE.json').exists()
    with np.load(tmp_path/'new/PLANNING_PHYSICAL.npz') as archive:
        assert np.array_equal(archive['PCC_P_kw'],arrays['PCC_P_kw'])


def test_future_forecast_source_is_rejected_before_power_generation(inputs,tmp_path):
    folder,module=inputs
    p=subject._read(folder/'PLANNING_INPUT_BUNDLE.json');f=p['forecast_inputs']['AEMO']
    f['pv_issue']='2025-05-01T00:00:00+00:00'
    (folder/'PLANNING_INPUT_BUNDLE.json').write_text(canonical(p))
    (folder/'forecast.json').write_text(canonical(f))
    prov=subject._read(folder/'SOURCE_PROVENANCE.json');prov['daily_sources']['aemo_forecast.json']=subject.record(folder/'forecast.json')
    (folder/'SOURCE_PROVENANCE.json').write_text(canonical(prov))
    with pytest.raises(ValueError,match='FUTURE_FORECAST_VINTAGE'):
        subject.build_planning('2025-05-01',folder,tmp_path/'new')
    assert not (tmp_path/'new').exists()


def make_archive(tmp_path,*,missing=False):
    member='jobs/year=2025/month=5/source.parquet'
    frame=pd.DataFrame(dict(id=['100'],submit_time=pd.to_datetime(['2025-05-01T00:00:00+10:00']),
        start_time=pd.to_datetime(['2025-05-01T00:00:00+10:00']),
        end_time=pd.to_datetime([None if missing else '2025-05-01T00:15:00+10:00'])))
    path=tmp_path/'raw.zip'
    with zipfile.ZipFile(path,'w') as archive: archive.writestr(member,frame.to_parquet(index=False))
    population=[dict(job_uid='100',source_member=member,source_row=0)]
    return population,subject.record(path)


def test_new_actual_truth_is_joined_from_exact_raw_source_row_not_saved_realization(tmp_path):
    population,receipt=make_archive(tmp_path)
    truth,checked=subject._truth(population,receipt)
    assert checked==receipt and truth['100']['realized_seconds']==900.
    assert truth['100']['private_future_duration_hidden_from_controller'] is True
    population[0]['job_uid']='200'
    with pytest.raises(ValueError,match='EXACT_REALIZED_UID_SOURCE_JOIN'):
        subject._truth(population,receipt)


def test_missing_raw_actual_service_cannot_use_q50_or_zero_fallback(tmp_path):
    population,receipt=make_archive(tmp_path,missing=True)
    with pytest.raises(ValueError,match='REALIZED_SERVICE_MISSING_NO_IMPUTATION'):
        subject._truth(population,receipt)


def test_actual_descriptor_and_truth_unavailable_before_new_planning_freeze(inputs,tmp_path):
    folder,module=inputs
    with patch.object(subject,'_c1',return_value=(module,None,[])):
        plan=subject.build_planning('2025-05-01',folder,tmp_path/'plan')
    subject._write(tmp_path/'bad_freeze.json',dict(schema=subject.VERSION,Planning_frozen=False,day='2025-05-01'))
    with pytest.raises(ValueError,match='PLANNING_FREEZE_BEFORE_ACTUAL_REQUIRED'):
        subject.build_actual(plan,folder,tmp_path/'actual',tmp_path/'bad_freeze.json')
    assert not (tmp_path/'actual').exists()


def test_real_may01_integer96_descriptor_generates_new_plan_without_dss_or_old_solution(tmp_path):
    folder=Path(r'D:/ChatGPT/Mobile ESS 2/v42_transformer_normalamps_pr/docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE/DAY_20250501')
    if not folder.exists(): pytest.skip('Original immutable May01 descriptor unavailable')
    assert subject._read(folder/'PLANNING_INPUT_BUNDLE.json')['slots']==96
    from v42_regcontrol import authority
    with patch.object(authority,'compile_verified',side_effect=AssertionError('Planning input generation must not invoke DSS')):
        result=subject.build_planning('2025-05-01',folder,tmp_path/'new_source_plan')
    assert result['arrays']['PCC_P_kw'].shape==(96,12)
    assert result['receipt']['Native_optimizer_calls']==0
    assert result['receipt']['old_solution_schedule_or_modelpoint_reads']==0


def test_original_frozen_trajectory_tuple_locations_bind_same_hash_as_equivalent_array():
    from v42_dstatcom.integration import _trajectory_sha
    from types import SimpleNamespace
    values=dict(day='2025-05-01',case='B0',namespace='ACTUAL',
        pcc_p_kw=np.zeros((96,12)),pcc_q_kvar=np.zeros((96,12)),
        mess_p_kw=np.zeros((96,4)),mess_q_kvar=np.zeros((96,4)))
    locations=tuple(tuple('DEPOT' for _ in range(4)) for _ in range(96))
    original=SimpleNamespace(**values,mess_locations_96x4=locations)
    normalized=SimpleNamespace(**values,mess_locations_96x4=np.asarray(locations))
    assert _trajectory_sha(original)==_trajectory_sha(normalized)
