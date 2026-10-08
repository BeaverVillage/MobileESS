# B2 ROOT 단일 검증 결과

**B2_ROOT_NONMATERIAL**

PR185 exact HEAD 위 별도 D: worktree에서 원본 목적함수·CSR·bounds·types·A1/물리 authority와 기존 651개 제약을 검증했다. Native optimize는 1회다. Cut 재생성·추가 ROOT·canary·production·downstream은 없다. 다른 작업을 중지하거나 수정하지 않았다.

| 지표 | 결과 |
|---|---|
| Native status | 2 |
| Runtime / Work | 210.22599983215332 / 387.4427666794086 |
| Native LP objective | 0.5687138902579907 |
| Archived native LP objective | 0.568711942993466 |
| Native 목적값 차이 | 1.947264524737591e-06 |
| Exact certified B2 LB | 0.5659508784310822 |
| Inherited global LB | 0.5687116104049206 |
| Final valid global LB | 0.5687116104049206 |
| B2 certificate − inherited LB | -0.002760731973838415 |
| Final global LB 개선량 | 0.0 |
| 검증된 UB | 0.6284141956452488 |
| Global gap | 9.500515051% |
| Material gate | False |
| M1_ACCEPTED | false |

요청의 B2 certificate−LB_old 차이와 기존 인증을 보존한 final global LB 개선량을 둘 다 기록한다. 사전등록 파일의 Delta_LB 이름은 final global 개선량을 가리키므로 사후에 그 정의를 바꾸지 않는다.

Native 목적값, exact finite-box certificate, inherited bound를 포함한 global LB를 구분한다. RAW LP point는 정수 incumbent가 아니다. 목적값 비교의 1e-6 기준은 진단 분류이며 원래 1e-8 feasibility tolerance를 변경하지 않는다. Original/B2 residual과 모든 651개 행의 exact violation, slack·Pi, SOC/PQ/route 질량과 critical-grid 변화를 동봉한다. 저장된 point가 strict residual을 통과하지 못하면 그 사실을 그대로 기록한다. Native ObjBound는 채택하지 않는다. RAM은 관측만 하고 MemLimit·SoftMemLimit은 default infinity로 보존했다.

분수해 비교 Case: `D_NATIVE_INCREASE_NOT_CERTIFIED_VALID_WEAKER_BOUND_ONLY`. 새 제약이 archived 점을 분리했다는 사실과 실제 목적값 상승은 별개다. 독립 CSR-row dyadic 계산으로 CSC producer의 모든 finite-bound term과 exact α를 대조한다. TIME_LIMIT 또는 certificate 실패의 raw point를 인증된 LB로 사용하지 않는다.

## 651개 제약과 분수점의 변화

Archived 점의 위반 651개는 새 점에서 0개가 됐다. 최대 archived 위반은 0.7225667872231565이며 새 최소 slack은 1.4409649638932203e-06다. Slack의 절댓값≤1e-6인 행은 0개지만 raw dual의 절댓값>1e-8인 행은 650개다. Barrier 내부점의 작은 양의 slack과 작은 dual을 함께 기록하며, 이를 단순한 cut 비활성 또는 최적값 동일성의 증명으로 해석하지 않는다.

분수 binary는 scientific 1e-8 기준 7454→8019개다. 1e-6 진단 기준에서는 7446→7446개로 같다. Charge_mode는 두 점 모두 384개가 분수이며, 상당한 route-flow 분수 질량도 남는다. SOC 380개는 모두 바뀌었고 최대 변화는 38.028175 kWh다. P/Q와 route 분포가 바뀌어 651개 행을 만족하는 다른 native 분수점이 관측됐지만, 이 점의 원본 strict 행 residual은 6.398198681978329e-08로 1e-8을 넘는다. 완전한 원본 LP feasible point나 두 exact 최적값의 동일성을 주장하지 않는다. Support count의 1e-8 부근 변화에는 barrier 내부점과 종료 정밀도의 영향이 있다.

## 인증 병목과 확대 실행 판단

Raw Pi의 부호 오류 20566개를 거부했다. 별도 sign-cone multiplier의 모든 583,459행·306,040 finite-bound term을 exact CSR 방식으로 재검증해 유효한 LB를 얻었다. 이 약한 인증은 native 목적값의 상승을 증명하지 못했다. Native ObjBound=-52.55404077294537도 채택하지 않는다.

Native primal과 exact LB 사이의 차이는 0.0027630118269085235다. Float 진단 분해에서 finite-box support 손실은 0.0027286831791978354, projected row residual 항은 3.432864771065314e-05다. Injection_Q 손실 0.0019236638463442266과 injection_P 손실 0.0008050070758503297이 finite-box 손실의 약 99.99955%를 차지한다. 이 분해는 exact scalar certificate와 구분한 진단 수치다.

Presolve는 1.98초, presolved size는 {'rows': 407906, 'columns': 299112, 'nnz': 4430819}다. Native 전체 ROOT는 210.226초로 900초 예산 안에 완료됐고 crossover는 0이다. Barrier 로그의 완료 시각 210.16초는 별도 독점 phase 시간이 아니므로 presolve와 합산하지 않는다. 기존 ROOT의 511.570초 / Work 481.275와 이번 210.226초 / Work 387.443를 기록하지만 단일 archived 비교로 인과적인 속도 향상을 입증하지 않는다. 실행 중 외부 May12 pytest가 관측됐으며 이를 통제된 성능 비교라고 주장하지 않는다.

계산시간 기준은 통과했으나 certified ΔLB=0.0이므로 Branch-and-Cut 확대를 정당화하지 못한다. B2_ROOT_NONMATERIAL은 이번 유효 하한 개선에 대한 판정이다. Raw dual 인증 실패와 별도 약한 certificate PASS를 구분하며, 실제 두 LP 최적값이 정확히 같다는 결론은 내리지 않는다.

다음 행동은 하나다: 인증 손실을 지배하는 injection_P/Q의 원래 binding 등식으로 stationarity residual을 상쇄하는 exact multiplier repair 한 건을 optimize=0의 별도 실험으로 검증한다.

현재 후속 실험을 실행하지 않았다. 최종 Git HEAD·PR URL·remote equality·clean tree는 외부 GIT_COMPLETION.json에 기록한다.
