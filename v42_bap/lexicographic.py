"""P1 -> P2 contract only. Never invokes a production objective layer."""

from dataclasses import dataclass
import math
from v42_two.contract import P1_EPS, COMPONENT_EPS, mess_groups


@dataclass(frozen=True)
class P1Acceptance:
    lower_bound: float
    upper_bound: float
    validated_incumbent: bool
    complete_open_node_coverage: bool
    scope_sha: str
    threshold: float = .005

    def check(self):
        if not all(math.isfinite(v) for v in (self.lower_bound, self.upper_bound, self.threshold)) or self.threshold < 0:
            raise ValueError('INVALID_P1_INTERVAL')
        if self.lower_bound > self.upper_bound or not self.validated_incumbent or not self.complete_open_node_coverage or not self.scope_sha:
            raise ValueError('P1_GLOBAL_ACCEPTANCE_REQUIRED')
        gap = (self.upper_bound - self.lower_bound) / max(abs(self.upper_bound), 1e-12)
        if gap > self.threshold:
            raise ValueError('P1_REQUIRED_GLOBAL_GAP_NOT_MET')
        return gap


def call_p2(acceptance, solve_layer):
    """The caller supplies frozen-contract tolerances and independently validated
    layer receipts. Acceptance is scoped; a root LP result is insufficient.
    Native reserve_shortfall remains a report-only auxiliary, unchanged.
    """
    acceptance.check()
    groups = mess_groups([('rho', None), ('reserve_shortfall', None), ('movement_kwh', None), ('movement_count', None), ('tie', None)])
    energy_name, count_name = [name for name, _ in groups[1].components]
    p1_cap = acceptance.upper_bound + P1_EPS
    energy = solve_layer(energy_name, p1_cap, None, acceptance.scope_sha)
    if not energy.get('validated') or not energy.get('globally_accepted') or energy.get('scope_sha') != acceptance.scope_sha:
        raise ValueError('P2_ENERGY_ACCEPTANCE_REQUIRED')
    if not math.isfinite(energy['objective']) or energy['objective'] < 0:
        raise ValueError('P2_ENERGY_OBJECTIVE_INVALID')
    count = solve_layer(count_name, p1_cap, energy['objective'] + COMPONENT_EPS, acceptance.scope_sha)
    if not count.get('validated') or not count.get('globally_accepted') or count.get('scope_sha') != acceptance.scope_sha:
        raise ValueError('P2_COUNT_ACCEPTANCE_REQUIRED')
    if not math.isfinite(count['objective']) or count['objective'] < 0 or count['objective'] != round(count['objective']):
        raise ValueError('P2_COUNT_OBJECTIVE_INVALID')
    return dict(movement_energy=energy, movement_count=count)
