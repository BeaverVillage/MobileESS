사용자의 2026-10-11 추가 지시에 따라 기존 Epoch15 May01 실행을 중단하고 B2 May01/May02를 새 Native0 실행으로 재시작한다. 중단된 시도의 Native ledger와 로그는 원래 경로에 보존한다.

날짜별 C2 transport 및 C3A independent certificate replay를 생략한다. 기존 Epoch15 대표 모델의 검증·실제 Native 증거를 원래 Source SHA로 유지하고, 새 소스에서 모델 생성 알고리즘이 달라지지 않았음을 AST 비교로 확인했다. 기존 검증 결과의 Source SHA를 새 실행 SHA로 바꾸지 않는다.

날짜별 원시 입력·Forecast·모델 행렬·경계는 해당 날짜 기준으로 생성한다. PCS/Farkas 감소와 affine support 경계 생성 알고리즘은 유지한다. 최종 가능해의 원본 FULL 제약 검사 및 결정 동결 이후 Actual Fresh OpenDSS 96슬롯은 유지한다. 새 독립 증명을 수행하지 않은 receipt에는 independent_model_proof_replayed=false를 기록하며, selected_C3A_independent_proof_PASS는 null이다.

B2 최대 2 Worker, M 누적 Native 1800초, 전체 Solver gap 목표 3%, U4 제한 bound의 전체 LB 사용 금지, A단계 예산과 B3 단계 Barrier를 유지한다. 메모리 입장은 Worker당 7 GiB 및 시스템 1 GiB 예비량으로 RAM/Commit을 확인하며, 메모리가 부족하면 신규 입장만 대기한다. 새로운 프로파일의 최대 메모리 감소량은 측정하지 않았다.

검사: 증명 생략 모드의 권한·SHA 변조 거부와 기본 모드 보존을 포함하여 24 tests passed. 추가 모델 증명·Solver smoke·전수 재검증은 실행하지 않았다.
