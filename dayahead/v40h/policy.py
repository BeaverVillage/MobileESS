"""Frozen interpretation and existing solver settings; no May-based tuning."""
OBJECTIVE_HIERARCHY = ('MIN_RHO_MAX', 'MIN_MIGRATIONS', 'MIN_COMPLETE_REFERENCE_DEVIATION', 'STABLE_TIE')
B1_SOLVER = dict(Threads=4, Seed=20260905, MIPGap=0, MIPGapAbs=0,
    FeasibilityTol=1e-9, IntFeasTol=1e-9, OptimalityTol=1e-9, WorkLimit_tiers=[60, 180, 300])
A1_SOLVER = dict(Threads=4, Seed=20260905, MIPGap=0, MIPGapAbs=0,
    FeasibilityTol=1e-8, IntFeasTol=1e-9, OptimalityTol=1e-8, WorkLimit=60)
MF_SOLVER = dict(Threads=4, Seed=20260828, MIPGap=1e-3, FeasibilityTol=1e-6,
    OptimalityTol=1e-6, TimeLimit=600, WorkLimit=60, MIPFocus=1, SoftMemLimit=8, NodefileStart=1)
INTERPRETATION = {
    'Planning': 'Optimization under the frozen affine/polyhedral distribution-system surrogate. Solver optimum or bounded incumbent refers only to this surrogate.',
    'Fresh': 'Post-decision exact three-phase OpenDSS physical verification.',
    'Actual': 'Fixed-decision realized-operation exact OpenDSS evaluation.',
    'nonlinear_AC_global_optimality_claim': False,
    'May_based_surrogate_retuning': False,
    'May_based_trust_region_added': False,
}


def configuration():
    return {'objective_hierarchy': OBJECTIVE_HIERARCHY, 'B1_solver': B1_SOLVER, 'A1_solver': A1_SOLVER,
        'MF_solver': MF_SOLVER, 'strict_primary': {'lower_priority_degradation_allowance': 0, 'extraction_roundoff': 1e-10,
        'MF_lower_priority_stages': 0}, 'interpretation': INTERPRETATION,
        'B3_A0_AIDC_OPTIMIZE_CALLS': 0, 'science_amendments': ['canonical migration segments',
        'generation provenance', 'counterfactual Actual completion proof', 'A1 strict accepted primary cap'],
        'unchanged_science': ['common causal T_DA', 'joint AIDC feasible set', 'MESS physics', 'traffic model',
            'power scale', 'corrected background allocation', 'electrical equations', 'Fresh limits', 'bounded solver tolerances']}
