from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_compact_rowgen_20261008'
STATIC=ROOT.parent/'v42-a-stage-compact-rowgen-static'
HISTORY=ROOT/'docs/v42_a_stage_phase1_pricing_20261007'
PR178=ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008'
DAY='2025-05-19'
POLICY=dict(schema='A_PRACTICAL_EXACT_OVERNIGHT_V1',budget_seconds=28800,Threads=1,workers=1,max_workers=4,
    frozen_batch_size=64,STAY=32,migration=32,reprice_before_frozen64_closure=False,reselection=False,
    preserve_original_fractional_native_LP=True,representation='exact lane sums + count-scaled perspective residual kernel +64 physical path columns',
    reciprocal_compilation=False,coefficient_rule='every compiled coefficient must be exactly representable binary64; otherwise projection STOP',
    row_tolerance=1e-6,initial_rows='all mandatory local/hard, all resource coupling, nonredundant current binding rows, all positive/negative residual rows, requested voltage node/time rows',
    delayed_rows_never_deleted=True,full_separation_after_every_solve=True,closure_before_Phi_certification=True,
    zero_tolerance=1e-8,materiality_threshold=.01,max_master_rounds=None,
    factor_limit_nnz=250000000,factor_limit_GB=2.,max_auxiliary_rows=2208913,max_auxiliary_cols=2158096,max_auxiliary_nnz=24825828,
    stagnation_consecutive_rounds=3,pricing_after_frozen64_closure=True,
    P1_requires_certified_zero_and_original_replay=True,P2_requires_full_domain_integer_acceptance=True,
    canaries_require_A1_acceptance_and_5400_seconds=True,production_Planning_Actual_Fresh_AC=False,
    no_parameter_sweep=True)
