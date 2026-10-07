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
    if (OUT/'DIRECT_RESULT.json').exists():case=read('DIRECT_RESULT.json')
    direct=read('DIRECT_CHECKPOINT.json') if (OUT/'DIRECT_CHECKPOINT.json').exists() else None
    dual=read('PRIMAL_DUAL_RESULT.json') if (OUT/'PRIMAL_DUAL_RESULT.json').exists() else None
    bounds=[]
    for e in read('INTEGER_INCUMBENT_TRACE.json')['events']:
        bounds.append(dict(component='rho',LB=e['valid_LB'],UB=e['valid_UB'],gap_ratio=e['global_gap'],authority='FULL_PRICED_RATIONAL_ROOT_DUAL_AND_ORIGINAL_PRIMAL',source='INTEGER_INCUMBENT_TRACE.json'))
    bounds.append(dict(component='migration_count',LB=0,UB=0,gap_ratio=0,authority='UNIVERSAL_NONNEGATIVE_BOUND_AND_ORIGINAL_PRIMAL',source='P2_MIGRATION_PROBE_RESULT.json'))
    bounds.append(dict(component='shift_magnitude',LB=946,UB=950,gap_ratio=4/950,authority='CURRENT_COMPLETE_RELEVANT_INTEGER_MODEL',source='M19/P2/REFINEMENT/SHIFT_MAGNITUDE/N0/INDEPENDENT_INTEGER_BOUND_PROVENANCE.json'))
    bounds.append(dict(component='shift_magnitude',LB=948,UB=950,gap_ratio=2/950,authority='CURRENT_COMPLETE_NATIVE_BOUND_WITH_EXHAUSTIVE_SIBLING',source='INTERRUPTED_BOUND_RECOVERY.json'))
    for folder in ('EXACT_CASES','WEIGHTED_CG'):
        for path in sorted((OUT/'M19/P2'/folder).rglob('INTEGER_BOUND_PROVENANCE.json')):
            r=json.loads(path.read_text(encoding='utf-8-sig'))
            if r.get('PASS') and r.get('valid_stage_LB') is not None:
                L=r['valid_stage_LB'];bounds.append(dict(component='shift_magnitude',LB=L,UB=950,gap_ratio=(950-L)/950,authority='CURRENT_COMPLETE_NATIVE_BOUND_WITH_EXHAUSTIVE_SIBLING',source=path.relative_to(OUT).as_posix()))
    if direct is not None:
        for e in direct.get('events',[]):
            bounds.append(dict(component=e['component'],LB=e['LB'],UB=e['UB'],gap_ratio=(e['UB']-e['LB'])/abs(e['UB']) if e['UB'] else 0,authority='COMPLETED_DIRECT_MODEL_AND_EXHAUSTIVE_SIBLING',source='DIRECT_CHECKPOINT.json'))
    with (OUT/'VALID_GLOBAL_BOUND_TRAJECTORY.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(bounds[0]));w.writeheader();w.writerows(bounds)
    recovery=read('CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json') if (OUT/'CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json').exists() else None
    repair=read('PRIMAL_REPAIR_V2_RESULT.json') if (OUT/'PRIMAL_REPAIR_V2_RESULT.json').exists() else None
    repair_calls=[r for r in results if '/PRIMAL_REPAIR' in r['folder']]
    cg=read('P2_CG_CHECKPOINT.json') if (OUT/'P2_CG_CHECKPOINT.json').exists() else None
    cg_stop=read('CG_RESOURCE_STOP_DIAGNOSIS.json') if (OUT/'CG_RESOURCE_STOP_DIAGNOSIS.json').exists() else None
    transportation=read('EXACT_TRANSPORT_RESULT.json') if (OUT/'EXACT_TRANSPORT_RESULT.json').exists() else None
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
| Same integer domain with weighted CG cuts | 732,641 | 255,356 | 23,980,385 |

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

The weighted-CG continuation preserves the prior integer bound and incumbent. Its first query covers Z in [ceil(validLB-1e-6), UB-1], while the Z>=UB sibling is recorded with analytic LB=UB. An open interval then enters the same exhaustive fixed-value case architecture. The current persisted stage ledger has LB `{None if cg is None else cg.get('valid_global_LB')}` and UB `{None if cg is None or cg.get('incumbent') is None else cg['incumbent']['value']}`; in-flight callback values are progress only.

The weighted-CG first interval completed 188 nodes in 1,189.448s / Work2,851.274 without a primal. Its following exact case stopped after 156.178s / one node because the system RAM guard observed 1,929,695,232 bytes available, below the 2GiB reserve. The generic runner message names the component limit; `CG_RESOURCE_STOP_DIAGNOSIS.json` records the actual resource cause. Status11 is not infeasibility. Total weighted-CG native time was 1,345.626s / Work3,123.764, with LB948 / UB950 preserved. All subsequent native execution is sequential. The system commit still had headroom; the RAM guard stopped the A process and did not inspect or control M.

A separate primal-only repair architecture proposes one-count histogram transfers that reduce Shift 950 to 948. Thirty-one proposals passed exact objective and GPU-box screening. Screening is not physical feasibility. Each temporary query fixes the original integer assignment and retains all original rows, continuous bounds, scientific objectives and inherited locks. Its LP bound is never used as a domain bound or to delete a candidate. Only a row/bound/integrality-qualified point followed by full original physical replay can become a UB. The first 90-second allocation ended with a raw point rejected by physical reconstruction; that source epoch and result are preserved. The next epoch applies the row/bound/integrality gates before physical reconstruction and allocates 180 seconds per query, with unchanged native solver policy. Completed repair calls: `{len(repair_calls)}`. Latest completed repair result: `{None if repair is None else {k:v for k,v in repair.items() if k in ('accepted','value','valid_LB','stop_reason')}}`. Two simultaneous A-stage solves, when used, each have Threads=1 and system-wide RAM/commit guards; no M process is inspected or controlled.

Primal-only exact original-row invariant pair swaps generated zero improving proposals. A pure-Python integer successive-shortest-path transportation method also considered multi-class cycles, preserving class/site mass and the occupied start histogram for equal GPU/service-length groups. Every proposed change must cancel exactly in every original scientific matrix row and pass the full physical replay. It used zero native solves and returned Shift `{None if transportation is None else transportation['shift']}` with no new UB. These restricted primal searches provide no full-domain lower bound. Bounded fixtures include a three-cycle missed by pair swaps and exact coupling-drift rejection.

Read-only parent-basis qualification verifies every CSR coefficient, row sense and RHS on 732,457 rows / 255,356 columns. Only unresolved fixed-assignment queries may reuse that basis with dual simplex / LPWarmStart2; previously infeasible temporary assignments and every scientific candidate remain recorded. The completed basis continuation reported all three previously open fixed assignments infeasible in 60.427s / Work215.961, without a new UB. Temporary-assignment infeasibility does not delete scientific candidates. The direct continuation uses the original affine integer objective, without Z, with exhaustive objective<=UB-1 / objective>=UB siblings. Incumbent [variable hints](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#varhintval) are nonbinding heuristic guidance; they never supply a bound or pruning authority. Matrix/box/type/RHS/objective read-back and full physical primal replay remain mandatory. Observed node rates differ between the inherited objective-row search and the Z-based searches; these are not an isolated causal benchmark. Actual direct execution is evidenced by `DIRECT_STARTED.json`, the immutable `DIRECT_SOURCE_FREEZE.json`, and completed per-query native results. Its current/final ledger and result appear below; in-flight callback bounds alone never certify closure.

## Conditional canaries and measured totals

May17 → May12 → May10 can execute only after May19 A1 acceptance with at least 5,400s remaining at the trigger. The same completed architecture and policies are used without retuning. No other date is included. Individual results, when present, live in `CANARIES/<date>/RESULT.json`; prepared code is not evidence of execution.

Completed solves: **{stats['completed_native_solves']}**; total native **{stats['native_seconds']:.3f}s**, Work **{stats['Work']:.3f}**; maximum observed own-process RSS **{stats['peak_RSS_bytes']:,} bytes**; elapsed wall **{stats['wall_seconds']:.3f}s**. In-flight work is excluded until its native result persists. `ALL_COMPLETED_NATIVE_SOLVES.csv` is the deduplicated per-folder ledger. Static build, serialization, full physical replay and source hashing contribute to wall time separately. The P1 target is already reached; the current measured bottleneck is exact P2 Shift integer closure, not P1 gap.

Across completed stages the maximum factor was `{stats['max_factor_nnz']:,}` nnz / `{stats['max_factor_memory_GB']}` GB; the Phase-I-specific maximum remains 17.73M / 0.5GB.

Source freezes record each actually executed commit, exact source file hashes and immutable ZIP archive. Matrix/point binaries remain in the external static directory with SHA256 receipts; repository evidence includes the replay, identity, source, trace and certificate JSON/CSV/log files.
'''
    text+='''\n## Continuation receipts\n\n'''
    text+=f"Completed qualified parent-basis continuation: `{None if dual is None else {k:v for k,v in dual.items() if k in ('accepted','attempts','native_seconds','Work','stop_reason')}}`. This is a primal-only repair; no temporary-query bound supplies full-domain authority.\n\n"
    text+=f"Original-objective direct continuation: `{None if case is None or not (OUT/'DIRECT_RESULT.json').exists() else {k:v for k,v in case.items() if k in ('A1_accepted','stages','native_seconds','Work','stop_reason')}}`. Current persisted direct ledger: LB `{None if direct is None else direct.get('valid_global_LB')}`, UB `{None if direct is None or direct.get('incumbent') is None else direct['incumbent']['value']}`. A running ledger is progress; final domain bound authority requires the completed native result, actual model read-back and exhaustive sibling partition.\n\n"
    text+="Exact final HEAD, Draft PR URL, remote match and clean tree are recorded after the final commit in the external `FINAL_HANDOFF.json` and `FINAL_REPORT.md`, outside the worktree to avoid a self-referential commit hash.\n"
    (OUT/'REPORT.md').write_text(text,encoding='utf8');print(json.dumps(stats))
if __name__=='__main__':build()
