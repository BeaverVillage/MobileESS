# V18 AIDC Physical Re-freeze Root-Cause Correction Review

RESULT CLASSIFICATION: `E. REFREEZE_FAILED_PHYSICAL_COHERENCE`

V18은 Kestrel의 공식 설치 경계 132-node x 4-H100 = **528 GPU**와 retrospective training trace를 결합했고, native semantic-flexible GPU-energy share를 **36.775122%**로 재현했다. 그러나 trace의 15분 평균 requested occupancy는 최대 **589.411111 GPU**로 528을 **902 slot** 초과했다. 가상 q99.5/u85 용량으로 바꿔 통과시키거나 clipping하지 않아 Gate A를 fail-closed했다.

Dataset312 full-node GPU-board+RAPL CPU-package 계수와 partial-node GPU-board lower bound의 hybrid power contract은 source-backed하게 복구했다.

그러나 현재 Kestrel archive는 최종 sacct record이고 D-1 18:00의 pending/running snapshot이 아니다. 미래 realized start/end를 사용하지 않고는 `QUEUED_KNOWN`과 `RUNNING_KNOWN`을 정확히 판별할 수 없으므로 Gate B를 fail-closed했다. 이에 따라 새 three-component facility decomposition, 새 whole-facility flexible share, prospective scheduler 및 B0-B3/OpenDSS 실행은 승인하지 않았다.

- Gate A: FAIL_NATIVE_PHYSICAL_COHERENCE
- Gate B: FAIL_QUEUE_AND_RUNNING_SNAPSHOT_AUTHORITY_MISSING
- Gate C: PASS_HYBRID_AUTHORITY
- Gate D: BLOCKED_NOT_EVALUATED
- Gate E: BLOCKED_NOT_IMPLEMENTED
- `READY_FOR_NEW_SCIENCE_RUN = false`

20-25% 문헌값은 `LITERATURE_CONTEXT_ONLY`이며 모델 builder에서 읽지 않았고 calibration 호출은 0이다.
