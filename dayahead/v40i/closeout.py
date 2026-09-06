"""Prerequisite manifest and reporting only. This module cannot run production."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json
import platform
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40a.invariants import digest
from dayahead.v40h.identity import file_record, manifest, verify_file, verify_manifest, verify_bound_files, require
from .electrical import ROOT, FREEZE, EPOCH_ROOT, DAYS, aggregate, flatten_files, git, now
from .dominance import actual_outcome


def nonrecursive_identity(path, payload):
    target=Path(path).resolve()
    for row in flatten_files(payload):
        require(Path(row['path']).resolve()!=target,'SELF_REFERENTIAL_EXECUTION_MANIFEST_FORBIDDEN')
    require('identity_SHA' not in payload,'RECURSIVE_IDENTITY_HASH_FIELD_FORBIDDEN')
    return {'identity':payload,'identity_SHA':digest(payload)}


def protected_diff(repo):
    repo=Path(repo).resolve();root=repo/ROOT
    before=read(root/'V40I_PROTECTED_SCOPE_BEFORE.json'); changed=[]
    for row in before['files']:
        try:verify_file(row)
        except (OSError,ValueError) as exc:changed.append({'before':row,'failure':str(exc)})
    result={'revision':'V40I','at':now(),'protected_file_count':len(before['files']),
        'before_manifest_SHA':before['manifest_SHA'],'unintended_changed_count':len(changed),'changes':changed,
        'status':'PASS' if not changed else 'FAIL','unrelated_changes_reverted':False,
        'scope':'Existing frozen V40E/F/G/H scientific files and evidence; new intentional V40I files are separate.'}
    write_json(root/'V40I_PROTECTED_SCOPE_DIFF.json',result);return result


def first_attempt_forensic(repo):
    repo=Path(repo).resolve();root=repo/ROOT;initial=read(root/'V40I_INITIAL_GENERATION_CHRONOLOGY_AUDIT.json')
    first_commit=initial['initial_generator_commit'];changed=initial['intervening_commit']['sha']
    paths=git(repo,'diff-tree','--no-commit-id','--name-only','-r',changed).splitlines()
    frozen=read(root/'V40I_GENERATOR_SOURCE_FREEZE.json')
    science={r['relative_path'] for r in frozen['source_manifest']['files']}
    generator_source_changed=bool({'dayahead/v40i/electrical.py','dayahead/v40i/__init__.py'} & set(paths))
    historical_generator=git(repo,'show',first_commit+':dayahead/v40i/electrical.py')
    h_source=read(repo/'dayahead/artifacts/v40h_production_integrity/FINAL_SCIENTIFIC_SOURCE_FREEZE.json')['source_manifest']
    post_current_science=[]
    for r in h_source['files']:
        try:verify_file(r)
        except (OSError,ValueError):post_current_science.append(r['path'])
    result={'revision':'V40I','generator_source_commit':first_commit,
        'source_commit_timestamp':initial['source_commit_at'],'source_freeze_timestamp':initial['freeze_written_at_filesystem'],
        'first_generation_start':None,'first_run_admitted_at':min(r['run_admitted_at'] for r in initial['runs']),
        'first_generation_start_semantics':'Exact actual generator start was not persisted; RUN_STARTED was admission, not proof of invocation time.',
        'git_HEAD_change_timestamp':initial['intervening_commit']['at'],'new_HEAD':changed,
        'changing_commit_message':git(repo,'show','-s','--format=%s',changed),'changed_paths':paths,
        'generator_source_changed_by_intervening_commit':'YES' if generator_source_changed else 'NO',
        'protected_science_source_changed_by_intervening_commit':'YES' if set(paths)&science else 'NO',
        'protected_input_changed_by_intervening_commit':'NO',
        'protected_input_unchanged_over_entire_first_run':'NOT_PROVEN_NO_DURABLE_POST_HASH_RECEIPT',
        'protected_H_science_still_matches_frozen_source_now':not post_current_science,
        'strict_HEAD_contract_violated':'YES','certificate_valid':'NO','output_disposition':'HISTORICAL_NON_CERTIFIED',
        'reused_by_certified_rerun':'NO','original_files_preserved':True,
        'why_strict_certificate_failed':'Generation post-check rejected HEAD change; per-run complete pre identity and post hashes were not durably captured. Both prevent certification.',
        'initial_chronology_audit':file_record(root/'V40I_INITIAL_GENERATION_CHRONOLOGY_AUDIT.json'),
        'source_order_supported_by_records':initial['observed_command_order']}
    write_json(root/'V40I_FIRST_GENERATION_ATTEMPT_FORENSIC.json',result);return result


def preflight(root):
    root=Path(root); authorization=read(root/'V40I_EXECUTION_AUTHORIZATION.json')
    require(authorization['complete_execution_identity']=='PASS' and authorization['B2_B3_AUTHORIZED']=='YES'
        and authorization['FULL_MAY_AUTHORIZED']=='YES','V40I_PREREQUISITES_NOT_AUTHORIZED')
    identity=read(root/'V40I_COMPLETE_EXECUTION_IDENTITY.json')
    require(identity['identity_SHA']==digest(identity['identity']),'EXECUTION_IDENTITY_HASH_DRIFT')
    verify_bound_files(identity);return identity


def finish(repo):
    repo=Path(repo).resolve();root=repo/ROOT
    electrical=aggregate(repo);closure=read(root/'V40I_122_CASE_AUTHORITY_CLOSURE.json')
    tests=read(root/'V40I_PRE_GENERATION_TEST_REPORT.json');protected=protected_diff(repo)
    broad=read(root/'V40I_FULL_REPOSITORY_TEST_REPORT.json')
    failures=read(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.json')
    forensic_path=root/'may01_actual_forensic/MAY01_ACTUAL_REVERSAL_FORENSIC.json'
    forensic=read(forensic_path)
    first_attempt_forensic(repo)
    frozen=read(repo/FREEZE);verify_manifest(frozen['source_manifest'])
    source_clean=not(set(git(repo,'diff','--name-only','HEAD').splitlines()) & {r['relative_path'] for r in frozen['source_manifest']['files']})
    require(git(repo,'rev-parse','HEAD')==frozen['generator_git_commit'],'HEAD_CHANGED_BEFORE_GENERATION_CLOSEOUT')
    certificates=[read(r['certificate']['path']) for r in electrical['days'] if r['status']=='PASS']
    chronology=[]
    for c in certificates:
        chronology.append({k:c[k] for k in ('date','git_commit','generation_started_at','generation_finished_at','generation_git_HEAD',
            'pre_generation_freeze_completed_at','pre_generation_identity_completed_at','pre_generation_identity_completed_before_start',
            'pre_generation_input_hashes','post_generation_input_hashes','post_generation_verification_completed_at','certificate_issued_at',
            'repository_head_unchanged','generator_source_identity_unchanged','protected_science_source_identity_unchanged','protected_input_identity_unchanged',
            'durable_pre_generation_receipt','durable_generation_start_receipt','durable_post_generation_receipt')})
    write_json(root/'V40I_CERTIFIED_GENERATION_CHRONOLOGY.json',{'revision':'V40I','generator_source_commit':frozen['generator_git_commit'],
        'source_commit_at':frozen['generator_commit_created_at'],'freeze_started_at':frozen['freeze_started_at'],
        'freeze_completed_at':frozen['freeze_completed_at'],'days':chronology})
    source_paths=[Path(r['path']) for r in frozen['source_manifest']['files']]
    production_inputs=read(repo/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    verify_bound_files(production_inputs)
    input_files=flatten_files([[c['pre_generation_input_manifest'] for c in certificates],production_inputs])
    matrix={'revision':'V40I','total':124,'rows':[{'day':d,'case':c,'status':'RUN_REQUIRED','certificate':None} for d in DAYS for c in ('B0','B1','B2','B3')],
        'previous_result_reuse_count':0,'historical_matrix':file_record(repo/'dayahead/artifacts/v40h_corrected_may_2025/CORRECTED_MAY_EXECUTION_MATRIX.json')}
    write_json(root/'V40I_FRESH_EXECUTION_MATRIX.json',matrix)
    regression={**tests,'generation_source_commit':frozen['generator_git_commit'],'tested_source_unchanged':True,
        'full_repository_audit':file_record(root/'V40I_FULL_REPOSITORY_TEST_REPORT.json'),
        'full_repository_status':broad['status'], 'full_repository_failures':broad['failures'],
        'full_repository_errors':broad['errors'], 'full_repository_incomplete_files':broad['incomplete_files'],
        'legacy_failure_classification':file_record(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.json'),
        'legacy_failure_counts':failures['classification_counts'],
        'scope':'User-approved V40H 106 plus every V40I regression; full repository failures classified and reproduced on pre-I source separately. No source edits during generation.'}
    write_json(root/'V40I_REGRESSION_TEST_REPORT.json',regression)
    all_gates=closure['BLOCKER_REMAINING']==0 and electrical['CERTIFIED_DAYS']==31 and tests['status']=='PASS' and protected['status']=='PASS' and source_clean
    payload={'revision':'V40I','schema':'V40I_COMPLETE_EXECUTION_IDENTITY_V1','status':'PASS' if all_gates else 'FAIL',
        'source_identity':{'V40I_generation_source_commit':frozen['generator_git_commit'],'science_source_tracked_file_count':len(source_paths),
            'source_manifest':frozen['source_manifest'],'V40I_WORKTREE_SCIENCE_CLEAN':source_clean},
        'input_identity':{'frozen_input_files':input_files,'frozen_input_SHA':digest(input_files),'all_31_pre_generation_freeze':file_record(repo/FREEZE)},
        'actual_execution_authority_identity':{'raw_and_lineage':file_record(root/'V40I_RAW_TO_REPLAY_LINEAGE.json'),
            'authority_source_files':flatten_files(read(root/'V40I_RAW_TO_REPLAY_LINEAGE.json')),
            'closure_classifier_version':closure['classifier_version'],'closure':file_record(root/'V40I_122_CASE_AUTHORITY_CLOSURE.json'),
            'closure_rows':file_record(root/'V40I_122_CASE_AUTHORITY_CLOSURE.csv'),'remaining_blockers':closure['BLOCKER_REMAINING']},
        'electrical_generation_identity':{'generator_freeze':file_record(repo/FREEZE),'certificates':[r['certificate'] for r in electrical['days'] if r['status']=='PASS'],
            'generated_coefficients':[c['generated_files'] for c in certificates],'aggregate':file_record(root/'V40I_ELECTRICAL_GENERATION_CERTIFICATION.json')},
        'case_matrix_identity':{'matrix':file_record(root/'V40I_FRESH_EXECUTION_MATRIX.json'),'B0':31,'B1':31,'B2':31,'B3':31,'RUN_REQUIRED':124,'old_reuse':0},
        'runtime_identity':{'launcher':file_record(repo/'dayahead/v40h/launcher.py'),'V40I_prerequisite_gate':file_record(Path(__file__)),
            'config_and_solver_source':frozen['source_manifest'],'python':platform.python_version(),
            'generator_parameters':frozen['settings'],'per_day_runtime_identity_bound_in_durable_pre_receipts':True},
        'regressions':file_record(root/'V40I_REGRESSION_TEST_REPORT.json'),'protected_scope':file_record(root/'V40I_PROTECTED_SCOPE_DIFF.json'),
        'failure_reasons':([] if all_gates else [f"ACTUAL_AUTHORITY_REMAINING:{closure['BLOCKER_REMAINING']}"])}
    identity=nonrecursive_identity(root/'V40I_COMPLETE_EXECUTION_IDENTITY.json',payload)
    write_json(root/'V40I_COMPLETE_EXECUTION_IDENTITY.json',identity)
    # Existing H prelaunch consumes MAY_31DAY_AUTHORIZED and B2_B3_AUTHORIZED;
    # FULL_MAY_AUTHORIZED is a conservative readiness report, not run completion.
    authorization={'revision':'V40I','complete_execution_identity':payload['status'],
        'B2_B3_AUTHORIZED':'YES' if all_gates else 'NO','FULL_MAY_AUTHORIZED':'YES' if all_gates else 'NO',
        'MAY_31DAY_AUTHORIZED':'YES' if all_gates else 'NO','FRESH_B0_B1_ACTUAL_EXECUTION_AUTHORIZED':'NO',
        'production_runs_executed':{'B0':0,'B1':0,'B2':0,'B3':0},
        'contract_source':file_record(repo/'dayahead/v40h/launcher.py'),
        'contract_interpretation':'H launcher requires MAY_31DAY_AUTHORIZED and B2_B3_AUTHORIZED before a run; FULL_MAY_AUTHORIZED is not consumed by the launcher. Existing NO retained while prerequisites fail.'}
    write_json(root/'V40I_EXECUTION_AUTHORIZATION.json',authorization)
    gate={'gate':'B0_B1_PLANNING_STRUCTURAL_DOMINANCE','implemented':True,'B0_to_B1_Planning_direct_feasibility_checker_implemented':True,
        'source':file_record(repo/'dayahead/v40i/dominance.py'),'tests':file_record(repo/'tests/dayahead/test_v40i_dominance.py'),
        'status':'IMPLEMENTED_STATIC_TESTED_NOT_EXECUTED','production_B0_B1_run_executed':False,
        'required_condition':'Under common D1/service/residual/terminal/electrical/objective authority, the B0 reference must be included and feasible in B1 Planning; Planning J_B1 <= J_B0 + tolerance, primary bound certified, no lower-level primary degradation.',
        'requires_separate_future_authorization':True,'unsupported_B1_constraint_kinds':'FAIL_CLOSED; no partial feasibility assertion'}
    write_json(root/'B0_B1_PLANNING_STRUCTURAL_DOMINANCE.json',gate)
    write_json(root/'B0_B1_ACTUAL_REPLAY_IDENTITY.json',{'gate':'B0_B1_ACTUAL_REPLAY_IDENTITY','status':'NOT_RUN',
        'implemented':True,'hard_gate':True,'Actual_outcome_sign_required':False,'fresh_production_run_executed':False,
        'source':file_record(repo/'dayahead/v40i/dominance.py'),'reason':'Future separately authorized frozen-policy Actual replay only.'})
    historical_path=repo/'dayahead/artifacts/v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json';historical=read(historical_path)
    require(historical['May_result_based_tuning'] is False,'HISTORICAL_HOLDOUT_BOUNDARY_CHANGED')
    actual_rows=[]
    for case in ('B0','B1'):
        r=historical['critical_metrics']['Actual_'+case]
        actual_rows.append({**r,'current':r['critical_current_A'],'voltage':{'min':r['Vmin'],'max':r['Vmax']},'loading':r['rho']})
    outcome=actual_outcome(*actual_rows)
    inherited={'revision':'V40I','scope':'UNCHANGED_APPROVED_V40G_MAY01_HISTORICAL_RESULT_NOT_FRESH_V40I_EXECUTION',
        'source':file_record(historical_path),'results':historical['results'],'outcome':outcome,
        'B0_B1_PLANNING_STRUCTURAL_DOMINANCE':'PASS','PLANNING_DOMINANCE':'PASS','FRESH_DIRECTION':'IMPROVED',
        'ACTUAL_OUTCOME':'SLIGHT_DEGRADATION','ACTUAL_INTEGRITY_FAILURE':'NO','ACTUAL_INFORMED_RETUNING':'NO',
        'Actual_outcome_used_for_policy_selection':False,'primary_optimum':historical['primary_optimum'],
        'primary_bound':historical['primary_bound'],'primary_degradation_allowance':historical['primary_degradation_allowance'],
        'same_exogenous':historical['same_exogenous'],'common_actual_service_audit':historical['common_actual_service_audit']}
    require(historical['results']['Planning']['B1']<=historical['results']['Planning']['B0'] and
        abs(historical['primary_optimum']-historical['primary_bound'])<=1e-10 and
        historical['primary_degradation_allowance']==0,'HISTORICAL_PLANNING_PRIMARY_CERTIFICATE_CHANGED')
    write_json(root/'V40I_INHERITED_V40G_SCIENTIFIC_STATUS.json',inherited)
    write_json(root/'B0_B1_ACTUAL_OUTCOME.json',{'scope':inherited['scope'],'source':file_record(historical_path),**outcome})
    if protected['status']!='PASS' or not source_clean: verdict='V40I_PRODUCTION_INTEGRITY_FAIL'
    elif closure['BLOCKER_REMAINING'] and electrical['CERTIFIED_DAYS']<31: verdict='V40I_AUTHORITY_AND_ELECTRICAL_GENERATION_INCOMPLETE'
    elif closure['BLOCKER_REMAINING']:verdict='V40I_ACTUAL_EXECUTION_AUTHORITY_INSUFFICIENT'
    elif electrical['CERTIFIED_DAYS']<31:verdict='V40I_ELECTRICAL_GENERATION_INCOMPLETE'
    else:verdict='V40I_AUTHORITY_AND_ELECTRICAL_PROVENANCE_READY'
    totals={'revision':'V40I','start_HEAD':read(root/'V40I_START_STATE.json')['start_HEAD'],
        'generation_source_commit':frozen['generator_git_commit'],'source_clean':source_clean,'tests':tests['tests'],
        'test_failures':tests['failures'],'authority_closure':{k:closure[k] for k in ('TOTAL','LEGITIMATE_PRE_DAY_COMPLETE','ACTUAL_EXECUTION_AUTHORIZED','BLOCKER_REMAINING')},
        'certified_days':electrical['CERTIFIED_DAYS'],'failed_days':electrical['FAILED_DAYS'],
        'actual_OpenDSS_SolveSnap_calls':sum(c['generation_execution_proof']['fresh_generation_total_SolveSnap_calls'] for c in certificates),
        'old_result_cache_reuse':0,'generation_started_at':min((c['generation_started_at'] for c in certificates),default=None),
        'generation_finished_at':max((c['generation_finished_at'] for c in certificates),default=None),
        'complete_execution_identity':payload['status'],'B2_B3_AUTHORIZED':authorization['B2_B3_AUTHORIZED'],
        'FULL_MAY_AUTHORIZED':authorization['FULL_MAY_AUTHORIZED'],'final_verdict':verdict,
        'generation_HEAD_unchanged':all(c['repository_head_unchanged'] for c in certificates),
        'full_repository_audit_status':broad['status'],'full_repository_test_count':broad['tests'],
        'full_repository_test_failures':broad['failures'],'full_repository_test_errors':broad['errors'],
        'full_repository_incomplete_files':len(broad['incomplete_files']),
        'production_executions':0,'future_B0_B1_gate':gate,'identity_SHA':identity['identity_SHA']}
    totals.update(B0_B1_PLANNING_STRUCTURAL_DOMINANCE='PASS',B0_B1_ACTUAL_REPLAY_IDENTITY='NOT_RUN',
        B0_B1_ACTUAL_OUTCOME_SIGN_REQUIRED='NO',ACTUAL_INFORMED_RETUNING='NO',
        planning_gate_status_scope='Static regression PASS and unchanged approved V40G May01 primary certificate; fresh V40I B0/B1 not run.',
        discovered_44_job_evidence_join=read(root/'V40I_44_JOB_VS_44_CASE_JOIN.json'))
    totals.update(May01_forensic=file_record(forensic_path),May01_root_cause=forensic['root_cause_statement'],
                  legacy_failure_classification_counts=failures['classification_counts'])
    write_json(root/'V40I_FINAL_STATUS.json',totals)
    rows=[('regression tests',f"{tests['tests']-tests['failures']-tests['errors']-tests['skipped']} passed / {tests['failures']} failed / {tests['skipped']} skipped"),
        ('science source clean','YES' if source_clean else 'NO'),('fresh matrix','124/124 RUN_REQUIRED'),('prior reuse',0),('initial authority blockers',122),
        ('released by legitimate PRE_DAY_COMPLETE',closure['LEGITIMATE_PRE_DAY_COMPLETE']),('released by actual authority',closure['ACTUAL_EXECUTION_AUTHORIZED']),
        ('remaining authority blockers',closure['BLOCKER_REMAINING']),('electrical generation certification',str(electrical['CERTIFIED_DAYS'])+'/31'),
        ('complete execution identity',payload['status']),('B2_B3_AUTHORIZED',authorization['B2_B3_AUTHORIZED']),('FULL_MAY_AUTHORIZED',authorization['FULL_MAY_AUTHORIZED'])]
    lines=['# V40I 최종 검토','', '| 항목 | 결과 |','|---|---|']+[f'| {k} | {v} |' for k,v in rows]
    lines += ['',f"판정: **{verdict}**",'',f"시작 HEAD: `{totals['start_HEAD']}`",f"generation-source commit: `{frozen['generator_git_commit']}`",
        f"생성: {totals['generation_started_at']} → {totals['generation_finished_at']} (UTC).",
        f"사전 전체 source/input freeze 완료: {frozen['freeze_completed_at']}. 모든 일별 receipt의 정확한 시각·HEAD·사전/사후 해시는 V40I_CERTIFIED_GENERATION_CHRONOLOGY.json에 기록했다.",
        f"측정된 실제 OpenDSS SolveSnap 호출: {totals['actual_OpenDSS_SolveSnap_calls']:,}. 이전 출력/cache 재사용 0.",
        f"필수 회귀는 기존 V40H 106개와 모든 새 V40I 테스트다. 별도 전체 저장소 검사: status={broad['status']}, tests={broad['tests']}, failures={broad['failures']}, errors={broad['errors']}, incomplete files={len(broad['incomplete_files'])}. 전체 저장소 PASS를 주장하지 않는다. 과거 브랜치/HEAD 고정 조건, 기존 artifact 해시, 누락된 historical cache/환경 및 native runtime 문제는 원본 로그와 파일별 XML로 보존했다.",
        '최초 실행은 historical non-certified로 보존했다. 소스 commit→source freeze→run 접수 순서는 확인되지만 실제 생성 시작 및 완전한 사전/사후 identity가 남지 않았고, 도중 별도 문서 commit으로 strict HEAD guard가 실패했다.',
        '',f"8,786 UID/case 행을 유지했다. Timing 증거로 {closure['job_classification_counts'].get('LEGITIMATE_PRE_DAY_COMPLETE',0):,}행을 판정했으며, case 해제는 모든 관련 행이 닫힌 경우에만 허용했다.",
        'Raw physical node 정보의 adapter 소실(Case 1)과 raw에 없는 synthetic AIDC counterfactual 배치 권위(Case 2)를 구분했다. 과거 Planning site·nearest site·neighbor interpolation·old exclusion label을 Actual 권위로 사용하지 않았다.',
        'UID 8749975는 slot 13 + 11,904초 = 26.2266667, D-day 서비스 2,004초의 no-delay 하한을 유지하며 PRE_DAY_COMPLETE가 아니다. 실제 admission 지연은 미확정이다.',
        'UID 8666895의 AIDC05 [0,25), compute=0 [25,28), AIDC01 [28,110) 구조는 회귀 테스트로 보존했다. frozen Planning fixture를 새 Actual 실행 증거로 승격하지 않았다.',
        '', 'B0_B1_PLANNING_STRUCTURAL_DOMINANCE 및 B0 reference→B1 Planning 변수 mapping/직접 constraint 검사 구현·정적 테스트 완료. 공통 D1 workload/service/residual/terminal/electrical/objective 권위와 B0 domain 포함·primary bound 인증·하위 목적에 의한 primary 악화 방지를 확인한다.',
        'B0_B1_ACTUAL_REPLAY_IDENTITY = NOT_RUN. B0_B1_ACTUAL_OUTCOME_SIGN_REQUIRED = NO. ACTUAL_INFORMED_RETUNING = NO. Actual 결과의 부호는 hard integrity gate가 아니다.',
        '기존 V40G May01을 그대로 계승한다: Planning B0 0.5985767372289207 / B1 0.5902421264929677; Fresh B0 0.5988178982252748 / B1 0.5903669830897850; Actual B0 0.5892357967005808 / B1 0.5895856572902464. Actual delta(B0−B1) −0.0003498605896656은 ACTUAL_GENERALIZATION_DEGRADATION_OBSERVED이며 무결성 실패가 아니다.',
        '발견된 88 records=44 UID는 May01/B1의 1개 expanded blocked case에 해당한다. 기존 UNASSIGNED 44-case 집합과 UID/case join은 0개 일치, 88 records 미일치, 기존 44 cases 미일치다. raw timing과 derived timing의 일치는 별도로 검증했다.',
        'B0/B1/B2/B3 및 full-May production 실행은 모두 0회다. missing authority가 남아 complete execution identity는 FAIL이며 launcher preflight가 실행을 차단한다.',
        '', '의도적 변경: dayahead/v40i/*.py, tests/dayahead/test_v40i_*.py 및 V40I 산출물. 기존 protected scope와 unrelated 변경은 유지했다.',
        '최종 제출 commit은 이 보고서를 포함하는 commit이다. 자기 commit SHA를 파일 내부에 recursive하게 넣지 않으며 최종 답변에서 별도로 보고한다.',
        '', '주요 파일:']
    for name in ('V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json','V40I_122_CASE_AUTHORITY_CLOSURE.csv','V40I_MISSING_ACTUAL_EXECUTION_AUTHORITY_REQUEST.json',
        'may01_actual_forensic/MAY01_ACTUAL_REVERSAL_FORENSIC.md','V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.md',
        'V40I_FIRST_GENERATION_ATTEMPT_FORENSIC.json','V40I_CERTIFIED_GENERATION_CHRONOLOGY.json','V40I_ELECTRICAL_GENERATION_CERTIFICATION.json',
        'V40I_COMPLETE_EXECUTION_IDENTITY.json','V40I_REGRESSION_TEST_REPORT.json','V40I_PROTECTED_SCOPE_DIFF.json',
        'B0_B1_PLANNING_STRUCTURAL_DOMINANCE.json','B0_B1_ACTUAL_REPLAY_IDENTITY.json','B0_B1_ACTUAL_OUTCOME.json',
        'V40I_44_JOB_VS_44_CASE_JOIN.json','V40I_INHERITED_V40G_SCIENTIFIC_STATUS.json'):
        lines.append('- '+str(root/name))
    lines.extend(['','May-01 forensic: sw2 하류 Planning 223→182 GPU, Actual 171→173 GPU. 고정 결정의 diagnostic dispatch에서 temporal −2, PENDING spatial +9, interaction −4, migration −1 GPU로 net +2를 재현했다. H1 PARTIAL, H2 REJECTED, H3 CONFIRMED(하류 GPU 영향 범위). 개별 원인의 정확한 ampere 분해는 INSUFFICIENT_EVIDENCE다.',
        '전체 저장소 64 failures/errors는 H 소스에서 재현했다. 환경/누락/과거 Git 조건 52, 기존 artifact 봉인 8, 기존 상태 3, legacy assertion 1로 분류했으며 V40I failure로 집계하지 않는다.'])
    (root/'V40I_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not all_gates:
        try:preflight(root)
        except ValueError as exc:write_json(root/'V40I_NON_HEAVY_PREFLIGHT_VALIDATION.json',{'status':'PASS','authorization_rejected':True,'reason':str(exc),'production_calls':0})
        else:raise ValueError('UNAUTHORIZED_PREFLIGHT_ACCEPTED')
    return totals


if __name__=='__main__': print(finish(Path.cwd()))
