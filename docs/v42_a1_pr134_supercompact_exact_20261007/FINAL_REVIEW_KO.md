# PR134 정확 압축 전수 검증

PR134 `52ef855a59144a7c561df44b81dc2ad265babdbd`의 accepted A1 원시 해를 재구성했다. 1,499개 작업, 96슬롯의 실제 accepted freeze이며 PR150/151 또는 V39/V41 historical operating point를 current witness로 사용하지 않았다.

원본 9,133,426행 / 7,449,002열 / binary 2,223,230 / continuous 5,184,087 / nnz 53,767,578.
A2SC 7,828,869행 / 6,852,953열 / binary 2,220,986 / continuous 4,590,282 / nnz 42,419,133.
행 14.2833%, 열 8.0017%, binary 0.1009%, continuous 11.4544%, nnz 21.1065% 감소.

모든 행·열 family를 감사했고 채택된 모든 삭제 index는 독립 verifier에서 exact rational/byte/equality 증명으로 확인했다. full LP feasible set, integer domain, rho·migration·absolute shift·prestart 네 목적, 서비스/WAN/Runtime/CC4/GPU/rack/grid를 보존한다. 원본 해 왕복 차이는 0이며 모든 원본 행 최대 잔차는 5.97575355e-7로 원래 numerical authority 이내이다. 삭제 tolerance는 사용하지 않았다.

일반 affine·global equality rank·별도 semantic pruning은 증명되지 않은 경우 UNKNOWN으로 보존했다. structural rank 자체를 삭제 증명으로 사용하지 않는다. 이 감사는 모든 row/column을 검사했다는 뜻이며 가능한 모든 새 정리까지 찾아냈다는 주장은 아니다.

각 arm 300초 한도의 동일 accepted-start P1 비교를 1회씩 수행했다. 원본 126.074초, A2SC 80.557초: 같은 valid UB 및 기존 gap 목표에 36.1034% 빨리 도달했다. sampled peak RSS는 18,364,227,584 → 16,940,888,064 bytes(7.7506% 감소). 두 root LP는 interrupted였으며 완료 LP 시간/Work 개선은 측정하지 않았다. presolved nnz는 거의 동일하고 A2SC가 0.0468% 더 크다. native four-pass 비교는 gate 미충족으로 실행하지 않았다. fresh 전체 A1 속도 개선·one-hour solvability는 주장하지 않는다.

분류: **A_STAGE_SUPERCOMPACT_SELECTED**. 선택 근거는 작은 matrix 자체가 아니라 동일 accepted P1 objective/gap 목표의 실제 runtime 개선이다. Phase II는 별도의 입력 호환성 감사와 detached 실행 증거를 기록한다.

PR134 accepted feasible witness reconstructed: TRUE.
PR134 scientific authority unchanged: TRUE.
No historical operating-point pruning: TRUE.
Performance-based exact formulation selected: TRUE (scope: accepted-start P1 diagnostic).
