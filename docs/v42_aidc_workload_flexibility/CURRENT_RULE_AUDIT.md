# Current rule reproduction

The literal stored gate is `state_at_issue == PENDING and qos == standby and RSP_start_slot + safe_duration_slots <= RW_completion_slot`. It is recomputed for all 47,009 reference records and compared exactly with `eligible_standby`.

The active V41R4 temporal restoration additionally requires the existing migration contract's admitted in-day PENDING reference: `24 <= reference_start < 120`. The original `terminal.start_bounds` uses:

```
lower = max(24, RSP_start_slot)
upper = min(RW_completion_slot - safe_duration_slots,
            119,
            120 - safe_duration_slots + max(0, reference_end - 120))
```

RUNNING, unadmitted, pre-day starts and out-of-day starts remain fixed for temporal decisions. A gate can be true but the start window can have zero width. Each restored start can use any original whole-gang-compatible site/rack. The restoration does not create shifted-start checkpoint migration products. A separate capacity coupling remains necessary across selected options.

| R0 definition | Job-days | Day GPUh | GPUh % | Incremental PCC % |
|---|---:|---:|---:|---:|
| stored standby eligibility gate | 18,588 | 143,867.50 | 28.760644 | 20.796256 |
| exact restored production temporal domain | 4,767 | 52,192.75 | 10.433886 | 7.544538 |
| registered standalone capacity-witness screen | 1,611 | 17,273.50 | 3.453156 | 2.496910 |

All 31 daily frozen manifests' per-job added option counts and daily restored counts match exactly. Independent verification extracts only the two pure original terminal functions by AST and compares bounds; it imports or runs no production pipeline. The baseline occupancy matches the frozen 96×12 GPU arrays exactly, and the separate C1 implementation matches frozen PCC arrays within 1e-8 kW.

Primary screen vs production: the standalone witness restriction is **additional analysis**, not a claim that production enforces fixed-other-job occupancy for every domain option. It rejects 3,156 domain job-days lacking a feasible single-job move. Joint coordinated movements might recover some; no optimizer was run, so neither their achievable share nor a system dispatch schedule is claimed.

No 14.x% value was used as an authority. With raw frozen B0 GPU and PCC denominators, gate GPUh is 28.760643992%, gate marginal PCC share 20.796255698%, domain GPUh 10.433886053%, and domain marginal PCC share 7.544537842%. These differ because idle/facility power and nonmovable gate-positive work are not flexible energy.

Energy is reference-occupancy attribution: `sum(P_C1(IT_total)-P_C1(IT_total - 0.5477239090195797*kW*flexible_GPU))*0.25h`; denominator is `sum(frozen B0 PCC)*0.25h`. It retains installed idle power and exact frozen weather/C1 coefficients. It is not measured per-job energy, energy saving, a new power scale, or post-dispatch energy. Dynamic IT energy is separately reported. Existing later paper scaling is outside this raw-authority audit.

Protection is temporal. Original frozen spatial/migration rights include protected/carry-in work; those rights and membership are unchanged. Historical migration has its own checkpoint/service contract and does not imply a universal user deadline. See prior frozen `docs/v41r4_final/evidence/posthoc/DEADLINE_AUDIT_REPORT.md` in the base branch. This study claims reference-completion/terminal preservation for new standalone temporal options only, not a retroactive SLA certificate for every legacy migration.
