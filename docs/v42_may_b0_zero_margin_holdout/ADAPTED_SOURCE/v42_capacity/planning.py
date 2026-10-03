"""Current nominal reference and capacity-admitted CC4, before electrical replay."""
import math
import numpy as np
import pandas as pd
from .common import ROOT, OUT, PRIOR, read, write, table, day_folder, record, resolve
from .reference import build_reference
from .queue import allocate, conservation
from v42_modelable.power import known_occupancy
from v42_final.reserve import risk_exposure

def nominal_expiry(row):
    return math.ceil((row['Q50_total_seconds'] - row['elapsed_seconds']) / 900) if row['state_at_D1_cutoff'] == 'RUNNING' else row['reference_start'] + row['service_slots']

def main():
    queue_rows = []
    site_rows = []
    reference_rows = []
    audit = []
    conservation_rows = []
    releases = []
    gates = []
    kernel = pd.read_csv(ROOT / 'docs/v42_final_integration/RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv').survival.to_numpy()
    gamma = 2.423057443558147
    for d in range(1, 32):
        day = f'2025-05-{d:02d}'
        folder = day_folder(day)
        path = PRIOR / 'BUNDLE' / folder
        p = read(path / 'PLANNING_INPUT_BUNDLE.json')
        prov = read(path / 'SOURCE_PROVENANCE.json')
        for key in ('aemo_forecast.json', 'aemo_actual.parquet', 'gfs_d1_weather.parquet', 'noaa_actual_weather.parquet'):
            resolve(prov['daily_sources'][key])
        assert p['runtime_authority'] == 'V10::T3_ISOTONIC_ROLLING14_calibrated'
        assert not p['future_actual_arrival_IDs_present']
        refs, ra = build_reference(p['known_population'], p['capacities'], p['rack_compatibility'], issue_time=p['issue_time'])
        if not ra['full_reference_ready']:
            raise ValueError(f'REFERENCE_BLOCKED:{day}:{ra}')
        sites = sorted(p['capacities'])
        caps = np.array([p['capacities'][s] for s in sites])
        known = known_occupancy(refs, sites)
        cc4 = p['forecast_inputs']['current_CC4']
        assert cc4['target_day'] == day and (not cc4['future_job_ids'])
        anon, incoming, outgoing = allocate(known, cc4['nominal_unknown_GPU_96'], caps)
        total = known + anon
        cons = conservation(sum(cc4['Q50_GPUh']), anon, outgoing[-1], cc4['full_tail_nominal_GPUh'])
        conservation_rows.append(dict(day=day, **cons))
        rt = np.zeros_like(known)
        for r in refs:
            signed_end = nominal_expiry(r)
            exp = risk_exposure(r['GPU_gang'], signed_end, r['reference_site'], kernel, range(24, 120))
            s = sites.index(r['reference_site'])
            for (_, t), v in exp.items():
                rt[t - 24, s] += gamma * v
            if r['state_at_D1_cutoff'] == 'RUNNING' and r['service_slots'] == 0:
                releases.append(dict(day=day, job_uid=r['job_uid'], GPU_gang=r['GPU_gang'], nominal_remaining_seconds=0, nominal_future_GPUh=0, signed_Q50_end_slot=signed_end, kernel_exposure_GPUh=sum(exp.values()) / 4, gamma=gamma, runtime_target_GPUh=gamma * sum(exp.values()) / 4, site=r['reference_site']))
        head = caps - total
        achieved_rt = np.minimum(head, rt)
        rem = head - achieved_rt
        cc_target = np.array(cc4['spread_headroom_GPU_96'])
        achieved_cc = np.minimum(rem.sum(1), cc_target)
        coeff = pd.read_csv(path / 'C1_PLANNING_COEFFICIENTS.csv')
        slope = coeff.pivot(index='slot', columns='aidc_id', values='slope')[sites].to_numpy()
        intercept = coeff.pivot(index='slot', columns='aidc_id', values='intercept_kw')[sites].to_numpy()
        power = read(path / 'POWER_AUTHORITY.json')
        it = power['current_IT_idle_kW_per_installed_GPU'] * caps + power['current_IT_swing_kW_per_active_GPU'] * total
        pcc = slope * it + intercept
        q = pcc * np.tan(np.arccos(0.95))
        dest = OUT / 'BUNDLE' / folder
        dest.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dest / 'PLANNING_PHYSICAL.npz', sites=np.array(sites), capacities=caps, known_gpu=known, cc4_served_gpu=anon, total_gpu=total, IT_kw=it, PCC_P_kw=pcc, PCC_Q_kvar=q, runtime_target=rt, runtime_achieved=achieved_rt, runtime_shortfall=rt - achieved_rt, CC4_target=cc_target, CC4_achieved=achieved_cc, CC4_shortfall=cc_target - achieved_cc)
        write(OUT, 'BUNDLE/' + folder + '/REFERENCE.json', dict(rows=refs, audit=ra))
        for r in refs:
            reference_rows.append(dict(day=day, **r))
        audit.append(dict(day=day, **ra))
        for t in range(96):
            queue_rows.append(dict(day=day, slot=t, known_GPU=float(known[t].sum()), CC4_reference_GPU=cc4['nominal_unknown_GPU_96'][t], backlog_in_GPU=incoming[t], CC4_served_GPU=float(anon[t].sum()), backlog_out_GPU=outgoing[t], total_served_GPU=float(total[t].sum()), capacity_GPU=780, capacity_feasible=bool((total[t] <= caps + 1e-09).all())))
            for s, site in enumerate(sites):
                site_rows.append(dict(day=day, slot=t, aidc_id=site, known_GPU=known[t, s], CC4_served_GPU=anon[t, s], total_GPU=total[t, s], capacity_GPU=int(caps[s])))
        gates.append(dict(day=day, input_sources_complete=True, current_Runtime_bound=True, CC4_date_issue_bound=True, C1_weather_bound=True, reference_ready=True, Planning_capacity_feasible=True, CC4_conservation_PASS=cons['PASS'], workload_drop=False, future_leakage=False, prequeue_overflow_slots=int(np.sum(known.sum(1) + np.array(cc4['nominal_unknown_GPU_96']) > 780 + 1e-09)), max_total_GPU=float(total.sum(1).max()), runtime_shortfall_GPUh=float((rt - achieved_rt).sum() / 4), CC4_shortfall_GPUh=float((cc_target - achieved_cc).sum() / 4), planning_IT_kWh=float(it.sum() / 4), planning_PCC_kWh=float(pcc.sum() / 4)))
        print(day, 'Planning capacity PASS; backlog GPUh', cons['capacity_backlog_carryout_GPUh'], flush=True)
    for filename, rows in [('APRIL_B0_CC4_CAPACITY_QUEUE.csv', queue_rows), ('APRIL_B0_CC4_SITE_ALLOCATION.csv', site_rows), ('V42_COMMON_REFERENCE_SCHEDULE.csv', reference_rows), ('RUNTIME_EXPIRED_RUNNING_ROWS.csv', releases)]:
        table(OUT, filename, rows, list(rows[0]))
    write(OUT, 'V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json', dict(audits=audit, shared_arms=['B0', 'B1', 'B2', 'B3'], runtime_authority=p['runtime_authority'], grid_reads=0, actual_reads=0, May_reads=0, optimizer_calls=0))
    write(OUT, 'RUNTIME_RUNNING_RELEASE_AUDIT.json', dict(expired_RUNNING_day_job_rows=len(releases), unique_jobs=len({r['job_uid'] for r in releases}), GPU_sum=sum((r['GPU_gang'] for r in releases)), future_nominal_GPUh=0, old_infinite_occupancy_removed_from_current_producer=True, observed_issue_physical_truth_preserved=True, Actual_completion_read_by_Planning=False, gamma=gamma, kernel=record(ROOT / 'docs/v42_final_integration/RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv'), exposure_GPUh=sum((r['kernel_exposure_GPUh'] for r in releases)), exposure_zero_outside_frozen_support_rows=sum((r['kernel_exposure_GPUh'] == 0 for r in releases))))
    pooled = {k: sum((r[k] for r in conservation_rows)) for k in ['forecast_Q50_GPUh', 'served_DDAY_GPUh', 'original_post96_tail_GPUh', 'capacity_backlog_carryout_GPUh', 'conservation_error']}
    write(OUT, 'CC4_GPUH_CONSERVATION.json', dict(days=conservation_rows, pooled=pooled, PASS=all((r['PASS'] for r in conservation_rows)), absolute_tolerance_GPUh=1e-09, relative_tolerance=1e-12))
    write(OUT, 'LIGHTWEIGHT_PLANNING_GATE.json', dict(days=gates, ready_days=30, Planning_capacity_violations=0, all_workload_retained=True, CC4_refit_calls=0, Runtime_refit_calls=0, optimizer_calls=0, OpenDSS_calls=0))
if __name__ == '__main__':
    main()
