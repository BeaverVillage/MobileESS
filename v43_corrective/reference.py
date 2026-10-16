"""Causal FIFO processing without a cross-site global start-time barrier."""
from dataclasses import asdict
import math

from v43_actual.vendor.qos import CausalReferenceScheduler, _sha, SLOT_SECONDS
from v43_actual.vendor.trajectory_tracking import require_tracking_public


class CorrectedReferenceScheduler(CausalReferenceScheduler):
    def submit(self, request, *, event_seconds):
        require_tracking_public(request.metadata)
        if request.submit > event_seconds:
            raise ValueError('INDIVIDUAL_NOT_YET_SUBMITTED')
        if event_seconds < self.last_event_seconds:
            raise ValueError('NONCAUSAL_REFERENCE_EVENT')
        if request.uid in self.assigned:
            prior = self.assigned[request.uid]
            if prior.get('request_sha') != _sha(asdict(request)):
                raise ValueError('REFERENCE_REQUEST_CHANGED')
            return prior
        if not math.isfinite(request.q50) or request.q50 < 0 or request.gpu <= 0 or int(request.gpu) != request.gpu:
            raise ValueError('NOMINAL_REFERENCE_REQUEST_REQUIRED')
        self.last_event_seconds = event_seconds
        m = request.metadata
        sites = sorted(s for s in request.compatible if s in self.capacities and request.gpu <= self.capacities[s]
                       and (request.source_site is None or request.source_site == s))
        lower = max(event_seconds, request.submit, m.get('release_seconds') or -math.inf,
                    m.get('hard_earliest_start_seconds') or -math.inf)
        earliest = SLOT_SECONDS * math.ceil(lower / SLOT_SECONDS)
        candidates = sorted({earliest} | {SLOT_SECONDS * math.ceil(b / SLOT_SECONDS)
            for s in sites for a, b, g in self.reservations[s] if b >= earliest})
        def fits(site, start):
            end = start + max(request.q50, 1e-9)
            if (m.get('hard_latest_start_seconds') is not None and start > m['hard_latest_start_seconds']
                    or m.get('completion_deadline_seconds') is not None and end > m['completion_deadline_seconds']):
                return False
            checkpoints = {start} | {a for a, b, g in self.reservations[site] if start < a < end}
            return all(request.gpu + sum(g for a, b, g in self.reservations[site] if a <= t < b)
                       <= self.capacities[site] for t in checkpoints)
        chosen = next(((t, s) for t in candidates for s in sites if fits(s, t)), None)
        # An impossible source deadline is recorded, not repaired by granting
        # a later deadline or dropping a submitted physical job.
        start, site = chosen if chosen is not None else (earliest, sites[0] if sites else None)
        if site is None:
            raise ValueError('CAUSAL_REFERENCE_NO_COMPATIBLE_SOURCE_SITE')
        release = SLOT_SECONDS * math.ceil((start + max(request.q50, 1e-9)) / SLOT_SECONDS)
        if chosen is not None:
            self.reservations[site].append((start, release, request.gpu))
        self.last_pending_start_seconds = start  # descriptive; never admission authority
        receipt = dict(uid=request.uid, reference_start_seconds=start, reference_site=site,
            nominal_release_seconds=release, origin='CORRECTED_CAUSAL_SITE_RESERVATION_REFERENCE',
            reference_sha=self.reference_sha, request_sha=_sha(asdict(request)),
            reference_feasible=chosen is not None, grid_reads=0, realized_completion_reads=0, solver_calls=0,
            global_known_or_unknown_start_barrier_used=False)
        self.assigned[request.uid] = receipt
        return receipt
