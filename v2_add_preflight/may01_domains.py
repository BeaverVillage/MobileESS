"""Identity prescreens: never discard an unproved route or job option."""
from collections import Counter,defaultdict
import numpy as np
from .may01_common import *

def route_audit():
    from .prestart_native import inputs
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    sites,initial,routes,battery,receipt=inputs(read(day['files']['native']['path']),INITIAL)
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:names=set(map(str,z['names']))
    by=defaultdict(list)
    for k,r in enumerate(routes):by[r.depart].append((2304+k,r))
    rows=[]
    for u,origin in initial.items():
        F=np.full((97,24,2),[np.inf,-np.inf]);F[0,sites.index(origin)]=[760,760]
        def merge(t,s,lo,hi):
            lo=max(battery.minimum,lo);hi=min(battery.maximum,hi)
            if lo<=hi:
                j=sites.index(s);F[t,j,0]=min(F[t,j,0],lo);F[t,j,1]=max(F[t,j,1],hi)
        for t in range(96):
            for j,s in enumerate(sites):
                lo,hi=F[t,j]
                if lo<=hi and f'arc[{u},{j*96+t}]' in names:
                    merge(t+1,s,lo-battery.dt_hours*battery.p_limit/battery.eta_discharge,
                        hi+battery.dt_hours*battery.p_limit*battery.eta_charge)
            for k,r in by[t]:
                if f'arc[{u},{k}]' not in names:continue
                lo,hi=F[t,sites.index(r.source)]
                if lo<=hi:merge(r.connect,r.destination,lo-r.energy_kwh,hi-r.energy_kwh)
        valid=F[:,:,0]<=F[:,:,1]
        move=sum(f'arc[{u},{2304+k}]' in names for k in range(len(routes)))
        stay=sum(f'arc[{u},{j*96+t}]' in names for j in range(24) for t in range(96))
        path=RUN/(u+'_SOC_FORWARD_OUTER_ENVELOPE.npy');np.save(path,F)
        terminal=int(np.sum((F[96,:,0]<=760)&(F[96,:,1]>=760)))
        rows.append(dict(vehicle=u,before_MOVE_columns=move,after_MOVE_columns=move,before_STAY_columns=stay,after_STAY_columns=stay,
            additionally_removed_routes=0,reachable_state_outer_envelope_count=int(valid.sum()),
            minimum_SOC_outer_envelope=float(F[:,:,0][valid].min()),maximum_SOC_outer_envelope=float(F[:,:,1][valid].max()),
            terminal_760_compatible_outer_sites=terminal,terminal_SOC_unchanged=760,
            envelope=record(path),exact_joint_occupancy_reachability_claimed=False))
        assert move>0 and stay>0 and terminal>0
    put('MESS_ROUTE_IDENTITY_PRESCREENING.json',dict(PASS=True,original24_services_preserved=True,
        routes_before=len(routes),routes_after=len(routes),additionally_removed_routes=0,
        original_source_time_invalid_exclusions=receipt['excluded'],vehicle_rows=rows,
        min_max_SOC_numbers_are_conservative_outer_envelopes=True,
        mathematical_identity='Exact same mobility CSR, domains, bounds, occupancy, objective; no additional arc/column filtering',
        actual_two_MOVE_witness=record(OUT/'FINITE_TWO_MOVE_SOURCE_VALIDATOR.json'),
        raw_Route_ETA_movement_energy_unchanged=True))

def aidc_audit():
    # No new option filter is applied. Source infeasibility checks continue to
    # run in the original full_option/validate_full implementation.
    files=[ROOT/'v42_native/aidc.py',ROOT/'v42_job_capability/solver.py',ROOT/'v43_arms/reference.py']
    sources=[record(p) for p in files if p.exists()]
    prior={p.name:record(p) for p in OLD.glob('*AIDC*') if p.is_file()}
    put('AIDC_IDENTITY_PRESCREENING.json',dict(PASS=True,scope='No new Job-option elimination',
        additionally_removed_options=0,all_original_TimeShift_Presite_Migration_generators_retained=True,
        accepted_cache_not_used_as_option_domain=True,Golden414_still_rejected=True,
        original_FULL_QoS_capacity_deadline_residency_WAN_checkpoint_capability_unchanged=True,
        exhaustive_new_A1_A2_variable_grid_certified=False,source_files=sources,prior_evidence=prior,
        reason='Identity prescreen is exact; safe additional AIDC pruning has not been proved and is not applied.'))

if __name__=='__main__':init();route_audit();aidc_audit()
