"""Publish source wiring evidence separately from deferred scientific results."""
from pathlib import Path
import hashlib
import json

from .contracts import digest
from .readiness import readiness

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/v42_b3_implementation_completion_20261009"
BUILD_DOCS = ROOT / "docs/v42_b2_b3_build_optimization_20261009"
V6_HEAD = "0f3da66e6edadc45f75d55011affcd3d2ec6954d"


def write(folder, name, value):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def reports():
    if ROOT != Path("D:/MobileESS_v42_B3_prep").resolve():
        raise PermissionError("REPORTS_REQUIRE_B3_WORKTREE")
    light = json.loads((DOCS / "B3_LIGHTWEIGHT_REGRESSION.json").read_text(encoding="utf-8"))
    if light["status"] != "LIGHTWEIGHT_TEST_PASS":
        raise ValueError("PASS_REPORT_REQUIRES_SUCCESSFUL_LIGHTWEIGHT_REGRESSION")
    pending = {"May01_original_FULL_equivalence": "NOT_RUN", "May23_original_FULL_equivalence": "NOT_RUN",
        "original_complete_A_domain_and_pricing_scientific_replay": "NOT_RUN",
        "original_FULL_Compact_C3A_scientific_replay": "NOT_RUN", "real_integer_physical_replay": "NOT_RUN",
        "real_stage_independent_exact_Global_LB_UB": "NOT_RUN", "measured_Gurobi_Runtime_and_peak_RSS": "NOT_RUN",
        "actual_OpenDSS_NormalAmps_RegControl_replay": "NOT_RUN", "real_baseline_optimized_equal_scope_timings": "NOT_RUN",
        "IEEE8500_2025_05_01_B0_B1_B2_B3": "NOT_RUN"}
    counts = {"actual_native_optimize": 0, "actual_OpenDSS": 0, "actual_FULL_model_build": 0,
              "actual_complete_domain_build": 0, "actual_pricing_optimize": 0, "B3_production_workers_started": 0}
    common = {"evidence_kind": "SOURCE_CODE_AND_LIGHTWEIGHT_FIXTURES", "scientific_certified": False,
              "real_full_model_validation": "NOT_RUN", "production_authorized": False, "counts": counts}
    write(DOCS, "A2_FIXED_MESS_SOURCE_BRIDGE.json", {**common,
        "status": "A2_FIXED_MESS_BINDING_IMPLEMENTED", "bridge": "v42_b3_joint/a_source.py:ASourceBridge",
        "source_stage": "v42_may_build_v6.a_stage", "source_grid": "v42_compact.native.grid(stage=Stage.A2,mess_p=original_injection_P,mess_q=original_injection_Q)",
        "original_MESS_validation": ["v42_native.mess.validate", "v42_bootstrap.attribution.supplemental_physical"],
        "fixed": ["route arcs", "location", "Pch", "Pdis", "Q", "charge_mode", "SOC", "move_energy", "initial/final"],
        "optimized": ["original complete job schedules", "migration", "time shifting", "STAY/migration integer blocks"],
        "P_Q_binding": "Original FULL injection helper values mapped by exact source control_names/site/slot; no manual subtraction or unit/sign conversion",
        "matrix_RHS": "Unchanged original linear grid expressions receive fixed P/Q constants; every free AIDC coefficient and voltage/line/transformer row remains original",
        "complete_domain_reuse": "Only independently rehashed exact same-day Job/Resource/Boundary/complete-domain input files; fresh grid/model/RHS/point/bound/ledger",
        "physical_replay": ["restore_types", "primal_replay", "Physical.verify", "source certify/check/grid_audit"],
        "global_bound": "Original full_pricing rerun using SHA-bound raw master/local primal/dual receipts and read-only RecordedNative; no new optimize during verifier",
        "A1_LB_UB_or_Runtime_reused": False})
    write(DOCS, "M2_FIXED_AIDC_SOURCE_BRIDGE.json", {**common,
        "status": "M2_FIXED_AIDC_BINDING_IMPLEMENTED", "bridge": "v42_b3_joint/m_source.py:MSourceBridge",
        "source_constructor": "v42_may_campaign_native90.m_model.build_case",
        "source_solver": "v42_may_campaign_native90.m_stage.run + original anytime primal/dual hybrid",
        "fixed": ["A2 selected jobs/placement/migration/time", "GPU", "IT/PCC P/Q", "Runtime/CC4", "original A2 model/decision/physical SHA"],
        "optimized": ["arc", "charge_mode", "Pch", "Pdis", "Q", "SOC", "rho_max"],
        "fresh_each_stage": ["FULL CSR/objective/RHS/sense/bounds/types", "Compact", "C3A", "strict point", "exact dual", "Native ledger"],
        "stage_routing_before_construction": True, "B2_FCFS_calls": 0, "Q_only_restriction": False,
        "M1_candidate": "Reconstruct original primary M1 values in NEW A2-bound FULL matrix; original strict integer/physical replay admits or rejects candidate. No M1 certificate/runtime copied",
        "independent_verification": ["verify_case", "verify_transport", "_strict_ub", "check_rational_dual_certificate", "point_vector_sha256"],
        "M1_LB_UB_or_Runtime_reused": False})
    mapping = {"A1": {"source": "V6 complete A-stage", "fixed": "MESS OFF", "optimized": "complete original AIDC domain", "gap": "1/200"},
        "M1": {"source": "native90 FULL/Compact/C3A Hybrid", "fixed": "entire optimized A1", "optimized": "entire original MESS", "gap": "3/100"},
        "A2": {"source": "V6 complete A-stage + original A2 grid", "fixed": "entire optimized M1", "optimized": "complete original AIDC domain", "gap": "1/200"},
        "M2": {"source": "fresh native90 FULL/Compact/C3A Hybrid", "fixed": "entire optimized A2", "optimized": "entire original MESS", "gap": "3/100"}}
    write(DOCS, "B3_ORIGINAL_MODEL_MAPPING.json", {**common, "stages": mapping,
        "objective": "min rho_max", "P2_calls": 0, "Threads": 1,
        "authority": "InjectionAuthority pins coefficient SHAs, phase/PCC/control mapping, kW/kvar units, original signs, validity domain, independent source checker and dynamic transformer rows",
        "original_solver_policy": "Existing V6 A Native policy and native90 M policy reused without changes, including existing V6 May11 PHASE_I/ORIGINAL_P1 precision route; policy.parameters describes default stage contract",
        "source_input_sha_basis": "digest({NATIVE_INPUT.json:raw SHA256,WINDOWS.json:raw SHA256}); bundle JSON must match original NATIVE_INPUT.json at SOURCE admission",
        "physical_domain_sha_basis": "Original v42_a_stage_domain_v2.domain.digest(sorted UID to domain.sha roster) must equal source DATA[7].physical_domain_hash and Authority.physical_domain_sha; each M stage also verifies its fresh route/FULL/Compact/C3A fingerprint",
        "cross_stage_context": "Same input folder, canonical original bundle, grid authority object, producer/source SHA, day and run_id required",
        "IEEE8500_interface": "Inject original coefficient constructor/checker, GridAuthority/voltage/current/transformer builders, validity and ActualBackend. No feeder node/voltage-row counts hardcoded in new bridges. Original experiment remains 12 AIDC/4 MESS/96 slots",
        "original_matrices_or_physical_equations_reimplemented": False})
    write(DOCS, "B3_NATIVE_LEDGER_BRIDGE.json", {**common, "status": "NATIVE_LEDGER_BRIDGE_IMPLEMENTED",
        "source": "v42_may_campaign_native90.budget.DateBudget native_optimize original function body",
        "stage_independent_native_budget_seconds": 5400, "wall_ceiling": None,
        "charged": ["LP", "MILP", "QCP", "local pricing", "failed entered optimize with measured Runtime"],
        "excluded": ["model/input/domain construction", "matrix/equivalence", "independent proof", "physical replay", "Actual", "Fresh AC"],
        "unknown_Runtime": "Original source records unavailable Runtime; stage quarantined with no estimate, reset, native reentry or continuation",
        "restart": "Original source ledger is rehydrated with identity sidecar, cumulative Runtime, all effective TimeLimit rows, inflight and costs; never invokes __init__ on existing ledger",
        "native_backstop": "Scoped source_guard routes original optimize backstop/guard aliases; exact ledgered model/day/Threads/P1 required and all aliases restored on normal/exception exits",
        "cross_stage_ledger_or_cost_transfer": False})
    write(DOCS, "B3_PLANNING_ACTUAL_FRESH_BRIDGE.json", {**common, "status": "ACTUAL_FRESH_AC_BRIDGE_IMPLEMENTED",
        "source": ["v42_native.planning.freeze_day_ahead_plan", "v42_native.actual.run_dday_actual", "native90.operations.freeze_planning/actual_sources/actual/fresh"],
        "final_decisions": "A2 AIDC + M2 MESS; all four source model/result/certificate SHAs independently replayed before freeze and resume",
        "actual_default_semantics": "Original V39E_FROZEN_DA_FIXED_REPLAY source materializer; realized background load/PV checked against same-day original parquet, source fixed AIDC state bound explicitly",
        "unknown_arrivals": "Existing causal policy/interface identity is preserved; no new unknown-job scheduling algorithm or retrospective repair is introduced",
        "repair_P": False, "repair_Q": False, "actual_new_MILP": False,
        "Fresh": "Original source 96-slot OpenDSS path retains NormalAmps/Autonomous RegControl and independently records physical violations; Planning gap PASS does not imply Fresh PASS",
        "resume": "Saved original freeze and Actual physical/result/Fresh identities are rechecked; partial/inflight execution quarantines, no repeated Fresh call",
        "fake_fresh_scientific_promotion": False})
    status = {**readiness(), "base_B3_commit": "1495b54594bd044f2104027564d647a0d0c12d71",
        "reference_source_HEAD": V6_HEAD, "branch": "codex/v42-b3-preparation",
        "PR191": "https://github.com/BeaverVillage/MobileESS/pull/191",
        "B2_PR": "https://github.com/BeaverVillage/MobileESS/pull/192",
        "states": readiness()["implementation_states"] + ["LIGHTWEIGHT_TEST_PASS"],
        "lightweight_tests": light["tests_run"], "schema_packets": 4, "original_tests_preserved": 75,
        "original_source_API_signatures": 39, "new_literal_source_routes": light["new_literal_source_API_routes_checked"],
        "pending_scientific_validation": pending, "counts": counts,
        "campaign_owner": "User-authorized v42 열여섯번째 owns current campaign V7 source/Coordinator version transition; this work never edits active campaign files",
        "latest_commit_location": "Git HEAD of this branch (reports avoid circular self-commit hashing)"}
    write(DOCS, "B3_FINAL_IMPLEMENTATION_STATUS.json", status)
    lower = [p for folder in ROOT.glob("v42_*") if folder.is_dir()
             for p in folder.rglob("*.py") if "__pycache__" not in p.parts]
    lower += [p for p in ROOT.glob("v42_*.py") if p.is_file()]
    tests = list((ROOT / "tests").glob("test_v42_b3_*.py"))
    files = sorted(set(lower + tests))
    write(DOCS, "B3_SOURCE_SHA_MANIFEST.json", {"schema": "B3_SOURCE_COMPLETION_SHA_MANIFEST_V1",
        "reference_source_HEAD": V6_HEAD, "hash_algorithm": "SHA256", "source_manifest": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "source_registry_pin_scope": "Original sources and new source bridges; self report excluded",
        "historical_preparation_SHA_manifest_preserved": True, "scientific_input_data_loaded": False})
    reuse = [
        {"original": "v42_job_capability.validate", "optimized": "V6 ConstructionChecks/routed_validate", "calculation": "Reuse immutable Boundary.require; preserve original other validation/WAN/transfer checks", "stages": ["A1", "A2"], "inapplicable": "M stages have no AIDC Option optimization"},
        {"original": "resources_used + resource_limit", "optimized": "V6 ConstructionChecks GPU prefix", "calculation": "Prefix count immutable GPU violations at original 1e-9 threshold, original WAN/active checks; before/after Resources equality", "stages": ["A1", "A2"], "inapplicable": "MESS SOC/PCS/resources are distinct"},
        {"original": "v42_exact.support.prune R1 set union", "optimized": "V6 interval_projection", "calculation": "Union overlapping intervals per destination; preserve holes/tail/all states", "stages": ["A1", "A2"], "inapplicable": "M route flow graph is distinct"},
        {"original": "repeated checkpoint_records", "optimized": "V6 checkpoint_memo", "calculation": "Scoped immutable source checkpoint reuse; original state and complete candidate roster", "stages": ["A1", "A2"], "inapplicable": "M source constructor has no same A checkpoint operation"},
        {"original": "duplicate A model/equivalence builds", "optimized": "V6 inherited exact construction + B3 one independent source replay", "calculation": "Use original source objects and avoid redundant execute-side typed model/physical replay; independent acceptance always reruns", "stages": ["A1", "A2"], "inapplicable": "Fixed M1 P/Q prohibits A1 FULL/grid/RHS reuse in A2"},
        {"original": "same-day input/domain generation", "optimized": "V6 input_cache/physical cache B3 source admission", "calculation": "Rehash original files and exact Job/Resource/Boundary semantics plus full domain hash; new model/bounds/ledger every stage", "stages": ["A1", "A2"], "inapplicable": "Different day/producer/boundary/resource; M full matrices cannot transfer between fixed A inputs"}]
    for row in reuse:
        row.update(equivalence="V6 B1 evidence is reference only; B3 complete equivalence NOT_RUN",
                   CPU_memory_runtime="Repeated construction work removed; B3 measured full performance/RSS NOT_RUN")
    write(BUILD_DOCS, "B1_V6_REUSE_AUDIT.json", {**common, "reference_HEAD": V6_HEAD, "improvements": reuse,
        "reference_evidence_read": ["original docs/v42_may_build_v6_20261009/README.md", "V6 exact source/dependency SHA comparison"],
        "B1_performance_automatically_transferred_to_B2_B3": False})
    mess = {**common, "source_build": "Original FULL→Compact→C3A, original strict transport replay each fresh case",
        "first_build_improvement": "Per-build exact float.hex cos/sin memo inside original pcs_rows identical code object; original expressions/FACES/source math retained, function restored finally",
        "fixture_math_counts": {"cos_requests": 96, "cos_source_evaluations": 17, "sin_requests": 48, "sin_source_evaluations": 16},
        "fixture_coefficient_hex_equal": True, "route_cache": "Private immutable source RouteArc/Battery inputs, verified SHA; source mappings detached each hit",
        "route_cache_first_build_speedup_claim": False,
        "matrix_assembly_or_sparse_changes": "No additional sparse optimization applied without a demonstrated duplicate computation/equivalence proof",
        "fresh_model_and_proofs_each_fixed_input": True, "global_mutable_cache": False,
        "measured_real_speedup_ratio": None, "real_comparison": "NOT_RUN"}
    write(BUILD_DOCS, "B2_MESS_BUILD_OPTIMIZATION.json", {**mess, "branch": "codex/v42-b2-build-optimization",
        "PR": "https://github.com/BeaverVillage/MobileESS/pull/192", "lightweight_tests": 17,
        "current_campaign_integration": "User-authorized campaign-owner chat implements V7 official version transition; no forced live-worker hot-swap"})
    write(BUILD_DOCS, "B3_A1_A2_BUILD_OPTIMIZATION.json", {**common, "improvements": reuse,
        "source": "Exact V6 namespace from reference HEAD with unchanged lower source dependencies",
        "A2_new_fixed_PQ_grid_and_RHS": True, "source_globals_restored_on_exception": True,
        "real_baseline_optimized_equivalence_and_performance": "NOT_RUN"})
    write(BUILD_DOCS, "B3_M1_M2_BUILD_OPTIMIZATION.json", {**mess, "stages": ["M1", "M2"],
        "fixed_inputs": {"M1": "optimized A1", "M2": "optimized A2"},
        "shared_LB_UB_or_Runtime": False, "B2_FCFS_calls": 0})
    write(BUILD_DOCS, "B2_B3_MODEL_EQUIVALENCE.json", {**common, "small_fixture_status": "PASS",
        "fixture_scope": ["Original PCS identical bytecode and exact coefficient hex", "B2 source AST unchanged after removing profile scopes/loader routing",
            "Tiny baseline/optimized FULL/Compact/C3A fixture arrays/types/RHS", "Exact affine fixed P/Q substitution preserves free terms", "source signatures/handoff/ledger/proof/SHA isolation"],
        "complete_domain_candidate_CSR_objective_RHS_sense_bounds_types_grid_SOC_PCS_traffic_global_proofs": pending})
    write(BUILD_DOCS, "B2_B3_BUILD_RUNTIME_COMPARISON.json", {**common,
        "phase_instrumentation": ["original input preparation", "physical domain/route", "graph", "FULL", "Compact/C3A", "equivalence", "total preparation"],
        "comparison_contract": "Same scope SHA and phase coverage; fixture ratios labelled fixture; real ratios require measured comparable source construction",
        "B1_May23_reference_is_B2_B3_benchmark": False, "B2_B3_actual_equal_scope_measurements": "NOT_RUN",
        "actual_speedup_ratio": None, "actual_peak_RSS": None,
        "memo_count_savings_is_wall_time_speedup": False})
    write(BUILD_DOCS, "B2_B3_RESOURCE_ISOLATION.json", {**common, "B2_worker_count_preserved": 3,
        "B2_cache_owner": "Explicit worker-owned VersionedB2BuildPort or fresh local port per entry call, no global port cache",
        "B3_cache_owner": "Coordinator bridge instance keyed by run/day/stage/fixed input/output identity",
        "models_matrices_native_ledgers_bounds_temp_cross_worker_shared": False,
        "native_ledger_stage_output_namespace": "B3 run/day/stage; original campaign output forbidden",
        "active_preservation_evidence": "../v42_b3_implementation_completion_20261009/B3_RESOURCE_ISOLATION_AUDIT.json",
        "active_source_version_application_owner": "v42 열여섯번째; user explicitly requested current-campaign B2 integration"})
    (DOCS / "B3_REAL_MODEL_PENDING_VALIDATION.md").write_text("# 실제 원본 모델 검증 대기\n\n실제 May01/May23 FULL 모델 비교, 원본 complete domain/pricing, 정수·물리 replay, 독립 exact Global LB/UB, 실제 Native Runtime/RSS, Actual/Fresh OpenDSS 검증은 모두 **NOT_RUN**입니다.\n\n네 단계의 고정 입력마다 원본 CSR·목적함수·RHS/Sense·Bounds/Types·PCC/위상·Grid 전압/선로/변압기·SOC/PCS/교통 제약과 FULL→Compact→C3A exact transport를 비교해야 합니다. 이후 별도 승인된 실행에서 A≤0.5%, M≤3%, 단계별 Native 5400초·Threads=1·P2=0을 검증해야 합니다.\n\nIEEE8500의 2025-05-01 B0/B1/B2/B3는 시작하지 않았습니다. 새 feeder의 source hook/validity/계수·phase mapping/NormalAmps/RegControl과 별도 전체 성능 검증이 필요합니다.\n", encoding="utf-8")
    (DOCS / "B3_IMPLEMENTATION_COMPLETION_KO.md").write_text(f"""# B3 실제 원본 연결 구현 결과

PR191의 기존 계약 위에 A1→M1→A2→M2, 원본 Native ledger, Planning→Actual→Fresh→Validation 및 재시작 Coordinator를 구현했습니다. 원본 알고리즘과 물리 수식을 호출하는 경로가 코드에 연결되었습니다. 현재 Production Guard는 닫혀 있습니다.

| 단계 | 실제 소스 연결 | 고정/최적화 |
|---|---|---|
| A1 | 원본 V6 A-stage complete domain/Phase I/pricing/integer recovery | MESS OFF, 전체 AIDC 최적화 |
| M1 | 원본 native90 FULL/Compact/C3A Hybrid | A1 전체 결정 고정, 전체 MESS 최적화 |
| A2 | V6 A-stage와 원본 compact.native.grid Stage.A2 | M1 전체 MESS 고정, P/Q 원본 helper 주입, 전체 AIDC 재최적화 |
| M2 | A2 입력으로 새 원본 FULL/Compact/C3A Hybrid | A2 전체 결정 고정, 전체 MESS 재최적화 |

A2는 원본 control_names/단위/sign/phase/계수 SHA를 검증하여 MESS P와 Q를 상수로 주입합니다. M2는 FCFS 또는 Q-only 경로를 사용하지 않습니다. M1 후보는 새 A2 FULL 모델에서 원본 strict verifier를 통과한 경우만 시작 후보로 사용합니다. 이전 LB/UB/Runtime은 이전하지 않습니다.

DateBudget 원본 함수 본문을 연결했으며 각 단계의 5400초는 실제 optimize Runtime 누적입니다. 실패 호출도 계상하고 unknown/inflight는 격리합니다. 원본 backstop도 정확한 B3 ledger 모델 scope를 확인하며 임시 guard/global/PCS 함수 교체는 예외 시에도 복원합니다. V6 기존 May11 정밀도 정책을 포함한 원본 날짜별 Solver 설정을 재사용합니다.

Planning은 A2 AIDC와 M2 MESS 및 네 단계 증명 SHA를 결합합니다. 원본 Actual fixed replay와 Fresh OpenDSS 경로, NormalAmps/RegControl을 연결하고 repair/MILP 재최적화를 차단했습니다. 실제 Fresh 결과는 Planning Gap과 독립입니다. 기본 Actual의 AIDC 상태는 원본 고정 replay 의미에 결속하며 새 unknown-job 알고리즘을 만들지 않았습니다.

경량 테스트 **{light['tests_run']}개 PASS**, 기존 75개 포함, Schema 4개 PASS, 기존 원본 API 39개 및 신규 literal source route {light['new_literal_source_API_routes_checked']}개를 확인했습니다. 기존 Preparation 보고서 13개와 SHA 목록을 보존했습니다. Fake source/solver는 소프트웨어 연결 검증이며 과학적 인증으로 승격하지 않습니다.

실제 Native optimize=0, OpenDSS=0, FULL 모델 생성=0, 실제 대규모 domain/pricing=0입니다. 기존 캠페인의 보호 결과는 B3_RESOURCE_ISOLATION_AUDIT.json에 있으며, 이 작업의 활성 소스·Worker·Scheduler·ledger 변경은 0회입니다. 사용자 후속 지시로 B2 현재 캠페인 반영은 별도 담당 대화에 확정 코드/PR192/SHA를 전달했습니다.

원본 전체 모델/정수·물리/독립 Global Gap/Native·RSS/Actual·Fresh와 실제 고속화율은 NOT_RUN입니다. **REAL_FULL_MODEL_VALIDATION_PENDING / PRODUCTION_NOT_AUTHORIZED**입니다. InjectionAuthority와 ActualBackend를 다른 feeder로 주입할 수 있으며 새로운 코드에는 IEEE123 노드/전압 행 수를 고정하지 않았습니다. 기존 실험의 12 AIDC·4 MESS·96-slot 인터페이스는 보존합니다.

정확한 상태·mapping·검증 경로·source SHA는 이 폴더의 JSON 보고서에, V6 적용성·B2/MESS 개선·측정 범위는 ../v42_b2_b3_build_optimization_20261009/에 기록했습니다. 최신 Commit SHA는 해당 브랜치 Git HEAD로 확인합니다.
""", encoding="utf-8")
    (BUILD_DOCS / "B2_B3_IMPLEMENTATION_STATUS_KO.md").write_text("# B2/B3 모델 생성 개선\n\nV6 효율적 Option/Resource/GPU interval/R1 projection/checkpoint 및 검증된 동일 날짜 input/domain cache를 B3 A1/A2에 연결했습니다. A2의 새 MESS P/Q Grid/FULL/RHS는 다시 생성하며 원본 source globals를 복원합니다.\n\nB2와 B3 M 단계는 원본 PCS 함수의 동일 bytecode/식과 exact float.hex 계수를 유지하면서 빌드 안의 반복 cos/sin 평가를 줄입니다. 원본 FULL/Compact/C3A는 매번 생성합니다. Route input cache는 반복 동일 입력에만 이득이 있으며 첫 build 속도 개선의 근거로 사용하지 않습니다. 추가 sparse assembly 변경은 중복·동치성이 확인되기 전 적용하지 않았습니다.\n\nB2 PR192의 별도 개발 코드와 테스트17개 PASS를 담당 캠페인 대화에 전달했습니다. 최신 사용자 지시대로 해당 대화가 현재 소스와 V7 정식 전환을 담당하며 실행 중 V6 Worker를 교체하지 않습니다. 별도 branch만 남기는 것을 캠페인 반영 완료로 주장하지 않습니다.\n\n단계별 일곱 구성 phase와 scope SHA의 비교 인터페이스를 구현했습니다. 실제 May01/May23 전체 모델 동치성·비교 성능·RSS는 NOT_RUN이고, B1 성능 수치를 B2/B3로 자동 이전하지 않습니다. 실제 Native/FULL/OpenDSS는 0회이며 B3 Production은 미승인입니다.\n", encoding="utf-8")
    print(json.dumps({"completion_docs": str(DOCS), "build_docs": str(BUILD_DOCS), "lightweight_tests": light["tests_run"]}))


if __name__ == "__main__":
    reports()
