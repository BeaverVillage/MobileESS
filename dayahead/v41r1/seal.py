"""Seal the authority-stop evidence without claiming a scientific margin freeze."""
import xml.etree.ElementTree as ET
import pandas as pd

from .audit import BASE, OUT, ROOT, STOP, old_files, read, ref, sha, write


def run():
    junit = OUT / 'V41R1_REGRESSION_JUNIT.xml'
    suite = ET.parse(junit).getroot()
    cases = list(suite.iter('testcase'))
    failures = len(list(suite.iter('failure'))) + len(list(suite.iter('error')))
    skipped = len(list(suite.iter('skipped')))
    assert cases and failures == skipped == 0
    preserved = read(OUT / 'V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json')['files']
    assert old_files() == preserved
    blocked = ['exact bus-phase-slot numerical pairing', 'daily maximum residual identity',
        'nearest-rank Q99 numeric reproduction', 'same operational margin across B0-B3/all May days',
        'V41R1 May01 DayAhead/Fresh/Actual voltage and objective comparisons',
        'V41R1 May01 P0 pilot closure, B0-in-B1 and complete persistence gates',
        '124-unit margin propagation']
    write('V41R1_REGRESSION_REPORT.json', dict(status='PASS_FOR_AUTHORITY_STOP_SCOPE',
        tests=len(cases), failures=failures, skipped=skipped, junit=ref(junit),
        new_authority_stop_tests=sum('v41r1' in case.attrib.get('classname', '') for case in cases),
        inherited_V41_tests=sum('v41r1' not in case.attrib.get('classname', '') for case in cases),
        scientific_margin_tests_not_run_due_to_Section_3_stop=blocked,
        distinction='Passing audit/unchanged V41 regressions does not pass the unexecuted R1 margin pilot'))
    write('V41R1_FINAL_AUTHORITY_STOP_GATE.json', dict(status=STOP, full_May_launch_gate='FAIL',
        numerical_margin_frozen=False, new_DayAhead_runs=0, new_Actual_runs=0,
        base_implementation_commit=BASE, old_May01_files_reverified=len(preserved),
        reports=dict(pairing=ref(OUT / 'V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json'),
            regression=ref(OUT / 'V41R1_REGRESSION_REPORT.json'),
            background=ref(OUT / 'V41R1_BACKGROUND_LOAD_REGRESSION.json'))))
    text = f'''V41R1 감사 결과: `{STOP}`

사용자 지시 3항의 중단 조건에 해당합니다. 수정된 부하 매퍼와 현재 Planning 전압 정의를 함께 만족하는 5월 이전 Planning–Actual 정책-일 쌍을 찾지 못했습니다. 마진은 생성하지 않았으며 V41R1 5월 1일 재실행과 전체 5월 실행을 시작하지 않았습니다.

Git에서 제외되는 결과 디렉터리까지 포함해 세 저장소 루트를 조사했습니다. 과거 Actual 전압 배열은 51건입니다. 이 중 25건은 생산 시점 코드 매니페스트의 구형 매퍼 해시를 확인했고, 나머지 26건도 수정된 매퍼로 생성되었다는 증명이 없어 제외했습니다. 정책별로 B0–B3 각 10건과 R0 11건이며 독립적인 적격 표본으로 세지 않았습니다.

수정된 매퍼의 4월 자료는 4월 1·2·4·5·7·8·11·17일, 326개 Fresh 보정 상태와 125,836행 민감도 자료입니다. 이는 실현 Actual 전압이 아닙니다. V40A 4월 1일 ACTUAL_FIXED_REPLAY 역시 결정 해시 일치 게이트만 수행한 기록입니다.

| 요청 항목 | 확정 결과 |
|---|---|
| 1. 사용한 pre-May 정책-일 | 없음 |
| 2. N | 0 |
| 3. k | 미정(null) |
| 4. EPSILON_V_UP | 미정(null); 0으로 대체하지 않음 |
| 5. 새 V_MAX_PLANNING | 미정(null); 기존 과학 코드 변경 없음 |
| 6. 출처·해시 | Pairing audit, 후보 51건의 원본·매니페스트·매퍼 해시 저장 |
| 7–8. 새 B0/B1 DA·Fresh·Actual Vmax | 재실행하지 않아 없음 |
| 9. 새 전압 위반 수 | 미평가 |
| 10. 새 목적함수 벡터·차이 | 미평가; 기존 목적함수 구현 보존 |
| 11. 새 B0-in-B1 | 파일럿 미실행 |
| 12. P0-01..07 | 기존 V41 회귀시험 및 구현 동일성 확인; 신규 R1 파일럿 게이트 미평가 |
| 13. 부하 중복 | 실제 OpenDSS에서 합성 입력 96슬롯 × 3개 stage 표기 검증 PASS, 중복 0; 과학적 Actual 재실행과 구분 |
| 14. 회귀시험 | {len(cases)} PASS, 실패·skip 0; 미실행 마진 검증은 REGRESSION_REPORT에 별도 열거 |
| 15. 과학 커밋 | 기반 {BASE}; 마진 과학 freeze 없음. 별도 감사 커밋은 작업 결과에 기록 |
| 16. 전체 5월 실행 게이트 | FAIL, 실행하지 않음 |

기존 5월 1일 파일 {len(preserved)}개는 파일 목록·크기·SHA256을 다시 확인했고 변경이 없습니다. V41_EXPOSED_PRE_MARGIN_PILOT 표시는 별도 감사 기록에만 추가했습니다. 기존 캠페인은 상태 메타데이터상 FAILED이며 중지 요청도 기록되어 있습니다. 5월 2–31일 Actual 과학 결과는 열지 않았습니다.

필요한 추가 근거는 수정된 전기 모델·매퍼·정격과 현재 Planning 전압 정의 아래 생성된, 5월 이전의 완전한 96슬롯 Planning–실현 Actual 쌍 및 생성 출처입니다. 이번 지시는 기존 증거가 없을 때 중단하도록 명시하므로 새 보정 캠페인이나 임의 epsilon을 만들지 않았습니다.
'''
    (OUT / 'V41R1_AUTHORITY_STOP_REPORT_KO.md').write_text(text, encoding='utf-8')
    artifacts = []
    for path in sorted(OUT.rglob('*')):
        if not path.is_file() or path.name == 'V41R1_PERSISTENCE_READBACK_MANIFEST.json':
            continue
        if path.suffix == '.json':
            read(path)
        elif path.suffix == '.parquet':
            frame = pd.read_parquet(path)
            pd.testing.assert_frame_equal(frame, pd.read_parquet(path), check_exact=True)
        elif path.suffix == '.xml':
            ET.parse(path)
        else:
            path.read_text(encoding='utf-8')
        receipt = ref(path)
        assert sha(path) == receipt['sha256']
        artifacts.append(receipt)
    write('V41R1_PERSISTENCE_READBACK_MANIFEST.json', dict(status='PASS', artifacts=artifacts,
        file_count=len(artifacts), self_excluded_to_avoid_circular_hash=True,
        all_exist=True, all_SHA256_rechecked=True, all_formats_reopened=True,
        empty_residual_tables_have_explicit_schema_and_zero_rows=True))
    print(f'SEALED authority stop: {len(cases)} tests PASS; {len(artifacts)} artifacts reopened; {len(preserved)} old files unchanged')


if __name__ == '__main__':
    run()
