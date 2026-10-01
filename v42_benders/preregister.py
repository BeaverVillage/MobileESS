"""Write scientific gates and sign derivations before implementing cut code."""
from datetime import datetime, timezone
from .common import *

def run():
    assert git('rev-parse', 'HEAD') == BASE
    assert not (OUT/'PREREGISTRATION.json').exists()
    from v42_threshold.common import resource_snapshot
    resource = resource_snapshot()
    threads = 1 if resource['other_heavy_solve'] else 4
    dump('RESOURCE_RECEIPT.json', dict(initial=resource, threads=threads, sequential=True,
        maximum_threads=4, parallel_recourse=False, continuous_absence_claim=False))
    files = git('ls-files').splitlines()
    dump('PR114_BASE_RECEIPT.json', dict(PR=114, exact_head=BASE, inherited_files=len(files),
        files=[dict(path=p, sha256=sha(ROOT/p)) for p in files], preserved=True))
    dump('PREREGISTRATION.json', dict(created_UTC=datetime.now(timezone.utc).isoformat(),
        exact_base=BASE, branch=git('branch','--show-current'), seed=20260929, threads=threads,
        preserved_problems=[1,2,3,4,5,6,8,13], excluded_new_work=[7,9,10,11,12],
        outer='A1 -> M1 -> A2 -> M2', inner='Joint route/mode/P/Q/SOC/grid feasible set',
        planning_voltage=[.955,1.045], eventual_fresh_AC=[.95,1.05], actual_PQ_repair=False,
        tolerances=dict(primal=1e-7, integer=1e-7, dual_stationarity=1e-7,
            fixture_optimum=1e-7, source_tightness=1e-7, strict_Farkas_margin=1e-8,
            physical=1e-6, threshold_safety_margin=1e-6),
        certificates='Exact rational arithmetic on stored IEEE doubles; finite-bound support correction and outward affine rounding. Unbounded residual support or lost strict margin: STOP, NO CUT.',
        LP=dict(Method=1, FeasibilityTol=1e-7, OptimalityTol=1e-7, InfUnbdInfo=1,
            DualReductions=0, NumericFocus=1, SoftMemLimit=12),
        master=dict(MIPGap=0, IntFeasTol=1e-7),
        fixtures='12 physical fixtures A-L, exhaustive all bit assignments; native fixed-x LP and canonical fixed-x LP separately; monolithic MILP and Benders P1; all infeasible assignments excluded by verified rays or discrete-only rows',
        budgets=dict(B3_decomposition_wall=1800, full_M1_canary_wall=600,
            production_P1_wall=1800, production_P1_max_runs=1, production_P2_wall=1800),
        B3_gate='Fixtures PASS; exact matrix and full B3 partition; no invalid/uncertifiable cut; witness/proof OR >=2 terminal recourse solves and >=2 valid cuts within 1800s. Iterations with stalled first LP do not pass.',
        production_gate='Canary exact, no numerical contradiction, >=2 terminal LP solves, valid finite LB, independently validated original UB, gap <=0.005 OR gap decreases by >=0.001 absolute from inherited 0.03224989640084286',
        P1_acceptance='Original physical/grid/mode/integer validated UB and valid global LB, gap<=0.005, no numerical contradiction',
        P2=dict(gate='Production P1 acceptance only', order=['movement_energy','movement_count'],
            inherited_P1_lock_tolerance=1e-7, component_lock_tolerance=1e-8),
        A2_RUN=False, M2_RUN=False, downstream_automatic=False,
        forbidden=['route pruning','Top-K','Hamming restriction','trajectory pool','physics relaxation','cut aging','cut deletion','aggregation','DW/CG'],
        unsafe_statuses=['TIME_LIMIT','NUMERIC','INTERRUPTED','INF_OR_UNBD'],
        immediate_stop=['not LP','invalid cut','fixture optimum mismatch','feasible assignment removed','uncertifiable ray','physics drift','route restriction']))
    dump('B3_DECOMPOSITION_PREREGISTRATION.json', dict(threshold=THRESHOLD, master_binaries=85744,
        outside_original_binaries='continuous recourse', original_rows=954560, horizon=96,
        wall_seconds=1800, objective=0, seed=20260929, threads=threads,
        reference=dict(PR=114, wall_seconds=1800.08, root_completed=False, certificate='B3_INCONCLUSIVE'),
        start='First solve exact discrete master; no restriction to warm-start routes',
        certificate='Validated witness -> NEGATIVE; proven master infeasible with only certified cuts -> POSITIVE; timeout/stop -> INCONCLUSIVE',
        performance_claim='Only same CPU/thread/memory conditions; initial snapshot is not continuous process monitoring'))
    texts = {
    'CANONICALIZATION_SPEC.md': '''# Exact canonical recourse

Stored original sparse rows C z (sense) d are partitioned in original column order into x and y. Every < row keeps sign, every > row is negated, every equality becomes both directions. Thus A y <= b - B x. Every original finite y upper bound gives +y <= upper; every finite lower bound gives -y <= -lower. Canonical LP variables are free: bounds are explicit rows. Finite means strictly within Gurobi infinity. No new physical bound is invented. Original x bounds and all y-free rows also occur in the discrete master; those rows remain in recourse for fixed-assignment census. Every original row and coefficient has indexed provenance. Original grid and PCS16 coefficients are preserved as stored, including tiny coefficients. Conversion involves only sign and duplication.

An initial state/anchor adapter rebuilds the native model with explicit inputs. M2 receives a fresh AIDC anchor, initial sites, and battery state. Warm starts set Start only, never LB/UB. The native constructor's original reachability authority is preserved; no additional pruning occurs.
''',
    'BENDERS_FEASIBILITY_CUT_DERIVATION.md': '''# Feasibility certificate, before cut implementation

Let h(x)=b-Bx, with all finite bounds and both equality directions present. For lambda >=0 and A^T lambda=0, any feasible y implies 0=lambda^T A y <= lambda^T h(x). If lambda^T h(xbar)<0, the necessary master cut is lambda^T(b-Bx)>=0. Gurobi FarkasDual on <= rows has this sign; it must be verified, never guessed.

Floating multipliers generally have a nonzero exact stationarity residual r=A^T lambda. For the original recourse bounds l,u, every feasible point satisfies r^T y >= L(r)=sum(r_j*l_j if r_j>=0 else r_j*u_j). Therefore the certified necessary inequality is lambda^T h(x)>=L(r). All products/sums and L use Fraction.from_float, exactly representing stored doubles. If a required bound is infinite, no cut can be certified and the engine stops. This is a bound-compensated Farkas certificate, not an assumed zero residual. It is equivalent to completing stationarity with nonnegative finite-bound multipliers already represented in the canonical rows. Require residual<=registered tolerance and strict corrected source margin>1e-8.

Write affine f(x)=lambda^T b-L(r)-lambda^T Bx. The cut f(x)>=0 is rounded outward: coefficient errors are bounded exactly over original x bounds; round the intercept upward with nextafter. This weaker cut cannot remove a feasible point. Recheck source exclusion. Independent validation recomputes coefficients from canonical matrix/provenance, sign, residual, bound/equality terms, correction, and every enumerated feasible fixture assignment. Altered ray/bound/B/RHS payloads are rejected. TIME_LIMIT/NUMERIC/INTERRUPTED never yields a cut.
''',
    'BENDERS_OPTIMALITY_CUT_DERIVATION.md': '''# P1 lower approximation, before cut implementation

For min c^T y with free y and A y<=h(x), dual pi<=0, A^T pi=c gives Q(x)>=pi^T(b-Bx). Thus theta>=pi^T b-pi^T Bx and min theta is the master relaxation of min rho. It is not a feasibility-only proof of P1. The original rho column alone has objective coefficient one.

For numerical residual r=c-A^T pi, c^T y >= pi^T h(x)+L(r), with L the exact finite-bound minimum used in the feasibility derivation. Infinite required support means STOP, NO CUT. This completes the dual using existing bound rows, preserving exact lower validity even when floating stationarity is imperfect. Compute all arithmetic exactly on IEEE stored doubles. Round affine intercept downward and account for every coefficient error over x bounds, producing a weaker globally valid lower approximation. Require source tightness<=1e-7 and residual<=1e-7; record both exact correction and outward rounding. Enumeration tests every feasible assignment against its independently computed Q(x).

Valid accumulated cuts bound all original assignments, so master ObjBound supplies a global lower bound. Only independently validated assembled x/y supplies UB. Relative gap=(UB-LB)/max(abs(UB),1e-10); LB>UB+tolerance is a contradiction and STOP. P2 instead locks rho<=accepted P1+1e-7 in recourse and uses movement energy then movement count in the master, with inherited component tolerance 1e-8. P2 and downstream gates remain explicit.

Official sign and ray reference: [Gurobi linear constraint attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html).
'''}
    for name, text in texts.items():
        (OUT/name).write_text(text, encoding='utf8')
    print('PREREGISTRATION AND DERIVATIONS SEALED', flush=True)

if __name__ == '__main__': run()
