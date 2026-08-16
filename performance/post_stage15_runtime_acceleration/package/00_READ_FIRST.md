# W02 final M1–M4 production binding

This package binds W02 to the final post-Stage15 comparison: M1 proposed Event30 + Local Repair mobile, M2 Fixed30 mobile, M3 Event30 without Local Repair mobile, and M4 fixed-location ESS mobility ablation. P4 Fixed15 is supplementary only. All four methods share canonical zero-burn-in PRE state `4fd2b4e8a6ef052fd08454f9888ad1e08e2706ed99d1118cac6d96d33c8a5a7b` and the outcome-blind sites MESS01=STA09, MESS02=IDC12, MESS03=STA07, MESS04=STA11.

The launcher prepares or reuses one read-only W02 exogenous source, then runs the four methods concurrently with topology-aware 4 processes × 4 Gurobi threads and `PYTHONHASHSEED=0`. Fresh Exact OpenDSS remains the physical gate before every committed transition.

Bounded actual validation ran 7 of 2016 issues per method; it did not run a full week or the other 11 weeks. The measured contended ETA bottleneck is 2.229 h/week; use 2.3–2.5 h/week for planning. See `../PERFORMANCE_RESULT/` for evidence and rollback instructions.

Run the full W02 episode only when ready:
```bash
cd /home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/performance/post_stage15_runtime_acceleration/package
bash RUN_W02_4POLICY_ACTUAL.sh
```
