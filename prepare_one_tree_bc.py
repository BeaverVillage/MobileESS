"""Scientific census and preregistration; no native optimization."""
import json
from collections import Counter
import numpy as np
from v42_degen.identity import inputs,signature
from v42_degen.common import POLICY
from v42_rowgen.core import OriginalRows,binding_proof,security_axis
from v42_one_tree_bc.core import BATCH,Separator
from v42_one_tree_bc.audit import Validator
from v42_one_tree_bc.files import ROOT,OUT,write,sha

def run():
    A,d,B,e,identity,freeze=inputs();rows=OriginalRows(B,e);grid=security_axis(e)
    assert len(grid)==598465 and len(binding_proof(B,e))==81216
    assert (B.shape[0],B.shape[1],B.nnz)==(886017,316743,8447855)
    seedfile=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006/A_BASELINE_FINAL_VALID_POINT.npz'
    with np.load(seedfile) as z:seed=z['point']
    seedcheck=Validator(A,d)(seed);assert seedcheck['PASS']
    parent=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006/A_BASELINE_RESULT.json'
    inherited=json.loads(parent.read_text())
    assert inherited['full_original_best_point_validation']['PASS']
    floor=inherited['final_valid_LB']
    C=B[rows.axis]
    family_counts=dict(Counter(str(e['row_names'][i]).split('[')[0] for i in grid))
    write('M1_ONE_TREE_BC_INITIAL_MODEL_CENSUS.json',dict(PASS=True,
        original=dict(rows=B.shape[0],columns=B.shape[1],binaries=int(np.count_nonzero(e['types']=='B')),nnz=B.nnz),
        original_unreduced=dict(rows=A.shape[0],columns=A.shape[1],nnz=A.nnz),
        initial=dict(rows=C.shape[0],columns=C.shape[1],binaries=int(np.count_nonzero(e['types']=='B')),nnz=C.nnz),
        deferred_rows=len(grid),deferred_by_family=family_counts,grid_auxiliaries=81216,
        retained_all_variables=True,coefficient_signature=signature(B,e),scientific_identity=identity))
    write('M1_ONE_TREE_BC_INPUT_FREEZE.json',dict(PASS=True,scientific_identity=identity,
        initial_security_policy='Empty; all original non-security rows and grid affine definitions retained.',
        seed_file=str(seedfile.relative_to(ROOT)),seed_SHA=sha(seedfile),seed_validation=seedcheck,
        initial_UB=seedcheck['objective'],inherited_full_domain_LB=floor,
        floor_provenance=dict(parent_file=str(parent.relative_to(ROOT)),SHA=sha(parent),
            semantics='Previously certified full-original-variable M1 global floor, preserved equally in both arms; no RMP bound or D-W duals loaded.'),
        core_solver_settings=POLICY,PreCrush=1,batch=BATCH,near_critical_policy=None,
        combined_wall_cap=600,arm_wall=280,common_preflight_and_finalize_reserve=40,
        native_stop_margin_seconds=5,Threads=1,callback_violation_authority=1e-8,
        raw_affine_postsolve_authority=1e-6,bounds_route_integer_authority=1e-8,
        user_authorized_lazy_resubmission=True,registry_unique=True,
        source_freeze_required_before_fullscale=True,maximum_fullscale_arm_optimize_calls=1,
        source_files={p:sha(ROOT/p) for p in ('v42_one_tree_bc/core.py','v42_one_tree_bc/audit.py','v42_one_tree_bc/files.py','verify_one_tree_bc.py','prepare_one_tree_bc.py','benchmark_one_tree_bc.py','run_one_tree_comparison.py')}))
    prereg='''# M1 one-tree original-grid callback preregistration

Base: PR158 a6045405b254703285a9d8469105746e3fc1b904. All inherited files remain untouched.

One fresh initial compact master and one optimize(callback) per full-scale arm.
Original objective, all route/mode/P/Q/SOC/rho variables, 81,216 affine auxiliaries,
all initial/terminal SOC and PCS16 constraints remain explicit. No pricing, RMP,
D-W columns, B&P queue or giant recourse solver is imported or executed.

MIPSOL exhaustively scans all 598,465 security rows, including previously
submitted rows. Every violation above 1e-8 is submitted as its exact original
row with cbLazy before the candidate can count as valid. Each grid-feasible
candidate also passes original full-matrix, exact integer, route, SOC, PCS and
mode/connection validators, with independent original objective recomputation.
Existing affine postsolve tolerance1e-6 is retained, bounds/route1e-8 and
unchanged native FeasibilityTol/OptimalityTol/IntFeasTol1e-8. No point repairs.

At optimal fractional MIPNODE, scan every security row; rank genuinely violated
not-yet-submitted original rows by violation/max(1, original coefficient L1
norm), ties by original row index. K_LINE=128, K_VOLTAGE=64 (both senses
combined), K_TRANSFORMER_CURRENT=32 (NormalAmps included), K_TRANSFORMER_KVA=32.
Submit via cbCut; PreCrush=1. No near-critical rows, gamma or result tuning.
All are original valid rows, so preserve every full-original integer point.

Unique original-row registry entries are immutable. No application cut deletion.
Gurobi can internally disregard cuts or present repeated lazy violations.
The user explicitly authorized cbLazy rejection resubmission (2026-10-06).
Record unique rows, avoided duplicate registry entries, usercut-to-lazy
promotion and native lazy resubmissions separately. Never assume submitted
rows are respected and never skip incumbent separation based on the registry.
Official semantics: https://docs.gurobi.com/projects/optimizer/en/current/reference/python/model.html#Model.cbLazy

Freeze source commit, hashes, fixture gate, scientific input/start hashes and
policy before the only comparison. One exclusive run marker forbids reruns.
Same Seed20260929, Threads1, Method2, NodeMethod1, Crossover2, MIPFocus3,
DegenMoves0, MIPGap.005, original numerical settings in both arms.
Both use PreCrush1; LazyConstraints1 only for callback arm, necessarily.
Sequential monolithic then one-tree. Continuous supervisor wall<=600s including
common input validation, model builds, starts, callback work and serialization;
each arm gets at most280s wall, native termination requested5s before its end.
Read-only1s RSS/process-commit/system-commit/free-RAM telemetry; no resource
threshold, waiting, kill or solver modification. Only fixed wall deadline acts.
Native logs preserved with OutputFlag1/LogToConsole0.

Use the same validated original point and already-certified full-original global
floor from PR158 in both arms. No D-W RMP duals/bounds/columns are loaded.
Native subset-tree bounds are full-domain lower bounds, conservatively nudged
down1e-8 (native numerical authority, not a new rational proof). Never use raw
invalid candidate objective as UB. Any callback exception/incomplete batch/
invalid terminal native solution invalidates new native-bound certification,
retaining only previously valid authorities and reporting INCONCLUSIVE.

Primary: reduction of valid global relative gap per end-to-end arm wallsecond.
Selected only with exactness PASS and >=20% improvement in a positive rate;
or materially stronger full-domain LB (>=1% of startingUB) at <=2s matched
wall difference, or genuine nonroot progress where baseline has none and
challenger has positive valid gap reduction. Both zero improvements=>false.
No memory-only selection. No additional policy comparison unless there is
positive promising progress and evidence a cut policy causes missed20% target;
default skip. Selected policy freezes and STOP. No3600s/P2/M2/B2/B3.
'''
    (OUT/'M1_ONE_TREE_BC_PREREGISTRATION.md').write_text(prereg,encoding='utf8')
    proof='''# Exactness proof and supported callback semantics

Let F be the original explicit-variable mixed-integer feasible set, and S0 be
all non-security rows (including every exact affine definition). For any set
of original grid rows R, F is a subset of F(S0 union R). Therefore minimization
over each relaxation gives a lower bound on the original M1 optimum. User cuts
are original rows and preserve every point in F, even if they tighten a node.
This is full original variable-domain authority, never restricted-column LB.

All MIPSOL points are exhaustively tested against every deferred row. A violation
triggers cbLazy with original coefficients, sense and RHS. Gurobi rejects that
candidate; even a previously added lazy row is resubmitted when necessary under
explicit user authorization. No rejected objective is admitted as UB. A passing
point must also pass the original nongrid/mobility/SOC/PCS/mode/connection,
bounds/integer and objective audits. Thus every recorded UB belongs to F under
the unchanged numerical authority. Registry uniqueness is an accounting
property, not an assumption that a native usercut/lazy pool is enforced forever.

Separator is PR158's direct sparse affine evaluator with cached CSR/absolute
CSR, outward floating-point enclosure and exact binary-rational fallback for
ambiguous rows at1e-8. It performs no LP or recourse optimization. <= and >= use
opposite residual signs, equality uses absolute residual. No coefficient/RHS
transformation occurs. All 81,216 grid auxiliary definitions stay in S0.

MIPNODE ranking/batches only affect acceleration; they cannot declare feasibility
or terminate successful certification. No application cut deletion, restart,
point rounding or scientific threshold modification occurs. Any unhandled
error/deadline-truncated lazy batch is fail-closed. OPTIMAL/TIME_LIMIT labels
alone never establish scientific acceptance. One optimize maintains one tree.

12 inherited bounded physical constructors are used only to construct tiny
original MILPs, never Benders recourse. 1,536 binary assignments are checked
against complete monolithic feasible statuses/optima. A separate fractional
node fixture exercises cbCut; direct reconstruction covers all three senses.
An explicit duplicate re-rejection protocol fixture confirms registry uniqueness
with authorized native cbLazy reuse. Fullscale gate also checks saved starting
point on the entire original unreduced matrix, all grid rows and native physical
validators. Full result is independently rechecked after the one optimize call.
'''
    (OUT/'M1_ONE_TREE_BC_EXACTNESS_PROOF.md').write_text(proof,encoding='utf8')
    print('PREPARED_NO_NATIVE_SOLVE',seedcheck['objective'],floor,len(grid),flush=True)
if __name__=='__main__':run()
