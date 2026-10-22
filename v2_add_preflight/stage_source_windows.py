"""Restore the user's frozen finite WINDOWS as A-stage input authority.

The r043 full-physical helper intentionally treats an old reference-start
endpoint as nonbinding. V2_add was explicitly instructed to reject starts
outside the original finite WINDOWS. Supply that same strict input domain
through the source's existing physical_domains interface; keep its native
builders, activation, pricing, objectives and acceptance arithmetic intact.
"""
from dataclasses import asdict
import types
from .stage_common import *


def starts(job,bound,control_end=120,hard_release=None):
    from v42_a_stage_domain_v2.domain import physical_starts
    allowed=set(bound.allowed_starts)
    return tuple(t for t in physical_starts(job,bound,control_end,hard_release) if t in allowed)


def physical_domain(job,bound,resources,generator=None,hard_release=None):
    from v42_a_stage_domain_v2.domain import physical_domain as original
    fn=types.FunctionType(original.__code__,dict(original.__globals__,physical_starts=starts),argdefs=original.__defaults__)
    domain=fn(job,bound,resources,generator,hard_release)
    allowed=set(bound.allowed_starts)
    assert all(t in allowed for t,s in domain.stays) and all(b[0] in allowed for b in domain.blocks)
    return domain


def audit():
    from .prestart_acceptance import source_domain
    from v42_a_stage_domain_v2.domain import physical_starts
    day=day_inputs();bundle=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    jobs,bounds,seconds,r,raw=source_domain(bundle,windows);rows=[]
    for uid,job in sorted(jobs.items()):
        broad=physical_starts(job,bounds[uid],r.control_end);strict=starts(job,bounds[uid],r.control_end)
        extra=sorted(set(broad)-set(strict))
        if extra:rows.append(dict(uid=uid,r043_full_physical_start_count=len(broad),
            original_WINDOW_start_count=len(strict),outside_original_WINDOW=len(extra),example=extra[:5]))
    return put('A_STAGE_SOURCE_WINDOW_AUTHORITY_AUDIT.json',dict(PASS=True,jobs=len(jobs),
        affected_jobs=len(rows),outside_WINDOW_start_choices=sum(r['outside_original_WINDOW'] for r in rows),rows=rows,
        original_WINDOW_file=day['files']['windows'],
        authority='User explicitly requires original finite WINDOWS and rejects START_WINDOW414 cache',
        source_r043_full_physical_universe_equivalence_claimed=False,
        domain_change='Only starts outside the original input WINDOW are excluded; no authorized original WINDOW start removed by this adapter',
        original_source_files_edited=False,source_optimizers_and_pricing_edited=False,
        Source_constraints_relaxed=False,new_Grid_constraint_generation=False,Native_optimize_calls=0,
        source=record(ROOT/'v42_a_stage_domain_v2/domain.py'),adapter=record(__file__)))


if __name__=='__main__':audit()
