# V42 Problem 4 구현 및 과학적 검토

**판정: NOT CLOSED — V42_PROBLEM4_REFERENCE_PLACEMENT_READY = FALSE.** Episode 연속성 구현과 독립 worker 검증은 완료했지만, 전체 reference의 서비스·용량 권위가 통과하지 않은 상태를 배포 가능하다고 선언하지 않는다.

1. **같은 UID가 여러 날짜에 나타나는 이유는?** D−1 issue마다 이미 제출됐고 아직 완료가 관측되지 않은 작업을 다시 snapshot에 담기 때문이다. 이것만으로 새 실행 attempt라는 뜻은 아니다.
2. **Episode 정의는?** 관측된 제출 식별정보와 동일 source record를 갖고 인접 snapshot에서 모순 없이 이어지는 실행이다. 명시적 attempt 증거가 있을 때만 새 attempt를 만든다. Raw에 없는 requeue/attempt 경계를 추정하지 않는다.
3. **같은 episode의 site는 유지되는가?** 연결된 episode 35,271개, 인접 연결 136,811건에서 설명 없는 변경은 0건이다. 양쪽 site가 존재하는 연결 54,685건과 할당 불가/미해결 연결 82,126건을 분리했다. 미할당을 site 유지 성공으로 세지 않았다.
4. **기존 5,661/531 현상은?** 기존 비교 모집단은 multi-day RUNNING UID 5,661개/여러 site 531개였다. 새 ledger의 할당된 multi-day RUNNING episode는 3,417개이며 여러 site를 가진 episode는 0개다. 모집단이 같다고 주장하지 않는다. 전체 242,842개 snapshot row를 보존했으며 미할당 133,977건과 실패 상태를 함께 보고한다.
5. **Apr1 PENDING→Apr2 RUNNING의 87개 변경은 사라졌는가?** 새 source-backed 비교는 104건, 설명 없는 변경은 0건이다. 양쪽 모두 site가 있는 것은 104건이다. 기존 변경 87개 UID는 모두 같은 새 episode/site로 연결됐고, 87개 모두 양쪽 row의 capacity 검증을 통과했다. April1/2 전체 day state도 각각 PASS다. 이 두 날짜의 회귀 문제는 해결했지만, 전체 412일의 자원 gate 통과와는 구분한다.
6. **Continuity 때문에 capacity violation이 생겼는가?** 전체 서비스 sweep에서 site/time 구간 위반 321건, rack compatibility 위반 0건이다. Gang splitting은 0건이다. 정확한 episode/site/time/GPU는 REFERENCE_CAPACITY_RACK_AUDIT.csv에 있다.
7. **원인과 처리는?** 고정된 합성 site에서 다음 causal 상태의 서비스 의무가 겹치는 문제와, 여전히 PENDING인데 이전 예약 시작이 지난 문제(28,025 job-day)가 있다. Pending 예약을 임의 재설정하지 않았고 continuing site도 옮기지 않았다. 충돌 때문에 신규 할당을 보류한 행은 57,125건이다. 전체 412일 중 실행 가능한 reference state는 225일이다. 현재 요청 duration에 의존하는 결과이며 runtime을 대체하여 해결하지 않았다.
8. **같은 UID의 새 episode가 새 site를 받을 수 있는가?** 그렇다. causal attempt authority가 있을 때만 가능하며 단위 테스트로 확인했다. 현재 raw regression에는 그 필드를 만들어 넣지 않았다.
9. **V38과 차이는?** 전 기간 UID마다 영구 home을 정하는 전역 모델이 아니다. 새 episode 최초 배치 후 연속된 같은 episode의 의무만 보존한다. 공백 뒤 재등장도 자동 영구 home/자동 새 episode로 처리하지 않는다.
10. **Initial placement와 migration은 분리되는가?** Reference는 합성 baseline, PENDING의 eligible site 선택은 initial placement, 실행 후 checkpoint/WAN/restart에 따른 변경은 migration이다. 이번 reference에 migration을 넣지 않았고 D-day migration을 활성화하지 않았다.
11. **Spatial/temporal은 독립적인가?** 그렇다. spatial_eligible과 nullable temporal_eligible_if_authorized를 따로 기록한다. 동일 April1/2 resource-valid PENDING 453건에서 새 spatial 자격 91건/고정 362건으로 기존 공간 자격이 유지됐다. April 전체 30일의 새 spatial 자격 row는 1588건이며 별도 모집단이다. V42 R0 시간 권위는 계속 미확정이고 시작 범위를 넓히지 않았다.
12. **RUNNING initial site를 바꿀 수 있는가?** 불가하다. 새 경계 guard에서 391,523개 변경 시도를 거절했다. 기존 V42 validator/source도 보존했다. 허용 mutation option은 0개다.
13. **Four-worker 독립성은?** 네 개의 독립 OS process에서 각 날짜의 freeze slice만 읽었다. 정순/역순/무작위/병렬의 412일 hash가 모두 같다. 차단된 날짜는 audit_only로 재현했고 실제 소비 API는 거절한다.
14. **다른 날짜 optimizer 결과를 읽는가?** 아니다. 이전 reference 의무는 policy-independent 사전 생성기의 상태일 뿐이다. Daily worker는 다른 worker 결과를 읽지 않는다.
15. **Grid/May/future outcome을 사용했는가?** Reference 생성기에서 모두 0개다. 관측 가능한 UID/제출/요청/상태/elapsed 기반 기존 duration과 고정 자원 권위만 사용한다. Archive hash도 배치 seed에서 제외했다. May 정책 효과 평가나 Fresh AC를 실행하지 않았다.
16. **Unknown reference 차이는 물리 상태인가, label 오염인가?** 기존 April2 P0/P1의 공통 admitted 2340건 중 site 차이 1586건이다. 차이가 있는 UID 32개를 사전 고정 방식으로 표본화하여 양 정책의 물리 점유를 재구성했고, 순수 reference 함수 결과와 비교했다. PHYSICAL_STATE_DEPENDENCE 관측 64건, 미해결 0건, policy identity contamination 0건이다. 이전 selected action은 이 별도 감사에서 점유 재구성에만 사용했고 canonical builder에는 입력되지 않았다.
17. **논문 의미는?** Kestrel job/workload 속성은 관측 자료, 12개 AIDC/PCC와 logical rack/site 배치는 모델, PENDING initial placement 및 유효 checkpoint migration은 최적화 결정이다. Kestrel job이 실제 그 12개 시설에서 왔다고 쓰면 안 된다. 이번 전체 ledger는 자원 gate가 막혀 있으므로 전체를 capacity-feasible이라고 부를 수 없다. 논문 본문은 작성하지 않았다.
18. **Problem 4를 CLOSED로 볼 수 있는가?** 아니다. 구현·재현성은 확보했으나 continuation 서비스 의무의 권위 충돌/자원 불가 상태가 남아 있다. source-backed 서비스·상태 reconciliation과 물리 용량에 맞는 원천 권위가 필요하다. Runtime/시간 유연성/용량을 임의 변경해 통과시키지 않았다.

## 전달 범위

- 회귀 테스트: `.....................                                                    [100%]
21 passed in 0.14s`
- 원본 보호 검증: 646개 파일 hash 불변.
- 분리 worktree/branch: `codex/v42-r0-aidc-reference-episode-continuity`.
- Runtime/CC4/MESS/전기 kernel·trust·epsilon 변경 없음. PR #77 및 runtime feature branch 의존 없음.
- 412일 canonical ledger, source/schema/freeze, 충돌/연속성/자격 ledger, 4-process hash, 이전 forensic 사본 및 negative verdict를 함께 전달한다.
- Draft PR은 미통과 결과를 명시한다. Native V42 및 unknown control은 활성화하지 않는다.
