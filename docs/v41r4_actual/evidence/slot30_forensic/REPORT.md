# May12 B3 slot 30 — Q_ONLY_SEARCH_FAILURE_FEASIBLE_POINT_FOUND

Exact AC trials: 2044 unique Q points; 1159 strict feasible points. Production method/results unchanged.

The original two SLSQP starts both reached their 25-iteration limit without a feasible point. This diagnostic covered the full PCS box with a 5×5×5×5 grid, 256 scrambled Sobol samples, eight derivative-free starts, and three progressively finer neighborhood scales. A feasible witness therefore establishes a search failure, not physical Q-only infeasibility. This is an existence result, not a minimum-deviation certificate.

| MESS | location | P kW | Q min kvar | Q max kvar | original Q | witness Q |
|---|---|---:|---:|---:|---:|---:|
| MESS01 | STA02 | 0.000000000 | -392.314112161 | 392.314112161 | 392.314112161 | 317.6154369464249 |
| MESS02 | STA12 | 300.000000000 | -254.815938129 | 254.815938129 | 103.592718230 | -7.709985212348954 |
| MESS03 | STA08 | 85.425162037 | -389.253474384 | 389.253474384 | -389.253474384 | -350.3499675038673 |
| MESS04 | STA06 | 0.000000000 | -392.314112161 | 392.314112161 | -392.314112161 | -375.2164261983751 |

Maximum absorption: feasible=False; V=[0.957804247, 1.052964509].
Witness: V=[0.975971476, 1.049486764], line=0.644988065, transformer current=0.751002186, transformer kVA=0.617679467.
Two additional clean-prefix replays independently reproduced the witness exactly.

Approved slot-start taps, in the frozen native ordering: [1.025, 0.99375, 1.0125, 1.0, 1.05, 1.025, 1.0375]. Exact binary values are retained in FROZEN_SLOT_AUTHORITY.json. Negative Q means reactive-power absorption. The table shows the PCS interval at fixed P; AC feasibility still depends on the joint Q vector and the native regulator response.

Runtime: 273.57 seconds, including input verification and search. All 536 source/result files checked before and after were unchanged. Production method SHA was unchanged, scheduling optimizer calls were zero, and the campaign continued under the common four-worker cap. Full-precision witnesses, hard-limit measurements and independent revalidations are in RESULT.json and FEASIBLE_WITNESS_AC.npz; trial evidence is in EXACT_AC_TRIALS.json and NATIVE_TRIAL_AUDIT.json.

Every trial replays approved slots 0–29 from a clean engine, verifies every prefix tap state, and uses the same approved slot-30 start state. Only Q at slot 30 changes. No production fallback, tuning or output replacement was performed.

An exact feasible witness disproves physical Q-only infeasibility. Absence of a witness in finite search would be UNRESOLVED; no global impossibility claim is made.
