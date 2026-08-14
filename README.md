# MobileESS

Mobile energy storage system rolling-horizon optimization research code.

This branch carries the R25R Stage-1 exact path-decomposition implementation.
Each rolling issue has a 54-slot, five-minute horizon and commits only its first
slot. The frozen Stage-1 acceptance rule is a globally certified relative gap of
at most 3%, followed by the numerical, causal, and Fresh OpenDSS gates.

## Repository layout

- `science/`: authoritative model, decomposition solver, contracts, proofs, and
  embedded frozen authorities.
- `driver_r25r_stage1_resume136.py`: validates the R25P/R25Q parent chain and
  resumes the causal run at issue 136.
- `R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz`: byte-frozen science bundle used
  by the resume driver.
- `HANDOFF.md`: current runtime state, root-cause record, and next work.

Runtime outputs, frozen parent result archives, and self-extracting `.run`
packages are intentionally kept outside Git.

## Validation

Use the project WSL Python environment:

```bash
cd science
/home/jaewon/miniconda3/envs/power_v61/bin/python release_self_test.py
```

The resume driver additionally requires its exact R25P and R25Q parent runtime
archives under `~/mobile_ess_work/frozen_artifacts/`; their names and SHA-256
digests are fail-closed in the driver.
