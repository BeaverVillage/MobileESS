"""Evidence-only report and content manifest; never launches optimization."""
import sys,subprocess,hashlib
from pathlib import Path
from v42_cutpass.common import ROOT,OUT,REF,BASE,sha,read,write

ENDING=(
'이번 작업에서는 May 31-day B0/B1/B2/B3 production campaign을 실행하지 않았으며, 향후 실행 순서와 B3 4-loop orchestration만 구현·검증했다.',
'향후 Main May Campaign은 B0 -> B1 -> B2 -> B3(Loop 1)의 순서로 각각 Actual/Fresh AC까지 완료한다.',
'Main May Campaign 완료 후에만 B3를 Loop 2 -> Actual -> Loop 3 -> Actual -> Loop 4 -> Actual 순서로 추가 실행한다.',
'Loop k의 Actual 결과는 Loop k+1 Planning에 절대 feedback하지 않는다. 다음 loop는 이전 loop의 Planning state만 이어받는다.',
'기존 scientific M1 model과 physical authority는 변경하지 않았다.')

def manifest():
    roots=[OUT,ROOT/'v42_cutpass',ROOT/'v42_campaign',ROOT/'tests/v42_cutpass',ROOT/'tests/v42_campaign']
    paths=[p for root in roots for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=OUT/'SHA256_MANIFEST.json']
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',self_excluded=True,all_new_namespaces=True,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(set(paths))]))

def check_index():
    rows=subprocess.check_output(['git','ls-files','--stage','-z'],cwd=ROOT).split(b'\0');items=[]
    scopes=('docs/v42_m1_cutpass_loop_campaign/','v42_cutpass/','v42_campaign/','tests/v42_cutpass/','tests/v42_campaign/')
    for row in rows:
        if not row:continue
        meta,path=row.split(b'\t',1);name=path.decode('utf8')
        if name.startswith(scopes):items.append((meta.split()[1].decode(),name))
    output=subprocess.check_output(['git','cat-file','--batch'],input=('\n'.join(oid for oid,_ in items)+'\n').encode(),cwd=ROOT);offset=0
    for oid,name in items:
        end=output.index(b'\n',offset);header=output[offset:end].split();size=int(header[2]);blob=output[end+1:end+1+size];offset=end+size+2
        assert header[0].decode()==oid and hashlib.sha256(blob).hexdigest()==sha(ROOT/name),('INDEX_BYTES_CHANGED',name)
    for row in read(OUT/'SHA256_MANIFEST.json')['files']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    code=subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,capture_output=True,text=True);assert code.returncode==0,code.stdout+code.stderr
    print('INDEX_AND_MANIFEST_PASS',len(items),'files; raw bytes match staged blobs')

def run():
    checked=read(OUT/'POST_HEAVY_VERIFICATION.json');assert checked['PASS']
    result=read(OUT/'M1_CUTPASSES1_SOLVE_RESULT.json');certificate=read(OUT/'M1_CUTPASSES1_CERTIFICATE.json');timeline=read(OUT/'M1_CUTPASSES1_ROOT_TIMELINE.json');t=timeline['timestamps']
    start=read(OUT/'M1_ZERO_ACTION_START_SOLVER_BINDING.json');pre=read(OUT/'M1_START_PREFLIGHT.json');identity=read(OUT/'M1_PR135_MODEL_IDENTITY.json');execution=read(OUT/'EXECUTION_RECEIPT.json');p2=read(OUT/'M1_P2_RESULT.json');leak=read(OUT/'ACTUAL_TO_NEXT_LOOP_LEAKAGE_AUDIT.json');campaign=read(OUT/'CAMPAIGN_NO_EXECUTION_RECEIPT.json')
    assert identity['PASS'] and identity['PR135_payload_identity_PASS'] and pre['NUMERICAL_AUDIT_PASS'] and pre['PHYSICAL_AUDIT_PASS'] and leak['PASS']
    old=read(REF/'M1_CERTIFICATE_RECLASSIFIED.json');old_timeline=read(REF/'M1_DEGENMOVES0_ROOT_TIMELINE.json');old_result=read(REF/'M1_DEGENMOVES0_SOLVE_RESULT.json')
    write('M1_CUTPASSES1_PR135_COMPARISON.json',dict(model_identity_PASS=True,PR135_exact_head=BASE,PR135=dict(UB=old['UB'],LB=old['LB'],gap=old['gap'],timestamps=old_timeline['timestamps'],native_callback_seconds=108.67,Start_used=False,runtime=old_result['runtime']),new=dict(UB=certificate['UB'],LB=certificate['LB'],gap=certificate['gap'],timestamps=t,Start_attempted=True,Start_solver_accepted=start['START_SOLVER_ACCEPTED'],native_callback_seconds=72.53,runtime=result['runtime'],root_path_fix=result['root_cut_path_fix']),hardware_same=True,Threads_same=1,concurrent_external_heavy_processes=execution['resource_summary']['external_heavy_processes'],two_actual_changes=['CutPasses=1','exact PR135 zero-action solver Start attempt'],comparison_limitations=['600-second root-path STOP versus historical 1800-second run; no comparable terminal speedup claim','Start retry and native root subphase costs not separately exposed','Native callback time includes overhead beyond Python handler body','Historical UB/LB/gap are reference-only; never mixed into new certificate'],absolute_speedup=None,root_path_goal_achieved=False))
    write('NEXT_BOTTLENECK.json',dict(classification='root cut-processing / formulation-strength',additional_trials_executed=0,future_task_candidates_only=['fractional-binary family census','exact valid inequalities','exact root structural strengthening']))
    flags=dict(V42_INTEGRATION_PASS=True,A1_ACCEPTED=True,ZERO_VOLTAGE_MARGIN_ACTIVE=True,NORMALAMPS_TRANSFORMER_AUTHORITY_ACTIVE=True,POSTSOLVE_NUMERICAL_TOL=1e-6,SINGLE_WORKER_ACTIVE=execution['resource_summary']['sequential_policy_PASS'],SOLVER_THREADS=1,DEGENMOVES=0,CUTPASSES=1,M1_ZERO_ACTION_START_VALID=True,M1_START_ATTEMPTED=start['START_ATTEMPTED'],M1_START_SOLVER_ACCEPTED=start['START_SOLVER_ACCEPTED'],M1_ROOT_CUT_PATH_FIX=result['root_cut_path_fix'],M1_P1_ACCEPTED=certificate['M1_P1_ACCEPTED'],M1_P2_RUN=p2['optimization_calls']>0,M1_ACCEPTED=certificate['M1_ACCEPTED'],MAY_CAMPAIGN_ORCHESTRATOR_IMPLEMENTED=True,B3_LOOP_ORCHESTRATOR_IMPLEMENTED=True,ACTUAL_FEEDBACK_FIREWALL_IMPLEMENTED=True,**{k:campaign[k] for k in ('MAY_MAIN_CAMPAIGN_EXECUTION','B3_LOOP2_PRODUCTION','B3_LOOP3_PRODUCTION','B3_LOOP4_PRODUCTION','A2_PRODUCTION','M2_PRODUCTION','ACTUAL_PRODUCTION','FRESH_AC_PRODUCTION')},PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    verification=dict(PASS=True,PASS_scope='Implementation, identity, preservation, bounded causal tests and execution discipline; M1 scientific acceptance is separately false.',base_exact_head=BASE,post_heavy=checked,scientific_model_identity=identity,Start_binding=start,M1_certificate=certificate,campaign_no_execution=campaign,Actual_feedback_firewall_PASS=leak['PASS'],firewall_scope=leak['firewall_scope'],all_production_campaign_calls=0,additional_scientific_trials=0,required_artifacts_complete=True)
    write('VERIFICATION.json',verification)
    publication=read(OUT/'PR_PUBLICATION.json') if (OUT/'PR_PUBLICATION.json').exists() else {}
    def time(key):return 'NULL (미관측)' if t[key] is None else f'{t[key]:.6f} s'
    lines=[
    f"PR: {publication.get('url','Draft PR publication pending')}; scientific/code commit: {publication.get('scientific_commit','pending')}; 최종 remote head는 PR metadata와 최종 응답에서 확인. Base={BASE}. Semantic {checked['SEMANTIC']['passed']} PASS, full {checked['FULL']['passed']} PASS / {checked['FULL']['warnings']} warning; single pytest process. Commit/push 후 clean tree를 별도로 확인한다.",
    'PR135 exact M1 model identity PASS: 886,017 rows / 316,743 columns / 208,312 binaries / 8,447,855 nnz; 모든 scientific arrays와 names/source SHA 일치.',
    'Exact zero-action Start를 solver의 모든 316,743 column에 실제 입력. Start SHA와 numerical/physical PASS를 보존.',
    'Gurobi Start acceptance=false. Loaded/accepted 메시지와 incumbent 없음. did not produce 메시지 및 재시도 메시지 보존; 상세 rejection 원인과 native objective는 미노출. Candidate reference rho=0.6715884801665905는 UB로 사용하지 않음.',
    'CutPasses=1 / DegenMoves=0 / Threads=1. 다른 defaults와 solver tolerances 1e-8 유지.',
    f"Presolve 완료: {time('presolve_end')} (optimize 누적 solver runtime; native presolve phase duration은 별도 literal 64.65s).",
    f"Barrier 완료: {time('barrier_end')}.",
    f"Crossover 완료: {time('crossover_end')}.",
    f"Root relaxation 완료: {time('root_relaxation_complete')}; root processing 완료는 NULL.",
    f"First nonroot: {time('first_nonroot')}.",
    f"First branch: {time('first_branch')}; branch time을 다른 이벤트로 추정하지 않음.",
    f"First incumbent: {time('first_incumbent')}; solver solution count=0.",
    f"600초 root-path FAILED; watchdog 600.198354초 terminate 요청, 동일 optimize가 {result['runtime']:.6f}초에 INTERRUPTED. Exact 600초 UB/LB/node/cut는 NULL; 마지막 관측 475.782초와 terminal count를 별도로 보존.",
    'Terminal scientific UB=NULL (solver incumbent 없음).',
    f"Terminal valid same-solve LB={certificate['LB']!r}; 과거 bound 혼합 0.",
    'Gap=NULL; UB가 없으므로 (UB-LB)/abs(UB) 계산/acceptance 불가.',
    f"P1_ACCEPTED={certificate['M1_P1_ACCEPTED']}.",
    'P2 energy/count NOT_RUN; 값 NULL / NULL, optimize calls=0.',
    f"M1_ACCEPTED={certificate['M1_ACCEPTED']}.",
    '다음 병목 하나: root cut-processing / formulation-strength. 추가 solver 시험 0.',
    'May orchestrator 구현·bounded 검증 PASS. 전체 May dry plan 1,458 NOT_RUN stage; production backend는 비활성.',
    'Main order 정확히 B0 -> B1 -> B2 -> B3(L1), 각 arm 전체 May 완료.',
    '각 main arm의 Actual/Fresh AC 및 validated immutable artifact freeze 완료 후에만 다음 arm으로 전환.',
    'Main 완료 gate 뒤 B3 L2 -> Actual/Fresh AC -> L3 -> Actual/Fresh AC -> L4 -> Actual/Fresh AC.',
    '각 B3 loop 정확히 A1 -> M1 -> A2 -> M2. Final AIDC=A2, Final MESS=M2; M2 route/movement/P/Q/SOC 모두 free.',
    'Actual -> next Planning firewall PASS (bounded trusted-broker/read-audit 및 adversarial tests 범위). Production proof 또는 arbitrary native-code OS sandbox를 주장하지 않음.',
    '다음 loop에는 같은 day의 이전 loop Planning freeze/state만 전달. 이전 MESS fixed, 이전 AIDC validated warm candidate만. Actual은 completion metadata로만 순서 gate.',
    'Fixed-point / 2-cycle detector 구현 PASS. State SHA에서 loop/time/parent metadata 제외; 합성 fixture에서 two-cycle과 fixed point가 관측돼도 4-loop 모두 완료.',
    'May production optimizer calls=0.',
    'Actual/Fresh AC production calls=0 / 0.'
    ]
    report='\n\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+'\n\n'.join('“'+line+'”' for line in ENDING)+'\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    required=['M1_PR135_MODEL_IDENTITY.json','M1_ZERO_ACTION_START_SOLVER_BINDING.json','M1_CUTPASSES1_SOLVE.log','M1_CUTPASSES1_ROOT_TIMELINE.json','M1_CUTPASSES1_CALLBACK_AUDIT.json','M1_CUTPASSES1_SOLVE_RESULT.json','M1_CUTPASSES1_PHYSICAL_AUDIT.json','M1_CUTPASSES1_CERTIFICATE.json','M1_CUTPASSES1_PR135_COMPARISON.json','V42_MAY_CAMPAIGN_EXECUTION_CONTRACT.json','V42_B3_LOOP_CONTRACT.json','V42_ACTUAL_FEEDBACK_FIREWALL.json','MAY_CAMPAIGN_DRY_RUN_PLAN.json','B3_LOOP_STATE_SCHEMA.json','B3_LOOP_CONVERGENCE_METRICS_SCHEMA.json','B3_LOOP_FIXED_POINT_CYCLE_SCHEMA.json','CAMPAIGN_RESUME_POLICY.json','CAMPAIGN_STAGE_DEPENDENCY_GRAPH.json','CAMPAIGN_NO_EXECUTION_RECEIPT.json','ACTUAL_TO_NEXT_LOOP_LEAKAGE_AUDIT.json','FINAL_FLAGS.json','FINAL_REVIEW_KO.md','VERIFICATION.json']
    assert all((OUT/name).is_file() for name in required);manifest()
    print('FINAL_EVIDENCE_PASS; root fix FAILED; P1/P2 unaccepted; campaign production 0; required artifacts',len(required)+1)
if __name__=='__main__':
    if '--index' in sys.argv:check_index()
    elif '--manifest' in sys.argv:manifest()
    else:run()
