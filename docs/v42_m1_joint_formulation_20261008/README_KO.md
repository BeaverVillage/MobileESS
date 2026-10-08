# M1 joint formulation 연구 산출물

이 디렉터리는 PR179 위의 격리된 연구 campaign이다. `FINAL_REVIEW_KO.md`와 `RESULT.json`이 결과의 시작점이다. 과학적 원본은 PR162 C3A이며 모든 원본 행/경계/type/목적계수를 유지한다.

- `PREREGISTRATION.md`: 실행 이전의 후보, 크기 한계, paired LP budget 및 gate.
- `VALIDITY_PROOF_KO.md`: 전체 96-slot integer projection의 양방향 algebraic proof.
- `formulations.py`: A의 9-term aggregate-count EF와 B의 joint Boolean-product RLT.
- `independent_verify.py`: production constructor를 호출하지 않는 exact Fraction 행 계수 verifier와 원본 UB lifting replay.
- `test_bounded_exactness.py`: 1,024개 bounded fixture 상태의 정확한 primal/dual·terminal SOC·lifting·optimum 증명과 negative test. SciPy HiGHS는 작은 fixture에서만 사용한다.
- `dual_recovery.py`: archived OPTIMAL Pi의 joint equality correction. Gurobi optimize를 금지한다. 두 correction의 실패 evidence도 보존한다.
- `runs/`: 호출당 ONCE marker, native input identity, parameters, solver log, barrier trace, 실행 당시 runner source snapshot 및 해/인증.
- `ROOT_COMPARISON.csv`, `CRITICAL_*`: LP strength/cost와 원본 retained row/variable scope의 fractional support.
- `CAMPAIGN_AUDIT.json`, `SHA256_MANIFEST.json`: 실행 한도, 원본 보호 및 raw-byte 증거 검증.

`run_root.py`는 등록된 각 label에 대해 하나의 native optimize만 허용한다. 이미 ONCE marker가 있으면 재실행을 거부한다. 새 optimize의 승인은 이 artifact를 복사하거나 marker를 지우는 것으로 우회하지 않는다.

수학 검증/dual correction/보고서 작성은 optimize를 차단한다. `finalize.py`는 기존 결과를 읽어 보고서와 manifest를 작성하며 solve를 실행하지 않는다. 기존 overnight deadline이나 tree controller의 main은 호출하지 않는다.

새 extended-variable 이름 때문에 NumPy의 통합 string dtype은 넓어질 수 있다. 원본 prefix 문자열의 길이·값·순서를 먼저 native solver에서 확인한 뒤, **잘림이 없음을 재확인하고 원본 dtype으로 저장 표현만 정규화**하여 원본 variable-axis hash를 계산한다. 목적계수와 ObjCon의 dtype/bit에는 정규화가 없다.

Git publication 이후의 final HEAD/PR/remote/clean receipt는 자기 commit hash를 같은 commit 안에 포함하는 순환을 피하기 위해 로컬 `GIT_COMPLETION.json`에 별도로 저장한다. 이 파일만 `.gitignore` 대상이며 scientific manifest에서 제외한다. GitHub PR 설명과 최종 답변에도 동일한 publication 결과를 제공한다.
