"""All policies, hypotheses and conditional diagnostics frozen before optimization."""
from .common import *

def main():
    assert git('rev-parse','HEAD')==BASE;assert not (OUT/'PREREGISTRATION.json').exists()
    preserve();LOCAL.mkdir(exist_ok=True)
    registration=dict(base=BASE,utc=stamp(),branch='codex/v42-m1-root-pathology-diagnostics',LP_common=LP_POLICY,MIP_method2=MIP_POLICY,
        root_order=[f'ROOT_LP_METHOD{method}_{kind.upper()}' for kind in ['original','compact'] for method in [0,1,2]],
        root_seconds_each=600,Method2_LP_additions=dict(Crossover=0,PreDual=0,BarConvTol=1e-11),fresh_LP_no_Start=True,
        Method2_MIP_seconds=300,MIP_Crossover='Default -1 unchanged. With NodeMethod=1 a basis/crossover is required; actual logs determine observed phases.',
        documentation={'Method_Crossover':'https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html',
            'barrier_logging':'https://docs.gurobi.com/projects/optimizer/en/current/concepts/logging/barrier.html',
            'Kappa':'https://docs.gurobi.com/projects/optimizer/en/current/concepts/numericguide/geometry.html'},
        historical_objectives=TARGET,objective_equivalence_absolute_tolerance=1e-8,
        hypotheses={
            'H1':dict(STRONGLY_SUPPORTED='Same exact LP: current Method2 OPTIMAL and historical same-model/core-policy barrier OPTIMAL repeat; Method1 incomplete at 600; objective equivalence <=1e-8.',
                CONFIRMED='Above plus literal root completion or a nonroot node in the same-science Method2 MIP diagnostic. Root processing or exact first-branch events not exposed remain null.'),
            'H2':dict(STRONGLY_SUPPORTED='Extreme dynamic range concentrated >=50% of extreme nnz in identified families AND exact row scaling changes incomplete unscaled Method1 into OPTIMAL at 300s, or is >=20% faster if both terminal optimal.',
                numerical_units='Infeasibility magnitudes in scaled rows are not compared as identical units. No certificate adoption.'),
            'H3':dict(STRONGLY_SUPPORTED='Terminal optimal basis with >=50% primal basic-at-bound or >=50% nonbasic near-zero RC at 1e-8, based on >=100 observed variables. Shows degeneracy presence, not a measured zero-step pivot count or exclusive causal mechanism.',
                basis_fallback='Only if no current Original/Compact M0/M1 terminal optimal basis, Original Method2 Crossover1 PreDual0 BarConvTol1e-11 max600.',
                tolerances=[1e-9,1e-8,1e-7],inconclusive_without_terminal_optimal_basis=True),
            'H4':dict(STRONGLY_SUPPORTED='Grid block contributes >50% nnz or >50% extremes/basis-neutral burden, or exact projection/isolated-family diagnostic materially improves terminal completion/time. Burden attribution and causal identification reported separately.')},
        conditioning=dict(large_Kappa_threshold=1e12,KappaExact='Null with reason on large 950k+ row basis to avoid unbudgeted factorization; estimate requested if available.'),
        coefficient_thresholds=[1e-14,1e-13,1e-12,1e-10,1e-8],extreme_trace_thresholds=dict(tiny_at_most=1e-12,large_at_least=1e2),
        tiny_impact='Absolute coefficient times finite global variable bound, summed by row; unbounded helpers give infinite/unknown bounds, never implicitly zero. No removal authorization.',
        duplicate_rows='Exact dyadic rational primitive normalization including RHS and sense; cryptographic hash grouping, every hit verified by exact proportional comparison. Zero constant rows explicitly counted.',
        row_scaling=dict(policy='Positive power-of-two per-row normalization; exact all-entry/RHS binary64 roundtrip; no coefficient removal, no bound/type/objective changes.',Method=1,seconds=300),
        auxiliary_projection=dict(full_count=81216,policy='Strict triangular +1 definitions prove unique full rational projection. If flattened coefficients are not binary64-exact, refuse approximate full flattening. Exact injection P/Q subset may be prototyped only after +/-1/disjoint-support/no-collision/infinite-bound/zero-objective proof.',
            transport='No rounding of rational projected coefficients allowed.',reference_seconds=300,Method1_seconds=300,Method2_seconds=600,
            scope='Partial prototype retains response helpers and cannot claim full block elimination benefit. Full-vs-partial evidence disclosed.'),
        isolation=dict(activation='If complete full helper projection cannot be transported exactly, response-block attribution remains unsettled after partial projection; last-run isolation copies allowed.',
            order=['FULL_REFERENCE','voltage_lower','line_thermal_face','response_line_correction_binding','energy_balance'],seconds_each=120,Method=1,
            one_source_family_per_copy=True,NON_SCIENTIFIC_DIAGNOSTIC_ONLY=True,certificate_pipeline_forbidden=True),
        stagnation=dict(minimum_iterations=5000,relative_phase_objective_change_less_than=1e-6,feasibility_improvement_less_than=.01,
            objective_denominator='max(1,abs(start phase objective))',infeasibility_spike_ratio=100,
            phase_objective_is_not_scientific_bound=True,zero_step_pivot_count='Not exposed; never invented.'),
        scientific_certificate=dict(UB=UB,LB=LB,gap=(UB-LB)/UB,automatic_updates=False),
        RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,independent_work_allowed=True,sequential_heavy_lane=True,BLAS_OpenMP_threads=1,
        M1_ACCEPTED=False,COMPACT_M1_PRODUCTION_AUTHORIZED=False,PRODUCTION_1800S='NOT_RUN',P2='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False,
        Benders_calls=0,new_decompositions=0,no_physics_domain_objective_tolerance_changes=True)
    dump('PREREGISTRATION.json',registration)
    files=list((ROOT/'v42_root_diagnostics').glob('*.py'))
    for folder in ['v42_monolithic','v42_exact_start','v42_m1_sparse','v42_native','v42_bootstrap']:files+=list((ROOT/folder).glob('*.py'))
    paths=[ROOT.parent/'THRESHOLD_LOCAL/F3.mps']+[CACHE/n for n in ['COMPACT_A.npz','COMPACT_DATA.npz','AXIS_START.npz','INVERSE_T.npz','FORWARD_F.npz']]
    paths+=[OLD/(k+'_RECONSTRUCTED_START.npz') for k in ['ORIGINAL','COMPACT']]
    dump('SOURCE_FREEZE.json',dict(utc=stamp(),pre_experiment_code_commit=git('rev-parse','HEAD'),
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in files},inputs={str(p):sha(p) for p in paths},
        preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),optimizer_calls_before_freeze=0))
    print('PREREGISTRATION_AND_SOURCE_FREEZE_COMPLETE',flush=True)

if __name__=='__main__':main()
