# IEEE8500 one-day operating-point construction — B0 only

**Status: NO_FEASIBLE_ALPHA_ON_FROZEN_GRID. Selected date: 2025-05-21. Selected alpha: null.**

The requested construction and complete frozen-grid screening are finished. No alpha in 1.00, 0.95, ..., 0.00 satisfies all four hard limits. No feasible operating-point authority is asserted. This is a grid-specific result; no claim is made about off-grid values, changed controls, or other dates. FINAL AIDC/STA mapping, PCC overlay, native source and all selection evidence remain unchanged.

## Date and causal inputs

The date is the argmax of the 31 May B0 DAYAHEAD Fresh daily phase-line maxima, with earliest-date tie-breaking preregistered. On 2025-05-21 the maximum is **0.8498557617902092 pu**, line.l10 / phase A / slot 31. Both the summary and phase arrays for each B0 day match the archived member SHA256. Date freeze occurred before construction or alpha screening. B1/B2/B3 result payloads and optimization were not accessed.

VIC1 demand was issued **2025-05-20 17:32:29 AEST**, predispatch sequence 2025052028/run 1; rooftop PV was issued **2025-05-20 18:00:00 AEST**. Both meet the D-1 18:00 cutoff. The 48 half-hour rows were checked directly against each original forecast ZIP and exactly reproduce the 96-slot cached forecast by repetition. Slots use fixed AEST (UTC+10), interval starts 00:00–23:45 and ends 00:15–24:00. Demand peak is 7388.6 MW; PV forecast peak is 2300.042 MW. Actual data is absent from construction.

`m_D(t) = demand_DA(t)/7388.6`. For every native load, nominal scheduled P and Q are `alpha*m_D(t)*P_native` and `alpha*m_D(t)*Q_native`. The original 2306 Variable and 48 Fixed statuses are retained, so assignments are made individually with LoadMult=1. Base definitions are restored after each complete trajectory and audited.

The B0 exogenous PV/background gross peak ratio is **0.0948856356620952 (9.488563566%)**. The denominator is gross native/background demand including its already applied V41R4 factor 1.15, excluding AIDC; the numerator is PV peak, not installed PV capacity. Only this ratio is transferred. IEEE8500 PV peak is `alpha*1022.219083545815` kW, with normalized D-1 rooftop-PV shape, Q=0 and deterministic base-kW proportional allocation to the identical native load bus and phase connection. The old gross-demand-plus-PV formula is not used in IEEE8500.

## Conservation and unchanged resources

Native load totals are **10773.170000 kW / 2700.010911176 kvar**, 2354 loads. Bus, local split-phase leg, upstream primary phase, connection, nominal voltage, native PF and model are audited. Local secondary node 2 is a split-phase leg, not automatically primary phase B. Conservation error across all screened slot/phase totals is at most 1.82e-12 kW/kvar; PF error at positive alpha is at most 2.22e-16.

| Upstream phase | Loads | Native kW | Native kvar | PV peak kW at alpha=1 |
|---|---:|---:|---:|---:|
| A | 852 | 3590.960000 | 899.979410 | 340.730522 |
| B | 780 | 3592.080000 | 900.260109 | 340.836794 |
| C | 722 | 3590.130000 | 899.771393 | 340.651767 |

The selected B0 GPU/IT/PCC/Q arrays are byte-identical to V41R4: 12 AIDC, 780 GPU capacity with the original per-site vector, fixed P/Q schedule and PF=0.95. Four MESS units retain the original zero-P/Q B0 commands and 1200-kWh capacity / 760-kWh initial energy. The current source-bound MESS runtime specifies 300-kW active limit and 400-kVA PCS; the older PCC design reference mentions 700 kVA, which is not substituted for the current runtime limit. All immutable 12×1500-kVA AIDC and 24×750-kVA MESS service PCC transformers are preserved. No resource optimization or rescaling is performed.

## Physical scope and screen

Each alpha starts a clean OpenDSS context and executes 96 chronological B0 snapshots with native regulator/capacitor controls and unchanged settings; native control states carry between slots. All **2016/2016** screened slots converged with control actions complete. Native/PCC static definitions compare unchanged after restoring scheduled load P/Q. Resource objects use existing buses: **4912 buses / 8639 electrical nodes / 1226 transformers / 3703 lines**, including five originally disabled tie lines whose current is verified zero. New objects are 12 AIDC loads and 2354 separate PV generators; MESS external injection remains zero.

Hard limits are 0.95–1.05 pu at every electrical node, line phase current ≤ unchanged NormAmps, all transformer winding phase currents ≤ nameplate current and winding total kVA ≤ nameplate kVA. Both line terminals and every transformer winding are checked. Ground conductors are excluded from phase-current ratios; each winding's total complex terminal power is measured independently. Numerical boundary tolerance is 1e-9. No emergency rating allowance or control retuning is used.

| Alpha | Vmin | Vmax | Line current max pu | TF current max pu | TF kVA max pu | All limits |
|---:|---:|---:|---:|---:|---:|---|
| 1.00 | 0.906248 | 1.062025 | 1.751216 | 0.464458 | 0.463808 | FAIL |
| 0.95 | 0.916437 | 1.061811 | 1.654973 | 0.436269 | 0.437607 | FAIL |
| 0.90 | 0.933214 | 1.061598 | 1.559477 | 0.407846 | 0.413187 | FAIL |
| 0.85 | 0.939845 | 1.060453 | 1.469856 | 0.382168 | 0.388339 | FAIL |
| 0.80 | 0.952777 | 1.061877 | 1.371153 | 0.356702 | 0.363978 | FAIL |
| 0.75 | 0.955584 | 1.062229 | 1.286000 | 0.335773 | 0.341841 | FAIL |
| 0.70 | 0.959997 | 1.062999 | 1.187805 | 0.312208 | 0.318976 | FAIL |
| 0.65 | 0.975207 | 1.064368 | 1.100122 | 0.287954 | 0.295753 | FAIL |
| 0.60 | 0.977058 | 1.066308 | 1.010892 | 0.267357 | 0.274415 | FAIL |
| 0.55 | 0.985617 | 1.070915 | 0.917287 | 0.244516 | 0.251690 | FAIL |
| 0.50 | 0.990691 | 1.067446 | 0.831716 | 0.222555 | 0.229643 | FAIL |
| 0.45 | 0.994588 | 1.068757 | 0.748098 | 0.200881 | 0.208193 | FAIL |
| 0.40 | 0.998670 | 1.069179 | 0.663037 | 0.180385 | 0.187255 | FAIL |
| 0.35 | 1.005258 | 1.067289 | 0.575481 | 0.167134 | 0.166823 | FAIL |
| 0.30 | 1.006039 | 1.060571 | 0.491118 | 0.140294 | 0.145623 | FAIL |
| 0.25 | 1.011610 | 1.053585 | 0.408044 | 0.119617 | 0.124371 | FAIL |
| 0.20 | 1.014619 | 1.056003 | 0.325548 | 0.099489 | 0.103664 | FAIL |
| 0.15 | 1.018838 | 1.057982 | 0.255075 | 0.080135 | 0.083666 | FAIL |
| 0.10 | 1.028464 | 1.060557 | 0.196618 | 0.062037 | 0.064746 | FAIL |
| 0.05 | 1.030916 | 1.055589 | 0.144999 | 0.046918 | 0.049304 | FAIL |
| 0.00 | 1.038218 | 1.058661 | 0.108933 | 0.046714 | 0.049303 | FAIL |

Alpha 1.00 fails voltage and line current limits. The first downward grid point passing line current is **0.55**, but its Vmax is **1.070915190**. The smallest daily Vmax among all tested alphas occurs at **0.25**, **1.053585239 pu**, still above 1.05. Transformer limits pass throughout. Thus decreasing background demand alone does not produce a feasible 96-slot B0 under this exact immutable model and rule.

Independent scalar OpenDSS reads of all 4935 enabled PDElements exactly match vectorized current/power measurements and the saved alpha1 slot0 voltage/line/transformer metrics (maximum difference 0). The native terminal-power numerical residual in that spot check is about 0.002004 kW; input P/Q and PF assertions pass. This residual is reported and is not an additional hard criterion or a relaxation of the requested voltage/current limits. Original voltage-dependent Model1 behavior is retained outside its constant-PQ voltage range.

## Files and freeze

- `SELECTED_DATE_FREEZE.json`, `MAY_B0_FRESH_DAILY_LINE_MAXIMA.csv`: date authority and 31-day B0 evidence.
- `DEMAND_PV_TEMPORAL_PROFILES.csv`, `FORECAST_CAUSALITY_AND_INPUT_BINDING.json`, `PV_PENETRATION_RATIO_AUTHORITY.json`: temporal forecasts, raw ZIP verification and ratio.
- `NATIVE_LOAD_AND_PV_ALLOCATION.csv`, `SPATIAL_PHASE_CONSERVATION_AUDIT.json`, `SPATIAL_PHASE_CONSERVATION_ALL_SCREEN_SLOTS.csv`: load/phase/PF and PV conservation.
- `ALPHA_SCREEN_TABLE.csv`, `SELECTED_ALPHA_AND_B0_STATUS.json`: full descending screen and explicit null selection.
- `B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv`, `B0_DAILY_EXTREMA_WITNESSES.csv`, `screen/alpha_*/B0_ALL_PHASE_ARRAYS.npz`: all slot extrema and phase measurements. There is no selected-alpha 96-slot file because no alpha is feasible.
- `IMMUTABILITY_AND_SOURCE_RECHECK.json`: all **2051** protected source, topology-selection and PCC files match SHA, size and mtime; no V41R4 writes.
- `OPERATING_POINT_FREEZE_MANIFEST.json` and `.sha256`: frozen construction, unsuccessful feasibility screen and evidence. The freeze does not authorize a feasible operating point or B1/B2/B3 execution.
