"""Opt-in Actual research assumption; no Source/QoS authorization is amended."""
import math
import inspect
import textwrap
from v43_actual.vendor.actual import JobEventController
from v43_actual.vendor.policy import migration_guard,digest

from .controller import CorrectiveController,admission_core

POLICY_ID='B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1'


def policy_assumption():
    return dict(policy_id=POLICY_ID,status='IMPLEMENTED_NOT_EXECUTED',
        scope='NEW_B1_ACTUAL_ONLY_EXPLICIT_OPT_IN',Source_authorized=False,
        Source_authority_promoted=False,original_windows_modified=False,
        original_QoS_receipts_modified=False,Planning_reoptimized=False,
        Known_service_equivalence='NOT_CERTIFIED',QoS_PASS='NOT_CLAIMED',
        membership_and_latest_and_deadline='POSTHOC_MEASUREMENT_ONLY',
        Unknown_policy='UNCHANGED_R1_FLEX30_C1',physical_guards='UNCHANGED')


def known_migration_core():
    # A private function namespace keeps every WAN/resource/checkpoint guard.
    # Only this Known adapter treats completion deadline as a measurement.
    def guard(metadata,*args,**kwargs):
        return migration_guard(dict(metadata,completion_deadline_seconds=None),*args,**kwargs)
    source=textwrap.dedent(inspect.getsource(JobEventController.migration))
    ns=dict(JobEventController.migration.__globals__,migration_guard=guard)
    exec(compile(source,inspect.getfile(JobEventController.migration),'exec'),ns)
    return ns['migration']


class RelaxedKnownController(CorrectiveController):
    """Frozen Known commands plus physical queueing; Unknown dispatch is inherited."""
    _admit_jobs=admission_core(relaxed_known=True)
    _planned_migration=known_migration_core()

    def __init__(self,*args,**kwargs):
        if kwargs.get('arm')!='B1':raise ValueError('RELAXED_KNOWN_B1_ONLY')
        super().__init__(*args,**kwargs)

    def _relaxed_known(self,uid):
        return self.metadata[uid]['origin_unknown'] is False and uid in self.known_schedule

    def _known_decision(self,uid,now):
        if not self._relaxed_known(uid):return super()._known_decision(uid,now)
        command=self.known_schedule[uid];r=self.requests[uid];m=self.metadata[uid]
        plan=float(command['start_seconds']);site=command['site'];receipt=self.budgets[uid]
        if not math.isfinite(plan):raise ValueError('FINITE_FROZEN_KNOWN_START_REQUIRED')
        # Source placement permissions and compatibility retain their existing gate.
        if site not in r.compatible or (r.source_site is not None and site!=r.source_site
                and m.get('can_prestart_place') is not True):
            return dict(uid=uid,action='QUEUE',status='PLAN_SITE_NO_AUTHORITY')
        start=max(plan,now,r.submit,m['event_seconds'],
            m.get('release_seconds') or -math.inf,m.get('hard_earliest_start_seconds') or -math.inf)
        action=('PREPLACE' if r.source_site is not None and site!=r.source_site else
            'DELAY' if plan>receipt.reference_start_seconds else 'START')
        return dict(uid=uid,action=action,site=site,start_seconds=start,
            nominal_end_seconds=start+max(r.q50,1e-9),plan_start_seconds=plan,
            status=POLICY_ID,additional_start_delay_seconds=max(0.,plan-receipt.reference_start_seconds))

    def submit(self,request,now):
        super().submit(request,now)
        if self._relaxed_known(request.uid):
            uid=request.uid;command=self.known_schedule[uid];receipt=self.budgets[uid]
            self._event(uid,now,'KNOWN_RESEARCH_WINDOW_ASSUMPTION',
                **policy_assumption(),plan_start_seconds=command['start_seconds'],planned_site=command['site'],
                original_allowed_starts_seconds=list(receipt.allowed_starts_seconds),
                plan_in_original_allowed_starts=command['start_seconds'] in receipt.allowed_starts_seconds,
                original_hard_latest_start_seconds=self.metadata[uid].get('hard_latest_start_seconds'),
                original_completion_deadline_seconds=self.metadata[uid].get('completion_deadline_seconds'),
                original_receipt_sha=digest(receipt.to_dict()))

    def admit(self,now):
        starts=super().admit(now)
        for uid in starts:
            if self._relaxed_known(uid):self._measure(uid,now,'START')
        return starts

    def _measure(self,uid,now,phase):
        m=self.metadata[uid];receipt=self.budgets[uid];job=self.ledger.jobs[uid]
        latest=m.get('hard_latest_start_seconds');deadline=m.get('completion_deadline_seconds')
        start=job['start_time'];completion=job.get('completion_observed_time')
        self._event(uid,now,'KNOWN_RESEARCH_QOS_MEASUREMENT',policy_id=POLICY_ID,phase=phase,
            actual_start_seconds=start,actual_completion_seconds=completion,
            plan_start_seconds=self.known_schedule[uid]['start_seconds'],
            physical_queue_delay_seconds=max(0.,start-self.known_schedule[uid]['start_seconds']),
            original_allowed_starts_seconds=list(receipt.allowed_starts_seconds),
            actual_start_in_original_allowed_starts=start in receipt.allowed_starts_seconds,
            original_hard_latest_start_seconds=latest,original_completion_deadline_seconds=deadline,
            hard_latest_start_excess_seconds=None if latest is None else max(0.,start-latest),
            start_after_completion_deadline_seconds=None if deadline is None else max(0.,start-deadline),
            actual_completion_deadline_excess_seconds=None if deadline is None or completion is None
                else max(0.,completion-deadline),QoS_PASS='NOT_CLAIMED',Source_authorized=False)

    def completion(self,uid,now):
        release=super().completion(uid,now)
        if self._relaxed_known(uid):self._measure(uid,now,'COMPLETION')
        return release

    def migration(self,uid,now,physical_checkpoint):
        command=self.known_schedule.get(uid,{})
        if self._relaxed_known(uid) and command.get('migration_destination') is not None:
            start=self.ledger.jobs[uid]['start_time']
            if start>command['start_seconds']:
                self._event(uid,now,'RUNNING_STAY',policy_id=POLICY_ID,
                    reason='KNOWN_DELAYED_START_INVALIDATES_PLANNED_CHECKPOINT',
                    actual_start_seconds=start,plan_start_seconds=command['start_seconds'],
                    planned_checkpoint_seconds=command.get('physical_checkpoint_seconds'),
                    frozen_command_modified=False)
                return None
            return self._planned_migration(uid,now,physical_checkpoint)
        return super().migration(uid,now,physical_checkpoint)

    def snapshot(self,now):
        result=super().snapshot(now)
        result['Known_research_assumption']=policy_assumption()
        return result

    def restore(self,snapshot):
        if snapshot.get('Known_research_assumption')!=policy_assumption():
            raise ValueError('RELAXED_KNOWN_CARRYOUT_POLICY_MISMATCH')
        super().restore(snapshot)


def select_controller(arm,policy=None):
    if policy is None:return CorrectiveController
    if arm!='B1' or policy!=POLICY_ID:raise ValueError('EXPLICIT_B1_RESEARCH_KNOWN_POLICY_REQUIRED')
    return RelaxedKnownController
