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
