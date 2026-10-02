"""Project only April prediction rows; source ledger is metadata, never labels."""
import zipfile
import numpy as np
import pandas as pd
from v42_april_port.audit import read, record, checked, write
from v42_april_port.builder import axis, timestamp
from v42_final.workload import profile
from .freeze import ROOT, OUT

def april_projection(path, indices):
    with zipfile.ZipFile(path) as z, z.open('q.npy') as f:
        version = np.lib.format.read_magic(f)
        shape, fortran, dtype = np.lib.format._read_array_header(f, version)
        if fortran or shape[1:] != (24,2) or dtype != np.dtype('float64'):
            raise ValueError('CC4_ARRAY_SCHEMA')
        offset = f.tell(); size = 48 * dtype.itemsize
        rows = []
        for index in indices:
            f.seek(offset + index*size)
            rows.append(np.frombuffer(f.read(size), dtype=dtype).copy().reshape(24,2))
    return np.array(rows), shape

def bind():
    authority_path = ROOT.parent/'v42_integrated_pr/docs/v42_final/AGGREGATE_BINDING.json'
    interface = read(authority_path)['interface']
    paths = {k:checked(interface[k]) for k in ('prediction','ledger','selection')}
    ledger = pd.read_csv(paths['ledger'], usecols=['target_day','issue_time'])
    selected = ledger[ledger.target_day.between('2025-04-01','2025-04-30')]
    if selected.target_day.tolist() != ['2025-04-%02d'%d for d in range(1,31)]:
        raise ValueError('APRIL_CC4_DATE_AXIS')
    q, shape = april_projection(paths['prediction'], selected.index.tolist())
    if not np.isfinite(q).all() or (q<0).any() or (q[:,:,0]>q[:,:,1]).any():
        raise ValueError('CC4_QUANTILE_SCHEMA')
    # This current V42 interface binds the raw named prediction archive.
    # Do not add an unbound calibration delta, rescale or refit the forecaster.
    kernel_path = ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv'
    kernel = pd.read_csv(kernel_path, usecols=['lag_slot','kappa'])
    days = {}
    for pos, row in enumerate(selected.itertuples()):
        issue = axis(row.target_day)[0]
        if timestamp(issue) != timestamp(row.issue_time):
            raise ValueError('CC4_D1_ISSUE_MISMATCH')
        nominal = profile(q[pos,:,0], kernel.kappa.to_numpy())
        reserve = profile(q[pos,:,1]-q[pos,:,0], kernel.kappa.to_numpy())
        days[row.target_day] = dict(target_day=row.target_day, issue_time=row.issue_time,
            prediction_index=int(row.Index), Q50_GPUh=q[pos,:,0].tolist(), Q90_GPUh=q[pos,:,1].tolist(),
            nominal_unknown_GPU_96=nominal[:96].tolist(), spread_headroom_GPU_96=reserve[:96].tolist(),
            full_tail_nominal_GPUh=float(nominal[96:].sum()*.25), future_job_ids=[],
            unknown_placement_optimized=False, unknown_profile_site_allocation_bound=False)
        write(OUT, 'CC4/DAY_'+row.target_day.replace('-','')+'.json', days[row.target_day])
    code = paths['prediction'].parent.parent/'experiment.py'
    write(OUT, 'CC4/APRIL_CC4_BINDING.json', dict(date_bound=True, days_bound=30,
        interface_source=record(authority_path), source_interface=interface,
        array_shape=shape, interpreted_prediction_indices=selected.index.tolist(),
        model=interface['model'], units='hourly arrival lifetime GPUh; TRAIN-only execution-lag convolution',
        kernel=record(kernel_path), causal_implementation=record(code),
        causal_rule='label_matured_at < refit_issue <= forecast_issue',
        per_fit_receipts_available=(code.parent/'fits'/interface['model']).exists(),
        historical_ingestion_latency_certified=False, model_selection_retrospective=True,
        causal_implementation_rule_verified=True, new_fit_calls=0, forecast_modifications=0,
        May_prediction_rows_interpreted=[], May_outcomes_used=False,
        physical_modelability_target_refit=False,
        limitations=['Current interface target is inherited CC4 hourly arrival population; no per-job modelability rescaling performed.',
                    'Date and issue binding do not certify unexported historical fit/ingestion receipts.']))
    return days
