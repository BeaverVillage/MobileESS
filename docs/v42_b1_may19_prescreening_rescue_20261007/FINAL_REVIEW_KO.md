# May19 practical prescreening rescue

1. 시작 도메인은 S38: 확장 클래스 26개, 같은 사이트 시작 옵션 38개이다. 기존 Method1 LP600초 TIME_LIMIT 기록을 보존했다.

2. LP feasible shell 없음. 네 raw LP 점 모두 원래 전체 행·bounds replay를 통과하지 못했다.

3. MIP feasible shell 없음. LP gate 미통과로 정수 MIP는 실행하지 않았다.

4. S38 대비 추가 클래스 0개. S0 대비 복원 대상으로 유지한 클래스는 26개이다.

5. S38 대비 같은 사이트 옵션 +48개, 마지막 테스트 shell의 누적 같은 사이트 옵션 86개이다.

6. 사이트/PRESTART 옵션 +64개이다.

7. 원래 허용된 migration 경로 옵션 +128개이다. 새 migration 과학적 권한은 만들지 않았다.

8. raw 변수: S38 2,739,814 → 마지막 테스트 S_D 2,741,385, 증가 1,571. S38 compressed 2,684,543을 분모로 한 추가량은 0.058520%이다.

9. binary: S38 930,864 → 마지막 테스트 S_D 931,507, 증가 643. S38 compressed 929,270을 분모로 한 추가량은 0.069194%이다.

10. raw 행: S38 3,734,330 → 마지막 테스트 S_D 3,735,529, 증가 1,199. S38 compressed 3,028,072을 분모로 한 추가량은 0.039596%이다.

11. raw nnz: S38 27,751,453 → 마지막 테스트 S_D 27,767,366, 증가 15,913. S38 compressed 18,247,889을 분모로 한 추가량은 0.087205%이다.

12. CC4 변경: NO.

13. 전압 한계 변경: NO (0.95–1.05 유지).

14. GPU 용량 변경: NO.

15. Runtime/서비스 변경: NO.

16. 미래 정보 사용: NO.

17. 정수 witness 미확보. 정수 MIP 미실행.

18. 정수 해의 original full replay 미실행. raw LP 네 점의 original full replay는 모두 FAIL이다.

19. rho: 정수-feasible gate 미통과로 정상 production 미실행.

20. migration objective: 미실행.

21. shift objective: 미실행.

22. prestart objective: 미실행.

23. Planning freeze: 미실행.

24. Actual/Fresh: 미실행. Actual/PQ 재최적화 없음.

25. Fresh 물리 위반 개수는 판정하지 않았다. Fresh/정수 검증 자체가 미실행이며, LP 잔차를 물리 검증 PASS로 처리하지 않았다.

26. 최종 분류: MAY19_PRESCREENING_UNRESOLVED. 전체 물리 후보 집합의 불가능성을 증명한 결과가 아니다.

27. 최종 commit / Draft PR는 PUBLICATION_RECEIPT.json과 최종 전달에 기록한다.

위 옵션 수와 마지막 census는 선택된 production 도메인이 아니라 계획상 마지막으로 테스트한 S_D를 설명한다. 첫 feasible tested shell은 확인되지 않았다. 전역 최소성을 주장하지 않는다.

동시 실행은 최신 사용자 지시로 허용됐다. 각 shell의 시간은 독립 성능 비교나 속도 개선의 근거로 사용하지 않는다. 모든 LP TimeLimit은 600으로 고정했고 실제 native Runtime의 소폭 초과도 그대로 보고한다. 추가 shell, 방법 sweep, 시간 연장, 정상3600초 solve는 실행하지 않았다.
