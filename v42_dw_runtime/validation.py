"""Solver-free validation, canonical MESS batches, and safe MIPSOL quota control."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import math

from .contracts import (Candidate, QUOTA, RC_THRESHOLD, STOP_REASON, canonical,
                        digest, certification_settings)


@dataclass(frozen=True)
class ValidationResult:
    unit: int
    trajectory_SHA: str
    iteration: int
    true_dual_SHA: str
    accepted: bool
    reasons: tuple
    true_RC: float | None
    search_RC: float | None
    max_residual: float | None
    physical_residuals_json: str

    def __post_init__(self):
        object.__setattr__(self, 'reasons', tuple(self.reasons))


def validate_candidate(candidate, snapshot, local_validator):
    """Always perform Tier 1 checks. Never reuse a receipt's reduced cost."""
    reasons = []
    if candidate.iteration != snapshot.iteration or candidate.true_dual_SHA != snapshot.dual_SHA:
        reasons.append('STALE_TRUE_DUAL')
    if candidate.unit != local_validator.unit:
        reasons.append('MESS_MISMATCH')
    if not all(math.isfinite(v) for v in candidate.values):
        return ValidationResult(candidate.unit, digest([candidate.unit, list(map(repr, candidate.values))]),
            candidate.iteration, candidate.true_dual_SHA, False,
            tuple(reasons + ['NONFINITE_TRAJECTORY']), None, None, None, '{}')
    report = local_validator.audit(candidate.values)
    if not report['local_PASS']:
        reasons.append('ORIGINAL_LOCAL_INFEASIBLE')
    if not report['integral']:
        reasons.append('NONINTEGRAL')
    if not report['physical_PASS']:
        reasons.append('PHYSICAL_INFEASIBLE')
    true_rc, search_rc = local_validator.reduced_costs(candidate.values, snapshot)
    if not math.isfinite(true_rc) or true_rc > RC_THRESHOLD:
        reasons.append('TRUE_RC_NOT_NEGATIVE')
    if not math.isfinite(search_rc) or search_rc > RC_THRESHOLD:
        reasons.append('SEARCH_RC_NOT_NEGATIVE')
    residual = float(report['max_residual'])
    if not math.isfinite(residual):
        reasons.append('NONFINITE_RESIDUAL')
    return ValidationResult(candidate.unit, local_validator.trajectory_sha(candidate.values),
        candidate.iteration, candidate.true_dual_SHA, not reasons, tuple(sorted(reasons)),
        true_rc, search_rc, residual, canonical(report))


def validate_batches(batches, snapshot, validators, flags, max_workers=4):
    """One task per MESS; caller-owned read-only validators must never solve."""
    if not 1 <= max_workers <= 4:
        raise ValueError('At most four validator threads')
    jobs = [(unit, tuple(batch)) for unit, batch in sorted(batches.items())]
    def work(job):
        unit, candidates = job
        return [validate_candidate(c, snapshot, validators[unit]) for c in candidates]
    if flags.DW_PARALLEL_VALIDATION:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='DW_VALIDATE') as executor:
            chunks = list(executor.map(work, jobs))
    else:
        chunks = [work(job) for job in jobs]
    # Deduplicate identical callback/final-X observations, independent of arrival order.
    results = {canonical(asdict(r)): r for chunk in chunks for r in chunk}
    return tuple(results[key] for key in sorted(results))


class DiscoveryController:
    """Per-pricer callback adapter. Only fully validated new columns fill quota."""
    def __init__(self, kind, unit, snapshot, validator, flags, retained_SHAs=()):
        self.kind, self.unit, self.snapshot = kind, unit, snapshot
        self.validator = validator
        self.enabled = certification_settings(kind, snapshot, flags)['early_quota_terminate']
        self.retained = frozenset(retained_SHAs)
        self.results = []
        self.accepted = {}
        self.stop_reason = None
        self.errors = []

    def observe(self, values, native, observed_objective=None):
        if not self.enabled or self.stop_reason:
            return None
        try:
            candidate = Candidate(self.unit, values, self.snapshot.iteration, self.snapshot.dual_SHA)
            result = validate_candidate(candidate, self.snapshot, self.validator)
            if observed_objective is not None and (not math.isfinite(observed_objective) or
                    result.search_RC is None or abs(result.search_RC-observed_objective) > 1e-8):
                from dataclasses import replace
                result = replace(result, accepted=False,
                                 reasons=tuple(sorted((*result.reasons, 'SEARCH_OBJECTIVE_MISMATCH'))))
            self.results.append(result)
            if result.accepted and result.trajectory_SHA not in self.retained:
                self.accepted.setdefault(result.trajectory_SHA, result)
            if len(self.accepted) >= QUOTA:
                self.stop_reason = STOP_REASON
                native.terminate()
            return result
        except Exception as error:
            self.errors.append(repr(error))
            self.accepted.clear()  # Fail closed: no incomplete callback audit is addable.
            self.stop_reason = 'CALLBACK_VALIDATION_ERROR'
            native.terminate()
            return None

    def callback(self, variables):
        import gurobipy as gp
        def control(native, where):
            if self.enabled and where == gp.GRB.Callback.MIPSOL:
                self.observe(native.cbGetSolution(variables), native,
                             float(native.cbGet(gp.GRB.Callback.MIPSOL_OBJ)))
        return control

    def terminal_receipt(self, native_status):
        # Discovery never supplies an optimality or no-negative certificate, even at status 2.
        return dict(native_status=int(native_status), STOP_REASON=self.stop_reason,
                    accepted_SHAs=sorted(self.accepted), accepted_count=len(self.accepted),
                    true_dual_SHA=self.snapshot.dual_SHA, iteration=self.snapshot.iteration,
                    pricing_optimality_claimed=False, valid_bound=False,
                    no_negative_certificate=False, pricing_convergence=False,
                    errors=self.errors.copy())


class OriginalBlockValidator:
    """Reuse PR143 physical and full original-row validators with no solver access.

    Supply an already prepared block/prototype and complete original local row slice.
    No model, optimize, candidate repair, fixing, or domain restriction is performed.
    """
    def __init__(self, unit, block, original_matrix, original_attributes, original_route_mask):
        self.unit, self.block = unit, block
        self.matrix, self.attributes, self.route_mask = original_matrix, original_attributes, original_route_mask

    def audit(self, values):
        import numpy as np
        from v42_dw_resume.audit import corrected_rows
        x = np.asarray(values, dtype=np.float64)
        physical = self.block.validate(x, True)
        local = corrected_rows(self.matrix, self.attributes, x, True, self.route_mask)
        residuals = [float(v) for k, v in local.items()
                     if ('violation' in k or 'residual' in k) and isinstance(v, (int, float))]
        ratio = physical.get('route_SOC_PCS', {}).get('max_exact_circle_ratio', 0.)
        residuals.append(max(0., float(ratio)-1.))
        return dict(local_PASS=bool(local['PASS']), physical_PASS=bool(physical['PASS']),
                    integral=bool(local['integer_pattern_exact']), max_residual=max(residuals, default=0.),
                    full_original_local=local, physical=physical)

    def trajectory_sha(self, values):
        import numpy as np
        return self.block.column(np.asarray(values, dtype=np.float64))[2]

    def reduced_costs(self, values, snapshot):
        import numpy as np
        from v42_dw_root.run import exact_rc
        x = np.asarray(values, dtype=np.float64)
        return (float(exact_rc(self.block, x, np.asarray(snapshot.true_dual), snapshot.convexity_dual[self.unit])),
                float(exact_rc(self.block, x, np.asarray(snapshot.smoothed_dual), snapshot.smoothed_convexity_dual[self.unit])))
