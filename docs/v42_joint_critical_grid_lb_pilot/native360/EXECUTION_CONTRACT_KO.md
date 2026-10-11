# 사용자 승인 360초 추가 실행

90초 실행은 2026-10-12에 TIME_LIMIT, ObjBound 0.42547778318693985, Root 완료, Native Runtime 90.03500008583069초로 종료했다. 사용자는 그 결과 이후 **“90초 짧아 360초 돌려”**라고 지시했다. 이 후속 지시가 기존 90초·최대1회 제한을 이번 추가 실행에 한해 대체한다.

원래 90초 latch와 모든 결과·인증을 유지한다. 이 폴더에는 같은 모델·U4 사영·exact K16·Native0 증거를 bytes 그대로 복사하여 재사용하고 새로운 배타적 latch로 추가 Optimize 최대1회를 제한한다. FULL/Compact/C3A 모델 재생성은 없다. Native TimeLimit만360초로 바꾸며 Threads=1, Worker=1, MIPGap=0.03, MIPFocus=3, Seed=42와 1e-8 수치 허용오차는 그대로다. Root LP 별도 실행은 없다.

시작 전 자원·HOLD·다른 Heavy Worker를 재확인하고 모델 Readback 및 4GiB RAM/6GiB Commit reserve+예상 성장 메모리 게이트를 새로 검사한다. 메모리·수치 오류 시 정상 terminate하며 결과를 보존한다. 새360초 종료 뒤 자동 재실행·연장·K16 확대·알고리즘 개발은 하지 않는다. 전체 연구의 Native 호출 수는90초1회+360초추가1회, 총2회로 명확히 보고한다.

이 추가 실행에서도 incumbent는 원본 FULL 가능해나 새로운 UB가 아니다. 유효 ObjBound만 Global LB로 인증하고, 90초와360초 결과를 별도로 비교한다. 모든 Source18r/PR207/PR209·U4·예산·캠페인·HOLD 및 예약 상태를 유지한다.
