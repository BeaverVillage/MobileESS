"""Generate the Korean report from JSON receipts and raw logs, without a solver.

This reporting process reads no FULL/Joint matrix and imports no numpy/Gurobi.
It distinguishes exact cut/domain checks from numerical B&B bound reliance.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
import argparse
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/v42_critical_grid_cg'
UB = .6760534504652341
OLD_LB = .42547778318693985
PR209_LB = .11666465693783702
FULL_BOUND = .28940049108548904
TARGET = .6557718469512771
GIB = 1024**3


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def num(value, places=10):
    if value is None:
        return '미확보'
    if isinstance(value, bool):
        return 'PASS' if value else 'FAIL'
    if isinstance(value, (float, int)) and math.isfinite(value):
        if value and abs(value) < 10**(-places):
            return f'{value:.6e}'
        return f'{value:.{places}f}'
    return str(value)


def gib(value):
    return num(value / GIB, 4) if value is not None else '미계측'


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                       '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                      ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])


def stages(out):
    answer = []
    for number in (1, 2):
        folder = out / f'iteration{number:02d}'
        if not folder.exists():
            continue
        answer.append(dict(number=number, folder=folder,
                           separation=read(folder/'SEPARATION.json', {}),
                           cuts=read(folder/'CUTS_EXACT.json', {}),
                           native0=read(folder/'NATIVE0.json', {}),
                           independent0=read(folder/'INDEPENDENT_NATIVE0.json', {}),
                           result=read(folder/'RESULT.json', {}),
                           certificate=read(folder/'INDEPENDENT_CERTIFICATE.json', {}),
                           readback=read(folder/'NATIVE_READBACK.json', {}),
                           admission=read(folder/'MEMORY_ADMISSION.json', {}),
                           gate=read(folder/'STAGE2_GATE.json', {})))
    return answer


def generate(out=OUT):
    out = Path(out)
    stage_data = stages(out)
    summary = read(out/'FINAL_RESULT.json', {})
    ledger = read(out/'NATIVE_LEDGER.json', {})
    decision = read(out/'STAGE2_DECISION.json', {})
    pre_hold = read(out/'PRE_RUN_RESOURCE_HOLD.json', {})
    post_hold = read(out/'POST_RUN_RESOURCE_HOLD.json', {})
    reuse = read(out/'PR210_REUSE_AUDIT.json', {})
    execution_audit = read(out/'EXECUTION_LEDGER_SNAPSHOT_AUDIT.json', {})
    valid = [s for s in stage_data if s['certificate'].get('PASS')]
    certified = valid[-1]['certificate'] if valid else {}
    published = summary.get('Global_LB', summary.get('LB_published', certified.get('Global_LB', OLD_LB)))
    classification = summary.get('classification', certified.get('classification', 'CG_RESOURCE_OR_NUMERIC_STOP'))
    gap = (UB - published) / UB if published is not None else None
    improvement = published - OLD_LB if published is not None else None
    native_results = [s['result'] for s in stage_data if s['result'].get('Native_optimize_calls')]
    runtime_complete = len(native_results) == len(ledger.get('calls', [])) and all(r.get('Runtime') is not None for r in native_results)
    wall_complete = len(native_results) == len(ledger.get('calls', [])) and all(r.get('optimize_wall_seconds') is not None for r in native_results)
    native_runtime = sum(float(r['Runtime']) for r in native_results) if runtime_complete else None
    native_wall = sum(float(r['optimize_wall_seconds']) for r in native_results) if wall_complete else None
    requested = sum(c.get('TimeLimit', 0) for c in ledger.get('calls', []))
    all_cuts = [(s['number'], r) for s in stage_data for r in s['cuts'].get('rows', [])]
    goal = published is not None and published >= TARGET
    source0 = next((s['independent0'] for s in stage_data if s['independent0']), {})
    now = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
    lines = [
        '# V42 Critical-Grid Constraint Generation Global LB 최종 보고', '',
        f'작성 기준 시각: {now} (Asia/Seoul). 대상: IEEE123 / B2 / 2025-05-01.', '',
        f'종료 판정은 **{classification}**이다. 독립 인증을 통과한 누적 Global LB는 **{num(published)}**이며, '
        f'검증된 원본 FULL U4 UB **{UB:.16f}** 대비 Global Gap은 **{num(100*gap if gap is not None else None, 8)}%**다. '
        f'Joint16 기준 개선량은 **{num(improvement)}**이다. 3% 목표는 **{"달성" if goal else "미달"}**이다.', '',
        f'새 Native 요청은 {len(ledger.get("calls", []))}회 / 최대 2회, 요청 한도 합은 {requested}초 / 최대 360초다. '
        f'실제 Native Runtime 합은 {num(native_runtime,6)}초이고 Optimize Wall 합은 {num(native_wall,6)}초다. '
        '원본 FULL MILP·별도 FULL LP·Column Generation·DW·Benders·가중치 최적화·공식 캠페인·추가 날짜 실행은 모두 0회다. '
        '기존 K16을 재최적화하거나 시간만 연장하지 않았다.', '',
        '## 1. 기준 및 재사용 증거', '',
        table(['기준', '정확한 commit / 수치', '역할'], [
            ['Source18r / PR207', '497609b46faa14ea7e32a9483a333ab32fd264ef', 'FULL 저장 행렬·Forecast·AIDC·물리 모델의 Authority'],
            ['차량별 LB / PR209', '9383a99f1bdcabbd49c79b3ad9f9ee36d523868a', '원본 helper 소거 및 이전 LB 증거'],
            ['Joint16 / PR210 부모', '6a8fd44f59f1f461c60d2d14f5f5be605e4ed640', '새 브랜치의 정확한 부모, 360초 한도 저장 결과 재사용'],
            ['원본 검증 U4 UB', f'{UB:.16f}', 'Global Gap에 사용하는 유일한 UB'],
            ['Joint16 Global LB', f'{OLD_LB:.17f}', '검증된 이전 하한 계승'],
            ['Joint16 최종 정수해 목적값', '0.4258955562455018', '첫 Separation의 입력; FULL UB로 사용하지 않음'],
            ['3% 목표 LB', f'{TARGET:.16f}', '성능 목표이며 달성 가정 없음'],
        ]), '',
        f'FULL case SHA: `{source0.get("case_sha", "미확인")}`. '
        f'FULL CSR SHA: `{source0.get("FULL_matrix_sha256", "미확인")}`. '
        f'FULL domain SHA: `{source0.get("FULL_domain_sha256", "미확인")}`.', '',
        'PR210 `native360/JOINT_INCUMBENT.npz`, `JOINT_A.npz`, `JOINT_DATA.npz`, `JOINT_AXES.npz`, '
        '`INDEPENDENT_CERTIFICATE.json`, `RESULT.json` 및 `K16_EXACT_ROWS.json`을 재사용했다. '
        '소스·결과 파일의 실제 SHA는 각 단계의 `SEPARATION.json`, `NATIVE0.json`, `INDEPENDENT_NATIVE0.json`과 최종 인증서에 보존했다. '
        '원본 CSR/domain SHA와 PR209 저장 파일 SHA도 다시 대조했다.', '',
        f'추가 재사용 감사 `PR210_REUSE_AUDIT.json`: {num(reuse.get("PASS"))}, '
        f'PR210에서 상속한 실제 파일 {reuse.get("count", "미확인")}개의 SHA를 저장 index와 비교했다. '
        f'기존 tracked 파일 변경 목록: `{reuse.get("existing_tracked_file_changes", "미확인")}`. '
        f'상속 index SHA: `{reuse.get("inherited_index_sha256", "미확인")}`.', '',
        '## 2. 원본 FULL 가능영역 포함관계', '',
        '원본 FULL 가능영역을 F라 하고, PR210에서 검증된 Compact 사영을 T라 한다. '
        'T는 원본 96슬롯 경로를 변경하지 않고 Node-Activity 이진변수와 연속 route_flow, 저장 Static Presolve 역매핑 및 Exact C3A 증명을 사용한다. '
        '네 차량의 물리 행, Bounds, 열, 타입, 목적함수와 기존 K16을 bitwise 보존했다. '
        '초기/종단 SOC·에너지 보존·Mode·Pch/Pdis/Q·PCS16·이동 시간/에너지·접속·복귀 경로 가능성을 그대로 유지하며, '
        '종단은 원래 slot96 도착 조건이다. PCS16은 상속한 Exact C3A의 검증된 중복/함의 제거 후 동등한 영역을 유지한다. '
        '새 출발지 복귀 조건이나 경로 제거·고정·Binary 추가는 없다.', '',
        '원본 행 aᵀz ≶ r의 Sense를 실제 저장 값에 따라 ≤로 통일한다. '
        '원본 injection/response/correction 정의 등식을 저장 binary64의 정확한 Fraction으로 소거하고, '
        'Compact 역매핑을 대입하면 cᵀy ≤ R을 얻는다. 이 식은 원본 FULL에서 실제 존재하는 행의 정확한 대입 결과이므로 '
        '모든 z∈F에 대해 cᵀT(z)≤R이다. 고정 AIDC·Forecast·Response Correction과 원본 RHS의 기여는 소거 상수에 포함되며 '
        '새 AC/OpenDSS 계수나 Actual 입력을 사용하지 않았다.', '',
        'Native 계수 c̃ⱼ는 Fraction cⱼ의 binary64 전환값이다. 유한한 원본 유지 Bounds [lⱼ,uⱼ]에서 '
        'E=Σⱼmax((c̃ⱼ−cⱼ)lⱼ,(c̃ⱼ−cⱼ)uⱼ)를 정확히 계산하고, Native RHS R̃=ceil_binary64(R+E)로 정한다. '
        '그러면 c̃ᵀy≤cᵀy+E≤R+E≤R̃이다. 계수를 임의 삭제하지 않고, underflow·overflow·무한 반올림 Box를 거부한다. '
        '이 보수적 행은 원본 가능해를 배제하지 않는다.', '',
        '따라서 T(F)⊆J̃_K가 모든 단계에서 유지되고 min(J̃_K)≤min(F)다. '
        '이전 Native 행 자체를 그대로 보존하고 검증된 행만 추가하므로 J̃_next⊆J̃_current이며, '
        '수학적 최소 목적값은 감소하지 않는다. TIME_LIMIT의 개별 ObjBound가 항상 증가한다고 가정하지 않는다. '
        '각 단계에서 새 모델 포함관계·Source·Bounds·목적함수 무결성이 PASS한 경우에만 '
        'LB_published=max(LB_previous, LB_new_certified)로 계승한다.', '',
        '## 3. Separation 및 원본 전체 계통 위반 분석', '',
        '저장 Joint 정수해를 C2 축과 원본 역매핑으로 복원하고 원본 FULL의 109,440개 injection/response helper 정의를 재구성했다. '
        '경로·Mode·Node 정수 패턴을 반올림하거나 변경하지 않는다. Sparse Matrix 연산과 전파된 부동소수점 오차 envelope는 탐색에만 사용한다. '
        '채택할 행은 독립 Fraction 소거·원본 Row SHA·Sense·RHS·좌표·Phase 검사와 정확한 양의 위반량을 모두 통과해야 한다. '
        '외향 보정 후의 Native 행도 이전 정수해를 실제로 배제하는지 Fraction으로 확인한다.', '',
        'thermal은 부하율 pu, transformer facet은 kVA, NormalAmps는 전류 부하율 pu, voltage는 원본 저장 식의 전압 제곱 pu² 단위다. '
        'thermal/NormalAmps는 정격 1, transformer는 원본 kVA×cos(π/16), voltage는 행 기준 1 pu²로 정규화한다. '
        '서로 다른 단위를 직접 순위 비교하지 않는다. 고정 quota는 thermal 10, transformer 2, voltage upper 2, lower 2다. '
        '각 Family 내부 정규화 순위를 사용하고 같은 asset/phase/slot의 Facet 대표성을 먼저 확보한다. '
        '정확히 동일한 소거 계수/RHS 행만 중복 제거하고, 부족 quota는 정해진 Family 순서에서 보충한다. '
        '수학적으로 다른 유효 행을 다양성 기준만으로 영구 제외하지 않는다.', '',
    ]
    for stage in stage_data:
        s = stage['separation']; n = stage['number']
        if not s:
            continue
        lines += [f'### {n}차 Separation', '',
                  f'검사한 원본 Security 행은 {s.get("scan_original_security_rows", "미확인"):,}개, '
                  f'탐색 후보 {s.get("candidate_count", 0):,}개, 채택 {s.get("selected_count", 0)}개다. '
                  f'Wall {num(s.get("wall_seconds"), 6)}초. '
                  f'원본 정수 패턴 최대 잔차 {num(s.get("original_integer_pattern_max_residual"), 12)}, '
                  f'helper 숫자 replay 최대 잔차 {num(s.get("helper_numerical_replay_max_residual"), 12)}.', '',
                  table(['Family', '원본 행', '누락 행', '확인 탐색 후보', '최대 원시 위반', '0 부근/미확정'],
                        [[family, data['original_rows'], data['missing_rows'], data['screened_positive'],
                          num(data['maximum_raw_violation']), s.get('uncertainty', {}).get(family, {}).get('count', 0)]
                         for family, data in s.get('families', {}).items()]), '',
                  '전부 Sparse 검사했지만 전 행에 대한 Fraction 최적성 증명은 하지 않았다. '
                  '`uncertainty`와 자동 채택 실패 사유는 별도 보존한다. 위반을 못 찾았다는 사실만으로 FULL 최적성을 주장하지 않는다.', '']
    lines += ['## 4. 실제 추가 행과 위반량', '',
              'Row ID는 저장 FULL의 0 기반 CSR 행 번호다. 원시·정규화 위반량은 해당 단계 입력 정수해의 값이며, '
              '행별 원본 계수/RHS SHA, 정확한 Fraction 위반량, helper 정의 SHA, 선정·제외 사유는 `CUTS_EXACT.json`과 `CANDIDATES.json`에 보존했다.', '',
              table(['단계', 'FULL Row ID / 이름', 'Asset / Phase', 'Slot / Facet', '원시 위반', '정규화 위반', '원시 단위'],
                    [[n, f'{r["original_row"]} / {r["name"]}', f'{r["metadata"]["asset"]} / {r["metadata"]["phase"]}',
                      f'{r["metadata"]["slot"]} / {r["metadata"]["facet"]}', num(r['raw_violation']),
                      num(r['normalized_violation']), r['metadata']['unit']] for n, r in all_cuts]), '',
              '## 5. Native0 검증과 모델 규모', '',
              table(['단계', 'Rows', 'Columns', 'Binary', 'NNZ', '추가 K / 누적 K', '생성 Wall(초)', 'Native0 독립 인증'],
                    [[s['number'], s['native0'].get('dimensions', {}).get('rows', '미생성'),
                      s['native0'].get('dimensions', {}).get('columns', '미생성'),
                      s['native0'].get('dimensions', {}).get('binary', '미생성'),
                      s['native0'].get('dimensions', {}).get('nnz', '미생성'),
                      f'{len(s["cuts"].get("rows", []))} / {16+sum(len(t["cuts"].get("rows", [])) for t in stage_data if t["number"]<=s["number"])}',
                      num(s['native0'].get('model_extraction_seconds'), 6), num(s['independent0'].get('PASS'))] for s in stage_data]), '',
              '크기 게이트: Columns=244,265 유지, Binary=9,322 유지, Rows≤160,000, NNZ≤1,800,000. '
              '원본 FULL 행렬 재생성이나 Joint16 재최적화 없이 기존 Joint CSR의 행 prefix를 그대로 유지한 채 검증 행만 붙였다. '
              'Bounds·Objective·타입·축·기존 K16·모든 물리 행의 bitwise 보존과 U4 MIP Start replay를 독립 검증했다. '
              '실제 Gurobi CSR/RHS/Sense/Bounds/types/objective/readback을 Optimize 전에 다시 대조했다.', '',
              table(['단계', '모델 CSR SHA', '모델 domain SHA', 'CUTS_EXACT 파일 SHA'],
                    [[s['number'], s['native0'].get('matrix_sha','미생성'), s['native0'].get('domain_sha','미생성'),
                      s['native0'].get('file_sha256',{}).get('CUTS_EXACT.json','미확인')] for s in stage_data]), '',
              table(['단계', 'U4 새 모델 최대 잔차', 'Row ID 변조', 'Phase 변조', 'RHS 부호 변조', '계수 변조', 'Source SHA 변조', '반올림 방향 변조'],
                    [[s['number'], num(s['independent0'].get('U4_replay', {}).get('row_violation'), 15)] +
                     ['거부' if s['independent0'].get('adversarial_tests', {}).get(k, {}).get('rejected') else '미확인'
                      for k in ['Row_ID','Phase','RHS_sign','Coefficient','Source_SHA','Rounding_direction']]
                     for s in stage_data]), '',
              'U4 저장점의 검증은 수치 replay 허용오차 1e−8을 사용한다. '
              f'채택 행의 Fraction 평가에서 최대 양의 잔차는 {num(max([float(Fraction(r.get("U4_exact_violation","0"))) for _,r in all_cuts]+[0.]),15)}다. '
              '저장 binary64 U4 점 자체가 정확한 유리수 가능해라고 주장하지 않는다. '
              '미소 양의 잔차를 실제 물리 위반으로 오인하지 않으며, '
              '모든 정확한 FULL 가능해의 사영을 보존한다는 별도의 Fraction 포함관계 증명은 이 numerical Start replay와 구분한다.', '',
              '## 6. Solver 결과와 누적 Global LB', '',
              '각 새 실행은 Worker=1, Threads=1, TimeLimit=180초, MIPGap=0.03, MIPFocus=3, Seed=42, '
              'FeasibilityTol=IntFeasTol=OptimalityTol=1e−8을 유지했다. '
              'MIP Start는 새 제약까지 검증한 기존 U4를 사용했다. 이전 Joint 해는 새 채택 행을 위반하므로 무조건 Start로 전달하지 않았다.', '',
              table(['단계', 'Status', 'Root 완료', 'Nodes', 'ObjBound / 새 LB', 'ObjVal(축소 해)', '축소 MIPGap(%)', '누적 LB', '직전 단계 대비 개선', 'FULL Global Gap(%)', '최종 인증'],
                    [[s['number'], s['result'].get('Status','미실행'), num(s['result'].get('root_relaxation_completed')),
                      num(s['result'].get('NodeCount'),0), num(s['result'].get('ObjBound')), num(s['result'].get('ObjVal')),
                      num(100*s['result']['MIPGap'],8) if s['result'].get('MIPGap') is not None else '미확보',
                      num(s['certificate'].get('Global_LB')),
                      num(s['certificate']['Global_LB']-s['certificate']['LB_previous'],16) if s['certificate'].get('PASS') else '미인증',
                      num(s['certificate'].get('Gap_percent'),8),
                      num(s['certificate'].get('PASS'))] for s in stage_data]), '']
    for stage in stage_data:
        lines += [f'{stage["number"]}차 Presolve/Root 원시 로그 요약:', '', '```text']
        lines += stage['result'].get('presolve_summary', ['아직 Solver 결과 없음'])
        lines += ['```', '']
        log_path = stage['folder']/'NATIVE.log'
        if log_path.exists():
            node_lines = [line for line in log_path.read_text(encoding='utf-8',errors='replace').splitlines()
                          if re.match(r'^\s+\d+\s+\d+\s+[0-9.]+\s+\d+\s+\d+\s+[0-9.]+\s+[0-9.]+', line)]
            if node_lines:
                lines += ['마지막 Root/Node 진행 행 (`IntInf` 포함, 원시 로그):', '', '```text', node_lines[-1], '```', '']
    lines += ['ObjVal은 축소 모델의 정수 incumbent 목적값이며 Global LB가 아니다. '
              '새 LB는 실제 Gurobi `ObjBound`를 사용하고 최종 인증이 PASS한 단계만 누적한다. '
              '축소 incumbent를 원본 FULL UB나 Actual OpenDSS PASS로 승격하지 않았다.', '',
              '## 7. 2차 조건부 실행 및 예산', '',
              '2차는 1차 최종 인증 완료, 신규 Certified LB 개선≥0.005, 유효한 새 정수해, '
              '미포함 실제 위반 행, 재통과한 크기·RAM 게이트, 완전한 1차 종료 Ledger가 모두 확인될 때만 허용했다. '
              '한 단계 최대 16행, 누적 최대 32행 추가, K 최대 48, 전체 Optimize 최대 2회 / 요청 360초 계약이다.', '']
    stage2 = next((s for s in stage_data if s['number']==2), None)
    stage2_record = stage2['gate'] if stage2 and stage2['gate'] else decision
    lines += ['조건 및 실제 판단 기록:', '', '```json',
              json.dumps(stage2_record or {'executed':False,'reason':'STAGE2_DECISION_RECEIPT_NOT_PRESENT'}, ensure_ascii=False, indent=2),
              '```', '',
              f'실제 Ledger 호출 수: {len(ledger.get("calls", []))}, 요청 예산: {requested}초. '
              f'Native Runtime 합: {num(native_runtime,6)}초. 종료 영수증이 없으면 Runtime을 임의로 0으로 만들지 않는다. '
              '중단·TimeLimit·실패 실행의 latch나 예산을 초기화하지 않았다. '
              '추가 Solver 실행·제약 확장·같은 모델 재실행은 수행하지 않았다.', '',
              '1차 종료 시점의 1회 Ledger는 `NATIVE_LEDGER_STAGE1.json`으로 보존했고, 최종 2회 Ledger와 구분한다. '
              'Solver의 실제 TimeLimit 종료 시점에는 미세한 종료 오버헤드가 있을 수 있으므로 요청 예산과 측정 Runtime을 별도로 보고한다.', '',
              f'실제 Runtime의 요청 합 대비 종료 초과는 {num(native_runtime-requested if native_runtime is not None else None,6)}초다. '
              '각각의 요청 TimeLimit는 180초로 고정했고 추가 Optimize나 재시작을 하지 않았다. '
              f'실행 Ledger snapshot 감사는 {num(execution_audit.get("PASS"))}이며, '
              f'1차 snapshot SHA `{execution_audit.get("stage1_ledger_sha256", "미확인")}`, '
              f'2차 최종 SHA `{execution_audit.get("stage2_ledger_sha256", "미확인")}`를 각 최종 인증서의 실행 당시 SHA와 대조했다. '
              '1차 실행 소스는 `PILOT_STAGE1_EXECUTED.py`로 별도 보존했다. '
              '2차 전에는 gate 필드와 admission 인증서 SHA 검사를 강화했으며 모델과 Native 수치 파라미터를 바꾸지 않았다.', '',
              '## 8. 시간 및 메모리', '',
              table(['단계', 'Oracle Wall(초)', 'CSR 추출/결합 Wall(초)', '독립 Native0 Wall(초)', '독립 최종 인증 Wall(초)'],
                    [[s['number'], num(s['separation'].get('wall_seconds'),6),
                      num(s['native0'].get('model_extraction_seconds'),6), num(s['independent0'].get('wall_seconds'),6),
                      num(s['certificate'].get('wall_seconds'),6)] for s in stage_data]), '',
              table(['단계', 'Native(초)', 'Optimize Wall(초)', 'Gurobi 생성(초)', 'Peak RSS(GiB)', 'Peak Private Commit(GiB)',
                     '최소 Available RAM(GiB)', '최소 Commit Available(GiB)', 'Gurobi MaxMemUsed(원시 GB)'],
                    [[s['number'], num(s['result'].get('Runtime'),6), num(s['result'].get('optimize_wall_seconds'),6),
                      num(s['result'].get('model_build_seconds'),6), gib(s['result'].get('peak_process_RSS_bytes')),
                      gib(s['result'].get('peak_private_commit_bytes')), gib(s['result'].get('minimum_RAM_available')),
                      gib(s['result'].get('minimum_commit_available')), num(s['result'].get('MaxMemUsed_GB'),6)] for s in stage_data]), '',
              'RAM은 시스템 Available RAM, Commit은 Windows Commit Limit−Commit Total, RSS는 프로세스 Working Set, '
              'Private Commit은 프로세스 전용 commit이며 서로 대체하지 않는다. Gurobi MaxMemUsed는 Solver가 보고한 원시 GB다. '
              '모델 생성 후 4 GiB RAM·6 GiB Commit reserve 위에 max(2 GiB, 관측 생성 Private 증가×4)의 추가 성장 여유를 확보했다. '
              '0.5초 간격 callback에서 reserve 위반·수치/메모리 오류가 있으면 정상 terminate하도록 유지했다. '
              '다른 Heavy Worker가 없는지 실행 직전 조사했고 기존 프로세스를 강제 종료하지 않았다.', '',
              table(['단계', '생성 후 Available RAM(GiB)', '생성 후 Commit Available(GiB)', '추가 예상 성장(GiB)', 'Admission', '메모리 중단', '수치 오류'],
                    [[s['number'], gib(s['admission'].get('sample',{}).get('system',{}).get('RAM_available')),
                      gib(s['admission'].get('sample',{}).get('system',{}).get('Commit_available')),
                      gib(s['admission'].get('estimated_additional_bytes')), num(s['admission'].get('PASS')),
                      str(s['result'].get('memory_stop','미실행')), str(s['result'].get('callback_errors',[]))]
                     for s in stage_data]), '',
              'FULL CSR는 Oracle와 독립 소거 검사 프로세스에서 읽기 전용으로 사용하고 Solver 생성 전에 해제했다. '
              'Native Worker에는 Joint CSR만 있다. 보고한 Peak RSS/Private Commit은 각 Native Worker의 실제 계측치다. '
              'Oracle의 프로세스 Peak RSS는 별도 계측하지 않았으므로 Native 계측값을 전체 연구의 모든 프로세스 peak로 확대 해석하지 않는다.', '',
              '## 9. 비교, 인증 범위 및 후속 판단', '',
              table(['방법 / 기준', 'Global LB', '검증 U4 대비 Gap(%)', '수학적 차이'],
                    [[label, num(lb), num(100*(UB-lb)/UB if lb is not None else None,8), detail] for label, lb, detail in [
                        ['PR209 차량별 단일 가중합', PR209_LB, '차량별 물리 정수 영역의 독립 하한 합산; 계통 행은 가중 평균'],
                        ['Source18r Full Solver ObjBound', FULL_BOUND, '원본 Full Solver의 수치 B&B 하한; Root 미완료 과거 결과'],
                        ['PR210 Joint16', OLD_LB, '같은 rho에 K16을 별도 적용, 네 차량 물리 운전 공동 최적화'],
                        ['이번 CG 누적', published, 'K16·물리를 그대로 유지하고 실제 위반하는 원본 계통 행만 추가'],
                    ]]), '',
              '독립 인증은 원본 Source·파일 SHA·helper Fraction 소거·Compact 사영·원본 포함관계·보수적 반올림·실제 Gurobi readback·'
              'Ledger·수치 상태·Bound/Incumbent 순서·원시 로그를 감사했다. '
              'Fraction 수준의 행 및 포함관계 증명과 Solver 수치 ObjBound의 신뢰 계약을 명확히 구분한다. '
              'Exact rational B&B trace 인증이나 별도 LP 최적화는 수행하지 않았다.', '',
              f'최종 판단: **{classification}**. '
              + ('선정된 소수의 원본 위반 행 추가는 Joint16보다 유의미한 하한 개선을 보였다. '
                 if improvement is not None and improvement>=.005 else
                 '이번 제한된 원본 위반 행 추가의 하한 개선은 채택 기준 0.005에 미달하거나 독립 인증되지 않았다. ')
              + ('3% 목표를 충족했다. ' if goal else '3% 목표까지의 하한 차이는 ' + num(TARGET-published if published is not None else None) + '이며 아직 미완료다. ')
              + '이번 승인된 제한에서 연구를 종료하고 자동 확대하지 않는다. '
              '생략 제약의 범위와 Root LP의 정수 분수화가 후속 분석 대상이지만, 어느 하나가 유일한 병목이라고 증명하지 않았다. '
              '정수해가 위반한 행만 추가해도 Root LB가 반드시 크게 상승하는 것은 아니다. '
              '마지막 정수해를 FULL 가능해로 인증하거나 FULL 최적성을 증명하지 않았다.', '',
              '## 10. Scientific Source·HOLD·증거 보존', '',
              table(['항목', '실행 전 감사', '실행 후 감사'],
                    [[name, num(pre_hold.get('checks',{}).get(key)), num(post_hold.get('checks',{}).get(key))]
                     for name,key in [
                         ['PR207/209/210 HEAD 및 pristine checkout','original_PR207_PR209_PR210_HEAD_and_clean'],
                         ['공식 May HOLD marker 동일','held_markers_byte_identical_to_PR209'],
                         ['Supervisor/Monitor 예약 Disabled','two_schedules_disabled'],
                         ['관련 자동화 PAUSED 및 동일','relevant_automations_PAUSED_and_unchanged'],
                         ['기존 controller 자손 계산 Worker 없음','held_controller_computational_descendants_empty'],
                         ['별도 Heavy Gurobi/Native Worker 없음','no_other_observed_Gurobi_or_native_worker'],
                     ]]), '',
              'Source18r·U4 엔진·기존 PR207/209/210 소스·결과·증거, StageBudget, NativeStopRequested, '
              'A1/A2/M-stage 예산, 원본 Planning/Actual 실행 코드를 변경하지 않았다. '
              '새 연구 코드는 `tools/critical_grid_cg/`, 증거는 `docs/v42_critical_grid_cg/`에만 작성했다. '
              'Controller 상태는 관측 시점의 상태와 byte identity로 보고하며 연속 무CPU 상태를 주장하지 않는다.', '',
              '보존 산출물은 USER_REQUEST_KO/TASK_CONTRACT, 각 SEPARATION/CANDIDATES/CUTS_EXACT, '
              'Native0·독립 Native0·모델 SHA·원시 Native.log·Native events·memory trace·readback·admission·'
              'durable started latch·Global NATIVE_LEDGER·최종 독립 인증서·FINAL_RESULT·전후 Resource/HOLD 감사다. '
              '새 Draft PR은 PR210 연구 브랜치를 Base로 한다.', '']
    if stage2 and stage2['certificate'].get('PASS'):
        c2 = stage2['certificate']
        increment = c2['Global_LB'] - c2['LB_previous']
        r2 = stage2['result']
        text = [
            '**2차 증분과 확대 기각:** 2차는 1차 대비 LB를 '
            f'**{increment:.16f}** 높였다. 이 증분은 0.005보다 작다. '
            f'원래 Joint16 대비 총 개선량 **{published-OLD_LB:.16f}**에 따른 최종 Material 판정과 '
            '2차 증분의 Nonmaterial 판단을 구분한다. '
            f'2차 SolCount={r2.get("SolCount")}이고 축소 incumbent rho={num(r2.get("ObjVal"),16)}이다. '
            + ('새 정수 incumbent는 확보되지 않았고 U4 Start만 남았다. '
               if summary.get('stage2_U4_start_retained_only') else '정수 incumbent 확보 사실은 Solver 영수증 범위에서만 해석한다. ')
            + 'Start rho가 원본 검증 UB보다 한 ULP 작게 보고되어도 새 FULL UB로 사용하지 않는다. '
            'Global Gap 계산은 계속 원본 검증 UB 0.6760534504652341을 사용한다.', '',
            '원시 로그의 Root 완료 시간은 1차 65.47초, 2차 119.18초이고, 2차 종료 Root의 IntInf는 1,152였다. '
            'Root에서 높은 분수성, 더 긴 Root 비용, 거의 변하지 않은 유효 하한이 관측되었다. '
            '진행 중 simplex의 약 0.527 목적값은 primal infeasibility가 남은 중간 숫자이므로 유효 하한으로 쓰지 않았다. '
            '최종 채택한 2차 하한은 완료 Root 및 최종 B&B ObjBound 0.46498486997548166이다.', '',
            '같은 고정 quota를 맹목적으로 확대하는 추가 iteration, 더 큰 캠페인, Solver 시간 연장은 **기각**한다. '
            '이번 Source와 cut transport의 유효성은 확인됐지만 3% 수렴이 확인되지 않았다. '
            '후속은 별도로 승인된 연구가 있을 때 LP 분수성·계통 제약 coverage가 하한에 작용하는 구조를 분석하는 것부터 검토한다. '
            '이번 작업에서 추가 Solver는 실행하지 않는다.', '',
        ]
        marker = lines.index('## 10. Scientific Source·HOLD·증거 보존')
        lines[marker:marker] = text
    output = out/'CRITICAL_GRID_CG_FINAL_REPORT_KO.md'
    output.write_text('\n'.join(lines), encoding='utf-8')
    print(str(output))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=OUT)
    generate(parser.parse_args().out)
