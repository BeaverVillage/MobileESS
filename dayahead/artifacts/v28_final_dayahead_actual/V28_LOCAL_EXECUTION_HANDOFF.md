# V28 local execution handoff

The implementation worktree is `/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual`. The full April and May campaigns were not run by Codex.

Current fail-closed integration blocker: the 24-step orchestrator, certificate, resume, freeze, monitor, and finalizer layers are implemented, but a production per-step heavy authority backend that binds the newly frozen V28 LightGBM/C1/V22SR1 inputs into the inherited V16.3 optimizer/OpenDSS context is not yet implemented. Full runs stop before creating a PASS certificate; the non-authority smoke cannot issue one.

Use `V28_LOCAL_EXECUTION_COMMANDS.md` after resolving `V28-BLOCK-001`. Do not bypass the backend gate or synthesize PASS certificates.
