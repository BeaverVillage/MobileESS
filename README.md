# MobileESS

Mobile energy storage system rolling-horizon optimization research code.

The production research implementation and its reproducibility notes are added
through reviewed pull requests. Runtime outputs, frozen parent artifacts, and
self-extracting execution packages are intentionally kept outside Git.

V42 operational architecture: D-1 input freeze → A1 → M1 → A2 → M2
(Day-Ahead Planning) → immutable final planning freeze → D-Day Actual with
realized inputs → Fresh OpenDSS validation. Planning has no separate AC stage.
Actual preserves frozen decisions with P/Q correction and full reoptimization
disabled. See [the V42 architecture contract](docs/v42_day_ahead_planning_direct_dday_actual/ARCHITECTURE_BEFORE_AFTER.md).
V41 remains historical; M1 and Problem 13 are not scientifically accepted.

The unified `v42` development workspace is `D:\MobileESS_v42`, with its own Git
object store. Run `./Start-V42.ps1 status`, `run`, `replay`, or `build-only` from
that directory. `V42_CONFIG.json` pins the A/M authorities and the new per-stage
5,400-second cumulative Native budget. The default evidence backend verifies the
May12 A1 P1-only handoff and stops at uncertified M1; it does not inherit the
May01 M1 point, bounds, or the historical 27-day campaign acceptance.

See the [Korean integration report](docs/v42_integration_20261008/INTEGRATION_REPORT_KO.md)
and [completed-M handoff contract](docs/v42_integration_20261008/FINAL_M_HANDOFF_KO.md).
Generate the integration-only ignored `V42_INTEGRATION_READY.json` after a clean
final commit with `python -m v42_unified.delivery`; it records that exact HEAD.
After the authorized May01 research, use `python -m v42_m1_research.delivery_ready`
to include its separate costs, final proofs, tests and unresolved scientific state.

The separate May01 M1 research runner is `./Start-V42-M1-Research.ps1`.
Its default is an optimize=0 baseline replay. `-Execute -RunId <new-id>` explicitly
starts one new bounded research ledger (LB 3,600 + UB 1,800, total 5,400 Native
seconds). A run ID cannot be reused to reset a ledger. This runner preserves the
production evidence backend and the distinct May12 anchor. For completed results,
proof scope, and remaining gap, see the [Korean M1 research review](docs/v42_m1_joint_gap_research/FINAL_REVIEW_KO.md).

The new bounded May01 full-trajectory pilot is `./Start-V42-M1-Hybrid.ps1`.
Its default is optimize=0 source/target/domain verification in a new ignored D
runtime directory, preserving committed receipts. `-Execute -RunId
<new-id>` starts one preregistered pilot with A/B/C strict UB neighborhoods,
four full96 MILP/LP prices, one diagnostic restricted master, and at most one
four-LP price update. The total requested Native limit is 2,310 seconds within
its separate 2,700-second ledger; historical ledgers cannot be reused or reset.
The executed runner is pinned to completed HEAD `6122331841e22562d23eb054c4168b5130566f3f`;
its guard deliberately rejects replaying Native at a different HEAD. Future
Native research requires a new reviewed completed-HEAD preregistration. The
default zero-Native replay works at the delivered HEAD. The research target is
5% for M1/M2 and 0.5% for A1/A2. Production settings and
the May12 anchor remain unchanged. See the [Korean hybrid review](docs/v42_m1_fast_hybrid_20261008/FINAL_REVIEW_KO.md)
and [handoff contract](docs/v42_m1_fast_hybrid_20261008/HYBRID_HANDOFF_KO.md).
After the current clean/pushed commit, generate current readiness with
`python -m v42_m1_hybrid.delivery_ready`; it checks the new manifest and exact
HEAD while preserving the earlier research receipts. M1 remains unaccepted
without a P2 certificate even if its research P1 gap target is achieved.
