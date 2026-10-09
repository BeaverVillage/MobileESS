# D드라이브 실행·증거 재현

공식 개발 기준은 `D:\MobileESS_v42`, branch `v42`다. 기본 production backend와 historical ledger는 이번 연구에서 변경하지 않았다. 새 module은 May01/1499 warm-start 연구 범위다.

기존 완료 Solver를 다시 실행하지 않고 저장된 strict RAW와 exact original-row dual을 replay할 수 있다. `Start-V42-M1-Anytime.ps1`의 기본 실행은 Native optimize=0 baseline audit이며 evidence는 새 D runtime directory에 쓴다. archive된 첫 실험의 `-Execute` guard는 완료 source HEAD e267과 새 Run ID를 요구하므로 최종 delivery HEAD에서 자동으로 신규 Native 캠페인을 시작하지 않는다. 후속 Native 연구는 새 인간 지시와 preregistration/source HEAD 감사를 필요로 한다. 이미 존재하는 ledger path는 거부한다.

이번 두 번째 구간은 `python -m v42_m1_anytime.continuation --execute --run-id anytime_may01_20261008_frontier02_continuation`으로 실행했다. 첫 구간의 명시된 `track` 호환성 오류만 허용하는 한 번의 복구이며 원래 T0와 모든 Native/실패 비용을 이어받는다. 두 구간을 분리하여 예산을 다시 부여하지 않았다. source archive와 원래 실패 receipt는 artifacts/segment01에 있다.

모든 실행은 TEMP/TMP를 D의 tmp에 고정하고 PYTHONDONTWRITEBYTECODE=1, Threads=1 및 BLAS/OMP 기본1을 사용한다. Native model에는 MemLimit/SoftMemLimit을 설정하지 않는다. 새 run output 및 matplotlib font/cache도 D에 있다. C source/data/환경에 새 설치나 쓰기를 하지 않았다.

SVG 렌더링 패키지는 `cache/plotting_py311`에만 `pip --no-deps --target`으로 설치했으며 버전은 PLOT_REQUIREMENTS.txt에 기록했다. 원래 NumPy/SciPy/Gurobi 설치를 변경하지 않았다. 최종 `.publish --run-id ...`는 strict/final90/native75 PASS와 원래 ledger/T0 승계 검사를 요구하고, `.publish --ready`는 clean/pushed identical HEAD와 manifest/649 PASS/행렬 certificate/first-passage chronology를 모두 확인한 뒤 ignored V42_INTEGRATION_READY.json을 발행한다. 그래프·CSV·JSON·한국어 보고서는 docs/v42_m1_anytime_gap_frontier에 있다.

기록의 10분 목표 checkpoint는 오류 복구 후 실제 11.3524분 snapshot이다. 그 구간은 정시 10분 관측으로 주장하지 않는다. actual snapshot/time delay 필드를 사용한다. 발견 시각과 인증 완료 시각은 별개이고 certificate 완료가 first passage를 정한다.

## 이번 delivery는 사용자 요청으로 중단된 partial Frontier

실제 final 검증은 `python -m v42_m1_anytime.cancelled_finalize`로 Native optimize=0에서 수행했다. 이미 종료된 원본 ledger를 수정하지 않고 마지막 검증된 RAW/LB를 replay하고 interrupted call은 exact Runtime/Work 미확보 상태로 배정 예산을 보수 계상했다. clean/pushed readiness는 `python -m v42_m1_anytime.cancelled_ready`로 발행한다. 일반 `.publish --ready`의 75분 완료 계약을 이번 partial 결과로 우회하지 않는다. 30/40/60/75분은 미관측이고 research goal completed=false다. 후속 Native를 자동 실행하거나 재시작하지 않는다.
