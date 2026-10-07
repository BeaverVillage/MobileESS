# M1 gap 원인 귀속 증거

정확한 Git base는 PR167 `0d423626790a1102d42e6ba84beeb5f7d4ab1d4b`이며 과학 base는 PR162 selected C3A다. 부모 증거와 model/data/start를 읽기 전용으로 사용한다. 새 산출물은 이 namespace에만 쓴다.

실행 코드에 ONCE 토큰이 있다. `solve_dispatch.py`, `solve_neighborhood.py`, `solve_window.py`, `multiwindow.py`, `coupling_master.py`, `selective_blocks.py`는 optimize를 포함한다. 재검증 목적으로 이 파일들을 다시 실행하거나 토큰을 삭제하지 않는다. LP primal을 먼저 저장한 뒤 dual/RC/slack 및 strict replay를 기록한다. raw 실패와 finite-bounds exact certificate를 구분한다. neighborhood와 partial-integrality/coupling master bound의 범위를 global 원본 문제와 혼동하지 않는다.

`verify_hull.py`는 solver를 호출하거나 production hull constructor를 import하지 않고 전체 저장 extended matrix를 재구성한다. `common_mode_separator.py`는 read-only exact support 진단이며 이 부등식을 원래 한 슬롯 cut loop에 추가하는 실험을 수행하지 않는다. 구체적인 exact hull 범위와 boundary interfaces는 `EXACT_LOCAL_HULL_PROOF_KO.md`에 정의돼 있다.

최종 검증은 strict raw numeric feasibility와 workflow/hash/proof integrity를 별도 결과로 보고한다. Runtime은 native 기록값 그대로 보존하고 TimeLimit finish overrun을 잘라 쓰지 않는다. 동시 실행 A-stage/기타 worker를 종료하지 않으며 겹친 Runtime은 통제 performance benchmark가 아니다.

`verify_causal_controls.py`는 solver 없이 separator의 원래면·유리수 multipliers·정점과 mode-only 대조를 독립 검사한다. `finalize_reports.py`는 완료된 receipt를 읽어 원인 귀속/최종 해시를 작성하며 solver model을 만들지 않는다. 대용량 multiwindow dual/RC/slack ZIP이 Git100MiB 제한을 넘으면 `split_large_capture.py`가 각 배열을 lossless NPZ로 나누고 배열 동일성과 원래 local bundle 해시를 증명한다. 원래 bundle은 local에 보존한다.

`homogeneous_bound_certificate.py`는 저장된 sparse 행렬과 dual만 읽는다. private 변수의 perspective box/λ simplex/transit mass를 사용한 exact Lagrangian 인증으로, 모델이나 physics를 바꾸지 않으며 optimize를 호출하지 않는다. box 인증과 이 인증 모두 final receipt에 남긴다.

`source_authority/`에 원래 FULL_A.npz/FULL_DATA.npz/DATA.pkl의 byte-identical 복사본을 포함했다. 원래 source의 SHA와 frozen A1 data SHA를 모두 확인했다. 원래 파일은 수정하지 않았다. `common.py`는 이 복사본을 우선 읽어 hardcoded 원래 Windows source 경로 없이 독립 검증을 재현하도록 한다. 선택적 경로 override는 `V42_SOURCE_AUTHORITY_DIR`이며 모든 원래 SHA guard를 유지한다. 다른 호스트에서는 저장 sparse matrix/dual, source 복사본, 부모 PR의 C2 inverse/C3A 자료로 solver 없는 proof·bound 재검증이 가능하다. optimize를 포함한 stage는 ONCE 제한 때문에 재실행하지 않는다.
