# C3A root gap 증거 읽기와 재검증

과학 base는 Draft PR #162 exact head `1d922c91eb27056a5ccc79c92ef18146707099ab`이다. 선택된 C3A matrix/data/start는 부모 namespace에서 그대로 읽는다. 이 폴더에는 진단 코드, 점과 dual의 압축 NPZ, 후보 계수, 독립 유효성 증명, native 로그와 한 번만 실행한 실험 토큰을 보관한다. 원래 대형 matrix를 새로 복제하지 않는다.

최종 35개 답은 `FINAL_REVIEW_KO.md`, 구조적 인과 경로는 `ROOT_GAP_CAUSAL_TRACE.md`, 증명 범위는 `HULL_SCOPE_KO.md`에서 읽는다. `ROOT_GAP_CONCLUSION.json`은 완료 receipt에서 계산한 최종 결론이다. Barrier primal objective, 실제 native ObjBound, exact bounded-Lagrangian certificate와 이전 유효 MILP bound를 구분한다. 약 15%는 알려진 정수 incumbent와의 차이이며 정수 최적 gap의 증명이 아니다.

`USER_AUTHORIZED_ABORT.json`과 `aborted_1h_provenance/`는 의도적으로 중단한 이전 1시간 실험이다. 완료 benchmark나 TIME_LIMIT 결과로 쓰지 않는다. 마지막 callback은 종료보다 오래된 관측이며 종료 시점 native Runtime/Work를 만들어 넣지 않았다. `failed_baseline_provenance/`는 최초 pure LP capture 실패를 보존한다. `EXTRA_LP_USER_AUTHORIZATION.json`에 사용자 승인 1회 recovery가 기록되어 있다.

Solver-free 재검증은 아래 한 명령으로 가능하다. 기존 C3A 부모 산출물과 원래 frozen 물리 source 경로가 필요하다. Native model을 만들거나 optimize를 호출하지 않는다.

```powershell
python -X utf8 docs/v42_m1_root_gap_attribution_20261007/verify_artifacts.py --deep
```

`--final`은 같은 검증을 수행하고 `VERIFICATION.json`을 쓴다. 그 파일은 workflow/hash/proof integrity와 엄격 raw numeric feasibility를 따로 기록한다. RAW 행 위반이 `1e-8`을 넘는 점을 PASS로 바꾸거나 tolerance를 높이지 않는다. Exact dual certificate는 원래 matrix와 저장된 Pi로 재계산하며 primal 점의 feasibility에 의존하지 않는다.

`pure_lp.py`, `strengthen.py`, `selective.py`, `root_only.py`는 실제 optimize를 포함하는 역사적 실행 코드다. 재실행하면 새로운 solve가 되므로 이번 산출물 재검증 목적으로 실행하지 않는다. ONCE 토큰을 삭제해 재실행하지 않는다. LP loop의 한 번뿐인 회차 경계 checkpoint/resume은 `CUT_LOOP_CHECKPOINT_TRANSITION.json`에서 추적할 수 있고 R1 solve를 반복하지 않았다.

최종 trace는 baseline 및 회차별 presolved-size 증분을 포함한다. 최초 solver capture CSV도 별도로 보존한다. 각 회차는 selected cut 배열의 prefix에 대응하고 원래 행 삭제나 열 추가 없이 작은 batch만 붙인다. 선택적 정수화 시험은 LP loop 종료 후에만 진행하고, 그 incumbent를 원래 all-integer 모델의 새 UB로 쓰지 않는다. C3S native root-only는 material한 검증 LB gain이 있는 경우에만 허용한다.

`SHA256_MANIFEST.json`은 자체 파일과 Python 캐시를 제외한 namespace 파일의 byte 수와 SHA256을 봉인한다. 실제 최종 commit SHA는 Draft PR head 및 PR body/최종 응답에서 확인한다.
