# Local Paths / Evidence Codex Should Inspect

Do not assume every path still exists. Search by basename if a path has moved.

## Repository / runtime

Likely repo/worktree:

```text
/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration
```

Production runner used by G12E:

```text
/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package/runtime/W02_POLICY_EPISODE_RUNNER_R21_FINAL.py
```

Scientific core:

```text
/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/science/main.py
```

Gurobi Python:

```text
/home/jaewon/miniconda3/envs/power_v61/bin/python
```

R6C canonical job source:

```text
/home/jaewon/mobile_ess_work/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet
```

Known R6C source SHA-256:

```text
0fe9399ece73e4e6906d036f3322697bd3c73b1498cf3e9c49b836631e19c98f
```

Shared W02 exogenous root:

```text
/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT
```

## Task/evidence lineage to search

Search under `/home/jaewon/mobile_ess_work/frozen_artifacts` for:

```text
MOBILEESS_TASK_G8T*
MOBILEESS_TASK_G9C*
MOBILEESS_TASK_G10F*
MOBILEESS_TASK_G11A*
MOBILEESS_TASK_G12A*
MOBILEESS_TASK_G12B*
MOBILEESS_TASK_G12C*
MOBILEESS_TASK_G12D*
MOBILEESS_TASK_G12E*
TASK_G12E_FULL_DAY_RUN
TASK_G12E_FULL_DAY_MATERIALIZER
```

G12E user-to-ChatGPT bundle basename:

```text
TASK_G12E_TO_CHATGPT_BUNDLE_20260821T150705+0900.tar.gz
```

Its SHA-256 from the handoff analysis:

```text
ba9753d280fad6df4b35014efae609ad8cbcdbe7785b49588164b06ff6743507
```

## Important configuration lineage

Legacy pre-feedback M1:

```text
performance/post_stage15_runtime_acceleration/package/configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json
```

Legacy pre-feedback M2:

```text
performance/post_stage15_runtime_acceleration/package/configs/P2_FIXED30.json
```

M3 was generated/overlaid during bounded task work; do not promote package-local monkeypatch semantics to production without clean source implementation.

M4:

```text
performance/post_stage15_runtime_acceleration/package/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json
```

## Evidence handling

Inspect raw evidence locally, but commit only compact summaries/audits. Never commit the full `TASK_G12E_FULL_DAY_RUN` or materializer output tree.
