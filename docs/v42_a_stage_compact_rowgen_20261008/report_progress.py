"""Read-only aggregation; never authorizes or invokes a native solve."""
import json,csv,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def build():
    frozen=read('FROZEN64_RESULT.json');p1=read('P1_RESULT.json');integer=read('INTEGER_RESULT.json');clock=read('OVERNIGHT_START.json')
    results=[]
    for p in sorted(OUT.rglob('NATIVE_RESULT.json')):
        r=json.loads(p.read_text(encoding='utf-8-sig'));results.append(dict(folder=p.parent.relative_to(OUT).as_posix(),**r))
    stats=dict(completed_native_solves=len(results),native_seconds=sum(r.get('native_seconds') or 0 for r in results),
        Work=sum(r.get('Work') or 0 for r in results),peak_RSS_bytes=max((r.get('peak_RSS_bytes') or 0 for r in results),default=0),
        max_factor_nnz=max((r.get('max_factor_nnz') or 0 for r in results),default=0),
        max_factor_memory_GB=max((r.get('max_factor_memory_GB') or 0 for r in results),default=0),
        wall_seconds=time.time()-clock['start_unix'],remaining_seconds=max(0,clock['deadline_unix']-time.time()),
        inflight_solve_not_in_completed_totals=True)
    (OUT/'AGGREGATE_PROGRESS.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf8')
    with (OUT/'ALL_COMPLETED_NATIVE_SOLVES.csv').open('w',newline='',encoding='utf8') as f:
        keys=['folder','status','objective','ObjBound','native_seconds','Work','NodeCount','peak_RSS_bytes','max_factor_nnz','max_factor_memory_GB']
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(results)
    case=read('P2_CASE_RESULT.json') if (OUT/'P2_CASE_RESULT.json').exists() else None
    if (OUT/'P2_CG_RESULT.json').exists():case=read('P2_CG_RESULT.json')
    recovery=read('CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json') if (OUT/'CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json').exists() else None
    trajectories=list(csv.DictReader((OUT/'PHASE1_ITERATION_TRACE.csv').open(encoding='utf8')))
    closed=read('M19/FROZEN64/ALL_REMAINING_ROWS/NATIVE_RESULT.json');identity=read('M19/FROZEN64/ALL_REMAINING_ROWS/MODEL_IDENTITY.json')
    trajectories.append(dict(solve=19,Phi=0,exact_Phi='0',row_closed=True,rows=identity['rows'],cols=identity['cols'],nnz=identity['nnz'],
        added_rows='ALL_REMAINING',Runtime=closed['native_seconds'],Work=closed['Work'],factor_nnz=closed['max_factor_nnz'],
        factor_memory_GB=closed['max_factor_memory_GB'],separation_seconds='ANALYTIC_ALL_ROWS_PRESENT',elapsed_wall=frozen['elapsed_wall_seconds']))
    with (OUT/'COMPLETE_PHASE1_MASTER_TRAJECTORY.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(trajectories[0]));w.writeheader();w.writerows(trajectories)
    classification=case['classification'] if case else integer['classification']
    text=f'''# Overnight A-stage practical exact solver

Current classification: **{classification}**. This report is refreshed during execution; the final repository handoff records the final HEAD and remote match separately.

## Scope and immutable budget

Stacked on Draft PR178, exact `e8c7634002cb6249ef79aacd585017b3cfaf0bd2`. Immutable UTC start 2026-10-07 16:53:17; deadline 2026-10-08 00:53:17 (KST 09:53:17). Every native solve uses Threads=1 and the inherited tolerances/objective hierarchy. Pricing is sequential, below the maximum four workers. RAM and system commit are sampled; the M lane is untouched. No production, Planning, Actual or Fresh AC execution is authorized.

## Exact representation actually used

Pure physical path lambdas fail to represent the original fractional native migration LP: with unshared Big-M links, fractional ACTIVE can coexist with zero WAN bytes. Bounded N=1/2/3 STAY/migration fixtures preserve that counterexample and verify the exact hybrid instead. Identical continuous optional lanes are summed exactly; a perspective residual kernel retains every nonprojectable fractional direction. Concrete path mass is lifted together with the residual, with exact coefficient checks for all couplings. Inverse lift uses zero path mass and retains the native fractional point. HIST counts remain unchanged. SUM migration lanes are never integerized: P1 integers restore actual original N native lanes and types. See `EXACT_PROJECTION.json`, `QUALIFICATION_TESTS.json`, `INTEGER_TESTS.json` and the source-bound archives.

| Model | Rows | Columns | nnz |
|---|---:|---:|---:|
| Frozen64 expanded original | 1,046,444 | 362,044 | 14,820,623 |
| Frozen64 full hybrid, artificial-free | 739,158 | 82,458 | 13,797,701 |
| Initial reduced Phase-I | 58,842 | 97,566 | 1,377,612 |
| Closed full Phase-I with artificials | {identity['rows']:,} | {identity['cols']:,} | {identity['nnz']:,} |
| P1 original integer control | 1,046,444 | 362,044 | 14,820,623 |
| Complete relevant MIG=0 integer domain | 732,455 | 255,356 | 23,972,931 |
| Same integer domain with inherited valid cuts | 732,618 | 255,356 | 23,979,160 |

## Frozen64 Phase-I and row closure

The exact PR178 batch was activated once: 32 STAY + 32 migration. No repricing or reselection preceded materiality. Phi before `{frozen['Phi_before']}`; certified Phi after **0**, reduction **100%**. S0 through S18 each returned raw Phi=0 but failed omitted-row closure; none was treated as scientific zero. `PHASE1_ITERATION_TRACE.csv` records every master solve, added rows, runtime, work and factor memory. All violated omitted rows above 1e-6 were added. After measured small-cut tail behavior, all remaining original rows were promoted in the same experiment. The final all-row solve took 137.900s; original expanded artificial-free replay had maximum row violation 9.095e-13 and zero bound violation. All artificials were removed before P1. Positive-Phi adaptive pricing was unnecessary; no stagnation classification was made.

Phase-I total native time **{frozen['native_seconds']:.3f}s**, Work **{frozen['Work']:.3f}**, recorded wall through closure **{frozen['elapsed_wall_seconds']:.3f}s**. There were **20 actual master solves**: 19 reduced solves and one all-row continuation. The historical `master_solves=19` field retains the first segment's count; `COMPLETE_PHASE1_MASTER_TRAJECTORY.csv` includes the continuation. Maximum factor 17.73M nnz / 0.5GB. The intentional source-bound architecture handoff and earlier segment remain archived; there was no candidate reset.

## Original P1 closure and global integer gap

One full original-row P1 LP and one complete pricing round covered all 150 classes, including 197,537 STAY and 97,724,022 migration options and their original fractional kernels. All omitted-block reduced-cost lower bounds were nonnegative. Artificial-free original replay passed. Rational dual correction gives full-domain LB **{p1['valid_LB']}** (`{p1['exact_valid_LB']}`). LP value **{p1['P1_LP_value']}**. Pricing wall was 176.939s. `M19/P1/S0/PRICE/FULL_PRICING_RESULT.json` retains complete class coverage and individual oracle certificates.

The original integer control returned a fully replayed 1,023-job A1 point in 27.968s / Work31.885, one native node. UB **{integer['global_UB']}**. Full-domain gap ratio **{integer['global_gap']:.16g}**, or **{100*integer['global_gap']:.16g}%**, below 0.5%. The control's active-only MIP bound was **not** used as the global P1 LB. The independently closed root LP plus original integer primal sufficed, so the external deterministic best-bound queue has one closed root and zero P1 children. P1 native node rate is approximately 128.7/hour; no multi-node P1 tractability claim is implied. The checkpoint contains the root, incumbent, closure and hashes.

## P2 under inherited locks

Rho lock is the inherited +1e-7 rule. Migration count **0** is globally certified by a fully replayed original integer point and the universal nonnegative objective bound. Only then is the complete MIG=0 relevant integer domain built: all full STAY options, all remaining original singleton native kernels, all original global rows, and exact zero projection of optional lanes. Migration candidates remain in the scientific domain and are excluded only within this certified prior-objective query.

The first full-domain Shift control produced UB950 / native bound946. Independent external LP children retained both branches; one interval dual certificate failed because an unbounded variable had a tiny wrong-sign reduced cost, so that open child was not pruned. Inherited integer-valid histogram cuts add 163 rows / 6,229 nnz and preserve integer schedules/objectives; they strengthen the LP.

A complete-domain objective partition Shift≤949 OR Shift≥950 was preserved. The left native search processed 2,009 nodes in 1,186.011s / Work2,220.580 without a new primal, terminating at its component allocation with current ObjBound948. It was not called infeasible. A separate recovery combines that current verified full-domain bound with the analytic right-child LB950, yielding stage LB948 / UB950. The actual Gurobi CSR, boxes, types, senses, RHS and objectives were independently read back and matched exactly. This is the repository's current-native complete-integer-model bound authority, **not an independent rational MIP dual proof**. [Gurobi ObjBound contract](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound) defines the post-solve bound, including objective-integrality rounding.

The continuing exact-Z architecture adds Z=the inherited integer affine objective, preserving the original LP projection and integer schedules. Both Z=k and Z≥k+1 children remain recorded. A feasible fixed-value case plus the full-domain lower bound certifies the integer optimum; proven current full-domain integer infeasibility advances k; a time-limited case stays open. Checkpoints are written every ten native nodes or five minutes. Prestart follows only a certified Shift lock. Current final-case result: `{None if case is None else {k:v for k,v in case.items() if k in ('A1_accepted','classification','migration_count','shift_magnitude','prestart_relocation','stop_reason')}}`.

Independent LP certificate recovery subsequently diagnosed four exact negative reduced costs of -1/1125899906842624 on unbounded variables. Full original-row upper-box propagation still left 7,104 unbounded global variables. A separate certificate dual proposal sets four legal Pi components to zero; raw Pi, solver points and native bounds remain unchanged. The complete interval Lagrangian bound was recomputed successfully: `{None if recovery is None else recovery.get('valid_LB')}`. Both old LP children are now closed in a separate restored queue, with parent-inherited global LP LB899.1914018481151; neither child is pruned. This repairs the numerical certificate obstruction and does not certify an integer optimum or replace the stronger current native integer LB948. The actual original-row LP child runtimes were 8.58s and 9.61s (median9.095s, interpolated p909.507s); the sample has only two children.

Prepared weighted integer histogram capacity rounding adds 23 valid rows / 1,225 nnz to the inherited 163-cut model. It preserves every original integer schedule and objective and strengthens only the LP relaxation. Its exact formula is sum(floor(g/d)*y)<=floor(R/d), derived from the actual nonnegative integer GPU binding. `WEIGHTED_CG_BUILD_VERIFICATION.json` records static preparation; native application is claimed only if a later `P2_CG_STARTED.json` and completed native results exist. No solver parameter sweep is used.

## Conditional canaries and measured totals

May17 → May12 → May10 can execute only after May19 A1 acceptance with at least 5,400s remaining at the trigger. The same completed architecture and policies are used without retuning. No other date is included. Individual results, when present, live in `CANARIES/<date>/RESULT.json`; prepared code is not evidence of execution.

Completed solves: **{stats['completed_native_solves']}**; total native **{stats['native_seconds']:.3f}s**, Work **{stats['Work']:.3f}**; maximum observed own-process RSS **{stats['peak_RSS_bytes']:,} bytes**; elapsed wall **{stats['wall_seconds']:.3f}s**. In-flight work is excluded until its native result persists. `ALL_COMPLETED_NATIVE_SOLVES.csv` is the deduplicated per-folder ledger. Static build, serialization, full physical replay and source hashing contribute to wall time separately. The P1 target is already reached; the current measured bottleneck is exact P2 Shift integer closure, not P1 gap.

Source freezes record each actually executed commit, exact source file hashes and immutable ZIP archive. Matrix/point binaries remain in the external static directory with SHA256 receipts; repository evidence includes the replay, identity, source, trace and certificate JSON/CSV/log files.
'''
    (OUT/'REPORT.md').write_text(text,encoding='utf8');print(json.dumps(stats))
if __name__=='__main__':build()
