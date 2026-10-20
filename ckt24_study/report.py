"""Publish measured preflight evidence and explicit unexecuted study gates."""
from .preflight import *
from .traffic import readcsv
from .gates import REQUIRED,admit
import subprocess

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf8').strip()

def report():
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    audit=json.loads((DOC/'ORIGINAL_CKT24_NETWORK_AUDIT.json').read_text())
    summary=json.loads((DOC/'ORIGINAL_BASELINE_SUMMARY.json').read_text())
    spatial=json.loads((DOC/'SPATIAL_SCREENING_STATUS.json').read_text())
    sensitivity=readcsv(DOC/'MESS_PQ_CONTROLLABILITY.csv')
    null=json.loads((DOC/'AC_NULL_PERTURBATION_CHECK.json').read_text())
    grouped={}
    for r in sensitivity:
        grouped.setdefault(r['bus'],{})[('P' if float(r['p_kw']) else 'Q','+' if float(r['p_kw'])+float(r['q_kvar'])>0 else '-')]=r
    quality=[]
    for bus,rr in grouped.items():
        row=dict(bus=bus,empirical_null_floor=null['max_abs_observed_null_delta'],not_a_controllability_certificate=True)
        for axis,step in [('P',30),('Q',25)]:
            plus,minus=rr[axis,'+'],rr[axis,'-']
            row[axis+'_central_derivative']=(float(plus['rho'])-float(minus['rho']))/(2*step)
            row[axis+'_center_offset']=(float(plus['rho'])+float(minus['rho']))/2-float(plus['base_rho'])
            row[axis+'_min_signal_to_empirical_null']=min(abs(float(plus['delta_rho'])),abs(float(minus['delta_rho'])))/max(null['max_abs_observed_null_delta'],1e-15)
        quality.append(row)
    csvout('FINITE_DIFFERENCE_QUALITY.csv',quality)
    core_paths=['v44/config.py','v44/q250_m4_v2.py','v44/science.py','v44/inputs.py','v44/initial_states.py',
                'v42_native/mess.py','v42_may_campaign_native90/traffic.py','v42_may_campaign_native90/m_model.py',
                'v43_actual/planning_reference.py','v44/frozen/v43_mess/library.py']
    core=[]
    for p in core_paths:
        original=subprocess.check_output(['git','show',FROZEN+':'+p],cwd=ROOT)
        actual=(ROOT/p).read_bytes()
        # The Git checkout may apply its tracked EOL policy, never executable edits.
        core.append(dict(path=p,git_blob_sha=git('rev-parse',FROZEN+':'+p),working_sha256=sha(ROOT/p),
            content_equal_after_EOL_normalization=actual.replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n')))
    save('SOURCE_AND_POLICY_FREEZE.json',dict(UTC=now,r043_algorithm_commit=FROZEN,
        study_source_commit=git('rev-parse','HEAD'),study_branch=git('branch','--show-current'),
        worktree=str(ROOT),runtime=str(RUNTIME),date='2025-05-01',evaluation_slots=96,dt_seconds=900,
        inherited_prefix_slots=24,inherited_execution_slots=120,
        objective='min whole-network maximum line/phase current divided by original NormAmps; includes MV/LV/Other_Feeders',
        policy_authority='Applied v44/q250_m4_v2.py overlay takes precedence over stale base config call cap',
        A1_A2_native_seconds=5400,A_gap=.005,A_threads=1,K48_native_seconds=300,
        Joint_native_seconds=900,Joint_single_call_cap_seconds=300,M_gap=.03,M_threads=4,Root_Method=2,
        P_kw=300,Q_kvar=250,PCS_kva=400,PCS_faces=16,SOC_initial=760,SOC_minimum=440,SOC_maximum=1080,SOC_terminal=760,
        charge_efficiency=.95,discharge_efficiency=.95,desired_vehicle_count=8,AIDC_count=12,service_count=24,
        inherited_feasibility_and_integrality_tolerances_changed=False,
        AC_numerical_tolerance=1e-10,AC_tolerance_scope='Independent finite-difference engine only; strengthened, not relaxed',
        B3_A1_policy='NEW_CKT24_B1_SAME_DAY_SAME_SOURCE_SHA_ONLY',legacy_A1_checkpoint_LB_UB_imports=0,
        production_modules_imported_by_study=False,production_registry_or_scheduled_tasks_updated=False,
        core_sources=core,code_manifest=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'ckt24_study').glob('*.py'))],
        inherited_external_M_algorithm_manifest='docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json',
        actual_voltage_policy='ORIGINAL_CKT24_CONTROL_DEFINITIONS; V44 Known/Unknown and TIME Actual adapter not implemented; SVR12 not copied'))
    hardcodes=[('v44/inputs.py',49,'Four-unit input shape rejection'),('v44/initial_states.py',22,'Four initial service IDs'),
        ('v42_may_campaign_native90/traffic.py',146,'Exactly four initial units required'),
        ('v42_may_campaign_native90/m_model.py',539,'Model size metadata units=4'),
        ('v42_may_campaign_native90/operations.py',63,'Four-unit result array IDs'),
        ('v43_actual/planning_reference.py',63,'Actual zero-MESS reference units=4'),
        ('v44/svr11_forecast_parallel.py',47,'Four-unit initial placement guard'),
        ('v44/svr11_frozen/v42_voltage_control/authority.py',231,'Hardware four-unit roster guard')]
    csvout('MESS8_HARDCODE_AUDIT.csv',[dict(file=f,line=n,finding=t,status='NOT_CHANGED_PENDING_VALID_SCENARIO_AND_INTEGRATION') for f,n,t in hardcodes])
    save('MODEL_SIZE_AND_EQUIVALENCE.json',dict(status='NOT_BUILT',vehicle_target=8,original_vehicles=4,
        Native0_FULL_verified=False,Compact_verified=False,projection_verified=False,independent_FULL_replay_verified=False,
        variables=None,constraints=None,nonzeros=None,peak_RAM=None,
        core_source_identity=all(r['content_equal_after_EOL_normalization'] for r in core),
        same_8vehicle_mathematics_certified=False,
        source_audit='Original solve iterates sorted(initial_sites.items()); wrapper and Actual hardcodes still require integration',
        reason='No physical PCC freeze, valid complete B0, or port/transformer interface authority. No mock solver PASS.'))
    mess=dict(status='VIRTUAL_ELECTRICAL_RESPONSE_ONLY',candidate_count=len(sensitivity)//4,
        actual_8_vehicle_SOC_route_feasibility=False,physical_PCC_ports_certified=False,
        best_delta_rho=min(float(r['delta_rho']) for r in sensitivity),
        worst_delta_rho=max(float(r['delta_rho']) for r in sensitivity))
    save('JOINT_CONTROLLABILITY_REPORT.json',dict(UTC=now,
        MESS_CONTROLLABILITY_VERIFIED=False,AIDC_CONTROLLABILITY_VERIFIED=False,JOINT_CONTROLLABILITY_VERIFIED=False,
        instantaneous_virtual_MESS=mess,
        AIDC='Actual descriptor permissions counted; no feasible changed schedule and Ckt24 AC witness',
        joint='NOT_TESTED; individual finite differences are not summed into a joint certificate'))
    csvout('AIDC_CONTROLLABILITY.csv',[dict(aidc_id=f'AIDC{i:02}',virtual_load_sensitivity='P injection sign reversal in MESS_PQ_CONTROLLABILITY.csv',
        actual_job_schedule_witness=False,deadline_GPU_WAN_checkpoint_replay=False,AC_schedule_replay=False,
        status='NOT_VERIFIED') for i in range(1,13)])
    save('MESS8_INITIAL_PLACEMENT.json',dict(status='NOT_FROZEN',vehicle_ids=[f'MESS{i:02}' for i in range(1,9)],
        initial_sites=None,initial_SOC_kWh=760,reason='Do not infer port availability from a three-phase MV bus. No certified physical PCC freeze.',
        new_service_sites_created=0,STAY_or_MOVE_forced=False))
    gates={name:dict(status='NOT_RUN') for name in REQUIRED}
    for name in ['Original Network','Traffic','Site Counts']:gates[name]=dict(status='PASS')
    gates['Spatial']=dict(status='PROVISIONAL',drawing_order=spatial,geographic_coordinate_meaning='NOT_VERIFIED')
    gates['PCC']=dict(status='NOT_VERIFIED',reason='Voltage and phases inventoried; physical PCC ratings, port capacity and branch dispersion not certified')
    gates['Baseline AC']=dict(status='NOT_PASSED',reason='Original/background-only scenarios violate voltage/transformer criteria; complete AIDC B0 is not built',
        original_static_summary=summary)
    gates['MESS8']=dict(status='NOT_BUILT')
    gates['AIDC']=dict(status='INPUT_AUDITED_ONLY')
    gates['MESS Sensitivity']=dict(mess,status='ELECTRICAL_SURVEY_ONLY')
    gates['AIDC Sensitivity']=dict(status='NO_ACTUAL_JOB_WITNESS')
    gates['Model Identity']=dict(status='SOURCE_AUDITED_MODEL_NOT_BUILT')
    gates['Source']=dict(status='PASS',sha=git('rev-parse','HEAD'))
    save('PRE_SOLVER_GATES.json',gates)
    try:admit(gates,'2025-05-01')
    except RuntimeError as exc:blocked=str(exc)
    else:raise RuntimeError('REPORT_MUST_NOT_DISPATCH_AN_UNBUILT_MODEL')
    csvout('MAY01_B0_B3_FINAL_RESULTS.csv',[dict(day='2025-05-01',arm=arm,status='NOT_RUN_PRE_SOLVER_GATES',
        final_UB='',final_LB='',gap='',Actual96_PASS=False,Fresh96_PASS=False,reason=blocked,
        source_sha=git('rev-parse','HEAD'),UTC=now) for arm in ['B0','B1','B2','B3']])
    old=ROOT/'docs/v44/r043_release_20261019/completed_results/2025-05-01'
    original_results={a:json.loads((old/a/'RESULT.json').read_text()) for a in ['B0','B1','B2','B3']}
    save('IEEE123_MAY01_REFERENCE_RESULTS.json',dict(scope='Historical comparison only, not Ckt24 seeds',results=original_results))
    rows=[('bus_count','NOT_RECOUNTED',audit['buses']),('electrical_nodes','NOT_RECOUNTED',audit['nodes']),
          ('MESS',4,8),('AIDC',12,12),('service_sites',24,24),('variables','NOT_EXTRACTED','NOT_BUILT'),
          ('constraints','NOT_EXTRACTED','NOT_BUILT'),('nonzeros','NOT_EXTRACTED','NOT_BUILT'),('peak_RAM','NOT_EXTRACTED','NOT_MEASURED')]
    for stage in ['A1','M1','A2','M2']:rows.append((stage+'_native_wall','NOT_EXTRACTED','NOT_RUN'))
    rows.extend([('UB_LB_gap','SEE_HISTORICAL_RESULTS_M_GAP_FALSE','NOT_RUN'),('Actual_Fresh','COMPLETED_MAY01','NOT_RUN')])
    csvout('SCALABILITY_COMPARISON_IEEE123_CKT24.csv',[dict(metric=m,IEEE123_r043=a,Ckt24_May01=b,
        interpretation='Grid size and vehicle count both change; not a pure grid-node scalability experiment') for m,a,b in rows])
    text=f'''# Ckt24 r043 May01 사전 검증 결과

작성 UTC: {now}. 요청한 B0/B1/B2/B3 및 8대 FULL/Compact/Actual/Fresh 최종 검증은 **미완료**다. 실행 전 Gate를 통과하지 못하여 A1/M1/A2/M2를 시작하지 않았다. 이 PR은 이식 완료나 확장성 성공 인증이 아닌 재현 가능한 사전 조사와 중단 근거다.

## 동결·격리

알고리즘 기준은 `{FROZEN}`이며 별도 Worktree `{ROOT}`와 Runtime `{RUNTIME}`를 사용했다. 기존 r044 이후 코드·운영 Worker·Monitor·원장·예약 작업을 수정하거나 중지하지 않았다. 소스의 기존 절대경로 기반 dispatcher를 호출하지 않았다. IEEE123 A1/UB/LB/Checkpoint를 Ckt24로 가져오지 않았다.

EPRI SVN r4176의 원본 파일 {len(json.loads((DOC/'ORIGINAL_DSS_SHA256_MANIFEST.json').read_text())['files'])}개를 SHA-256으로 봉인했다. master는 스스로 전체 실행을 금지하는 복수 A-Diakoptics 예제를 포함하므로, 별도 adapter에서 계통 정의 prefix만 읽고 경로를 절대경로로 해석했다. 선로·변압기·부하·RegControl·정격은 변경하지 않았다. 원본 Ckt24에는 PV가 없고 RegControl은 {audit['regcontrols']}개다. IEEE123의 7개 RegControl이나 SVR12를 복사하지 않았다. SVR12 배치·연속접속·권선 검증은 수행되지 않았으므로 적용할 수 있다고 인증하지 않는다.

## 실제 측정

원본은 {audit['buses']:,} buses, {audit['nodes']:,} 전기 노드, {audit['lines']:,} 선로, {audit['transformers']:,} 변압기다. MV buses {audit['mv_buses']:,}, LV buses {audit['lv_buses']:,}. 원본 좌표가 있는 bus는 {audit['buses_with_coordinates']:,}개다. 좌표가 없는 LV bus의 XY를 생성하지 않았다. 도면은 원본 좌표를 가진 연결만 표시하며 전체 AC에는 모든 설비를 포함했다. 원본 buscoords의 GIS CRS·단위·지리적 의미는 다운로드 폴더에서 확인되지 않아 실제 GIS 위치 보존을 인증하지 않는다.

원본 8760시간 shape에 May01(연중 시간 2880–2903.75)을 대응시켰다. 이는 원본 shape를 2025년 실측 자료라고 주장하는 것이 아니다. 15분 시작 시각 96개에서 모든 bus/상 전압, 양단 선로/상 전류, 변압기 각 권선 kVA/전류 및 원본 제어 상태를 추출했다. `ORIGINAL_BASELINE_*`와 요청 이름을 따른 `B0_MV_LV_BOTTLENECKS.csv`는 **AIDC가 아직 포함되지 않은 원본 배경망 진단**으로, 공식 B0 결과가 아니다.

원본 제어를 동작시킨 순차 진단: 최대 부하율 {summary['rho_max']:.9f}, 전압 {summary['v_min']:.9f}–{summary['v_max']:.9f} pu, 최대 변압기 부하 {summary['max_transformer_loading']:.9f} pu. 변압기 초과 {summary['transformer_overload_slots']}/96슬롯, 전압 범위 초과 {summary['voltage_violating_slots']}/96슬롯이다. 원본 master처럼 controls off인 경우와 static인 경우를 모두 별도 비교했다.

낮의 지배 선로는 원본 `Other_Feeders`다. 이는 SubXfmr_LSB에서 `Feeders` 등가 부하로 이어지는 가지다. LV 선로나 이 가지를 목적함수에서 제외하거나 정격을 높이지 않았다. static 주간 최대 서비스 변압기는 `05410_g2100nj7400`이며 과부하를 숨기지 않았다.

배경부하 후보 1.0·0.75·0.5를 AC와 B3 실행 전에 등록했다. AIDC/GPU/Job/PCS/PV/정격은 스케일하지 않았다. 배경망 단독 검사에서 어느 후보도 전압·전류·변압기 조건을 동시에 통과하지 못했으므로 최종 시나리오를 선정하지 않았다. 이것을 모든 가능한 AIDC 배치의 불가능성 증명으로 해석하면 안 된다. 완전한 B0와 실제 Job/전력 모델 검증은 별도로 남아 있다.

## 교통·공간·제어 가능성

교통 서비스 24개(IDC12+STA12), 48개 교통 노드, 509개 Link 및 May01 Route Table 55,296개 경로를 확인했다. Route/Forecast는 r043 SHA와 일치하고, SUMO 원본 junction에서 XY를 직접 읽었다. 경로·ETA·에너지·connection-ready·서비스 ID를 재생성하지 않았다. `IDCnn → AIDCnn`은 원래 workload와의 명시적 별칭이며 순서를 바꾸지 않았다. 전력망–교통망은 합성적 거점 대응이며 동일 GIS 위치라는 주장이 아니다.

380개 원본 좌표 보유 MV 3상 bus에서 P ±30 kW / Q ±25 kvar의 독립 Fresh AC를 계산했다. 이는 가상 MV 주입 포트의 순간 응답이며 포트 설치·변압기·PCS 접속·SOC·경로·Job의 운전 가능성 인증이 아니다. 전체 최대 부하율과 Top20 각각의 부하율 변화, 전압 극값, 변압기 부하를 기록했다. 최상 delta rho는 {mess['best_delta_rho']:.9g}, 최악 delta rho는 {mess['worst_delta_rho']:.9g}다. Top20은 기본 혼잡 집합과 전체 max 변화를 함께 기록한다.

무교란 0 kW / 0 kvar 포트 추가에서도 최대 {null['max_abs_observed_null_delta']:.9g} pu의 차이가 관측됐다. 이는 엄밀한 오차 상한이 아닌 경험적 수치 바닥이다. 원본 `Other_Feeders`의 R1=1e-8, X1=1e-9 ohm은 수치 조건을 주의해야 하는 요소이며, 원인 확인을 위해 원본 임피던스를 변경하지 않았다. 작은 응답의 신호/무교란 비와 중앙 유한차분을 `FINITE_DIFFERENCE_QUALITY.csv`에 함께 기록했고, 약한 P 응답을 인증으로 승격하지 않았다.

공간 screening: `{spatial}`. 모든 관계는 원본 X/Y축에서 검산하며 .01m Traffic 공차와 .01 원본 Ckt24 좌표 단위 공차를 먼저 고정했다. Mapping이 존재해도 물리적 PCC freeze가 아닌 **원본 도면 순서의 잠정 witness**다. branch 분산·실제 PCC 정격·포트 수가 인증되지 않아 최종 배치로 사용하지 않았다. 원본 정격을 만족하는 8대 초기 위치도 동결하지 않았다.

원본 Job descriptor와 12개 GPU 용량 및 전력 권한을 보존했다. descriptor의 Timeshift/Migration 권한은 실제 feasible schedule이 아니다. 실제 Job 변경→P/Q→Ckt24 AC witness가 없으므로 AIDC 및 Joint controllability는 false다. 가상 AIDC 부하 응답은 P 주입 부호를 반대로 해석할 수 있지만 실제 부하 감축 가능량으로 인증하지 않는다.

## 남은 필수 작업과 결과 해석

8대 Native0/FULL/Compact/Projection/독립 Replay, Ckt24 전기 계수와 실제 AIDC 기준 B0, 유효 PCC/포트 정격, branch 분산, 실제 Job 스케줄 기반 제어 가능성, 원본 Ckt24 설비 기반 TIME Actual adapter가 남아 있다. 차량 4 고정 위치는 `MESS8_HARDCODE_AUDIT.csv`에 기록했으며 수학적 동등성을 검증하지 않고 고쳤다고 주장하지 않았다. 따라서 기존 B0/B1/B2/B3 dispatcher에 이 실험을 연결하지 않았다.

`MAY01_B0_B3_FINAL_RESULTS.csv`의 네 행은 모두 NOT_RUN이며 UB/LB/Gap은 빈 값이다. TIME_LIMIT, FULL 가능해, Gap 인증, Actual/Fresh PASS를 생성하지 않았다. 개별 전기 민감도 합을 공동 효과로 보고하지 않았다. 최종 비교·계산시간·실제 AIDC 제어 heatmap은 측정이 없어 생성하지 않았다.

기존 r043 May01 최종 결과는 비교용으로만 별도 보존했다. 기존 B2/B3의 M_gap_certified=false도 유지했다. Ckt24 계통 규모와 차량 수가 함께 달라지므로 향후 성공해도 순수 계통 노드 수만의 scalability 실험이 아니다.

실행 명령과 파일 범위는 `README.md`, 각 Gate는 `PRE_SOLVER_GATES.json`, Raw 파일 경로·SHA는 `RAW_AC_RECEIPTS.json` 및 `SENSITIVITY_RAW_RECEIPT.json`에 있다. 원본 파일과 core source를 임의 수정하지 않고 모든 Gate를 다시 통과한 후에만 새 Ckt24 B1 A1부터 계산해야 한다.
'''
    (DOC/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
    print(blocked)

if __name__=='__main__':report()
