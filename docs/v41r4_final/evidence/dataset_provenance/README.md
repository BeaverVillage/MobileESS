# Dataset provenance audit snapshot

Start with [the audit report](FINAL_DATASET_PROVENANCE_AUDIT.md) and
[the full 72-row inventory](FINAL_DATASET_PROVENANCE_AUDIT.csv).
The [paper citation table](PAPER_DATA_SOURCE_TABLE.csv),
[unused downloads](UNUSED_DOWNLOADED_DATASETS.csv) and
[unresolved candidates](UNRESOLVED_DATASETS.csv) are separate views.

Files copied from the completed local audit are byte-preserved. Their source
paths, sizes and SHA256 bindings are recorded in `PR_SNAPSHOT_MANIFEST.json`;
`DELIVERABLE_SHA256.json` seals the five required deliverables. These are local
audit evidence snapshots, not a clean-clone reconstruction pipeline. Absolute
Windows/WSL paths identify original evidence locations.

Large file-level inventories, the Windows root inventory, historical derived
root listing and transitive-reference search output remain local. The manifest
lists each omitted file and its size/path. References to those files in the
report require that original audit directory. This PR contains no raw datasets,
model checkpoints or scientific result CSV payloads. The CSV files here are
provenance tables only. Scope gaps and unresolved records remain explicit.
