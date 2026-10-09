"""Exact construction checks with interval proofs over one frozen Resources.

Only the construction adapter is rebound. The original integer/physical
acceptance checker remains untouched and independently replays final points.
"""
import ast
import inspect
from dataclasses import asdict, is_dataclass
from contextlib import contextmanager
import numpy as np
from v42_job_capability import validate, resources_used, resource_limit
from v42_may_campaign_native90.a_routing import rebound


class ConstructionChecks:
    def __init__(self):
        self.boundaries = {}
        self.resources = {}
        self.calls = 0
        self.boundary_hits = 0

    def boundary(self, value):
        # Only frozen dataclasses with entirely immutable scalar/tuple fields
        # can reuse a successful original require(). Everything else falls back.
        key = id(value)
        if self.boundaries.get(key) is value:
            self.boundary_hits += 1
            return
        value.require()
        def immutable(x):
            return type(x) in (str, int, float, bool, type(None)) or type(x) is tuple and all(immutable(y) for y in x)
        if (is_dataclass(value) and value.__dataclass_params__.frozen
                and all(immutable(x) for x in asdict(value).values())):
            self.boundaries[key] = value

    def limits(self, resources):
        key = id(resources)
        if key not in self.resources:
            self.resources[key] = (resources, asdict(resources), {},
                                   max((t + 1 for _, t in resources.fixed_gpu), default=0))
        return self.resources[key]

    def fits(self, job, option, resources):
        self.calls += 1
        _, _, memo, fixed_end = self.limits(resources)
        # Earlier original checks prove disjoint compute segments, unique WAN
        # occupancy and one migration. Thus GPU use is exactly job.gpu per slot.
        for site, start, end in option.segments:
            key = (site, job.gpu)
            max_slot = max(end, resources.control_end, fixed_end)
            old = memo.get(key)
            if old is None or old[0] < max_slot:
                cap = resources.capacities.get(site, 0)
                bad = np.full(max_slot, float(job.gpu) > cap + 1e-9, dtype=np.int64)
                for (s, t), used in resources.fixed_gpu.items():
                    if s == site and 0 <= t < max_slot:
                        # Identical operation order and tolerance as original.
                        bad[t] = float(job.gpu) > cap - used + 1e-9
                old = (max_slot, np.r_[0, np.cumsum(bad)])
                memo[key] = old
            if start < 0 or end < start:
                return not any(n > resource_limit(k, resources) + 1e-9
                               for k, n in resources_used(job, option).items())
            if old[1][end] != old[1][start]:
                return False
        for link, slot, amount in option.wan:
            if amount > resource_limit(('WAN', link, slot), resources) + 1e-9:
                return False
        if option.migrated:
            for slot in range(option.transfer_start, option.transfer_end):
                if 1 > resource_limit(('ACTIVE', '', slot), resources) + 1e-9:
                    return False
        return True

    def verify_resources(self):
        for resources, original, _, _ in self.resources.values():
            if asdict(resources) != original:
                raise ValueError('CONSTRUCTION_RESOURCE_MUTATION')

    def report(self):
        return dict(resource_checks=self.calls, boundary_require_hits=self.boundary_hits,
                    original_checks_retained=True, interval_tolerance=1e-9,
                    scope='ONE_FRESH_CONSTRUCTION', Native_calls=0)


def routed_validate(checks):
    tree = ast.parse(inspect.getsource(validate))
    function = tree.body[0]
    if ast.unparse(function.body[0]) != 'boundary.require()':
        raise ValueError('ORIGINAL_BOUNDARY_CHECK_SOURCE_SHAPE')
    function.body[0] = ast.parse('construction_boundary(boundary)').body[0]
    last = function.body[-2]
    if not isinstance(last, ast.If) or 'resources_used(job, option).items()' not in ast.unparse(last.test):
        raise ValueError('ORIGINAL_RESOURCE_CHECK_SOURCE_SHAPE')
    last.test = ast.parse('not construction_fits(job, option, resources)', mode='eval').body
    ast.fix_missing_locations(tree)
    namespace = dict(validate.__globals__, construction_boundary=checks.boundary, construction_fits=checks.fits)
    exec(compile(tree, inspect.getfile(validate), 'exec'), namespace)
    return namespace['validate']


@contextmanager
def construction_checks():
    import v42_a_stage_domain_v2.domain as domain
    checks = ConstructionChecks()
    original = domain.validate
    domain.validate = routed_validate(checks)
    try:
        yield checks
        checks.verify_resources()
    finally:
        domain.validate = original
