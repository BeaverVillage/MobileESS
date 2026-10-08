# V42 M1 Anytime 연구 — 사용자 요청 중단 및 PR 마감

사용자 지시에 따라 진행 중인 신규 Anytime 실행만 중단했다. 75분 Frontier는 완료하지 않았다. 기존 실험·production·다른 프로세스는 변경하거나 중단하지 않았다.

동일 May01 / 1499 jobs / 4 MESS / 24 sites / 96 slots, Case SHA `cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a`, baseline `e26790e9f10217fb8f5a3cecddb1e578b879efb7`에서 시작한 warm-start 후속 연구다.

- 시작 Gap 4.4289785520% → 최종 독립 검증 Gap **2.9759626222%**.
- Strict integer UB **0.5860861758345995**, 감소 0.0089105728583642.
- Exact Global LB **0.5686444703080522**, 증가 0. UB의 개선이며 LB strengthening 성공으로 주장하지 않는다.
- 4% / 3.5% 최초 인증: 1.109088분. 3% 최초 인증: 24.876206분. 인증 완료 시각 기준이며 callback 발견으로 소급하지 않았다.
- 완료 26회 Native Runtime **506.786초**, Work **1026.277437**. 중단된 27번째 호출의 정확한 Runtime/Work는 미확보다. 해당 호출의 배정 300초를 보수적으로 소비 예산에 포함하여 **806.786초**를 계상했다. 이는 정확한 총 Runtime으로 주장하지 않는다.
- 10분 목표는 실제 11.3524분 관측, 20분은 실제 20.0001분 관측이다. 30/40/60/75분은 사용자 중단으로 NOT_OBSERVED. 2.5/2/1.5/1/0.5%는 NOT_REACHED이며 불가능성 증명이 아니다.
- 회귀 **680 PASS / 12 SKIP / 0 FAIL**; 기존649 PASS를 보존했고 SKIP은 PASS로 세지 않았다. 마감 검증 Native optimize=0.
- 마지막 공개·검증된 RAW만 새로 C3A/FULL 전체 binary literal0/1·전체 matrix·Route/SOC/PQ/PCS/grid에서 replay했다. 중단 호출의 더 낮은 잠정 후보는 채택하지 않았다.

## 연구 결과와 한계

U4 충·방전 시간·SOC 연결을 활용한 neighborhood가 인증 UB 개선을 만들었다. 반경·시간창은 사전등록 값에서 바꾸고 모든 원본 행을 보존했다. 최신 궤적의 RMP feedback은 실행했지만 해당 L2 가격의 candidate LB는 기존 최고값보다 낮았다. L3 rational dual mixing도 LB를 높이지 못했다. L4 정수 Pricing은 exact integer closure=NOT_PROVEN이다. 제한 RMP 목적값과 Native BestBd를 Global LB로 쓰지 않았다.

첫 실행의 RMP ledger `track` 인수 호환성 오류는 source archive·실패 receipt와 함께 보존했다. 새 연속 구간은 최초 T0와 모든 완료·실패 비용을 승계했다. 사용자 중단까지 오류 복구 비용을 포함한 동일 Wall을 유지했고 예산을 재설정하지 않았다. 현재 연구는 75분 비교, 40/60분 실용성 또는 75~90분 추가 탐색의 이득을 판단하지 못한다. 이전 C와 동등한 새 대조군도 없으므로 일반적 우월성을 주장하지 않는다. 3% warm-start 최초 인증은 이 May01 사례의 성과이며 May12/A2/M2로 전용하지 않는다.

P2=null, M1_ACCEPTED=false, production 기본 backend와 historical input/ledger는 보존한다. 원래 A186/M188/C3A162와 공통 물리 authority를 변경하지 않았다. 모든 개발·임시·cache·검증·commit 경로는 D:\MobileESS_v42다. C 데이터·repo는 읽기 전용이다.

CSV·SVG는 실제 인증 완료 시각만 사용한다. 미관측 future checkpoints를 채우지 않았다. 독립 최종 검증 Wall과 모델 생성·pricing·replay·exact checker·회귀는 RUNTIME_BREAKDOWN.json에 별도로 기록했다. 과거20.109분·549.057초는 신규 시간에 더하지 않았다.
