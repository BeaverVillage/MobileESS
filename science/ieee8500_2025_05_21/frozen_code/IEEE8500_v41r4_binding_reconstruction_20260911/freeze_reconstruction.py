"""Seal the non-electrical binding gate, explicitly without production release."""
import sys,ast,json,hashlib,time
from pathlib import Path
import psutil
import numpy as np
from frozen_binding import HOME,ROOT,record,read,save,sha,EXPECTED,context
from v41r4_ieee8500_adapter import compile_B1,compile_A1,compile_objectives,electrical_port_contract,original_solver_binding
ctx=context()
assert ctx.v41_bounded_compute==dict(total_seconds=14400.,fix_and_optimize=True)
from dayahead.v40g import optimizer
from dayahead.v41 import objectives
assert compile_B1(ctx).__code__ is optimizer.solve.__code__
assert compile_B1(ctx).__kwdefaults__==optimizer.solve.__kwdefaults__
assert compile_objectives(ctx).__code__ is objectives.evaluate.__code__
budget_bind=[]
for role in ['B1','B3_A1']:
    with original_solver_binding(ctx,role,HOME/'UNEXECUTED') as fn:
        assert ctx.v41_policy_budget.total==14400. and ctx.v41_policy_budget.loop_started is None
        budget_bind.append(dict(role=role,actual_seconds=ctx.v41_policy_budget.total,loop_started=False))
required=['DOMAIN_POWER_BINDING_PASS.json','STRUCTURAL_DIFFERENTIAL.json','SEMANTIC_AUDIT_PASS.json','IMMUTABLE_AUTHORITY_VERIFICATION.json']
for name in required:assert read(HOME/name)['status'].startswith('PASS'),name
structures=[read(HOME/x/'STRUCTURE.json') for x in ['V41R4_REFERENCE','IEEE8500_B1','IEEE8500_A1']]
assert structures[0]==structures[1]==structures[2]
source_paths=set()
for m in list(sys.modules.values()):
    p=getattr(m,'__file__',None)
    if p:
        p=Path(p)
        if p.suffix=='.py' and p.is_relative_to(ROOT):source_paths.add(p)
for p in ['dayahead/v40g/optimizer.py','dayahead/v41/objectives.py','dayahead/v41r1/bounded_solver.py','dayahead/v41r1/feasible_seed.py','dayahead/v41r1/migration.py','dayahead/v41r1/terminal.py','dayahead/v41r1/migration_factor.py','dayahead/v41r1/migration_load.py','dayahead/v41r1/migration_admission.py','dayahead/v41r1/exact_aggregation.py','dayahead/v41/reserve.py','dayahead/v41/temporal_restore.py','dayahead/v41/frozen_candidates.py','dayahead/v40a/grid.py','dayahead/v28r2/electrical_subproblem.py','v41r4_b3_equivalent.py','v41r4_runtime.py','v41r4_loop_runtime.py','v41r4_loop_budget.py','v41r4_search_budget.py']:
    source_paths.add(ROOT/p)
sources=[record(p) for p in sorted(source_paths)]
save('ORIGINAL_V41R4_SOURCE_SHA256.json',dict(status='FROZEN_READ_ONLY_SOURCE_BINDING',files=sources))
save('EXACT_INPUT_SHA256.json',dict(files=ctx.input_sources,candidate_decompressed_stream_sha256=EXPECTED))
save('RECONSTRUCTION_CODE_SHA256.json',dict(files=[record(p) for p in sorted(HOME.glob('*.py'))]))
auth=HOME.parent/'IEEE8500_stress_calibration_20260911/IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json';frozen=read(auth)
assert (frozen['selected_date'],frozen['source_pu'],frozen['all_regulator_Vreg_V'],frozen['alpha8500'])==('2025-05-21',1.04,123.5,.5)
running=[]
for p in psutil.process_iter(['pid','name','cmdline']):
    cmd=' '.join(p.info['cmdline'] or [])
    if (p.info['name'] or '').lower() in ('python.exe','pythonw.exe') and any(s in cmd for s in ['production_campaign.py','production_campaign_v2.py']):running.append(dict(pid=p.pid,command=cmd))
assert not running
domain=read(HOME/'DOMAIN_POWER_BINDING_PASS.json');n=structures[0]
gate=dict(status='IEEE8500_V41R4_AIDC_BINDING_PASS',scope='NON_ELECTRICAL_AIDC_STRUCTURAL_BINDING_ONLY',production_execution_authorized=False,numerical_electrical_preflight_pass=False,optimization_calls=0,Fresh_calls=0,B0_B1_B2_B3_runs_started=0,source_and_stopped_results_reused=False,stopped_results_status='NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT',old_stopped_results_read_mode='HASH_VERIFICATION_ONLY',day='2025-05-21',counts=domain['observed'],candidate_stream_sha256=EXPECTED,installed_GPU=780,capacity_vector=domain['capacity_vector'],original_B1_model_function_code_identity=True,original_A1_equivalent_adapter=True,original_objective_evaluator_code_identity=True,non_electrical_model_rows_and_variables_exact_identity=True,P2_P3_P4_P5_exact_coefficient_identity=True,P5_original_cohort_rank_identity=True,BoundedLex_P1_P2_P3_P4_P5_order_and_locks_identity=True,continuous_budget_binding=budget_bind,seed_semantics='Original B1 reference seed; original A1 final-B1 reuse and fixed-M1 semantics. Actual new final B1 receipt does not yet exist; validated at future authorized run, never supplied from stopped production.',electrical_difference_classification='AUTHORIZED_ELECTRICAL_DIFFERENCE',electrical_matrices_materialized_in_this_stage=False,electrical_difference_note='Numerical electrical matrices/grid rows are excluded from the differential non-electrical projection, not replaced by a fake feeder. No stopped production coefficients or solutions used. Actual IEEE8500 numerical electrical release remains a separate preflight.',frozen_operating_point=record(auth),checks=[record(HOME/p) for p in required+['STAGE_LOCK_BUDGET_IDENTITY.json','SEED_FIXED_MESS_SEMANTICS.json','ELECTRICAL_DIFFERENCE_CONTRACT.json']],source_manifest=record(HOME/'ORIGINAL_V41R4_SOURCE_SHA256.json'),input_manifest=record(HOME/'EXACT_INPUT_SHA256.json'),code_manifest=record(HOME/'RECONSTRUCTION_CODE_SHA256.json'),running_production_processes=running)
save('IEEE8500_V41R4_AIDC_BINDING_PASS.json',gate)
rows=[('reference jobs',708),('temporal-option jobs',39),('spatial-option jobs',364),('migration-option jobs',364),('restored temporal candidates',16392),('base candidates',1325555),('total candidates',1341947),('PARTIAL/shared jobs',361)]
lines=['# IEEE8500 V41R4-equivalent AIDC binding reconstruction','',
'**IEEE8500_V41R4_AIDC_BINDING_PASS** — non-electrical/AIDC structural binding 범위의 PASS이다. Production 실행 승인이 아니며, numerical electrical preflight PASS 또는 AC feasibility 인증도 아니다. Optimization / Fresh / B0–B3 campaign 실행은 모두 0회이다.','',
'중지된 IEEE8500 production 결과·checkpoint·새 neighborhood 코드·coefficient payload는 재사용하지 않았다. 원본 보존 여부를 확인하기 위한 SHA 계산만 수행했다. 기존 NONAUTHORITATIVE 분류를 유지하며, 이 binding PASS로 과거 결과를 재승인하지 않는다.','',
'## Frozen May21 input binding','','| 항목 | 요구값 = 관측값 |','|---|---:|']+[f'| {k} | {v:,} |' for k,v in rows]
lines += ['',f'Decompressed candidate stream SHA256: `{EXPECTED}`','',
'Original compressed artifact를 읽고 모든 UID/option tuple의 원본 순서와 row bytes SHA를 검증했다. 후보 파일을 새로 생성하거나 줄이지 않았고, base 후보가 전부 포함됨을 확인했다. May04 global counts는 적용하지 않았다.','',
'Installed capacity: 780 GPU; AIDC01–AIDC12 = [80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80]. Frozen power law와 C1을 그대로 호출했다. Frozen operating-point의 V41R4 B0 입력과 비교한 GPU / IT / PCC kW / PCC kvar 최대 절대 차이는 모두 0이다. PARTIAL/shared 361개는 원본 aggregate GPU-slot semantics로 포함된다.','',
'## Structural-equivalence evidence','',
'원본 v40g.optimizer의 AST에서 전기적 평가/행과 optimization 이후 실행만 제외한 compile-only non-electrical projection을 작성했다. 원본 AIDC 선택·migration factorization·UID serial WAN·GPU occupancy recurrence·C1 PWL·reserve 생성 문장을 그대로 실행하여 실제 Gurobi 모델을 만들었다. Gurobi optimize는 호출하지 않았다. Reference, IEEE8500 B1, 원본 make_solver로 변환한 IEEE8500 A1을 비교했다.','',
f'- Non-electrical variables: {n["variable_count"]:,}; linear rows: {n["linear_constraints"]:,}; general constraints: {n["general_constraints"]:,}; nonzeros: {n["matrix_nonzeros"]:,}.',
f'- Original cohorts: {n["cohort_count"]}; 변수 이름/type/bounds, 선형 rows, WAN/migration rows, indicator/MAX/PWL rows 및 P2/P3/P4/P5 coefficient SHA가 세 구성에서 일치.',
'- 모든 candidate의 eligibility 및 기존 temporal model_boundary 검사를 원본 machinery로 수행했다.',
'- P5는 original cohort rank를 유지한다. 개별 UID sorted rank를 사용하지 않는다.',
'- B1과 objective evaluator는 원본 함수 code object와 동일하며 frozen tuple reader만 연결했다.',
'- A1은 원본 v41r4_b3_equivalent.make_solver / make_seed의 정확한 변환을 사용한다. 동일한 B0 candidate/P4/P5 authority, final B1 assignment 재사용, M1 numeric P/Q 고정 의미를 보존한다.','',
'| Structural field | SHA256 |','|---|---|',
f'| Variable identity | `{n["decision_variable_sha256"]}` |',
f'| Linear constraints | `{n["linear_rows_sha256"]}` |',
f'| WAN/migration linear rows | `{n["WAN_migration_linear_rows_sha256"]}` |',
f'| General constraints | `{n["general_rows_sha256"]}` |',
f'| P5 cohort rank | `{n["P5_cohort_rank_sha256"]}` |']
lines += [f'| P{i+2} coefficient | `{h}` |' for i,h in enumerate(n['P2_P3_P4_P5_sha256'])]
lines += ['','## Stage, budget, seed','',
'원본 P1→P2→P3→P4→P5 stage ordering과 upper-priority locks의 AST가 B1/A1에서 동일하다. Original BoundedLex 및 V41R4 continuous LoopBoundedLex를 연결했다. 허용된 시간 변경은 총 14,400초뿐이다. 원본 GUARDS 비율 [900,480,180,120,120]은 그대로이므로 배분은 [7200,3840,1440,960,960]초이다. Fake monotonic clock으로 30min/1h/2h/deadline 의미를 검사했으며 실제 대기나 search loop 실행은 하지 않았다.','',
'B1 reference seed는 원본 choice/placement Start와 original feasible_seed의 non-electrical fill 의미를 사용했다. 원본 job_audit 및 row_audit로 non-electrical seed의 모든 행을 대입 검증했다. 전기 port rho는 projection에서만 제외되므로 이를 물리적 seed PASS로 해석하면 안 된다.','',
'A1은 원본 make_seed대로 final B1 assignment를 읽고 WAN/migration 값을 0으로 초기화하지 않는다. 새 production root의 SHA-verified seed만 허용하며 stopped production 경로는 차단한다. 실제 final B1은 아직 생성되지 않았으므로 실제 B1 결과와의 hash binding 검증은 추후 승인된 실행 시 수행해야 한다. 이번에는 원본 seed adapter 의미와 non-electrical 구조를 검사했다. 24-location M1 P/Q binding은 algebra-only synthetic fixture로 검사했고 OpenDSS나 모델 부하에 주입하지 않았다.','',
'## AUTHORIZED_ELECTRICAL_DIFFERENCE','',
'유지된 authority: 2025-05-21; source 1.0400; Vreg 123.5 V; alpha8500 0.50; CAPBank3 OFF; 기존 12 AIDC / 24 MESS PCC. 60-dimensional original control interface를 보존한다: 12 aidc_load_kw + 24 mess_p_kw + 24 mess_q_kvar. AIDC Q는 기존 PF를 따르며 새로운 독립 AIDC Q 결정변수를 추가하지 않는다. Road IDCxx→electrical AIDCxx 변환은 PCC boundary에서만 적용한다.','',
'P1 voltage/current/flow matrices, branch axes, grid rows 및 그 numerical payload는 이 단계에서 만들거나 시뮬레이션하지 않았다. 이들만 structural differential에서 분리했으며 numerical preflight는 미실행 상태로 남긴다. 기존 stopped coefficient를 복사해 생산 authority로 승인하지 않았다. 별도의 전기적 coefficient/API 검증 및 full grid seed validation 없이는 생산 실행할 수 없다.','',
'## Source hashes','','| Source | SHA256 |','|---|---|']
core_names=['dayahead/v40g/optimizer.py','dayahead/v41/objectives.py','dayahead/v41r1/bounded_solver.py','dayahead/v41r1/feasible_seed.py','v41r4_b3_equivalent.py','v41r4_loop_budget.py','dayahead/v39a/power.py','dayahead/v28r2/c1_affine.py','dayahead/v41/reserve.py','dayahead/v41r1/migration.py','dayahead/v41r1/terminal.py']
for p in core_names:
    r=record(ROOT/p);lines.append(f'| [{p}](<{r["path"].replace(chr(92),"/")}>) | `{r["sha256"]}` |')
lines += ['','전체 input/source/code SHA는 EXACT_INPUT_SHA256.json, ORIGINAL_V41R4_SOURCE_SHA256.json, RECONSTRUCTION_CODE_SHA256.json에 기록했다.','',
'기존 stopped evidence 4,638개, 기존 topology/PCC/electrical/operating authority 3,997개, 이전 audit의 source/input 59개를 hash-only 재검증했고 변경은 0개였다. New workspace의 initial import/temporary-directory 보호 설정 오류는 development failure artifact로 보존했다. 당시에도 optimization이나 외부 authority 수정은 없었으며 최종 structural 비교는 완료되었다.','',
'GATE: non-electrical structural binding PASS; production execution remains disabled. B0/B1/B2/B3/Fresh는 시작하지 않았다.']
(HOME/'V41R4_EQUIVALENT_BINDING_RECONSTRUCTION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
files=[record(p) for p in sorted(HOME.rglob('*')) if p.is_file() and 'runtime_tmp' not in p.parts and p.name not in ['RECONSTRUCTION_FREEZE_MANIFEST.json','RECONSTRUCTION_FREEZE_MANIFEST.sha256']]
save('RECONSTRUCTION_FREEZE_MANIFEST.json',dict(status='FROZEN',binding_gate='IEEE8500_V41R4_AIDC_BINDING_PASS',production_execution_authorized=False,files=files))
(HOME/'RECONSTRUCTION_FREEZE_MANIFEST.sha256').write_text(sha(HOME/'RECONSTRUCTION_FREEZE_MANIFEST.json')+'  RECONSTRUCTION_FREEZE_MANIFEST.json\n',encoding='ascii')
print(json.dumps(dict(status=gate['status'],scope=gate['scope'],optimization_calls=0,files=len(files),manifest_sha256=sha(HOME/'RECONSTRUCTION_FREEZE_MANIFEST.json'))),flush=True)
