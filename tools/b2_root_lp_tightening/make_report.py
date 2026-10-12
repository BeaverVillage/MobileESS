"""Korean BASE/GRID/SOC report from small preserved receipts; no solver/matrix.

All LP objective comparisons use the completed current BASE. Exact weak-dual
finite-box certificates are reported separately from native ObjVal/ObjBound.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction as F
from pathlib import Path
import argparse
import json
import math
import re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/v42_b2_root_lp_tightening'
UB=.6760534504652341
OLD=.46498486997548166
GIB=1024**3


def read(path,default=None):
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def n(value,places=10):
    if value is None:return '미확보'
    if isinstance(value,bool):return 'PASS' if value else 'FAIL'
    if isinstance(value,(float,int)) and math.isfinite(value):
        return f'{value:.6e}' if value and abs(value)<10**(-places) else f'{value:.{places}f}'
    return str(value)


def gib(value):return n(value/GIB,4) if value is not None else '미계측'
def cell(value):return str(value).replace('|','\\|').replace('\n',' ')
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(cell(v) for v in row)+' |' for row in rows])


def stage(out,kind):
    p=out/kind.lower()
    return dict(kind=kind,path=p,zero=read(p/'NATIVE0.json',{}),
                independent0=read(p/'INDEPENDENT_NATIVE0.json',{}),result=read(p/'RESULT.json',{}),
                cert=read(p/'INDEPENDENT_CERTIFICATE.json',{}),readback=read(p/'NATIVE_READBACK.json',{}),
                memory=read(p/'MEMORY_ADMISSION.json',{}),b1_trace=read(p/'B1_PRIORITY_TRACE.json',{}))


def generate(out=OUT):
    out=Path(out)
    summary=read(out/'FINAL_RESULT.json',{})
    runs=[stage(out,k) for k in ('BASE','GRID','SOC')]
    base=runs[0]['cert']
    diagnosis=read(out/'BASE_FRACTIONAL_DIAGNOSTICS.json',{})
    original_diagnosis=read(out/'SOC_BASE_FRACTIONAL_DIAGNOSTICS.json',{})
    separation=read(out/'grid/SEPARATION.json',{})
    gridcuts=read(out/'grid/CUTS_EXACT.json',{}).get('rows',[])
    gridcontrib=read(out/'grid/FRACTIONAL_GRID_CONTRIBUTIONS.json',{})
    socsep=read(out/'soc/SOC_FRACTIONAL_SEPARATION.json',{})
    soccuts=read(out/'soc/CUTS_EXACT.json',{}).get('rows',[])
    socproof=read(out/'SOC_INTEGER_VALIDITY_NATIVE0.json',{})
    socind=read(out/'INDEPENDENT_SOC_NATIVE0.json',{})
    soc_after=read(out/'SOC_AFTER_LP_CANDIDATE_DIAGNOSTICS.json',{})
    ledger=read(out/'NATIVE_LEDGER.json',{})
    pre=read(out/'PRE_RUN_RESOURCE_HOLD.json',{})
    post=read(out/'POST_RUN_RESOURCE_HOLD.json',{})
    history=read(out/'HISTORICAL_STRENGTHENING_AUDIT.json',{})
    gate_tests=read(out/'RESOURCE_GATE_TESTS.json',{})
    priority=read(out/'USER_PRIORITY_OVERRIDE.json',{})
    requested=sum(r.get('TimeLimit',0) for r in ledger.get('calls',[]))
    actual=[r['result'] for r in runs if r['result'].get('Native_optimize_calls')]
    complete=len(actual)==len(ledger.get('calls',[])) and all(r.get('Runtime') is not None for r in actual)
    runtime=sum(r['Runtime'] for r in actual) if complete else None
    wall=sum(r['optimize_wall_seconds'] for r in actual) if complete and all(r.get('optimize_wall_seconds') is not None for r in actual) else None
    adopted=[r['kind'] for r in runs[1:] if r['cert'].get('PASS') and r['cert'].get('candidate_material_LP_gain')]
    pending=[r['kind'] for r in runs[1:] if not r['result'].get('Native_optimize_calls')]
    classification=summary.get('classification','ROOT_LP_CANDIDATES_RESOURCE_PENDING' if pending else
                               'ROOT_LP_MATERIAL_CANDIDATE' if adopted else 'ROOT_LP_TIGHTENING_NONMATERIAL')
    valid=[r['cert']['LP_lower_bound'] for r in runs if r['cert'].get('PASS')]
    global_lb=summary.get('Global_LB',max([OLD]+valid))
    counts=diagnosis.get('fractional_counts',{})
    sim=[r for r in diagnosis.get('vehicle_slot_diagnostics',[]) if r.get('simultaneous_C_D')]
    now=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
    callback_times={}
    for run in runs:
        logfile=run['path']/'NATIVE.log'
        if logfile.exists():
            matches=re.findall(r'time in user-callback ([0-9.]+) sec',logfile.read_text(encoding='utf-8',errors='replace'))
            callback_times[run['kind']]=float(matches[-1]) if matches else None
    lines=[
      '# V42 B2 Root LP Tightening 최종 보고', '',
      f'작성 시각 {now} (Asia/Seoul). IEEE123 / B2 / 2025-05-01.', '',
      f'최종 판정: **{classification}**. 현재 완료·독립 인증된 BASE LP 목적값은 **{n(base.get("ObjVal"),16)}**, '
      f'exact weak-duality 하한은 **{n(base.get("LP_lower_bound"),16)}**이다. '
      f'후속 MIP 후보의 하한 개선 채택 기준 0.001을 충족한 후보는 **{", ".join(adopted) if adopted else "없음"}**이다. '
      f'누적 유효 Global LB는 **{n(global_lb,17)}**, 원본 검증 U4 UB 대비 Gap은 **{n(100*(UB-global_lb)/UB,8)}%**다.', '',
      f'새 Native는 {len(ledger.get("calls",[]))}회 / 최대 3회, 각 요청 최대 240초, 요청 예산 합 {requested}초 / 최대 720초다. '
      f'실제 Native Runtime 합 {n(runtime,6)}초, Optimize Wall 합 {n(wall,6)}초. '
      'Full MILP B&B·U4 변경·Production 통합·공식 5월 캠페인·IEEE8500·GRID+SOC 결합 실행은 0회다.', '',
      '## 1. Source·기준과 실제 BASE 확보', '',
      table(['기준','commit / 값','역할'],[
       ['PR211 정확한 부모','d12315a3757aec187c8da0685c28ef901466386a','K48 물리·Grid CSR/Domain 및 실행 증거 재사용'],
       ['Source18r 롤백 기준 / PR207','497609b46faa14ea7e32a9483a333ab32fd264ef','원본 FULL 물리·계통 coefficient Authority'],
       ['PR211 기존 Global LB',OLD,'과거 수치 MIP ObjBound 계약에 따른 검증값'],
       ['원본 검증 FULL U4 UB',UB,'모든 Global Gap의 유일한 UB'],
       ['현재 BASE Native 목적값',n(base.get('ObjVal'),16),'실제 numerical OPTIMAL 결과; 기존 숫자를 가정하지 않음'],
       ['현재 BASE exact weak-duality LB',n(base.get('LP_lower_bound'),16),'완료 LP Pi의 sign 및 finite-box stationarity 보정 하한'],
      ]), '',
      'PR211 실행에는 전체 Root fractional vector가 저장되지 않아 K48의 원본 행·RHS·Sense·Bounds·rho Objective를 그대로 복사하고 '
      '원래 9,322개 Binary만 C로 완화한 별도 BASE LP를 구성했다. 기존 route_flow는 원래 C였고 추가 물리 완화·열 삭제·Bounds 강화는 없다. '
      'LP는 실제 status=OPTIMAL(2)이며 Primal/Pi/RC를 저장해 독립 검증했다. '
      '중단 Barrier나 simplex 로그 목적값, IntInf만으로 벡터를 만들어내지 않았다.', '',
      '## 2. BASE 분수 운전 구조', '',
      table(['변수 Family','분수 개수 (1e−8 기준)','양의 값 개수'],[
       ['node_activity',counts.get('node_activity_fractional','미확보'),counts.get('node_activity_active','미확보')],
       ['charge_mode',counts.get('charge_mode_fractional','미확보'),counts.get('charge_mode_active','미확보')],
       ['route_flow',counts.get('route_flow_fractional','미확보'),counts.get('route_flow_active','미확보')],
      ]), '',
      f'차량·slot 단위에서 C와 D가 함께 양수인 경우는 {diagnosis.get("vehicle_slot_simultaneous_C_D","미확보")}개다. '
      f'같은 station에서 Pch/Pdis가 동시에 양수인 경우는 {diagnosis.get("same_station_simultaneous_C_D","미확보")}개다. '
      '이는 서로 다른 station의 분수 location과 하나의 분수 Mode가 허용한 aggregate C/D 섞임을 보여준다. '
      '분수 개수 감소 자체를 채택 근거로 삼지 않는다.', '',
      f'원래 에너지 행 최대 수치 잔차는 {n(diagnosis.get("energy_balance_maximum_residual"),12)}다. '
      '각 차량의 97개 SOC 경계와 원래 초기/종단 760 kWh를 inverse alias로 유지했다. '
      'retained node 이름만 집계하면 slot95의 alias된 node95→node96 상태가 빠질 수 있다. '
      'literal retained location 질량 0을 charging-in-transit의 증거로 해석하지 않는다. '
      'Original node/STAY 사영은 저장 Compact/alias 검증과 SOC 후보의 원본 route audit로 확인한다. '
      'travel 진단의 retained energy term 외에도 제거된 상수 alias의 이동 debit은 실제 행 RHS에 들어 있다. '
      '완전한 원본 departure debit은 SOC exact 후보의 원본 행 reconstruction에 보존했다.', '',
      f'`SOC_BASE_FRACTIONAL_DIAGNOSTICS.json`은 alias 역매핑 후 원본 384개 차량·slot의 '
      'SOC_before/after, C/D, departure T, Mode, STAY/move/transit 질량을 별도로 기록한다. '
      f'복원 원본 arc의 분수 개수 합은 {sum(u.get("original_fractional_arc_count",0) for u in original_diagnosis.get("units",[]))}개이며 '
      'retained route_flow 1,928개와 축이 다르다. '
      f'충전과 출발 travel debit이 함께 양수인 분수 slot은 {original_diagnosis.get("total_charge_departure_travel_simultaneous_vehicle_slots","미확보")}개다. '
      f'원본 energy Fraction replay 최대 잔차는 {n(original_diagnosis.get("maximum_original_energy_residual"),12)}다. '
      '이는 분수 운전 혼합의 진단이며 실제 정수 차량이 이동 중 충전했다는 주장이 아니다.', '',
      table(['MESS / slot','원본 C(kW)','원본 D(kW)','SOC 전 / 후(kWh)','Mode','STAY / depart-move / transit 질량'],[
       [f'{r["unit"]} / {r["slot"]}',n(r['C_kw'],6),n(r['D_kw'],6),
        f'{n(r["SOC_before_kWh"],6)} / {n(r["SOC_after_kWh"],6)}',n(r['charge_mode'],8),
        f'{n(r["stay_mass"],8)} / {n(r["departure_move_mass"],8)} / {n(r["transit_mass"],8)}']
       for r in original_diagnosis.get('slots',[]) if r.get('C_D_simultaneous')]), '',
      '세부 384개 차량·slot 에너지/C/D/Q/Mode/location/travel 기록은 `BASE_FRACTIONAL_DIAGNOSTICS.json`에 있다. '
      '어떤 분수값도 반올림·정수화하거나 Planning 가능해/Actual PASS로 승격하지 않았다.', '',
      '## 3. 후보 A: 실제 Fractional Root Grid Separation', '',
      f'원본 Security {separation.get("scan_original_security_rows","미확보")}행을 검사해 '
      f'{separation.get("candidate_count","미확보")}개 확인 탐색 후보에서 {len(gridcuts)}개만 선정했다. '
      '원본 injection/response/correction 정의를 저장 FULL CSR로 재구성하고 선정 행은 Fraction 기반 원본 Row SHA·Sense·RHS·Phase·축 대조를 통과한다. '
      '실행 전 BASE point SHA와 완료 인증, B1 안전/다른 Heavy Solver 부재를 확인한 후 FULL CSR에 접근했다. '
      'FULL CSR와 Native Solver model은 동시에 중복 상주시키지 않았다.', '',
      table(['Family','원본 행','누락 행','확인 탐색 후보','최대 원시 위반','미확정/0 부근'],[
       [fam,d['original_rows'],d['missing_rows'],d['screened_positive'],n(d['maximum_raw_violation']),
        separation.get('uncertainty',{}).get(fam,{}).get('count',0)] for fam,d in separation.get('families',{}).items()]), '',
      'thermal은 부하율 pu, voltage는 원본 squared-voltage pu², transformer는 kVA, NormalAmps는 전류 부하율 pu로 기록한다. '
      'Family 내부 분수 위반 순위가 우선이며, 동률은 원본 저장 coefficient의 P/Q L1 민감도 상한과 Row ID로 정한다. '
      '서로 다른 단위를 직접 비교하지 않는다. 민감도는 진단·tie-break이고 exact 계수 Authority를 대체하지 않는다. '
      '기본 quota 10 thermal+2 transformer+2 upper+2 lower에서 실제 transformer 위반이 없으면 정해진 순서로 quota를 보충한다. '
      '원본 기존 K48 행과 exact coefficient/RHS 중복은 제거하고, 실제 서로 다른 유효 행은 다양성만으로 영구 제외하지 않는다.', '',
      table(['원본 FULL Row ID / 이름','Asset / phase','Slot / facet','원시 위반','정규화 위반','정규화 민감도 상한'],[
       [f'{r["original_row"]} / {r["name"]}',f'{r["metadata"]["asset"]} / {r["metadata"]["phase"]}',
        f'{r["metadata"]["slot"]} / {r["metadata"]["facet"]}',n(r['raw_violation']),n(r['normalized_violation']),n(r['normalized_sensitivity'])]
       for r in gridcuts]), '',
      '각 critical row의 원래 signed P/Q 기여는 아래와 같다. P는 Pch/Pdis 두 항의 합이며 Q를 별도로 기록한다. '
      'fixed constant와 rho는 한 번씩만 계산하고, 정확한 signed 합이 Fraction violation과 같은지 검사했다. '
      '기존 K48 전 행과 신규 행의 MESS별 Pch/Pdis/Q 및 fixed/rho 분해는 `FRACTIONAL_GRID_CONTRIBUTIONS.json`에 보존했다.', '',
      table(['FULL row','MESS01 P / Q','MESS02 P / Q','MESS03 P / Q','MESS04 P / Q'],[
       [r['original_row']]+[f'{n(float(F(u["P_contribution_exact"])),6)} / {n(u["contribution"]["Q"],6)}' for u in r['per_vehicle']]
       for r in gridcontrib.get('newly_selected',[])]), '',
      '## 4. 후보 B: SOC–Mode–Travel 유효성과 실제 선택', '',
      '원본 에너지 식은 `E_next=E+αC−βD−T`다. '
      '`C=ΣPch`, `D=ΣPdis`, `T=Σ_depart e_a route_flow_a`이며 travel energy는 depart slot의 `E[t+1]`에 한 번 차감된다. '
      'α, β, e는 현재 Source18r 저장 binary64를 정확한 Fraction으로 해석했다. 이상화된 효율을 다시 계산하지 않는다. '
      '원래 SOC Bounds, 96슬롯/97경계, Mode 배타성, STAY 접속, 단일 차량 DAG path와 Compact alias를 독립 검사했다.', '',
      '`C>0`인 원본 정수점은 충전 STAY를 선택하므로 Mode 배타성으로 `D=0`, 유일 경로로 `T=0`이다. '
      'B1 `E≥E_min+βD+T`는 원래 현재 SOC 최소 Bounds가 되고, B2 `E≤E_max−αC`는 `E_next≤E_max`에서 나온다. '
      '`C=0`이면 `E_next=E−βD−T≥E_min`이 B1을 주고 B2는 원래 현재 SOC 최대 Bounds가 된다. '
      'unused transit Mode가 0이든 1이든 성립하며 새로운 복귀·접속·물리 가정을 사용하지 않는다. '
      '모든 원본 정수점에 대한 이 증명과 단일 U4 수치 replay는 구분한다.', '',
      f'2×4×96={socproof.get("candidate_count",768)}개 exact 후보의 정수 유효성 독립 감사는 {n(socind.get("PASS"))}다. '
      f'실제 BASE 분수점 위반은 {socsep.get("robustly_violated_count","미확보")}개이며 '
      f'최대 32개 한도에서 {len(soccuts)}개만 선택했다. '
      f'선택 Family 분포는 `{dict(Counter(r["family"] for r in soccuts))}`다. '
      '이번 실제 위반과 선택은 방전·이동 가용성 B1에만 있다. 충전 저장공간 B2는 정수 유효성은 PASS했지만 '
      'BASE에서 실제 위반 0개·선택 0개이므로 B2 행의 Native 효과는 측정하지 않았다. '
      '위반하지 않은 행은 넣지 않고 기존 LP에 함의되는지 전체를 단정하지 않는다. '
      '새 Binary·열·Bounds·Objective 변경은 없다.', '',
      '선택 행에서 독립 검증한 저장 coefficient와 SOC Bounds의 고유 조합은 다음과 같다. '
      '개별 원본 energy 행/alias 대조는 모든 행에 대해 수행했으며 같은 값을 가정해 생략하지 않았다.', '',
      table(['정확 α','정확 β','원래 E_min','원래 E_max'],sorted({
       (r['alpha'],r['beta'],r['Emin'],r['Emax']) for r in soccuts})), '',
      table(['SOC 추가 행','원본 energy Row','BASE 위반(kWh)'],[
       [r['name'],r['original_energy_row'],n(r['raw_violation'],8)]
       for r in soccuts]), '',
      '## 5. 정수 포함관계와 LP 강화의 정확한 관계', '',
      '원본 FULL 정수 가능영역을 F_int, 저장된 Compact 사영을 T라 한다. BASE는 동일 K48의 Binary만 C로 바꿨으므로 '
      '`T(F_int)⊆BASE`다. 원본 실제 Grid 행의 helper/Fraction 소거는 모든 원래 정수점에서 유효하며, SOC 후보도 위 정수 disjunction으로 유효하다. '
      '따라서 `T(F_int)⊆GRID⊆BASE`, `T(F_int)⊆SOC⊆BASE`다. '
      'SOC의 정수 유효성을 원래 Full의 모든 연속 LP 점에 대한 함의로 바꾸어 주장하지 않는다. '
      'GRID와 SOC는 서로 독립적으로 같은 BASE에 붙이며 둘 사이의 포함관계나 결합 효과는 측정하지 않았다.', '',
      '추가 행 때문에 정확한 수학적 LP 최소값은 BASE보다 낮아질 수 없다. '
      '다만 numerical ObjVal의 미소 변화와 finite-box 보정 하한의 변화는 정확한 최적값 차이가 아니다. '
      '보정 하한이 조금 낮아져도 포함관계의 위반을 뜻하지 않으며, 작은 Δ를 정확한 LP 최적값 개선으로 승격하지 않는다.', '',
      '추가 행의 정확 식을 `cᵀy≤R`, Native 계수를 c̃라 하면 유지된 finite Bounds에서 '
      '`E=Σmax((c̃−c)l,(c̃−c)u)`, `R̃=ceil_binary64(R+E)`다. '
      '`c̃ᵀy≤cᵀy+E≤R̃`이므로 원래 정수 가능해를 배제하지 않는 외향 전달이다. '
      '모든 기존 BASE 행·RHS·Sense·Bounds·열·목적함수를 그대로 보존하고 새 행만 추가했다. '
      '따라서 각 완료 LP의 유효 하한은 원본 정수 FULL 최적값의 하한이다.', '',
      table(['모델','Rows','Columns','원래 Binary / 실제 LP Binary','NNZ','추가 행','독립 Native0'],[
       [r['kind'],r['zero'].get('dimensions',{}).get('rows','미생성'),r['zero'].get('dimensions',{}).get('columns','미생성'),
        f'{r["zero"].get("original_binary_count","미확인")} / {r["zero"].get("dimensions",{}).get("binary","미생성")}',
        r['zero'].get('dimensions',{}).get('nnz','미생성'),0 if r['kind']=='BASE' else len(gridcuts if r['kind']=='GRID' else soccuts),
        n(r['independent0'].get('PASS'))] for r in runs]), '',
      table(['모델','CSR SHA','Domain SHA','CUTS_EXACT 파일 SHA'],[
       [r['kind'],r['zero'].get('matrix_sha','미확인'),r['zero'].get('domain_sha','미확인'),
        r['zero'].get('file_sha256',{}).get('CUTS_EXACT.json','해당 없음')] for r in runs]), '',
      '## 6. 완료 LP 결과와 독립 하한 인증', '',
      '세 모델 모두 Worker=1, Threads=1, TimeLimit=240초, Method=1, '
      'FeasibilityTol=OptimalityTol=1e−8을 유지했다. 실제 CSR/RHS/Sense/Bounds/types/objective/ObjCon/ModelSense 및 IsMIP=false를 Native readback으로 대조한다.', '',
      table(['모델','Solver Status','Native LP ObjVal','Exact weak-duality LB','BASE 대비 ObjVal Δ','BASE 대비 인증 LB Δ','재사용 누적 Global LB','완료 인증'],[
       [r['kind'],r['result'].get('Status','미실행'),r['result'].get('ObjVal') if r['result'].get('ObjVal') is not None else '미확보',n(r['cert'].get('LP_lower_bound'),16),
        '기준' if r['kind']=='BASE' else n(r['cert'].get('Delta_LP_objective'),16),
        '기준' if r['kind']=='BASE' else n(r['cert'].get('Delta_LP_lower_bound'),16),
        n(r['cert'].get('Global_LB'),16),n(r['cert'].get('PASS'))] for r in runs]), '',
      'Native numerical OPTIMAL은 원시 목적값·Primal/Pi/RC 및 잔차가 수치 계약 안에서 완료됐다는 결과다. '
      '**Exact LP optimum이 Primal 목적값과 정확히 같다는 증명은 없다.** '
      '여기서 비교·채택하는 독립 인증 하한은 실제 row multiplier를 sign cone에 맞춘 뒤 저장 binary64의 Fraction으로 '
      '`d=c−Aᵀπ`를 계산하고 `L=ObjCon+πᵀb+Σ_j min(d_j l_j,d_j u_j)`로 보정한 값이다. '
      '≤ 행의 π≤0, ≥ 행의 π≥0, equality의 π free를 확인하며 모든 finite variable Bound를 포함한다. '
      '작은 잘못된 Pi 부호는 유효 sign로 보정해 별도 보존한다. '
      '이 weak-duality 증명은 `L≤min(stored native LP)≤min(original integer FULL)`을 준다. '
      '현재 LP 하한은 과거 MIP ObjBound와 인증 범위가 다르고, Native LP ObjVal을 정수 FULL UB로 사용하지 않는다.', '',
      table(['모델','최대 행 잔차','최대 Bound 잔차','RC/stationarity 오차','row complementarity','bound complementarity','Primal−exact LB'],[
       [r['kind'],n(r['cert'].get('primal_maximum_row_violation'),12),n(r['cert'].get('primal_maximum_bound_violation'),12),
        n(r['cert'].get('reduced_cost_stationarity_maximum_error'),12),n(r['cert'].get('row_complementarity_maximum_error'),12),
        n(r['cert'].get('bound_complementarity_maximum_error'),12),n(r['cert'].get('primal_exact_dual_gap_float'),12)] for r in runs]), '',
      table(['모델','U4 모델 replay 최대 잔차','Native readback','exact weak-duality 인증','Exact LP optimum 인증'],[
       [r['kind'],n(r['zero'].get('U4_max_violation'),12),n(r['readback'].get('PASS')),
        n(r['cert'].get('exact_weak_duality_LP_lower_bound_certificate')),
        '증명 완료' if r['cert'].get('exact_LP_optimum_certificate') else '미인증(주장하지 않음)'] for r in runs]), '',
      'U4는 기존 원본 FULL에서 검증된 상한과 point를 재사용하고 새 모델에서도 수치 replay했다. '
      '이 연구에서 Full MILP나 Actual AC를 새로 실행해 U4를 검증했다는 뜻이 아니다. '
      '새 LP point는 분수점이며 FULL 가능계획·Actual PASS가 아니다.', '',
      'GRID는 보호 callback의 opaque 실패 신호로 약 34.988초에 INTERRUPTED(11)로 종료했다. '
      '`LP_POINT.npz`와 완료 OPTIMAL Primal/Dual을 확보하지 못해 최종 인증은 `LP_NOT_COMPLETED_OPTIMAL`로 거부했다. '
      '로그의 중간 목적값이나 중단된 ObjBound=0을 새 LP 하한·Delta로 사용하지 않는다. '
      'Native0의 원본 정수 포함관계와 16개 Cut 유효성은 유지되며, **A의 Native 효과는 미확정, 후속 채택은 보류**다. '
      'A를 수학적으로 무효라고 기각하거나 ΔLB=0이라고 기록하지 않는다.', '',
      '해당 stop receipt의 `b1_conflict_stop=true`는 gate 신호를 기록한 이름이다. '
      '실제 B1 Heavy Native 출현/충돌이나 보호 파일 변경이 증명된 사건은 아니다. '
      '직후 full safety 재검사는 PASS였고 원인은 당시 opaque detector만으로 확정하지 못했다. '
      'SOC 전에는 relative path 정규화·조회 중 자연 종료 처리·구조화된 거부 이유 기록을 보완했다. '
      '원본 실패·실행 소스와 로그는 보존했고, 모델·LP 수치 설정은 변경하지 않았다. '
      'GRID는 소비한 2번째 Optimize이므로 재실행하지 않았다.', '',
      '## 7. Runtime·RAM·예산과 사용자 우선순위', '',
      '최초 요청은 B1 우선이었다. 이후 사용자가 '
      f'**“{priority.get("user_request","후속 우선순위 지시 영수증 미확보")}”**라고 지시했다. '
      '현재 실행 계약은 이 후속 지시에 따라 B2 Root LP 연구를 우선하며 B1을 새로 시작하지 않는다. '
      '모델·LP 설정·최대 3회/720초 계약과 B1 Source/Ledger/결과 보호는 그대로 유지한다. '
      '알려진 read-only Native0 audit는 CPU/RAM/Commit이 안전하면 공존할 수 있지만, 실제 다른 Heavy Solver·unknown Gurobi·메모리 한계 gate는 유지한다. '
      '원래 B1 우선 gate에 따른 이전 admission 거부를 소급해서 삭제하지 않는다.', '',
      table(['모델','Native(초)','Optimize Wall(초)','모델 추출(초)','Gurobi 생성(초)','Peak RSS(GiB)','Peak Private Commit(GiB)',
             '최소 RAM Available(GiB)','최소 Commit Available(GiB)','Gurobi MaxMemUsed(원시 GB)'],[
       [r['kind'],n(r['result'].get('Runtime'),6),n(r['result'].get('optimize_wall_seconds'),6),
        n(r['zero'].get('model_extraction_seconds'),6),n(r['result'].get('model_build_seconds'),6),
        gib(r['result'].get('peak_process_RSS_bytes')),gib(r['result'].get('peak_private_commit_bytes')),
        gib(r['result'].get('minimum_RAM_available')),gib(r['result'].get('minimum_commit_available')),n(r['result'].get('MaxMemUsed_GB'),6)] for r in runs]), '',
      f'Oracle Wall {n(separation.get("wall_seconds"),6)}초, SOC integer proof 생성 {n(socproof.get("wall_seconds"),6)}초, '
      f'독립 SOC 정수 유효성 검증 {n(socind.get("wall_seconds"),6)}초. '
      '각 Native Worker의 RSS/Private Commit, 시스템 Available RAM과 Commit Available, Gurobi 보고 메모리는 서로 구분한다. '
      '보고한 Native peak를 모든 검증 프로세스의 전체 peak로 확대하지 않는다. '
      '모델 생성 후 4 GiB RAM·6 GiB Commit reserve와 max(2 GiB, 관측 생성 Private 증가×4)의 추가 여유를 유지했다. '
      '메모리 reserve, 실제 다른 Heavy Solver/unknown Gurobi 또는 보호 파일 drift가 관측되면 B2만 정상 terminate한다. '
      '후속 우선순위 변경 계약에서 구분한 알려진 Native0 audit와 실제 Solver를 구분한다.', '',
      table(['모델','원시 로그 callback 비용(초)','관측된 보호 gate 실패','Actual Heavy Native 충돌 확정'],[
       [r['kind'],n(callback_times.get(r['kind']),2),len(r['b1_trace'].get('conflicts',[])),
        '미확정: opaque stop' if r['kind']=='GRID' and r['result'].get('b1_conflict_stop') else '0건 관측'] for r in runs]), '',
      f'BASE callback 비용은 {n(callback_times.get("BASE"),2)}초, SOC는 {n(callback_times.get("SOC"),2)}초다. '
      'SOC 전 detector 보완으로 보호 관측 비용이 달라졌고 외부 자원 조건도 동일 통제하지 않았다. '
      '따라서 Native Runtime 100.464초와 BASE 86.840초의 차이를 SOC 정식화만의 인과적 비용이나 속도 개선으로 해석하지 않는다.', '',
      f'B1의 실제 상태는 `{post.get("B1",pre.get("B1",{})).get("B1_campaign_status","미확인")}`이며 '
      f'date 결과는 `{post.get("B1",pre.get("B1",{})).get("date_status_counts",{})}`다. '
      '1 PASS·2 FAIL·28 미실행으로 31일 캠페인을 완료했다고 주장하지 않는다. '
      '기존 global integrity error guard가 새 dispatch 전에 반환하는 상태에서 B1 Native Worker/Supervisor 부재와 자원 안전을 실제 확인했다. '
      '본 B2 연구는 B1 PR212 Source·Worker·Ledger·원본 FAIL/PASS·예약·프로세스를 변경하지 않았다. '
      '후속 관측의 B1 예약 Disabled는 이후 별도로 사용자가 승인한 중단 상태이며 이 연구가 변경한 상태가 아니다. '
      '원래 예약 Actions, Source, Ledger 및 원본 FAIL/PASS는 보존했다.', '',
      table(['모델','보호 gate 실패 관측','B1 보호 변경','보호 gate 위반 시 B2 정상 종료','guard stop flag','RAM stop'],[
       [r['kind'],len(r['b1_trace'].get('conflicts',[])),r['b1_trace'].get('mutations','미확인'),
        n(r['b1_trace'].get('normal_B2_terminate_on_B1_appearance')),r['result'].get('b1_conflict_stop','미실행'),
        r['result'].get('memory_stop','미실행')] for r in runs]), '',
      'BASE/SOC에서 실제 Heavy Solver 충돌은 0건 관측됐고 GRID에는 원인이 미확정인 보호 gate 실패 1건이 있다. '
      '실제 B1 Heavy Native 충돌을 확정한 증거는 없으며 opaque 실패를 충돌 확정으로 바꾸지 않는다. '
      f'`RESOURCE_GATE_TESTS.json` {n(gate_tests.get("PASS"))}: B1 Worker/Supervisor 출현, 보호 SHA drift, unknown process scan 오류, RAM/Commit 한계 위반의 거부를 검증했다. '
      '테스트는 함수 대체와 읽기 전용 관측이며 실제 B1 파일/프로세스/예약을 바꾸지 않았다.', '',
      'GRID 최초 admission은 B1 Gurobi module을 로드한 pricing qualification audit 때문에 거부됐고, '
      '다음 admission은 약 1.65 GiB private commit의 B1 history model audit 때문에 거부됐다. '
      '둘 다 `Native_optimize_started=false`이며 실제 Optimize 0회, 예산/latch를 소비하지 않았다. '
      '실패 영수증은 `NATIVE_FAILURE_FIRST_ADMISSION_REJECTED.json`과 '
      '`NATIVE_FAILURE_SECOND_ADMISSION_REJECTED.json`에 보존했다. '
      '첫 거부 뒤에는 실제 해당 audit 종료와 fresh 안전 확인을 기다렸다. '
      '후속 사용자 우선순위 지시 뒤에는 알려진 Native0 audit 공존만 명시적으로 허용하고 실제 Heavy Solver·unknown Gurobi 및 RAM/Commit gate를 유지했다. '
      '이 admission 거부와 실행 중 Heavy Solver 충돌은 구분한다. B1 캠페인을 새로 실행하지 않았다.', '',
      '## 8. 역사적 강화 실험과 이번 범위', '',
      f'역사적 감사 {n(history.get("PASS"))}: 7개 PR의 pinned HEAD와 14개 원문 코드/증명 Git blob SHA를 보존했다. '
      '`HISTORICAL_STRENGTHENING_AUDIT_KO.md`에 수학식·실패 범위·Source 차이를 정리했다.', '',
      table(['PR','조사 계열','이번 실험과의 관계'],[
       [109,'connection-aware Mode hull + arc-energy mass EF','unused transit mode canonicalization은 원본 bit assignment를 제거할 수 있어 재사용하지 않음'],
       [137,'aggregate C/D/connected power, DP SOC envelope, SOC-flow EF','동일 단순 Mode cut 재제출 없음; B는 원래 SOC 경계에 C/D/T를 직접 결합한 작은 사영'],
       [167,'connected power + folded PCS local hull','예전 single-slot 상태 증명은 이미 SOC/Mode/Travel 논리를 포함; 새로운 물리 정리라고 주장하지 않음'],
       [169,'4-slot joint route/mode/PQ/SOC hull','B는 기존 국소 joint hull 논리와 관련된 명시적 작은 행; window EF를 다시 구현하지 않음'],
       [185,'per-arc departure/arrival SOC reachability','현재 B의 aggregate D+T와 charge headroom은 행 형태가 다르지만 기존 물리 사실을 재검증'],
       [186,'May12 A-stage Phase-I/P1 exact recovery','M-stage Mode/PCS/Reachability 실패 후보가 아님'],
       [187,'651개 Route–SOC 행 LP 단일 검증','raw ObjVal 미소 증가가 독립 인증 개선은 아니었음; 현재도 exact finite-box 하한을 따로 계산'],
      ]), '',
      'A는 원본 Grid 행 자체가 새롭지 않다. PR211의 정수 incumbent 대신 현재 완료·인증된 실제 BASE 분수점에서 '
      '원래 Grid 위반과 sensitivity를 조사한 실험 축이다. B는 최초의 SOC–Mode–Travel 정리라고 주장하지 않고 '
      '현재 K48에 없는 작고 명시적인 정수 유효 행을 실제 Root 분수점에서 검증한 후보다. 과거 결과를 현재 Source18r 성과로 재사용하지 않는다.', '',
      '## 9. 채택·기각 및 실제 미완료 사항', '',
      table(['후보','완료 인증','BASE 대비 인증 ΔLB','하한 개선≥0.001','후속 MIP 후보 판단'],[
       [r['kind'],n(r['cert'].get('PASS')),n(r['cert'].get('Delta_LP_lower_bound'),16),
        n(r['cert'].get('candidate_material_LP_gain')),
        '자원 우선 대기: Native 효과 미계측' if not r['result'].get('Native_optimize_calls') else
        '하한 개선 기준 충족; 별도 승인 후 검토' if r['cert'].get('PASS') and r['cert'].get('candidate_material_LP_gain') else
        '기각: 완료·인증 개선 기준 미달' if r['cert'].get('PASS') else '완료 인증 실패: 효과 미확정'] for r in runs[1:]]), '',
      '계산시간 또는 메모리 감소만으로 채택하지 않는다. 이 경로에는 유의미한 자원 개선과 LP/정수 동등성의 독립 증명이 필요하다. '
      '새 행이 BASE의 수치 분수점을 배제했고 단지 같은 LP 목적값이 관측됐다는 사실은 LP 가능영역 동등성 증명이 아니다. '
      '세 모델 각각의 실제 완료 결과를 비교하며 Native0 행 수·분수 개수·위반 개수만으로 효과를 주장하지 않는다.', '',
      f'SOC의 현재 완료 Native 목적값 변화는 {n(runs[2]["cert"].get("Delta_LP_objective"),16)}, '
      f'exact weak-duality 하한 변화는 {n(runs[2]["cert"].get("Delta_LP_lower_bound"),16)}다. '
      '두 Native 목적값은 사실상 같고 약 2.4e−8의 보정 하한 차이는 dual correction 손실 차이다. '
      'Global 강화나 정확한 LP 최적값 상승으로 주장하지 않는다. SOC는 0.001 기준 미달로 후속 MIP 후보에서 **기각**한다. '
      'GRID는 완료·인증된 효과를 확보하지 못해 **보류**한다. '
      '두 후보를 합쳐서 실행하거나 새로운 물리 가정을 도입하지 않았다.', '',
      f'SOC 종료점의 Native0 재검사에서는 선택하지 않은 방전·이동 B1 행 '
      f'{soc_after.get("unselected_robustly_violated_count","미확보")}개가 여전히 위반되고 최대 위반은 '
      f'{n(soc_after.get("maximum_exact_row_violation_float_by_family",{}).get("SOC_DISCHARGE_TRAVEL_AVAILABILITY"),8)} kWh다. '
      f'선택 32행의 최대 Fraction 잔차는 {n(soc_after.get("maximum_selected_cut_exact_violation_float"),12)}로 수치 허용오차 안이며 '
      '충전 저장공간 B2의 실제 위반은 0개다. '
      '이 결과는 이번 32행 강화 뒤에도 원래 정수 운전과 다른 분수 상태가 남는다는 진단이다. '
      '남은 41행을 추가하면 하한이 개선된다는 근거는 아니며 추가 Cut·Native 실행을 하지 않았다. '
      '이번 기각은 시험한 SOC 32행의 Material 성과에 대한 판단이며 전체 768행이나 모든 joint hull의 효과를 판정하지 않는다.', '',
      '현재 인증된 비교 효과는 BASE 대비 SOC의 개별 효과이며 GRID 효과는 미확정이다. 결합 효과·Full MIP B&B 개선·Production 효율·'
      '3% Global Gap 달성·원본 FULL integer optimum·Actual OpenDSS PASS는 미검증이다. '
      '이번 승인된 최대 3회 LP 연구에서 종료하고 Native retry·모델 추가 확대·Production 통합을 하지 않는다.', '',
      '## 10. Source·B1 보존 및 증거', '',
      table(['보존 항목','실행 전 감사','실행 후 감사'],[
       [label,n(pre.get('checks',{}).get(key)),n(post.get('checks',{}).get(key))] for label,key in [
        ['PR207/209/210 HEAD clean','original_PR207_PR209_PR210_HEAD_and_clean'],
        ['PR211 정확한 HEAD clean','PR211_exact_HEAD_clean'],
        ['May 기존 HOLD marker 동일','held_markers_byte_identical_to_PR209'],
        ['기존 Supervisor/Monitor 두 예약 Disabled','two_schedules_disabled'],
        ['현재 PR212 자동화 PAUSED 및 frozen','current_PR212_automations_PAUSED_and_frozen'],
        ['B1 실제 실행 종료 및 error guard quiescent','B1_actual_execution_ended_and_error_guard_quiescence'],
       ]]), '',
      'PR212의 이전 승인된 B1-only 자동화 prompt가 과거 PR209 prompt와 달라졌다는 사실은 `historical_PR209_automation_check`에 그대로 보존했다. '
      '이번 연구는 현재 B1 보호 baseline의 PAUSED bytes를 유지하며 prompt·예약·프로세스를 변경하지 않는다. '
      'Source18r·U4·PR207/209/210/211·B1 PR212, StageBudget, NativeStopRequested, A1/A2/M-stage 예산 및 Planning/Actual 코드는 수정하지 않았다.', '',
      '보존 산출물: 원문 요청·TASK_CONTRACT, source/history SHA, 각 LP_A/DATA/AXES/ORIGINAL_BINARY, '
      '실제 x/Pi/RC, Native0/독립 Native0, exact Cut packet, source Full Row SHA, U4 replay, '
      'Native readback, resource/B1 preflight, B1/memory trace, native log, durable started latch, '
      '단계별 RESULT/독립 최종 인증, 전체 NATIVE_LEDGER, 전후 source/B1 audit 및 FINAL_RESULT. '
      '새 Draft PR은 PR211 연구 브랜치를 Base로 하고 기존 Source나 과거 증거를 덮어쓰지 않는다.', ''
    ]
    if summary:
        lines += ['최종 의사결정 영수증:', '', '```json',json.dumps(summary,ensure_ascii=False,indent=2),'```','']
    target=out/'B2_ROOT_LP_TIGHTENING_FINAL_KO.md'
    target.write_text('\n'.join(lines),encoding='utf-8')
    print(str(target))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    generate(parser.parse_args().out)
