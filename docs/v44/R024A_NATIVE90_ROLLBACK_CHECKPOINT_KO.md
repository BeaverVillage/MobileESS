# r024a 정책 복귀 및 May02 B3 A2 체크포인트 승계

사용자의 최종 지시로 Native3600초, Phase I400/1000초 cutoff, UB-only 진입 정책을 취소했다. 수정 전 버전은 **r024a(알고리즘r024)**다. B1·B3의 모든 A단계를 다시 **총 측정 Native5400초, 별도 Phase I timeout 없음**으로 실행한다. Phase I zero·원본 P1 FullPricing·정수성·독립gap≤0.5% 및 원본 물리 검증을 유지한다.

**r024b는 r024a 알고리즘에 체크포인트 승계만 적용한 운영 어댑터**다. Adaptive의 후보 선택·확대·관측과 Rebuild 본문이 revision label 정규화 후 r024a와 같음을 확인했다. 원본 P1 본문과 acceptance를 바꾸지 않았다. 이후 미실행 B1/B3 A단계에 현재 A2 PASS 조건 없이 적용한다.

May02 B3 attempt010 A2는 이전 비용 **Native458.1179983615875초**에서 이어간다. 시계를0으로 초기화하지 않는다. 같은날 완료 A1/M1은 동일plan SHA로 재사용하며 새 A1/M1 최적화는0회다. 저장 master와 fingerprint가 일치하는 **활성행176887개**, 후보6회 확장, 고정 가중치, 최신 Raw에서 검증한 full-elastic 가능점 **Phi≈0.001542343** 및 Adaptive 탐색 이력을 복원했다. 인공변수가 없는 원본 가능해 인증을 이미 획득했다고 주장하지 않는다.

중간 복원 실행 attempt009는 row closure 후 Pricing roster 파일 누락으로 종료했다. 이를 숨기거나 성공으로 표시하지 않고 원본 RESULT·Raw·Native 원장을 보존했다. 새 output에 원본 `BLOCK_PRICING_ORACLE_VERIFICATION.json`을 복원하고 full-block cache138개 SHA를 확인한다. 원본 targeted의 roster 접근 경로를 Native0 시험으로 확인했다.

회귀270개 PASS. 저장 LP fingerprint 및 이전 full-elastic 가능점 재검산도 Native0 PASS다. 새 Worker는 Native5400 원장과 별도 Phase I 제한없음으로 실제 시작했다. 기존 PASS/A1/M1 및 자연종료한 May05 B0 PASS를 보존했다. 시간별 자동점검과 Windows 독립 supervisor도 복귀 정책으로 갱신했다.

## 5월 1일 비교

| 단계 | Phase I Native | 구성 |
|---|---:|---|
| B1 A1 | 49.1469996초 | Phase I LP17회, 기존 완료결과 재사용 |
| B3 A2 | 873.6390002초 | LP866.6170001초/21회 + 후보탐색7.0220001초/37회 |

B3 A2 값은 May01 attempt002의 원장에서 첫 ORIGINAL_P1 전 호출을 합산했다. B1은 Golden B1 attempt003의 A_NATIVE_CALLS에서 첫 ORIGINAL_P1 이전 호출을 합산했다. Native Runtime과 전체 Wall Time은 다르다.
