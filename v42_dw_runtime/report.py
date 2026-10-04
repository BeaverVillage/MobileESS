"""Build review artifacts from existing bounded evidence; never invoke a solver."""
from dataclasses import asdict, fields
from pathlib import Path
import hashlib
import json
import subprocess

from .contracts import BASE_HEAD, RuntimeFlags
from .audit import AuditAuthority

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_m1_dw_runtime_acceleration'


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf8'))


def write(name, text):
    (OUT/name).write_text(text.strip()+'\n', encoding='utf8', newline='\n')


def main():
    base = read('DW_RUNTIME_BASE_AUDIT.json')
    early = read('DW_EARLY_STOP_FIXTURE.json')
    parallel = read('DW_PARALLEL_VALIDATOR_EQUIVALENCE.json')
    cache = read('DW_AUDIT_CACHE_INVALIDATION_TEST.json')
    equivalent = read('DW_PERSISTENT_RMP_EQUIVALENCE.json')
    timing = read('DW_PERSISTENT_RMP_TIMING_TOY.json')
    restart = read('DW_PERSISTENT_RMP_RESTART_TEST.json')
    certification = read('DW_CERTIFICATION_FIREWALL_TEST.json')
    resources = read('DW_BOUNDED_RESOURCE_RECEIPT.json')
    tests = read('DW_LANE_C_TEST_RECEIPT.json')
    assert all(p['PASS'] for p in (base, early, parallel, cache, equivalent, timing, restart, certification, resources))
    assert tests['exit_code'] == 0 and tests['counts']['failed'] == 0
    assert tests['observed_calls_nonoverlapping'] and tests['observed_all_solver_calls_bounded']
    flags = dict(DW_EARLY_STOP_IMPLEMENTED=True, DW_EARLY_STOP_FULL_SCALE_RUN=False,
        DW_PARALLEL_VALIDATION_IMPLEMENTED=True, DW_PARALLEL_VALIDATION_FULL_SCALE_RUN=False,
        DW_INCREMENTAL_AUDIT_IMPLEMENTED=True, DW_PERSISTENT_RMP_IMPLEMENTED=True,
        DW_PERSISTENT_RMP_FULL_SCALE_RUN=False, DW_WARM_BASIS_SELECTED=False,
        CERTIFICATION_SEMANTICS_PRESERVED=True, FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True,
        MAY_PRODUCTION_CALLS=0)
    write('DW_RUNTIME_BASE_AUDIT.md', f"""
# Lane C base authority

Repository: BeaverVillage/MobileESS. Branch: codex/v42-m1-dw-runtime-acceleration-prep.
Exact PR143 head: `{BASE_HEAD}`. Base selection was independently checked with `gh pr view 143`.
Parent authority retained checkpoint: {base['retained_checkpoint_columns']} columns.
Source and checkpoint Git blob identity is recorded in DW_RUNTIME_BASE_AUDIT.json.
The checkpoint pool was read for registry identity only; no historical full physical audit
or scientific matrix load was performed in this lane. Existing receipts are not silently
promoted into the new cache schema: missing matching receipts trigger re-audit on integration.

PR142/143 authority remains: actual four-way pricing PASS (historical, not rerun),
Threads=1, RAM floor=1 GiB, adaptive smoothing in Discovery only, true RC <= -1e-7,
up to 4 columns/MESS and 16/round. Warm RMP basis remains rejected.
Historical columns/minute 0.809981 -> 6.910010; Discovery median 70.334 s;
cold/warm RMP medians 33.996/38.943 s are user-provided PR142 context, not Lane C measurements.

Changes are new helper/test/evidence packages only. Production scientific modules,
pricing domain, certificates, retained pool and campaign orchestration are untouched.
No merges/rebases from other lanes, production optimization, May calls, or full pytest.
""")
    first, continued = early['runs']
    write('DW_EARLY_STOP_DESIGN.md', f"""
# Discovery quota controller

`DiscoveryController` is an opt-in per-MESS adapter. The same immutable DiscoverySnapshot
must be created from the completed RMP before all worker jobs are dispatched.
It includes true/smoothed coupling duals, both convexity dual vectors, alpha, RMP objective,
iteration and exact PR143-compatible dual SHAs. Tuples detach the snapshot from source arrays.

Inside MIPSOL, the adapter performs the existing PR143 block physical validator,
the complete original-local corrected-row/integrality audit, and exact_rc under the true
same-iteration dual. Search RC and the native objective must also agree within 1e-8.
Only distinct PR143 column SHA values that are legal, true RC <= -1e-7, and absent from
the retained MESS set fill the quota. Hash identity uses the original x/a/c hash function.
MESS ownership is carried separately; axis identity prevents cross-MESS cache reuse.

After four accepted columns, terminate() is requested once and acceptance is frozen.
The reason is DISCOVERY_QUOTA_FILLED. Any callback exception aborts and clears addable
results. Errors, duplicates, nonintegral points and smoothed-only negatives never fill quota.
Discovery receipts always set optimality, convergence, valid_bound and no-negative claims false.
INTERRUPTED (11) is expected; it is never promoted to OPTIMAL (2).
Caller cancellation must still be combined with this callback by the integrating worker.

DW_EARLY_STOP_FIXTURE.json uses a synthetic 586-variable, 2-row model with ten selector
profiles and the real PR143 96-slot idle-route/SOC/PCS validators. Nine profiles are valid
true-negative trajectories; one is negative only under the smoothed dual. Ten feasible
MIP starts expose native MIPSOL observations without fixing or restricting the domain.
Early/continued models have identical matrix, bounds and objective identities.
Quota run status={first['status']}, accepted={first['receipt']['accepted_count']};
continued status={continued['status']}. All added columns passed original audits.

The quota request occurred at callback {first['quota_request_callback_index']}.
Gurobi issued {first['native_callbacks_after_quota_request']} further callbacks while completing
start processing; the controller added no more columns. Termination is cooperative.
Measured wall times: early {first['optimize_seconds']:.6f} s, continued {continued['optimize_seconds']:.6f} s.
This toy does not establish a runtime benefit or production speedup. It proves safe acceptance
and terminal semantics. Production callback latency and solver-thread interaction remain
integration measurements for an authorized later lane; full-size pricing was not executed.
Certification controllers are disabled even when all four runtime flags are enabled.
""")
    write('DW_PARALLEL_VALIDATOR_DESIGN.md', f"""
# Canonical validation batches

`validate_batches` dispatches one immutable candidate batch per MESS with ThreadPoolExecutor,
at most four threads. Read-only block prototypes and the same immutable snapshot are supplied
by the caller. The task uses original Python physical/row audits and exact RC arithmetic;
it never builds or optimizes Gurobi models. Workers return immutable ValidationResult values.

Results are canonicalized by the full sorted JSON record and identical observations are
deduplicated. MESS, SHA, iteration, dual SHA, acceptance, reasons, true/search RC, maximum
residual and all original physical residual reports participate in equality. Different
observations of a trajectory, including stale-dual observations, keep their distinct reasons.
Accepted and rejected SHA sets describe observations and can overlap for a stale retry.

The bounded fixture validates {parallel['bounded_candidates']} observations across four
synthetic MESS contexts, reverses worker and arrival order, and compares results exactly.
PASS includes smoothed-only negative, nonintegral, physical invalid, stale and duplicate inputs.
Thread wall time {parallel['parallel_wall_seconds']:.6f} s is a toy measurement only.
Python GIL and original validator work may limit CPU scaling; no four full-size validators
were launched, and no production parallel speed claim is made. A future process variant
must transport solver-free prototypes and preserve identical canonical output.
""")
    write('DW_PERSISTENT_RMP_DESIGN.md', """
# Retained model construction prototype

RMPRows and RMPColumn are immutable mathematical registry records. PersistentRMP retains
the Gurobi object, creates fixed coupling/convexity rows once, appends lambda columns with
gp.Column, and calls update. The default build_rmp path builds a fresh model; the persistent
flag reuses a model only when rows and the complete prior registry prefix are exactly equal.
Changed coefficients, row identity, bounds, senses or objectives require reconstruction.
All variables are continuous; production adapters must map master z and lambda coefficients
in their original order. The prototype does not alter the production Master class.

Model.reset(0) precedes EVERY optimization and LPWarmStart=0 is explicit. No VBasis/CBasis
is imported, exported, read, or intentionally selected. Native implementation caches other
than discarded solution state may remain; the experiment measures construction/update
architecture and is not a warm-basis retest. There is no solver parameter sweep.

The representative toy has two MESS convexity equalities, one capacity inequality,
an objective constant and four append iterations. At each iteration, full native identities
are compared: row/column counts, nnz, matrix, names, RHS, senses, bounds, types, coefficients,
constant and model sense. Objective, primal solution and duals agree within absolute 1e-8.
The chosen toy has comparable primal/dual optima; equality of returned primal/dual vectors
is not generally guaranteed for degenerate production LPs, even for identical matrices.

Disk rows/column registry is authoritative and has a canonical SHA integrity binding.
The prior model is disposed, the disk registry reloaded and a new model reconstructed;
matrix identity, objective, primal and dual recovery pass. This is a simulated model/process
restart, not a real process-kill experiment. No in-memory basis is required by the checkpoint.

Timing records separate Python registry reconstruction, native model build, persistent
add-column/update and optimize wall time. Initial persistent build is a separate field.
The resource guard samples before/after native calls; its overhead is in wrapped wall times.
Native Gurobi Runtime is also recorded separately. There are no production extrapolations.
""")
    table = '\n'.join(f"| {r['iteration']} | {r['fresh_python_reconstruction']*1e3:.3f} | {r['fresh_Gurobi_build']*1e3:.3f} | {r['fresh_optimize']*1e3:.3f} | {(r['persistent_initial_build'] if r['iteration']==0 else r['persistent_add_column_update'])*1e3:.3f} | {r['persistent_optimize']*1e3:.3f} |" for r in timing['seconds'])
    write('DW_RUNTIME_INTEGRATION_GUIDE.md', f"""
# Later integration of four independent adapters

No production caller is switched on by this PR. RuntimeFlags are all false by default;
from_environment accepts explicit true/false or 1/0 values. Integrators must pass the flags
to the helper being used. DW_DISCOVERY_EARLY_STOP, DW_PARALLEL_VALIDATION,
DW_INCREMENTAL_AUDIT and DW_PERSISTENT_RMP are independent. Merely setting environment
variables on the original PR143 runner currently has no effect.

1. Capture true and smoothed pi/convexity arrays BEFORE optimizing any worker; create one
   DiscoverySnapshot. Send all four workers that same iteration and exact SHA authority.
   The solver search objective must match smoothed pi/convexity only for Discovery.
2. Prepare OriginalBlockValidator with the original PR143 block/prototype and COMPLETE
   original local matrix/attribute/route-mask slice. Keep its inputs read-only during workers.
   The controller callback is combined with original cancellation/capture logic.
   Supply retained SHAs per MESS; save accepted result and trajectory together.
   Recheck returned Candidate bindings against the same snapshot before adding a column.
3. Pricing workers return candidate batches. Opt-in validate_batches performs only Python
   audit work. Canonical results remain equal regardless of worker or candidate ordering.
   Tier 1 always performs full physical/local/integrality and current RC checks.
4. Build AuditAuthority from every scientific/local/coupling matrix and relevant attributes,
   variable/local row axes, complete validator dependency source bytes, physical inputs and
   numerical tolerance authority. The scientific base SHA alone is insufficient. Recompute
   each trajectory SHA from checkpoint values; a filename/mtime is never an authority key.
   The cache schema hashes trajectory SHA plus the complete exact authority vector.
   Existing old-format receipts have no matching key and must be re-audited before reuse.
5. execute_audit_tiers requires original current RMP point auditor EVERY round. Under
   incremental Discovery, it fully audits new and stale columns and reuses only matching
   retained physical receipts. Current RC must still be recomputed against the current dual;
   historical receipt RC is provenance only. Tier 3 Certification/final checkpoint always
   fully audits the retained pool. Audit failures abort without committing staged receipts.
6. PersistentRMP is a prototype: map original fixed rows, z variables and column registry.
   Append only; changed scientific authority requires reconstruction. Preserve checkpoint
   registry as the restart source. reset(0), LPWarmStart=0 and no basis import stay mandatory.
7. Certification remains routed through the original code: unstabilized true dual, finite
   valid global BestBd for each MESS and the unchanged exact corrected LB. Never pass
   quota INTERRUPTED receipts or smoothed values to certificate.receipt.

The likely shared integration edits are v42_dw_throughput/worker.py (snapshot loaded before
pricing, callback combination), v42_dw_throughput/run.py (batch validation/audit tiers/RMP
construction), and v42_dw_resume/audit.py / v42_dw_root/models.py adapters. They overlap
possible Lane A/B changes. Lane C edits none of these files. No merges/rebases from A/B/D
were performed. Resolve integration later against its then-authoritative checkpoint.

Validation commands are `python -m v42_dw_runtime.fixtures`,
`python -m v42_dw_runtime.testing`, `python -m compileall -q v42_dw_runtime tests/v42_dw_runtime`,
and `git diff --check`. The testing entrypoint selects only tests/v42_dw_runtime and
enforces Threads=1, TimeLimit<=30 and nonoverlapping native optimize calls. It never selects
full pytest. Fixtures use TimeLimit=5 seconds, one process, no memory stress or production inputs.

Toy timing, milliseconds (persistent column 0 is initial build):

| Iteration | Python reconstruct | Fresh build | Fresh optimize wall | Retained build/update | Retained optimize wall |
| --- | --- | --- | --- | --- | --- |
{table}

These are single toy observations with guard overhead, not production performance estimates.
""")
    schema = dict(
        **{'$schema': 'https://json-schema.org/draft/2020-12/schema'},
        title='DW immutable physical audit receipt', type='object', additionalProperties=False,
        required=['trajectory_SHA','authority','max_residual','true_RC','true_dual_SHA','iteration','timestamp','run_id','physical_residuals_json'],
        properties=dict(trajectory_SHA=dict(type='string', pattern='^[a-f0-9]{64}$'),
            authority=dict(type='object', additionalProperties=False,
                required=[f.name for f in fields(AuditAuthority)],
                properties={f.name:dict(type='string',pattern='^([a-f0-9]{40}|[a-f0-9]{64})$'
                    if f.name == 'scientific_base_SHA' else '^[a-f0-9]{64}$') for f in fields(AuditAuthority)}),
            max_residual=dict(type='number',minimum=0), true_RC=dict(type='number'),
            true_dual_SHA=dict(type='string',pattern='^[a-f0-9]{64}$'), iteration=dict(type='integer',minimum=0),
            timestamp=dict(type='string'),run_id=dict(type='string'),physical_residuals_json=dict(type='string')),
        description='Cache key = SHA256(canonical JSON of trajectory_SHA + exact authority). RC/dual SHA are historical provenance; no current RC reuse. Finite numbers and complete passing physical/local/integrality report required.')
    write('DW_INCREMENTAL_AUDIT_SCHEMA.json', json.dumps(schema, indent=2))
    peak = max(resources['peak_sampled_RSS_bytes'], tests['peak_sampled_RSS_bytes'])/2**20
    publication_path = OUT/'DW_PUBLICATION_RECEIPT.json'
    publication = json.loads(publication_path.read_text(encoding='utf8')) if publication_path.exists() else None
    publication_text = (f"Draft PR: [{publication['draft_PR']}]({publication['draft_PR']}). 최초 게시 SHA "
                        f"`{publication['first_published_head']}`의 원격 일치와 clean tree를 확인했다."
                        if publication else 'Draft PR 게시 후 DW_PUBLICATION_RECEIPT.json에 URL과 최초 게시 SHA를 기록한다.')
    write('FINAL_REVIEW_KO.md', f"""
# Lane C 최종 검토

1. 기준은 PR143 exact head `{BASE_HEAD}`이며 1,158개 retained registry를 보존했다.
2. {publication_text}
   브랜치 `codex/v42-m1-dw-runtime-acceleration-prep`의 Draft PR과 게시 SHA는
   DW_PUBLICATION_RECEIPT.json 및 PR의 현재 head를 확인한다. 최종 head는 후속 게시 기록
   커밋을 포함하므로 `git ls-remote origin refs/heads/codex/v42-m1-dw-runtime-acceleration-prep`가
   최종 SHA 권위다. 게시 후 사용자에게 최종 SHA를 별도로 보고한다.
3. DiscoveryController가 실제 MIPSOL에서 original local/physical audit, exact integrality,
   same-iteration true RC를 검사한다. 적법한 신규 SHA 4개에서만 terminate를 요청한다.
4. smoothed-only negative, 중복 및 기존 SHA, 물리/정수 실패는 quota에 포함하지 않는다.
   native 종료는 협력적이며 quota 이후 callback이 와도 수락은 4개로 고정된다.
5. true RC <= -1e-7, immutable dual SHA/iteration 검사를 유지했다. INTERRUPTED는
   OPTIMAL·no-negative certificate·pricing convergence로 해석하지 않는다.
6. MESS별 candidate batch를 최대 4개 Python thread로 검증하는 구조를 구현했다.
7. {parallel['bounded_candidates']}개 synthetic observation에 대해 순차/병렬의 수락·거부 SHA,
   reasons, true RC, physical residual이 정확히 동일했다. 실제 full-size validator는 실행하지 않았다.
8. Tier 1은 신규 후보 full audit, Tier 2는 매 RMP 현재 point + 신규/무효화 열,
   Tier 3은 Certification/final checkpoint 전체 retained pool audit로 구성했다.
9. scientific base/matrix, local row/variable axis, validator version, physical semantics,
   numerical tolerance SHA의 정확한 일치만 재사용한다. RC는 매 반복 다시 계산한다.
   기존 receipt에 신규 스키마 키가 없으면 재감사가 필요하다.
10. PersistentRMP는 모델 객체와 열 추가 구조만 보존한다. reset(0), LPWarmStart=0을
    적용하며 이전 VBasis/CBasis를 읽거나 import하지 않았다. warm-basis 선정은 false다.
11. 4개 toy 반복에서 행·열·nnz·행렬·RHS·senses·bounds·objective identity가 같고,
    해와 dual은 절대 허용오차 1e-8에서 일치했다.
12. Python 재구성·Gurobi build·열 update·optimize wall/native Runtime을 분리 기록했다.
    단일 toy 수치이며 production 배속 주장은 없다. early-stop toy도 속도 개선을 입증하지 않는다.
13. 기존 객체를 dispose하고 디스크 registry로 재구축한 simulated restart에서 같은 목적값,
    해·dual·행렬을 복구했다. 실제 process kill 시험은 수행하지 않았다.
14. 기존 Certification source는 byte/Git blob identity를 유지한다. 실제 기존 corrected 함수의
    exact Fraction 계산과 invalid INTERRUPTED receipt 거부를 회귀 검증했다.
15. 네 feature flag는 기본 false이며 독립적으로 helper에 전달한다. 기존 production runner는
    이 PR에서 연결하지 않았다. 환경변수만 설정하면 기존 runner가 변경되는 구조가 아니다.
16. 단일 Gurobi process, Threads=1, fixture당 TimeLimit=5 s. fixture optimize {len(resources['solver_calls'])}회,
    Lane C test optimize {len(tests['solver_calls'])}회는 모두 작은 모델이며 순차 실행됐다.
    관측 RSS 최대 {peak:.2f} MiB(호출 전후 표본), memory stress 없음. 공유 Lane A 프로세스는 측정하지 않았다.
17. Full-scale M1/Arc-LP/pricing, production RMP/OpenDSS, May 호출은 모두 0회다.
18. Lane C {tests['counts']['passed']}개 테스트 PASS, compileall/static diff 검사 PASS.
    FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=true로 repo-wide pytest는 유보했다.
19. 변경은 별도 helper/test/evidence에 한정했다. A/B/D merge/rebase 없음. 후속 통합 시
    worker callback·snapshot transport, run batch/audit/RMP 경로의 변경 충돌을 점검해야 한다.

이번 Lane C는 PR143 scientific model과 Certification semantics를
변경하지 않고 Discovery runtime을 줄이기 위한 실행 구조만
구현했다.

Full-scale M1/Arc-LP/pricing은 실행하지 않았으며 Lane A의 heavy
계산과 자원 경쟁을 만들지 않았다.
""")
    write('PR_DESCRIPTION.md', """
Prepare four independently opt-in Discovery runtime adapters against PR143 exact head
ce5d30fb9bcb91ab8395d1313e868d24f5fde517: fully validated true-RC quota stop,
canonical per-MESS thread validation, authority-bound immutable receipts/audit tiers,
and append-only persistent RMP construction with reset(0)/LPWarmStart=0.

Production scientific modules and callers remain untouched; flags default off.
Certification continues to use true unstabilized duals and original global BestBd/
exact corrected LB. Warm basis remains unselected. New helpers need later production integration.

Validation: Lane C unit tests and bounded native Gurobi fixtures only. Threads=1,
TimeLimit=5 s, sequential native calls. Early quota returns 4 legal true-negative
columns with INTERRUPTED, including a smoothed-only rejection. Sequential/thread
validation matches exactly. Four RMP append iterations and disk reconstruction
match matrix identity, objective, primal and duals. No production/full-scale solve,
May execution or repo-wide pytest. Timings are toy-only; no speedup extrapolation.

Evidence and Korean review: docs/v42_m1_dw_runtime_acceleration/.
""")
    compile_result = subprocess.run(['python','-m','compileall','-q','v42_dw_runtime','tests/v42_dw_runtime'], cwd=ROOT)
    diff_result = subprocess.run(['git','diff','--check'], cwd=ROOT)
    assert compile_result.returncode == diff_result.returncode == 0
    manifest = {str(p.relative_to(ROOT)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in (ROOT/'v42_dw_runtime', ROOT/'tests/v42_dw_runtime', OUT)
                for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                and p.name not in ('VERIFICATION.json','DW_PUBLICATION_RECEIPT.json','FINAL_REVIEW_KO.md')}
    write('VERIFICATION.json', json.dumps(dict(PASS=True, base_SHA=BASE_HEAD, flags=flags,
        production_integration_enabled=False, feature_defaults=asdict(RuntimeFlags()),
        narrow_test_counts=tests['counts'], test_exit_code=tests['exit_code'],
        static_compileall=True, static_git_diff_check=True, evidence_manifest=manifest,
        resources=resources, real_process_kill_test=False, simulated_model_restart_PASS=True,
        no_production_speedup_claim=True, no_pricing_domain_restriction=True,
        no_merge_or_rebase_from_other_lanes=True), indent=2))
    print('Lane C review artifacts: PASS')


if __name__ == '__main__':
    main()
