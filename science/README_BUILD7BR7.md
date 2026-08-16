BUILD7BR7 — EXACT DOMAIN SPARSIFICATION + TRUE RUNTIME PROFILER

Gap policy is unchanged:
- objectives 1–4: exact 0% when solved, or skipped only when an exact mathematical
  lower-bound certificate proves their optimum;
- objective 5 (economic): 1.5% relative MIP gap for the current production target.

BR7 performs exact speed improvements only:
1. reachable-state stay variables only;
2. reachable-state Pcharge/Pdischarge/Q variables only;
3. omit identically zero mobility-flow rows;
4. omit service-transformer kVA constraints for service/horizon pairs with no possible
   connected MESS injection;
5. pre-index move binaries by (MESS,horizon) so SOC and extraction no longer rescan
   the entire ~100k move dictionary hundreds of times;
6. eliminate workload-debt variables when the exact lex-zero certificate proves the
   workload debt is identically zero;
7. preserve BR6 exact route pruning, warm start, sparse grid, 14-thread trial, and all
   physical/no-look-ahead contracts.

The former wrapper printed [8], [9], [10] before calling main.py, so the screen could
appear to be 'stuck at [10]' while the model was actually still being built or solved.
BR7 writes real [RUNTIME ...] markers from inside main.py and continuously writes
BUILD7BR7_RUNTIME_TIMING_LIVE.json.
