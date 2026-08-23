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
- Its checkpoint payload is modeled as requested GPU count multiplied by
  80,000,000,000 bytes. This is a conservative full-H100-memory upper proxy,
  not a Kestrel checkpoint measurement.
- Restart downtime is modeled as one five-minute step.
- Queued jobs receive deterministic capacity-feasible pre-start placement.
  Running jobs use exact deterministic single-action enumeration and at most
  one checkpoint migration per slow replan.
- Every run records the authority SHA-256, pre-start placement events,
  migration start/completion/restart events, per-step WAN bytes, and cumulative
  WAN bytes.

## Interpretation boundary

The completed January artifacts that reported zero WAN bytes predate this
implementation and cannot support a claim that spatial migration was tested.
January must be rerun under the new implementation fingerprint before its
spatial arms are interpreted. This parameterization is post-hoc design
validation and does not create an independent-holdout claim.
