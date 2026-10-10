# SVR4/SVR7 엔진 증거 재현 안내

현재 실행 소스는 `ce30af2a74d9d2b6a2f2a33fee7a690927752f940f94bd466218075ba34cbf04`이다. 이 문서와 첨부 helper는 기존 동결 Planning P/Q·위치의 Actual 재생 및 저장자료 감사 범위다. 신규 Planning 모델 재생성·최적화·Planning–Actual E2E와 31일 전체 물리 PASS를 의미하지 않는다.

## Git 보존

`ENGINE_HELPER_REPRODUCTION_MANIFEST.json`에는 8개 helper의 원본·복사본 SHA256/길이와 권장 Git 경로가 있다. `HELPER_BYTES`는 실제 Python 원본 바이트를 보존한다. 현재 실행 SourceMap은 checkout 내부의 Python 파일을 포함하므로, 실행 중에는 helper를 checkout의 `.py` 파일로 추가하면 안 된다. Git에는 원본 바이트 그대로 `.py.txt`로 보존하고, 필요 시 외부 실험 디렉터리에서 `.py`로 복원한다. 과거 Source2cf helper는 고정 경로와 독점 출력 디렉터리, 동일 과거 SourceSHA 조건을 가진다. 최신 Sourcece30에서 과거 물리 작업을 자동 재실행할 권한을 부여하지 않는다.

## 읽기 전용 재검증

모든 출력은 새 디렉터리를 지정한다. 기존 출력이 있으면 helper가 중단한다. 아래 두 감사는 OpenDSS 엔진을 생성하거나 Solve·Native optimizer를 호출하지 않는다.

```powershell
python -B D:/v42_voltage_control_development_20261011/audit_svr_dispatch_pins_saved_01.py --source D:/v42voltage --root D:/v42_voltage_control_development_20261011/AC_ONLY_SVR4_SVR7_CANARY_03 --output D:/v42_voltage_control_development_20261011/READONLY_DISPATCH_PIN_GUARD_AUDIT_NEW

python -B D:/v42_voltage_control_development_20261011/audit_final_svr_time_current_saved_01.py --source D:/v42voltage --root D:/v42_voltage_control_development_20261011/AC_ONLY_SVR4_SVR7_CANARY_03 --output D:/v42_voltage_control_development_20261011/FINAL_COMMON_SVR_KNOWN_DATE_READONLY_AUDIT_NEW

python -B D:/v42_voltage_control_development_20261011/verify_frozen_svr_receipt_v2.py --source D:/v42voltage --freeze D:/v42_voltage_control_development_20261011/FROZEN_SVR4_INFRASTRUCTURE_06/HARDWARE_FREEZE_RECEIPT.json --receipt D:/v42_voltage_control_development_20261011/SVR4_COLD_AUDIT_NEW.json

python -B D:/v42_voltage_control_development_20261011/verify_frozen_svr_receipt_v2.py --source D:/v42voltage --freeze D:/v42_voltage_control_development_20261011/FROZEN_SVR7_INFRASTRUCTURE_02/HARDWARE_FREEZE_RECEIPT.json --receipt D:/v42_voltage_control_development_20261011/SVR7_COLD_AUDIT_NEW.json
```

첫 helper는 dispatcher가 선언한 소스·driver·queue·설비 동결 영수증과 실제 완료 작업의 동일 연결을 검증한다. 각 작업 원본 입력 영수증과 실제 완료 raw/audit 파일을 다시 hash하고 관찰 전후 바이트 일치를 확인한다. REF 파일은 dispatcher 최초 영수증에 별도 pin 항목이 없어 이 감사에서 두 번 관찰하며, worker의 Source archive가 실행 당시 바이트를 별도 보존한다. 이 제한을 영수증에 명시했다.

둘째 helper는 두 기존 알려진 날짜(2025-05-01 B2, 2025-05-28 B1)의 SVR4/SVR7 네 완료 작업을 요구한다. 초기 독립 DAYAHEAD/ACTUAL 문서와 원본 7개 RegControl 정적 설정, capacitor ON, 모든 실제 물리 solve 후 snapshot, 96 슬롯 순서를 검증한다. TIME 단계마다 직전 큐의 가장 이른 시각을 그대로 사용했는지와 `[start,end)` 경계 처리, 다음 슬롯 carry 및 실제 호출 수를 검증한다. iteration을 초로 변환하지 않는다. 원본 RegDelay 15초/TapDelay 2초와 신규 SVR Delay30초/TapDelay2초를 보존했다.

양단 전류는 저장 I(A)·native NormAmps 및 별도의 nameplate 기준을 재산출한다. 3상 정격 기준은 winding kVA/(√3×winding kV), 단상은 kVA/kV이며 추가 ×1000을 사용하지 않는다. native NormAmps는 원본 값을 유지하고 winding별 전압 변환만 검사한다. 모든 원본+추가 노드 전압과 양단 전류·변압기 kVA를 검사하며, 원본 raw386상 전압과 full-network 저장 전압도 일치해야 한다.

## 동결 설비 producer

`freeze_svr_infrastructure_v2.py`는 별도 승인된 소스 epoch에서만 사용한다. 기존 4기 V1 `.03` 영수증을 공통 predecessor로 사용한다. source·input scenario·output·variant·original-svr4-receipt CLI를 받으며, 4기 또는 7기 설치 후 독립 Fresh DAYAHEAD/ACTUAL 초기 readback을 저장한다. 런타임 SolveSnap0/Native0이고 초기 original compiler `CalcVoltageBases`의 zero-load 전압 base 계산은 별도로 유지·표시된다. 설비 초기 readback은 물리 96슬롯 PASS 또는 제조사 성능 인증이 아니다.

현재 동결 입력 및 결과:

- 4기: `FROZEN_SVR4_INFRASTRUCTURE_06/SCENARIO.json`, `HARDWARE_FREEZE_RECEIPT.json`
- 7기: `FROZEN_SVR7_INFRASTRUCTURE_02/SCENARIO.json`, `HARDWARE_FREEZE_RECEIPT.json`
- 공통 이전 4기: `FROZEN_SVR4_INFRASTRUCTURE_03/HARDWARE_FREEZE_RECEIPT.json`

기존 4기의 canonical unit DTO는 그대로이며 신규 3기는 BUS79/BUS108/BUS50이다. CapControl 또는 D-STATCOM을 사용하지 않는다. 원본 caps는 C83 600kvar 단일 step 및 C88A/C90B/C92C 각50kvar, 총750kvar로 모두 ON이다. 원본 7기 tap setter·control OFF·Planning 상태 복사 없이 원본 native AUTO가 TIME 큐를 처리한다.

## 결과의 물리 범위

현재 네 알려진 비교의 독립 저장자료 감사는 PASS다. 전류 arithmetic error와 원본 raw 전압 차이는 모두 0이었다. 이는 슬롯 종료 상태와 실제 큐 electrical solve snapshot 검사이며, 연속 waveform·열 transient 인증은 아니다. 전체 월간 단계는 대표 10비교 관문 이후에만 열리며 physical FAIL은 변경 없이 보존한다. 신규 모델 E2E는 `NOT_RUN`이다.
