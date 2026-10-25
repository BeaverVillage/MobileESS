# B2 May23 causal-weather recovery

The May23 B2 Actual loader omitted the existing r049 same-time weather
supplement scope that the original week4 worker already uses. The incomplete
hourly rows were correctly rejected by the original finite/as-of observer,
causing `CAUSAL_OBSERVATION_TOO_STALE:weather`. The outer audit then attempted
to read an absent Fresh file and obscured the cause with FileNotFoundError.

This adapter installs the unchanged verified r049 loader for B2. It retains
the original 7200-second age, same observation/availability timestamps, and
derived-pressure provenance. It changes neither raw weather nor any optimizer,
budget, voltage, PCS, battery or physical acceptance rule. Original source and
failed attempts stay immutable. The audit stops on the original driver error.

May22 PASS is reused. May23's completed M1 and its checkpoint/source/hardware,
FULL result and reconciled Native ledgers are verified and reused without new
M Native calls; a separate attempt runs Actual120 and independent Fresh120.
May24–31 run sequential full B2 cases with the original r043 engine and common
825 kVA equipment. New technical errors stop dispatch for diagnosis; physical
FAIL remains FAIL. A sealed source authority, distinct controller lock and all
six original OS locks prevent duplicate dispatch. A scheduled task survives
the chat; interrupted workers require diagnosis and cannot reset Native clocks.

The existing active equipment registry receives only authorized B2 rows; the
original publisher verifies every other row is identical to its preserved
baseline. The previous controller state, all checkpoints and failure evidence
remain at their original paths. New controller state records its own location
so the follow-on V44_iteration2 supervisor waits for this recovery too.
