# PR 원본 방법 재사용 감사

| PR | 확인 HEAD | 사용 범위 |
|---|---|---|
| [187](https://github.com/BeaverVillage/MobileESS/pull/187) | `e67ecfa827e4262c2f2df17c226d6442656af18b` | Injection P/Q stationarity support 손실과 raw sign 실패의 역사적 원인. 값 전용 없음. |
| [202](https://github.com/BeaverVillage/MobileESS/pull/202) | `a5ce8685eb694f750dca7a539d010eece38ece37` | 원래 등식 유도 finite envelope와 sign-cone/box 인증 원칙. 기존 코드/보고서 원본 Git object 읽음; 숫자 이전 없음. |
| [203](https://github.com/BeaverVillage/MobileESS/pull/203) | `1535584eaea7162931642878a6a9728b4988bb6f` | 완전96-slot integer trajectory support와 탐색 가격/인증 가격 분리. 원본 adapter/pricing/보고서 읽음; 기존 가격·LB 이전 없음. |
| [209](https://github.com/BeaverVillage/MobileESS/pull/209) | `9383a99f1bdcabbd49c79b3ad9f9ee36d523868a` | 모든 단일 차량 FULL 물리 행/Bounds/types, exact helper 소거, A0 네 인증값 재사용 및 현재 행렬 재대조. |
| [210](https://github.com/BeaverVillage/MobileESS/pull/210) | `6a8fd44f59f1f461c60d2d14f5f5be605e4ed640` | 4-MESS Joint16 및 exact Compact proof. 원본 그대로 보존. |
| [211](https://github.com/BeaverVillage/MobileESS/pull/211) | `d12315a3757aec187c8da0685c28ef901466386a` | K48 포함관계·외향행 및 수치 Global Bound 재사용; current FULL 수치 영역 동일성 확인. |
| [214](https://github.com/BeaverVillage/MobileESS/pull/214) | `40ab888b884255e76fd6c89fd01933570b60c242` | 기존 BASE Point/CSR/Pi/RC 검증 후 Original 좌표 복원. 기존 단일 SOC cut을 반복하지 않음. |
| [215](https://github.com/BeaverVillage/MobileESS/pull/215) | `6ca7624d7eafd45d5b061ff33e262b0de32bfe8d` | Snapshot/Window 약한 하한의 부정적 결과. 시간 분해로 실험을 대체하지 않음. |
| [220](https://github.com/BeaverVillage/MobileESS/pull/220) | `b9684fa0999b88092d0cd38229f3453ef3f901b4` | 보호할 FULL Moving UB와 원본 Raw/DAG. 새 UB 탐색 없음. |
| [221](https://github.com/BeaverVillage/MobileESS/pull/221) | `a874df15b9a306a7d769a60622b40fb76de3ffcc` | 별도 승인 연구1790.197s 원장 보존, 새 PR222 원장과 실행 범위 구분. |
| [222](https://github.com/BeaverVillage/MobileESS/pull/222) | `12594e281bb89611331950f11f775a2612d3cb48` | 수치적 FULL/Dense 동일 문제와 incumbent registry, 현재1003.501s prefix, HOLD 연구 기준. |

HEAD 정정 필요 없음. PR222 위 별도 Research worktree만 변경했다. 다른 PR을 cherry-pick하지 않았다.
PR202/203/187은 Git fetch된 원본 보고서 및 코드를 읽었다. Source18r helper 포함관계는 현재 전체 FULL CSR/domain과 저장 slice를 독립 재대조했다.
