파일 SHA만 맞는 과거 Fresh PASS에 현재 Source 표지를 붙이는 경로를 닫았다. 현재 D0 계획 체크포인트에서 A1→M1→A2→M2의 FULL 수용, 부모 해시, P/Q/MESS 앵커, 원시점 및 Source bytes를 순서 검증한 뒤 A2/M2 조상을 얻는다. 사용 Native 원장은 별도 파일 SHA·승인 claim·Source/Case/parent·모델 binding·유한 비용·in-flight 해소를 확인한다.

정착 Gate는 실제 raw Fresh receipt와 16개/96개 slot rows를 다시 읽고 원본 측정 검증기를 적용한다. Actual 전용 Source freeze와 원시 trace도 재검증한다. Planning Case와 Actual evaluation Case는 구분하며 R1/R2/Source-strict, C0/C1, 16/96 범위는 canonical payload의 서로 다른 SHA를 갖는다. Actual 정책과 Native Planning 승인 정책을 혼동하지 않는다. ASOF substep FAIL은 공식 Global Gate를 차단하지 않는다.

Full production은 검증된 planning checkpoint를 별도 output에 복원해 이미 끝난 4단계 최적화를 반복하지 않는다. 새 예산은 검증된 단계만 cap 요구에서 제외하고 이전 사용 원장을 읽기 전용으로 보호한다. 현재 Case K48 포함성과 executor는 아직 인증되지 않았으므로 Full production은 계속 차단된다. Planning-only는 이를 선행 조건으로 요구하지 않지만 새 Native 승인과 각 단계 Original FULL을 반드시 요구한다.

현재 구현에 맞는 미승인 제안은 먼저 Planning 570초(단계 cap합480+반환30+overshoot60), 이후 현재 K48 packet 인증 뒤 별도270초(cap180+반환30+overshoot60)다. 두 상한합840초는 실행시간 예측이나 실제 사용량이 아니다. 이전750초 single-ledger 안은 원문 그대로 역사 자료로 보존하고 현재 분리 원장 승인의 근거로 쓰지 않는다.

A2 FULL 뒤 M1의 큰 케이스를 정상·복원 경로 모두 해제한다. 날짜별 finally에서 context/engine/result/case를 정리하므로 실패나 복원 오류도 다음 날짜로 큰 객체를 누적하지 않는다. 날짜 순서를 바꿔도 다른 날짜 실행에는 May01 Full96 원시 launch 증거가 필요하다. 각 날짜 Actual 정책을 local gate copy에 선택하며 다른 날짜 16슬롯 검증을 새 필수로 발명하지 않는다. 각 날짜 자체 A2/M2 FULL과 Actual96/Fresh96는 별도로 검증해야 한다.

새 검증 85개가 통과했다. 큰 모델 생성·최적화·Actual·AC는 이번 감사에서 모두 0회다. 원본 103개 보호 파일과 Source13·성공 A1·기존 Native0 실행 도구/결과·원장 bytes가 보존됐다. 실제 생산 import/후속 최적화/Actual96/Fresh96 실행 인증을 주장하지 않는다. 이전 보고와 Source snapshot은 덮어쓰지 않았다. 최종 cross-agent Source freeze는 Root가 Actual/private factory 동결 뒤 작성해야 한다.
