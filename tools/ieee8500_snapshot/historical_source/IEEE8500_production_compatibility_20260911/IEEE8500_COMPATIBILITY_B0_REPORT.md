# IEEE8500 production operating-point compatibility B0 screen

**NO_FEASIBLE_ALPHA_ON_FIXED_COMPATIBILITY_GRID**

Selected date: **2025-05-21**. Selected alpha8500: **None**.

This is a user-fixed compatibility adaptation for the reduced-load IEEE8500 operating point and the 0.95–1.05 pu study envelope. It is **not canonical IEEE8500 reproduction**.

Only FEEDER_REGA/B/C Vreg changes from 126.5 V to 125.0 V, and uncontrolled fixed CAPBank3 is out of service. Source pu=1.05, PT ratio=60, band=2 V, tap limits, all nine controlled capacitor phases and their CapControls, native topology/impedance/ratings, 24 locations, PCC transformers, and AIDC/MESS scales remain unchanged.

Rule, code and all previous source/PCC/topology/input/evidence hashes were frozen before execution. Every alpha uses a fresh OpenDSS context with 96 chronological snapshots and accepted control-state carry-forward. No EventLog properties were edited. Only the unchanged D-1 demand/PV forecasts, frozen B0 exogenous PV ratio and AIDC P/Q inputs are used. MESS injections remain zero.

| alpha | feasible | converged/controls | Vmin | Vmax | line I pu | transformer phase I pu | transformer winding kVA pu |
|---:|:---:|:---:|---:|---:|---:|---:|---:|
| 1.00 | False | 96/96 | 0.877432057 | 1.052508356 | 1.752353103 | 0.480762474 | 0.474046333 |
| 0.95 | False | 96/96 | 0.887046556 | 1.052553716 | 1.644508271 | 0.449265395 | 0.445727043 |
| 0.90 | False | 96/96 | 0.906893416 | 1.052495259 | 1.555096685 | 0.417115183 | 0.418053385 |
| 0.85 | False | 96/96 | 0.915295576 | 1.052947610 | 1.466224788 | 0.388843956 | 0.392207752 |
| 0.80 | False | 96/96 | 0.929398738 | 1.052335985 | 1.374452710 | 0.361761237 | 0.366454995 |
| 0.75 | False | 96/96 | 0.934128133 | 1.053288209 | 1.279749718 | 0.336840194 | 0.342168967 |
| 0.70 | False | 96/96 | 0.947132960 | 1.052724582 | 1.182873113 | 0.311968367 | 0.318372077 |
| 0.65 | False | 96/96 | 0.959513797 | 1.052670739 | 1.100345512 | 0.288016154 | 0.295750426 |
| 0.60 | False | 96/96 | 0.961524080 | 1.053249872 | 1.013209464 | 0.267596905 | 0.273374085 |
| 0.55 | False | 96/96 | 0.973642527 | 1.053441002 | 0.926059045 | 0.244297975 | 0.251397646 |
| 0.50 | False | 96/96 | 0.979108844 | 1.051818210 | 0.833650093 | 0.222109902 | 0.229187943 |
| 0.45 | False | 96/96 | 0.989091934 | 1.053266346 | 0.747191169 | 0.200458251 | 0.207645681 |
| 0.40 | False | 96/96 | 0.990758357 | 1.055464378 | 0.661260273 | 0.186696050 | 0.186264295 |
| 0.35 | False | 96/96 | 0.993140901 | 1.052650700 | 0.570848055 | 0.164065266 | 0.165140563 |
| 0.30 | False | 96/96 | 0.996864797 | 1.050666447 | 0.488037384 | 0.139737585 | 0.144911817 |
| 0.25 | False | 96/96 | 0.999008911 | 1.050913191 | 0.408408584 | 0.118935534 | 0.123604902 |
| 0.20 | False | 96/96 | 1.007803759 | 1.051581599 | 0.325813174 | 0.098711513 | 0.102814905 |
| 0.15 | False | 96/96 | 1.016262504 | 1.052235056 | 0.255536187 | 0.079345674 | 0.082753662 |
| 0.10 | False | 96/96 | 1.024462041 | 1.052879006 | 0.196215426 | 0.061101910 | 0.063797559 |
| 0.05 | False | 96/96 | 1.020669652 | 1.053301098 | 0.142553845 | 0.050012668 | 0.049306402 |
| 0.00 | False | 96/96 | 1.028358503 | 1.053848881 | 0.102977502 | 0.047859673 | 0.049306030 |

Limits: 0.95≤V≤1.05 pu and line/transformer phase-current/transformer winding-kVA loading ≤1.0 pu, unchanged numerical boundary tolerance 1e-9. All 8639 nodes, both line terminals and every transformer winding are included. Voltage/thermal violations and unconverged or unsettled slots fail feasibility. The largest feasible value is selected from all 21 fixed grid values; there is no grid refinement or tuning.

Independent selected-alpha replay: **NOT_APPLICABLE_NO_FEASIBLE_ALPHA**. All 21 saved phase-array sets independently reproduce the recorded feasibility decisions. All 2492 previous evidence files retain SHA256, size and modification time.

The original NO_FEASIBLE_ALPHA_ON_FROZEN_GRID and NATIVE_VOLTAGE_CONTROL_COMPATIBILITY_MISMATCH evidence remain intact, including native alpha=0 Vmax>1.05. New adapted results do not replace or relabel those native findings.

B1/B2/B3 runs: **0**. Additional setpoint/source/capacitor tuning or resource rescaling: **0**. No feasible alpha exists under the fixed rule; stop here without additional changes.

Artifacts: ALPHA8500_AUTHORITY.json, ALPHA_SCREEN_TABLE.csv, B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv, screen/alpha_*/B0_ALL_PHASE_ARRAYS.npz, screen/alpha_*/B0_CONTROL_STATES_96.json, PRE_SOLVE_ALLOWED_CHANGE_AUDIT.json, INDEPENDENT_SELECTED_ALPHA_VERIFICATION.json, IMMUTABILITY_FINAL_AUDIT.json, PRE_EXECUTION_FREEZE_MANIFEST.json.
