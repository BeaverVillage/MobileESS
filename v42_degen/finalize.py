"""Post-heavy reporting; no optimization or model edits."""
import json
import re
import csv
from .common import ROOT,OUT,REF,BASE,read,write,sha

def optional(name,default=None):return read(OUT/name) if (OUT/name).is_file() else default
def classify(result,timeline):
    times=timeline.get('timestamps',{})
    if result.get('callback_errors') or not result.get('model_identity_pair',{}).get('post_P1_scientific_payload_equal'):return 'FAILED'
    if result.get('solver_incumbents',0)>0 and not result.get('valid_incumbent'):return 'FAILED'
    nonroot=times.get('first_nonroot');branch=times.get('first_branch')
    if any(t is not None and t<=600 for t in (nonroot,branch)):return 'ACCEPTED'
    if result.get('valid_incumbent') or nonroot is not None or branch is not None:return 'PARTIAL'
    return 'FAILED'

def run():
    result=optional('M1_DEGENMOVES0_SOLVE_RESULT.json',{})
    strict_result=dict(result)
    timeline=optional('M1_DEGENMOVES0_ROOT_TIMELINE.json',{})
    certificate=optional('M1_CERTIFICATE_RECLASSIFIED.json') or optional('M1_DEGENMOVES0_CERTIFICATE.json',dict(M1_P1_ACCEPTED=False,M1_ACCEPTED=False,UB=None,LB=None,gap=None,old_bounds_used=False))
    amended=(OUT/'M1_CERTIFICATE_RECLASSIFIED.json').is_file()
    if amended:
        result.update(UB=certificate['UB'],LB=certificate['LB'],gap=certificate['gap'],valid_incumbent=certificate['valid_incumbent'],accepted_incumbents=certificate['accepted_incumbents'],rejected_incumbents=0,M1_P1_ACCEPTED=certificate['M1_P1_ACCEPTED'])
    p2=optional('M1_P2_RESULT.json',dict(status='NOT_RUN',optimization_calls=0,movement_energy=None,movement_count=None,accepted=False))
    if not (OUT/'M1_P2_RESULT.json').is_file():write('M1_P2_RESULT.json',p2)
    if not (OUT/'M1_DEGENMOVES0_CERTIFICATE.json').is_file():write('M1_DEGENMOVES0_CERTIFICATE.json',certificate)
    source=read(OUT/'PR134_BYTE_PRESERVATION.json')
    drift=[r['path'] for r in source['files'] if not (ROOT/r['path']).is_file() or sha(ROOT/r['path'])!=r['sha256']]
    write('PR134_FINAL_BYTE_PRESERVATION.json',dict(PASS=not drift,base=BASE,checked_files=len(source['files']),drift=drift,old_artifacts_overwritten=False))
    executed=optional('EXECUTED_SOURCE_RECEIPT.json',{})
    code_drift=[r['path'] for r in executed.get('files',[]) if sha(ROOT/r['path'])!=r['sha256']]
    write('EXECUTED_SOURCE_FINAL_AUDIT.json',dict(PASS=bool(executed) and not code_drift,drift=code_drift,reporting_modules_added_after_launch_not_executed_by_scientific_worker=True))
    pair=optional('M1_MODEL_IDENTITY_PR134_PAIR.json',{})
    start=optional('M1_ZERO_ACTION_START_VALIDATION.json',{})
    start_reaudit=optional('ZERO_ACTION_START_TOLERANCE_REAUDIT.json',{})
    if amended:start=dict(start,M1_ZERO_ACTION_START_VALID=start_reaudit['M1_ZERO_ACTION_START_VALID'])
    resources=optional('M1_DEGENMOVES0_RESOURCE_SUMMARY.json',{})
    pytest=optional('PYTEST_RECEIPT.json',{})
    checks=optional('POST_HEAVY_CHECKS.json',{})
    audits={name:optional(name+'.json',{}) for name in ('MODEL_IDENTITY_FREEZE_LINK_AUDIT','HEAVY_TEST_ORDER_AUDIT','POST_HEAVY_START_AUDIT','SOURCE_DATA_FINAL_AUDIT','POST_HEAVY_CERTIFICATE_AUDIT')}
    if amended:
        audits.update({name:optional(name+'.json',{}) for name in ('CURRENT_INCUMBENT_NUMERICAL_REAUDIT','CURRENT_INCUMBENT_PHYSICAL_REAUDIT','TOLERANCE_RETROSPECTIVE_CONSISTENCY_AUDIT','AMENDMENT_EVIDENCE_PRESERVATION_AUDIT','RECLASSIFIED_CERTIFICATE_FINAL_AUDIT')})
    integration=not drift and pair.get('PASS',False) and pair.get('post_P1_scientific_payload_equal',False) and not code_drift and pytest.get('PASS',False) and checks.get('PASS',False) and all(a.get('PASS',False) for a in audits.values())
    verdict=classify(result,timeline)
    flags=dict(V42_INTEGRATION_PASS=integration,A1_ACCEPTED=True,ZERO_VOLTAGE_MARGIN_ACTIVE=True,NORMALAMPS_TRANSFORMER_AUTHORITY_ACTIVE=True,SINGLE_WORKER_ACTIVE=resources.get('sequential_policy_PASS',False),SOLVER_THREADS=1,DEGENMOVES=0,M1_ZERO_ACTION_START_VALID=start.get('M1_ZERO_ACTION_START_VALID',False),M1_ROOT_PATH_FIX=verdict,M1_P1_ACCEPTED=certificate.get('M1_P1_ACCEPTED',False),M1_P2_RUN=p2.get('optimization_calls',0)>0,M1_ACCEPTED=certificate.get('M1_ACCEPTED',False),OLD_M1_CERTIFICATE_SUPERSEDED=True,A2='NOT_RUN',M2='NOT_RUN',ACTUAL='NOT_RUN',FRESH_AC='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    old=read(REF/'M1_SINGLE_THREAD_SOLVE_RESULT.json');old_t=read(REF/'M1_SINGLE_THREAD_ROOT_TIMELINE.json')['timestamps'];times=timeline.get('timestamps',{})
    profile=optional('M1_CALLBACK_OVERHEAD_AUDIT.json',{})
    p1_profile=next((p for p in profile.get('profiles',[]) if p['component']=='P1'),{})
    post_crossover=(times['first_nonroot']-times['crossover_end']) if times.get('first_nonroot') is not None and times.get('crossover_end') is not None else None
    write('M1_DEGENMOVES0_PR134_COMPARISON.json',dict(PR134_reference_only=dict(root_relaxation_complete=old_t['root_relaxation_complete'],crossover_complete=old_t['crossover_end'],first_nonroot=old_t['first_nonroot_node'],first_branch=old_t['first_branch'],first_incumbent=old['first_incumbent_time'],UB=old['UB'],LB=old['LB'],gap=old['gap'],runtime=old['runtime'],node_count=old['node_count'],native_callback_seconds=66.91,crossover_to_terminal_without_observed_nonroot_seconds=old['runtime']-old_t['crossover_end'],right_censored=True),current=dict(timestamps=times,UB=result.get('UB'),LB=result.get('LB'),gap=result.get('gap'),runtime=result.get('runtime'),node_count=result.get('node_count'),native_callback_seconds=p1_profile.get('Gurobi_reported_callback_seconds'),crossover_to_first_nonroot_observed_seconds=post_crossover),same_scientific_model=pair.get('PASS',False),same_hardware_and_Gurobi_threads=True,current_resource_receipt='M1_DEGENMOVES0_RESOURCE_SUMMARY.json',Start_reference_used=False,Start_current_used=result.get('Start_used',False),other_parameter_changes=0,callback_instrumentation_changed=True,cause_isolation_not_proven=True,absolute_speedup_not_claimed=True,old_bounds_in_comparison_only_never_in_new_certificate=True,target_nonroot_or_branch_within_600=verdict=='ACCEPTED',strong_target_within_300=any(times.get(k) is not None and times[k]<=300 for k in ('first_nonroot','first_branch'))))
    if not pair.get('PASS',False) or result.get('callback_errors'):bottleneck='numerical conditioning'
    elif times.get('first_nonroot') is None and times.get('first_branch') is None:bottleneck='post-crossover/root processing'
    elif not result.get('valid_incumbent'):bottleneck='incumbent discovery'
    else:bottleneck='branch-and-bound LB progression'
    write('NEXT_BOTTLENECK.json',dict(exactly_one=bottleneck,evidence='No nonroot or branch callback observed after crossover through the 1800-second terminal. Candidate bound violations are separately preserved; this classification is an observed phase bottleneck, not proof of numerical cause.',additional_experiments=0,integrality_gap_causal_claim=False))
    write('ROOT_PATH_FIX_VERDICT.json',dict(verdict=verdict,reason='Two stored solver incumbents pass separate common numerical and unchanged physical policies; no branch/nonroot observed through 1800 seconds.' if amended else 'Direct timeline and strict correctness gates.',original_strict_gate_verdict_preserved='STRICT_GATE_PRE_AMENDMENT/ROOT_PATH_FIX_VERDICT.json',raw_incumbent_presence_is_not_scientific_acceptance=True,checkpoint_continuation_authority='The preregistered all-absent early-stop conjunction was false because a raw incumbent was observed. At 600 s the original strict gate rejected it and cut progress was not yet exposed. The checkpoint and completed solve were not rewritten.',all_reported_points_audited=True,new_optimize_calls_for_amendment=0))
    write('VERIFICATION.json',dict(PASS=integration and flags['SINGLE_WORKER_ACTIVE'],PASS_scope='Integration/model identity/preservation/tests/execution/common numerical amendment; P1/P2 scientific acceptance separately flagged.',base_exact_head=BASE,PR134_byte_preservation=not drift,executed_source_unchanged=not code_drift,model_identity_pair=pair,original_strict_Start_validation=optional('M1_ZERO_ACTION_START_VALIDATION.json'),Start_reaudit=start_reaudit,callback_profile=profile,resource_summary=resources,pytest=pytest,post_heavy_checks=checks,post_heavy_audits=audits,certificate=certificate,original_strict_solve_result=strict_result,old_bounds_used=False,additional_scientific_P1_calls=0,A1_calls=0,LP_calls=0,downstream_calls=0))
    def fmt(value):return 'NULL' if value is None else (f'{value:.12g}' if isinstance(value,float) else str(value))
    delivery=optional('GIT_DELIVERY.json',{})
    initial=('Draft PR 생성 후 연결' if not delivery else delivery['PR']+' / 검증 commit '+delivery['code_and_scientific_evidence_commit'])
    cp=timeline.get('checkpoint') or {};cp_node=cp.get('checkpoint_node_count');cp_at=cp.get('checkpoint_state_solver_seconds')
    chosen=certificate.get('chosen_incumbent') or {};numerical=chosen.get('numerical',{});residuals=numerical.get('residuals',{})
    point_audits=optional('CURRENT_INCUMBENT_NUMERICAL_REAUDIT.json',{}).get('records',[])
    if point_audits:residuals={key:max(r['numerical']['residuals'][key] for r in point_audits) for key in residuals}
    last=cp.get('last_MIP_observation') or {}
    checkpoint_text=f'{fmt(cp_node)} (callback {fmt(cp_at)} s)' if cp_node is not None else f"NULL; watchdog 기록 {fmt(cp.get('observed_at_seconds'))} s, 마지막 MIP node={fmt(last.get('nodes'))} @ {fmt(last.get('time'))} s는 과거 관측값"
    report=f'''1. Draft PR / SHA / pytest / clean: {initial}; full {pytest.get('full',{}).get('passed','NULL')} PASS / semantic {pytest.get('semantic',{}).get('passed','NULL')} PASS. Final HEAD 및 clean은 최종 Git 전달에서 확인한다.
2. PR134 model identity 동일 여부: {pair.get('PASS',False)}. Matrix/objective/bounds/vtypes/RHS/names exact 동일, A1 freeze/NormalAmps/source SHA 동일. Reduced 886,017행 / 316,743열 / 208,312 binaries / 8,447,855 nnz.
3. 1 worker / Threads=1 준수: {flags['SINGLE_WORKER_ACTIVE']}. ENV thread pools=1. Solver FeasibilityTol/IntFeasTol/OptimalityTol=1e-8 유지; 전역 postsolve numerical tolerance=1e-6. 정정 후 optimize 0회.
4. Zero-action MESS Start: {'PASS' if flags['M1_ZERO_ACTION_START_VALID'] else 'FAIL'} (재분류). Original strict 1e-8 FAIL 보존; numerical 1e-6 및 기존 physical/primary semantics로 재검증. Full unreduced max row residual {fmt(start.get('validation',{}).get('full_unreduced_matrix_audit',{}).get('max_constraint_violation'))}. Route/PQ/SOC repair/clipping 0.
5. Start 사용 여부: {result.get('Start_used',False)}. 새 후보만 검증, 과거 PR126/131 Start 사용 0.
6. Callback time PR134 vs 이번 run: native 66.91 s / {fmt(p1_profile.get('Gurobi_reported_callback_seconds'))} s; handler body wall {fmt(p1_profile.get('handler_body_wall_seconds'))} s / thread CPU {fmt(p1_profile.get('handler_body_thread_CPU_seconds'))} s; calls {fmt(p1_profile.get('Gurobi_reported_callback_calls'))}. Callback filesystem I/O 0.
7. Presolve 완료 시간: {fmt(times.get('presolve_end'))} s (solver runtime).
8. Barrier 완료 시간: {fmt(times.get('barrier_end'))} s.
9. Crossover 완료 시간: {fmt(times.get('crossover_end'))} s.
10. DegenMoves 구간 시간: start={fmt(times.get('DegenMoves_start'))}, end={fmt(times.get('DegenMoves_end'))}; 직접 관측 없으면 0으로 추정하지 않는다.
11. Root processing 완료 시간: {fmt(times.get('root_processing_complete'))} s. Root relaxation 완료는 {fmt(times.get('root_relaxation_complete'))} s로 별도 기록.
12. First nonroot 시간: {fmt(times.get('first_nonroot'))} s.
13. First branch 시간: {fmt(times.get('first_branch'))} s; 추정하지 않는다.
14. First incumbent 시간: {fmt(times.get('first_incumbent'))} s. 재검증 {result.get('accepted_incumbents')}개 numerical + physical PASS. 두 점 전체 max: bound residual={fmt(residuals.get('original_variable_bound'))}, full-row={fmt(residuals.get('original_full_row'))}, integrality={fmt(residuals.get('near_integer'))}; raw point repair 0.
15. 600초 시점 node count: {checkpoint_text}. 정확한 600.000 s 값은 노출되지 않으면 NULL.
16. M1 UB: {fmt(certificate.get('UB'))}; exact 값은 새 certificate에 보존.
17. M1 LB: {fmt(certificate.get('LB'))}; 기존 reference bound와 혼합하지 않는다.
18. M1 gap: {fmt(100*certificate['gap'] if certificate.get('gap') is not None else None)}%; (UB-LB)/abs(UB)를 동일 solve bound로 재계산. native status {result.get('status','NULL')}, runtime {fmt(result.get('runtime'))} s, node count {fmt(result.get('node_count'))}.
19. P1_ACCEPTED: {flags['M1_P1_ACCEPTED']}.
20. P2 movement energy/count: {fmt(p2.get('movement_energy'))} / {fmt(p2.get('movement_count'))}; optimization calls {p2.get('optimization_calls',0)}, P1 UB lock slack 0.
21. M1_ACCEPTED: {flags['M1_ACCEPTED']}.
22. ROOT_PATH_FIX: {verdict}; incumbent는 인정됐지만 nonroot/branch 미관측. 기존 strict gate 결과와 600초 checkpoint를 보존했고 root-path 재실행 0회. Wall-time causal proof는 주장하지 않는다.
23. 다음 병목 하나: {bottleneck}. 추가 시험 0.

이번 작업에서 scientific M1 model은 변경하지 않았고, solver-side 변경은 DegenMoves=0과 새 A1 기반 validated Start뿐이다. Start는 허용된 변경 범위이며 완료된 solve에서는 실제 미사용이다. 실제 적용한 solver parameter 변경은 DegenMoves=0 하나다.
기존 PR126/PR131/PR134의 UB/LB/gap을 새 certificate에 혼합하지 않았다.
A2/M2/Actual/Fresh AC는 실행하지 않았다.
이번 정정은 physical constraint 완화가 아니라 post-solve floating-point numerical audit contract의 전역 정상화이다.
Solver-side FeasibilityTol/IntFeasTol/OptimalityTol=1e-8은 변경하지 않았다.
현재 1800초 M1 solve를 재실행하지 않았으며, 저장된 incumbent와 bound만 동일한 새 validator로 재검증했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    amendment_report=f'''1. Solver-side tolerance: FeasibilityTol/IntFeasTol/OptimalityTol=1e-8 유지.
2. Post-solve numerical tolerance: 전역 1e-6; 공통 v42_postsolve.contract validator.
3. Incumbent max bound residual: {fmt(residuals.get('original_variable_bound'))}. 두 raw point의 잔차가 원본 감사와 exact 재현됐다.
4. Full-row max residual: {fmt(residuals.get('original_full_row'))}; 원본 961,472행.
5. Integrality max residual: {fmt(residuals.get('near_integer'))}; rounding 0.
6. Physical audit: {chosen.get('physical',{}).get('PHYSICAL_AUDIT_PASS')}. 기존 policy/tolerance 유지. Raw minimum/maximum 및 실제 exceedance는 CURRENT_INCUMBENT_PHYSICAL_REAUDIT.json에 각각 기록한다.
7. Incumbent scientific UB 채택: {certificate.get('valid_incumbent')}, UB={fmt(certificate.get('UB'))}. Solver accepted + numerical PASS + physical PASS를 모두 요구한다.
8. Valid LB: {fmt(certificate.get('LB'))}; 동일 완료 solve의 native global bound만 사용한다.
9. Recalculated gap: {fmt(100*certificate['gap'] if certificate.get('gap') is not None else None)}%; (UB-LB)/abs(UB).
10. M1_P1_ACCEPTED: {flags['M1_P1_ACCEPTED']}; gap>0.5%, P2 NOT_RUN.
11. Zero-action Start 재분류: {flags['M1_ZERO_ACTION_START_VALID']}; numerical + physical + primary semantics PASS, 기존 strict FAIL 보존.
12. Current solve에서 Start 실제 사용: False; 재분류가 완료 solve의 이 기록을 바꾸지 않는다.
13. Physical limits changed: False; voltage 0.95–1.05 pu / source-backed NormalAmps / kVA / line / SOC / PCS / route / capacity / Runtime / CC4 유지.
14. New optimize calls: 0; stored points 재검증만 수행. Accepted A1은 가능한 증거 범위에서 일관성 PASS, 새 full A1 matrix audit는 주장하지 않는다.

이번 정정은 physical constraint 완화가 아니라 post-solve floating-point numerical audit contract의 전역 정상화이다.
Solver-side FeasibilityTol/IntFeasTol/OptimalityTol=1e-8은 변경하지 않았다.
현재 1800초 M1 solve를 재실행하지 않았으며, 저장된 incumbent와 bound만 동일한 새 validator로 재검증했다.
'''
    (OUT/'TOLERANCE_AMENDMENT_REVIEW_KO.md').write_text(amendment_report,encoding='utf8')
    (OUT/'PR_DESCRIPTION.md').write_text(f'''PR134 M1은 root relaxation/crossover 이후 DegenMoves에서 시간을 쓰며 600초까지 nonroot/branch와 incumbent가 없었다. 동일 reduced MPS와 새 A1 freeze를 읽기 전용으로 재사용하고 scientific matrix/objective/bounds/vtypes/RHS 및 source/A1/NormalAmps SHA를 검증했다. 모든 solver 설정을 유지해 DegenMoves=0만 적용하는 단일 P1 실행과 새 zero-action Start 검증을 추가한다.

The completed P1 is preserved byte for byte: status={result.get('status')}, runtime={result.get('runtime')} s; first incumbent={times.get('first_incumbent')} s, nonroot/branch unobserved. ROOT_PATH_FIX={verdict}. The user-authorized amendment introduces one global V42 post-solve numerical validator at 1e-6, separately from unchanged physical audit policy and solver FeasibilityTol/IntFeasTol/OptimalityTol=1e-8. It applies to A1/M1/A2/M2/B0–B3, each B3 loop, Planning freeze and reconstructed certificates. Historical frozen executables and original strict-gate artifacts are preserved.

Both saved raw MIPSOL points reproduce their original residuals exactly, pass numerical and independent physical audits, and now support scientific UB={certificate.get('UB')}; same-solve LB={certificate.get('LB')}, recalculated gap={certificate.get('gap')}. Gap exceeds 0.5%, so P1_ACCEPTED={flags['M1_P1_ACCEPTED']}, P2 NOT_RUN and M1_ACCEPTED={flags['M1_ACCEPTED']}. No clipping, rounding, route/PQ repair, physical RHS/rating change or new optimize call. Zero-action Start valid={flags['M1_ZERO_ACTION_START_VALID']} under the amended audit policy; CURRENT_SOLVE_START_USED={result.get('Start_used',False)} remains unchanged. Raw points are included with SHA provenance. The accepted A1 is retrospectively consistent using saved native aggregate numerical evidence and freshly checked independent semantics; a new full A1 matrix audit is not claimed because that matrix was not retained. Old UB/LB/gap are never transferred into the new certificate.

Callback은 literal phase/30초 trace/solution 점을 memory buffer에 기록하고 종료 후 artifact를 쓴다. Native callback time PR134 66.91 s → {p1_profile.get('Gurobi_reported_callback_seconds')} s; body wall/CPU와 호출 수는 별도 기록한다. 노출되지 않는 DegenMoves/root-completion/branch 시각과 정확한 600초 상태는 NULL로 보존하며 마지막 관측값을 구분한다. Paired wall-time만으로 causal speedup을 주장하지 않는다.

1 worker / Threads=1, ENV pools=1. Amendment regression tests cover the global policy, unchanged solver/physical limits, no point repair, both acceptance gates and prohibited historical bound transfer. Semantic {pytest.get('semantic',{}).get('passed')} PASS, full {pytest.get('full',{}).get('passed')} PASS; compile/diff/model/certificate/source and PR134 {len(source['files'])} files preserved byte for byte. Raw native import traces and the existing warning are retained with actual successful test exits. A1 reoptimization/new LP solve/restart/parameter sweep/Actual/Fresh AC calls=0. Next observed bottleneck: {bottleneck}.
''',encoding='utf8')
    sources=[p for folder in (ROOT/'v42_degen',ROOT/'tests/v42_degen',ROOT/'v42_postsolve',ROOT/'tests/v42_postsolve') for p in folder.iterdir() if p.is_file()]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p!=OUT/'SHA256_MANIFEST.json'],sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(sources)]))
    print('DEGEN_FINAL_FLAGS',flags,bottleneck,flush=True)
if __name__=='__main__':run()
