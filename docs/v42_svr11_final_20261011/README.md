# SVR11 official May 2025 campaign

This release continues Draft PR #206 at a26133a with the latest explicit user approval. It retains the original seven SVR banks and Bus82/Bus48, adds Bus86 downstream Line.l77 and Bus62 downstream Line.l61, and runs B0 → B2 → B1 → B3 with 1/3/1/1 workers. Each policy attempts all 31 dates independently of PASS counts.

All eleven banks use three individual finite-rated single-phase transformers and native RegControls. The original seven IEEE123 RegControls remain autonomous; four capacitors remain fixed on; no CapControl or D-STATCOM is used. Taps and queues are never optimization variables or Planning-to-Actual handoffs. The new MV banks retain each original 400 A line and use 960.7108479315374 kVA per phase at 4.16 kV. VReg 120 V, Band 2 V, Delay 30 s, TapDelay 2 s, MaxTapChange 1, and 0.9–1.1 taps are retained.

Minimum installation validation checks exact native wiring, original ratings/properties, independent source-initial contexts, controller readback and a single AC timestamp. Implementation controller regressions exercise synthetic exogenous variation at a single timestamp. No monthly AC-only canary or additional siting/comparison study is performed. These checks do not certify monthly voltage safety. May03 informed this retrospective design; May 2025 is not an independent holdout.

B0 regenerates raw causal FCFS planning and realized operation. Non-B0 workers require a new source-bound forecast-only electrical certificate before Native optimization. Independent native TIME prefix probes regenerate local central secants on the new graph, including all 153 transformer phase rows. The finite response includes discrete autonomous tap response, so this local planning surrogate does not prove nonlinear AC feasibility. Forecast AC and independent chronological Actual Fresh AC evaluate the accepted plan with exact full-node/phase and both-terminal current/kVA evidence. No Actual repair or reoptimization occurs.

B2 and B3 M1/M2 use the unchanged common U4 Anytime engine and cumulative measured Native Runtime of 1,800 seconds per M stage. FULL-feasible UB acceptance is separate from a valid independent global bound/gap. A stages retain the existing approved settings and 5,400-second Native allowance. B3 starts with a freshly optimized A1 and preserves A1→M1→A2→M2 dependencies; historical B1 points or AC results are not substituted. Only the immutable original job-domain roster is used as domain provenance.

`v42_svr11.controller` persists all 124 ledger entries, adopts exact PID/create-time/command/root/source workers, isolates date failures, and advances policies after every date is terminal. Only pre-Native file-sharing/process-start failures receive up to two retries. Any inflight/unknown Native call prevents a zero-budget retry. Global source/hardware integrity failure stops dispatch and records a distinct system error while retaining healthy workers and all evidence.

Runtime root: `D:\v42_svr11_may_20261011`. Entry points:

```powershell
python -B -X utf8 -m v42_svr11.freeze D:\v42_svr11_may_20261011\hardware
python -B -X utf8 -m v42_svr11.prepare raw D:\v42_svr11_may_20261011
python -B -X utf8 -m v42_svr11.regression D:\v42_svr11_may_20261011
python -B -X utf8 -m v42_svr11.prepare release D:\v42_svr11_may_20261011
python -B -X utf8 -m v42_svr11.watchdog D:\v42_svr11_may_20261011
```

The read-only dashboard is `http://localhost:8796`, with five-second refresh, policy/date summaries, live process state, measured Native Runtime, separate bounds, and clickable physical detail. Existing hourly Codex recovery and five-minute Windows tasks are repointed to this release, preserving their old definitions. Scheduling registration is distinct from observed scheduled execution.

The runtime `CAMPAIGN_MANIFEST.json` binds executable source SHA, hardware/scenario/thermal receipts and raw input receipts. `CAMPAIGN_LEDGER.json`, `REPORT.json`, `REPORT.md`, process receipts and scheduled-run receipts provide live evidence. Published snapshots must explicitly label incomplete campaigns; the final report is produced only when all 124 dates have terminal results. SVR7/SVR9 artifacts and PR #206 remain untouched.
