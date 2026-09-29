# 재현 및 증거 검증 순서

기준은 PR #89의 `c84588e02727eb5311ba25f6a3ed43ff229cfe07`이다. 기존
V6–V15의 로컬 모델·행 단위 예측과 원본 데이터가 필요하다. Git 저장소만으로
대용량 원본이나 `.local` 증거가 제공되지는 않는다. 각 경로·크기·SHA256은
SOURCE_MANIFEST, LOCAL_EVIDENCE_MANIFEST, BASE_PRESERVATION_RECEIPT에 기록한다.
완료된 디렉터리에서 준비/사전등록 스크립트를 다시 실행해 증거를 덮어쓰지 않는다.

Runtime과 native는 MODEL_FAMILY_DECISION.json의 고정 Python 환경을 사용한다.
CC4 모델 학습은 실제로 authorization이 열렸을 때에만 기존 NumPy 1.26.4
환경을 사용한다. 환경을 바꾼 재실행은 원 결과의 재현으로 간주하지 않는다.

1. `prepare16.py`, `audit16.py`, `authority16.py`, `inspect_embedding16.py`로
   기준 보존 영수증과 원본 필드·권한·배포 좌표를 감사한다.
2. `crosswalk16.py`, `mapping_supplement16.py`, `population16.py`로 유일한
   연구용 연결과 기존 GPU 검증 모집단의 교집합을 확인한다. 원래 partition
   namespace 비교 오류와 UTC 경계 assertion의 최초 산출물도 보존한다.
3. `register16.py`가 생성한 초기 PREREGISTRATION과 코드 SHA는 변경하지 않는다.
   실행 경로 정정은 EXECUTION_ROUTING_CORRECTION에 별도로 공개돼 있다.
   이는 일부 결과 이후의 정정이며 전체 과정이 무수정 사전등록이었다고 주장하지 않는다.
4. `train_native16.py 1`, `2`, `3`으로 primary 및 고정 대비·대조군을 실행한다.
   `embedding16.py`는 별도 동일 표본 진단이다. `collect_native16.py`와
   `collect_native16.py embedding`이 저장 예측에서 지표를 재집계한다.
5. `ablation16.py`는 원 D1–D4의 조건부 제거 진단이다. `paired_ablation16.py`와
   `stack_ablation16.py`는 사용자 material-win 조건을 만족한 추가 대비의
   공개된 진단 확장이다. 각각의 실행 freeze를 확인하며 primary 기준을 바꾸지 않는다.
6. native 동결 이후에만 `bridge16.py`가 authorization을 검사하고 R16-A/B/C의
   기존 5-fold를 실행한다. `bridge_replay16.py`가 모델·receipt·이웃을 재생하고
   `collect_bridge16.py`가 선택과 CC4 authorization을 동결한다.
7. CC4가 승인된 경우에만 `cc416.py prepare`와 정확한 CC4 환경의
   `cc416.py run`을 실행한다. C4도 C3 development 조건을 통과해야 실행된다.
   C0는 T0/B0이며 target, 시간해상도, 모델 계열을 변경하지 않는다.
8. `replay16.py`는 native의 새 프로세스 예측·이웃 재생이다.
   모든 증거 writer가 종료된 후 `finalize16.py`, `verify16.py`를 실행한다.
   검증기는 이전 파일 hash, 원본 fingerprint, 모든 선택 이웃의 완료 시점,
   지표 재집계, 모델/예측 SHA, 집중 테스트와 전달 manifest를 확인한다.

TOTAL 통과가 발생하면 `finalize16.py`는 의도적으로 중단한다. 그러한 결과에
대해 필요한 remaining/provider/April 절차를 생략한 채 완료로 표시하지 않기 위함이다.
May 2025 payload는 모든 경로에서 봉인한다. SOURCE_MANIFEST의 ZIP SHA 계산은
압축 파일 바이트 검증이며 May member의 압축 해제·해석이 아니다.
