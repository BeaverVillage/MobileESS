"""Read-only status/accounting; no DSS solve or policy solver execution."""
from .run_ac import REPORT,HIGH,ROOT,read,write,receipt,rows,table,DAY


def run():
    ledger=read(REPORT/'EXECUTION_REUSE_LEDGER.json')
    # M3 was computed during the resume, then its Planning record was aliased.
    # Repair the earlier summary overwrite using the preserved completion receipt.
    tag='C2_M3_SCHEDULE_PLANNING'
    if ledger[tag].get('new_operating_point_solves',0)==0:
        r=read(REPORT/'ac'/tag/'RECEIPT.json')
        ledger[tag].update(status='COMPLETED',new_operating_point_solves=96,runtime_seconds=r['runtime_seconds'],
            summary_correction='completed in May01 resume then aliased into final Planning; no repeat AC')
        write(REPORT/'EXECUTION_REUSE_LEDGER.json',ledger)
    new=[v for v in ledger.values() if v['status']=='COMPLETED']
    old=[v for v in ledger.values() if v['status']=='REUSED']
    finite=read(REPORT/'precheck/RECEIPT.json')
    reused=[('PR197 Balanced topology/ratings/P5/Balanced96',ROOT/'docs/ieee8500_v42_balanced_case/INDEPENDENT_VERIFICATION.json'),
        ('May01 original Job/GPU-h/C1/facility recomputation',HIGH/'AIDC_CAPACITY_RECOMPUTATION_RECEIPT.json'),
        ('Completed QoS/hardware review',HIGH/'AIDC_FLEXIBILITY_QOS_RECEIPT.json'),
        ('Completed MV interface/source eligibility audit',HIGH/'MV_ORIGINAL_SOURCE_PRESERVATION.json'),
        ('Existing fixed-AIDC impossibility scope proof and joint witness',HIGH/'JOINT_MV_TRAFFIC_ETA_AUDIT.json'),
        ('1783 candidates x7 May01 sensitivity',REPORT/'MAY01_SENSITIVITY_EXECUTION_REUSE.json'),
        ('Selected C2 direction/dispersion/source paths',REPORT/'SELECTION_SOURCE_IMMUTABILITY_RECEIPT.json')]
    tasks=[dict(task=n,status='REUSED',evidence=receipt(p)['sha256'],new_DSS_operating_points=0) for n,p in reused]
    tasks.extend(dict(task=t,status=v['status'],evidence=v['receipt']['sha256'],
        new_DSS_operating_points=v.get('new_operating_point_solves',0)) for t,v in ledger.items())
    tasks.extend([dict(task='Selected physical finite P/Q AC',status='COMPLETED',evidence=receipt(REPORT/'precheck/RECEIPT.json')['sha256'],new_DSS_operating_points=193),
        dict(task='Nonzero AIDC QoS/WAN/checkpoint policy',status='BLOCKED',evidence='NOT_CERTIFIED; same original May01 population retained',new_DSS_operating_points=0),
        dict(task='Field GIS/port protection/actual ETA Production promotion',status='BLOCKED',evidence='UNVERIFIED; engineering case only',new_DSS_operating_points=0),
        dict(task='B1/B2/B3 long Production solvers',status='BLOCKED',evidence='explicit human prohibition; not a feasibility result',new_DSS_operating_points=0)])
    table(REPORT/'EXECUTION_TASK_STATUS.csv',tasks)
    operating=sum(v.get('new_operating_point_solves',0) for v in new)+193
    seconds=sum(v.get('runtime_seconds',0) for v in new)+finite['runtime_seconds']
    result=dict(day=DAY,May02_new_joint_AC=0,May02_records='preserved excluded',completed96_reused=len(old),
        new_completed96_cases=len(new),new_completed96_operating_points=96*len(new),
        new_finite_operating_points=193,new_completed_operating_point_Solution_Solve_calls=operating,
        explicit_initialization_Solution_Solve_calls=2*(len(new)+1),
        known_completed_explicit_API_Solve_calls=operating+2*(len(new)+1),
        DSS_internal_network_iterations_or_CalcVoltageBases_solves='not instrumented; not included in explicit API count',
        interrupted_prior_runner_unknown_operating_points='0..95, preserved incomplete May01 M2; excluded from known completed count',
        new_recorded_AC_runtime_seconds=seconds,finite_runtime_is_filesystem_approximation=True,
        avoided_completed96_replays=len(old),avoided_candidate_sensitivity_operating_points=49931,
        avoided_PR197_and_prior46_replays=True,avoided_QoS_and_eligibility_and_geometry_reruns=True,
        new_lightweight_date_resume_tests=6,new_lightweight_test_PASS=True,
        all_older_test_results='REUSED; not rerun',Native_or_long_policy_Solver_calls=0,
        own_diagnostic_runner_processes_stopped=2,other_campaign_processes_stopped=0,other_campaign_writes=0,
        endpoint_raw_readback_detail='UNAVAILABLE serialization error; numeric CSV retained; zero recovery solves')
    write(REPORT/'EXECUTION_EFFICIENCY.json',result)
    (REPORT/'EXECUTION_EFFICIENCY_KO.md').write_text(
        f'# May01 전용 실행·재사용 기록\n\n연구 날짜는 {DAY} 96슬롯이다. May02 기록은 SHA로 보존하고 제외했다.\n\n'
        f'완료96슬롯 {len(old)}건을 재사용했다. 신규 {len(new)}건(각96슬롯)과 선택된 PCC의 유한 P/Q 반사실193회를 계산했다. '
        f'완료 운전점 Solve는 {operating}회, 명시적 초기화 Solve까지 {operating+2*(len(new)+1)}회이며 Native/장시간 정책 Solver는0회이다. '
        f'기록된 AC 시간 합계는 {seconds:.2f}초다(반사실은 파일 타임스탬프 근사). '
        '중단된 이전 May01 M2 실행의 완료 슬롯 수는0–95 범위 미계측이며 이 완료 집계에서 제외했다. '
        'DSS 내부 반복·CalcVoltageBases 내부 해석 수는 계측하지 않았다.\n\n'
        '1,783후보×7시간대49,931회 민감도, 원본 모델 감사, 이전46케이스, 적격성·QoS·수학적 증명과 기존 회귀 테스트를 반복하지 않았다. '
        '신규 날짜·재개·계수 가드 테스트6개만 실행해 통과했다. 실제 새PCC의 19개 완료 케이스 저장 배열은 별도 검증했다.\n\n'
        '반사실190개와 기준3개는 계산을 마쳤지만 NumPy bool의 JSON 직렬화 오류로 개별 반사실 포트 readback 상세를 저장하지 못했다. '
        '수치 CSV와 실제 포트 제한 검사 요약은 보존했다. AC를 반복하지 않고 파일만 복구했다. 최종96슬롯의 포트 상세 파일은 완전하다.\n\n'
        '타 V42 캠페인 프로세스·입력·스케줄러는 변경하지 않았다. May02 자동 실행을 차단하기 위해 이 공동진단 실행기2개 프로세스만 중지했다. '
        'AIDC QoS와 현장 GIS·보호·접근성 자료는 BLOCKED/UNVERIFIED로 남겨 Production 승격을 차단한다.\n',encoding='utf-8')
    return result

if __name__=='__main__':run()
