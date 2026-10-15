기존 PR230의 후속 검토 자료다. 과거 보고서와 결과는 그대로 보존했다.

- [25개 질문과 최종 검토](FINAL_UNIFIED_REVIEW_KO.md)
- [최종 검증 Gate](FINAL_VALIDATION_GATE.json)
- [Source/Case 분리](COMMON_SOURCE_CASE_MANIFEST.json)
- [AIDC 검토](AIDC_FINAL_REVIEW_KO.md) · [MESS 검토](MESS_FINAL_REVIEW_KO.md)
- [회귀](UNIFIED_REGRESSION_RESULTS.json) · [원장](UNIFIED_NATIVE_LEDGER.json)

실제 May01 C0/C1/C2와 Full96 Fresh AC는 NOT_RUN이다. Runtime과 전력계수 Fixture 수치를 실제 May 개선으로 쓰지 않는다. 새 연구 기본 Case/Science 계약은 이 디렉터리의 SHARED_SOURCE_CASE_MANIFEST와 UNIFIED_INTERFACE_CONTRACT다. build_current_event_case가 이 계약을 사용하며 별도의 인증된 Dday Handoff를 요구한다. 기존 상위 디렉터리의 FCFS 진단 계약은 역사적 재현용으로 보존한다.

대형 Source archive·원본 CSR·LP Point·Native Log는 로컬 runtime과 기존 원본에 보존하며 JSON에 SHA/경로를 기록했다. PR clone만으로 모든 원본 실제 데이터가 제공된다고 주장하지 않는다.
