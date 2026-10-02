# Reproduce / verify this frozen April campaign

The external raw archive and daily weather/AEMO/static authority paths and SHAs
are recorded in exact PR123 inputs and the new source receipts. Do not use PR124
or May numerical donor/cache outputs. Current package is `v42_capacity`.

Preparation on the exact base (before any outcomes): `register`, `truth_audit`,
`planning`, full pytest, then freeze HEAVY_EXECUTION_GATE only after all 30-day
source/nominal/queue tests pass. Registration refuses to overwrite its freeze.

Execute `python -X utf8 -m v42_capacity.electrical` after the heavy gate.
Per day it generates a fresh April Planning response, freezes its SHAs, invokes
causal `replay --day YYYY-MM-DD`, then starts an independent Actual DSS context.
Existing response coefficients may be reused only at the same exact current
April reference/source binding; fresh Actual AC always runs again. Replay
refuses any drift in previously saved Actual physical arrays.

Then run `python -X utf8 -m v42_capacity.report` and
`python -X utf8 -m v42_capacity.validate`. The report requires all 30 days.
Full-precision CSV is reconstructed without loss from the versioned `.csv.gz`;
VOLTAGE_RESIDUAL_STORAGE.json gives its SHA and byte count. CSV is locally
ignored because it exceeds GitHub's single-blob limit, while the gzip is tracked.

This campaign is 30 independent daily replays from that day's observed D-1
snapshot. Carry-out is explicitly retained per day, not carried counterfactually
into a different day's newly observed snapshot. Counts are daily job rows.
