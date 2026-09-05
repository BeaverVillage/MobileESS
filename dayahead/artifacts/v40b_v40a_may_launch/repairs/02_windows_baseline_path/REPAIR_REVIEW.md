May 18 B2 failed while atomically writing `RESTRICTED_VALUES.csv.tmp` for
MESS02. The parent directory existed, but the complete path was 266 characters
and this Windows installation had `LongPathsEnabled=0`. A short filename in
the same directory succeeded; a filename over the limit reproduced the error.

The baseline output namespace is now `V40B`, reducing the failing path to 250
characters. The full 64-character execution fingerprint, stage identifiers,
candidate keys, solver parameters, and scientific sources are unchanged.
The May 18 B2 execution fingerprint was independently rebuilt with both
namespace values and matched exactly.

The recovery supervisor adopts the existing workers by PID and creation time,
counts them toward the four-day limit, verifies completed certificates, and
prioritizes the failed date when a slot opens. It copies this date's exact
beam prefix into the shorter namespace, verifies every copied hash, and
preserves the original files. An adopted baseline worker that encounters the
same precise path error can retry once; other failures remain fail-closed.
Existing B0/B1/B2 certificates and completed new V40A B3 results are validated
and skipped rather than rerun.

Validation: 28 focused Python tests, 54 monitor stage/layout assertions, nine
monitor liveness assertions, and compilation passed. The 820 protected files
from the 14 completed dates matched their pre-repair hashes. The original
execution freeze is retained under `before/`; the replacement execution freeze
links its predecessor. The V40A method SHA and all frozen scientific inputs
remain unchanged.

`CHANGE_IMPACT_AUDIT.json` records the old/new fingerprints and execution SHAs.
`ADOPTION_RECEIPT.json` records the detached supervisor and adopted workers.
`cache_copy/` records the verified cache copies. `failed_attempts/` preserves
failure logs and statuses. Runtime recovery status is recorded separately and
does not represent completion until the corresponding PASS certificate exists.
