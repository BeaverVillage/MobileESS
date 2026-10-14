"""Finite Planning-only spatial CC4 service alternatives with exact CDF mass.

Redistribution changes sites, retaining every cohort x[h,t], carry and timing.
Profiles are replacement scenarios, never added together or physical bookings.
No temporal redistribution is authorized without a separate CDF certificate.
"""
from copy import deepcopy
import numpy as np
from .policy import digest


def spatial_frames(nominal,sites,remaining_slot,*,fractions=(1.,),preserve_reference=None):
    base=np.asarray(nominal['nominal_site_GPU'],float)
    frames=[dict(frame_id='BASE',delta=np.zeros_like(base),certificate=dict(Q50_CDF_and_mass_unchanged=True,
        cohort_x_unchanged=True,carryout_unchanged=True,site_projection_max_error=0.))]
    for donor in range(len(sites)):
        for recipient in range(len(sites)):
            if donor==recipient:continue
            for fraction in fractions:
                if not 0<fraction<=1:raise ValueError('SPATIAL_FRACTION_AUTHORITY')
                reserved=np.zeros(len(base)) if preserve_reference is None else np.asarray(preserve_reference)[:,donor]
                delta=np.zeros_like(base);amount=np.maximum(0.,base[remaining_slot:,donor]-reserved[remaining_slot:])*fraction
                if not np.any(amount):continue
                delta[remaining_slot:,donor]-=amount;delta[remaining_slot:,recipient]+=amount
                projected=base+delta
                error=float(np.max(np.abs(projected.sum(axis=1)-base.sum(axis=1))))
                if error>1e-9 or np.any(projected<-1e-9):raise ValueError('Q50_SPATIAL_CDF_MASS_CHANGED')
                sparse=[[int(t),sites[j],float(delta[t,j])] for t,j in zip(*np.nonzero(delta))]
                frames.append(dict(frame_id=digest(sparse),delta=delta,sparse_site_GPU_delta=sparse,
                    certificate=dict(Q50_CDF_and_mass_unchanged=True,cohort_x_unchanged=True,carryout_unchanged=True,
                        nominal_service_parent_sha=nominal['nominal_service_sha'],site_projection_max_error=error,
                        minimum_nominal_GPU=float(projected.min()),past_slots_changed=0,
                        reference_forecast_share_not_reallocated=True,
                        original_cohort_CDF_receipt=deepcopy(nominal['replay']))))
    return frames
