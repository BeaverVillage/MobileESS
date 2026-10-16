"""Selective existing event controller: retry Unknown, never replan Known."""
import ast
from copy import deepcopy
import inspect
import textwrap

from v43_arms.controller import UniformArmController
from v43_actual.controller import V43EventController,V43Reservations
from v43_actual.vendor.actual import JobEventController
from v43_actual.vendor.policy import digest
from .participation import ArrivalParticipation


def admission_core():
    source=textwrap.dedent(inspect.getsource(JobEventController.admit))
    old='if uid not in self.decisions or self.decisions[uid]["action"] == "QUEUE":'
    if source.count(old)!=1:raise ValueError('UNKNOWN_RETRY_REUSE_BOUNDARY_DRIFT')
    source=source.replace(old,'if self.metadata[uid]["origin_unknown"] or uid not in self.decisions or self.decisions[uid]["action"] == "QUEUE":')
    tree=ast.parse(source)
    # CorrectivePolicy handles a safe basic-site fallback itself. The legacy
    # zero-QoS-budget fallback could cache START after a later hard rejection.
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.If) and
        'self.budgets[uid].budget_seconds == 0' in ast.unparse(n.test)]
    if len(nodes)!=1:raise ValueError('UNKNOWN_FALLBACK_REUSE_BOUNDARY_DRIFT')
    nodes[0].test=ast.Constant(False);ast.fix_missing_locations(tree)
    ns=dict(JobEventController.admit.__globals__)
    exec(compile(tree,inspect.getfile(JobEventController.admit),'exec'),ns)
    return ns['admit']


def tick_core():
    source=textwrap.dedent(inspect.getsource(V43EventController.admit))
    if source.count('result=super().admit(now)')!=1:raise ValueError('CONTROLLER_TICK_REUSE_BOUNDARY_DRIFT')
    source=source.replace('result=super().admit(now)','result=self._admit_jobs(now)')
    ns=dict(V43EventController.admit.__globals__)
    exec(compile(source,inspect.getfile(V43EventController.admit),'exec'),ns)
    return ns['admit']


class CorrectiveReservations(V43Reservations):
    """The incoming Known UID replaces its own nominal booking, never a peer."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._incoming_uid=None

    def reserve(self,uid,segments,**kwargs):
        with self._lock:
            previous=self._incoming_uid;self._incoming_uid=uid
            try:return super().reserve(uid,segments,**kwargs)
            finally:self._incoming_uid=previous

    def _fits(self,segments,*,exclude=None,envelope=None,scope='physical'):
        if exclude is None and self._incoming_uid in self.known_plans:
            exclude=self._incoming_uid
        return super()._fits(segments,exclude=exclude,envelope=envelope,scope=scope)


class CorrectiveController(UniformArmController):
    _admit_jobs=admission_core()
    _admit_tick=tick_core()

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.reservations=CorrectiveReservations(self,capacities=self.ledger.capacities,
            wan_capacities=kwargs.get('wan_capacities'))
        self.participation=ArrivalParticipation()
        self.overrun_observations=[];self._seen_overruns=set()
        self._frozen_known_commands=deepcopy(self.known_schedule)
        self._last_admission_state=None

    def _state_key(self,now):
        return digest(dict(now=now,pending=sorted(self.pending),
            observed_jobs=self.ledger.jobs,committed=self.reservations.reservations,
            known_plans=self.reservations.known_plans))

    def submit(self,request,now):
        super().submit(request,now)
        m=self.metadata[request.uid]
        if m['origin_unknown']:
            m['r1_flex30']=self.participation.observe(m,now)
            self._event(request.uid,now,'R1_PARTICIPATION_OBSERVED',
                participant=m['r1_flex30']['participant'],eligible=m['r1_flex30']['eligible'],
                authority='R1_ASSUMED',receipt_sha=m['r1_flex30']['receipt_sha'])

    def admit(self,now):
        if now%900:return []
        if self._state_key(now)==self._last_admission_state:return []
        if self.known_schedule!=self._frozen_known_commands:
            raise ValueError('KNOWN_FROZEN_COMMANDS_MODIFIED')
        for uid,m in self.metadata.items():
            if m['state']=='RUNNING' and m.get('accumulated_compute_seconds',0)>m['t50_seconds']:
                if uid not in self._seen_overruns:
                    self._seen_overruns.add(uid)
                    row=dict(uid=uid,time_seconds=now,site=m['current_site'],
                        origin_unknown=m['origin_unknown'],elapsed_compute_seconds=m['accumulated_compute_seconds'],
                        nominal_Q50_seconds=m['t50_seconds'],GPU=m['gpu'],
                        observed_start_seconds=self.ledger.jobs[uid]['start_time'],
                        nominal_completion_without_pause_seconds=self.ledger.jobs[uid]['start_time']+m['t50_seconds'],
                        future_runtime_or_completion_reads=0)
                    self.overrun_observations.append(row);self._event(uid,now,'OVERRUN_OBSERVED',**{k:v for k,v in row.items() if k not in ('uid','time_seconds')})
        starts=self._admit_tick(now)
        self._last_admission_state=self._state_key(now)
        return starts
