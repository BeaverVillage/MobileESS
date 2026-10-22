# Verified May15--24 daily export

`python -B -X utf8 -u -m daily_archive.archive_may15_24`
exports only2025-05-15 through2025-05-24 into the user's existing IEEE123
destination, using one ZIP per date. Both original750 and completed825
equipment results, every attempt/failure and frozen support snapshots are
included. `common.py` preserves the previous May01--14 archive utilities.

Each ZIP uses an embedded manifest, file SHA256, original size/mtime, exact
inventory, full source/archive byte comparison and ZIP CRC. It is flushed,
renamed and hashed before its location is published to the campaign index.
Deletion is held until `CONNECTION_READY.json` has a verified PASS receipt.
Immediately before deletion, terminal state, process identity, resolved exact
date directories, complete inventories and retained authority receipts are
checked again. No path outside these ten dates is eligible for deletion.

Existing B2 authority inputs and all release-gate Native ledgers/checkpoints
stay at their exact original paths; their contents are also in the archives.
Shared campaign journals and immutable inputs remain in place. Only verified
exported result files are removed. Progress and receipts are stored under
`D:/MobileESS_V44/development/archive_may15_24_20261022`, with the final
verification report beside the ZIP files. A partial or pre-existing archive
requires inspection rather than overwrite or forced deletion.

The 2026-10-23 continuation is `python -B -X utf8 -u -m daily_archive.archive_may25_31`.
It exports May25–31 with the same byte/SHA/CRC/inventory checks and retains
required authority metadata. Before each deletion it also verifies all31
baseline receipt identities through the newly published archive index.
Its reports use `archive_may25_31_20261023` and `V44_2025-05-25_31_VERIFICATION.json`.
