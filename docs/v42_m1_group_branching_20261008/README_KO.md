# 완료 증거의 optimize=0 재현

실제 실행은 v42_group_branching.experiment의 spawn Worker 2개씩 최대3 pairs였다. 소비된 launch/child token을 삭제하거나 experiment를 다시 실행하지 않는다. 추가 solve는 승인 범위에 없다. Native scientific model/objective/bounds identity는 Worker별 MODEL_IDENTITY에, all9322 mapping은 CSV에 저장했다.

`python -m v42_group_branching.verify_saved`는 이 Git namespace만 이용해 original C3A+B2를 로드하고 저장된 exact dyadic support 전체를 CSR 독립 checker로 재검증한다. Native optimize는 명시적으로 금지한다. 과학 원본 배열과 ROUTE_TABLE은 SOURCE_IDENTITY에 지정된 SHA로 D: workspace에 준비해야 한다. authority 원본은 기존 scientific namespace에 보존되어 있다. README의 명령은 소비된 실험을 반복하지 않는다.

children/Cxx/z0와 z1의 RAW.npz, 원본 Pi, 별도 sign-cone/equality multiplier, exact payload, Native log, MODEL_IDENTITY, RESULT 및 resource receipt를 보존했다. Controller만 합친 pair 및 global min/max 결과는 FINAL_DECISION과 GROUP_GLOBAL_LB_COMPARISON에 있다. Absolute 실행 경로는 당시 receipt의 역사적 경로이며 verify_saved는 proof basename을 committed child 폴더로 안전하게 복원한다.

기존 saved-root equality repair와 옛1e-4 품질 FAIL은 변경하지 않았다. REVISED_EXECUTION_GATE와 사용자 반영 사전등록이 이를 diagnostic-only로 바꾼 후 실제 LP를 수행했다. 처음 optimize=0 자원 보류도 PRE_ADMISSION 기록에 보존했다. Actual parallel overlap과 CPU/RSS는 측정했으나 순차 baseline 및 memory bandwidth counter는 없어서 speedup/대역폭은 미측정이다. 다른 May12 작업과 같은 host였음을 숨기지 않는다.

SHA256_MANIFEST는 자기 자신을 제외한 모든 증거와 신규 source modules의 raw SHA256을 포함한다. GIT_COMPLETION은 최종 HEAD의 자기참조를 피하여 Git 밖 WORK/reports에 저장한다. 중간 산출물은 reports/checkpoints에 있으며 Python 새 writes는 D: WORK로 한정했다. 모든 production/P2/downstream calls는0이다.
