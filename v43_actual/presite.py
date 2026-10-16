"""V43 PENDING-only adapter over the existing signed original-grid scorer."""
from copy import deepcopy
import math
from time import perf_counter

from .vendor.aidc_sensitivity_runtime import SignedSensitivityPolicy
from .vendor.policy import _receipt, digest
from .vendor.trajectory_tracking import require_tracking_public


def change_authority(metadata, site, now):
    """Initial study placement is separate from source change/data/WAN rights."""
    require_tracking_public(metadata)
    if metadata.get('state') != 'PENDING':
        return 'PENDING_ONLY_RUNNING_MOVE_HOLD'
    if metadata.get('can_prestart_place') is not True:
        return 'SOURCE_PREPLACEMENT_AUTHORITY_MISSING'
    authority = metadata.get('source_presite_authority', {})
    payload = {k:v for k,v in authority.items() if k != 'authority_sha'}
    if (authority.get('authority_sha') != digest(payload)
            or authority.get('scope') != 'SOURCE_VERIFIED_UID_DESTINATION_PRESTART'
            or authority.get('uid') != metadata['uid']
            or site not in authority.get('destinations', ())
            or not authority.get('source_sha')
            or authority.get('observed_at_seconds', math.inf) > now):
        return 'SOURCE_UID_DESTINATION_CONSENT_NOT_VERIFIED'
    ready = metadata.get('source_data_ready', {}).get(site, {})
    if (not ready.get('source_sha') or ready.get('uid') != metadata['uid']
            or ready.get('observed_at_seconds', math.inf) > now
            or ready.get('ready_at_seconds', math.inf) > now
            or ready.get('requires_new_transfer') is not False):
        return 'SOURCE_DATA_WAN_READY_NOT_VERIFIED'
    return None


class PendingPresitePolicy(SignedSensitivityPolicy):
    """C0 and Strict C1 share designation, timing and hard guards.

    Current admission is independently supplied by the original-hardware AC
    adapter. Forecast scoring remains the original signed electrical model.
    Migration and deliberate time shifts are outside this PENDING-only gate.
    """
    def __init__(self, *args, variant, current_ac_guard, **kwargs):
        if variant not in ('C0','C1') or not callable(current_ac_guard):
            raise ValueError('V43_VARIANT_AND_CURRENT_AC_GUARD_REQUIRED')
        super().__init__(*args, basic=False, runtime_repair=False, **kwargs)
        self.variant = variant
        self.current_ac_guard = current_ac_guard
        self.spec.update(V43_contract='PR189_FROZEN_KNOWN_PENDING_PRESITE_V1',
            variant=variant, initial_designation='CAUSAL_GRID_BLIND_REFERENCE',
            presite='SOURCE_UID_DESTINATION_AND_READY_DATA_STRICTLY_BETTER_THAN_BASIC',
            intentional_delay=False, running_migration='R2_HOLD',
            original_7_RegControl_hardware_required=True)
        self.sha = digest(self.spec)

    def current_guard(self, metadata, segments, now, observed):
        reason = super().current_guard(metadata, segments, now, observed)
        return reason or self.current_ac_guard(metadata, segments, now, observed)

    def select(self, metadata, receipt, now, reservations, *, reserve=True):
        began = perf_counter()
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if (metadata.get('state') != 'PENDING' or metadata['submit_seconds'] > now
                or metadata.get('is_observed') is not True):
            return self._record(metadata, now, dict(action='QUEUE',status='OBSERVED_PENDING_REQUIRED'),began,0,[])
        if now % 900 or self.current is None or self.current[0] != now:
            raise ValueError('CURRENT_OBSERVED_CONTROL_TICK_REQUIRED')
        r = _receipt(receipt)
        origin = math.ceil(max(now,r['reference_start_seconds'],metadata.get('release_seconds') or -math.inf,
            metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        basic = metadata['reference_site']
        if origin > now:
            return self._record(metadata,now,dict(action='QUEUE',status='CAUSAL_REFERENCE_NOT_READY'),began,0,[])
        baseline, _ = self._public_future(reservations, metadata['uid'])
        if self.anonymous_residual_audit['status'] not in (
                'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS','ZERO_ANONYMOUS_FORECAST'):
            return self._record(metadata,now,dict(action='QUEUE',status='CC4_CONSERVATION_NOT_CERTIFIED'),began,0,[])
        candidates, rejected = {}, []
        sites = [basic] + sorted(set(metadata['compatible_sites'])-{basic})
        for site in sites:
            changing = site != basic
            reason = None
            if site not in metadata['compatible_sites']:
                reason = 'SOURCE_SITE_INCOMPATIBLE'
            elif changing:
                reason = 'C0_BASIC_SITE_ONLY' if self.variant == 'C0' else change_authority(metadata,site,now)
            if reason is None and metadata['gpu'] > max(self.packet.rack_compatibility[site]):
                reason = 'RACK_GANG_INCOMPATIBLE'
            end = now + max(metadata['t50_seconds'],1e-9)
            if reason is None and any(metadata.get(k) is not None and value > metadata[k]
                    for k,value in (('hard_latest_start_seconds',now),('completion_deadline_seconds',end))):
                reason = 'SOURCE_HARD_WINDOW'
            segments = [dict(resource='gpu:'+site,begin=now,end=end,quantity=metadata['gpu'])]
            if reason is None:
                reason = reservations.feasible(segments,exclude=metadata['uid'])
            if reason is None:
                reason = self.current_guard(metadata,segments,now,self.current[1])
            score = None
            if reason is None:
                score,reason = self._score(metadata,segments,now,baseline)
            if reason:
                rejected.append(dict(site=site,reason=reason))
                continue
            key = (round(score['grid_peak'],12),score['loading_hours'],score['risk_GPUh'])
            candidates[site] = (key,segments,score)
        selected = basic if basic in candidates else None
        for site in sorted(candidates):
            if site != basic and (selected is None or candidates[site][0] < candidates[selected][0]):
                selected = site
        if selected is None:
            return self._record(metadata,now,dict(action='QUEUE',status='NO_COMMON_HARD_FEASIBLE_ACTION'),began,len(sites),rejected)
        key, segments, score = candidates[selected]
        if reserve:
            ok,reason = reservations.reserve(metadata['uid'],segments,replace=True)
            if not ok:
                return self._record(metadata,now,dict(action='QUEUE',status=reason),began,len(sites),rejected)
            self.assignments[metadata['uid']] = score['profile']/4
        return self._record(metadata,now,dict(action='START' if selected == basic else 'PREPLACE',
            status='V43_BASIC_STAY' if selected == basic else 'V43_STRICTLY_BETTER_PENDING_PRESITE',
            site=selected,start_seconds=now,nominal_end_seconds=segments[0]['end'],segments=segments,
            additional_start_delay_seconds=metadata.get('additional_start_delay_seconds',0.),
            tracking={k:v for k,v in score.items() if k != 'profile'}),began,len(sites),rejected)

    def select_migration(self, metadata, receipt, now, reservations, **kwargs):
        return dict(action='STAY',status='R2_HOLD',uid=metadata['uid'],policy_sha=self.sha)
