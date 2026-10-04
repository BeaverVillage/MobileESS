# Authoritative May 2025 B0 production

Base is PR146 exact head `0760b8f56398344e55d938b175d88761d19ff657`.
This branch adds one explicit B0 production adapter; PR146's global default
production guard remains blocked. B1/B2/B3 flags and auto advance cannot be enabled.

The current frozen B0 path is deterministic reference/capacity calculation,
with AIDC/workload present, grid flexibility off and MESS off. It invokes no
A1/M1/A2/M2 optimizer. Native Gurobi models, if any helper constructs one, are
forced to Threads=1; unexpected optimize() is blocked because this existing B0
contract does not optimize. Every native stage shares the global four-slot token
system. Process isolation prevents global OpenDSS context and cwd collisions.

The original scientific files are unchanged. `v42_holdout.calendar_adapter`
continues to load the reviewed reference and Actual reconstruction. Single-day
queue routing selects one original planning loop iteration; all scientific loop
statements remain unchanged. Fresh AC retains the exact `v42_regcontrol.runner`
96-slot computation AST. Only May/output routing and the path to the independently
accepted, newly reconstructed Actual physical file change. The current
`v42_thermal` NormalAmps checker, separate kVA checker, source line ratings,
seven autonomous enabled RegControls and four fixed-ON capacitors remain active.

The five PR146 B0 stages map to:

1. B0_PLANNING: existing capacity/reference producer, then existing May native
   D1 anchor/sensitivity producer. Its own freeze-file write is a candidate artifact.
2. PLANNING_FREEZE: validate and accept the existing producer's immutable files.
3. ACTUAL: recompute occupancy and IT/PCC P/Q with the original private-environment
   queue and frozen observed weather; no DayAhead power copy or grid repair.
4. FRESH_AC: independent source-initial context per day and sequential Actual
   controls within that day; source parameters and engine P/Q readback are audited.
5. VALIDATION_FREEZE: accept only zero Planning voltage, Actual voltage, line
   current, transformer NormalAmps current and separate transformer kVA violations.

The existing May contract requires *all 31 new Planning freezes before Actual
truth*. Therefore two ordered dynamic day queues use the same day-worker cap:
Planning/Freeze for all dates, followed by Actual/Fresh/Validation for all dates.
No four-day batches are hardcoded. Source inputs are the existing frozen causal
May bundles and exogenous authorities; old B0 outputs are never used. The inherited
input envelope still says `INCOMPLETE_NONEXECUTABLE`, while the reviewed B0 producer
uses its explicit `input_gate_PASS` plus full reference/capacity gates. No field is
edited to obtain feasibility. A new raw realized-duration ledger is reconstructed
after every new Planning freeze, using the original source-observed rules.

PR146 lacked native production receipt/admission interfaces. Its Ledger now has
small mode-specific identity, payload and counter hooks; the original mock mode
and its tests keep their behavior. B0Ledger rejects mock roots, checks output
file hashes on every acceptance/resume, and uses a distinct production run ID,
stage version and identity. The reviewed B0Scheduler inherits the existing
transition/retry machinery and global resources. Scientific failures block
dependent stages; transient I/O/process failures use the bounded retry policy.
All dates must be terminally accounted for; scheduler completion alone is never
scientific PASS. The receipt report reopens the checkpoint, verifies every PASS
file and confirms that no completed stage is recomputed.

Live telemetry samples at one second using psutil, Windows GetPerformanceInfo
system commit and PDH Pages Input/sec. The only RAM admission floor is 1 GiB.
OOM, commit >=95%, unavailable telemetry and sustained catastrophic paging stop
native admission/own workers. The explicit paging threshold is >=8192 Pages
Input/sec sustained for 30 seconds. Only measured hard resource events can
reduce day capacity from 4 to 3 to 2 to 1. The policy never kills another lane.
Plausible unrelated full-scale native processes require command, loaded native
module, RSS and recent CPU evidence before new day admission pauses; ordinary
verification/mock/unit/semantic processes are allowed. Existing valid B0 stages
are not canceled for an unrelated heavy process.

Commands from the repository root:

```text
python -X utf8 -m unittest discover -s tests/v42_b0_production -v
python -X utf8 -m unittest discover -s tests/v42_orchestrator -v
python -X utf8 -m v42_b0_production prepare
python -X utf8 -m v42_b0_production run
python -X utf8 -m v42_b0_production report
```

`prepare` checks the exact base and hashes scientific/code/input/grid/Actual
authorities, creates a new run root and explicit config, and writes the freeze
manifest. `run` rechecks all frozen bytes before admission. `report` gives B0-only
results, terminal counts, independent Fresh AC and resource metrics, restart/
idempotency receipts and SHA manifests. Huge native logs/arrays stay at the local
run root; intended summary/evidence files are versioned here. No other-arm
comparison or optimized rho is invented by this fixed B0 producer.

Final authoritative run: B0_202505_20261004T203131_71a9bf18, 31/31 days and 155/155 stages PASS; Fresh AC 2976/2976 slots; no voltage/current/kVA violations. Four workers passed the first wave; measured commit 95.08044393176834% later caused 4->3 downgrade. Max sampling gap=1.156s.

The superseded run failed the sampling interval requirement and is non-authoritative. The final run reconstructed every output independently, with no earlier output substitution. Both run roots remain locally available.

C1 binding loads the exact frozen v41r2 file into isolated workers while the grid package uses its separately frozen v41r3 authority. C1 file bytes are identical; equations unchanged.

The post-production observer allowlist correction exempts the exact SHA-audited verification-only lane driver. Full-scale cg remains detected. EXECUTED_PRODUCTION_OBSERVER.py preserves the actual production observer; OBSERVER_PUBLICATION_FIX.json binds its frozen SHA to the later correction. Use archived execution bytes for original-run reproduction. No native scientific producer changed. The original false-positive pauses remain in evidence; no coordinator restart was performed for this fix.

Authoritative run: no retries/crashes. Superseded diagnostic run: one transient checkpoint-read PermissionError, retained in its run root.
