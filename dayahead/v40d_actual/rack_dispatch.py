"""Execution-time first fit. Only current occupancy is inspected, never grid cost."""
from dataclasses import dataclass
from types import MappingProxyType
from .contracts import ReplayError


@dataclass(frozen=True)
class Rack:
    site: str
    rack_id: str
    capacity: int


class RackDispatcher:
    def __init__(self, site_capacity, racks):
        self.sites = MappingProxyType(dict(site_capacity))
        if any(type(c) is not int or c <= 0 for c in self.sites.values()):
            raise ReplayError("INVALID_SITE_CAPACITY_AUTHORITY")
        self.racks = tuple(sorted(racks, key=lambda r: r.rack_id))
        if len({r.rack_id for r in self.racks}) != len(self.racks):
            raise ReplayError("DUPLICATE_RACK_ID")
        if any(r.site not in self.sites or r.capacity <= 0 for r in self.racks):
            raise ReplayError("INVALID_RACK_AUTHORITY")
        self.active = {}
        self.assignments = []
        self.failures = []
        self.calls = 0

    def release(self, slot):
        self.active = {u: r for u, r in self.active.items() if r["release_slot"] > slot}

    def occupied(self, site=None, rack=None):
        return sum(r["requested_GPU"] for r in self.active.values()
                   if (site is None or r["AIDC_site"] == site)
                   and (rack is None or r["rack_pool_id"] == rack))

    def admit(self, job, slot, release_slot, key, *, existing=False):
        self.calls += 1
        uid, site, gpu = job["job_uid"], job["AIDC_site"], job["requested_GPU"]
        if site != job.get("frozen_AIDC_site", site):
            raise ReplayError("ALTERNATE_AIDC_FORBIDDEN:" + uid)
        if site not in self.sites:
            raise ReplayError("MISSING_FROZEN_SITE_AUTHORITY:" + uid)
        if uid in self.active:
            raise ReplayError("DUPLICATE_ADMISSION:" + uid)
        candidates = [r for r in self.racks if r.site == site and r.capacity >= gpu]
        if not candidates or gpu > self.sites[site]:
            raise ReplayError("GANG_EXCEEDS_AUTHORITY_CAPACITY:" + uid)
        site_ok = self.occupied(site=site) + gpu <= self.sites[site]
        # V39D envelopes admit one whole gang. They are NOT physical bins:
        # cumulative occupancy on a logical label cannot impose another cap.
        selected = candidates[0]
        if not site_ok:
            reason = "GPU_CAPACITY"
            if existing:
                raise ReplayError("RUNNING_INITIAL_CAPACITY_CONFLICT:" + uid)
            self.failures.append({"job_uid": uid, "AIDC_site": site, "slot": slot,
                "waiting_since": job["start_slot"], "next_retry_slot": slot + 1, "reason": reason})
            return None, reason
        before = self.sites[site] - self.occupied(site=site)
        row = {"job_uid": uid, "AIDC_site": site, "rack_pool_id": selected.rack_id,
               "assignment_slot": slot, "release_slot": release_slot, "requested_GPU": gpu,
               "assignment_method": "STABLE_RACK_ID_FIRST_FIT", "stable_priority_key": list(key),
               "Rack_semantics": "NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE",
               "gang_compatibility_GPU_limit": selected.capacity,
               "site_headroom_before_GPU": before, "site_headroom_after_GPU": before - gpu}
        self.active[uid] = row
        self.assignments.append(row)
        return selected.rack_id, None

    def validate(self):
        if any(self.occupied(site=s) > cap for s, cap in self.sites.items()):
            raise ReplayError("SITE_CAPACITY_EXCEEDED")
        by_id = {r.rack_id: r for r in self.racks}
        for row in self.active.values():
            rack = by_id[row["rack_pool_id"]]
            if rack.site != row["AIDC_site"] or row["requested_GPU"] > rack.capacity:
                raise ReplayError("RACK_GANG_COMPATIBILITY_FAILED")
