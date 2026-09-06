"""Actual execution occupancy -> frozen CENTER power -> observed-weather C1."""
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import reference
from .contracts import BEGIN, H, ReplayError
from .pre_day_complete import audit_exclusion
from .capacity_audit import compare_occupancy, check_it_power


def power_from_execution(repo, replay, capacity, weather):
    from dayahead.v39a.power import site_it_power_kw, aggregate_it_power_kw
    from dayahead.v39a.contracts import IDLE_W_PER_GPU, CENTER_SWING_W_PER_GPU
    from dayahead.v28r2.c1_affine import load_c1, exact_c1_pcc_kw
    from dayahead.v36.contracts import PF_TAN
    sites = sorted(capacity)
    occupancy, contributions, occupancy_audit = compare_occupancy(replay,capacity)
    audit_exclusion(replay["pre_day_complete"], replay["rack_ledger"], contributions)
    it = np.asarray([[float(site_it_power_kw(capacity[s], int(occupancy[t,i]))) for i,s in enumerate(sites)] for t in range(96)])
    independent = np.asarray([[float((Decimal(capacity[s])*IDLE_W_PER_GPU + Decimal(int(occupancy[t,i]))*CENTER_SWING_W_PER_GPU)/Decimal(1000))
                               for i,s in enumerate(sites)] for t in range(96)])
    if not np.array_equal(it, independent):
        raise ReplayError("ACTUAL_IT_MODEL_RECALCULATION_FAIL")
    aggregate_error = max(abs(sum(site_it_power_kw(capacity[s], int(occupancy[t,i])) for i,s in enumerate(sites))
                              -aggregate_it_power_kw(int(occupancy[t].sum()))) for t in range(96))
    power_conservation = check_it_power(capacity,occupancy,it)
    c1_path = Path(repo) / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
    c1 = load_c1(c1_path)
    pcc = np.asarray([exact_c1_pcc_kw(it[t], float(weather.iloc[t].t_wb_c), float(weather.iloc[t].rh_pct), c1) for t in range(96)])
    q = pcc * PF_TAN
    if not np.isfinite(pcc).all() or pcc.shape != (96, 12):
        raise ReplayError("ACTUAL_C1_POWER_AXIS")
    frame = pd.DataFrame({"slot": np.repeat(np.arange(96),len(sites)), "site_id": np.tile(sites,96),
        "occupied_GPU": occupancy.ravel(), "GPU_capacity": np.tile([capacity[s] for s in sites],96),
        "P_IT_kW": it.ravel(), "P_PCC_kW": pcc.ravel(), "Q_PCC_kvar": q.ravel(),
        "observed_t_wb_c": np.repeat(weather.t_wb_c.to_numpy(),len(sites)), "observed_rh_pct": np.repeat(weather.rh_pct.to_numpy(),len(sites)),
        "field_role": "ACTUAL_EXECUTION_ONLY"})
    return {"occupancy": occupancy, "IT": it, "PCC_P": pcc, "PCC_Q": q, "frame": frame,
        "job_slot_contributions": contributions,
        "occupancy_audit": occupancy_audit,
        "power_audit": {**power_conservation, "IT_recomputed_from_actual_occupancy": True, "IT_independent_recalculation_bit_equal": True,
            "site_to_aggregate_IT_max_error_kW": str(aggregate_error), "CENTER_mapping": reference(Path(repo)/"dayahead/v39a/power.py"),
            "C1_model": reference(c1_path), "C1_applications_in_physical_chain": 1,
            "C1_thermal_input": "OBSERVED_WEATHER", "additional_beta_or_PUE_multiplier": 0,
            "DayAhead_power_arrays_copied": False, "per_job_CPU_or_host_power_invented": False}}
