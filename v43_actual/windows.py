"""Preserve PR189 Known windows; issue strict empirical budgets only for Unknown."""
from dataclasses import asdict

from .vendor.qos import BudgetReceipt, QoSWindowProvider
from .vendor.policy import digest


class OriginalKnownWindows(QoSWindowProvider):
    def __init__(self, stats, *, case_sha, provider_sha, windows, issue_seconds, external_running=()):
        super().__init__(stats, case_sha=case_sha, provider_sha=provider_sha)
        self.windows = {row['job_id']:dict(row) for row in windows}
        if len(self.windows) != len(windows):
            raise ValueError('PR189_DUPLICATE_WINDOW_UID')
        self.issue_seconds = issue_seconds
        self.external_running = frozenset(external_running)
        if self.external_running.intersection(self.windows):
            raise ValueError('EXTERNAL_RUNNING_OVERLAPS_NATIVE_WINDOW')

    def issue(self, job):
        if job.origin_unknown:
            if job.uid in self.windows or job.uid in self.external_running:
                raise ValueError('KNOWN_UNKNOWN_ROSTER_OVERLAP')
            return super().issue(job)
        external = job.uid in self.external_running
        if job.uid not in self.windows and not external:
            raise ValueError('ORIGINAL_KNOWN_WINDOW_REQUIRED')
        if external and job.state != 'RUNNING' and job.uid not in self.receipts:
            raise ValueError('EXTERNAL_RUNNING_CANNOT_CREATE_PENDING_COMMAND')
        if job.provider_sha != self.provider_sha:
            raise ValueError('ORIGINAL_KNOWN_PROVIDER_DRIFT')
        prior = self.receipts.get(job.uid)
        if prior is not None:
            if prior.authority_sha != job.authority_sha:
                raise ValueError('ORIGINAL_KNOWN_WINDOW_AUTHORITY_CHANGED')
            return prior
        window = (dict(reference_start=0,latest_start=0,allowed_starts=[0],
            reason='EXTERNAL_OBSERVED_RUNNING_CONTINUATION_ONLY') if external else self.windows[job.uid])
        starts = tuple(self.issue_seconds + 900*t for t in window['allowed_starts'])
        reference = self.issue_seconds + 900*window['reference_start']
        budget = 900*(window['latest_start']-window['reference_start'])
        if job.reference_start_seconds != reference:
            raise ValueError('ORIGINAL_KNOWN_REFERENCE_AXIS_DRIFT')
        contract = {key:asdict(job)[key] for key in ('release_seconds',
            'hard_earliest_start_seconds','hard_latest_start_seconds',
            'completion_deadline_seconds','representation_starts_seconds',
            'nominal_service_seconds','provider_sha','reference_sha','batch_eligible',
            'qos','protected','partition','gpu','requested_walltime_seconds')}
        contract['PR189_WINDOW'] = dict(window)
        receipt = BudgetReceipt(job.uid, self.case_sha,
            'EXTERNAL_OBSERVED_RUNNING_CONTINUATION_ONLY' if external else 'PR189_ORIGINAL_KNOWN_WINDOWS',
            self.stats.sha, self.provider_sha, job.reference_sha, job.authority_sha,
            job.event_seconds, reference, reference-job.submit_seconds, job.t50_seconds,
            None, budget, self.issue_seconds+900*window['latest_start'], starts,
            None, 0, None, 'ORIGINAL_MODEL_RESEARCH_AUTHORITY',
            ('CUSTOMER_SLA_OR_CHANGE_CONSENT_NOT_INFERRED',), False, True,
            job.batch_eligible, job.state, contract, digest(contract))
        self.receipts[job.uid] = receipt
        return receipt

    def to_dict(self):
        result = super().to_dict()
        result.update(Known_authority='PR189_ORIGINAL_WINDOWS_UNCHANGED',
            Known_windows_sha=digest(self.windows),
            Unknown_authority='STRICT_EMPIRICAL_OBSERVED_METADATA_ONLY',
            Known_empirical_budget_cap_applied=False)
        return result
