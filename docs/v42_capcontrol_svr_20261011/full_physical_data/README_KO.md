# 전체15경로 Actual 물리 자료

Source `ce30af2a74d9d2b6a2f2a33fee7a690927752f940f94bd466218075ba34cbf04`의 완료된 5개 arm/day 사례를 REF_TIME·SVR4·SVR7별로 구분한 총15경로, 각96시간순 슬롯 자료다. 전 경로를 동일 원본 영수증으로 검증했고, 신규 OpenDSS·Native·Planning 실행이나 원본 수치 보정은 없다.

| 자료 | 전체 데이터 행 | 파일 |
|---|---:|---|
| 모든 원본·추가 node-phase 전압pu | 571,680 | VOLTAGES.csv.gz |
| 모든 Line/TX 양단 phase 전류A·nativeNorm·독립nameplate | 1,134,720 | CURRENTS.part001..005.csv.gz |
| 모든 TX 양단 terminal 전체상 apparentkVA·winding정격 | 158,400 | TRANSFORMER_KVA.csv.gz |

각 파일은 30,000,000바이트 이하이고 현재 최대8,924,841바이트다. 전류는 최대250,000행 조각으로 나눴으며 각 조각이 같은 header를 갖는다. manifest의 순서대로 이어 읽으면 완전한 단일 전류 표가 된다. `FULL_PHYSICAL_EXPORT_RECEIPT.json`은 정확한 SHA/길이, 압축해제 CSV SHA/길이, 15경로별 행 수·축 SHA와 모든 입력 영수증을 포함한다. 모든 CSV 필드를 원본과 다시 비교했으며 모든 gzip을 독립 재압축해 바이트 동일성을 검증했다.

정렬은 day, arm, REF_TIME/SVR4/SVR7, slot0..95, 원본 native 물리 축 순서다. SourceSHA·ScenarioSHA·configuration·arm·day·namespace·slot0/slot1·dateTime_AEST·native_last_solve_seconds가 각 행에 포함된다. float는 원본 JSON의 binary64 수치를 반올림 없이 보존하고 `float.hex` roundtrip을 확인했다. `original`/`added`는 명시적 Boolean이다.

`dateTime_AEST`는 원본15분 interval 종료 표시(UTC+10)다. slot0는 당일00:15, slot95는 다음날00:00이며 `native_last_solve_seconds`는 슬롯의 마지막 electrical solve 시각을 당일 절대초로 표시한다. 이후 큐 이벤트가 없는 시간에는 같은 슬롯의 고정입력 상태가 유지됐다. 연속 waveform·열 transient 인증은 아니다.

전압은 REF_TIME386상/SVR4398상/SVR7407상이고, 모든 양단 전류는 각각766/790/808개 terminal-phase다. 실제 원본 native Transformer는 44개(36 PCC service+7원본 Reg transformer+xfm1)이므로 전체 TX 양단 kVA는 슬롯당88/112/130개다. 원본 transformer-phase120개는 service108상+원본Reg9상+xfm1의3상으로 구성된다.

Line에는 winding kVA/kV 또는 독립 Transformer nameplate가 적용되지 않아 관련 필드가 비어 있다. 빈 값은 0이 아니다. 저장 자료에는 Line terminal P/Q/kVA가 없어 이를 추정해 추가하지 않았다. TX kVA는 전체 존재 상의 합산 terminal S이며 per-phase S가 아니다. 독립 nameplate current는 3상 kVA/(√3×kV), 단상 kVA/kV이고 추가 ×1000이 없다. native NormAmps는 변경 없이 함께 보존했다.

위반 flag는 기존0.95≤V≤1.05와 loading≤1을 사용한다. Physical FAIL 값도 그대로 포함한다. 내보내기 PASS는 완전성·값/바이트 재현성을 뜻하며 모든 전기제약 PASS를 뜻하지 않는다. 기존 동결 Planning의 Actual-only 범위로, 신규 Planning 모델·최적화·E2E는 `NOT_RUN`이다.

`EXPORT_SCRIPT_USED.py`는 실제 실행한 정확한 원본 바이트다. 아래 명령은 새 빈 출력 디렉터리에서만 재현한다. Python 표준 라이브러리만 사용하며 실행소스 import/DSS engine 생성/optimizer를 하지 않는다.

```powershell
python -B EXPORT_SCRIPT_USED.py --source D:/v42voltage --root D:/v42_voltage_control_development_20261011/AC_ONLY_SVR4_SVR7_CANARY_03 --output D:/v42_voltage_control_development_20261011/SVR7_CE30_FULL_PHYSICAL_DATA_EXPORT_NEW
```

상위 폴더의 첫 단일 전류 gzip은 30MB 제한을 넘어 실패한 출력으로 별도 보존돼 있다. 최종 유효 자료와 PR 대상은 이 `VALIDATED_EXPORT` 폴더다.
