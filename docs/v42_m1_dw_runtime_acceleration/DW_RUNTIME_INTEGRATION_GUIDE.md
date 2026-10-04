# Later integration of four independent adapters

No production caller is switched on by this PR. RuntimeFlags are all false by default;
from_environment accepts explicit true/false or 1/0 values. Integrators must pass the flags
to the helper being used. DW_DISCOVERY_EARLY_STOP, DW_PARALLEL_VALIDATION,
DW_INCREMENTAL_AUDIT and DW_PERSISTENT_RMP are independent. Merely setting environment
variables on the original PR143 runner currently has no effect.

1. Capture true and smoothed pi/convexity arrays BEFORE optimizing any worker; create one
   DiscoverySnapshot. Send all four workers that same iteration and exact SHA authority.
   The solver search objective must match smoothed pi/convexity only for Discovery.
2. Prepare OriginalBlockValidator with the original PR143 block/prototype and COMPLETE
   original local matrix/attribute/route-mask slice. Keep its inputs read-only during workers.
   The controller callback is combined with original cancellation/capture logic.
   Supply retained SHAs per MESS; save accepted result and trajectory together.
   Recheck returned Candidate bindings against the same snapshot before adding a column.
3. Pricing workers return candidate batches. Opt-in validate_batches performs only Python
   audit work. Canonical results remain equal regardless of worker or candidate ordering.
   Tier 1 always performs full physical/local/integrality and current RC checks.
4. Build AuditAuthority from every scientific/local/coupling matrix and relevant attributes,
   variable/local row axes, complete validator dependency source bytes, physical inputs and
   numerical tolerance authority. The scientific base SHA alone is insufficient. Recompute
   each trajectory SHA from checkpoint values; a filename/mtime is never an authority key.
   The cache schema hashes trajectory SHA plus the complete exact authority vector.
   Existing old-format receipts have no matching key and must be re-audited before reuse.
5. execute_audit_tiers requires original current RMP point auditor EVERY round. Under
   incremental Discovery, it fully audits new and stale columns and reuses only matching
   retained physical receipts. Current RC must still be recomputed against the current dual;
   historical receipt RC is provenance only. Tier 3 Certification/final checkpoint always
   fully audits the retained pool. Audit failures abort without committing staged receipts.
6. PersistentRMP is a prototype: map original fixed rows, z variables and column registry.
   Append only; changed scientific authority requires reconstruction. Preserve checkpoint
   registry as the restart source. reset(0), LPWarmStart=0 and no basis import stay mandatory.
7. Certification remains routed through the original code: unstabilized true dual, finite
   valid global BestBd for each MESS and the unchanged exact corrected LB. Never pass
   quota INTERRUPTED receipts or smoothed values to certificate.receipt.

The likely shared integration edits are v42_dw_throughput/worker.py (snapshot loaded before
pricing, callback combination), v42_dw_throughput/run.py (batch validation/audit tiers/RMP
construction), and v42_dw_resume/audit.py / v42_dw_root/models.py adapters. They overlap
possible Lane A/B changes. Lane C edits none of these files. No merges/rebases from A/B/D
were performed. Resolve integration later against its then-authoritative checkpoint.

Validation commands are `python -m v42_dw_runtime.fixtures`,
`python -m v42_dw_runtime.testing`, `python -m compileall -q v42_dw_runtime tests/v42_dw_runtime`,
and `git diff --check`. The testing entrypoint selects only tests/v42_dw_runtime and
enforces Threads=1, TimeLimit<=30 and nonoverlapping native optimize calls. It never selects
full pytest. Fixtures use TimeLimit=5 seconds, one process, no memory stress or production inputs.

Toy timing, milliseconds (persistent column 0 is initial build):

| Iteration | Python reconstruct | Fresh build | Fresh optimize wall | Retained build/update | Retained optimize wall |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.085 | 0.242 | 1.450 | 0.129 | 1.194 |
| 1 | 0.100 | 0.133 | 0.985 | 0.036 | 0.911 |
| 2 | 0.103 | 0.128 | 0.917 | 0.033 | 0.980 |
| 3 | 0.158 | 0.149 | 0.991 | 0.037 | 1.016 |

These are single toy observations with guard overhead, not production performance estimates.
