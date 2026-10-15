현재 FullFlex의 authorized geometry 생성은 약224초이며 model build+binding 전체300.656초의 큰 부분이다. Native Bindings만으로 전체가 정체된 것은 아니다. 새 케이스의 도메인은 migration block 2,634,483개다.

확인한 결함은 `NativeServiceBoundary.window_authority_sha256`이 UID별 lineage인데 수치 geometry cache key에도 포함된다는 것이다. `a_engine.py`는 original Source13 동결 대상이므로 직접 수정하지 않았다. `table_v_geometry_cache.py`는 원본 함수의 code object를 별도 namespace로 route하여 key의 이 lineage-only 필드 하나만 분리한다. 원본 bound.require는 모든 UID에 실행하고, allowed_starts·completion·duration authority·job semantics·resources·retained flow는 유지한다. 캐시 hit에도 원본 코드가 각 UID의 authority domain SHA를 다시 봉인한다. scientific class grouping과 원본 module globals는 바꾸지 않는다.

작은32UID fixture의 원본/개선 비교에서 모든 STAY·migration block·옵션·domain SHA·graph SHA가 일치했다. 원본 miss32/hit0에서 개선 miss1/hit31이며 계산 구간0.0245911→0.0041120초였다. 이 약5.98배는 작은fixture 한정이며 May01 가속률이 아니다. 공개 Source-derived keypotential은1555→227, 잠재hit1328이나 실제 현재 case.data 재compile·전체geometry벤치가 아니므로 실측hit로 보고하지 않는다.

잘못된 lineage는 cache hit여도 거부하고, 수치 window·완료한계·duration authority가 다르면 공유하지 않는다. 집중88개 PASS 후 전체793개 PASS, Native/presolve/IIS 진입0 및 기존 원장 byte불변을 확인했다. 기존 Source13도 불변이다. 원본 함수 code object/global namespace 불변과 UID별 후보·SHA 동등성을 fixture로 검사했다.

이 versioned additive adapter는 실행 중인 EXECUTION02에 설치하지 않았다. 기존 Source/Case를 중간에 바꾸지 않으며, 향후 DW 복원 adapter의 Source 동결과 현재 행렬/Domain/Objective 동등성 검증에 포함해야 한다. 현재 진행 중인 Native의 TimeLimit·Threads·모델·원장은 바꾸지 않았다. 추가 대규모 Solver·FULL build는0이다. DW 복원 및 실제 전체 시뮬레이션 성능은 아직 미검증이다.
