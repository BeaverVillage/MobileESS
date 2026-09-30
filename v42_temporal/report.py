"""Materialize truthful stopped-stage receipts and immutable-source audit."""
import subprocess
import xml.etree.ElementTree as ET
from .common import *

def main():
    folder=LOCAL/'A1_utf8_repair';receipt=read(folder/'stage_receipt.json')
    require(not (folder/'raw_complete_plan.json').exists(),'RAW_PLAN_REQUIRES_INDEPENDENT_VALIDATION_AND_CONTINUATION')
    require(not (folder/'incumbent_pointer.json').exists(),'ACCEPTED_PLAN_REQUIRES_STAGE_CONTINUATION')
    progress=read(folder/'solver_progress.json') if (folder/'solver_progress.json').exists() else {}
    model=read(folder/'model_build.json') if (folder/'model_build.json').exists() else None
    solve=read(folder/'solve_receipt.json') if (folder/'solve_receipt.json').exists() else None
    require(model is None and solve is None,'REPORT_EXPECTS_PRE_SOLVE_STOP; REVIEW_MEASURED_RESULTS')
    stopped=receipt['timeout_reason']
    blocker='A1_COMPLETE_OPTION_GENERATION_600S_TIMEOUT' if stopped=='EXTERNAL_HARD_WALL_TIMEOUT' else 'A1_BUILD_FAILURE'
    common=dict(accepted_native_plan=False,incumbent=None,best_bound=None,gap=None,nodes=None,
        binary_count=None,continuous_count=None,presolved_rows=None,presolved_columns=None,build_completed=False,
        solve_time_seconds=None,target_MIPGap=.001,maximum_optimize_seconds=600,warm_start_available=False)
    a1=dict(stage='A1',status=blocker,launched=True,solver_called=False,**common,
        build_time_seconds=receipt['total_wall_seconds'],build_time_scope='Externally bounded partial source-loading/candidate-generation attempt; not completed model construction',
        latest_complete_progress=progress,supervisor=receipt,termination_reason=stopped,
        scientific_feasibility='UNKNOWN; necessary resource condition passed but no native incumbent',
        zero_nominal_service_jobs=106,positive_service_jobs=1499,total_admitted_jobs=1605,
        zero_nominal_RUNNING_semantics='Full physical gang at issue retained; frozen Planning risk retained, no invented nominal service')
    dump('A1_MODEL_STATS.json',a1);summaries=[a1]
    for stage in ('M1','A2','M2'):
        row=dict(stage=stage,status='NOT_RUN',launched=False,solver_called=False,**common,build_time_seconds=None,
            termination_reason='PRIOR_NATIVE_STAGE_NOT_ACCEPTED')
        dump(stage+'_MODEL_STATS.json',row);summaries.append(row)
    keys=('stage','status','launched','solver_called','build_time_seconds','solve_time_seconds','incumbent','best_bound','gap','nodes',
        'binary_count','continuous_count','presolved_rows','presolved_columns','termination_reason')
    csv('V42_TS_CC4_SOLVER_SUMMARY.csv',[{k:r.get(k) for k in keys} for r in summaries])
    dump('FRESH_AC_VALIDATION.json',dict(status='NOT_RUN',PASS=None,reason='NO_ACCEPTED_A1_M1_A2_M2_PLAN',
        stale_AC_reused=False,response_kernel_created=False,Vmin=None,Vmax=None,maximum_loading=None))
    flags=dict(NEW_RUNTIME_ML_TRAINED=False,NEW_CC4_ML_TRAINED=False,NEW_TIMESHIFT_ML_TRAINED=False,NEW_CC4_TIMING_ML_TRAINED=False,
        TS_RULE_FROZEN=True,CC4_ENVELOPE_FROZEN=True,CC4_FIXED_PROFILE_EQUALITY_REMOVED=True,
        CC4_REFERENCE_KERNEL_PRESERVED=True,DEPLETION_PRESERVED=True,CARRYOUT_PRESERVED=True,
        RUNTIME_PROVIDER_UNCHANGED=True,GAMMA90_UNCHANGED=True,CAPACITY_780_UNCHANGED=True,MESS_MILP_UNCHANGED=True,
        MAY_OUTCOMES_USED=False,VALID_TUNING=False,ARTIFICIAL_FLEXIBILITY_TARGET=False,
        NECESSARY_CONDITION_PASS=True,A1_AUTHORIZED=True,A1_LAUNCHED=True,A1_OPTIMIZE_CALLED=False,
        M1_RUN=False,A2_RUN=False,M2_RUN=False,NATIVE_MODEL_BUILD_COMPLETE=False,NATIVE_ACCEPTED_PLAN=False,
        FRESH_AC_PASS=False,FINAL_RESPONSE_KERNEL_FROZEN=False)
    dump('FINAL_FLAGS.json',flags)
    verdict=dict(status='INTERFACES_IMPLEMENTED_NATIVE_CANARY_BLOCKED',blocker=blocker,
        necessary_condition='PASS_DIAGNOSTIC_ONLY',native_feasibility='UNRESOLVED_NOT_PROVEN_INFEASIBLE',
        TS_jobs=0,TS_share=0,TS_nominal_GPUh_share=0,capacity_GPU=780,gamma90=2.423057443558147,
        closed_subproblems=['Preregistered hierarchical TS eligibility and audit','TRAIN Q10/Q90 aggregate timing envelope',
            'Linear service/carryout/deviation interface','Updated necessary resource condition and immutable PR96 preservation'],
        open_subproblems=['Complete native A1 model build and solver incumbent','Independent native acceptance and M1/A2/M2 continuation',
            'Fresh AC and final response kernel','Four-stage native solver scalability'],
        Problem3='NOT_END_TO_END_CLOSED',Problem8='NOT_END_TO_END_CLOSED',
        Problem10='PARTIAL_BUILD_TIMEOUT_OBSERVED; OPTIMIZER_TIMING_GAP_NOT_MEASURED',
        no_third_rescue=True,no_solver_sweep=True,accepted_plan=False)
    dump('FINAL_VERDICT.json',verdict)
    oldroot=ROOT.parent/'v42_job_capability_pr'
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    preserved=[]
    for name in names:
        p=ROOT/name;old=oldroot/name
        require(p.is_file() and old.is_file() and sha(p)==sha(old),'LEGACY_BYTE_DRIFT:'+name)
        preserved.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size))
    require(not subprocess.check_output(['git','diff',BASE,'--']+names,cwd=ROOT),'BASE_TRACKED_DIFF')
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base=BASE,files=preserved,
        original_PR96_certificate_status='SUPERSEDED_BY_TS_AND_CC4_TEMPORAL_FLEXIBILITY_INTERFACE',
        certificate_bytes_unchanged=True,certificate=rec(OLD/'MAY01_RESUMED_SERVICE_CERTIFICATE.json'),
        baseline_file_modifications=0))
    # Preserve the failed encoding launch independently from the scientific run.
    dump('PRE_SOLVE_IO_REPAIR.json',dict(original_receipt=read(LOCAL/'A1/stage_receipt.json'),
        cause='Inherited stage_worker default Windows text decoding did not decode UTF-8 source paths',
        repair='PYTHONUTF8=1 environment for child and parent; no old solver or authority file edited',
        original_solver_calls=0,rerun_parameter_sweep=False,evidence=[rec(p) for p in (LOCAL/'A1').glob('*') if p.is_file()]))
    src=[TRAIN,OUT/'PREREGISTRATION.json',OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json',OLD/'RUNTIME_RESERVE_CALIBRATION.json',
        OLD/'RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv',OLD/'CC4_EXECUTION_LAG_KERNEL.csv',OLD/'CC4_FORECAST_DEPLETION_LEDGER.csv',
        ROOT/'docs/v42_may01_native_canary/MAY01_CC4_P2_BINDING.json']
    src += list((ROOT/'v42_temporal').glob('*.py'))+[ROOT/'v42_native/temporal_worker.py',ROOT/'tests/test_v42_temporal.py']
    dump('SOURCE_MANIFEST.json',dict(PASS=True,files=[rec(p) for p in src],base=BASE,
        inherited_transitive_native_source_manifest=rec(ROOT/'docs/v42_may01_native_canary/SOURCE_MANIFEST.json'),
        calibration_or_training_calls=0,May_outcome_reads=0))
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()],
        primary_stage_directory=str(folder),portable_native_reproduction_requires_local_sources=True))
    tests=[]
    for name in ('temporal_tests.xml','regression_tests.xml'):
        tree=ET.parse(LOCAL/name);s=tree.getroot().find('testsuite')
        tests.append(dict(file=name,tests=int(s.attrib['tests']),failures=int(s.attrib['failures']),errors=int(s.attrib['errors']),
            skipped=int(s.attrib.get('skipped',0)),seconds=float(s.attrib['time'])))
    require(all(r['failures']==r['errors']==r['skipped']==0 for r in tests),'TEST_FAILURE')
    dump('VERIFICATION.json',dict(PASS=True,test_suites=tests,tests_passed=sum(r['tests'] for r in tests),
        legacy_files_byte_preserved=len(preserved),legacy_tracking_diff_empty=True,
        no_final_response_kernel=not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),
        native_model_solve_verified=False,native_plan_accepted=False,
        warning='One inherited frozen calibration numpy log1p RuntimeWarning; test passes; provider left unchanged',
        scientific_scope='Unit/regression and necessary-condition witness verification; not native feasibility or Fresh AC'))
    answers=[
        '아니다. Runtime, CC4, TS, CC4 timing 모두 새 ML 학습은 FALSE이다.',
        '정확 cohort와 W>age 조건이 support를 줄였다. 이번 PENDING age는 120,931~291,228초이고, L4에서도 N_cond가 3/8/50뿐이라 단순 세분화만이 원인은 아니다.',
        'L0=qos/protected/partition/workload_class/gpu_bucket/wall_bucket/requested_nodes; L1은 nodes 제거, L2는 partition 제거, L3은 workload_class 제거, L4는 gpu_bucket 제거이다. L4 이후 backoff는 없다.',
        '합치지 않았다. 모든 level에 QoS와 protected가 남고 high/urgent/protected는 fail-closed이다.',
        '최소 N_cond=100이다. W>age를 만족하는 TRAIN 관측만 센다.',
        '0/1,605건, 0%이다.',
        '0/10,582.75 nominal reserved GPUh, 0%이다.',
        '선택된 level이 없다. 1,395건 모두 L4까지 조회했지만 support에 실패했다.',
        '1,395건이다. 다른 210건은 state/protection 경계에서 제외됐다. age-cap 실패는 0건이다.',
        '아니다. 결과는 여전히 TS=0이며 preregistered rule을 결과 확인 뒤 바꾸지 않았다.',
        '사용하지 않았다. Runtime>=15min도 standby shortcut도 없다.',
        'CC4 ML과 B0/C0 Q50/Q90 forecast 값은 변경하지 않았다.',
        '버리지 않았다. 기존 6,729-slot kernel의 bytes/mass를 그대로 보존했다.',
        '고정 equality 대신 비음수 x[h,t], 누적 Q10/Q90 envelope, work conservation, carryout과 soft L1 reference-deviation을 사용한다.',
        'GPUh이다. 15분 slot GPU는 GPUh/0.25이다.',
        '각 cohort마다 active x의 합+carryout=remaining W50이다. 저장된 LP witness에서도 검증했다.',
        '보존한다. 24:00은 전기 평가 경계이며 workload completion deadline이 아니다.',
        '기존 kernel과 동일한 fold1 TRAIN parquet에서 완료된 submission-hour cohort 3,748개의 정확 GPU-second overlap CDF를 계산했다. 불완전 21개와 zero-work 4개를 제외했다. lag별 observed support만 사용했다.',
        '사용자가 지정한 단 하나의 preregistered Q10/Q90이다. 다른 폭을 시험하지 않았다.',
        'May outcome을 사용하지 않았다. May 입력은 이미 알려진 issue metadata와 기존 forecast만 읽었다. VALID tuning도 없다.',
        '없다. 지원 lag의 모든 cumulative lower/upper bound가 선형 제약이다.',
        'P1 grid security와 P2 reserve shortfall 다음, 기존 migration/shift/placement/tie 이전이다.',
        'TS는 이미 제출된 개별 PENDING job의 empirical 추가 대기 budget이다. CC4는 아직 개별 identity가 없는 anonymous aggregate GPUh의 서비스 시점이다.',
        '유지한다. DeltaW=max(W90-W50,0)을 별도 동일 envelope timing target으로 다룬다. reserve는 IT load가 아니다.',
        '유지한다. ForecastBook을 수정하지 않았고 제출마다 한 번만 감소하며, explicit job과 중복 계산하지 않는다. 현재 자료는 D-1 initial ledger이며 event replay 완료 주장은 없다.',
        'V10 T3 Isotonic Q50 provider와 기존 파일 모두 그대로이다.',
        'gamma90=2.423057443558147 그대로이다. 기존 CAL 약90.01%, fold5 약91.24% 검증값을 다시 보정하지 않았다.',
        '780 GPU 그대로이다. capacity scaling, gang 완화, job drop은 없다.',
        '795.2690276>780의 PR96 05:00 증거는 byte-preserved이다. 새 receipt에만 SUPERSEDED_BY_TS_AND_CC4_TEMPORAL_FLEXIBILITY_INTERFACE라고 표시했다.',
        '독립 slot 하한의 최댓값은 2025-05-01 23:45 AEST, Dday slot95/issue slot119이다.',
        '해당 slot known GPU lower bound는 509이다.',
        '해당 slot의 minimum anonymous CC4 GPU는 0이다. 이 개별 slot 최소가 모든 slot에서 동시에 성립한다는 뜻은 아니며 별도 joint LP를 통과했다.',
        'TS relief는 0 GPU이다.',
        '최대 necessary lower bound는 509 GPU이다.',
        '진단용 하한은 780 이하이고 joint necessary LP도 PASS이다. full native feasibility를 뜻하지 않는다.',
        'reserve=0으로 명시한 diagnostic relaxation은 PASS이다. full A1 adapter에는 실제 Runtime/CC4 Planning reserve target과 P2 shortfall을 유지했다.',
        '필요조건 PASS에 따라 A1 실행이 authorized되었다.',
        f'A1 worker를 실행했다. 그러나 600초 bounded complete-option 생성에서 중단되어 full model과 optimize()는 실행 완료되지 않았다. 종료={stopped}.',
        'A1 accepted incumbent가 없어서 M1/A2/M2는 NOT_RUN이다. 단계 순서를 건너뛰지 않았다.',
        f'A1 partial build wall={receipt["total_wall_seconds"]:.6f}초. solve time/gap/bound/nodes/최종 binary·continuous·presolved size는 null이다. 마지막 관측은 {progress.get("jobs_completed")} / {progress.get("jobs_total")} jobs, retained options {progress.get("retained_options")}; 미완료 job의 수를 최종 총수로 해석하지 않는다.',
        'Fresh OpenDSS AC는 NOT_RUN이다. accepted four-stage plan이 없다.',
        '최종 response kernel을 만들거나 freeze하지 않았다. FINAL_RESPONSE_KERNEL_AUTHORITY.json은 없다.',
        '테스트와 necessary LP witness에서 conservation violation은 없다. 아직 native accepted plan의 전역 conservation 완료를 주장하지 않는다.',
        '새 통계는 TRAIN만 사용했다. May future outcome read는 없고, 기존 retrospective case-study authority의 한계를 그대로 유지한다.',
        '없다. TS 비율, envelope 폭, gamma, capacity를 결과에 맞춰 조정하지 않았다.',
        'TS hierarchy audit, TRAIN timing-envelope construction, linear service/carryout/deviation interface, 새 necessary-condition 판정과 legacy preservation 하위 문제를 닫았다. 전체 native execution은 아니다.',
        'Problem 3을 end-to-end CLOSED라고 판단하지 않는다. 개별/aggregate 시간 유연성 interface는 구현됐지만 native accepted schedule이 없다.',
        'Problem 8도 end-to-end CLOSED가 아니다. MESS/전력/AC를 포함한 accepted 실행 검증이 남아 있다.',
        'Problem 10은 후보 생성의 bounded failure wall을 측정했다. native optimizer runtime/gap와 전체 A1/M1/A2/M2 scalability는 아직 측정할 수 없다.',
        f'다음 blocker는 {blocker}이다. 기존 complete-option 생성이 600초 안에 완료되지 않는다. 이는 새 resource infeasibility 증명이 아니다. 추가 rescue나 solver sweep 없이 중단했다.'
    ]
    require(len(answers)==50,'KOREAN_REVIEW_50')
    (OUT/'FINAL_REVIEW_KO.md').write_text('# V42 TS / CC4 temporal refinement 최종 검토\n\n'+'\n\n'.join(f'{i}. {a}' for i,a in enumerate(answers,1))+'\n',encoding='utf8')
    print(dict(blocker=blocker,tests=sum(r['tests'] for r in tests),preserved=len(preserved)))

if __name__=='__main__':main()
