# B2 ROOT 저장 증거의 재현

PR185 exact HEAD `6d1d64beaf012d32ddf39245890785e3d8f01d4b`를 기준으로 만든 결과다. 실행은 원본 `v42_physics_redesign.root`를 byte-identical로 재사용한 `v42_b2_root_validation.run`이다. 실행 token과 ledger가 이미 소비됐으므로 run을 다시 실행하거나 token을 삭제하지 않는다. 추가 optimize는 승인된 작업 범위에 없다.

`B2_ROOT_RAW.npz`에 X/Pi/RC/Slack 원시값을 보존했다. 부호 오류가 있는 raw Pi는 거부했고 별도 sign-cone multiplier와 exact dyadic payload를 `artifacts/`에 저장했다. 인증 producer는 CSC 열을 계산했고 독립 checker는 CSR 행으로 모든 finite bound 항을 대조했다. `B2_ROOT_LB_CERTIFICATE.json`이 정확한 alpha와 payload SHA를 연결한다.

이 작업공간의 D: 활성화 스크립트를 로드한 후 `python -m v42_b2_root_validation.package`를 실행하면 solve 없이 기존 source·71개 PR185 증거·15개 원본 모듈·native call ledger·독립 인증·분석 및 이 manifest를 검증한다. `python -m v42_b2_root_validation.certificate`는 analytic .25 하한과 잘못된 alpha/intercept/bound/sign 네 가지를 optimize=0으로 검사한다. 새 native solve는 어느 명령에도 포함되지 않는다.

`python -m v42_b2_root_validation.verify_saved`는 Git namespace에 저장된 raw Pi와 별도 multiplier를 대조하고 exact proof를 다시 계산한다. 이 명령은 실행 작업공간의 기존 reports·logs·이전 PR185 checkout 없이도 동작하며, 현재 repository에서 동일 SHA의 원본 C3A 자료가 사용 가능해야 한다. 새 optimize 호출은 0이며 결과 receipt만 D: WORK/reports에 쓴다.

다른 위치에서 전체 작업공간 감사까지 재현할 때는 PR185가 참조하는 원본 C3A·archived LP·20개 witness를 동일 SHA로 D:에 준비하고, 이 namespace의 보고서는 WORK/reports, artifacts는 WORK/artifacts, raw 파일은 WORK/artifacts/B2_ROOT_RAW.npz에 복원한다. 원본 경로와 SHA는 SOURCE_IDENTITY에 있다. `ACTIVATE_D_WORKSPACE.ps1`은 이번 실제 작업공간용이다. 재현 source는 Git에, 기존 source는 이전 namespace에 모두 보존했다. Manifest 경로는 namespace 또는 repository 기준이며 SHA256_MANIFEST 자체는 self-reference를 피하기 위해 제외했다.

사전등록의 Delta_LB는 최종 global LB 개선량이다. 요청의 B2 certificate−LB_old는 별도 Delta_LB_B2_minus_old에 보존했다. Native 목적값·독립 인증값·기존 하한을 보존한 최종 global LB를 구분한다. Strict 원본 행 replay FAIL과 raw dual sign FAIL을 숨기지 않는다. 새 fractional point는 정수 UB가 아니다. 후속 실험은 실행하지 않았다.

실행 직전 inherited resource gate는 통과했다. 실행 중 외부 May12 pytest의 단일 관측을 동봉했으므로 전체 실행의 지속적 host isolation 또는 인과적 speedup을 주장하지 않는다. 다른 프로세스·priority·작업 증거는 변경하지 않았다. 최종 Git HEAD·PR URL·remote equality·clean tree 영수증은 commit self-reference를 피하여 작업공간 외부 reports/GIT_COMPLETION.json에 저장한다.
