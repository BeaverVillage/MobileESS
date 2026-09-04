# V28R2 heavy authority backend final report

RESULT CLASSIFICATION: `V28R2_HEAVY_BACKEND_READY_FOR_LOCAL_APRIL_PREFLIGHT`
V28-BLOCK-001: `RESOLVED`

## 1. Starting state

Branch `codex/v28r2-resolve-blockers-heavy-backend`, base `e1680d971e7a2b3b12b4ad92a6c1c47a535340f5`; historical artifacts and raw sources were protected.

## 2–10. Authority and blocker resolution

The 2026-08-29 re-freeze has precedence. PARTIAL/shared work is non-controllable but remains in total reference. P, G, and strict full-node W LightGBM authorities, deterministic reference scheduling, nonnegative reference-delta closure, certified affine C1 LP mapping, and April 30/30 source coverage all pass.

## 11–18. Production backend

One common formulation supplies complete primal schedules. B3 equivalence, schedule freeze, Fresh OpenDSS, fixed-command Actual replay, real PI B3, isolated day subprocesses, measured counters, and recursive cryptographic certificates pass. Actual optimizer calls are zero.

## 19. One-day heavy smoke

The only permitted smoke completed all 30 steps on 2025-04-01: 7 solver calls (Day-Ahead 6, Actual 0, PI 1), ten Fresh OpenDSS trajectories at 96/96, one measured PUE evaluation per trajectory, zero hidden shedding, and workload mass error at or below 1e-9. B3 relative objective range was 4.3626951655564487e-16. No April PASS certificate was issued.

## 20–23. Tests, artifacts, Git, and remaining state

All 71 V28R2 tests pass. Artifact hashes are in `V28R2_ARTIFACT_SHA256.json`; historical/raw preservation passes. The fixed commit sequence is retained with no merge. April full-month PASS, May runner, May final science, and final grid-science authorization remain false until their separate work is completed.

## 24–25. Local execution and monitoring

See `V28R2_LOCAL_APRIL_EXECUTION_COMMANDS.md` for two exact copy-paste WSL commands: one starts setup, source verification, execution, and audit; the other opens the compact 10-second monitor. The runner uses four isolated day processes, four Gurobi threads per child, and 15-minute/96-slot days. The monitor is read-only.

## 26. Q1–Q25

Q1 YES. Q2 YES. Q3 NO. Q4 YES. Q5 NO. Q6 YES. Q7 YES. Q8 YES. Q9 YES. Q10 YES. Q11 YES. Q12 YES. Q13 YES. Q14 YES. Q15 YES. Q16 YES. Q17 YES. Q18 YES. Q19 NO. Q20 YES. Q21 YES. Q22 YES. Q23 NO. Q24 NO. Q25 YES (`APRIL_RUNNER_READY=true`).
