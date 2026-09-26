# CC4 reserve miss and execution delay audit

This read-only audit of the frozen V41R4 May 2025 archive found **466 misses in
2,511 H4 windows**, reproducing **81.4416567% actionable coverage**. The future
arrival jobs contributing to those labels are absent from the same-day Actual
replay. Their policy-dependent delay and a causal CC4 delay effect are therefore
**NOT_IDENTIFIABLE**, not zero.

Existing frozen jobs have recorded capacity-contention delays: B1 has 1,465 and
B3 has 1,466 delayed job-days. Deterministic dispatch waits for GPU capacity;
there is no online CC4 scheduling recourse. Migration-related service deferral
is reported separately. No optimization, replay, OpenDSS or ML training/inference
was run to prepare this audit or this PR.

## Results

- [Full Korean forensic report](CC4_HEADROOM_MISS_DELAY_FORENSIC.md): definitions,
  code call chain, all requested judgments, top misses, delay and migration
  statistics, and causal limitations.
- [All 2,511 windows](CC4_HEADROOM_MISS_WINDOWS.csv): H/R, cap flags and separate
  B1/B3 headroom and planned shortfall columns.
- [Full job links, lossless gzip](CC4_MISS_JOB_DELAY_LINK.csv.gz): 193,624 rows
  including both policies and explicitly separated frozen/label-only populations.
  Decompression yields the original 103,277,677-byte CSV without any row edits.
- [Machine-readable summary](CC4_HEADROOM_MISS_DELAY_SUMMARY.json).
- [Daily policy aggregates](CC4_DAY_POLICY_AGGREGATION.csv),
  [window diagnostics](CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv), and
  [migration separation](CC4_MIGRATION_DELAY_SEPARATION.csv).

The May 21 contributor table is unavailable in the archive. Its 81 H4 labels
are available and contain no misses. All 466 miss windows have contributor
evidence; the non-miss job population remains incomplete. JSON nulls and CSV
`NOT_AVAILABLE` must not be converted to zero delay. Overlapping windows and
repeated job snapshots across independent days are not independent samples.

## Verify the published package

From the repository root, with Python 3.10 or newer (standard library only):

```sh
python tools/v41r4_cc4_forensic/verify_package.py
```

This checks the package hashes, decompressed CSV identity, 31 × 81 windows,
forecast statistics, canonical arrival assignments, job population separation,
and B1/B3 delay totals against the saved summary. It reads only the published
files and does not require the raw archive or execute scientific source.

The [package manifest](PACKAGE_MANIFEST.json) documents unchanged copies and
publication-only transformations. The original audit receipt is preserved in
[ORIGINAL_DELIVERY_MANIFEST.json](ORIGINAL_DELIVERY_MANIFEST.json). Original
source paths inside JSON are historical provenance, not current filesystem
dependencies. See [archive evidence access](ARCHIVE_EVIDENCE.md) and the
[historical analysis scripts](../../tools/v41r4_cc4_forensic/README.md).

This review is stacked on the V41R4 final-result branch (PR #42). It adds audit
evidence; it does not revise the final experiment, its execution source, or the
paper export's scientific authority. The new derived audit tables are included
here; the original raw archive and extracted runtime data remain local.
