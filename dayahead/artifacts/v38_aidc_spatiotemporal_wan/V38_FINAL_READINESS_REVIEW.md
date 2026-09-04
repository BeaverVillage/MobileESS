# V38 Final Readiness Review

V38_READY = NO
MAY_STARTED = NO

## Exact blocker

The mandated global synthetic reference-home mapping is mathematically
infeasible. Gurobi status 3 and the persisted IIS prove that the same
`job_uid -> home AIDC` invariant cannot jointly satisfy the accepted V37
RW/RSP schedules, gang indivisibility, and the frozen 12-site capacities
whose sum is 624.

The IIS contains 172 constraints and binds site
capacity cells on May 24 through May 28. Evidence:
`dayahead/artifacts/v38_aidc_spatiotemporal_wan/V38_HOME_MAPPING_IIS.ilp` (SHA-256 `98152c572f127907b153ba61147c632411458f4346daa6f2713f291818621b9a`).

No date-dependent remapping, gang splitting, capacity inflation, temporal
rescheduling, result-based fitting, runtime Rack reoptimization, or Fresh
feedback was used. Downstream production spatial/Rack/power/identity
artifacts remain explicitly NOT_RUN or FAIL, the science freeze was not
written, and the May launcher must refuse execution.

The exact V37 electrical production-loader regression also fails in this
clean worktree: applicability expects byte SHA `3ee89daad6d63cffb70c1a890f5141cf33bf4c951c9a9c364ae36692bcda6151`, while
the canonical LF-normalized authority file is `ffa1db91e4a7abca6312c3b4763d0bd9030eb115743fb3b17bd2b96381e37c24`. The
preserved original V37 working tree has CRLF-era bytes and passes its 80/80
namespace regression, but those bytes are not the clean parent checkout. No
frozen historical artifact was silently rewritten to conceal this mismatch.

## Recovered authorities

- Abilene pre-installed benchmark link capacities: PASS.
- 5-minute rate-to-byte and 15-minute sum adapter: PASS.
- Latency binding: NO_AUTHORITATIVE_LATENCY_AVAILABLE; no latency invented.
- Fixed OD paths: 132/132 PASS; WAN path optimization disabled.
- Current terminology: AIDC; frozen historical IDC fields use documented aliases.
- Checkpoint payload/restart authority: recovered and synthetic test PASS.
- 48 logical Rack pools as GPU-gang oracle only: PASS.
- Historical runtime Rack optimization: disabled for V38; runtime call counts 0.
- CENTER coefficient remains 547.7239090195797 W/GPU.
