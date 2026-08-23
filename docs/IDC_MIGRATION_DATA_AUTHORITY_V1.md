# IDC migration data authority V1

This note separates raw observations from the modeled parameters used by the
post-hoc IDC-migration case study. The raw-data root audited on 2026-08-23 was:

`C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터`

## Raw sources found

| Raw source | Fields relevant to migration | Authorized role |
| --- | --- | --- |
| Alibaba GPU Cluster job execution summary | job/server identity, GPU request/specification, duration, scheduling and ready delays | Workload and scheduling evidence; it does not contain dataset or checkpoint bytes |
| Alibaba network hourly | per-server average RX/TX GiB/s | Observed server traffic sensitivity only; it is not an inter-IDC link-capacity measurement |
| Kestrel canonical job table | January source-matched runtime, GPU and power fields | Primary job cohort; `input_bytes` is entirely NULL and remains NULL |
| NLR generative-AI power profiles | H100/B200 utilization and power profiles | GPU power authority; it does not measure checkpoint bytes or restart time |
| Abilene native topology | 12 nodes and 15 links with 2,480/9,920 Mbit/s preinstalled capacities | Primary 12-node WAN capacity benchmark, not a measured Melbourne IDC WAN |
| Abilene 5-minute traffic matrices | directed 5-minute historical demand matrices | Background-traffic sensitivity source, not applied to the primary preinstalled-capacity case |
| M-Lab and RIPE Melbourne files | client throughput, RTT, loss, ping and traceroute observations | External-network sensitivity/context; not inter-IDC link-capacity authority |

## Frozen post-hoc case-study assumptions

The executable authority is
`pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json`.

- Training datasets are declared pre-staged at all 12 IDCs. Therefore a queued
  job can be placed before start without a dataset WAN transfer. This is a
  scenario assumption, not a conversion of NULL `input_bytes` to zero.
- A running job can move only after six completed five-minute compute steps.
- Its checkpoint payload is modeled as `rho_ckpt * requested GPU count *
  80,000,000,000 bytes`. The primary `rho_ckpt=1.0` case is a conservative
  aggregate-framebuffer engineering reference, not a Kestrel checkpoint
  measurement and not a physical law that checkpoint state scales with GPU
  count. Actual state depends on the model, optimizer, metadata, replication,
  sharding, and parallelism configuration.
- January development sensitivity is preregistered at
  `rho_ckpt in {0.25, 0.5, 1.0}`, corresponding to 20/40/80 GB per allocated
  H100-equivalent GPU. Each value receives a distinct parameterization SHA.
- Restart downtime is modeled as one five-minute step.
- Queued jobs receive deterministic capacity-feasible pre-start placement.
  Running jobs use exact deterministic single-action enumeration and at most
  one checkpoint migration per slow replan.
- Every run records the authority SHA-256, pre-start placement events,
  migration start/completion/restart events, per-step WAN bytes, and cumulative
  WAN bytes.
- B7 and B8 share the same migration authority and actuator eligibility. B8's
  five-minute full-plan invocation cannot bypass the 30-minute checkpoint
  boundary; only the slow-planning invocation timing differs from B7.

The deterministic preflight canary executes the full state chain and requires
positive WAN bytes, transfer completion, one restart interval, execution at a
different IDC, and exact preservation of remaining compute work. It also runs
B8 for six five-minute replans and requires zero pre-checkpoint migrations.

The January development sensitivity launcher is
`pfr/tools/run_january_2025_migration_sensitivity_local.sh`. It runs B3-B8 at
all three preregistered `rho_ckpt` values and aggregates migration count, WAN
bytes, replan count, and deadline misses without selecting a factor to favor a
method.

## Interpretation boundary

The completed January artifacts that reported zero WAN bytes predate this
implementation and cannot support a claim that spatial migration was tested.
January must be rerun under the new implementation fingerprint before its
spatial arms are interpreted. This parameterization is post-hoc design
validation and does not create an independent-holdout claim.

Scientific launchers require `PFR_EXPECTED_FULL_COMMIT_SHA` to contain the
frozen 40-character Git commit and default to branch
`codex/pr6-b8-periodic5`. They abort before the main campaign if the commit,
branch, clean-worktree state, primary migration parameterization, or B7/B8
capability contract differs. `RUN_MANIFEST.json` records the full commit SHA,
branch, dirty flag, migration-contract SHA, parameterization SHA, and
`rho_ckpt`.

The safe local entrypoint is
`pfr/tools/run_january_to_march_2025_local.sh`. It runs migration sensitivity,
a fresh January B0-B8 campaign, artifact validation, daily analysis, and
B7-versus-B8 timing analysis, then automatically continues to February and
March. Scientific failures are preserved and reflected in the final nonzero
status but do not suppress later methods, days, or months. `--january-only`
explicitly stops after January. Source-identity and authority mismatches still
fail closed before any campaign because their outputs would not be comparable.
