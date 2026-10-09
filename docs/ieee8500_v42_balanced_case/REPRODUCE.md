# 재현

부모 P5 commit 및 원본 데이터 SHA를 유지한 현재 branch에서 실행한다. Python3.11, NumPy1.26.4, SciPy1.14.1, pandas2.2.3, OpenDSSDirect0.9.4 / DSS-CAPI0.14.5가 기존 실행 환경이다. 새 원본 수집·normalization·Job/C1 생성 없이 부모 `.npz` 입력을 그대로 사용한다.

```powershell
python -B -m ieee8500_v42_balanced.audit before
python -B -m ieee8500_v42_balanced.audit audit
python -B -m ieee8500_v42_balanced.run_ac
python -B -m ieee8500_v42_balanced.precheck
python -B -m ieee8500_v42_balanced.verify
python -B -m ieee8500_v42_balanced.report
python -B -m ieee8500_v42_balanced.figures
python -B -m ieee8500_v42_balanced.audit after
python -B -m ieee8500_v42_balanced.seal
```

after snapshot은 실행 시의 기존 캠페인 등록·source/manifest를 읽기만 한다. 현재 작업의 쓰기·중단·Scheduler 변경은 허용하지 않는다. 다른 Worker의 외부 진행/추가 등록까지 정지시키거나 동일하다고 주장하지 않는다. 결과를 다시 만들면 다른 별도 출력 작업 트리에서 실행해 이번 sealed 결과와 SHA를 비교해야 한다. Native / B1–B3 Solver 호출은 없다.

96슬롯 전체 hard-axis archive는 `ac/BALANCED_{PLANNING,ACTUAL}[_FRESH]/AC_96.npz`이고 metadata는 AC_AXES.json이다. 전체 고객/두 레그/PV/PCC/전력수지는 CUSTOMER_PV_PQ_96.npz, 원본제어 궤적은 CONTROL_STATES.json/CSV다. 별도의 Fresh가 동일 byte input으로 새 context를 compile한다. 2025-05-01은 이미 노출된 날이며 미노출 holdout은 아니다.
