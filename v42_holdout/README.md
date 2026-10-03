# Frozen May B0 zero-margin holdout

Run from the repository root, in this order:

```text
python -X utf8 -m v42_holdout.prepare
python -X utf8 -m v42_holdout.inputs
python -X utf8 -m v42_holdout.planning
python -X utf8 -m v42_holdout.vintages
python -X utf8 -m v42_holdout.realization
python -X utf8 -m v42_holdout.actual
python -X utf8 -m v42_holdout.report
python -X utf8 -m v42_holdout.test_suite
python -X utf8 -m v42_holdout.verify
python -X utf8 -m v42_holdout.verify --manifest
```

This evaluates May 1–31 from the existing frozen May source manifests. Every
April file and parameter remains byte preserved at PR128. Planning uses the
same Q50 nominal reference release, Runtime reserve gamma/kernel, capacity
admission of the unchanged CC4 forecast, current C1 secants and native affine
anchor/sensitivity equation. Its physical reference controls equal the anchor;
the resulting Planning magnitude is checked against 0.95–1.05 pu with no
margin. B0 uses a deterministic grid-blind reference and queue, with no grid
flexibility, MESS, P/Q repair or optimization.

The inherited Planning and physical replay producers are loaded into isolated
namespaces with a narrowly checked AST calendar transform: April date literals
become May, and the month loop includes 31 days. Only OUT/PRIOR routing may be
overridden. The equations, parameters and controller statements are unchanged;
the expanded source is retained under ADAPTED_SOURCE for review. Output files
produced by these inherited routines retain some April-prefixed names inside
the new May namespace. Their day column is the authority. Inherited reference
`May_reads=0` denotes no holdout-outcome input into the reference rule; this May
caller supplies causal May job descriptors and records that explicitly.

All 31 Planning quantities are frozen before the Actual environment is read.
Actual receives only causal submission/completion events from the private
realized-duration environment. Quarter-hour interval-end demand sampling,
half-hour PV repeated twice and quarter-hour-start observed weather interpolation
follow the recorded frozen source rules. Derived daily files cite their monthly
raw authorities; no external raw file is copied into Git or changed.

Actual executes the exact PR128 physical slot-loop AST through its shared
autonomous session. Each day has a fresh source context and sequential state
within that day. Seven native RegControls remain enabled, four capacitors stay
fixed ON, and zero CapControls exist. Planning tap/cap injection is absent.
Settings and capacitor states are checked before and after each solve.

Physical modelability is the existing rule, not a new coverage or result filter.
Missing/invalid source requests remain in an exclusion ledger; modelable jobs
cannot be dropped for capacity or voltage. A modelable job without uniquely
source-backed realized duration stops execution rather than using Q50/walltime
or an invented zero. Requested walltime remains a Runtime feature only.

Any Actual voltage violation gives a margin=0 holdout FAIL. Zero gives a PASS
candidate; convergence and Planning feasibility are reported independently.
The ±0.005 residual coverage is only a reference diagnostic. There is no May
quantile selection, tuning or immediate margin adjustment. FINAL_MARGIN_ACCEPTED
and PROBLEM13_FINAL_VALIDATED remain false because B1/B2/B3 are untested.

The frozen CC4 interface retains its documented retrospective model-selection
and unexported ingestion-receipt limitations; Kestrel request-version history
remains an unverified retrospective proxy. The repository also contains an
earlier May01 development canary. “Holdout” here means May outcomes did not
inform the April calibration or this parameter freeze; it does not claim that
no prior repository development ever inspected any May data.

Full pytest uses the inherited recorded eight-file Windows EOL compatibility
variant and restores the exact PR128 bytes in a finally block. Independent QA
then verifies every BASE Git blob, frozen source and array hash, engine P/Q
readback, source-control logs and every lossless residual CSV point.
