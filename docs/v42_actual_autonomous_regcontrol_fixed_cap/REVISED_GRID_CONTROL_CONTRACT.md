# Current V42 conventional controls

PR127 exact base f535cc2671b285068f6b5ffbec55b951ffb7ea6d supplies the audited
source authority. The revised user contract accepts seven autonomous
RegControls and four fixed ON physical capacitors with zero CapControls.
No capacitor control equipment, threshold, delay or switching event is added.

Planning remains unchanged: forecast inputs, a source-initial engine per day,
static/snapshot RegControl convergence, sequential state across 96 slots, then
affine anchor/sensitivity. Only local finite differences hold anchor states.
Tap/cap states are not AIDC/MESS decision variables or P1/P2 objectives.

Actual uses a fresh source-initial NewContext per day and its own sequential
RegControl state under realized inputs. It consumes frozen PR125 physical
P/Q without retiming, migration, optimization, MESS or P/Q repair. Planning
tap/cap arrays are not controller inputs. All source parameters, engine
version, enabled status, static mode and capacitor state [1] are verified
before and after every solve. Drift stops the run without state correction.
There is no cross-day state transfer and no Planning state initialization.

The common session and authority interface serve April/May and B0/B1/B2/B3.
Arm-specific parameter SHA overrides fail fast. Scientific execution here is
April B0 only; the reusable control layer itself does not decide AIDC/MESS
policy. May outcomes are not loaded; the campaign rejects non-April dates.

The preregistered diagnostic is April 15/16/30. Control/identity/convergence
PASS permits a separate full 30-day rerun. Voltage violations are measured,
never a tuning trigger or convergence-gate failure. Empirical quantiles use
`higher`; final margin remains unaccepted pending May holdout.

Tap operation counts are **net settled tap steps between consecutive slot
states**, including source-initial to slot 0. The engine API exposes control
iterations, convergence iterations and completion status. Within-solve tap
reversals/event counts are not inferred from these values. Comparisons with
the old frozen result are paired simulation evidence conditional on identical
physical inputs; they do not imply broader empirical causation.
