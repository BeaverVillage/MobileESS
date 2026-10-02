"""Grid-independent forward service backlog; reserve never enters electrical load."""
import numpy as np


def allocate(known, reference, capacities):
    known = np.asarray(known, float)
    reference = np.asarray(reference, float)
    caps = np.asarray(capacities, float)
    if known.ndim != 2 or reference.shape != (len(known),) or caps.shape != (known.shape[1],):
        raise ValueError('CAPACITY_AXIS')
    if not all(np.isfinite(x).all() for x in (known, reference, caps)) or (known < 0).any() or (reference < 0).any() or (caps <= 0).any() or (known > caps + 1e-9).any():
        raise ValueError('PHYSICAL_KNOWN_CAPACITY')
    served = np.zeros_like(known)
    incoming = np.zeros(len(known)); outgoing = incoming.copy()
    backlog = 0.
    for t in range(len(known)):
        incoming[t] = backlog
        demand = float(reference[t]) + backlog
        for s, cap in enumerate(caps):
            take = min(demand, max(0., cap - known[t, s]))
            served[t, s] = take
            demand -= take
        backlog = demand
        outgoing[t] = backlog
    assert (known + served <= caps + 1e-9).all()
    assert abs(served.sum() + backlog - reference.sum()) <= 1e-9 + 1e-12 * reference.sum()
    return served, incoming, outgoing


def conservation(forecast_gpuh, served, carryout_gpu, original_tail_gpuh):
    got = float(np.sum(served) / 4 + carryout_gpu / 4 + original_tail_gpuh)
    error = got - forecast_gpuh
    result = dict(forecast_Q50_GPUh=float(forecast_gpuh), served_DDAY_GPUh=float(np.sum(served) / 4),
        original_post96_tail_GPUh=float(original_tail_gpuh), capacity_backlog_carryout_GPUh=float(carryout_gpu / 4),
        conservation_error=float(error), PASS=bool(abs(error) <= 1e-9 + 1e-12 * abs(forecast_gpuh)))
    if not result['PASS']: raise ValueError('CC4_GPUH_CONSERVATION')
    return result
