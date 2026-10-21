V2_add를 V44 r043 (`affc7226a519adbe072d7debbc3ae25ea71c3487`)과 별도의 IEEE8500 Balanced / AIDC12 / STA12 / MESS8 확장실험으로 등록합니다. 독립 브랜치·worktree·runtime·감사 원장을 사용하며 기존 V44/V1_add/IEEE8500 연구 소스, Worker, Monitor, 예산 및 결과는 변경하지 않습니다.

PR #197의 공식 계통 31개 파일을 Git 원본 바이트로 복원하고 OpenDSS에서 8,531 전기 노드·3,703 선로·1,177 Triplex·1,190 변압기를 확인했습니다. May01~07 권위 검사 190행(고유 path/SHA 쌍 135개)과 PR #235 May01 동결 전력 배열 16개가 모두 일치합니다. 원본 alpha_BG=1.15는 재적용하지 않았습니다. 최종 Window 권위상 시간 이동 허용 Job 1,024개와 raw Native mask를 구분하며, 이를 실제 피크 kW 제어량으로 해석하지 않습니다.

후보 beta_BG 1.00~1.50 및 B0·MV/LV·실현 가능한 pilot 중심의 선정/동률 규칙을 먼저 등록했습니다. PR #199 C2 PCC24는 사전 고정된 후보로만 복원하고, 원본 4대 초기 STA를 유지한 8대 초기상태 후보와 기존 route service ID 연결을 기록했습니다. 6대·450 kW 모델은 사용하지 않았습니다.

**현재 상태: NO_GO_PENDING_PREFLIGHT / INPUT_MAPPING_NOT_VERIFIED.** PV 전압/상/인버터 이전, P300/Q250/PCS400 포트 및 8대 동시 접속, IEEE8500과 V44 Planning/Actual 전압제어 계약의 독립 검증이 남아 있습니다. 기존 V44 프로세스와 heavy-worker lease도 활성 상태입니다. 운영 B0 96슬롯, Scale screening, 민감도/pilot, Native 최적화는 실행하지 않았고 Primary Scenario는 동결하지 않았습니다. 미실행 수치는 빈 값과 NOT_VERIFIED/사유로 보존합니다. 이는 적격 시나리오가 없다는 실측 판정이 아닙니다.

검증: 독립 저장 산출물 무결성/보존 검사 59개 PASS, 원본 r043 추적 파일 변경 0. 공식 Master의 CalcVoltageBases 및 source inventory용 명목 snapshot은 운영 입력 AC와 구분합니다. 전체 원본 3,703개 선로를 그린 topology와 PCC 후보 SVG/PNG를 포함하며 측정자료가 없는 성과 그림은 생성하지 않았습니다.

진입점: `docs/v2_add/README_KO.md`; 상세 상태: `FINAL_V2_ADD_REVIEW_KO.md`, `FINAL_GO_NO_GO.json`; 재현: `python -B -m v2_add_preflight.audit`, `figures`, `verify`. Runtime venv는 별도 경로이며 읽기 전용 system site packages를 상속합니다. 완전한 vendored 환경이나 알고리즘 이식 완료를 주장하지 않습니다. 연구 진행 기록용 Draft이며 merge/Production 승격을 요청하지 않습니다.
