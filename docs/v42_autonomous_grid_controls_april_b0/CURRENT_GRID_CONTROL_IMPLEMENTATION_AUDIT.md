# PR125 conventional grid control audit — STOP

Exact base: `043298363fe51edde0bddaa073a553e526ffef2c`, Draft PR125.
The requested autonomous regulator **and capacitor** correction is blocked by
missing source CapControl equipment and settings. No new diagnostic or April
campaign was executed. PR125 production files and results are preserved.

## Equipment and parameter authority

The complete compiled DSS input graph has seven files: IEEE123Master.dss,
IEEELineCodes.DSS, IEEE123Regulators.DSS, IEEE123Loads.DSS, the exact PCC v4
redirect, line ratings u080, and phase PV. Every file was read and hashed.
Master redirects and equipment-definition line numbers are recorded in
REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json. The first six static authority records
and all six code records match the PR125 ELECTRICAL_SOURCE_AUTHORITY hashes.

Both exact source compiler paths produce the same inventory: **seven regulator
transformers, seven enabled RegControl objects, four capacitor banks, zero
CapControl objects**. `CapControls.Count()` is zero and `AllNames()` is empty.
No source redirect or generated PCC/PV/rating file creates a CapControl.

| RegControl | Transformer | VReg | Band | PTRatio | CTPrim | R | X |
|---|---|---:|---:|---:|---:|---:|---:|
| creg1a | reg1a | 120 | 2 | 20 | 700 | 3 | 7.5 |
| creg2a | reg2a | 120 | 2 | 20 | 50 | 0.4 | 0.4 |
| creg3a | reg3a | 120 | 1 | 20 | 50 | 0.4 | 0.4 |
| creg3c | reg3c | 120 | 1 | 20 | 50 | 0.4 | 0.4 |
| creg4a | reg4a | 124 | 2 | 20 | 300 | 0.6 | 1.3 |
| creg4b | reg4b | 124 | 2 | 20 | 300 | 1.4 | 2.6 |
| creg4c | reg4c | 124 | 2 | 20 | 300 | 0.2 | 1.4 |

VReg/Band and the listed measurement/line-drop settings are explicit DSS source
or resolved `like=` inheritance. Delay=15, TapDelay=2, MaxTapChange=16 are
**observed defaults in the version-bound compiled engine**, not newly selected
parameters. Winding 2 has MinTap=0.9, MaxTap=1.1, NumTaps=32, step=0.00625.
All resolved RegControl properties and engine version are recorded, including
parameters not shown in this table. Source uses snapshot/static mode and
maxcontroliter=100; this audit does not reinterpret it as a time-mode delay
simulation.

C83 is three phase, 600 kvar, 4.16 kV; C88a/C90b/C92c are single phase, 50 kvar,
2.402 kV each. All four are enabled, single-step, and source state `[1]`.
Their bus connections, phases and states are recorded. These are fixed shunt
capacitors. No capacitor sensor, on/off threshold, control type, switching
delay or controller-to-bank mapping is defined. A capacitor being enabled or
ON does not establish autonomous switching. CapControl API defaults for a
nonexistent controller cannot supply the missing authority.

## Planning behavior and carryover

`v42_capacity.electrical.generate` builds the current D-1 forecast background
and PR125 physical reference power, then invokes
`_anchor_and_sensitivity_day`. The source `_compile(..., "NATIVE")` uses the
same master/PCC/ratings/PV as Actual, with snapshot/static controls.

The anchor producer compiles once **before** its 96-slot loop. At each slot it
calls `_enable_native_controls`, enabling existing RegControls and setting
static/maxcontroliter=100; applies forecast inputs; calls `SolveSnap`; checks
convergence; then reads converged taps and capacitor states. Regulator anchor
operation is autonomous. Capacitors remain inherited fixed ON: the producer
does not create a CapControl. `_native_capacitor_q` in the full-grid binding
also uses the enabled physical banks' fixed states when forming base Q.

For finite differences `_fix_controls` disables RegControls, restores the
just-observed taps/caps, and sets controlmode off. Each perturbation restores
its P/Q control afterward. These solves cannot move taps/caps. The next slot
reenables native regulators in the same engine, starting from the previous
anchor state. There is no per-slot recompile, ClearAll, or native reset.
This is **sequential state carryover within each day**, with a source-initial
compile at the next day. It is not independent per-slot source initialization.
V_PLAN is the affine squared-pu model evaluated at the B0 anchor and converted
with sqrt; taps/caps are not optimization variables. Planning source and all
stored V_PLAN values remain unchanged in this blocked task.

## PR125 Actual forcing

`compile_clean_engine` creates a NewContext, clears it, compiles the exact
assets and sets snapshot/static/maxcontroliter=100. Before it is forced, its
seven RegControls are enabled; it contains no CapControl.

In `v42_capacity.electrical.generate`, each Actual slot first applies realized
background/PV, Actual physical AIDC P/Q and zero MESS. It then calls
`apply_frozen_native_state(odd, anchor, t)` **inside every slot**, immediately
before `SolveSnap`. The source backend has the same forcing pattern.

`apply_frozen_native_state` validates `(96,7)` taps and `(96,4)` caps; disables
all RegControls; sets regulator winding-2 taps and capacitor States from the
Planning row; and sets global controlmode off. It does not set unrelated
load/PV/AIDC/MESS P/Q, ratings, topology, source voltage or equipment targets.
The global off mode prevents all autonomous control actions; disabled
RegControls remain disabled. `_native_state` only reads physical taps/states
after the solve, so agreement with Planning is a forced result, not an
independent control-law validation.

The generic `v42_native.actual` replay freezes optimizer policy/controls and
prohibits local P/Q repair and full reoptimization; it does not implement a
native RegControl/CapControl controller. Its final physics acceptance gate
also rejects voltage violations. The requested calibration diagnostic would
need a separate convergence/control-isolation gate that accepts measured
violations. Neither gate nor that generic production module was changed here.
`v42_native.grid` has affine electrical constraints without tap/cap decision
variables. `v42_native.voltage` keeps Actual physical 0.95–1.05 and separates
A1 from robust planning authority. None of these constants was changed.

All 30 PLANNING_FREEZE and 30 FRESH_ACTUAL_AC_RECEIPT files were read and
hashed into PR125_DAILY_FREEZE_RECEIPT_AUDIT.json. These prove historical frozen
execution only: 2880 converged slots, 22 voltage cells across April 15/16/30.
They are not new autonomous execution evidence.

## Mandatory STOP

User §25 requires immediate STOP if autonomous RegControl/CapControl cannot
be enabled without changing source equipment settings, or control parameters
are missing/unverifiable. Both conditions apply to capacitors. Enabling an
existing object is impossible when its class count is zero. Adding controllers
would require choosing their measured element/type/thresholds/delays and would
change the source equipment/control law. That would violate the instruction
to use existing source-backed settings without invention or tuning.

Accordingly no production adapter was activated, no replay correction was
claimed, and no regulator-only rerun was substituted for the requested
regulator-plus-capacitor contract. Diagnostics, full rerun, new residuals and
new margin candidates remain NOT_RUN. May outcomes were not opened by the
audit. Two static compilations include the source's zero-load CalcVoltageBases;
they are equipment inventory checks, not a scientific day-slot campaign.

Resuming requires source-backed CapControl definitions/settings for these
banks, or an explicit revised contract accepting autonomous regulators with
the source's fixed ON capacitors. Neither has been supplied or adopted here.
