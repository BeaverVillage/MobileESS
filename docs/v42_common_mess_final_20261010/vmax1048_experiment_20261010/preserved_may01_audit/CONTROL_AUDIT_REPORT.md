# V42 May01 Original Controls and Voltage Audit

B2 Actual contains **19 overvoltage cells**, all at MESS PCC nodes. B0 and B1 contain zero voltage violations. All three arms converged at all 96 slots.

Peak: **mess_sta08_pcc.1 / phase A**, slot 10 (0-based; 2025-05-01T02:45:00+10:00), **1.0583754890888868 pu**, exceeding the unchanged 1.05 pu limit by **0.0083754890888867 pu** (0.837548908889 percentage points).

The three full source initial inventories are identical. The same seven RegControls remain enabled in every recorded slot. They share settings SHA **3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf**, snapshot/static mode, maxcontroliter=100, initial taps all 1.0, and four fixed capacitors ON. CapControl count is zero. RegControl settings, settled taps, capacitor states, original models and voltage limits were not changed.

B0 records control iteration counts (maximum 3) and convergence iterations (maximum 9). Original B1/B2 logs do not record these counts or configured MaxIterations. These fields remain UNKNOWN. Their unchanged post-solve hook requires ControlActionsDone=true and the original control inventory before accepting each voltage measurement; this establishes completion through the accepted source path, while distinguishing it from an explicit historical log field.

Read-only source analysis found no demonstrated common-control implementation defect. The original Fresh backend SolveSnap body remains unchanged. Its Planning-state setter hook is replaced with an inventory-only check, so Actual regulators operate autonomously. Any causal attribution to MESS P or Q is pending the separately assigned factorial replay.

Files: `CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv` preserves all resolved properties and each of seven individual regulator settings SHAs. `CONTROL_SLOT_COMPARISON_B0_B1_B2.csv` and `CONTROL_TAP_TRAJECTORIES_B0_B1_B2.csv` preserve per-slot observations. `CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv` compares settled tap values, enabled status and fixed capacitors directly across arms. `CONTROL_SOURCE_SHA_LEDGER.json` checks all original bytes before/after this audit. Detailed voltage cells and Planning/Actual comparison are published separately in `B2_MAY01_VOLTAGE_VIOLATIONS.csv` and `B2_MAY01_VOLTAGE_AUDIT.json` by the numerical audit.

This audit made zero optimizer calls and zero new AC solves. It wrote only external audit artifacts and preserved the old failed canary result.
