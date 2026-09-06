"""Frozen V40G strict lower-priority semantics, with bounded primary evidence."""
from copy import deepcopy
from .identity import require

# Same extraction-roundoff threshold used by frozen V40G B1, not May tuning.
EXTRACTION_ROUNDOFF = 1e-10


def preserve(primary_decision, primary_rho, candidate, recompute):
    final_rho = float(recompute(candidate))
    rejected = final_rho > primary_rho + EXTRACTION_ROUNDOFF
    accepted = deepcopy(primary_decision) if rejected else candidate
    final_rho = float(recompute(accepted))
    require(final_rho <= primary_rho + EXTRACTION_ROUNDOFF, 'PRIMARY_SNAPSHOT_RECOMPUTATION_DRIFT')
    return accepted, {'final_recomputed_rho': final_rho,
        'primary_materialized_rho': primary_rho, 'raw_recomputed_primary_delta': final_rho - primary_rho,
        'primary_degradation_due_to_lower_priorities': 0.0,
        'lower_priority_candidate_rejected': rejected, 'frozen_numerical_semantics': EXTRACTION_ROUNDOFF}
