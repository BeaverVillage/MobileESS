"""Use r043 physical timing authority; retain WINDOWS as frozen lineage.

The October23 directive requires adjudicating the prior intersection. Source
explicitly defines reference/empirical starts as objective metadata, not hard
release or deadline. Its physical validator still enforces observation/release,
service completion representation, protected timing and every resource rule.
"""
from dataclasses import asdict
import types
from .stage_common import *


def starts(job,bound,control_end=120,hard_release=None):
    from v42_a_stage_domain_v2.domain import physical_starts
    return physical_starts(job,bound,control_end,hard_release)


def physical_domain(job,bound,resources,generator=None,hard_release=None):
    from v42_a_stage_domain_v2.domain import physical_domain as original
    from .stage_a_performance import domain_constructor,domain_code,intern_times,ACTIVE
    # Source assigns the authoritative domain.sha immediately after Domain()
    # returns. Avoid only the constructor hash that is unconditionally replaced.
    fn=types.FunctionType(domain_code() if ACTIVE.get() is not None else original.__code__,
        dict(original.__globals__,physical_starts=starts,Domain=domain_constructor(),_V2_intern_times=intern_times),argdefs=original.__defaults__)
    domain=fn(job,bound,resources,generator,hard_release)
    allowed=set(starts(job,bound,resources.control_end,hard_release))
    assert all(t in allowed for t,s in domain.stays) and all(b[0] in allowed for b in domain.blocks)
    return domain


def audit():
    from .stage_timing_audit import audit as adjudicate
    return adjudicate()


if __name__=='__main__':audit()
