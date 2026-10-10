# Source35 original full-LP diagnosis and external observer proposal

This additive evidence package preserves a read-only comparison of the May01,
May02 and May03 Source35 original full-LP calls, the first comparison-harness
failure, and the subsequent external observer prototype tests. The diagnosis
receipt PASS validates its listed evidence comparisons. The test receipt PASS
validates 35 simulated observer tests with actual Gurobi model and Native entry
points denied. Neither receipt certifies a campaign date, an improved scientific
bound, a final 3% Global Gap, or a production observer implementation.

## Actual saved Source35 evidence

The original calls used Method6, LPWarmStart2, Crossover-1, Threads1 and the
original 300-second Native cap. The current same-day F1 complete primal point,
dual vector and basis were admitted; the saved original full-domain replay
receipts report PASS. All three calls ended with status11, SolCount0 and no
recorded exception, after the original Runtime callback cap:

| Date | Saved Native Runtime (s) | Full-LP/F1 independently certified LB | Nonzero dual rows |
| --- | ---: | ---: | ---: |
| May01 | 300.88899993896484 | -492.54522661241856 | 9463 |
| May02 | 300.8159999847412 | -406.1207858228788 | 9518 |
| May03 | 301.01900005340576 | -591.3602997475448 | 9518 |

The full-LP and current F1 certificate mathematical fields agree per date;
diagnostic `check_wall_seconds` is excluded from that equality. All three have
nonzero dual certificates and no saved `LP_DUAL_UNAVAILABLE.json`. SolCount0
therefore does not establish that Pi was unavailable. The exact initial bound
selection remains the original zero signed dual; the full-LP calls did not
improve that selected bound.

The frozen original diagnostic code has no PDHG callback branch and does not
read PDHGIterCount at completion. Saved SIMPLEX iteration0 and header-only
Native logs cannot establish actual PDHG iteration counts, residuals, or which
phase consumed the cap. The cap interruption and this observability gap are
established. A numerical failure or the precise solver phase is not established.
The possibility that the returned Pi remained the starting basis Pi while an
unfinished PDHG/crossover iterate progressed is an inference only.

## Official warm-start semantics and the future decision

Gurobi documents PDHG primal/dual starts, including vectors derived from a
basis. LPWarmStart2 transforms starts for the presolved model. Method2 with
complete warm vectors or a basis uses crossover without barrier iterations;
that is a possible future computational candidate, with no measured benefit
or 300-second guarantee here. [Official LPWarmStart documentation](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-LPWarmStart).

Gurobi13.0.2 includes a PDHG dual-start sign correction. The saved calls already
used13.0.2. [Official fixed bugs](https://docs.gurobi.com/projects/optimizer/en/current/reference/releasenotes/fixedbugs.html).

Keep the separately qualified Source36 RMP policy and evaluate its actual
behavior. No observer integration or new repair source is authorized by this
package. A later guarded observer could collect PDHG iterations and residuals
at the single existing original full-LP call, retaining original Runtime and
UNKNOWN failure guards before delegation. Official fields are listed in
[callback codes](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html)
and [PDHGIterCount](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#attr-PDHGIterCount).
Such scalar diagnostics must remain separate from Native accounting,
independent dual certificates, LB/UB and Global Gap.

## Preserved failure and test qualification limits

`INITIAL_HARNESS_01` is the initial producer and its partial raw May01 snapshot.
Its actual exit1 occurred because a whole-dictionary comparison included the
diagnostic checker wall time. The recorded mathematical fields match. The
corrected diagnosis02 excludes only `check_wall_seconds`; it does not weaken
any mathematical-field comparison. The initial failure receipt is retained
exactly; it is not represented as an independently redirected full stderr log.

`DIAGNOSIS_QUALIFIED_02` includes the final receipt, all three raw requests,
Native ledgers, call/warm-start/admission/selection and replay/certificate
receipts, original frozen source copies and historical draft. State archives
and matrices remain referenced by saved hashes; this package performs no fresh
scientific matrix or rational-checker replay. The historical draft's statement
that tests had not run describes that draft's earlier creation time.

`EXTERNAL_OBSERVER_PROPOSAL_TESTS` preserves the exact runner, test source,
JUnit XML and receipt for 35 passing simulated tests. Actual Gurobi Model,
retained Model.__init__ and optimize were denied; attempted entries were empty.
The JUnit XML is the existing raw test artifact. Original runner stdout was not
separately redirected; this package does not invent a raw terminal log.
`EXTERNAL_OBSERVER_SOURCE` is the exact tested prototype source. Tests cover
PDHG fields, phase separation, unknown/nonfinite values, model/closed/authority
guards, original callback-first behavior, accounting preservation and bounded
publication timing. They prove no actual solver callback or performance gain.

The external prototype is explicitly not production-admission qualified.
Future production work requires sealed current request/case/source/model and
single-call bindings, retained callable-code checks, original admission and
Runtime/UNKNOWN guards, and bounded per-field error aggregation. Public
prototype bindings are mutable and its diagnostic fault list is unbounded.
No model construction, Native call, physical constraint or precision change,
extra budget, production integration, process mutation or Git action occurred
while assembling this package.

## Inventory and byte preservation

`COPY_PROVENANCE.json` records exact origin/destination bytes and SHA256;
`SHA_INVENTORY.json` seals every payload file except itself. Package-local
`.gitattributes` disables text conversion for these immutable evidence copies.
It affects only this new documentation folder. The earlier sealed Source35,
Source36 and monitor documentation inventories are unchanged.
