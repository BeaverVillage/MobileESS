# V41R2 capacity-sizing audit (no production application)

Start with [the six-candidate report](V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.md).

This package compares LEGACY_SHAPE_SCALE (A) and the newly generalized
MINIMUM_PLUS_WEIGHTED_RESIDUAL (B) at the same 75/80/85% aggregate-mean totals.
It recommends B as the relative allocation philosophy, while rejecting all
tested installed-capacity applications because material D-day work remains
unstarted. Full May remains HOLD.

## Portable verification

With Python, numpy and pandas installed, run:

```sh
python verify_package.py
```

This reads only this package, checks hashes, independently reconstructs both
integer allocations, reconciles offered GPU-hours and recalculates all six
occupancy/FULL/destination summaries. It does not invoke an optimizer, a model,
OpenDSS, Actual replay, a network connection or a production writer.

## Reproduction boundary

The saved results are independently verifiable without external raw data.
Rebuilding causal Q90/source provenance from original frozen artifacts requires
the paths and hashes in INPUT_SOURCE_MANIFEST.json. External Kestrel data and
31-day runtime snapshots are not copied into this PR.

The audit source can locate those repositories through
`V41R2_AUTHORITY_ROOT` and `V41R2_SOURCE_ROOT`; defaults match the audited host.
All output writes are confined to the script directory. For a full rebuild,
copy the scripts into a fresh output folder and run `audit.py`,
`final_audit.py`, `finish.py`, `compare_allocations.py`, then `package.py`.
The early admitted-only analysis is a bootstrap stage and is superseded by
the final all-D-day, six-candidate report. Matplotlib is optional.
The source readers retain historical absolute paths embedded in frozen
receipts; moving raw authority files requires restoring equivalent paths.

The deterministic placement study combines inherited tier/FIFO event-first-fit,
whole-gang/rack eligibility and numeric site preference. The original production
baseline skips UNASSIGNED and cannot perform the user-requested re-admission.
This adaptation is explicit; no global placement-optimality claim is made.

`D_GPU_offered_total` includes missing-site D-day work. The NPZ alias
`D_GPU_offered` is only the known-site component; never size from it alone.
Counts sum independent job-day forecast observations, not unique actual jobs.

## Evidence layout

- Authority and history: CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json,
  HISTORICAL_SITE_SCALE_AUTHORITY.json, GITHUB_PR12_AUTHORITY.json.
- Offered workload: MAY_31DAY_Q90_OFFERED_GPU_DEMAND.npz and manifest,
  UNASSIGNED_CAUSE_AND_COHORT_AUDIT.json, compressed classification ledger.
- Six allocations: V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv,
  CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json, A_B_ALLOCATION_RULE_FREEZE.json.
- Replay: B0_RESOURCE_REMATERIALIZATION_STUDY.npz uses explicit A75/A80/A85/
  B75/B80/B85 keys; A/B job changes are separate gzip-compressed CSVs.
- Headroom: HEADROOM_BY_SLOT_A75 through HEADROOM_BY_SLOT_B85.
- Dependencies: GPU_CAPACITY_DEPENDENCY_GRAPH.md and electrical/power/H4 audits.
- Preservation: 8,646 pre-existing files byte-identical; prior dirty changes were
  separately committed by external PR work, so Git HEAD changes are distinguished
  from source/evidence-byte changes.

This is a stacked audit PR over the V41R1 branch. It changes no production file
outside this new artifact namespace. PACKAGE_SHA256.json seals the published
package; PR_PACKAGE_VERIFICATION.json records the portable check.
