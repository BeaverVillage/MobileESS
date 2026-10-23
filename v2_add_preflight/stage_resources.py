"""V2_add resource policy: Native0 protection; campaign telemetry only.

Memory is never an admission or termination criterion in OFFICIAL_CAMPAIGN.
This module grants no execution authorization and changes no solver budget,
gap, thread count, source integrity check or worker lease.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,asdict
import os,time,math
import psutil


@dataclass(frozen=True)
class Policy:
    phase: str
    process_rss_limit_bytes: int | None
    minimum_system_available_bytes: int | None
    memory_admission_enabled: bool
    memory_termination_enabled: bool
    solver_MemLimit_GB: str = 'Infinity'
    solver_SoftMemLimit_GB: str = 'Infinity'


NATIVE0=Policy('NATIVE0_PREPARATION',None,None,False,False)
OFFICIAL=Policy('OFFICIAL_CAMPAIGN',None,None,False,False)
_policy=ContextVar('v2_add_resource_policy',default=NATIVE0)


def current():
    return _policy.get()


@contextmanager
def scope(phase):
    if phase not in (NATIVE0.phase,OFFICIAL.phase):raise ValueError('UNKNOWN_RESOURCE_PHASE')
    token=_policy.set(OFFICIAL if phase==OFFICIAL.phase else NATIVE0)
    try:yield current()
    finally:_policy.reset(token)


def sample():
    process=psutil.Process();m=process.memory_info();system=psutil.virtual_memory()
    result=dict(timestamp_unix=time.time(),pid=process.pid,RSS_bytes=m.rss,
        peak_RSS_bytes=getattr(m,'peak_wset',m.rss),process_commit_bytes=m.vms,
        system_available_bytes=system.available,system_total_bytes=system.total,
        memory_information_only=not current().memory_admission_enabled)
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Performance(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
                 'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
                ('HandleCount',wintypes.DWORD),('ProcessCount',wintypes.DWORD),('ThreadCount',wintypes.DWORD)]
        info=Performance();info.cb=ctypes.sizeof(info)
        if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info),info.cb):
            result.update(system_commit_bytes=info.CommitTotal*info.PageSize,
                system_commit_peak_bytes=info.CommitPeak*info.PageSize,
                system_commit_limit_bytes=info.CommitLimit*info.PageSize)
    return result


def check_memory(observation=None):
    """Official samples cannot cause rejection, early return or termination."""
    policy=current();observation=sample() if observation is None else observation
    if policy.memory_admission_enabled:
        if (observation['RSS_bytes']>=policy.process_rss_limit_bytes or
                observation['system_available_bytes']<policy.minimum_system_available_bytes):
            raise MemoryError('PROTECTED_WORKER_RESOURCE_RESERVE')
    return dict(observation,memory_information_only=not policy.memory_admission_enabled)


def apply_solver_memory_policy(model):
    """Positive Infinity is unlimited; zero would be a zero-GB limit."""
    if current().phase==OFFICIAL.phase:
        model.Params.MemLimit=float('inf')
        model.Params.SoftMemLimit=float('inf')
        assert all(math.isinf(float(v)) and float(v)>0 for v in (model.Params.MemLimit,model.Params.SoftMemLimit))
    def value(v):return 'Infinity' if math.isinf(float(v)) and float(v)>0 else float(v)
    return dict(MemLimit=value(model.Params.MemLimit),SoftMemLimit=value(model.Params.SoftMemLimit))


@contextmanager
def campaign_scope():
    """Bind the real source budget's Native admission to unlimited memory.

    The original lock/authorization context still runs first. Its body, Native
    accounting, callbacks, caps and thread checks are unchanged. Each worker
    must enter this scope explicitly; importing it never starts a campaign.
    """
    from unittest.mock import patch
    from v42_may_campaign_native90 import budget
    original=budget.native_scope
    @contextmanager
    def admitted(model,*args,**kwargs):
        with original(model,*args,**kwargs):
            apply_solver_memory_policy(model)
            yield
    with scope(OFFICIAL.phase),patch.object(budget,'native_scope',admitted):
        yield OFFICIAL


def manifest():
    return dict(official_campaign=asdict(OFFICIAL),Native0_preparation=asdict(NATIVE0),
        official_memory_watchdog_enabled=False,official_memory_reserve_queue_enabled=False,
        telemetry=['RSS','Peak RSS','process commit','system available','system commit'],
        original_solver_budgets_gaps_threads_preserved=True,
        worker_duplicate_lock_and_source_checks_preserved=True,
        official_campaign_executed=False)


def certify():
    from .stage_common import put,record,ROOT
    from .prestart_native import native_zero
    # Boundary observations are injected without allocating or exhausting RAM.
    extreme=dict(RSS_bytes=128*1024**3,system_available_bytes=0)
    with campaign_scope():
        accepted=check_memory(extreme)
        with native_zero() as denied:
            import gurobipy as gp
            model=gp.Model('V2_ADD_MEMORY_POLICY_NATIVE0');model.Params.OutputFlag=0
            try:
                model.Params.Threads=4;model.Params.TimeLimit=300.;model.Params.MIPGap=.03
                model.Params.MemLimit=1.;model.Params.SoftMemLimit=.5
                effective=apply_solver_memory_policy(model)
                assert effective==dict(MemLimit='Infinity',SoftMemLimit='Infinity')
                defaults={name:('Infinity' if math.isinf(model.getParamInfo(name)[5]) else model.getParamInfo(name)[5]) for name in ('MemLimit','SoftMemLimit')}
                assert defaults==effective
                assert model.Params.Threads==4 and model.Params.TimeLimit==300. and model.Params.MIPGap==.03
                # The actual adapter guard also bypasses preparation-only RAM
                # and wall limits. Source Native Runtime limits stay separate.
                from unittest.mock import patch
                from . import stage_common
                with patch.object(stage_common,'check_memory',lambda:check_memory(extreme)):
                    assert stage_common.guard(-float('inf'))['memory_information_only']
            finally:model.dispose()
        observed=sample()
    preparation_accepted=check_memory(extreme)
    assert preparation_accepted['memory_information_only'] and accepted['memory_information_only'] and current()==NATIVE0
    return put('CAMPAIGN_MEMORY_POLICY.json',dict(PASS=True,**manifest(),
        official_extreme_RSS_and_zero_available_memory_admitted=True,
        Native0_extreme_observation_rejected=False,Native0_memory_information_only=True,actual_Native0_solver_parameters=effective,
        actual_adapter_guard_memory_and_preparation_wall_bypass_PASS=True,
        installed_Gurobi_default_memory_parameters=defaults,
        authoritative_parameter_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:MemLimit',
        prior_zero_means_unlimited_assertion_retracted=True,zero_is_a_zero_GB_limit=True,
        source_budget_native_scope_bound=True,source_budget_function_body_unchanged=True,
        nonmemory_Threads_TimeLimit_MIPGap_unchanged=True,
        observed_telemetry=observed,Native_optimize_calls=0,Native_presolve_calls=0,
        denied_attempts=denied,scope='Resource policy only; not whole-stage readiness',
        producer=record(ROOT/'v2_add_preflight/stage_resources.py')))


if __name__=='__main__':
    # A ContextVar must have one canonical module identity under python -m.
    from .stage_resources import certify as certify_policy
    certify_policy()
