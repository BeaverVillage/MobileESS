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
Generate the ignored `V42_INTEGRATION_READY.json` after a clean final commit with
`python -m v42_unified.delivery`; it records that exact integration HEAD.
