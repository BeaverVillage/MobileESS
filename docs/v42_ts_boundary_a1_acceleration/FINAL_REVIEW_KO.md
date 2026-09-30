# V42 service-boundary TS / A1 가속 최종 검토

1. PR97의 1,395 PENDING jobs는 age가 120,931~291,228초였고, W>age를 만족하는 L4 TRAIN 표본도 3/8/50개뿐이라 N_cond=100을 채우지 못했다.

2. 과거 잔여 대기시간은 현재 job의 승인된 시작 구간과 다르다. 해당 규칙은 forensic evidence로 보존하고 production TS는 ServiceBoundary로 교체했다.

3. 기존 R0의 요청 walltime 기반 planning completion, reference/earliest start, admission·QoS·terminal/carryout 권한이다. 실제 미래 완료시간이 아니다.

4. V10 Q50은 보존해야 할 nominal 서비스 길이, boundary는 선택 가능한 유한 시작 slot 집합이다.

5. earliest=max(reference,RSP,24), latest=min(RW_completion-d50,119,120+원래 승인 tail-d50)이다. pre-D00/post-H reference, 미승인 class는 singleton을 유지한다.

6. 아니다. 원래 승인된 post-H tail을 보존한다. R0의 finite start/control 규칙은 유지한다.

7. 아니다. RUNNING은 전체 물리 gang을 유지하며 checkpoint migration은 별도 capability다.

8. 없다. 제출 전 개인 identity/runtime/start boundary를 만들지 않는다.

9. 그대로 보존한 PR97 CC4 x[h,t]와 TRAIN Q10/Q90 누적 service envelope다.

10. explicit ID 생성, V10 Q50 호출, anonymous forecast 한 번 depletion, PENDING 생성과 physical GPU=0, live finite boundary 계산을 수행한다.

11. 동일한 frozen V10 Q50 provider를 호출하는 inherited EpisodeLedger.submit 경로를 쓴다.

12. PENDING이면 origin unknown이라는 이유로 영구 차단하지 않는다. 다만 현재 audited TRAIN R0 window support가 없어 실제 live TS 권한은 fail-closed다.

13. 권한이 재현된 TRAIN historical R0 authorized start-window여야 한다. 조사한 TRAIN reference ledger에는 temporal authority가 null이어서 유효 표본은 0개다.

14. raw queue wait가 아니다. 이를 대체 표본으로 사용하지 않았다.

15. 사용 가능한 source의 종류는 historical authorized R0 shift window다. 현재 실제 지원 데이터가 있다는 뜻은 아니며, 빈 분포를 명시했다.

16. Q25 한 가지이며 empirical method는 higher다.

17. 사용자가 지정한 preregistered conservative quantile이다. May를 본 뒤 분위수를 비교하거나 선택하지 않았다.

18. L0=qos/protected/partition/gpu_bucket/wall_bucket, L1=partition 제거, L2=gpu_bucket 제거, L3=wall_bucket 제거. 첫 N_window>=100 level만 사용한다.

19. 합치지 않는다. standby 비보호 class만 기존 R0 live temporal QoS를 가진다. normal/high/urgent/protected에 자동 권한을 주지 않는다.

20. 아니다. Runtime/CC4/TS/A1 모두 NEW_ML=FALSE다.

21. Known TS candidate는 1024건이며 live initial count는 0이다.

22. 전체 admitted 기준 job share 63.800623%, nominal GPUh share 76.922350%. PENDING 내부 비율 73.405018%. Global witness/selected share는 미측정이다.

23. 비율을 목표로 rule을 조정하지 않았다. W>age/N_cond를 production known boundary에 적용하지 않는다.

24. PR97 TS=0와 관련 파일은 바이트 그대로 보존했다. 새 supersession receipt만 추가했다.

25. PR97은 complete-option generation에서 600초 timeout이었다.

26. Gurobi optimize()는 호출되지 않았다. generation 병목이었다.

27. static site/rack/residency, fixed-only interval masks, arithmetic checkpoint, WAN template/latest-start, skeleton signature dedup와 exact template reuse를 추가했다.

28. May static site hard removals=0. 모든 제거 사유와 cache source를 CSV에 기록했다.

29. STAY start-mask/terminal removals=0. Full STAY 실패로 migration branch를 삭제하지 않는다.

30. Checkpoint capability 차단=4458, empty skeleton=6576, prefix capacity 차단=0. Branch와 complete option을 혼동하지 않는다.

31. WAN latest-start 사전 제거=38006815, 검사 후 WAN/destination 제거=855. 물리 template은 19800개만 계산했다.

32. Exact duplicate removal=0. 공유 template reuse는 valid option 삭제가 아니다.

33. 최종 complete physical option 수는 349,215,815개다. 모든 1,499 jobs를 포함한다.

34. Raw candidate attempts 대비 reduction=9.815435%; 유효 complete-option set의 삭제율은 0%. PR97 부분 count와 비교한 가짜 감소율은 없다.

35. Input prep+generation=36.802924초, 그중 generation=32.422982초. 저장/감독 포함 external wall=39.078000초다.

36. 그렇다. 1,499개 전체 complete domain을 600초 이내에 완성했다. Lazy representation은 모든 option을 열거할 수 있으며 count를 추정하지 않았다.

37. 기존 synthetic fixtures와 deterministic real subset은 missing=extra=0, 순서도 동일하다. 추가 30개 물리 조건 fixture로 zero-rate WAN bug를 찾아 고친 뒤 전체 354 tests를 통과했다.

38. 사용하지 않았다. grid-benefit/nearest-site/earliest-only/shortest-route/random pruning은 없다.

39. 사용하지 않았다. 완전한 domain 생성이 600초를 넘었을 때만 허용된 fallback trigger가 성립하지 않았다.

40. 미발동이므로 compact MILP 결과/증명 파일을 생성하지 않았다. 현재 모델은 여전히 complete-option마다 binary를 하나씩 갖는다.

41. 여전히 PASS다. worst independent lower bound는 23:45의 509 GPU, anonymous slot minimum=0, capacity780이다. 별도 joint LP도 PASS이며 진단 reserve relaxation임을 명시했다.

42. A1 partial model build external wall=600.313000초. 마지막 progress는 {'phase': 'MODEL_CONSTRUCTION', 'domain_complete': True, 'model_complete': False, 'jobs_modelled': 387, 'total_jobs': 1499, 'current_job': '8665321', 'complete_option_binaries_added': 6640000, 'total_authorized_complete_options': 349215815, 'partial_binary_count': 6640000, 'partial_continuous_count': 18653, 'partial_constraints': 688215, 'partial_nonzeros': 301661094, 'elapsed_seconds': 598.8146156000003, 'model_construction_seconds': 558.1049047999986, 'optimizer_called': False, 'request_sha256': 'ce5bcf7ba59f65028a9a6595ec351544247e30c3ba2b0a8ad6522304bc743802', 'scientific_acceptance': False}. Full build completion 주장은 없다.

43. optimize() 미호출이다. solve time은 null이며 build time을 solver time으로 보고하지 않는다.

44. 검증된 incumbent가 없고 gap/bound/nodes는 null이다.

45. A1 accepted plan이 없어 M1/A2/M2는 NOT_RUN이다. 순서를 건너뛰지 않았다.

46. 전체 domain 생성과 native grid/complete-option column 구축의 bounded scalability를 측정했다. 최종 MILP/optimizer 및 전체 four-stage scalability는 아직 미완료다.

47. Fresh AC는 NOT_RUN이다. accepted M2가 없다.

48. freeze하지 않았다. FINAL_RESPONSE_KERNEL_AUTHORITY.json도 없다.

49. Problem 8은 end-to-end CLOSED가 아니다. domain 생성 하위 병목은 해결됐지만 accepted native plan/AC가 없다.

50. 다음 blocker는 A1_COMPLETE_OPTION_MODEL_CONSTRUCTION_600S_TIMEOUT. 약 3.49억 complete-option binary의 full model 구축이 남는다. 또한 live TS는 audited TRAIN R0 boundary source가 없는 별도 제한이 있다. 추가 rule, ML, CC4 envelope 변경, solver sweep은 없었다.
